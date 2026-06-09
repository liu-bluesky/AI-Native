from __future__ import annotations
import asyncio
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from core.config import get_settings


_LARK_AUTH_DOMAIN_ALIAS_NAMES = (
    "approval",
    "attendance",
    "base",
    "calendar",
    "contact",
    "docs",
    "drive",
    "im",
    "mail",
    "minutes",
    "okr",
    "sheets",
    "task",
    "vc",
    "wiki",
)
_LARK_AUTH_DOMAIN_ALIAS_PATTERN = re.compile(
    rf"^(?:{'|'.join(_LARK_AUTH_DOMAIN_ALIAS_NAMES)})(?:\s*,\s*(?:{'|'.join(_LARK_AUTH_DOMAIN_ALIAS_NAMES)}))*$",
    re.IGNORECASE,
)
_TASK_TREE_TOOL_NAMES = {
    "get_current_task_tree",
    "update_task_node_status",
    "complete_task_node_with_verification",
}
_LARK_AUTH_ACTION_TERMS = {
    "login": frozenset({"login", "登录", "授权"}),
    "logout": frozenset(
        {
            "logout",
            "退出",
            "退出登录",
            "退出登陆",
            "登出",
            "登出登录",
            "登出登陆",
            "注销",
            "注销登录",
            "注销登陆",
        }
    ),
    "status": frozenset({"status", "状态", "登录状态", "检测登录", "检测登录状态"}),
}


@dataclass(frozen=True)
class _LarkCliAuthIntent:
    action: str
    suffix: str = ""
    explicit_command: str = ""


def _parse_shell_like_command(command: str) -> list[str]:
    try:
        return shlex.split(str(command or "").strip())
    except ValueError:
        return str(command or "").strip().split()


