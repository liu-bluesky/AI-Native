"""Project chat local host command helpers."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from core.config import get_project_root
from services.cli_plugin_market_service import build_cli_plugin_runtime_environment

PROJECT_HOST_RUN_COMMAND_TOOL_NAME = "project_host_run_command"
_PROJECT_WORKSPACE_SOURCE = "project_workspace"
_SERVICE_REPO_ROOT_FALLBACK_SOURCE = "service_repo_root_fallback"
_SERVICE_START_SCRIPT_HINT = "web-admin/api/scripts/start_api_with_runner.sh"

_BLOCKED_COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(^|[;&|])\s*rm\s+-rf\s+/(?:\s|$)", re.IGNORECASE),
        "禁止执行会清空系统根目录的命令。",
    ),
    (
        re.compile(r"\b(shutdown|reboot|halt|poweroff)\b", re.IGNORECASE),
        "禁止执行会关闭或重启当前电脑的命令。",
    ),
    (
        re.compile(r"\bmkfs(?:\.[0-9A-Za-z_+-]+)?\b", re.IGNORECASE),
        "禁止执行会格式化磁盘的命令。",
    ),
    (
        re.compile(r"\bdiskutil\s+eraseDisk\b", re.IGNORECASE),
        "禁止执行会擦除磁盘的命令。",
    ),
    (
        re.compile(r"\bdd\b[^\n]*\bof=/dev/", re.IGNORECASE),
        "禁止执行会直接写入设备文件的命令。",
    ),
)


def build_project_host_command_tools(workspace_path: str) -> list[dict[str, Any]]:
    normalized_workspace_path = str(workspace_path or "").strip()
    return [
        {
            "tool_name": PROJECT_HOST_RUN_COMMAND_TOOL_NAME,
            "description": (
                "在当前项目所在电脑上直接执行 shell 命令，不依赖 Local Connector。"
                "适合本地运行项目时执行安装、构建、测试、脚本和排障命令。"
                "若项目未配置 workspace_path，会回退到当前 API 服务所在仓库根目录执行。"
                "当用户明确要你在当前电脑执行命令、安装、登录验证、查看状态、列出数据或返回实际结果时，"
                "应优先直接执行并返回结果，不要只给命令让用户自己执行。"
                "只有遇到真实交互阻塞、权限受限或必须由用户亲自完成的授权步骤时，"
                "才改为说明阻塞点和下一步。"
                "执行后应明确告知用户本次命令使用的工作目录和环境来源。"
            ),
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "必填，要执行的 shell 命令。需要交互确认的命令应自行加上非交互参数，"
                            "例如 npm/yarn/pnpm/npx 安装命令。"
                        ),
                    },
                    "cwd": {
                        "type": "string",
                        "description": "可选。相对项目工作区的子目录；留空表示项目根目录。",
                    },
                    "timeout_sec": {
                        "type": "integer",
                        "description": "超时时间秒数，默认 20，范围 1-600。",
                    },
                    "max_output_chars": {
                        "type": "integer",
                        "description": "stdout/stderr 各自最多保留的字符数，默认 12000。",
                    },
                },
                "required": ["command"],
            },
            "builtin": True,
            "module_type": "builtin_tool",
            "workspace_path": normalized_workspace_path,
        }
    ]


def is_project_host_command_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() == PROJECT_HOST_RUN_COMMAND_TOOL_NAME


def run_project_host_command(
    *,
    workspace_path: str,
    command: str,
    cwd: str = "",
    timeout_sec: int = 20,
    max_output_chars: int = 12000,
) -> dict[str, Any]:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return {"error": "command is required"}
    if len(normalized_command) > 4000:
        return {"error": "command is too long"}

    blocked_reason = _match_blocked_command(normalized_command)
    requested_workspace_path = str(workspace_path or "").strip()
    try:
        workspace_root, workspace_source = _resolve_workspace_root(workspace_path)
    except ValueError as exc:
        return {
            "error": str(exc),
            "requested_workspace_path": requested_workspace_path,
        }
    environment_metadata = _build_environment_metadata(
        workspace_root=workspace_root,
        workspace_source=workspace_source,
        requested_workspace_path=requested_workspace_path,
    )
    if blocked_reason:
        return {
            "ok": False,
            "blocked": True,
            "error": blocked_reason,
            "command": normalized_command,
            "workspace_path": str(workspace_root),
            "cwd": str(workspace_root),
            **environment_metadata,
        }

    try:
        resolved_cwd = _resolve_command_cwd(workspace_root, cwd)
    except ValueError as exc:
        return {
            "error": str(exc),
            "workspace_path": str(workspace_root),
            "requested_cwd": str(cwd or "").strip(),
            **environment_metadata,
        }

    shell_args = _build_shell_args(normalized_command)
    safe_timeout = max(1, min(int(timeout_sec or 20), 600))
    safe_output_limit = max(200, min(int(max_output_chars or 12000), 40000))
    exec_env, plugin_runtime_metadata = build_cli_plugin_runtime_environment()
    environment_metadata.update(plugin_runtime_metadata)
    if plugin_runtime_metadata.get("plugin_runtime_enabled"):
        path_entries = list(plugin_runtime_metadata.get("plugin_runtime_path_entries") or [])
        if path_entries:
            environment_metadata["plugin_runtime_summary"] = (
                "已附加已安装插件运行路径："
                + ", ".join(path_entries)
            )

    try:
        completed = subprocess.run(
            shell_args,
            cwd=str(resolved_cwd),
            capture_output=True,
            text=True,
            timeout=safe_timeout,
            env=exec_env,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "command": normalized_command,
            "workspace_path": str(workspace_root),
            "cwd": str(resolved_cwd),
            **environment_metadata,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "timed_out": True,
            "error": f"Command timed out after {safe_timeout} seconds",
            "command": normalized_command,
            "workspace_path": str(workspace_root),
            "cwd": str(resolved_cwd),
            "stdout": _truncate_output(exc.stdout, safe_output_limit),
            "stderr": _truncate_output(exc.stderr, safe_output_limit),
            **environment_metadata,
        }

    return {
        "ok": completed.returncode == 0,
        "command": normalized_command,
        "workspace_path": str(workspace_root),
        "cwd": str(resolved_cwd),
        "exit_code": int(completed.returncode),
        "stdout": _truncate_output(completed.stdout, safe_output_limit),
        "stderr": _truncate_output(completed.stderr, safe_output_limit),
        "source": "project_host",
        **environment_metadata,
    }


def _match_blocked_command(command: str) -> str:
    for pattern, reason in _BLOCKED_COMMAND_PATTERNS:
        if pattern.search(command):
            return reason
    return ""


def _resolve_workspace_root(workspace_path: str) -> tuple[Path, str]:
    normalized_workspace_path = str(workspace_path or "").strip()
    if not normalized_workspace_path:
        try:
            return get_project_root().resolve(), _SERVICE_REPO_ROOT_FALLBACK_SOURCE
        except RuntimeError as exc:
            raise ValueError(f"Cannot resolve fallback service repo root: {exc}") from exc
    candidate = Path(normalized_workspace_path).expanduser()
    if not candidate.is_absolute():
        raise ValueError("Host workspace_path must be absolute")
    resolved = candidate.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError("Host workspace_path does not exist")
    return resolved, _PROJECT_WORKSPACE_SOURCE


def _build_environment_metadata(
    *,
    workspace_root: Path,
    workspace_source: str,
    requested_workspace_path: str,
) -> dict[str, str]:
    if workspace_source == _PROJECT_WORKSPACE_SOURCE:
        environment_label = "项目工作区"
        environment_summary = f"命令在项目工作区执行：{workspace_root}"
    else:
        environment_label = "当前 API 服务仓库根目录（回退）"
        environment_summary = (
            "项目未配置 workspace_path，已回退到当前 API 服务所在仓库根目录执行："
            f"{workspace_root}"
        )
    return {
        "workspace_source": workspace_source,
        "requested_workspace_path": requested_workspace_path,
        "environment_label": environment_label,
        "environment_summary": environment_summary,
        "service_start_script_hint": _SERVICE_START_SCRIPT_HINT,
    }


def _resolve_command_cwd(workspace_root: Path, cwd: str) -> Path:
    normalized_cwd = str(cwd or "").strip()
    if not normalized_cwd:
        return workspace_root
    candidate = Path(normalized_cwd).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    resolved = candidate.resolve()
    if not _is_path_within_workspace(resolved, workspace_root):
        raise ValueError("cwd must stay within project workspace")
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError("cwd does not exist")
    return resolved


def _is_path_within_workspace(candidate: Path, workspace_root: Path) -> bool:
    try:
        candidate.relative_to(workspace_root)
        return True
    except ValueError:
        return False


def _build_shell_args(command: str) -> list[str]:
    if os.name == "nt":
        return ["cmd", "/C", command]
    return ["/bin/bash", "-lc", command]


def _truncate_output(value: Any, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    half = max(40, max_chars // 2)
    omitted = len(text) - half * 2
    return f"{text[:half]}\n... [truncated {omitted} chars] ...\n{text[-half:]}"
