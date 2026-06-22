"""Execute collected tool calls and persist observations."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from services.agent_runtime.builtin_tools.definitions import is_local_builtin_tool
from services.agent_runtime.core.event_log import RuntimeEventLog
from services.agent_runtime.contract import validate_permission_option
from services.agent_runtime.shared.tool_calls import CollectedToolCall
from services.agent_runtime.shared.tool_registry import RuntimeToolEntry
from services.agent_runtime.shared.tool_results import ToolObservation, ToolResultNormalizer
from services.agent_runtime.v2.permission_policy import PermissionPolicy
from services.agent_runtime.v2.permission_store import PermissionDecision


@dataclass
class ToolExecutionRecord:
    tool_call: CollectedToolCall
    raw_result: dict[str, Any]
    observation: ToolObservation
    permission_decision: PermissionDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_call": self.tool_call.to_dict(),
            "raw_result": dict(self.raw_result),
            "observation": self.observation.to_dict(),
            "permission_decision": (
                self.permission_decision.to_dict()
                if self.permission_decision is not None
                else None
            ),
        }


class ToolExecutionRunner:
    def __init__(
        self,
        tool_executor: Any,
        *,
        event_log: RuntimeEventLog | None = None,
        normalizer: ToolResultNormalizer | None = None,
        permission_policy: PermissionPolicy | None = None,
        project_id: str = "",
        username: str = "",
        chat_session_id: str = "",
        workspace_trusted: bool = True,
        tool_entries: list[RuntimeToolEntry | dict[str, Any]] | None = None,
    ):
        self._tool_executor = tool_executor
        self._event_log = event_log or RuntimeEventLog()
        self._normalizer = normalizer or ToolResultNormalizer()
        self._permission_policy = permission_policy or PermissionPolicy()
        self._project_id = str(project_id or "").strip()
        self._username = str(username or "").strip()
        self._chat_session_id = str(chat_session_id or "").strip()
        self._workspace_trusted = bool(workspace_trusted)
        self._tool_entries = self._normalize_tool_entries(tool_entries)

    async def execute(
        self,
        *,
        run_id: str,
        tool_calls: list[CollectedToolCall],
    ) -> list[ToolExecutionRecord]:
        records: list[ToolExecutionRecord | None] = []
        allowed_tool_calls: list[CollectedToolCall] = []
        allowed_record_indexes: list[int] = []
        for item in tool_calls:
            self._event_log.append(
                run_id,
                "tool_call_started",
                item.to_dict(),
            )
            args = self._parse_arguments(item.arguments)
            executable_item = item
            if args is not None and item.tool_name == "project_host_run_command":
                args = dict(args)
                args.setdefault("_agent_runtime_run_id", str(run_id or "").strip())
                args.setdefault("_agent_runtime_call_id", item.call_id)
                args.setdefault("_agent_runtime_tool_name", item.tool_name)
                executable_item = self._tool_call_with_arguments(item, args)
            tool_entry = self._tool_entry_for(item.tool_name)
            decision = self._permission_policy.evaluate(
                run_id=run_id,
                call_id=item.call_id,
                tool_name=item.tool_name,
                args=args,
                project_id=self._project_id,
                username=self._username,
                chat_session_id=self._chat_session_id,
                workspace_trusted=self._workspace_trusted,
                tool_entry=tool_entry,
            )
            permission_request = (
                self._permission_request_payload(
                    decision=decision,
                    tool_call=executable_item,
                    args=args or {},
                    args_parse_status="ok" if args is not None else "invalid_json",
                    tool_entry=tool_entry,
                )
                if decision.behavior == "ask"
                else {}
            )
            if permission_request:
                self._event_log.append(
                    run_id,
                    "approval_required",
                    permission_request,
                    session_id=self._chat_session_id,
                )
            self._event_log.append(
                run_id,
                "permission_decision",
                {
                    "tool_call": executable_item.to_dict(),
                    "decision": decision.to_dict(),
                    "canonical_decision": decision.canonical_decision(),
                    "permission_request": permission_request,
                    "args": dict(args or {}),
                    "args_parse_status": "ok" if args is not None else "invalid_json",
                    "tool_entry": tool_entry,
                },
                session_id=self._chat_session_id,
            )
            if not decision.allowed:
                records.append(
                    self._build_blocked_record(
                        run_id=run_id,
                        tool_call=executable_item,
                        decision=decision,
                        args=args or {},
                        args_parse_status="ok" if args is not None else "invalid_json",
                        tool_entry=tool_entry,
                        permission_request=permission_request,
                    )
                )
                continue
            allowed_record_indexes.append(len(records))
            records.append(None)
            allowed_tool_calls.append(executable_item)

        if allowed_tool_calls:
            server_tool_calls: list[CollectedToolCall] = []
            server_record_indexes: list[int] = []
            for tool_call, record_index in zip(allowed_tool_calls, allowed_record_indexes):
                tool_entry = self._tool_entry_for(tool_call.tool_name)
                if self._should_delegate_to_desktop(tool_call.tool_name, tool_entry):
                    records[record_index] = self._build_desktop_client_wait_record(
                        run_id=run_id,
                        tool_call=tool_call,
                        args=self._parse_arguments(tool_call.arguments) or {},
                        tool_entry=tool_entry,
                    )
                    continue
                server_tool_calls.append(tool_call)
                server_record_indexes.append(record_index)
            if server_tool_calls:
                openai_tool_calls = [item.to_openai_tool_call() for item in server_tool_calls]
                results = await self._tool_executor.execute_parallel(openai_tool_calls)
                for tool_call, raw_result, record_index in zip(
                    server_tool_calls,
                    results,
                    server_record_indexes,
                ):
                    records[record_index] = self._build_executed_record(
                        run_id=run_id,
                        tool_call=tool_call,
                        raw_result=raw_result,
                    )
        return [item for item in records if item is not None]

    def _normalize_tool_entries(
        self,
        entries: list[RuntimeToolEntry | dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for entry in entries or []:
            if isinstance(entry, RuntimeToolEntry):
                payload = entry.summary()
            elif isinstance(entry, dict):
                payload = dict(entry)
            else:
                continue
            tool_name = str(payload.get("tool_name") or payload.get("name") or "").strip()
            if not tool_name:
                continue
            normalized[tool_name] = payload
        return normalized

    def _tool_entry_for(self, tool_name: str) -> dict[str, Any]:
        return dict(self._tool_entries.get(str(tool_name or "").strip(), {}))

    def _tool_call_with_arguments(
        self,
        item: CollectedToolCall,
        args: dict[str, Any],
    ) -> CollectedToolCall:
        arguments = json.dumps(args, ensure_ascii=False)
        raw = dict(item.raw or {})
        raw_function = raw.get("function") if isinstance(raw.get("function"), dict) else {}
        raw["id"] = item.call_id
        raw["type"] = "function"
        raw["function"] = {
            **dict(raw_function),
            "name": item.tool_name,
            "arguments": arguments,
        }
        return CollectedToolCall(
            call_id=item.call_id,
            tool_name=item.tool_name,
            arguments=arguments,
            raw=raw,
        )

    def _build_executed_record(
        self,
        *,
        run_id: str,
        tool_call: CollectedToolCall,
        raw_result: Any,
    ) -> ToolExecutionRecord:
        if isinstance(raw_result, Exception):
            payload: dict[str, Any] = {"error": str(raw_result)}
        elif isinstance(raw_result, dict):
            payload = dict(raw_result)
        else:
            payload = {"result": raw_result}
        observation = self._normalizer.normalize(
            run_id=run_id,
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            raw_result=payload,
        )
        self._event_log.append(
            run_id,
            "tool_observation_created",
            observation.to_dict(),
            session_id=self._chat_session_id,
        )
        return ToolExecutionRecord(
            tool_call=tool_call,
            raw_result=payload,
            observation=observation,
        )

    def _build_blocked_record(
        self,
        *,
        run_id: str,
        tool_call: CollectedToolCall,
        decision: PermissionDecision,
        args: dict[str, Any],
        args_parse_status: str,
        tool_entry: dict[str, Any] | None = None,
        permission_request: dict[str, Any] | None = None,
    ) -> ToolExecutionRecord:
        payload: dict[str, Any] = {
            "status": "blocked",
            "ok": False,
            "error": "tool call blocked by permission policy",
            "summary": self._blocked_summary(decision),
            "permission_decision": decision.to_dict(),
            "permission_request": dict(permission_request or {}),
            "tool_args": dict(args),
            "args_parse_status": args_parse_status,
            "tool_entry": dict(tool_entry or {}),
        }
        observation = self._normalizer.normalize(
            run_id=run_id,
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            raw_result=payload,
        )
        self._event_log.append(
            run_id,
            "tool_observation_created",
            observation.to_dict(),
            session_id=self._chat_session_id,
        )
        return ToolExecutionRecord(
            tool_call=tool_call,
            raw_result=payload,
            observation=observation,
            permission_decision=decision,
        )

    def _should_delegate_to_desktop(
        self,
        tool_name: str,
        tool_entry: dict[str, Any] | None = None,
    ) -> bool:
        entry = dict(tool_entry or {})
        backend = str(entry.get("execution_backend") or "").strip().lower()
        if backend in {"desktop_client", "tauri", "native_desktop"}:
            return True
        return is_local_builtin_tool(tool_name)

    def _build_desktop_client_wait_record(
        self,
        *,
        run_id: str,
        tool_call: CollectedToolCall,
        args: dict[str, Any],
        tool_entry: dict[str, Any] | None = None,
    ) -> ToolExecutionRecord:
        task_id = self._desktop_client_task_id(
            run_id=run_id,
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
        )
        payload: dict[str, Any] = {
            "ok": True,
            "source": "desktop_client_tool",
            "status": "waiting_user_action",
            "operation_kind": "desktop_client_tool",
            "operation_label": f"桌面本地工具：{tool_call.tool_name}",
            "task_id": task_id,
            "run_id": run_id,
            "call_id": tool_call.call_id,
            "tool_name": tool_call.tool_name,
            "tool_args": dict(args),
            "tool_entry": dict(tool_entry or {}),
            "summary": "等待桌面客户端在用户本机执行工具。",
            "next_step": "桌面端将调用 Tauri/Rust 本地运行时执行该工具，并把结果回传服务端继续对话。",
        }
        observation = self._normalizer.normalize(
            run_id=run_id,
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            raw_result=payload,
        )
        self._event_log.append(
            run_id,
            "tool_observation_created",
            observation.to_dict(),
            session_id=self._chat_session_id,
        )
        return ToolExecutionRecord(
            tool_call=tool_call,
            raw_result=payload,
            observation=observation,
        )

    def _desktop_client_task_id(
        self,
        *,
        run_id: str,
        call_id: str,
        tool_name: str,
    ) -> str:
        seed = f"{run_id}:{call_id}:{tool_name}:{uuid4().hex}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return f"desktop-tool-{digest}"

    def _parse_arguments(self, value: str) -> dict[str, Any] | None:
        text = str(value or "").strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else {}

    def _permission_request_payload(
        self,
        *,
        decision: PermissionDecision,
        tool_call: CollectedToolCall,
        args: dict[str, Any],
        args_parse_status: str,
        tool_entry: dict[str, Any],
    ) -> dict[str, Any]:
        options = [
            validate_permission_option(
                {"decision": "approve_once", "grant_scope": "once", "label": "允许一次"}
            ),
            validate_permission_option(
                {
                    "decision": "approve_session",
                    "grant_scope": "session",
                    "label": "允许本会话",
                }
            ),
            validate_permission_option({"decision": "deny", "label": "拒绝"}),
        ]
        scope = str(tool_entry.get("permission_scope") or "workspace").strip() or "workspace"
        action = self._permission_action_for(tool_call.tool_name)
        # 中文注释：approval_required 是给 Adapter 展示的审批请求，不代表用户已经批准。
        return {
            "request_id": decision.request_id,
            "title": "允许执行工具？",
            "risk": decision.risk_level,
            "action": action,
            "scope": scope,
            "reason": decision.reason,
            "tool_call": tool_call.to_dict(),
            "args": dict(args),
            "args_parse_status": args_parse_status,
            "tool_entry": dict(tool_entry),
            "options": options,
        }

    def _permission_action_for(self, tool_name: str) -> str:
        if str(tool_name or "").strip() in {
            "project_host_run_command",
            "project_host_terminal_start",
            "project_host_terminal_input",
            "project_host_terminal_stop",
        }:
            return "command.run"
        return "tool.execute"

    def _blocked_summary(self, decision: PermissionDecision) -> str:
        if decision.behavior == "ask":
            return "Permission required before executing this tool call."
        if decision.behavior == "deny":
            return "Tool call denied by permission policy."
        return "Tool call blocked by permission policy."


__all__ = ["ToolExecutionRecord", "ToolExecutionRunner"]