def _compact_lark_cli_auth_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _strip_lark_cli_command_prefix(command: str) -> str:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return ""
    return re.sub(
        r"^/?(?:\S+/)?lark-cli(?:\s+|$)",
        "",
        normalized_command,
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def _parse_lark_cli_auth_intent(command: str) -> _LarkCliAuthIntent | None:
    """Resolve user-facing lark-cli auth text into a canonical auth action."""

    normalized_command = str(command or "").strip()
    if not normalized_command:
        return None
    args = _parse_shell_like_command(normalized_command)
    if any(str(arg or "").strip().lower() in {"-h", "--help", "help"} for arg in args):
        return None
    has_lark_cli_prefix = False
    if args and str(args[0] or "").split("/")[-1] == "lark-cli":
        has_lark_cli_prefix = True
        lowered = [str(item or "").strip().lower() for item in args]
        if len(lowered) == 1:
            return _LarkCliAuthIntent("status")
        if len(lowered) >= 3 and lowered[1] == "auth" and lowered[2] in {
            "login",
            "logout",
            "status",
        }:
            suffix = " ".join(args[3:]).strip()
            return _LarkCliAuthIntent(
                lowered[2],
                suffix=suffix,
                explicit_command=normalized_command,
            )
        if len(lowered) >= 3 and lowered[1] == "login" and lowered[2] in {
            "logout",
            "status",
        }:
            suffix = " ".join(args[3:]).strip()
            return _LarkCliAuthIntent(lowered[2], suffix=suffix)
        auth_text = _strip_lark_cli_command_prefix(normalized_command)
    else:
        auth_text = normalized_command

    lowered_text = auth_text.lower()
    compact_text = _compact_lark_cli_auth_text(auth_text)
    if compact_text == "status" or (
        has_lark_cli_prefix and compact_text in _LARK_AUTH_ACTION_TERMS["status"]
    ):
        return _LarkCliAuthIntent("status")
    if compact_text in _LARK_AUTH_ACTION_TERMS["logout"]:
        return _LarkCliAuthIntent("logout")
    if lowered_text == "login status":
        return _LarkCliAuthIntent("status")
    if lowered_text == "login logout":
        return _LarkCliAuthIntent("logout")
    auth_match = re.match(
        r"^auth\s+(login|logout|status)(?:\s+([\s\S]*))?$",
        auth_text,
        re.IGNORECASE,
    )
    if auth_match:
        action = str(auth_match.group(1) or "").strip().lower()
        suffix = str(auth_match.group(2) or "").strip()
        return _LarkCliAuthIntent(action, suffix=suffix)
    for term in sorted(_LARK_AUTH_ACTION_TERMS["login"], key=len, reverse=True):
        if compact_text == term:
            return _LarkCliAuthIntent("login")
        if lowered_text.startswith(f"{term} "):
            return _LarkCliAuthIntent("login", suffix=auth_text[len(term) :].strip())
    return None


def _lark_auth_login_args_include_authorization_scope(args: list[str]) -> bool:
    lowered_args = [str(arg or "").strip().lower() for arg in args]
    for index, arg in enumerate(lowered_args):
        if arg in {"--recommend", "--device-code"}:
            return True
        if arg.startswith("--device-code="):
            return True
        if arg in {"--scope", "--domain"} and index + 1 < len(lowered_args):
            return True
        if arg.startswith("--scope=") or arg.startswith("--domain="):
            return True
    return False


def _normalize_lark_auth_login_command(command: str) -> str:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return ""
    intent = _parse_lark_cli_auth_intent(normalized_command)
    if intent is None or intent.action != "login":
        return ""
    if intent.explicit_command:
        explicit_args = _parse_shell_like_command(intent.explicit_command)
        if len(explicit_args) == 3:
            return "lark-cli auth login --recommend"
        if not _lark_auth_login_args_include_authorization_scope(explicit_args[3:]):
            return "lark-cli auth login --recommend"
        return intent.explicit_command
    suffix = intent.suffix
    if not suffix or suffix.lower() in {"recommend", "推荐"}:
        return "lark-cli auth login --recommend"
    if suffix.startswith("--"):
        if not _lark_auth_login_args_include_authorization_scope(
            _parse_shell_like_command(suffix)
        ):
            return "lark-cli auth login --recommend"
        return f"lark-cli auth login {suffix}"
    if _LARK_AUTH_DOMAIN_ALIAS_PATTERN.fullmatch(suffix):
        compact_suffix = re.sub(r"\s+", "", suffix)
        return f"lark-cli auth login --domain {compact_suffix}"
    return "lark-cli auth login --recommend"


def _normalize_lark_auth_logout_command(command: str) -> str:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return ""
    intent = _parse_lark_cli_auth_intent(normalized_command)
    if intent is None or intent.action != "logout":
        return ""
    if not intent.explicit_command:
        return "lark-cli auth logout"
    return intent.explicit_command


def _normalize_lark_auth_status_command(command: str) -> str:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return ""
    intent = _parse_lark_cli_auth_intent(normalized_command)
    if intent is None or intent.action != "status":
        return ""
    if intent.explicit_command:
        return intent.explicit_command
    return "lark-cli auth status"


def normalize_lark_cli_user_command(command: str) -> str:
    """Normalize explicit user-facing lark-cli aliases into executable commands."""

    normalized_command = str(command or "").strip()
    if not normalized_command:
        return ""
    direct = (
        _normalize_lark_auth_logout_command(normalized_command)
        or _normalize_lark_auth_status_command(normalized_command)
        or _normalize_lark_auth_login_command(normalized_command)
    )
    if direct:
        return direct
    return ""


def _normalize_lark_command_segments(command: str) -> str:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return ""
    direct = normalize_lark_cli_user_command(normalized_command)
    if direct:
        return direct
    pieces = re.split(r"(\s*(?:&&|\|\||;)\s*)", normalized_command)
    if len(pieces) <= 1:
        return (
            _normalize_lark_auth_logout_command(normalized_command)
            or _normalize_lark_auth_status_command(normalized_command)
            or normalized_command
        )
    changed = False
    next_pieces: list[str] = []
    for piece in pieces:
        if re.fullmatch(r"\s*(?:&&|\|\||;)\s*", piece):
            next_pieces.append(piece)
            continue
        stripped = piece.strip()
        replacement = (
            _normalize_lark_auth_logout_command(stripped)
            or _normalize_lark_auth_status_command(stripped)
        )
        if replacement:
            leading = piece[: len(piece) - len(piece.lstrip())]
            trailing = piece[len(piece.rstrip()) :]
            next_pieces.append(f"{leading}{replacement}{trailing}")
            changed = True
        else:
            next_pieces.append(piece)
    return "".join(next_pieces) if changed else normalized_command


def _normalize_lark_status_command_segments(command: str) -> str:
    return _normalize_lark_command_segments(command)


def _is_lark_cli_global_auth_command(command: str) -> bool:
    args = _parse_shell_like_command(command)
    if len(args) < 3:
        return False
    binary = str(args[0] or "").split("/")[-1]
    lowered = [str(item or "").strip().lower() for item in args]
    return binary == "lark-cli" and lowered[1] == "auth" and lowered[2] in {
        "status",
        "logout",
    }


def _command_matches_pattern(command: str, pattern: str) -> bool:
    normalized_command = str(command or "").strip()
    normalized_pattern = str(pattern or "").strip()
    if not normalized_command or not normalized_pattern:
        return False
    try:
        return re.search(normalized_pattern, normalized_command, re.IGNORECASE) is not None
    except re.error:
        return normalized_pattern.lower() in normalized_command.lower()


def _iter_cli_auth_command_candidates(command: str) -> list[str]:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return []
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str) -> None:
        normalized_value = str(value or "").strip()
        if not normalized_value or normalized_value in seen:
            return
        seen.add(normalized_value)
        candidates.append(normalized_value)

    add_candidate(normalized_command)
    for line in normalized_command.splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        add_candidate(stripped_line)
        for segment in re.split(r"\s*(?:&&|\|\||;)\s*", stripped_line):
            add_candidate(segment)
    return candidates


