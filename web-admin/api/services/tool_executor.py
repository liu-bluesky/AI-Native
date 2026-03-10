from __future__ import annotations
import asyncio
import json
from core.config import get_settings

class ToolExecutor:
    def __init__(
        self,
        project_id: str,
        employee_id: str,
        *,
        timeout_sec: int | None = None,
        max_retries: int = 0,
        allowed_tool_names: list[str] | None = None,
    ):
        self._project_id = project_id
        self._employee_id = employee_id
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
        from services.dynamic_mcp_runtime import invoke_project_tool_runtime
        from starlette.concurrency import run_in_threadpool
        result = await run_in_threadpool(
            invoke_project_tool_runtime,
            project_id=self._project_id,
            tool_name=tool_name,
            employee_id=self._employee_id,
            args=args,
            args_json=json.dumps(args),
            timeout_sec=self._timeout
        )
        return result
