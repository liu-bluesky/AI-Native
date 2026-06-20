"""Minimal continuous execution loop for agent_runtime_v2."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime.shared.completion_policy import CompletionDecision, CompletionPolicy
from services.agent_runtime.core.event_log import RuntimeEventLog
from services.agent_runtime.v2.llm_step import LLMStep
from services.agent_runtime.core.state_store import TaskRunStore
from services.agent_runtime.core.task_run import TaskRun
from services.agent_runtime.shared.tool_execution_runner import (
    ToolExecutionRecord,
    ToolExecutionRunner,
)
from services.agent_runtime.shared.model_output_normalizer import (
    ModelOutputNormalizationResult,
    normalize_model_output,
)
from services.agent_runtime.shared.tool_results import ToolObservation
from services.agent_runtime.core.transcript_store import TranscriptStore
from services.agent_runtime.shared.verification_policy import (
    VerificationEvidence,
    VerificationPolicy,
)


def _preview_text(value: str, max_chars: int = 800) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n（内容已截断）"


@dataclass
class QueryEngineResult:
    task_run: TaskRun
    final_content: str = ""
    completion_decision: CompletionDecision | None = None
    observations: list[ToolObservation] = field(default_factory=list)
    model_steps: int = 0
    total_tool_calls: int = 0

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
            "total_tool_calls": self.total_tool_calls,
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
        max_tool_calls_total: int | None = None,
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
        default_total = self._max_model_steps * self._max_tool_calls_per_round
        self._max_tool_calls_total = max(
            1,
            int(max_tool_calls_total or default_total),
        )

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
            {
                "max_model_steps": self._max_model_steps,
                "max_tool_calls_per_round": self._max_tool_calls_per_round,
                "max_tool_calls_total": self._max_tool_calls_total,
            },
            status="running",
        )
        self._event_log.append(
            task_run.run_id,
            "query_engine_started",
            {
                "max_model_steps": self._max_model_steps,
                "max_tool_calls_per_round": self._max_tool_calls_per_round,
                "max_tool_calls_total": self._max_tool_calls_total,
            },
        )
        working_messages = list(messages or [])
        final_content = ""
        observations: list[ToolObservation] = []
        latest_decision: CompletionDecision | None = None
        model_steps = 0
        tool_round_completed = False
        final_answer_retry_used = False
        step_index = 0
        total_tool_calls = 0
        while step_index < self._max_model_steps:
            step_index += 1
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
            normalization = self._normalize_llm_result(
                llm_result,
                tools=tools,
            )
            final_content = llm_result.content
            self._event_log.append(
                task_run.run_id,
                "llm_step_completed",
                {
                    "step_index": step_index,
                    "content_preview": _preview_text(llm_result.content),
                    "content_length": len(llm_result.content),
                    "tool_call_count": len(llm_result.tool_calls),
                    "usage": dict(llm_result.usage),
                    "normalization": normalization.to_event_payload(),
                },
            )
            self._record_model_output_normalized(
                task_run.run_id,
                step_index=step_index,
                normalization=normalization,
            )
            self._transcript_store.append(
                task_run.run_id,
                "model_output",
                {
                    "step_index": step_index,
                    "content": llm_result.content,
                    "raw_content": normalization.raw_content,
                    "tool_calls": [item.to_dict() for item in llm_result.tool_calls],
                    "normalization": normalization.to_transcript_payload(),
                },
            )
            if llm_result.error:
                error_message = self._llm_error_message(llm_result.error)
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
                    final_content=final_content or f"对话失败：{error_message}",
                    completion_decision=latest_decision,
                    observations=observations,
                    model_steps=step_index,
                    total_tool_calls=total_tool_calls,
                )
            if llm_result.tool_calls:
                next_tool_call_count = len(llm_result.tool_calls)
                if total_tool_calls + next_tool_call_count > self._max_tool_calls_total:
                    latest_decision = CompletionDecision(
                        "fail",
                        ["tool_call_budget_exceeded"],
                    )
                    self._record_completion_decision(task_run.run_id, latest_decision)
                    final_content = (
                        "工具调用次数已达到上限，已停止继续执行。"
                        "请缩小问题范围或调整运行时工具调用预算后重试。"
                    )
                    payload = {
                        "decision": latest_decision.to_dict(),
                        "step_index": step_index,
                        "tool_call_count": next_tool_call_count,
                        "total_tool_calls": total_tool_calls,
                        "max_tool_calls_total": self._max_tool_calls_total,
                    }
                    self._event_log.append(
                        task_run.run_id,
                        "tool_call_budget_exceeded",
                        payload,
                    )
                    task_run = self._state_store.append_event(
                        task_run,
                        "query_engine_failed",
                        payload,
                        status="failed",
                    )
                    return QueryEngineResult(
                        task_run=task_run,
                        final_content=final_content,
                        completion_decision=latest_decision,
                        observations=observations,
                        model_steps=step_index,
                        total_tool_calls=total_tool_calls,
                    )
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
                total_tool_calls += next_tool_call_count
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
                tool_round_completed = True
                observations.extend([item.observation for item in records])
                self._append_tool_messages(working_messages, records)
                self._event_log.append(
                    task_run.run_id,
                    "tool_round_completed",
                    {
                        "step_index": step_index,
                        "observation_count": len(records),
                        "total_tool_calls": total_tool_calls,
                        "max_tool_calls_total": self._max_tool_calls_total,
                    },
                )
                blocked_decision = self._blocked_tool_decision(records)
                if blocked_decision is not None:
                    latest_decision = blocked_decision
                    self._record_completion_decision(task_run.run_id, latest_decision)
                    final_content = self._blocked_tool_final_content(
                        latest_decision,
                        records,
                    )
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
                    final_content = self._background_operation_final_content(records)
                    task_run = self._state_store.append_event(
                        task_run,
                        "query_engine_waiting_operation",
                        {"decision": latest_decision.to_dict()},
                        status="waiting_user",
                    )
                    break
                environment_block_decision = self._environment_block_decision(records)
                if environment_block_decision is not None:
                    latest_decision = environment_block_decision
                    self._record_completion_decision(task_run.run_id, latest_decision)
                    final_content = self._environment_block_final_content(records)
                    task_run = self._state_store.append_event(
                        task_run,
                        "query_engine_blocked",
                        {"decision": latest_decision.to_dict()},
                        status="blocked",
                    )
                    break
                continue
            if normalization.leak_detected and not str(llm_result.content or "").strip():
                latest_decision = CompletionDecision("retry_model", ["protocol_leak_retry"])
                self._record_completion_decision(task_run.run_id, latest_decision)
                working_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "上一条模型输出包含内部工具调用协议，但没有形成可执行工具调用。"
                            "请改用结构化 tool_calls 调用可用工具；如果不需要工具，"
                            "只输出用户可见回答，不要输出内部协议。"
                        ),
                    }
                )
                continue
            verification = self._verification_policy.build_state(
                user_goal=task_run.user_goal,
                evidence=verification_evidence,
            )
            completion_observation = self._completion_observation(
                observations,
                response_content=llm_result.content,
            )
            latest_decision = self._completion_policy.evaluate(
                response_content=llm_result.content,
                latest_observation=completion_observation,
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
            if latest_decision.action in {"retry_model", "continue"}:
                if latest_decision.action == "continue":
                    working_messages.append(
                        {
                            "role": "assistant",
                            "content": llm_result.content,
                        }
                    )
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
            if tool_round_completed and not str(final_content or "").strip() and not final_answer_retry_used:
                final_answer_retry_used = True
                step_index += 1
                model_steps = step_index
                final_prompt = (
                    "工具执行已经完成。请基于上面的工具返回结果，直接回答用户原始问题；"
                    "不要再调用工具，不要只复述原始工具输出。"
                )
                final_messages = [
                    *working_messages,
                    {"role": "user", "content": final_prompt},
                ]
                llm_result = await self._llm_step.run(
                    provider_id=provider_id,
                    model_name=model_name,
                    messages=final_messages,
                    tools=[],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_tool_calls=0,
                )
                normalization = self._normalize_llm_result(
                    llm_result,
                    tools=[],
                    max_tool_calls=0,
                )
                final_content = llm_result.content
                self._event_log.append(
                    task_run.run_id,
                    "llm_step_completed",
                    {
                        "step_index": step_index,
                        "content_preview": _preview_text(llm_result.content),
                        "content_length": len(llm_result.content),
                        "tool_call_count": len(llm_result.tool_calls),
                        "usage": dict(llm_result.usage),
                        "final_answer_retry": True,
                        "normalization": normalization.to_event_payload(),
                    },
                )
                self._record_model_output_normalized(
                    task_run.run_id,
                    step_index=step_index,
                    normalization=normalization,
                    final_answer_retry=True,
                )
                self._transcript_store.append(
                    task_run.run_id,
                    "model_output",
                    {
                        "step_index": step_index,
                        "content": llm_result.content,
                        "raw_content": normalization.raw_content,
                        "tool_calls": [item.to_dict() for item in llm_result.tool_calls],
                        "final_answer_retry": True,
                        "normalization": normalization.to_transcript_payload(),
                    },
                )
                if llm_result.error:
                    error_message = self._llm_error_message(llm_result.error)
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
                        final_content=final_content or f"对话失败：{error_message}",
                        completion_decision=latest_decision,
                        observations=observations,
                        model_steps=step_index,
                        total_tool_calls=total_tool_calls,
                    )
                if str(final_content or "").strip():
                    latest_decision = CompletionDecision("complete", ["final_answer_after_tool"])
                    self._record_completion_decision(task_run.run_id, latest_decision)
                    task_run = self._state_store.append_event(
                        task_run,
                        "query_engine_completed",
                        {"decision": latest_decision.to_dict()},
                        status="completed",
                    )
                    return QueryEngineResult(
                        task_run=task_run,
                        final_content=final_content,
                        completion_decision=latest_decision,
                        observations=observations,
                        model_steps=step_index,
                        total_tool_calls=total_tool_calls,
                    )
            reason = (
                "missing_final_response_after_tool"
                if tool_round_completed and not str(final_content or "").strip()
                else "model_step_budget_exceeded"
            )
            latest_decision = CompletionDecision("fail", [reason])
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
            total_tool_calls=total_tool_calls,
        )

    def _normalize_llm_result(
        self,
        llm_result: Any,
        *,
        tools: list[dict[str, Any]] | None,
        max_tool_calls: int | None = None,
    ) -> ModelOutputNormalizationResult:
        normalization = normalize_model_output(
            content=str(getattr(llm_result, "content", "") or ""),
            structured_tool_calls=list(getattr(llm_result, "tool_calls", []) or []),
            allowed_tool_names=self._allowed_tool_names(tools),
            max_tool_calls=(
                self._max_tool_calls_per_round
                if max_tool_calls is None
                else max_tool_calls
            ),
        )
        llm_result.content = normalization.visible_content
        llm_result.tool_calls = normalization.tool_calls
        return normalization

    def _allowed_tool_names(self, tools: list[dict[str, Any]] | None) -> set[str]:
        names: set[str] = set()
        for tool in tools or []:
            if not isinstance(tool, dict):
                continue
            tool_name = str(tool.get("tool_name") or tool.get("name") or "").strip()
            if tool_name:
                names.add(tool_name)
                continue
            function = tool.get("function")
            if isinstance(function, dict):
                function_name = str(function.get("name") or "").strip()
                if function_name:
                    names.add(function_name)
        return names

    def _completion_observation(
        self,
        observations: list[ToolObservation],
        *,
        response_content: str,
    ) -> ToolObservation | None:
        if not observations:
            return None
        latest = observations[-1]
        if not latest.is_error:
            return latest
        if not str(response_content or "").strip():
            return latest
        if self._error_observation_has_useful_output(latest):
            return None
        return latest

    def _error_observation_has_useful_output(self, observation: ToolObservation) -> bool:
        raw_result = observation.raw_result if isinstance(observation.raw_result, dict) else {}
        for key in ("summary", "stdout", "result"):
            value = raw_result.get(key)
            if isinstance(value, (dict, list)) and value:
                return True
            if isinstance(value, str) and value.strip():
                return True
        return bool(str(observation.summary or "").strip())

    def _record_model_output_normalized(
        self,
        run_id: str,
        *,
        step_index: int,
        normalization: ModelOutputNormalizationResult,
        final_answer_retry: bool = False,
    ) -> None:
        if not normalization.has_changes():
            return
        payload = {
            "step_index": step_index,
            **normalization.to_event_payload(),
        }
        if final_answer_retry:
            payload["final_answer_retry"] = True
        self._event_log.append(
            run_id,
            "model_output_normalized",
            payload,
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
            if status in {"queued", "running"}:
                return CompletionDecision("request_user", ["background_operation_pending"])
            if status == "waiting_user_action":
                has_user_action = bool(
                    str(raw.get("authorization_url") or "").strip()
                    or (
                        isinstance(raw.get("interaction_schema"), dict)
                        and raw.get("interaction_schema")
                    )
                )
                if has_user_action:
                    return CompletionDecision("request_user", ["background_operation_pending"])
        return None

    def _environment_block_decision(
        self,
        records: list[ToolExecutionRecord],
    ) -> CompletionDecision | None:
        for item in records:
            reason = self._environment_block_reason(item)
            if reason:
                return CompletionDecision("blocked", [reason])
        return None

    def _environment_block_reason(self, record: ToolExecutionRecord) -> str:
        if record.tool_call.tool_name != "project_host_run_command":
            return ""
        if record.observation.status not in {"error", "failed", "blocked"}:
            return ""
        payload = record.raw_result if isinstance(record.raw_result, dict) else {}
        error_text = self._record_text(payload, "error", "message", "stderr", "stdout")
        if "host workspace_path does not exist" in error_text.lower():
            return "host_workspace_missing"
        if "host workspace_path must be absolute" in error_text.lower():
            return "host_workspace_invalid"
        if "cannot resolve fallback service repo root" in error_text.lower():
            return "host_workspace_unresolved"
        return ""

    def _environment_block_final_content(
        self,
        records: list[ToolExecutionRecord],
    ) -> str:
        for item in records:
            reason = self._environment_block_reason(item)
            if not reason:
                continue
            payload = item.raw_result if isinstance(item.raw_result, dict) else {}
            command = str(payload.get("command") or "").strip()
            requested_workspace_path = str(payload.get("requested_workspace_path") or "").strip()
            error_text = self._record_text(payload, "error", "message", "stderr", "stdout")
            lines = [
                "执行环境阻塞：本轮工具调用已经尝试执行，但当前项目工作区不可用，不能继续等待授权。",
            ]
            if error_text:
                lines.append(f"原因：{error_text}")
            if requested_workspace_path:
                lines.append(f"工作区路径：{requested_workspace_path}")
            if command:
                lines.append(f"受影响命令：{command}")
            lines.extend(
                [
                    "",
                    "下一步：请先在项目设置中改成当前机器存在的 workspace_path，或挂载对应磁盘后重新发起本轮命令。",
                ]
            )
            return "\n".join(lines).strip()
        return "执行环境阻塞：当前工具执行环境不可用，请先修正项目工作区配置后重试。"

    def _record_text(self, payload: dict[str, Any], *keys: str) -> str:
        values: list[str] = []
        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            values.append(str(value).strip())
        return "\n".join(item for item in values if item).strip()

    def _background_operation_final_content(
        self,
        records: list[ToolExecutionRecord],
    ) -> str:
        for item in records:
            raw = item.raw_result if isinstance(item.raw_result, dict) else {}
            if str(raw.get("source") or "").strip() not in {
                "operation_wait_task",
                "cli_plugin_login_task",
            }:
                continue
            status = str(raw.get("status") or "").strip().lower()
            if status not in {"queued", "running", "waiting_user_action"}:
                continue
            return self._format_background_operation_waiting_content(raw, status=status)
        return "操作仍在继续，完成后会自动恢复本轮执行。"

    def _format_background_operation_waiting_content(
        self,
        raw: dict[str, Any],
        *,
        status: str,
    ) -> str:
        command = str(raw.get("command") or "").strip()
        task_id = str(raw.get("task_id") or raw.get("operation_id") or "").strip()
        operation_label = str(raw.get("operation_label") or "").strip()
        operation_kind = str(raw.get("operation_kind") or "").strip().lower()
        authorization_url = str(raw.get("authorization_url") or "").strip()
        interaction_schema = (
            raw.get("interaction_schema")
            if isinstance(raw.get("interaction_schema"), dict)
            else None
        )
        interaction_title = ""
        if interaction_schema:
            interaction_title = str(interaction_schema.get("title") or "").strip()
        next_step = str(raw.get("next_step") or raw.get("message") or "").strip()

        lines = ["等待用户操作：后台授权流程已经启动，但还需要后续动作才能继续。"]
        if operation_label:
            lines.append(f"等待对象：{operation_label}")
        elif operation_kind == "auth_login":
            lines.append("等待对象：登录授权")
        if command:
            lines.append(f"执行命令：{command}")
        if task_id:
            lines.append(f"任务 ID：{task_id}")
        lines.append(f"当前状态：{status}")

        if next_step:
            lines.append(f"下一步：{next_step}")
        elif interaction_schema:
            if interaction_title:
                lines.append(f"下一步：在表单中完成“{interaction_title}”，选择授权范围后继续。")
            else:
                lines.append("下一步：在表单中选择授权范围后继续。")
        elif authorization_url:
            lines.append("下一步：打开授权链接并在浏览器完成授权。")
            lines.append(f"授权链接：{authorization_url}")
        elif status == "queued":
            lines.append("下一步：等待后台任务开始执行；有授权链接、验证码或表单时会继续更新本轮状态。")
        elif status == "running":
            lines.append("下一步：等待后台任务返回授权链接、验证码或完成结果。")
        elif operation_kind == "auth_login":
            lines.append("下一步：等待授权流程返回可操作信息或完成结果。")
        else:
            lines.append("下一步：等待操作完成，完成后会自动恢复本轮执行。")
        return "\n".join(lines).strip()

    def _blocked_tool_final_content(
        self,
        decision: CompletionDecision,
        records: list[ToolExecutionRecord],
    ) -> str:
        if decision.action == "request_user":
            pending = [
                item
                for item in records
                if item.permission_decision is not None
                and item.permission_decision.behavior == "ask"
            ]
            if len(pending) > 1:
                return "等待你授权这些工具调用后继续。"
            return "等待你授权工具调用后继续。"
        if decision.action == "blocked":
            return "工具调用被权限策略阻塞。"
        return ""

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
        return "blocked"

    def _llm_error_message(self, error: dict[str, Any] | None) -> str:
        payload = error if isinstance(error, dict) else {}
        for key in ("message", "error_message", "detail", "raw_error", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "模型服务请求失败"
