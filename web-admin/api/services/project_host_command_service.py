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
PROJECT_HOST_TERMINAL_START_TOOL_NAME = "project_host_terminal_start"
PROJECT_HOST_TERMINAL_INPUT_TOOL_NAME = "project_host_terminal_input"
PROJECT_HOST_TERMINAL_READ_TOOL_NAME = "project_host_terminal_read"
PROJECT_HOST_TERMINAL_STOP_TOOL_NAME = "project_host_terminal_stop"
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
                        "description": "超时时间秒数，默认 20；填 0 表示不限制，范围 0-600。",
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
        },
        {
            "tool_name": PROJECT_HOST_TERMINAL_START_TOOL_NAME,
            "description": (
                "启动或附加当前项目的交互式 PTY 终端。适合处理第三方 CLI 的菜单选择、验证码、"
                "设备授权、REPL、持续输出或其它需要多轮输入的场景。可传 initial_command 启动后立即执行。"
            ),
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "initial_command": {
                        "type": "string",
                        "description": "可选。终端启动或附加后立即发送的命令，系统会自动补回车。",
                    },
                },
            },
            "builtin": True,
            "module_type": "builtin_tool",
            "workspace_path": normalized_workspace_path,
        },
        {
            "tool_name": PROJECT_HOST_TERMINAL_INPUT_TOOL_NAME,
            "description": (
                "向当前项目已启动的交互式 PTY 终端发送文本。发送普通命令或菜单确认时需要自行包含换行，"
                "例如 content='1\\n'、content='y\\n' 或 content='\\u001b[B\\n'。"
            ),
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "必填。要发送到终端 stdin 的原始文本。",
                    },
                },
                "required": ["content"],
            },
            "builtin": True,
            "module_type": "builtin_tool",
            "workspace_path": normalized_workspace_path,
        },
        {
            "tool_name": PROJECT_HOST_TERMINAL_READ_TOOL_NAME,
            "description": "读取当前项目交互式 PTY 终端最近输出，用于判断下一步应输入什么。",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "max_chars": {
                        "type": "integer",
                        "description": "最多返回最近多少字符，默认 12000，范围 200-40000。",
                    },
                },
            },
            "builtin": True,
            "module_type": "builtin_tool",
            "workspace_path": normalized_workspace_path,
        },
        {
            "tool_name": PROJECT_HOST_TERMINAL_STOP_TOOL_NAME,
            "description": "停止当前项目交互式 PTY 终端。交互任务结束或需要清理挂起进程时使用。",
            "parameters_schema": {
                "type": "object",
                "properties": {},
            },
            "builtin": True,
            "module_type": "builtin_tool",
            "workspace_path": normalized_workspace_path,
        },
    ]


def is_project_host_command_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() == PROJECT_HOST_RUN_COMMAND_TOOL_NAME


def is_project_host_terminal_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() in {
        PROJECT_HOST_TERMINAL_START_TOOL_NAME,
        PROJECT_HOST_TERMINAL_INPUT_TOOL_NAME,
        PROJECT_HOST_TERMINAL_READ_TOOL_NAME,
        PROJECT_HOST_TERMINAL_STOP_TOOL_NAME,
    }


def run_project_host_command(
    *,
    workspace_path: str,
    command: str,
    owner_username: str = "",
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
    try:
        safe_timeout = max(0, min(int(timeout_sec), 600))
    except (TypeError, ValueError):
        safe_timeout = 20
    safe_output_limit = max(200, min(int(max_output_chars or 12000), 40000))
    exec_env, plugin_runtime_metadata = build_cli_plugin_runtime_environment(
        owner_username=str(owner_username or "").strip(),
    )
    environment_metadata.update(plugin_runtime_metadata)
    if plugin_runtime_metadata.get("plugin_runtime_enabled"):
        path_entries = list(plugin_runtime_metadata.get("plugin_runtime_path_entries") or [])
        if path_entries:
            environment_metadata["plugin_runtime_summary"] = (
                "已附加已安装插件运行路径："
                + ", ".join(path_entries)
            )
    runtime_home = str(plugin_runtime_metadata.get("plugin_runtime_home") or "").strip()
    if runtime_home:
        environment_metadata["plugin_runtime_summary"] = (
            str(environment_metadata.get("plugin_runtime_summary") or "").strip() + f"；用户隔离 HOME={runtime_home}"
        ).strip("；")

    try:
        completed = subprocess.run(
            shell_args,
            cwd=str(resolved_cwd),
            capture_output=True,
            text=False,
            timeout=safe_timeout if safe_timeout > 0 else None,
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
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value or "")
    if len(text) <= max_chars:
        return text
    half = max(40, max_chars // 2)
    omitted = len(text) - half * 2
    return f"{text[:half]}\n... [truncated {omitted} chars] ...\n{text[-half:]}"
