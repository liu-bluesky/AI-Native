from __future__ import annotations
import asyncio
import json
import re
from typing import Any
from core.config import get_settings


_LARK_AUTH_LOGIN_COMMAND_PATTERN = re.compile(
    r"(^|[\s;&|])(lark-cli)\s+auth\s+login(?:[\s;&|]|$)",
    re.IGNORECASE,
)
_LARK_AUTH_LOGIN_ALIAS_PATTERN = re.compile(
    r"^(?:lark-cli\s+)?(?:auth\s+)?(?:login|登录)(?:\s+([\s\S]*))?$",
    re.IGNORECASE,
)
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


def _normalize_lark_auth_login_command(command: str) -> str:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return ""
    if _LARK_AUTH_LOGIN_COMMAND_PATTERN.search(normalized_command):
        return normalized_command
    match = _LARK_AUTH_LOGIN_ALIAS_PATTERN.match(normalized_command)
    if not match:
        return ""
    suffix = str(match.group(1) or "").strip()
    if not suffix or suffix.lower() in {"recommend", "推荐"}:
        return "lark-cli auth login --recommend"
    if suffix.startswith("--"):
        return f"lark-cli auth login {suffix}"
    if _LARK_AUTH_DOMAIN_ALIAS_PATTERN.fullmatch(suffix):
        compact_suffix = re.sub(r"\s+", "", suffix)
        return f"lark-cli auth login --domain {compact_suffix}"
    return "lark-cli auth login --recommend"


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
        from services.global_assistant_service import (
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
        if str(tool_name or "").strip().startswith("local_connector_"):
            return await self._execute_local_connector_tool(tool_name, args)
        from services.dynamic_mcp_runtime import invoke_project_tool_runtime
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
        from services.local_connector_service import (
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
        command = str(args.get("command") or "").strip()
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

        from services.project_host_command_service import run_project_host_command
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(
            run_project_host_command,
            workspace_path=self._host_workspace_path,
            command=command,
            owner_username=self._username,
            cwd=str(args.get("cwd") or "").strip(),
            timeout_sec=int(args.get("timeout_sec", 20)),
            max_output_chars=int(args.get("max_output_chars", 12000) or 12000),
        )

    async def _maybe_execute_cli_auth_operation_task(
        self,
        *,
        command: str,
        timeout_sec: int,
        agent_runtime_context: dict[str, str] | None = None,
    ) -> dict | None:
        normalized_command = _normalize_lark_auth_login_command(command)
        if not normalized_command:
            return None
        from services.operation_wait_task_service import create_cli_plugin_auth_operation_task
        from starlette.concurrency import run_in_threadpool

        task = await run_in_threadpool(
            create_cli_plugin_auth_operation_task,
            "feishu-cli",
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
        )
        execution = dict(task.get("execution") or {})
        authorization_url = str(execution.get("authorization_url") or "").strip()
        status = str(task.get("status") or "").strip().lower()
        waiting_user_action = status == "waiting_user_action"
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
            "action_type": "open_url" if waiting_user_action else "none",
            "authorization_url": authorization_url,
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
