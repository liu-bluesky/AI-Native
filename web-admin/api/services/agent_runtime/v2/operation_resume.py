"""Resume blocked agent_runtime_v2 operations on the original TaskRun."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime.core.event_log import RuntimeEventLog
from services.agent_runtime.v2.llm_step import LLMStep
from services.agent_runtime.v2.permission_policy import PermissionPolicy
from services.agent_runtime.v2.query_engine import QueryEngine, QueryEngineResult
from services.agent_runtime.core.state_store import TaskRunStore
from services.agent_runtime.shared.tool_calls import CollectedToolCall
from services.agent_runtime.shared.tool_execution_runner import (
    ToolExecutionRecord,
    ToolExecutionRunner,
)
from services.agent_runtime.core.transcript_store import TranscriptStore


@dataclass
class ResumeOperationResult:
    run_id: str
    status: str
    resumed: bool
    reason: str = ""
    records: list[ToolExecutionRecord] = field(default_factory=list)
    continuation: QueryEngineResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "resumed": self.resumed,
            "reason": self.reason,
            "records": [item.to_dict() for item in self.records],
            "observations": [item.observation.to_dict() for item in self.records],
            "continuation": (
                self.continuation.to_dict()
                if self.continuation is not None
                else None
            ),
        }


class OperationResumeCoordinator:
    def __init__(
        self,
        *,
        state_store: TaskRunStore | None = None,
        transcript_store: TranscriptStore | None = None,
        event_log: RuntimeEventLog | None = None,
        permission_policy: PermissionPolicy | None = None,
    ):
        self._state_store = state_store or TaskRunStore()
        self._transcript_store = transcript_store or TranscriptStore()
        self._event_log = event_log or RuntimeEventLog()
        self._permission_policy = permission_policy or PermissionPolicy()

    async def resume_permission_action(
        self,
        *,
        run_id: str,
        call_id: str,
        tool_name: str,
        tool_executor: Any,
        project_id: str = "",
        username: str = "",
        chat_session_id: str = "",
        workspace_trusted: bool = True,
        llm_service: Any | None = None,
        tools: list[dict[str, Any]] | None = None,
        provider_id: str = "",
        model_name: str = "",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        max_model_steps: int = 3,
    ) -> ResumeOperationResult:
        task_run = self._state_store.load(run_id)
        if task_run is None:
            return ResumeOperationResult(
                run_id=str(run_id or "").strip(),
                status="not_found",
                resumed=False,
                reason="task_run_not_found",
            )
        if str(task_run.status or "").strip() != "waiting_user":
            return ResumeOperationResult(
                run_id=task_run.run_id,
                status=task_run.status,
                resumed=False,
                reason="task_run_not_waiting_user",
            )
        pending_call = self.find_permission_request(
            run_id=task_run.run_id,
            call_id=call_id,
            tool_name=tool_name,
        )
        if pending_call is None:
            return ResumeOperationResult(
                run_id=task_run.run_id,
                status=task_run.status,
                resumed=False,
                reason="permission_request_not_found",
            )

        task_run = self._state_store.append_event(
            task_run,
            "operation_resume_started",
            {
                "resume_strategy": "permission_action_tool_call",
                "call_id": pending_call.call_id,
                "tool_name": pending_call.tool_name,
            },
            status="running",
        )
        self._event_log.append(
            task_run.run_id,
            "operation_resume_started",
            {
                "resume_strategy": "permission_action_tool_call",
                "call_id": pending_call.call_id,
                "tool_name": pending_call.tool_name,
            },
        )
        runner = ToolExecutionRunner(
            tool_executor,
            event_log=self._event_log,
            permission_policy=self._permission_policy,
            project_id=project_id or task_run.project_id,
            username=username or task_run.username,
            chat_session_id=chat_session_id or task_run.chat_session_id,
            workspace_trusted=workspace_trusted,
        )
        records = await runner.execute(
            run_id=task_run.run_id,
            tool_calls=[pending_call],
        )
        for record in records:
            self._transcript_store.append(
                task_run.run_id,
                "operation_resume_tool_result",
                record.to_dict(),
            )
        final_status = "running"
        if any(item.observation.status == "blocked" for item in records):
            final_status = "waiting_user"
        continuation: QueryEngineResult | None = None
        if final_status == "running" and llm_service is not None:
            continuation_messages = self._build_continuation_messages(
                run_id=task_run.run_id,
                resumed_call=pending_call,
                records=records,
            )
            if continuation_messages:
                self._transcript_store.append(
                    task_run.run_id,
                    "operation_resume_continuation_input",
                    {
                        "message_count": len(continuation_messages),
                        "call_id": pending_call.call_id,
                        "tool_name": pending_call.tool_name,
                    },
                )
                self._event_log.append(
                    task_run.run_id,
                    "operation_resume_continuation_started",
                    {
                        "call_id": pending_call.call_id,
                        "tool_name": pending_call.tool_name,
                    },
                )
                continuation = await QueryEngine(
                    llm_step=LLMStep(llm_service),
                    tool_runner=ToolExecutionRunner(
                        tool_executor,
                        event_log=self._event_log,
                        permission_policy=self._permission_policy,
                        project_id=project_id or task_run.project_id,
                        username=username or task_run.username,
                        chat_session_id=chat_session_id or task_run.chat_session_id,
                        workspace_trusted=workspace_trusted,
                    ),
                    state_store=self._state_store,
                    transcript_store=self._transcript_store,
                    event_log=self._event_log,
                    max_model_steps=max_model_steps,
                ).run(
                    task_run,
                    messages=continuation_messages,
                    tools=tools or [],
                    provider_id=provider_id or str(task_run.metadata.get("provider_id") or ""),
                    model_name=model_name or str(task_run.metadata.get("model_name") or ""),
                    temperature=temperature,
                    max_tokens=max_tokens,
                    task_tree_verified=True,
                    goal_covered=True,
                )
                final_status = continuation.task_run.status
                self._event_log.append(
                    task_run.run_id,
                    "operation_resume_continuation_completed",
                    {
                        "status": final_status,
                        "model_steps": continuation.model_steps,
                    },
                )
        task_run = self._state_store.append_event(
            task_run,
            "operation_resume_completed",
            {
                "resume_strategy": "permission_action_tool_call",
                "call_id": pending_call.call_id,
                "tool_name": pending_call.tool_name,
                "record_count": len(records),
                "continued_query_engine": continuation is not None,
            },
            status=final_status,
        )
        self._event_log.append(
            task_run.run_id,
            "operation_resume_completed",
            {
                "status": final_status,
                "call_id": pending_call.call_id,
                "tool_name": pending_call.tool_name,
                "record_count": len(records),
                "continued_query_engine": continuation is not None,
            },
        )
        return ResumeOperationResult(
            run_id=task_run.run_id,
            status=task_run.status,
            resumed=True,
            records=records,
            continuation=continuation,
        )

    async def resume_background_operation(
        self,
        *,
        run_id: str,
        tool_executor: Any,
        operation_task: dict[str, Any],
        project_id: str = "",
        username: str = "",
        chat_session_id: str = "",
        workspace_trusted: bool = True,
        llm_service: Any | None = None,
        tools: list[dict[str, Any]] | None = None,
        provider_id: str = "",
        model_name: str = "",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        max_model_steps: int = 3,
    ) -> ResumeOperationResult:
        task_run = self._state_store.load(run_id)
        if task_run is None:
            return ResumeOperationResult(
                run_id=str(run_id or "").strip(),
                status="not_found",
                resumed=False,
                reason="task_run_not_found",
            )
        if str(task_run.status or "").strip() != "waiting_user":
            return ResumeOperationResult(
                run_id=task_run.run_id,
                status=task_run.status,
                resumed=False,
                reason="task_run_not_waiting_user",
            )
        pending_record = self.find_background_operation_request(
            run_id=task_run.run_id,
            task_id=str(operation_task.get("task_id") or "").strip(),
        )
        if pending_record is None:
            return ResumeOperationResult(
                run_id=task_run.run_id,
                status=task_run.status,
                resumed=False,
                reason="background_operation_request_not_found",
            )
        task_run = self._state_store.append_event(
            task_run,
            "background_operation_resume_started",
            {
                "task_id": str(operation_task.get("task_id") or "").strip(),
                "call_id": pending_record.tool_call.call_id,
                "tool_name": pending_record.tool_call.tool_name,
            },
            status="running",
        )
        self._event_log.append(
            task_run.run_id,
            "background_operation_resume_started",
            {
                "task_id": str(operation_task.get("task_id") or "").strip(),
                "call_id": pending_record.tool_call.call_id,
                "tool_name": pending_record.tool_call.tool_name,
            },
        )
        completed_record = self._completed_background_record(
            run_id=task_run.run_id,
            pending_record=pending_record,
            operation_task=operation_task,
        )
        self._transcript_store.append(
            task_run.run_id,
            "background_operation_tool_result",
            completed_record.to_dict(),
        )
        continuation: QueryEngineResult | None = None
        final_status = "running"
        if llm_service is not None:
            continuation_messages = self._build_continuation_messages(
                run_id=task_run.run_id,
                resumed_call=completed_record.tool_call,
                records=[completed_record],
            )
            if continuation_messages:
                self._event_log.append(
                    task_run.run_id,
                    "background_operation_continuation_started",
                    {
                        "task_id": str(operation_task.get("task_id") or "").strip(),
                        "call_id": completed_record.tool_call.call_id,
                    },
                )
                continuation = await QueryEngine(
                    llm_step=LLMStep(llm_service),
                    tool_runner=ToolExecutionRunner(
                        tool_executor,
                        event_log=self._event_log,
                        permission_policy=self._permission_policy,
                        project_id=project_id or task_run.project_id,
                        username=username or task_run.username,
                        chat_session_id=chat_session_id or task_run.chat_session_id,
                        workspace_trusted=workspace_trusted,
                    ),
                    state_store=self._state_store,
                    transcript_store=self._transcript_store,
                    event_log=self._event_log,
                    max_model_steps=max_model_steps,
                ).run(
                    task_run,
                    messages=continuation_messages,
                    tools=tools or [],
                    provider_id=provider_id or str(task_run.metadata.get("provider_id") or ""),
                    model_name=model_name or str(task_run.metadata.get("model_name") or ""),
                    temperature=temperature,
                    max_tokens=max_tokens,
                    task_tree_verified=True,
                    goal_covered=True,
                )
                final_status = continuation.task_run.status
                self._event_log.append(
                    task_run.run_id,
                    "background_operation_continuation_completed",
                    {
                        "status": final_status,
                        "model_steps": continuation.model_steps,
                    },
                )
        task_run = self._state_store.append_event(
            task_run,
            "background_operation_resume_completed",
            {
                "task_id": str(operation_task.get("task_id") or "").strip(),
                "call_id": completed_record.tool_call.call_id,
                "tool_name": completed_record.tool_call.tool_name,
                "continued_query_engine": continuation is not None,
            },
            status=final_status,
        )
        self._event_log.append(
            task_run.run_id,
            "background_operation_resume_completed",
            {
                "status": final_status,
                "task_id": str(operation_task.get("task_id") or "").strip(),
                "call_id": completed_record.tool_call.call_id,
                "tool_name": completed_record.tool_call.tool_name,
                "continued_query_engine": continuation is not None,
            },
        )
        return ResumeOperationResult(
            run_id=task_run.run_id,
            status=task_run.status,
            resumed=True,
            records=[completed_record],
            continuation=continuation,
        )

    def find_background_operation_request(
        self,
        *,
        run_id: str,
        task_id: str,
    ) -> ToolExecutionRecord | None:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return None
        for event in reversed(self._event_log.list_events(run_id)):
            if event.event_type != "tool_observation_created":
                continue
            payload = dict(event.payload or {})
            raw_result = payload.get("raw_result") if isinstance(payload.get("raw_result"), dict) else {}
            if str(raw_result.get("task_id") or "").strip() != normalized_task_id:
                continue
            if str(raw_result.get("source") or "").strip() not in {
                "operation_wait_task",
                "cli_plugin_login_task",
                "desktop_client_tool",
            }:
                continue
            return ToolExecutionRecord(
                tool_call=self._tool_call_from_event(
                    {
                        "arguments": self._background_operation_arguments(raw_result)
                    },
                    str(payload.get("call_id") or "").strip(),
                    str(payload.get("tool_name") or "project_host_run_command").strip(),
                ),
                raw_result=raw_result,
                observation=self._observation_from_payload(payload),
            )
        return None

    def find_permission_request(
        self,
        *,
        run_id: str,
        call_id: str,
        tool_name: str,
    ) -> CollectedToolCall | None:
        normalized_call_id = str(call_id or "").strip()
        normalized_tool_name = str(tool_name or "").strip()
        if not normalized_call_id or not normalized_tool_name:
            return None
        for event in reversed(self._event_log.list_events(run_id)):
            if event.event_type != "permission_decision":
                continue
            payload = dict(event.payload or {})
            decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
            tool_call = payload.get("tool_call") if isinstance(payload.get("tool_call"), dict) else {}
            if str(decision.get("behavior") or "").strip().lower() != "ask":
                continue
            if str(decision.get("call_id") or tool_call.get("call_id") or "").strip() != normalized_call_id:
                continue
            if str(decision.get("tool_name") or tool_call.get("tool_name") or "").strip() != normalized_tool_name:
                continue
            return self._tool_call_from_event(tool_call, normalized_call_id, normalized_tool_name)
        return None

    def _tool_call_from_event(
        self,
        payload: dict[str, Any],
        call_id: str,
        tool_name: str,
    ) -> CollectedToolCall:
        arguments = str(payload.get("arguments") or "").strip()
        if not arguments:
            arguments = "{}"
        try:
            json.loads(arguments)
        except json.JSONDecodeError:
            arguments = "{}"
        raw = dict(payload.get("raw") or {})
        if not raw:
            raw = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
        return CollectedToolCall(
            call_id=call_id,
            tool_name=tool_name,
            arguments=arguments,
            raw=raw,
        )

    def _observation_from_payload(self, payload: dict[str, Any]):
        from services.agent_runtime.shared.tool_results import ToolObservation

        return ToolObservation(
            observation_id=str(payload.get("observation_id") or "").strip(),
            run_id=str(payload.get("run_id") or "").strip(),
            call_id=str(payload.get("call_id") or "").strip(),
            tool_name=str(payload.get("tool_name") or "").strip(),
            status=str(payload.get("status") or "").strip(),
            summary=str(payload.get("summary") or "").strip(),
            raw_result=dict(payload.get("raw_result") or {}),
            created_at=str(payload.get("created_at") or "").strip(),
        )

    def _completed_background_record(
        self,
        *,
        run_id: str,
        pending_record: ToolExecutionRecord,
        operation_task: dict[str, Any],
    ) -> ToolExecutionRecord:
        source = str(pending_record.raw_result.get("source") or "operation_wait_task").strip()
        if source == "desktop_client_tool":
            return self._completed_desktop_client_tool_record(
                run_id=run_id,
                pending_record=pending_record,
                operation_task=operation_task,
            )
        raw_result = {
            "ok": bool(operation_task.get("ok", True)),
            "execution_ok": bool(operation_task.get("execution_ok", operation_task.get("ok", True))),
            "source": source,
            "command": str(pending_record.raw_result.get("command") or "").strip(),
            "operation_kind": str(operation_task.get("operation_kind") or "").strip(),
            "operation_label": str(operation_task.get("operation_label") or "").strip(),
            "status": "succeeded",
            "status_label": str(operation_task.get("status_label") or "").strip(),
            "task_id": str(operation_task.get("task_id") or "").strip(),
            "stdout": str(operation_task.get("stdout") or "").strip(),
            "stderr": str(operation_task.get("stderr") or "").strip(),
            "exit_code": operation_task.get("exit_code"),
            "operation_task": dict(operation_task),
        }
        observation = self._normalizer().normalize(
            run_id=run_id,
            call_id=pending_record.tool_call.call_id,
            tool_name=pending_record.tool_call.tool_name,
            raw_result=raw_result,
        )
        self._event_log.append(
            run_id,
            "tool_observation_created",
            observation.to_dict(),
        )
        return ToolExecutionRecord(
            tool_call=pending_record.tool_call,
            raw_result=raw_result,
            observation=observation,
        )

    def _background_operation_arguments(self, raw_result: dict[str, Any]) -> str:
        source = str(raw_result.get("source") or "").strip()
        if source == "desktop_client_tool":
            args = raw_result.get("tool_args") if isinstance(raw_result.get("tool_args"), dict) else {}
            return json.dumps(dict(args), ensure_ascii=False)
        return json.dumps(
            {
                "command": raw_result.get("command") or "",
                "timeout_sec": raw_result.get("timeout_sec") or 120,
            },
            ensure_ascii=False,
        )

    def _completed_desktop_client_tool_record(
        self,
        *,
        run_id: str,
        pending_record: ToolExecutionRecord,
        operation_task: dict[str, Any],
    ) -> ToolExecutionRecord:
        tool_result = (
            operation_task.get("tool_result")
            if isinstance(operation_task.get("tool_result"), dict)
            else {}
        )
        content = tool_result.get("content") if isinstance(tool_result.get("content"), dict) else {}
        raw_result: dict[str, Any] = {
            "ok": bool(tool_result.get("ok", operation_task.get("ok", True))),
            "execution_ok": bool(tool_result.get("ok", operation_task.get("ok", True))),
            "source": "desktop_client_tool",
            "status": "succeeded" if bool(tool_result.get("ok", operation_task.get("ok", True))) else "error",
            "task_id": str(operation_task.get("task_id") or "").strip(),
            "run_id": str(operation_task.get("run_id") or "").strip(),
            "call_id": pending_record.tool_call.call_id,
            "tool_name": pending_record.tool_call.tool_name,
            "tool_args": dict(pending_record.raw_result.get("tool_args") or {}),
            "result": content if content else dict(tool_result),
            "summary": str(
                content.get("summary")
                or tool_result.get("summary")
                or operation_task.get("summary")
                or ""
            ).strip(),
            "error": str(tool_result.get("error") or operation_task.get("error") or "").strip(),
            "error_code": str(tool_result.get("errorCode") or tool_result.get("error_code") or "").strip(),
            "audit_summary": str(content.get("audit_summary") or "").strip(),
        }
        if "stdout" in content:
            raw_result["stdout"] = str(content.get("stdout") or "")
        if "stderr" in content:
            raw_result["stderr"] = str(content.get("stderr") or "")
        if "exit_code" in content:
            raw_result["exit_code"] = content.get("exit_code")
        observation = self._normalizer().normalize(
            run_id=run_id,
            call_id=pending_record.tool_call.call_id,
            tool_name=pending_record.tool_call.tool_name,
            raw_result=raw_result,
        )
        self._event_log.append(
            run_id,
            "tool_observation_created",
            observation.to_dict(),
        )
        return ToolExecutionRecord(
            tool_call=pending_record.tool_call,
            raw_result=raw_result,
            observation=observation,
        )

    def _normalizer(self):
        from services.agent_runtime.shared.tool_results import ToolResultNormalizer

        return ToolResultNormalizer()

    def _build_continuation_messages(
        self,
        *,
        run_id: str,
        resumed_call: CollectedToolCall,
        records: list[ToolExecutionRecord],
    ) -> list[dict[str, Any]]:
        messages = self._initial_messages_for_run(run_id)
        if not messages:
            return []
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [resumed_call.to_openai_tool_call()],
            }
        )
        for record in records:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": record.tool_call.call_id,
                    "content": json.dumps(record.raw_result, ensure_ascii=False),
                }
            )
        return messages

    def _initial_messages_for_run(self, run_id: str) -> list[dict[str, Any]]:
        for event in reversed(self._transcript_store.list_events(run_id)):
            if str(event.get("type") or "").strip() != "initial_messages":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
            return [dict(item) for item in messages if isinstance(item, dict)]
        for event in reversed(self._transcript_store.list_events(run_id)):
            if str(event.get("type") or "").strip() != "user_message":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            content = str(payload.get("content") or "").strip()
            if content:
                return [{"role": "user", "content": content}]
        return []
