"""外部 Agent 会话与终端镜像适配。"""

from __future__ import annotations

import asyncio
import errno
import httpx
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

from core.config import get_settings
from services.local_connector_service import connector_headers

_ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)
_GEMINI_DIRNAME = ".gemini"
_GEMINI_RUNTIME_HOME_DIRNAME = ".gemini-home"
_GEMINI_AUTH_ENV_KEYS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_GCA",
)
_GEMINI_PASSTHROUGH_ENV_KEYS = (
    "GOOGLE_GEMINI_BASE_URL",
    "GOOGLE_VERTEX_BASE_URL",
    "GEMINI_MODEL",
    "GEMINI_API_KEY_AUTH_MECHANISM",
    "GOOGLE_GENAI_API_VERSION",
)
_GEMINI_RUNTIME_COPY_FILENAMES = (
    "oauth_creds.json",
    "google_accounts.json",
    "installation_id",
    "mcp-oauth-tokens.json",
    "mcp-oauth-tokens-v2.json",
)
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

_EXTERNAL_AGENT_SPECS: dict[str, dict[str, Any]] = {
    "codex_cli": {
        "label": "Codex CLI",
        "binary_name": "codex",
        "override_attr": "external_agent_codex_bin",
        "runtime_model_name": "codex-cli",
        "supports_terminal_mirror": True,
        "supports_workspace_write": True,
        "implemented": True,
    },
    "claude_cli": {
        "label": "Claude Code",
        "binary_name": "claude",
        "override_attr": "external_agent_claude_bin",
        "runtime_model_name": "claude-code",
        "supports_terminal_mirror": False,
        "supports_workspace_write": True,
        "implemented": True,
        "reason": "",
    },
    "gemini_cli": {
        "label": "Gemini CLI",
        "binary_name": "gemini",
        "override_attr": "external_agent_gemini_bin",
        "runtime_model_name": "gemini-cli",
        "supports_terminal_mirror": False,
        "supports_workspace_write": True,
        "implemented": True,
        "reason": "",
    },
}


def normalize_external_agent_type(value: str | None) -> str:
    agent_type = str(value or "codex_cli").strip().lower()
    return agent_type if agent_type in _EXTERNAL_AGENT_SPECS else "codex_cli"


def _resolve_external_agent_command(spec: dict[str, Any]) -> tuple[str, str, str]:
    settings = get_settings()
    binary_name = str(spec.get("binary_name") or "").strip()
    override_attr = str(spec.get("override_attr") or "").strip()
    configured = str(getattr(settings, override_attr, "") or "").strip() if override_attr else ""
    system_command = shutil.which(binary_name) or ""

    configured_command = ""
    if configured:
        if os.path.sep in configured:
            configured_command = configured if Path(configured).exists() else ""
        else:
            configured_command = shutil.which(configured) or ""

    resolved = system_command or configured_command
    command_source = "system" if system_command else ("override" if configured_command else "missing")
    display_command = resolved or configured or binary_name
    return resolved, display_command, command_source


def resolve_external_agent_status(agent_type: str | None = None) -> dict[str, Any]:
    normalized_type = normalize_external_agent_type(agent_type)
    spec = dict(_EXTERNAL_AGENT_SPECS.get(normalized_type) or _EXTERNAL_AGENT_SPECS["codex_cli"])
    resolved, display_command, command_source = _resolve_external_agent_command(spec)
    implemented = bool(spec.get("implemented"))
    available = bool(resolved)
    return {
        "agent_type": normalized_type,
        "label": str(spec.get("label") or normalized_type),
        "command": display_command,
        "resolved_command": resolved,
        "command_source": command_source,
        "available": available and implemented,
        "installed": available,
        "implemented": implemented,
        "reason": str(spec.get("reason") or "").strip(),
        "runtime_model_name": str(spec.get("runtime_model_name") or normalized_type),
        "exact_model_name": "",
        "sandbox_modes": ["read-only", "workspace-write"] if bool(spec.get("supports_workspace_write")) else ["read-only"],
        "runner_url": _runner_base_url(),
        "execution_mode": "runner" if _runner_base_url() and implemented else "local",
        "supports_terminal_mirror": bool(spec.get("supports_terminal_mirror")),
        "supports_workspace_write": bool(spec.get("supports_workspace_write")),
    }


def list_external_agent_statuses() -> list[dict[str, Any]]:
    return [resolve_external_agent_status(agent_type) for agent_type in _EXTERNAL_AGENT_SPECS]


