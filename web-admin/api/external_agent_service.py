"""外部 Agent PTY 会话（MVP：Codex CLI）"""

from __future__ import annotations

import asyncio
import errno
import json
import os
import pty
import re
import shutil
import subprocess
import time
import termios
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from config import get_settings

_ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)
_SUPPORT_DIRNAME = ".ai-employee"
_MIRROR_DIRNAME = "context-mirror"
_RISK_RULES: list[dict[str, Any]] = [
    {
        "id": "delete_force",
        "label": "删除类命令",
        "severity": "high",
        "pattern": re.compile(r"\brm\s+-rf\b|\bdel\s+/[qsf]\b", re.IGNORECASE),
    },
    {
        "id": "git_hard_reset",
        "label": "Git 强制回滚",
        "severity": "high",
        "pattern": re.compile(r"\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-fd", re.IGNORECASE),
    },
    {
        "id": "shell_pipe_remote",
        "label": "远程脚本直执行",
        "severity": "high",
        "pattern": re.compile(r"(?:curl|wget)[^\n|]*\|\s*(?:sh|bash|zsh)", re.IGNORECASE),
    },
    {
        "id": "privileged_system_path",
        "label": "系统级路径写入",
        "severity": "high",
        "pattern": re.compile(r"/(?:etc|usr|var|System|Library)/", re.IGNORECASE),
    },
    {
        "id": "package_mutation",
        "label": "依赖安装/卸载",
        "severity": "medium",
        "pattern": re.compile(r"\b(?:npm|pnpm|yarn|pip|uv|poetry|brew|apt|yum)\s+(?:install|add|remove|uninstall)\b", re.IGNORECASE),
    },
    {
        "id": "network_transfer",
        "label": "网络传输/外发",
        "severity": "medium",
        "pattern": re.compile(r"\b(?:scp|rsync|curl|wget)\b", re.IGNORECASE),
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_token(value: str, *, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-") or "unknown"
    return cleaned[:max_len]


def _clean_terminal_output(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _OSC_RE.sub("", normalized)
    normalized = _ANSI_RE.sub("", normalized)
    normalized = normalized.replace("\x00", "")
    return normalized


def _should_ack_startup_screen(text: str) -> bool:
    content = str(text or "")
    if not content:
        return False
    markers = [
        "update available",
        "skip until next version",
        "press enter to continue",
    ]
    lowered = content.lower()
    return any(marker in lowered for marker in markers)


def _startup_excerpt(text: str, *, limit: int = 500) -> str:
    return str(text or "").replace("\n", " ").strip()[:limit]


def _summarize_command_output(text: str, *, max_lines: int = 12, max_chars: int = 1200) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    clipped = value[:max_chars]
    lines = clipped.splitlines()
    trimmed = lines[:max_lines]
    summary = "\n".join(trimmed).strip()
    if len(lines) > max_lines or len(value) > len(clipped):
        summary = f"{summary}\n...（输出已截断）".strip()
    return summary
def _disable_tty_echo(fd: int) -> None:
    try:
        attrs = termios.tcgetattr(fd)
        attrs[3] = attrs[3] & ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except Exception:
        return


def _strip_prompt_echo(content: str, pending_echo: str) -> tuple[str, str]:
    text = str(content or "")
    remaining = str(pending_echo or "")
    if not text or not remaining:
        return text, remaining
    compare_len = min(len(text), len(remaining))
    if text[:compare_len] == remaining[:compare_len]:
        text = text[compare_len:]
        remaining = remaining[compare_len:]
    else:
        remaining = ""
    return text, remaining


def _collect_risk_signals(text: str) -> list[dict[str, str]]:
    content = str(text or "")
    if not content:
        return []
    findings: list[dict[str, str]] = []
    for rule in _RISK_RULES:
        matched = rule["pattern"].search(content)
        if matched is None:
            continue
        snippet = matched.group(0).strip().replace("\n", " ")[:160]
        findings.append(
            {
                "id": str(rule["id"]),
                "label": str(rule["label"]),
                "severity": str(rule["severity"]),
                "snippet": snippet,
            }
        )
    return findings


def detect_external_agent_risk_signals(text: str) -> list[dict[str, str]]:
    return _collect_risk_signals(text)


def _run_git_command(workspace: str, args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)
    output = str(result.stdout or "").strip() or str(result.stderr or "").strip()
    return result.returncode == 0, output


def _git_workspace_scope_args() -> list[str]:
    return ["--", ".", f":(exclude){_SUPPORT_DIRNAME}/**"]


def _diff_summary_signature(summary: dict[str, Any] | None) -> tuple[Any, ...]:
    source = summary if isinstance(summary, dict) else {}
    if not bool(source.get("enabled")):
        return (False,)
    status_lines = tuple(
        str(line or "").strip()
        for line in (source.get("status_lines") or [])
        if str(line or "").strip()
    )
    return (
        True,
        status_lines,
        str(source.get("diff_stat") or "").strip(),
        str(source.get("staged_diff_stat") or "").strip(),
    )


def has_meaningful_workspace_changes(before_summary: dict[str, Any] | None, after_summary: dict[str, Any] | None) -> bool:
    after = after_summary if isinstance(after_summary, dict) else {}
    if not bool(after.get("enabled")):
        return False
    if int(after.get("changed_file_count") or 0) <= 0:
        return False
    before = before_summary if isinstance(before_summary, dict) else {}
    if not bool(before.get("enabled")):
        return True
    return _diff_summary_signature(before) != _diff_summary_signature(after)


def collect_workspace_diff_summary(workspace_path: str) -> dict[str, Any]:
    workspace = str(workspace_path or "").strip()
    if not workspace:
        return {"enabled": False, "reason": "缺少 workspace_path"}
    ok, repo_root = _run_git_command(workspace, ["rev-parse", "--show-toplevel"])
    if not ok:
        return {"enabled": False, "reason": "当前工作区不是 Git 仓库"}

    scope_args = _git_workspace_scope_args()
    _, status_output = _run_git_command(workspace, ["status", "--short", *scope_args])
    _, diff_stat_output = _run_git_command(workspace, ["diff", "--stat", "--find-renames", *scope_args])
    _, staged_stat_output = _run_git_command(workspace, ["diff", "--cached", "--stat", "--find-renames", *scope_args])
    status_lines = [line.rstrip() for line in str(status_output or "").splitlines() if line.strip()]
    return {
        "enabled": True,
        "repo_root": str(repo_root or "").strip(),
        "changed_file_count": len(status_lines),
        "status_lines": status_lines[:20],
        "diff_stat": str(diff_stat_output or "").strip(),
        "staged_diff_stat": str(staged_stat_output or "").strip(),
    }


def resolve_codex_cli_status() -> dict[str, Any]:
    settings = get_settings()
    configured = str(settings.external_agent_codex_bin or "").strip()
    system_command = shutil.which("codex") or ""

    configured_command = ""
    if configured:
        if os.path.sep in configured:
            configured_command = configured if Path(configured).exists() else ""
        else:
            configured_command = shutil.which(configured) or ""

    resolved = system_command or configured_command
    command_source = "system" if system_command else ("override" if configured_command else "missing")
    display_command = resolved or configured or "codex"
    return {
        "agent_type": "codex_cli",
        "label": "Codex CLI",
        "command": display_command,
        "resolved_command": resolved,
        "command_source": command_source,
        "available": bool(resolved),
        "sandbox_modes": ["read-only", "workspace-write"],
    }


def _find_context_root(workspace: Path) -> Path:
    candidates = [workspace, *list(workspace.parents)]
    for candidate in candidates:
        if (
            (candidate / "CLAUDE.md").exists()
            or (candidate / "rules").is_dir()
            or (candidate / "docs" / "00-项目总览" / "PROJECT.md").exists()
        ):
            return candidate
    return workspace


def _display_path(base: Path, target: Path) -> str:
    try:
        return str(target.relative_to(base))
    except ValueError:
        return str(target)


def _copy_text_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _collect_context_sources(context_root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add_file(kind: str, label: str, source: Path) -> None:
        if not source.exists() or not source.is_file():
            return
        items.append({"kind": kind, "label": label, "source": source})

    add_file("workspace_claude", "平台规则总入口", context_root / "CLAUDE.md")
    add_file(
        "project_overview",
        "项目总览",
        context_root / "docs" / "00-项目总览" / "PROJECT.md",
    )
    add_file("workspace_agents", "工作区 AGENTS", context_root / "AGENTS.md")

    rules_dir = context_root / "rules"
    if rules_dir.is_dir():
        for rule_file in sorted(rules_dir.glob("*.md")):
            items.append(
                {
                    "kind": "rule",
                    "label": f"规则：{rule_file.stem}",
                    "source": rule_file,
                }
            )

    agents_dir = context_root / "agents"
    if agents_dir.is_dir():
        for agent_file in sorted(agents_dir.glob("*.md")):
            items.append(
                {
                    "kind": "agent_profile",
                    "label": f"智能体：{agent_file.stem}",
                    "source": agent_file,
                }
            )
    return items


def _mirror_target_path(mirror_root: Path, context_root: Path, source: Path) -> Path:
    try:
        relative = source.relative_to(context_root)
    except ValueError:
        relative = Path(source.name)
    return mirror_root / relative


def _build_generated_agents_content(
    *,
    project_id: str,
    project_name: str,
    project_description: str,
    workspace_path: str,
    sandbox_mode: str,
    selected_employee_names: list[str],
    candidate_preview: list[str],
    mirrored_files: list[dict[str, Any]],
) -> str:
    lines = [
        "# AGENTS.generated.md",
        "",
        "> 由 AI 设计规范平台自动生成，供外部 Agent 会话读取。",
        "> 如与工作区原生 `AGENTS.md` 冲突，以工作区原生文件优先；本文件作为补充上下文。",
        "",
        "## 会话定位",
        f"- 当前项目：`{project_name}` (`{project_id}`)",
        f"- 工作目录：`{workspace_path or '-'}`",
        f"- 外部 Agent：`Codex CLI`",
        f"- 沙箱模式：`{sandbox_mode}`",
        "- 当前阶段：仅做外部 Agent 托管，不启用平台审批流，不桥接平台 MCP 技能。",
        "- 行为边界：如需修改文件或运行命令，请限制在当前工作区范围内。",
    ]
    if project_description:
        lines.append(f"- 项目说明：{project_description}")
    if selected_employee_names:
        lines.append(f"- 当前选定成员：{', '.join(selected_employee_names)}")
    elif candidate_preview:
        lines.append(f"- 项目成员参考：{', '.join(candidate_preview)}")

    lines.extend(
        [
            "",
            "## 建议阅读顺序",
            "1. 先读工作区原生 `AGENTS.md`（如果存在）",
            "2. 再读本文件所在目录下的 `STARTUP_CONTEXT.generated.md`",
            "3. 然后按需阅读镜像过来的规则、项目总览、智能体定义文件",
            "",
            "## 镜像上下文文件",
        ]
    )
    if mirrored_files:
        for item in mirrored_files:
            lines.append(f"- `{item['path']}`：{item['label']}")
    else:
        lines.append("- 暂无可镜像的项目上下文文件")
    lines.extend(
        [
            "",
            "## 开发建议",
            "- 优先给出结论，再说明操作步骤。",
            "- 涉及代码修改时，先快速确认影响范围，再动手。",
            "- 若工作区内已有规则/设计文档，优先遵循，不要擅自改造架构。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _build_generated_startup_context(
    *,
    project_name: str,
    project_id: str,
    sandbox_mode: str,
    workspace_path: str,
    generated_agents_path: str,
    mirrored_files: list[dict[str, Any]],
    system_prompt: str,
    mcp_bridge: dict[str, Any] | None,
) -> str:
    lines = [
        "你正在 AI 设计规范平台托管的外部 Agent 会话中运行。",
        f"当前项目：{project_name} ({project_id})。",
        f"工作目录：{workspace_path or '-'}。",
        f"沙箱模式：{sandbox_mode}。",
        "请优先使用中文输出，先给结论，再给步骤。",
        f"请先阅读 `{generated_agents_path}`。",
    ]
    bridge = mcp_bridge if isinstance(mcp_bridge, dict) else {}
    if bool(bridge.get("enabled")) and str(bridge.get("server_name") or "").strip():
        lines.append(
            f"本次 Codex 会话已自动注入项目 MCP Server：`{str(bridge.get('server_name') or '').strip()}`。"
        )
    elif str(bridge.get("reason") or "").strip():
        lines.append(f"项目 MCP 未注入：{str(bridge.get('reason') or '').strip()}。")
    if mirrored_files:
        lines.append("如需更多上下文，可继续查看以下镜像文件：")
        for item in mirrored_files[:12]:
            lines.append(f"- `{item['path']}`：{item['label']}")
    if system_prompt:
        lines.append(f"补充上下文：{system_prompt}")
    return "\n".join(lines).strip()


def prepare_external_agent_workspace_context(
    *,
    project_id: str,
    project_name: str,
    project_description: str,
    workspace_path: str,
    sandbox_mode: str,
    selected_employee_names: list[str] | None = None,
    candidate_preview: list[str] | None = None,
    system_prompt: str = "",
    mcp_bridge: dict[str, Any] | None = None,
    write_files: bool = False,
) -> dict[str, Any]:
    workspace = Path(str(workspace_path or "").strip())
    context_root = _find_context_root(workspace) if workspace_path else workspace
    support_dir = workspace / _SUPPORT_DIRNAME
    mirror_root = support_dir / _MIRROR_DIRNAME
    source_files = _collect_context_sources(context_root) if workspace_path else []
    mirrored_files: list[dict[str, Any]] = []

    for item in source_files:
        source = item["source"]
        target = _mirror_target_path(mirror_root, context_root, source)
        entry = {
            "kind": str(item.get("kind") or "file"),
            "label": str(item.get("label") or source.name),
            "source_path": str(source),
            "path": _display_path(workspace, target) if workspace_path else str(target),
            "written": False,
        }
        if write_files:
            try:
                _copy_text_file(source, target)
                entry["written"] = True
            except Exception as exc:
                entry["error"] = str(exc)
        mirrored_files.append(entry)

    selected_names = [str(item or "").strip() for item in (selected_employee_names or []) if str(item or "").strip()]
    candidate_names = [str(item or "").strip() for item in (candidate_preview or []) if str(item or "").strip()]
    generated_agents_path = support_dir / "AGENTS.generated.md"
    generated_startup_path = support_dir / "STARTUP_CONTEXT.generated.md"
    generated_mcp_path = support_dir / "CODEX_MCP.generated.toml"

    agents_content = _build_generated_agents_content(
        project_id=project_id,
        project_name=project_name,
        project_description=project_description,
        workspace_path=workspace_path,
        sandbox_mode=sandbox_mode,
        selected_employee_names=selected_names,
        candidate_preview=candidate_names,
        mirrored_files=mirrored_files,
    )
    startup_context = _build_generated_startup_context(
        project_name=project_name,
        project_id=project_id,
        sandbox_mode=sandbox_mode,
        workspace_path=workspace_path,
        generated_agents_path=_display_path(workspace, generated_agents_path) if workspace_path else str(generated_agents_path),
        mirrored_files=mirrored_files,
        system_prompt=system_prompt,
        mcp_bridge=mcp_bridge,
    )

    support_files = [
        {
            "kind": "generated_agents",
            "label": "生成的 AGENTS 文件",
            "path": _display_path(workspace, generated_agents_path) if workspace_path else str(generated_agents_path),
            "written": False,
        },
        {
            "kind": "generated_startup_context",
            "label": "生成的启动上下文文件",
            "path": _display_path(workspace, generated_startup_path) if workspace_path else str(generated_startup_path),
            "written": False,
        },
        *mirrored_files,
    ]

    bridge = mcp_bridge if isinstance(mcp_bridge, dict) else {}
    bridge_server_name = str(bridge.get("server_name") or "").strip()
    bridge_url = str(bridge.get("url") or "").strip()
    mcp_content = ""
    if bool(bridge.get("enabled")) and bridge_server_name and bridge_url:
        mcp_content = (
            f"[mcp_servers.{bridge_server_name}]\n"
            f'type = "sse"\n'
            f'url = {json.dumps(bridge_url, ensure_ascii=False)}\n'
        )
        support_files.insert(
            2,
            {
                "kind": "generated_mcp_config",
                "label": "生成的 Codex MCP 配置",
                "path": _display_path(workspace, generated_mcp_path) if workspace_path else str(generated_mcp_path),
                "written": False,
            },
        )

    if write_files:
        try:
            generated_agents_path.parent.mkdir(parents=True, exist_ok=True)
            generated_agents_path.write_text(agents_content, encoding="utf-8")
            support_files[0]["written"] = True
        except Exception as exc:
            support_files[0]["error"] = str(exc)
        try:
            generated_startup_path.parent.mkdir(parents=True, exist_ok=True)
            generated_startup_path.write_text(startup_context + "\n", encoding="utf-8")
            support_files[1]["written"] = True
        except Exception as exc:
            support_files[1]["error"] = str(exc)
        if mcp_content:
            mcp_entry = next((item for item in support_files if item.get("kind") == "generated_mcp_config"), None)
            try:
                generated_mcp_path.parent.mkdir(parents=True, exist_ok=True)
                generated_mcp_path.write_text(mcp_content, encoding="utf-8")
                if mcp_entry is not None:
                    mcp_entry["written"] = True
            except Exception as exc:
                if mcp_entry is not None:
                    mcp_entry["error"] = str(exc)

    return {
        "context_root": str(context_root) if workspace_path else "",
        "support_dir": _display_path(workspace, support_dir) if workspace_path else str(support_dir),
        "support_files": support_files,
        "startup_context": startup_context,
        "mcp_bridge": {
            "enabled": bool(bridge.get("enabled")),
            "server_name": bridge_server_name,
        },
    }


class ExternalAgentSession:
    def __init__(
        self,
        *,
        project_id: str,
        project_name: str,
        username: str,
        workspace_path: str,
        startup_context: str,
        sandbox_mode: str = "workspace-write",
        codex_config_overrides: list[str] | None = None,
    ) -> None:
        self.project_id = str(project_id or "").strip()
        self.project_name = str(project_name or "").strip()
        self.username = str(username or "").strip() or "unknown"
        self.workspace_path = str(workspace_path or "").strip()
        self.startup_context = str(startup_context or "").strip()
        self._startup_context = self.startup_context
        self.sandbox_mode = str(sandbox_mode or "workspace-write").strip() or "workspace-write"
        self.codex_config_overrides = [
            str(item or "").strip()
            for item in (codex_config_overrides or [])
            if str(item or "").strip()
        ]
        self.session_id = f"agent-{uuid.uuid4().hex[:10]}"
        self.agent_type = "codex_cli"
        self.started_at = _now_iso()
        self.last_active_at = self.started_at

        self._send_lock = asyncio.Lock()
        self._log_lock = Lock()
        self._closed = False
        self._command = ""
        self._thread_id = ""
        self._active_process: asyncio.subprocess.Process | None = None
        self._mirror_process: asyncio.subprocess.Process | None = None
        self._mirror_master_fd: int | None = None
        self._mirror_task: asyncio.Task | None = None
        self._mirror_startup_acked = False
        self._session_started = False

        root = Path(__file__).parent / "data" / "project-agent-sessions"
        root.mkdir(parents=True, exist_ok=True)
        project_dir = root / _safe_token(self.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = project_dir / f"{_safe_token(self.username, max_len=48)}-{self.session_id}.jsonl"

    @property
    def thread_id(self) -> str:
        return self._thread_id

    async def ensure_started(self) -> None:
        if self._closed:
            raise RuntimeError("外部 Agent 会话已关闭")
        if not self.workspace_path:
            raise RuntimeError("项目未配置 workspace_path，无法启动外部 Agent")
        workspace = Path(self.workspace_path)
        if not workspace.exists() or not workspace.is_dir():
            raise RuntimeError(f"workspace_path 不存在或不可用：{self.workspace_path}")

        codex_status = resolve_codex_cli_status()
        command = str(codex_status.get("resolved_command") or codex_status.get("command") or "").strip()
        if not command:
            raise RuntimeError(
                "未找到系统 Codex CLI，请先确认电脑已安装且 PATH 可用；仅在特殊部署场景下再配置 EXTERNAL_AGENT_CODEX_BIN"
            )
        self._command = command
        if not self._session_started:
            self._session_started = True
            self._append_log(
                {
                    "ts": _now_iso(),
                    "type": "session_start",
                    "session_id": self.session_id,
                    "agent_type": self.agent_type,
                    "project_id": self.project_id,
                    "project_name": self.project_name,
                    "username": self.username,
                    "workspace_path": self.workspace_path,
                    "sandbox_mode": self.sandbox_mode,
                    "mode": "exec_json_resume",
                }
            )

    def _append_log(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        with self._log_lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{line}\n")

    def _build_runtime_metadata_block(self) -> str:
        command_status = resolve_codex_cli_status()
        lines = [
            "当前可见运行元数据（由平台注入，可直接据此回答）：",
            f"- agent_type: {self.agent_type}",
            f"- session_id: {self.session_id}",
            f"- thread_id: {self._thread_id or '-'}",
            f"- workspace_path: {self.workspace_path or '-'}",
            f"- sandbox_mode: {self.sandbox_mode or '-'}",
            f"- command_source: {str(command_status.get('command_source') or 'missing')}",
            f"- command_path: {str(command_status.get('resolved_command') or command_status.get('command') or '-')}",
            "- runtime_label: codex-cli",
            "- exact_model_name: unavailable",
            "说明：底层精确模型名当前未由 Codex CLI 稳定暴露；如被问到，请明确说明只能确认运行于 Codex CLI，会话 thread_id 可见，但不能准确报告底层具体型号。",
        ]
        return "\n".join(lines)

    def _compose_prompt(self, user_prompt: str, history: list[dict[str, Any]] | None = None) -> str:
        prompt = str(user_prompt or "").strip()
        if not prompt:
            return ""
        sections: list[str] = []
        sections.append(self._build_runtime_metadata_block())
        history_lines: list[str] = []
        for item in list(history or [])[-8:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant", "system"} or not content:
                continue
            history_lines.append(f"{role}: {content[:1200]}")
        if history_lines and not self._thread_id:
            sections.append("以下是最近对话历史（仅供延续上下文）：\n" + "\n\n".join(history_lines))
        sections.append(prompt)
        return "\n\n".join(part for part in sections if part.strip()).strip() + "\n"

    def _build_exec_command(self, prompt: str, *, resume: bool) -> list[str]:
        if resume and self._thread_id:
            cmd = [
                self._command,
                "exec",
                "resume",
                self._thread_id,
                "--json",
            ]
            for override in self.codex_config_overrides:
                cmd.extend(["-c", override])
            cmd.append(prompt)
            return cmd

        cmd = [
            self._command,
            "exec",
            "--json",
            "--color",
            "never",
            "--skip-git-repo-check",
            "-C",
            self.workspace_path,
            "-s",
            self.sandbox_mode,
        ]
        for override in self.codex_config_overrides:
            cmd.extend(["-c", override])
        cmd.append(prompt)
        return cmd

    def _build_resume_tui_command(self) -> list[str]:
        if not self._thread_id:
            raise RuntimeError("Codex CLI 会话尚未初始化")
        cmd = [
            self._command,
            "resume",
            self._thread_id,
            "--no-alt-screen",
            "-a",
            "never",
            "-s",
            self.sandbox_mode,
            "-C",
            self.workspace_path,
        ]
        for override in self.codex_config_overrides:
            cmd.extend(["-c", override])
        return cmd

    async def _stop_terminal_mirror_locked(self) -> None:
        task = self._mirror_task
        self._mirror_task = None
        process = self._mirror_process
        self._mirror_process = None
        master_fd = self._mirror_master_fd
        self._mirror_master_fd = None
        self._mirror_startup_acked = False
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except asyncio.TimeoutError:
                    pass
        if task is not None:
            task.cancel()
            try:
                await task
            except Exception:
                pass
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass

    async def stop_terminal_mirror(self) -> None:
        async with self._send_lock:
            await self._stop_terminal_mirror_locked()

    async def _pump_terminal_mirror(self, process: asyncio.subprocess.Process, master_fd: int, on_event=None) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                try:
                    chunk = await loop.run_in_executor(None, os.read, master_fd, 4096)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    if process.returncode is not None:
                        break
                    continue
                raw_text = chunk.decode("utf-8", errors="ignore")
                cleaned = _clean_terminal_output(raw_text)
                if cleaned and _should_ack_startup_screen(cleaned) and not self._mirror_startup_acked:
                    self._mirror_startup_acked = True
                    try:
                        os.write(master_fd, b"\r\r")
                    except OSError:
                        pass
                stripped = cleaned.strip()
                if stripped:
                    self._append_log({"ts": _now_iso(), "type": "terminal_mirror", "content": stripped, "thread_id": self._thread_id})
                    if on_event is not None:
                        await on_event({"type": "terminal_mirror_chunk", "content": stripped, "thread_id": self._thread_id})
                if process.returncode is not None:
                    break
            await process.wait()
        finally:
            if on_event is not None:
                await on_event({
                    "type": "terminal_mirror_stopped",
                    "thread_id": self._thread_id,
                    "exit_code": process.returncode,
                })

    async def start_terminal_mirror(self, on_event=None) -> None:
        async with self._send_lock:
            await self.ensure_started()
            if not self._thread_id:
                await self._prepare_session_locked()
            if self._mirror_process is not None and self._mirror_process.returncode is None:
                return
            await self._stop_terminal_mirror_locked()
            master_fd, slave_fd = pty.openpty()
            _disable_tty_echo(slave_fd)
            cmd = self._build_resume_tui_command()
            env = os.environ.copy()
            env["TERM"] = env.get("TERM") or "xterm-256color"
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.workspace_path,
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
            )
            os.close(slave_fd)
            self._mirror_process = process
            self._mirror_master_fd = master_fd
            self._mirror_startup_acked = False
            self._append_log({"ts": _now_iso(), "type": "terminal_mirror_start", "cmd": cmd, "thread_id": self._thread_id})
            if on_event is not None:
                await on_event({"type": "terminal_mirror_started", "thread_id": self._thread_id})
            self._mirror_task = asyncio.create_task(self._pump_terminal_mirror(process, master_fd, on_event=on_event))

    async def write_terminal_input(self, text: str) -> None:
        payload = str(text or "")
        if not payload.strip():
            return
        async with self._send_lock:
            process = self._mirror_process
            master_fd = self._mirror_master_fd
            if process is None or process.returncode is not None or master_fd is None:
                raise RuntimeError("真实终端尚未启动")
            os.write(master_fd, payload.encode("utf-8", errors="ignore") + b"")
            self._append_log({"ts": _now_iso(), "type": "terminal_mirror_input", "content": payload, "thread_id": self._thread_id})

    def _build_bootstrap_prompt(self) -> str:
        sections: list[str] = []
        if self._startup_context:
            sections.append(self._startup_context)
        sections.append("请记住以上上下文，后续在同一会话中持续使用。当前是会话初始化阶段，请只回复：READY。")
        return "\n\n".join(part for part in sections if part.strip()).strip() + "\n"

    async def _read_exec_stderr(
        self,
        stream: asyncio.StreamReader | None,
        sink: list[str],
        on_event=None,
    ) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.readline()
            if not chunk:
                break
            text = _clean_terminal_output(chunk.decode("utf-8", errors="ignore")).strip()
            if not text:
                continue
            sink.append(text)
            self._append_log({"ts": _now_iso(), "type": "stderr", "content": text, "thread_id": self._thread_id})
            if on_event is not None:
                await on_event({"type": "stderr", "message": text, "thread_id": self._thread_id})

    async def _terminate_active_process(self) -> None:
        process = self._active_process
        if process is None or process.returncode is not None:
            return
        self._append_log({"ts": _now_iso(), "type": "interrupt", "thread_id": self._thread_id})
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except asyncio.TimeoutError:
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                return

    async def _run_exec_turn(
        self,
        prompt: str,
        *,
        resume: bool,
        cancel_event: asyncio.Event | None = None,
        on_event=None,
    ) -> tuple[str, list[str], bool]:
        cmd = self._build_exec_command(prompt, resume=resume)
        env = os.environ.copy()
        env["TERM"] = env.get("TERM") or "xterm-256color"
        env["NO_COLOR"] = "1"
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.workspace_path,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_process = process
        self._append_log(
            {
                "ts": _now_iso(),
                "type": "request_start",
                "cmd": cmd,
                "resume": resume,
                "thread_id": self._thread_id,
            }
        )

        stderr_lines: list[str] = []
        stderr_task = asyncio.create_task(self._read_exec_stderr(process.stderr, stderr_lines, on_event=on_event))
        final_content = ""
        interrupted = False
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set() and not interrupted:
                    interrupted = True
                    await self._terminate_active_process()
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=0.25)
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue
                if not line:
                    if process.returncode is not None:
                        break
                    continue
                raw = _clean_terminal_output(line.decode("utf-8", errors="ignore")).strip()
                if not raw:
                    continue
                self.last_active_at = _now_iso()
                self._append_log({"ts": self.last_active_at, "type": "exec_event_raw", "content": raw, "thread_id": self._thread_id})
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                event_type = str(event.get("type") or "").strip()
                if event_type == "thread.started":
                    thread_id = str(event.get("thread_id") or "").strip()
                    if thread_id:
                        self._thread_id = thread_id
                    if on_event is not None and self._thread_id:
                        await on_event(
                            {
                                "type": "status",
                                "stage": "thread_started",
                                "message": f"已连接到会话线程 {self._thread_id}",
                                "thread_id": self._thread_id,
                            }
                        )
                    continue
                if event_type == "turn.started":
                    if on_event is not None:
                        await on_event(
                            {
                                "type": "status",
                                "stage": "turn_started",
                                "message": "Codex CLI 正在处理请求…",
                                "thread_id": self._thread_id,
                            }
                        )
                    continue
                if event_type == "item.started":
                    item = event.get("item") if isinstance(event.get("item"), dict) else {}
                    item_type = str(item.get("type") or "").strip()
                    if item_type == "command_execution" and on_event is not None:
                        await on_event(
                            {
                                "type": "command_start",
                                "command": str(item.get("command") or "").strip(),
                                "thread_id": self._thread_id,
                            }
                        )
                    continue
                if event_type == "item.completed":
                    item = event.get("item") if isinstance(event.get("item"), dict) else {}
                    item_type = str(item.get("type") or "").strip()
                    if item_type == "agent_message":
                        text = str(item.get("text") or "")
                        if text and len(text) > len(final_content):
                            delta = text[len(final_content):]
                            final_content = text
                            if delta and on_event is not None:
                                await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
                        elif text:
                            final_content = text
                    elif item_type == "command_execution" and on_event is not None:
                        await on_event(
                            {
                                "type": "command_result",
                                "command": str(item.get("command") or "").strip(),
                                "exit_code": item.get("exit_code"),
                                "status": str(item.get("status") or "").strip(),
                                "output_preview": _summarize_command_output(item.get("aggregated_output") or ""),
                                "thread_id": self._thread_id,
                            }
                        )
                    elif item_type == "reasoning" and on_event is not None:
                        await on_event(
                            {
                                "type": "status",
                                "stage": "reasoning",
                                "message": "正在分析并规划下一步…",
                                "thread_id": self._thread_id,
                            }
                        )
                    continue
                if event_type.endswith(".delta"):
                    delta = str(event.get("delta") or event.get("text") or event.get("content") or "")
                    if delta:
                        final_content += delta
                        if on_event is not None:
                            await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
                    continue
                if event_type == "turn.completed":
                    usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
                    if on_event is not None and usage:
                        await on_event({"type": "usage", "usage": usage, "thread_id": self._thread_id})
                    break

            await process.wait()
            await stderr_task
        finally:
            if not stderr_task.done():
                stderr_task.cancel()
            self._active_process = None

        return final_content, stderr_lines, interrupted

    async def _prepare_session_locked(self) -> str:
        await self.ensure_started()
        if self._thread_id:
            return self._thread_id

        bootstrap_prompt = self._build_bootstrap_prompt()
        self.last_active_at = _now_iso()
        self._append_log({"ts": self.last_active_at, "type": "bootstrap_start", "content": bootstrap_prompt})
        final_content, stderr_lines, _ = await self._run_exec_turn(
            bootstrap_prompt,
            resume=False,
            cancel_event=None,
            on_event=None,
        )
        if not self._thread_id:
            stderr_text = "\n".join(stderr_lines[-8:]).strip()
            if stderr_text:
                raise RuntimeError(stderr_text)
            raise RuntimeError("Codex CLI 会话初始化失败：未返回 thread_id")
        self._append_log(
            {
                "ts": _now_iso(),
                "type": "bootstrap_done",
                "thread_id": self._thread_id,
                "content": final_content or "READY",
            }
        )
        return self._thread_id

    async def prepare_session(self) -> str:
        async with self._send_lock:
            return await self._prepare_session_locked()

    async def send_prompt(
        self,
        user_prompt: str,
        cancel_event: asyncio.Event | None = None,
        approval_context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
    ):
        prompt = self._compose_prompt(user_prompt, history)
        if not prompt.strip():
            raise RuntimeError("消息不能为空")

        async with self._send_lock:
            await self.ensure_started()
            if not self._thread_id:
                await self._prepare_session_locked()
            self.last_active_at = _now_iso()
            prompt_risks = _collect_risk_signals(user_prompt)
            before_diff_summary = collect_workspace_diff_summary(self.workspace_path)
            self._append_log(
                {
                    "ts": self.last_active_at,
                    "type": "user_input",
                    "content": prompt,
                    "thread_id": self._thread_id,
                }
            )
            if prompt_risks:
                self._append_log({"ts": self.last_active_at, "type": "risk_signals", "source": "user_prompt", "items": prompt_risks})

            event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def capture_event(event: dict[str, Any]) -> None:
                if not isinstance(event, dict):
                    return
                await event_queue.put(event)

            turn_task = asyncio.create_task(
                self._run_exec_turn(
                    prompt,
                    resume=True,
                    cancel_event=cancel_event,
                    on_event=capture_event,
                )
            )
            await event_queue.put({"type": "status", "stage": "request_started", "message": "外部 Agent 已接入，开始执行…", "thread_id": self._thread_id})
            while True:
                if turn_task.done() and event_queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                if isinstance(event, dict):
                    yield event
            final_content, stderr_lines, interrupted = await turn_task

            if interrupted and not final_content:
                final_content = "已停止生成。"
            if not final_content:
                stderr_text = "\n".join(stderr_lines[-8:]).strip()
                if stderr_text:
                    raise RuntimeError(stderr_text)
                raise RuntimeError("Codex CLI 未返回有效内容")

            output_risks = _collect_risk_signals(final_content)
            after_diff_summary = collect_workspace_diff_summary(self.workspace_path)
            approval_info = approval_context if isinstance(approval_context, dict) else {}
            audit_payload = {
                "risk_signals": prompt_risks,
                "output_risk_signals": output_risks,
                "approval_required": bool(prompt_risks),
                "approval_mode": str(approval_info.get("mode") or ("websocket_confirm" if prompt_risks else "none")),
                "approval_status": str(approval_info.get("status") or ("approved" if prompt_risks else "not_required")),
                "before_diff_summary": before_diff_summary,
                "after_diff_summary": after_diff_summary,
                "thread_id": self._thread_id,
            }
            self._append_log({"ts": _now_iso(), "type": "request_audit", "audit": audit_payload, "thread_id": self._thread_id})
            yield {"type": "audit", "audit": audit_payload, "thread_id": self._thread_id}
            self._append_log({"ts": _now_iso(), "type": "request_done", "content": final_content, "thread_id": self._thread_id})
            yield {"type": "done", "content": final_content, "thread_id": self._thread_id}

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._stop_terminal_mirror_locked()
        await self._terminate_active_process()
        self._append_log({"ts": _now_iso(), "type": "session_closed", "thread_id": self._thread_id})