def _normalize_cli_auth_operation_command(command: str) -> dict[str, str]:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return {}
    command_candidates = _iter_cli_auth_command_candidates(normalized_command)

    from services.plugins.cli_plugin_market_service import list_cli_plugins

    for plugin in list_cli_plugins(include_status=False):
        auth = plugin.get("auth") if isinstance(plugin.get("auth"), dict) else {}
        patterns = [
            str(item or "").strip()
            for item in (auth.get("command_patterns") or [])
            if str(item or "").strip()
        ]
        for candidate in command_candidates:
            candidate_args = _parse_shell_like_command(candidate)
            if any(str(arg or "").strip().lower() in {"-h", "--help", "help"} for arg in candidate_args):
                continue
            if patterns and any(_command_matches_pattern(candidate, pattern) for pattern in patterns):
                return {
                    "plugin_id": str(plugin.get("id") or "").strip(),
                    "command": candidate,
                }

    for candidate in command_candidates:
        lark_alias = _normalize_lark_auth_login_command(candidate)
        if lark_alias:
            return {"plugin_id": "feishu-cli", "command": lark_alias}
    return {}


class ToolExecutor:
    def __init__(
        self,
        project_id: str,
        employee_id: str,
        *,
        username: str = "",
        chat_session_id: str = "",
        role_ids: list[str] | None = None,
        timeout_sec: int | None = None,
        max_retries: int = 0,
        allowed_tool_names: list[str] | None = None,
        local_connector: Any | None = None,
        local_connector_workspace_path: str = "",
        host_workspace_path: str = "",
        local_connector_sandbox_mode: str = "workspace-write",
        global_assistant_bridge_handler: Any | None = None,
    ):
        self._project_id = project_id
        self._employee_id = employee_id
        self._username = str(username or "").strip()
        self._chat_session_id = str(chat_session_id or "").strip()
        self._role_ids = [
            str(item or "").strip().lower()
            for item in (role_ids or [])
            if str(item or "").strip()
        ]
        settings = get_settings()
        base_timeout = int(settings.tool_timeout)
        if timeout_sec is not None:
            try:
                base_timeout = int(timeout_sec)
            except (TypeError, ValueError):
                pass
        self._timeout = max(0, min(base_timeout, 600))
        try:
            retries = int(max_retries)
        except (TypeError, ValueError):
            retries = 0
        self._max_retries = max(0, min(retries, 5))
        self._allowed_tool_names = {
            str(name or "").strip()
            for name in (allowed_tool_names or [])
            if str(name or "").strip()
        }
        self._local_connector = local_connector
        self._local_connector_workspace_path = str(local_connector_workspace_path or "").strip()
        self._host_workspace_path = str(host_workspace_path or "").strip()
        self._local_connector_sandbox_mode = (
            str(local_connector_sandbox_mode or "workspace-write").strip()
            or "workspace-write"
        )
        self._global_assistant_bridge_handler = global_assistant_bridge_handler

    async def execute_parallel(self, tool_calls: list[dict], timeout: int | None = None) -> list[dict]:
        timeout = self._timeout if timeout is None else timeout
        tasks = [self._execute_with_timeout(tc, timeout) for tc in tool_calls]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_with_timeout(self, tool_call: dict, timeout: int | None) -> dict:
        tool_name = tool_call["function"]["name"]
        args_str = tool_call["function"]["arguments"]
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON arguments: {args_str}"}
        args = self._inject_runtime_context_args(tool_name, args)
        call_id = str(tool_call.get("id") or "").strip()
        if call_id:
            args.setdefault("_agent_runtime_call_id", call_id)
        args.setdefault("_agent_runtime_tool_name", str(tool_name or "").strip())

        if self._allowed_tool_names and str(tool_name or "").strip() not in self._allowed_tool_names:
            return {"error": f"Tool {tool_name} is not allowed in current chat settings"}

        attempt = 0
        while True:
            try:
                effective_timeout = self._resolve_tool_timeout(tool_name, args, timeout)
                if effective_timeout is None or effective_timeout <= 0:
                    result = await self._execute_tool(tool_name, args)
                else:
                    result = await asyncio.wait_for(
                        self._execute_tool(tool_name, args),
                        timeout=effective_timeout
                    )
                return result
            except asyncio.TimeoutError:
                if attempt >= self._max_retries:
                    return {"error": f"Tool {tool_name} execution timeout"}
            except Exception as e:
                if attempt >= self._max_retries:
                    return {"error": f"Tool {tool_name} failed: {str(e)}"}
            attempt += 1

    def _inject_runtime_context_args(self, tool_name: str, args: Any) -> dict:
        payload = dict(args or {}) if isinstance(args, dict) else {}
        normalized_tool_name = str(tool_name or "").strip()
        if normalized_tool_name in _TASK_TREE_TOOL_NAMES:
            if self._chat_session_id and not str(payload.get("chat_session_id") or "").strip():
                payload["chat_session_id"] = self._chat_session_id
            if self._username and not str(payload.get("username") or "").strip():
                payload["username"] = self._username
        return payload

    async def _execute_tool(self, tool_name: str, args: dict) -> dict:
        from services.assistant.global_assistant_service import (
            is_global_assistant_builtin_tool,
            execute_global_assistant_builtin_tool,
        )

        if is_global_assistant_builtin_tool(tool_name):
            return await execute_global_assistant_builtin_tool(
                tool_name,
                args,
                username=self._username,
                role_ids=self._role_ids,
                browser_bridge_handler=self._global_assistant_bridge_handler,
            )
        if str(tool_name or "").strip() == "project_host_run_command":
            return await self._execute_project_host_command(args)
        if str(tool_name or "").strip().startswith("project_host_terminal_"):
            return await self._execute_project_host_terminal_tool(tool_name, args)
        if str(tool_name or "").strip().startswith("local_connector_"):
            return await self._execute_local_connector_tool(tool_name, args)
        from services.mcp.dynamic_mcp_runtime import invoke_project_tool_runtime
        from starlette.concurrency import run_in_threadpool
        result = await run_in_threadpool(
            invoke_project_tool_runtime,
            project_id=self._project_id,
            tool_name=tool_name,
            employee_id=self._employee_id,
            username=self._username,
            chat_session_id=self._chat_session_id,
            args=args,
            args_json=json.dumps(args),
            timeout_sec=self._timeout
        )
        return result

    async def _execute_local_connector_tool(self, tool_name: str, args: dict) -> dict:
        from services.connectors.local_connector_service import (
            LOCAL_CONNECTOR_FILE_TOOL_NAMES,
            list_connector_workspace_files,
            read_connector_file,
            search_connector_workspace_files,
            write_connector_file,
        )

        normalized_tool_name = str(tool_name or "").strip()
        if normalized_tool_name not in LOCAL_CONNECTOR_FILE_TOOL_NAMES:
            return {"error": f"Unsupported local connector tool: {normalized_tool_name}"}
        if self._local_connector is None:
            return {"error": "Local connector is not configured for current chat"}
        if not self._local_connector_workspace_path:
            return {"error": "Local connector workspace_path is empty"}

        if normalized_tool_name == "local_connector_list_files":
            return await list_connector_workspace_files(
                self._local_connector,
                workspace_path=self._local_connector_workspace_path,
                path=str(args.get("path") or "").strip(),
                depth=int(args.get("depth", 3) or 3),
                limit=int(args.get("limit", 200) or 200),
                include_hidden=bool(args.get("include_hidden")),
                sandbox_mode=self._local_connector_sandbox_mode,
            )

        if normalized_tool_name == "local_connector_search_files":
            return await search_connector_workspace_files(
                self._local_connector,
                workspace_path=self._local_connector_workspace_path,
                query=str(args.get("query") or "").strip(),
                path=str(args.get("path") or "").strip(),
                depth=int(args.get("depth", 8) or 8),
                limit=int(args.get("limit", 100) or 100),
                case_sensitive=bool(args.get("case_sensitive")),
                include_hidden=bool(args.get("include_hidden")),
                sandbox_mode=self._local_connector_sandbox_mode,
            )

        if normalized_tool_name == "local_connector_read_file":
            end_line = args.get("end_line")
            return await read_connector_file(
                self._local_connector,
                workspace_path=self._local_connector_workspace_path,
                path=str(args.get("path") or "").strip(),
                start_line=int(args.get("start_line", 1) or 1),
                end_line=int(end_line) if end_line is not None else None,
                sandbox_mode=self._local_connector_sandbox_mode,
            )

        return await write_connector_file(
            self._local_connector,
            workspace_path=self._local_connector_workspace_path,
            path=str(args.get("path") or "").strip(),
            content=str(args.get("content") or ""),
            sandbox_mode=self._local_connector_sandbox_mode,
        )

    async def _execute_project_host_command(self, args: dict) -> dict:
        command = _normalize_lark_command_segments(
            str(args.get("command") or "").strip()
        )
        routed_login_result = await self._maybe_execute_cli_auth_operation_task(
            command=command,
            timeout_sec=int(args.get("timeout_sec", 20)),
            agent_runtime_context={
                "run_id": str(args.get("_agent_runtime_run_id") or "").strip(),
                "call_id": str(args.get("_agent_runtime_call_id") or "").strip(),
                "tool_name": str(args.get("_agent_runtime_tool_name") or "project_host_run_command").strip(),
            },
        )
        if routed_login_result is not None:
            return routed_login_result

        from services.connectors.project_host_command_service import run_project_host_command
        from starlette.concurrency import run_in_threadpool

        host_workspace_path = self._host_workspace_path
        if _is_lark_cli_global_auth_command(command) and host_workspace_path:
            candidate = Path(host_workspace_path).expanduser()
            if not candidate.exists() or not candidate.is_dir():
                host_workspace_path = ""

        return await run_in_threadpool(
            run_project_host_command,
            workspace_path=host_workspace_path,
            command=command,
            owner_username=self._username,
            cwd=str(args.get("cwd") or "").strip(),
            timeout_sec=int(args.get("timeout_sec", 20)),
            max_output_chars=int(args.get("max_output_chars", 12000) or 12000),
        )

    async def _execute_project_host_terminal_tool(self, tool_name: str, args: dict) -> dict:
        normalized_tool_name = str(tool_name or "").strip()
        try:
            if normalized_tool_name == "project_host_terminal_start":
                from services.connectors.project_host_terminal_service import start_or_attach_project_host_terminal

                result = await start_or_attach_project_host_terminal(
                    project_id=self._project_id,
                    username=self._username,
                    chat_session_id=self._chat_session_id,
                    workspace_path=self._host_workspace_path,
                    initial_command=str(args.get("initial_command") or "").strip(),
                )
                return {
                    "ok": True,
                    "source": "project_host_terminal",
                    "interactive": True,
                    "action_type": "enter_text",
                    **dict(result),
                }
            if normalized_tool_name == "project_host_terminal_input":
                from services.connectors.project_host_terminal_service import (
                    get_project_host_terminal_session,
                    write_project_host_terminal_input,
                )

                session = get_project_host_terminal_session(
                    project_id=self._project_id,
                    username=self._username,
                    chat_session_id=self._chat_session_id,
                )
                if session is None:
                    return {"ok": False, "error": "terminal session is not running"}
                result = await write_project_host_terminal_input(
                    session.session_id,
                    str(args.get("content") or ""),
                )
                return {
                    "source": "project_host_terminal",
                    "session_id": session.session_id,
                    "workspace_path": session.workspace_path,
                    **dict(result),
                }
            if normalized_tool_name == "project_host_terminal_read":
                from services.connectors.project_host_terminal_service import read_project_host_terminal_output

                return {
                    "source": "project_host_terminal",
                    **read_project_host_terminal_output(
                        project_id=self._project_id,
                        username=self._username,
                        chat_session_id=self._chat_session_id,
                        max_chars=int(args.get("max_chars", 12000) or 12000),
                    ),
                }
            if normalized_tool_name == "project_host_terminal_stop":
                from services.connectors.project_host_terminal_service import (
                    get_project_host_terminal_session,
                    stop_project_host_terminal,
                )

                session = get_project_host_terminal_session(
                    project_id=self._project_id,
                    username=self._username,
                    chat_session_id=self._chat_session_id,
                )
                if session is None:
                    return {"ok": False, "error": "terminal session is not running"}
                result = await stop_project_host_terminal(session.session_id)
                return {
                    "source": "project_host_terminal",
                    "session_id": session.session_id,
                    "workspace_path": session.workspace_path,
                    **dict(result),
                }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "source": "project_host_terminal"}
        return {"ok": False, "error": f"Unsupported project host terminal tool: {normalized_tool_name}"}

    async def _maybe_execute_cli_auth_operation_task(
        self,
        *,
        command: str,
        timeout_sec: int,
        agent_runtime_context: dict[str, str] | None = None,
    ) -> dict | None:
        operation = _normalize_cli_auth_operation_command(command)
        normalized_command = str(operation.get("command") or "").strip()
        plugin_id = str(operation.get("plugin_id") or "").strip()
        if not normalized_command or not plugin_id:
            return None
        from services.operation_wait_task_service import create_cli_plugin_auth_operation_task
        from starlette.concurrency import run_in_threadpool

        task = await run_in_threadpool(
            create_cli_plugin_auth_operation_task,
            plugin_id,
            username=self._username,
            login_command=normalized_command,
            metadata={
                "source": "project_chat",
                "project_id": self._project_id,
                "chat_session_id": self._chat_session_id,
                "employee_id": self._employee_id,
                "agent_runtime_v2": dict(agent_runtime_context or {}),
            },
            timeout_sec=max(15, min(int(timeout_sec or 120), 600)),
            wait_for_initial_user_action_sec=1.5,
        )
        execution = dict(task.get("execution") or {})
        authorization_url = str(execution.get("authorization_url") or "").strip()
        interaction_schema = (
            execution.get("interaction_schema")
            if isinstance(execution.get("interaction_schema"), dict)
            else None
        )
        action_type = str(execution.get("action_type") or "").strip().lower()
        if not action_type:
            action_type = "open_url" if authorization_url else "interaction_form" if interaction_schema else "none"
        status = str(task.get("status") or "").strip().lower()
        waiting_user_action = status == "waiting_user_action" and bool(
            authorization_url or interaction_schema
        )
        execution_ok = bool(task.get("execution_ok", task.get("ok")))
        return {
            "ok": execution_ok,
            "execution_ok": execution_ok,
            "command": normalized_command,
            "source": "operation_wait_task",
            "operation_kind": str(task.get("operation_kind") or "auth_login").strip(),
            "operation_label": str(task.get("operation_label") or "网页登录授权").strip(),
            "interactive": True,
            "requires_user_action": waiting_user_action,
            "waiting_user_action": waiting_user_action,
            "action_type": action_type if waiting_user_action else "none",
            "authorization_url": authorization_url,
            "interaction_schema": interaction_schema,
            "status": status or "queued",
            "status_label": str(task.get("status_label") or "").strip(),
            "next_step": str(task.get("status_reason") or execution.get("next_step") or "").strip(),
            "task_id": str(task.get("task_id") or "").strip(),
            "operation_task": task,
            "login_task": task,
            "stdout": str(task.get("stdout") or execution.get("stdout") or "").strip(),
            "stderr": str(task.get("stderr") or execution.get("stderr") or "").strip(),
            "exit_code": task.get("exit_code"),
            "timed_out": status == "timeout",
            "workspace_path": self._host_workspace_path,
        }

    def _resolve_tool_timeout(self, tool_name: str, args: dict, default_timeout: int | None) -> int | None:
        try:
            resolved_default = int(self._timeout if default_timeout is None else default_timeout)
        except (TypeError, ValueError):
            resolved_default = int(self._timeout or 0)
        safe_timeout = max(0, min(resolved_default, 600))
        normalized_tool_name = str(tool_name or "").strip()
        if normalized_tool_name != "project_host_run_command":
            return safe_timeout if safe_timeout > 0 else None
        try:
            requested_timeout = int(args.get("timeout_sec", 0) or 0)
        except (TypeError, ValueError):
            requested_timeout = 0
        if requested_timeout <= 0:
            return safe_timeout if safe_timeout > 0 else None
        if safe_timeout <= 0:
            return min(requested_timeout + 5, 600)
        return max(safe_timeout, min(requested_timeout + 5, 600))
