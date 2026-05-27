"""Minimal continuous execution loop for agent_runtime_v2."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime_v2.completion_policy import CompletionDecision, CompletionPolicy
from services.agent_runtime_v2.event_log import RuntimeEventLog
from services.agent_runtime_v2.llm_step import LLMStep
from services.agent_runtime_v2.state_store import TaskRunStore
from services.agent_runtime_v2.task_run import TaskRun
from services.agent_runtime_v2.tool_execution_runner import ToolExecutionRecord, ToolExecutionRunner
from services.agent_runtime_v2.tool_result_normalizer import ToolObservation
from services.agent_runtime_v2.transcript_store import TranscriptStore
from services.agent_runtime_v2.verification_policy import VerificationEvidence, VerificationPolicy


@dataclass
class QueryEngineResult:
    task_run: TaskRun
    final_content: str = ""
    completion_decision: CompletionDecision | None = None
    observations: list[ToolObservation] = field(default_factory=list)
    model_steps: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.task_run.run_id,
            "status": self.task_run.status,
            "final_content": self.final_content,
            "completion_decision": (
                self.completion_decision.to_dict()
                if self.completion_decision is not None
                else None
            ),
            "observations": [item.to_dict() for item in self.observations],
            "model_steps": self.model_steps,
        }


class QueryEngine:
    def __init__(
        self,
        *,
        llm_step: LLMStep,
        tool_runner: ToolExecutionRunner | None = None,
        state_store: TaskRunStore | None = None,
        transcript_store: TranscriptStore | None = None,
        event_log: RuntimeEventLog | None = None,
        completion_policy: CompletionPolicy | None = None,
        verification_policy: VerificationPolicy | None = None,
        max_model_steps: int = 3,
        max_tool_calls_per_round: int = 6,
    ):
        self._llm_step = llm_step
        self._tool_runner = tool_runner
        self._state_store = state_store or TaskRunStore()
        self._transcript_store = transcript_store or TranscriptStore()
        self._event_log = event_log or RuntimeEventLog()
        self._completion_policy = completion_policy or CompletionPolicy()
        self._verification_policy = verification_policy or VerificationPolicy()
        self._max_model_steps = max(1, int(max_model_steps or 3))
        self._max_tool_calls_per_round = max(1, int(max_tool_calls_per_round or 6))

    async def run(
        self,
        task_run: TaskRun,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        provider_id: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        verification_evidence: list[VerificationEvidence] | None = None,
        task_tree_verified: bool = False,
        goal_covered: bool = False,
    ) -> QueryEngineResult:
        task_run = self._state_store.append_event(
            task_run,
            "query_engine_started",
            {"max_model_steps": self._max_model_steps},
            status="running",
        )
        self._event_log.append(
            task_run.run_id,
            "query_engine_started",
            {"max_model_steps": self._max_model_steps},
        )
        working_messages = list(messages or [])
        final_content = ""
        observations: list[ToolObservation] = []
        latest_decision: CompletionDecision | None = None
        model_steps = 0
        for step_index in range(1, self._max_model_steps + 1):
            model_steps = step_index
            llm_result = await self._llm_step.run(
                provider_id=provider_id,
                model_name=model_name,
                messages=working_messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                max_tool_calls=self._max_tool_calls_per_round,
            )
            final_content = llm_result.content
            self._event_log.append(
                task_run.run_id,
                "llm_step_completed",
                {
                    "step_index": step_index,
                    "content_length": len(llm_result.content),
                    "tool_call_count": len(llm_result.tool_calls),
                    "usage": dict(llm_result.usage),
                },
            )
            self._transcript_store.append(
                task_run.run_id,
                "model_output",
                {
                    "step_index": step_index,
                    "content": llm_result.content,
                    "tool_calls": [item.to_dict() for item in llm_result.tool_calls],
                },
            )
            if llm_result.error:
                latest_decision = CompletionDecision("fail", ["llm_error"])
                self._record_completion_decision(task_run.run_id, latest_decision)
                task_run = self._state_store.append_event(
                    task_run,
                    "query_engine_failed",
                    {"error": llm_result.error},
                    status="failed",
                )
                return QueryEngineResult(
                    task_run=task_run,
                    final_content=final_content,
                    completion_decision=latest_decision,
                    observations=observations,
                    model_steps=step_index,
                )
            if llm_result.tool_calls:
                if self._tool_runner is None:
                    latest_decision = CompletionDecision("blocked", ["tool_runner_missing"])
                    self._record_completion_decision(task_run.run_id, latest_decision)
                    task_run = self._state_store.append_event(
                        task_run,
                        "query_engine_blocked",
                        {"reason": "tool_runner_missing"},
                        status="blocked",
                    )
                    break
                working_messages.append(
                    {
                        "role": "assistant",
                        "content": llm_result.content or None,
                        "tool_calls": [
                            item.to_openai_tool_call()
                            for item in llm_result.tool_calls
                        ],
                    }
                )
                records = await self._tool_runner.execute(
                    run_id=task_run.run_id,
                    tool_calls=llm_result.tool_calls,
                )
                observations.extend([item.observation for item in records])
                self._append_tool_messages(working_messages, records)
                self._event_log.append(
                    task_run.run_id,
                    "tool_round_completed",
                    {
                        "step_index": step_index,
                        "observation_count": len(records),
                    },
                )
                blocked_decision = self._blocked_tool_decision(records)
                if blocked_decision is not None:
                    latest_decision = blocked_decision
                    self._record_completion_decision(task_run.run_id, latest_decision)
                    task_run = self._state_store.append_event(
                        task_run,
                        "query_engine_blocked",
                        {"decision": latest_decision.to_dict()},
                        status=self._status_for_decision(latest_decision),
                    )
                    break
                background_decision = self._background_operation_decision(records)
                if background_decision is not None:
                    latest_decision = background_decision
                    self._record_completion_decision(task_run.run_id, latest_decision)
                    task_run = self._state_store.append_event(
                        task_run,
                        "query_engine_waiting_operation",
                        {"decision": latest_decision.to_dict()},
                        status="waiting_user",
                    )
                    break
                continue
            verification = self._verification_policy.build_state(
                user_goal=task_run.user_goal,
                evidence=verification_evidence,
            )
            latest_decision = self._completion_policy.evaluate(
                response_content=llm_result.content,
                latest_observation=observations[-1] if observations else None,
                verification=verification,
                task_tree_verified=task_tree_verified,
                goal_covered=goal_covered,
            )
            self._record_completion_decision(task_run.run_id, latest_decision)
            if latest_decision.action == "complete":
                task_run = self._state_store.append_event(
                    task_run,
                    "query_engine_completed",
                    {"decision": latest_decision.to_dict()},
                    status="completed",
                )
                break
            if latest_decision.action == "retry_model":
                continue
            status = self._status_for_decision(latest_decision)
            task_run = self._state_store.append_event(
                task_run,
                "query_engine_paused",
                {"decision": latest_decision.to_dict()},
                status=status,
            )
            break
        else:
            latest_decision = CompletionDecision("fail", ["model_step_budget_exceeded"])
            self._record_completion_decision(task_run.run_id, latest_decision)
            task_run = self._state_store.append_event(
                task_run,
                "query_engine_failed",
                {"decision": latest_decision.to_dict()},
                status="failed",
            )
        return QueryEngineResult(
            task_run=task_run,
            final_content=final_content,
            completion_decision=latest_decision,
            observations=observations,
            model_steps=model_steps,
        )

    def _record_completion_decision(
        self,
        run_id: str,
        decision: CompletionDecision,
    ) -> None:
        self._event_log.append(
            run_id,
            "completion_decision",
            decision.to_dict(),
        )

    def _append_tool_messages(
        self,
        messages: list[dict[str, Any]],
        records: list[ToolExecutionRecord],
    ) -> None:
        for record in records:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": record.tool_call.call_id,
                    "content": json.dumps(record.raw_result, ensure_ascii=False),
                }
            )

    def _blocked_tool_decision(
        self,
        records: list[ToolExecutionRecord],
    ) -> CompletionDecision | None:
        blocked = [item for item in records if item.observation.status == "blocked"]
        if not blocked:
            return None
        if any(
            item.permission_decision is not None
            and item.permission_decision.behavior == "ask"
            for item in blocked
        ):
            return CompletionDecision("request_user", ["permission_required"])
            return CompletionDecision("blocked", ["permission_denied"])

    def _background_operation_decision(
        self,
        records: list[ToolExecutionRecord],
    ) -> CompletionDecision | None:
        for item in records:
            raw = item.raw_result if isinstance(item.raw_result, dict) else {}
            if str(raw.get("source") or "").strip() not in {
                "operation_wait_task",
                "cli_plugin_login_task",
            }:
                continue
            status = str(raw.get("status") or "").strip().lower()
            if status in {"queued", "running", "waiting_user_action"}:
                return CompletionDecision("request_user", ["background_operation_pending"])
        return None

    def _status_for_decision(self, decision: CompletionDecision) -> str:
        if decision.action == "verify":
            return "verifying"
        if decision.action == "wait_background":
            return "waiting_background"
        if decision.action == "request_user":
            return "waiting_user"
        if decision.action == "fail":
            return "failed"
        if decision.action == "blocked":
            return "blocked"
        return "running"
