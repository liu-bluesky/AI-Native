"""Execute collected tool calls and persist observations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from services.agent_runtime.core.event_log import RuntimeEventLog
from services.agent_runtime.shared.tool_calls import CollectedToolCall
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
    ):
        self._tool_executor = tool_executor
        self._event_log = event_log or RuntimeEventLog()
        self._normalizer = normalizer or ToolResultNormalizer()
        self._permission_policy = permission_policy or PermissionPolicy()
        self._project_id = str(project_id or "").strip()
        self._username = str(username or "").strip()
        self._chat_session_id = str(chat_session_id or "").strip()
        self._workspace_trusted = bool(workspace_trusted)

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
            decision = self._permission_policy.evaluate(
                run_id=run_id,
                call_id=item.call_id,
                tool_name=item.tool_name,
                args=args,
                project_id=self._project_id,
                username=self._username,
                chat_session_id=self._chat_session_id,
                workspace_trusted=self._workspace_trusted,
            )
            self._event_log.append(
                run_id,
                "permission_decision",
                {
                    "tool_call": executable_item.to_dict(),
                    "decision": decision.to_dict(),
                    "args": dict(args or {}),
                    "args_parse_status": "ok" if args is not None else "invalid_json",
                },
            )
            if not decision.allowed:
                records.append(
                    self._build_blocked_record(
                        run_id=run_id,
                        tool_call=executable_item,
                        decision=decision,
                        args=args or {},
                        args_parse_status="ok" if args is not None else "invalid_json",
                    )
                )
                continue
            allowed_record_indexes.append(len(records))
            records.append(None)
            allowed_tool_calls.append(executable_item)

        if allowed_tool_calls:
            openai_tool_calls = [item.to_openai_tool_call() for item in allowed_tool_calls]
            results = await self._tool_executor.execute_parallel(openai_tool_calls)
            for tool_call, raw_result, record_index in zip(
                allowed_tool_calls,
                results,
                allowed_record_indexes,
            ):
                records[record_index] = self._build_executed_record(
                    run_id=run_id,
                    tool_call=tool_call,
                    raw_result=raw_result,
                )
        return [item for item in records if item is not None]

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
    ) -> ToolExecutionRecord:
        payload: dict[str, Any] = {
            "status": "blocked",
            "ok": False,
            "error": "tool call blocked by permission policy",
            "summary": self._blocked_summary(decision),
            "permission_decision": decision.to_dict(),
            "tool_args": dict(args),
            "args_parse_status": args_parse_status,
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
        )
        return ToolExecutionRecord(
            tool_call=tool_call,
            raw_result=payload,
            observation=observation,
            permission_decision=decision,
        )

    def _parse_arguments(self, value: str) -> dict[str, Any] | None:
        text = str(value or "").strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else {}

    def _blocked_summary(self, decision: PermissionDecision) -> str:
        if decision.behavior == "ask":
            return "Permission required before executing this tool call."
        if decision.behavior == "deny":
            return "Tool call denied by permission policy."
        return "Tool call blocked by permission policy."


__all__ = ["ToolExecutionRecord", "ToolExecutionRunner"]