def get_implemented_external_agent_types() -> set[str]:
    return {agent_type for agent_type, spec in _EXTERNAL_AGENT_SPECS.items() if bool(spec.get("implemented"))}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_token(value: str, *, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-") or "unknown"
    return cleaned[:max_len]


def _parse_simple_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return result
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        result[key] = value
    return result


def _gemini_runtime_home_path(workspace_path: str) -> Path:
    workspace = Path(str(workspace_path or "").strip()).expanduser()
    return workspace / _GEMINI_RUNTIME_HOME_DIRNAME


def _gemini_runtime_user_dir(workspace_path: str) -> Path:
    return _gemini_runtime_home_path(workspace_path) / _GEMINI_DIRNAME


def _gemini_host_user_dir() -> Path:
    return Path.home() / _GEMINI_DIRNAME


def _build_gemini_workspace_settings(bridge: dict[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    bridge_payload = bridge if isinstance(bridge, dict) else {}
    server_name = str(bridge_payload.get("server_name") or "").strip()
    server_url = str(bridge_payload.get("url") or "").strip()
    if bool(bridge_payload.get("enabled")) and server_name and server_url:
        payload["mcpServers"] = {
            server_name: {
                "type": "sse",
                "url": server_url,
            }
        }
    return payload


def _resolve_gemini_auth_env() -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key in _GEMINI_AUTH_ENV_KEYS:
        value = str(os.environ.get(key) or "").strip()
        if value:
            resolved[key] = value
    env_path = _gemini_host_user_dir() / ".env"
    if env_path.is_file():
        file_env = _parse_simple_env_file(env_path)
        for key in _GEMINI_AUTH_ENV_KEYS:
            value = str(file_env.get(key) or "").strip()
            if value and key not in resolved:
                resolved[key] = value
    return resolved


def _resolve_gemini_passthrough_env() -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key in _GEMINI_PASSTHROUGH_ENV_KEYS:
        value = str(os.environ.get(key) or "").strip()
        if value:
            resolved[key] = value
    env_path = _gemini_host_user_dir() / ".env"
    if env_path.is_file():
        file_env = _parse_simple_env_file(env_path)
        for key in _GEMINI_PASSTHROUGH_ENV_KEYS:
            value = str(file_env.get(key) or "").strip()
            if value and key not in resolved:
                resolved[key] = value
    return resolved


def _detect_gemini_auth_mode(workspace_path: str) -> str:
    auth_env = _resolve_gemini_auth_env()
    if str(auth_env.get("GEMINI_API_KEY") or "").strip():
        return "gemini-api-key"
    if str(auth_env.get("GOOGLE_GENAI_USE_VERTEXAI") or "").strip().lower() == "true":
        return "vertex-ai"
    if str(auth_env.get("GOOGLE_API_KEY") or "").strip():
        return "vertex-ai"
    if str(auth_env.get("GOOGLE_CLOUD_PROJECT") or "").strip() and str(auth_env.get("GOOGLE_CLOUD_LOCATION") or "").strip():
        return "vertex-ai"
    runtime_user_dir = _gemini_runtime_user_dir(workspace_path)
    host_user_dir = _gemini_host_user_dir()
    if (runtime_user_dir / "oauth_creds.json").is_file() or (host_user_dir / "oauth_creds.json").is_file():
        return "oauth-personal"
    return ""


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
    return ["--", ".", f":(exclude){_GEMINI_RUNTIME_HOME_DIRNAME}/**"]


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
    return resolve_external_agent_status("codex_cli")


def _runner_base_url() -> str:
    return str(get_settings().external_agent_runner_url or "").strip().rstrip("/")


async def probe_workspace_access_effective_async(workspace_path: str, sandbox_mode: str = "workspace-write") -> dict[str, Any]:
    runner_url = _runner_base_url()
    return await probe_workspace_access_effective_with_runner_async(
        workspace_path,
        sandbox_mode,
        runner_url=runner_url,
        extra_headers=None,
    )


async def probe_workspace_access_effective_with_runner_async(
    workspace_path: str,
    sandbox_mode: str = "workspace-write",
    *,
    runner_url: str = "",
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    runner_url = str(runner_url or "").strip().rstrip("/")
    if runner_url:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{runner_url}/probe-workspace",
                    headers=extra_headers or {},
                    json={"workspace_path": str(workspace_path or ""), "sandbox_mode": str(sandbox_mode or "workspace-write")},
                )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    payload.setdefault("source", "runner")
                    return payload
        except Exception as exc:
            fallback = probe_workspace_access(workspace_path, sandbox_mode)
            fallback["source"] = "local_fallback"
            fallback["runner_error"] = str(exc)
            return fallback
    fallback = probe_workspace_access(workspace_path, sandbox_mode)
    fallback.setdefault("source", "local")
    return fallback


def _display_path(base: Path, target: Path) -> str:
    try:
        return str(target.relative_to(base))
    except ValueError:
        return str(target)


def probe_workspace_access(workspace_path: str, sandbox_mode: str = "workspace-write") -> dict[str, Any]:
    raw = str(workspace_path or "").strip()
    mode = str(sandbox_mode or "workspace-write").strip() or "workspace-write"
    if not raw:
        return {
            "configured": False,
            "exists": False,
            "is_dir": False,
            "read_ok": False,
            "write_ok": False,
            "sandbox_mode": mode,
            "reason": "未配置 workspace_path",
        }

    workspace = Path(raw).expanduser()
    if not workspace.exists():
        return {
            "configured": True,
            "exists": False,
            "is_dir": False,
            "read_ok": False,
            "write_ok": False,
            "sandbox_mode": mode,
            "reason": f"工作区不存在：{workspace}",
        }
    if not workspace.is_dir():
        return {
            "configured": True,
            "exists": True,
            "is_dir": False,
            "read_ok": False,
            "write_ok": False,
            "sandbox_mode": mode,
            "reason": f"工作区不是目录：{workspace}",
        }

    result = {
        "configured": True,
        "exists": True,
        "is_dir": True,
        "read_ok": True,
        "write_ok": False,
        "sandbox_mode": mode,
        "path": str(workspace),
        "reason": "",
    }
    if mode != "workspace-write":
        result["reason"] = "当前请求的是只读模式(read-only)"
        return result

    probe_file = workspace / f".write-probe-{uuid.uuid4().hex}.tmp"
    try:
        probe_file.write_text("ok", encoding="utf-8")
        try:
            probe_file.unlink()
        except FileNotFoundError:
            pass
        result["write_ok"] = True
    except Exception as exc:
        result["reason"] = str(exc)
    return result


def _copy_text_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def prepare_external_agent_workspace_context(
    *,
    project_id: str,
    project_name: str,
    project_description: str,
    workspace_path: str,
    sandbox_mode: str,
    agent_type: str = "codex_cli",
    selected_employee_names: list[str] | None = None,
    candidate_preview: list[str] | None = None,
    system_prompt: str = "",
    mcp_bridge: dict[str, Any] | None = None,
    write_files: bool = False,
    skill_resource_directory: str = "",
) -> dict[str, Any]:
    workspace = Path(str(workspace_path or "").strip())
    bridge = mcp_bridge if isinstance(mcp_bridge, dict) else {}
    bridge_server_name = str(bridge.get("server_name") or "").strip()
    materialize_copies: list[dict[str, Any]] = []
    generated_gemini_settings_path = workspace / _GEMINI_DIRNAME / "settings.json"
    generated_gemini_user_settings_path = _gemini_runtime_user_dir(workspace_path) / "settings.json"
    startup_context = ""
    support_files: list[dict[str, Any]] = []
    materialize_files: list[dict[str, Any]] = []
    normalized_agent_type = normalize_external_agent_type(agent_type)
    if normalized_agent_type == "gemini_cli":
        gemini_workspace_settings = json.dumps(
            _build_gemini_workspace_settings(bridge),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        materialize_files.append(
            {
                "kind": "generated_gemini_workspace_settings",
                "path": str(generated_gemini_settings_path),
                "content": gemini_workspace_settings,
            }
        )
        materialize_files.append(
            {
                "kind": "generated_gemini_user_settings",
                "path": str(generated_gemini_user_settings_path),
                "content": "{}\n",
            }
        )
        support_files.insert(
            2,
            {
                "kind": "generated_gemini_workspace_settings",
                "label": "生成的 Gemini 工作区配置",
                "path": _display_path(workspace, generated_gemini_settings_path) if workspace_path else str(generated_gemini_settings_path),
                "materialize_path": str(generated_gemini_settings_path),
                "written": False,
            },
        )
        host_gemini_dir = _gemini_host_user_dir()
        runtime_gemini_dir = _gemini_runtime_user_dir(workspace_path)
        for filename in _GEMINI_RUNTIME_COPY_FILENAMES:
            source = host_gemini_dir / filename
            if not source.is_file():
                continue
            target = runtime_gemini_dir / filename
            materialize_copies.append(
                {
                    "kind": "gemini_runtime_copy",
                    "source_path": str(source),
                    "target_path": str(target),
                    "path": _display_path(workspace, target) if workspace_path else str(target),
                }
            )

    if write_files:
        for item in support_files:
            materialize_path = Path(str(item.get("materialize_path") or "").strip())
            content = next(
                (
                    str(materialize_item.get("content") or "")
                    for materialize_item in materialize_files
                    if str(materialize_item.get("path") or "").strip() == str(materialize_path)
                ),
                None,
            )
            if content is None:
                continue
            try:
                materialize_path.parent.mkdir(parents=True, exist_ok=True)
                materialize_path.write_text(content, encoding="utf-8")
                item["written"] = True
            except Exception as exc:
                item["error"] = str(exc)

    return {
        "context_root": "",
        "support_dir": "",
        "support_files": support_files,
        "startup_context": startup_context,
        "workspace_access": probe_workspace_access(workspace_path, sandbox_mode),
        "materialization": {
            "workspace_path": str(workspace),
            "sandbox_mode": sandbox_mode,
            "files": materialize_files,
            "copies": materialize_copies,
        },
        "mcp_bridge": {
            "enabled": bool(bridge.get("enabled")),
            "server_name": bridge_server_name,
        },
    }


async def materialize_external_agent_workspace_context_async(context: dict[str, Any] | None) -> dict[str, Any]:
    return await materialize_external_agent_workspace_context_with_runner_async(context)


async def materialize_external_agent_workspace_context_with_runner_async(
    context: dict[str, Any] | None,
    *,
    runner_url: str = "",
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = dict(context or {})
    materialization = payload.get("materialization") if isinstance(payload.get("materialization"), dict) else {}
    runner_url = str(runner_url or _runner_base_url() or "").strip().rstrip("/")
    if not materialization:
        payload["materialized_by"] = "local"
        return payload

    files = list(materialization.get("files") or [])
    copies = list(materialization.get("copies") or [])
    if not files and not copies:
        payload["materialized_by"] = "runner"
        return payload

    support_files = list(payload.get("support_files") or [])
    file_results: dict[str, dict[str, Any]] = {}
    copy_results: dict[str, dict[str, Any]] = {}
    try:
        if runner_url:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{runner_url}/workspace/materialize",
                    headers=extra_headers or {},
                    json={
                        "workspace_path": materialization.get("workspace_path") or "",
                        "sandbox_mode": materialization.get("sandbox_mode") or "workspace-write",
                        "files": [
                            {"path": str(item.get("path") or ""), "content": str(item.get("content") or "")}
                            for item in files
                        ],
                        "copies": [
                            {"source_path": str(item.get("source_path") or ""), "target_path": str(item.get("target_path") or "")}
                            for item in copies
                        ],
                    },
                )
                response.raise_for_status()
                runner_payload = response.json() if response.content else {}
            for item in list(runner_payload.get("files") or []):
                file_results[str(item.get("path") or "").strip()] = item
            for item in list(runner_payload.get("copies") or []):
                copy_results[str(item.get("target_path") or "").strip()] = item
            if isinstance(runner_payload.get("workspace_access"), dict):
                payload["workspace_access"] = runner_payload.get("workspace_access")
            payload["materialized_by"] = "runner"
        else:
            for item in files:
                path = Path(str(item.get("path") or "").strip())
                result = {"path": str(path), "written": False}
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(str(item.get("content") or ""), encoding="utf-8")
                    result["written"] = True
                except Exception as exc:
                    result["error"] = str(exc)
                file_results[str(path)] = result
            for item in copies:
                source_path = Path(str(item.get("source_path") or "").strip())
                target_path = Path(str(item.get("target_path") or "").strip())
                result = {
                    "source_path": str(source_path),
                    "target_path": str(target_path),
                    "written": False,
                }
                try:
                    _copy_text_file(source_path, target_path)
                    result["written"] = True
                except Exception as exc:
                    result["error"] = str(exc)
                copy_results[str(target_path)] = result
            payload["materialized_by"] = "local"
    except Exception as exc:
        payload["materialized_by"] = "runner_failed" if runner_url else "local_failed"
        payload["materialization_error"] = str(exc)
        return payload

    for item in support_files:
        materialize_path = str(item.get("materialize_path") or "").strip()
        result = file_results.get(materialize_path) or copy_results.get(materialize_path)
        if not isinstance(result, dict):
            continue
        item["written"] = bool(result.get("written"))
        if str(result.get("error") or "").strip():
            item["error"] = str(result.get("error") or "").strip()
        elif "error" in item:
            item.pop("error", None)
    return payload


class ExternalAgentSession:
    def __init__(
        self,
        *,
        project_id: str,
        project_name: str,
        username: str,
        workspace_path: str,
        startup_context: str,
        agent_type: str = "codex_cli",
        sandbox_mode: str = "workspace-write",
        codex_config_overrides: list[str] | None = None,
        runner_url_override: str = "",
        runner_headers: dict[str, str] | None = None,
    ) -> None:
        self.project_id = str(project_id or "").strip()
        self.project_name = str(project_name or "").strip()
        self.username = str(username or "").strip() or "unknown"
        self.workspace_path = str(workspace_path or "").strip()
        self.startup_context = str(startup_context or "").strip()
        self._startup_context = self.startup_context
        self.agent_type = normalize_external_agent_type(agent_type)
        self.sandbox_mode = str(sandbox_mode or "workspace-write").strip() or "workspace-write"
        self.codex_config_overrides = [
            str(item or "").strip()
            for item in (codex_config_overrides or [])
            if str(item or "").strip()
        ]
        self.runner_url_override = str(runner_url_override or "").strip().rstrip("/")
        self.runner_headers = {
            str(key or "").strip(): str(value or "").strip()
            for key, value in (runner_headers or {}).items()
            if str(key or "").strip()
        }
        self.session_id = f"agent-{uuid.uuid4().hex[:10]}"
        self.started_at = _now_iso()
        self.last_active_at = self.started_at

        self._send_lock = asyncio.Lock()
        self._log_lock = Lock()
        self._closed = False
        self._command = ""
        self._thread_id = ""
        self._active_process: asyncio.subprocess.Process | None = None
        self._runner_exec_id = ""
        self._runner_mirror_session_id = ""
        self._mirror_process: asyncio.subprocess.Process | None = None
        self._mirror_master_fd: int | None = None
        self._mirror_task: asyncio.Task | None = None
        self._mirror_startup_acked = False
        self._session_started = False

        root = Path(__file__).resolve().parent.parent / "data" / "project-agent-sessions"
        root.mkdir(parents=True, exist_ok=True)
        project_dir = root / _safe_token(self.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = project_dir / f"{_safe_token(self.username, max_len=48)}-{self.session_id}.jsonl"

    @property
    def thread_id(self) -> str:
        return self._thread_id

    def _effective_runner_url(self) -> str:
        return self.runner_url_override or _runner_base_url()

    def _effective_runner_headers(self) -> dict[str, str]:
        return dict(self.runner_headers or {})

    def _workspace_diff_summary(self) -> dict[str, Any]:
        if self.runner_url_override:
            return {"enabled": False, "reason": "本地连接器模式暂不支持远程 Git 差异摘要"}
        return collect_workspace_diff_summary(self.workspace_path)

    async def ensure_started(self) -> None:
        if self._closed:
            raise RuntimeError("外部 Agent 会话已关闭")
        if not self.workspace_path:
            raise RuntimeError("项目未配置 workspace_path，无法启动外部 Agent")
        runner_url = self._effective_runner_url()
        if not runner_url:
            workspace = Path(self.workspace_path)
            if not workspace.exists() or not workspace.is_dir():
                raise RuntimeError(f"workspace_path 不存在或不可用：{self.workspace_path}")
        access = await probe_workspace_access_effective_with_runner_async(
            self.workspace_path,
            self.sandbox_mode,
            runner_url=runner_url,
            extra_headers=self._effective_runner_headers(),
        )
        if not bool(access.get("read_ok")):
            reason = str(access.get("reason") or "未知原因")
            raise RuntimeError(f"工作区不可用：{reason}")
        if self.sandbox_mode == "workspace-write" and not bool(access.get("write_ok")):
            reason = str(access.get("reason") or "未知原因")
            raise RuntimeError(
                "当前外部 Agent 请求的是 workspace-write，但服务进程对目标工作区没有真实写权限："
                f"{reason}。这通常意味着后端服务本身运行在受限沙箱中，或该目录不在可写白名单。"
            )

        agent_status = resolve_external_agent_status(self.agent_type)
        spec = dict(_EXTERNAL_AGENT_SPECS.get(self.agent_type) or _EXTERNAL_AGENT_SPECS["codex_cli"])
        if not bool(agent_status.get("implemented")):
            label = str(agent_status.get("label") or self.agent_type)
            reason = str(agent_status.get("reason") or "该外部 Agent 尚未完成后端适配").strip()
            raise RuntimeError(f"{label} 当前还不能直接用于对话框会话：{reason}")
        command = (
            str(spec.get("binary_name") or "").strip()
            if runner_url
            else str(agent_status.get("resolved_command") or agent_status.get("command") or "").strip()
        )
        if not command:
            label = str(agent_status.get("label") or self.agent_type)
            raise RuntimeError(
                f"未找到系统 {label} 命令，请先确认电脑已安装且 PATH 可用；仅在特殊部署场景下再配置对应 *_BIN 环境变量"
            )
        if self.agent_type == "gemini_cli" and not runner_url:
            auth_mode = _detect_gemini_auth_mode(self.workspace_path)
            if not auth_mode:
                raise RuntimeError(
                    "Gemini CLI 未检测到可用认证。请先满足以下任一条件后再使用："
                    "1) 在当前用户环境变量或 `~/.gemini/.env` 中提供 `GEMINI_API_KEY`；"
                    "2) 完成 Gemini CLI 的 Google 登录；"
                    "3) 配置 Vertex AI 所需的 `GOOGLE_API_KEY` 或 `GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION`。"
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
        command_status = resolve_external_agent_status(self.agent_type)
        lines = [
            "当前可见运行元数据（由平台注入，可直接据此回答）：",
            f"- agent_type: {self.agent_type}",
            f"- session_id: {self.session_id}",
            f"- thread_id: {self._thread_id or '-'}",
            f"- workspace_path: {self.workspace_path or '-'}",
            f"- sandbox_mode: {self.sandbox_mode or '-'}",
            f"- execution_mode: {'local_connector' if self.runner_url_override else ('runner' if _runner_base_url() else 'local')}",
            f"- command_source: {str(command_status.get('command_source') or 'missing')}",
            f"- command_path: {str(command_status.get('resolved_command') or command_status.get('command') or '-')}",
            f"- runtime_label: {str(command_status.get('runtime_model_name') or self.agent_type)}",
            f"- exact_model_name: {str(command_status.get('exact_model_name') or 'unavailable')}",
            f"说明：当前外部 Agent 为 {str(command_status.get('label') or self.agent_type)}；若其 CLI 未稳定暴露底层精确模型名，请明确说明无法准确报告具体型号。",
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
                "--full-auto",
                "--skip-git-repo-check",
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
        runner_session_id = self._runner_mirror_session_id
        self._runner_mirror_session_id = ""
        self._mirror_startup_acked = False
        runner_url = self._effective_runner_url()
        if runner_session_id and runner_url:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{runner_url}/pty/close/{runner_session_id}",
                        headers=self._effective_runner_headers(),
                    )
            except Exception:
                pass
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

    async def _pump_terminal_mirror_via_runner(self, session_id: str, on_event=None) -> None:
        runner_url = self._effective_runner_url()
        if not runner_url:
            return
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
                async with client.stream(
                    "GET",
                    f"{runner_url}/pty/stream/{session_id}",
                    headers=self._effective_runner_headers(),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        raw = str(line or "").strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except Exception:
                            continue
                        event_type = str(event.get("type") or "").strip()
                        if event_type == "chunk":
                            cleaned = _clean_terminal_output(str(event.get("data") or ""))
                            if cleaned and _should_ack_startup_screen(cleaned) and not self._mirror_startup_acked:
                                self._mirror_startup_acked = True
                                try:
                                    async with httpx.AsyncClient(timeout=10.0) as ack_client:
                                        await ack_client.post(
                                            f"{runner_url}/pty/input/{session_id}",
                                            headers=self._effective_runner_headers(),
                                            json={"content": "\r\r"},
                                        )
                                except Exception:
                                    pass
                            stripped = cleaned.strip()
                            if stripped:
                                self._append_log({"ts": _now_iso(), "type": "terminal_mirror", "content": stripped, "thread_id": self._thread_id})
                                if on_event is not None:
                                    await on_event({"type": "terminal_mirror_chunk", "content": stripped, "thread_id": self._thread_id})
                            continue
                        if event_type == "exit":
                            break
        finally:
            if on_event is not None:
                await on_event({"type": "terminal_mirror_stopped", "thread_id": self._thread_id})

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
            if self._runner_mirror_session_id:
                return
            if self._mirror_process is not None and self._mirror_process.returncode is None:
                return
            await self._stop_terminal_mirror_locked()
            cmd = self._build_resume_tui_command()
            env = os.environ.copy()
            env["TERM"] = env.get("TERM") or "xterm-256color"
            runner_url = self._effective_runner_url()
            if runner_url:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{runner_url}/pty/open",
                        headers=self._effective_runner_headers(),
                        json={"cmd": cmd, "cwd": self.workspace_path, "env": env},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    self._runner_mirror_session_id = str(payload.get("session_id") or "").strip()
                self._mirror_startup_acked = False
                self._append_log({"ts": _now_iso(), "type": "terminal_mirror_start", "cmd": cmd, "thread_id": self._thread_id, "execution_mode": "runner"})
                if on_event is not None:
                    await on_event({"type": "terminal_mirror_started", "thread_id": self._thread_id})
                self._mirror_task = asyncio.create_task(self._pump_terminal_mirror_via_runner(self._runner_mirror_session_id, on_event=on_event))
                return
            master_fd, slave_fd = pty.openpty()
            _disable_tty_echo(slave_fd)
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
            runner_url = self._effective_runner_url()
            if self._runner_mirror_session_id and runner_url:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{runner_url}/pty/input/{self._runner_mirror_session_id}",
                        headers=self._effective_runner_headers(),
                        json={"content": payload},
                    )
                    response.raise_for_status()
                self._append_log({"ts": _now_iso(), "type": "terminal_mirror_input", "content": payload, "thread_id": self._thread_id})
                return
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
        self._append_log({"ts": _now_iso(), "type": "interrupt", "thread_id": self._thread_id})
        if self._runner_exec_id:
            runner_url = self._effective_runner_url()
            if runner_url:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            f"{runner_url}/exec/cancel/{self._runner_exec_id}",
                            headers=self._effective_runner_headers(),
                        )
                except Exception:
                    pass
                return
        process = self._active_process
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except asyncio.TimeoutError:
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                return

    async def _run_exec_turn_via_runner(
        self,
        cmd: list[str],
        env: dict[str, str],
        *,
        cancel_event: asyncio.Event | None = None,
        on_event=None,
    ) -> tuple[str, list[str], bool]:
        runner_url = self._effective_runner_url()
        if not runner_url:
            raise RuntimeError("未配置 EXTERNAL_AGENT_RUNNER_URL")
        self._append_log({"ts": _now_iso(), "type": "request_start", "cmd": cmd, "resume": True, "thread_id": self._thread_id, "execution_mode": "runner"})
        stderr_lines: list[str] = []
        final_content = ""
        interrupted = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
            async with client.stream(
                "POST",
                f"{runner_url}/exec/stream",
                headers=self._effective_runner_headers(),
                json={"cmd": cmd, "cwd": self.workspace_path, "env": env},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if cancel_event is not None and cancel_event.is_set() and not interrupted:
                        interrupted = True
                        await self._terminate_active_process()
                    raw_line = str(line or "").strip()
                    if not raw_line:
                        continue
                    try:
                        runner_event = json.loads(raw_line)
                    except Exception:
                        continue
                    event_type = str(runner_event.get("type") or "").strip()
                    if event_type == "started":
                        self._runner_exec_id = str(runner_event.get("exec_id") or "").strip()
                        continue
                    if event_type == "stderr":
                        text = _clean_terminal_output(str(runner_event.get("data") or "")).strip()
                        if not text:
                            continue
                        stderr_lines.append(text)
                        self._append_log({"ts": _now_iso(), "type": "stderr", "content": text, "thread_id": self._thread_id})
                        if on_event is not None:
                            await on_event({"type": "stderr", "message": text, "thread_id": self._thread_id})
                        continue
                    if event_type == "exit":
                        break
                    if event_type != "stdout":
                        continue
                    raw = _clean_terminal_output(str(runner_event.get("data") or "")).strip()
                    if not raw:
                        continue
                    self.last_active_at = _now_iso()
                    self._append_log({"ts": self.last_active_at, "type": "exec_event_raw", "content": raw, "thread_id": self._thread_id})
                    try:
                        event = json.loads(raw)
                    except Exception:
                        continue
                    inner_type = str(event.get("type") or "").strip()
                    if inner_type == "thread.started":
                        thread_id = str(event.get("thread_id") or "").strip()
                        if thread_id:
                            self._thread_id = thread_id
                        if on_event is not None and self._thread_id:
                            await on_event({"type": "status", "stage": "thread_started", "message": f"已连接到会话线程 {self._thread_id}", "thread_id": self._thread_id})
                        continue
                    if inner_type == "turn.started":
                        if on_event is not None:
                            await on_event({"type": "status", "stage": "turn_started", "message": "Codex CLI 正在处理请求…", "thread_id": self._thread_id})
                        continue
                    if inner_type == "item.started":
                        item = event.get("item") if isinstance(event.get("item"), dict) else {}
                        item_type = str(item.get("type") or "").strip()
                        if item_type == "command_execution" and on_event is not None:
                            await on_event({"type": "command_start", "command": str(item.get("command") or "").strip(), "thread_id": self._thread_id})
                        continue
                    if inner_type == "item.completed":
                        item = event.get("item") if isinstance(event.get("item"), dict) else {}
                        item_type = str(item.get("type") or "").strip()
                        if item_type == "agent_message":
                            value = str(item.get("text") or "")
                            if value and len(value) > len(final_content):
                                delta = value[len(final_content):]
                                final_content = value
                                if delta and on_event is not None:
                                    await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
                            elif value:
                                final_content = value
                        elif item_type == "command_execution" and on_event is not None:
                            await on_event({
                                "type": "command_result",
                                "command": str(item.get("command") or "").strip(),
                                "exit_code": item.get("exit_code"),
                                "status": str(item.get("status") or "").strip(),
                                "output_preview": _summarize_command_output(item.get("aggregated_output") or ""),
                                "thread_id": self._thread_id,
                            })
                        elif item_type == "reasoning" and on_event is not None:
                            await on_event({"type": "status", "stage": "reasoning", "message": "正在分析并规划下一步…", "thread_id": self._thread_id})
                        continue
                    if inner_type.endswith(".delta"):
                        delta = str(event.get("delta") or event.get("text") or event.get("content") or "")
                        if delta:
                            final_content += delta
                            if on_event is not None:
                                await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
                        continue
                    if inner_type == "turn.completed":
                        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
                        if on_event is not None and usage:
                            await on_event({"type": "usage", "usage": usage, "thread_id": self._thread_id})
                        break
        self._runner_exec_id = ""
        return final_content, stderr_lines, interrupted

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
        if self._effective_runner_url():
            return await self._run_exec_turn_via_runner(cmd, env, cancel_event=cancel_event, on_event=on_event)
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
            before_diff_summary = self._workspace_diff_summary()
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
                raise RuntimeError("外部 Agent 未返回有效内容")

            output_risks = _collect_risk_signals(final_content)
            after_diff_summary = self._workspace_diff_summary()
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



def _extract_text_segments(value: Any) -> list[str]:
    parts: list[str] = []
    if isinstance(value, str):
        text = str(value).strip()
        if text:
            parts.append(text)
        return parts
    if isinstance(value, list):
        for item in value:
            parts.extend(_extract_text_segments(item))
        return parts
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            text = str(value.get("text") or "").strip()
            if text:
                parts.append(text)
        for key in ("content", "message", "result", "delta", "completion", "value"):
            if key in value:
                parts.extend(_extract_text_segments(value.get(key)))
        return parts
    return parts


def _extract_text_payload(value: Any) -> str:
    seen: set[str] = set()
    parts: list[str] = []
    for item in _extract_text_segments(value):
        if item in seen:
            continue
        seen.add(item)
        parts.append(item)
    return "\n".join(parts).strip()


def _compute_incremental_text(previous: str, current: str) -> tuple[str, str]:
    prev = str(previous or "")
    curr = str(current or "")
    if not curr:
        return prev, ""
    if prev and curr.startswith(prev):
        return curr, curr[len(prev):]
    if curr == prev:
        return prev, ""
    return curr, curr


def _claude_permission_mode(sandbox_mode: str) -> str:
    mode = str(sandbox_mode or "workspace-write").strip().lower()
    if mode == "read-only":
        return "plan"
    return "acceptEdits"


def _gemini_approval_mode(sandbox_mode: str) -> str:
    mode = str(sandbox_mode or "workspace-write").strip().lower()
    if mode == "read-only":
        return "plan"
    return "auto_edit"


class ClaudeExternalAgentSession(ExternalAgentSession):
    def __init__(self, **kwargs: Any) -> None:
        kwargs["agent_type"] = "claude_cli"
        super().__init__(**kwargs)
        self._thread_id = self._thread_id or str(uuid.uuid4())

    def _build_exec_command(self, prompt: str, *, resume: bool) -> list[str]:
        session_id = self._thread_id or str(uuid.uuid4())
        self._thread_id = session_id
        cmd = [
            self._command,
            "-p",
            prompt,
            "--verbose",
            "--output-format",
            "stream-json",
            "--include-partial-messages",
            "--permission-mode",
            _claude_permission_mode(self.sandbox_mode),
            "--session-id",
            session_id,
        ]
        if self.workspace_path:
            cmd.extend(["--add-dir", self.workspace_path])
        if self._startup_context:
            cmd.extend(["--append-system-prompt", self._startup_context])
        return cmd

    async def _prepare_session_locked(self) -> str:
        await self.ensure_started()
        if not self._thread_id:
            self._thread_id = str(uuid.uuid4())
        self._append_log(
            {
                "ts": _now_iso(),
                "type": "bootstrap_done",
                "thread_id": self._thread_id,
                "content": "READY",
            }
        )
        return self._thread_id

    async def start_terminal_mirror(self, on_event=None) -> None:
        raise RuntimeError("Claude Code 当前接入的是 print/stream-json 模式，暂不支持终端镜像")

    async def write_terminal_input(self, text: str) -> None:
        raise RuntimeError("Claude Code 当前未启用终端镜像输入")

    async def stop_terminal_mirror(self) -> None:
        return

    async def _handle_claude_stream_event(
        self,
        payload: dict[str, Any],
        final_content: str,
        on_event=None,
    ) -> str:
        event_type = str(payload.get("type") or "").strip().lower()
        subtype = str(payload.get("subtype") or "").strip().lower()
        if event_type == "system" and subtype == "init":
            session_id = str(payload.get("session_id") or self._thread_id or "").strip()
            if session_id:
                self._thread_id = session_id
            if on_event is not None and self._thread_id:
                await on_event({
                    "type": "status",
                    "stage": "thread_started",
                    "message": f"已连接到 Claude 会话 {self._thread_id}",
                    "thread_id": self._thread_id,
                })
            return final_content
        if event_type == "assistant":
            text = _extract_text_payload(payload.get("message") or payload.get("content") or payload)
            updated, delta = _compute_incremental_text(final_content, text)
            if delta and on_event is not None:
                await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
            return updated
        if event_type == "result":
            text = _extract_text_payload(payload)
            updated, delta = _compute_incremental_text(final_content, text)
            if delta and on_event is not None:
                await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
            return updated
        if event_type == "error":
            message = _extract_text_payload(payload) or str(payload.get("message") or "Claude Code 执行失败")
            raise RuntimeError(message)
        return final_content

    async def _run_claude_turn_via_runner(
        self,
        cmd: list[str],
        env: dict[str, str],
        *,
        cancel_event: asyncio.Event | None = None,
        on_event=None,
    ) -> tuple[str, list[str], bool]:
        runner_url = self._effective_runner_url()
        if not runner_url:
            raise RuntimeError("未配置 EXTERNAL_AGENT_RUNNER_URL")
        self._append_log({"ts": _now_iso(), "type": "request_start", "cmd": cmd, "resume": True, "thread_id": self._thread_id, "execution_mode": "runner"})
        stderr_lines: list[str] = []
        final_content = ""
        interrupted = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
            async with client.stream(
                "POST",
                f"{runner_url}/exec/stream",
                headers=self._effective_runner_headers(),
                json={"cmd": cmd, "cwd": self.workspace_path, "env": env},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if cancel_event is not None and cancel_event.is_set() and not interrupted:
                        interrupted = True
                        await self._terminate_active_process()
                    raw_line = str(line or "").strip()
                    if not raw_line:
                        continue
                    try:
                        runner_event = json.loads(raw_line)
                    except Exception:
                        continue
                    event_type = str(runner_event.get("type") or "").strip()
                    if event_type == "started":
                        self._runner_exec_id = str(runner_event.get("exec_id") or "").strip()
                        if on_event is not None:
                            await on_event({"type": "status", "stage": "turn_started", "message": "Claude Code 正在处理请求…", "thread_id": self._thread_id})
                        continue
                    if event_type == "stderr":
                        text = _clean_terminal_output(str(runner_event.get("data") or "")).strip()
                        if text:
                            stderr_lines.append(text)
                            self._append_log({"ts": _now_iso(), "type": "stderr", "content": text, "thread_id": self._thread_id})
                            if on_event is not None:
                                await on_event({"type": "stderr", "message": text, "thread_id": self._thread_id})
                        continue
                    if event_type == "exit":
                        break
                    if event_type != "stdout":
                        continue
                    raw = _clean_terminal_output(str(runner_event.get("data") or "")).strip()
                    if not raw:
                        continue
                    self.last_active_at = _now_iso()
                    self._append_log({"ts": self.last_active_at, "type": "exec_event_raw", "content": raw, "thread_id": self._thread_id})
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        updated, delta = _compute_incremental_text(final_content, raw)
                        final_content = updated
                        if delta and on_event is not None:
                            await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
                        continue
                    final_content = await self._handle_claude_stream_event(payload, final_content, on_event=on_event)
        self._runner_exec_id = ""
        return final_content, stderr_lines, interrupted

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
        if self._effective_runner_url():
            return await self._run_claude_turn_via_runner(cmd, env, cancel_event=cancel_event, on_event=on_event)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.workspace_path,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_process = process
        self._append_log({"ts": _now_iso(), "type": "request_start", "cmd": cmd, "resume": resume, "thread_id": self._thread_id})
        stderr_lines: list[str] = []
        final_content = ""
        interrupted = False
        stderr_task = asyncio.create_task(self._read_exec_stderr(process.stderr, stderr_lines, on_event=on_event))
        try:
            if on_event is not None:
                await on_event({"type": "status", "stage": "turn_started", "message": "Claude Code 正在处理请求…", "thread_id": self._thread_id})
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
                    payload = json.loads(raw)
                except Exception:
                    updated, delta = _compute_incremental_text(final_content, raw)
                    final_content = updated
                    if delta and on_event is not None:
                        await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
                    continue
                final_content = await self._handle_claude_stream_event(payload, final_content, on_event=on_event)
            await process.wait()
            await stderr_task
        finally:
            if not stderr_task.done():
                stderr_task.cancel()
            self._active_process = None
        return final_content, stderr_lines, interrupted


class GeminiExternalAgentSession(ExternalAgentSession):
    def __init__(self, **kwargs: Any) -> None:
        kwargs["agent_type"] = "gemini_cli"
        super().__init__(**kwargs)

    def _build_gemini_exec_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["TERM"] = env.get("TERM") or "xterm-256color"
        env["NO_COLOR"] = "1"
        runtime_home = _gemini_runtime_home_path(self.workspace_path)
        env["HOME"] = str(runtime_home)
        env["USERPROFILE"] = str(runtime_home)
        for key, value in _resolve_gemini_auth_env().items():
            if value and not str(env.get(key) or "").strip():
                env[key] = value
        for key, value in _resolve_gemini_passthrough_env().items():
            if value and not str(env.get(key) or "").strip():
                env[key] = value
        if not str(env.get("GOOGLE_GENAI_USE_VERTEXAI") or "").strip():
            if str(env.get("GOOGLE_API_KEY") or "").strip() or (
                str(env.get("GOOGLE_CLOUD_PROJECT") or "").strip()
                and str(env.get("GOOGLE_CLOUD_LOCATION") or "").strip()
            ):
                env["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        if not str(env.get("GOOGLE_GENAI_USE_GCA") or "").strip():
            runtime_user_dir = _gemini_runtime_user_dir(self.workspace_path)
            if (runtime_user_dir / "oauth_creds.json").is_file():
                env["GOOGLE_GENAI_USE_GCA"] = "true"
        return env

    def _build_exec_command(self, prompt: str, *, resume: bool) -> list[str]:
        effective_prompt = str(prompt or "").strip()
        if self._startup_context and not (resume and self._thread_id):
            effective_prompt = (
                f"{self._startup_context}\n\n"
                "请记住以上上下文，并在本次会话后续持续沿用。\n\n"
                f"{effective_prompt}"
            ).strip()
        cmd = [
            self._command,
            "--output-format",
            "stream-json",
            "--approval-mode",
            _gemini_approval_mode(self.sandbox_mode),
        ]
        if resume and self._thread_id:
            cmd.extend(["--resume", self._thread_id])
        if self.workspace_path:
            cmd.extend(["--include-directories", self.workspace_path])
        cmd.extend(["-p", effective_prompt])
        return cmd

    async def _prepare_session_locked(self) -> str:
        await self.ensure_started()
        return self._thread_id

    async def start_terminal_mirror(self, on_event=None) -> None:
        raise RuntimeError("Gemini CLI 当前接入的是 stream-json 模式，暂不支持终端镜像")

    async def write_terminal_input(self, text: str) -> None:
        raise RuntimeError("Gemini CLI 当前未启用终端镜像输入")

    async def stop_terminal_mirror(self) -> None:
        return

    async def _handle_gemini_stream_event(
        self,
        payload: dict[str, Any],
        final_content: str,
        on_event=None,
    ) -> str:
        event_type = str(payload.get("type") or "").strip().lower()
        if event_type == "init":
            session_id = str(payload.get("session_id") or self._thread_id or "").strip()
            if session_id:
                self._thread_id = session_id
            if on_event is not None and self._thread_id:
                await on_event({
                    "type": "status",
                    "stage": "thread_started",
                    "message": f"已连接到 Gemini 会话 {self._thread_id}",
                    "thread_id": self._thread_id,
                })
            return final_content
        if event_type == "message":
            role = str(payload.get("role") or "").strip().lower()
            if role == "user":
                return final_content
            content = _extract_text_payload(payload.get("content") or payload)
            if not content:
                return final_content
            if bool(payload.get("delta")):
                if on_event is not None:
                    await on_event({"type": "delta", "content": content, "thread_id": self._thread_id})
                return final_content + content
            updated, delta = _compute_incremental_text(final_content, content)
            if delta and on_event is not None:
                await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
            return updated
        if event_type == "tool_use":
            if on_event is not None:
                tool_name = str(payload.get("tool_name") or payload.get("name") or "tool").strip()
                parameters = payload.get("parameters")
                command = tool_name
                if parameters not in (None, "", {}, []):
                    try:
                        command = f"{tool_name} {json.dumps(parameters, ensure_ascii=False)}"
                    except Exception:
                        command = f"{tool_name} {str(parameters)}"
                await on_event({"type": "command_start", "command": command, "thread_id": self._thread_id})
            return final_content
        if event_type == "tool_result":
            if on_event is not None:
                output_preview = _summarize_command_output(
                    _extract_text_payload(payload.get("output") or payload.get("result") or payload)
                )
                await on_event({
                    "type": "command_result",
                    "command": str(payload.get("tool_name") or payload.get("tool_id") or "tool").strip(),
                    "exit_code": None,
                    "status": str(payload.get("status") or "").strip() or "success",
                    "output_preview": output_preview,
                    "thread_id": self._thread_id,
                })
            return final_content
        if event_type == "error":
            message = _extract_text_payload(payload) or str(payload.get("message") or "Gemini CLI 执行失败")
            severity = str(payload.get("severity") or "error").strip().lower()
            if severity in {"warning", "info"}:
                if on_event is not None and message:
                    await on_event({"type": "stderr", "message": message, "thread_id": self._thread_id})
                return final_content
            raise RuntimeError(message)
        if event_type == "result":
            stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
            if on_event is not None and stats:
                await on_event({"type": "usage", "usage": stats, "thread_id": self._thread_id})
            status = str(payload.get("status") or "").strip().lower()
            if status and status not in {"success", "ok"}:
                message = _extract_text_payload(payload) or str(payload.get("message") or status)
                raise RuntimeError(message)
            return final_content
        return final_content

    async def _run_gemini_turn_via_runner(
        self,
        cmd: list[str],
        env: dict[str, str],
        *,
        cancel_event: asyncio.Event | None = None,
        on_event=None,
    ) -> tuple[str, list[str], bool]:
        runner_url = self._effective_runner_url()
        if not runner_url:
            raise RuntimeError("未配置 EXTERNAL_AGENT_RUNNER_URL")
        self._append_log({"ts": _now_iso(), "type": "request_start", "cmd": cmd, "resume": bool(self._thread_id), "thread_id": self._thread_id, "execution_mode": "runner"})
        stderr_lines: list[str] = []
        final_content = ""
        interrupted = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
            async with client.stream(
                "POST",
                f"{runner_url}/exec/stream",
                headers=self._effective_runner_headers(),
                json={"cmd": cmd, "cwd": self.workspace_path, "env": env},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if cancel_event is not None and cancel_event.is_set() and not interrupted:
                        interrupted = True
                        await self._terminate_active_process()
                    raw_line = str(line or "").strip()
                    if not raw_line:
                        continue
                    try:
                        runner_event = json.loads(raw_line)
                    except Exception:
                        continue
                    event_type = str(runner_event.get("type") or "").strip()
                    if event_type == "started":
                        self._runner_exec_id = str(runner_event.get("exec_id") or "").strip()
                        if on_event is not None:
                            await on_event({"type": "status", "stage": "turn_started", "message": "Gemini CLI 正在处理请求…", "thread_id": self._thread_id})
                        continue
                    if event_type == "stderr":
                        text = _clean_terminal_output(str(runner_event.get("data") or "")).strip()
                        if text:
                            stderr_lines.append(text)
                            self._append_log({"ts": _now_iso(), "type": "stderr", "content": text, "thread_id": self._thread_id})
                            if on_event is not None:
                                await on_event({"type": "stderr", "message": text, "thread_id": self._thread_id})
                        continue
                    if event_type == "exit":
                        break
                    if event_type != "stdout":
                        continue
                    raw = _clean_terminal_output(str(runner_event.get("data") or "")).strip()
                    if not raw:
                        continue
                    self.last_active_at = _now_iso()
                    self._append_log({"ts": self.last_active_at, "type": "exec_event_raw", "content": raw, "thread_id": self._thread_id})
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        updated, delta = _compute_incremental_text(final_content, raw)
                        final_content = updated
                        if delta and on_event is not None:
                            await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
                        continue
                    final_content = await self._handle_gemini_stream_event(payload, final_content, on_event=on_event)
        self._runner_exec_id = ""
        return final_content, stderr_lines, interrupted

    async def _run_exec_turn(
        self,
        prompt: str,
        *,
        resume: bool,
        cancel_event: asyncio.Event | None = None,
        on_event=None,
    ) -> tuple[str, list[str], bool]:
        cmd = self._build_exec_command(prompt, resume=resume)
        env = self._build_gemini_exec_env()
        if self._effective_runner_url():
            return await self._run_gemini_turn_via_runner(cmd, env, cancel_event=cancel_event, on_event=on_event)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.workspace_path,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_process = process
        self._append_log({"ts": _now_iso(), "type": "request_start", "cmd": cmd, "resume": resume, "thread_id": self._thread_id})
        stderr_lines: list[str] = []
        final_content = ""
        interrupted = False
        stderr_task = asyncio.create_task(self._read_exec_stderr(process.stderr, stderr_lines, on_event=on_event))
        try:
            if on_event is not None:
                await on_event({"type": "status", "stage": "turn_started", "message": "Gemini CLI 正在处理请求…", "thread_id": self._thread_id})
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
                    payload = json.loads(raw)
                except Exception:
                    updated, delta = _compute_incremental_text(final_content, raw)
                    final_content = updated
                    if delta and on_event is not None:
                        await on_event({"type": "delta", "content": delta, "thread_id": self._thread_id})
                    continue
                final_content = await self._handle_gemini_stream_event(payload, final_content, on_event=on_event)
            await process.wait()
            await stderr_task
        finally:
            if not stderr_task.done():
                stderr_task.cancel()
            self._active_process = None
        return final_content, stderr_lines, interrupted

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
            self.last_active_at = _now_iso()
            prompt_risks = _collect_risk_signals(user_prompt)
            before_diff_summary = self._workspace_diff_summary()
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
                    resume=bool(self._thread_id),
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
                raise RuntimeError("外部 Agent 未返回有效内容")

            output_risks = _collect_risk_signals(final_content)
            after_diff_summary = self._workspace_diff_summary()
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

def create_external_agent_session(**kwargs: Any) -> ExternalAgentSession:
    agent_type = normalize_external_agent_type(kwargs.get("agent_type"))
    if agent_type == "claude_cli":
        return ClaudeExternalAgentSession(**kwargs)
    if agent_type == "gemini_cli":
        return GeminiExternalAgentSession(**kwargs)
    return ExternalAgentSession(**kwargs)
