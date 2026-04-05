from __future__ import annotations
import asyncio
import json
from typing import Any
from core.config import get_settings

class ToolExecutor:
    def __init__(
        self,
        project_id: str,
        employee_id: str,
        *,
        username: str = "",
        chat_session_id: str = "",
        timeout_sec: int | None = None,
        max_retries: int = 0,
        allowed_tool_names: list[str] | None = None,
        local_connector: Any | None = None,
        local_connector_workspace_path: str = "",
        local_connector_sandbox_mode: str = "workspace-write",
    ):
        self._project_id = project_id
        self._employee_id = employee_id
        self._username = str(username or "").strip()
        self._chat_session_id = str(chat_session_id or "").strip()
        settings = get_settings()
        base_timeout = int(settings.tool_timeout)
        if timeout_sec is not None:
            try:
                base_timeout = int(timeout_sec)
            except (TypeError, ValueError):
                pass
        self._timeout = max(1, min(base_timeout, 600))
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
        self._local_connector_sandbox_mode = (
            str(local_connector_sandbox_mode or "workspace-write").strip()
            or "workspace-write"
        )

    async def execute_parallel(self, tool_calls: list[dict], timeout: int | None = None) -> list[dict]:
        timeout = timeout or self._timeout
        tasks = [self._execute_with_timeout(tc, timeout) for tc in tool_calls]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_with_timeout(self, tool_call: dict, timeout: int) -> dict:
        tool_name = tool_call["function"]["name"]
        args_str = tool_call["function"]["arguments"]
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON arguments: {args_str}"}

        if self._allowed_tool_names and str(tool_name or "").strip() not in self._allowed_tool_names:
            return {"error": f"Tool {tool_name} is not allowed in current chat settings"}

        attempt = 0
        while True:
            try:
                result = await asyncio.wait_for(
                    self._execute_tool(tool_name, args),
                    timeout=timeout
                )
                return result
            except asyncio.TimeoutError:
                if attempt >= self._max_retries:
                    return {"error": f"Tool {tool_name} execution timeout"}
            except Exception as e:
                if attempt >= self._max_retries:
                    return {"error": f"Tool {tool_name} failed: {str(e)}"}
            attempt += 1

    async def _execute_tool(self, tool_name: str, args: dict) -> dict:
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
            run_connector_command,
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

        if normalized_tool_name == "local_connector_run_command":
            return await run_connector_command(
                self._local_connector,
                workspace_path=self._local_connector_workspace_path,
                command=str(args.get("command") or "").strip(),
                cwd=str(args.get("cwd") or "").strip(),
                timeout_sec=int(args.get("timeout_sec", 20) or 20),
                max_output_chars=int(args.get("max_output_chars", 12000) or 12000),
                sandbox_mode=self._local_connector_sandbox_mode,
            )

        return await write_connector_file(
            self._local_connector,
            workspace_path=self._local_connector_workspace_path,
            path=str(args.get("path") or "").strip(),
            content=str(args.get("content") or ""),
            sandbox_mode=self._local_connector_sandbox_mode,
        )
