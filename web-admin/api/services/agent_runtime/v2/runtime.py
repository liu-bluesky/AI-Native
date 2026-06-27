"""Stage 6 v2-only AgentTaskRuntime."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Callable

from services.agent_runtime.core.event_log import RuntimeEventLog
from services.agent_runtime.v2.dynamic_tool_pool import DynamicToolPool
from services.agent_runtime.v2.llm_step import LLMStep
from services.agent_runtime.v2.permission_policy import PermissionPolicy
from services.agent_runtime.shared.tool_registry import default_plugin_registry_context
from services.agent_runtime.v2.query_engine import QueryEngine, QueryEngineResult
from services.agent_runtime.core.state_store import TaskRunStore
from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
from services.agent_runtime.core.transcript_store import TranscriptStore
from services.agent_runtime.shared.trust_policy import TrustPolicy
from services.agent_runtime.shared.verification_policy import VerificationPolicy
from services.tool_executor import ToolExecutor


class AgentTaskRuntime:
    def __init__(
        self,
        *,
        llm_service: Any | None = None,
        conversation_manager: Any | None = None,
        tool_executor: Any | None = None,
        tool_executor_factory: Callable[..., Any] | None = None,
        runtime_options: dict[str, Any] | None = None,
        state_store: TaskRunStore | None = None,
        transcript_store: TranscriptStore | None = None,
        event_log: RuntimeEventLog | None = None,
    ):
        self._llm_service = llm_service
        self._conversation_manager = conversation_manager
        self._tool_executor = tool_executor
        self._tool_executor_factory = tool_executor_factory
        self._runtime_options = dict(runtime_options or {})
        self._state_store = state_store or TaskRunStore()
        self._transcript_store = transcript_store or TranscriptStore()
        self._event_log = event_log or RuntimeEventLog()

    @property
    def state_store(self) -> TaskRunStore:
        return self._state_store

    @property
    def transcript_store(self) -> TranscriptStore:
        return self._transcript_store

    @property
    def event_log(self) -> RuntimeEventLog:
        return self._event_log

    def _resolve_mode(self, assistant_workflow: dict[str, Any] | None) -> str:
        source = assistant_workflow if isinstance(assistant_workflow, dict) else {}
        raw_mode = str(source.get("agent_runtime_mode") or "").strip().lower()
        if raw_mode in {"", "query_engine", "v2", "delegate", "legacy", "legacy_orchestrator"}:
            return "query_engine"
        return "query_engine"

    def _json_safe(self, value: Any) -> Any:
        try:
            return json.loads(json.dumps(value, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            return None

    def _resolve_llm_service(self) -> Any | None:
        return self._llm_service

    def _resolve_conversation_manager(self) -> Any | None:
        return self._conversation_manager

    def _resolve_tool_executor(
        self,
        *,
        project_id: str,
        employee_id: str,
        username: str,
        chat_session_id: str,
        role_ids: list[str] | None,
        allowed_tool_names: list[str],
        local_connector: Any | None,
        local_connector_workspace_path: str,
        host_workspace_path: str,
        local_connector_sandbox_mode: str,
        global_assistant_bridge_handler: Any | None,
    ) -> Any:
        if self._tool_executor is not None:
            return self._tool_executor
        if self._tool_executor_factory is not None:
            return self._tool_executor_factory(
                project_id=project_id,
                employee_id=employee_id,
                username=username,
                chat_session_id=chat_session_id,
                role_ids=role_ids,
                allowed_tool_names=allowed_tool_names,
                local_connector=local_connector,
                local_connector_workspace_path=local_connector_workspace_path,
                host_workspace_path=host_workspace_path,
                local_connector_sandbox_mode=local_connector_sandbox_mode,
                global_assistant_bridge_handler=global_assistant_bridge_handler,
            )
        return ToolExecutor(
            project_id,
            employee_id,
            username=username,
            chat_session_id=chat_session_id,
            role_ids=role_ids,
            allowed_tool_names=allowed_tool_names,
            local_connector=local_connector,
            local_connector_workspace_path=local_connector_workspace_path,
            host_workspace_path=host_workspace_path,
            local_connector_sandbox_mode=local_connector_sandbox_mode,
            global_assistant_bridge_handler=global_assistant_bridge_handler,
        )

    def _requires_completion_evidence(self, user_goal: str) -> bool:
        return VerificationPolicy().build_state(user_goal=user_goal).required

    def _completion_gate_inputs(self, user_goal: str) -> dict[str, bool]:
        requires_evidence = self._requires_completion_evidence(user_goal)
        return {
            "task_tree_verified": not requires_evidence,
            "goal_covered": not requires_evidence,
        }

    def _fallback_content_from_observations(
        self,
        observations: list[Any] | None,
    ) -> str:
        items = list(observations or [])
        if not items:
            return ""
        lines = ["工具执行已完成，但模型未继续生成正文。以下是工具返回摘要："]
        for index, observation in enumerate(items[-5:], start=1):
            tool_name = str(getattr(observation, "tool_name", "") or "").strip() or "工具"
            status = str(getattr(observation, "status", "") or "").strip()
            summary = str(getattr(observation, "summary", "") or "").strip()
            raw_result = getattr(observation, "raw_result", None)
            if not summary and isinstance(raw_result, dict):
                summary = str(
                    raw_result.get("stdout")
                    or raw_result.get("output_preview")
                    or raw_result.get("message")
                    or raw_result.get("stderr")
                    or raw_result.get("error")
                    or ""
                ).strip()
            summary = summary[-1200:] if summary else "无输出摘要"
            status_text = f" · {status}" if status else ""
            lines.append(f"{index}. {tool_name}{status_text}\n{summary}")
        return "\n\n".join(lines).strip()

    def _background_operation_payload_from_observations(
        self,
        observations: list[Any] | None,
    ) -> dict[str, Any]:
        for observation in reversed(list(observations or [])):
            raw_result = getattr(observation, "raw_result", None)
            if not isinstance(raw_result, dict):
                continue
            if str(raw_result.get("source") or "").strip() not in {
                "operation_wait_task",
                "cli_plugin_login_task",
            }:
                continue
            status = str(raw_result.get("status") or "").strip().lower()
            if status not in {"queued", "running", "waiting_user_action"}:
                continue
            authorization_url = str(raw_result.get("authorization_url") or "").strip()
            interaction_schema = (
                raw_result.get("interaction_schema")
                if isinstance(raw_result.get("interaction_schema"), dict)
                else None
            )
            action_type = str(raw_result.get("action_type") or "").strip().lower()
            if action_type == "open_url" and not authorization_url:
                action_type = "none"
            if not action_type:
                action_type = (
                    "open_url"
                    if authorization_url
                    else "interaction_form"
                    if interaction_schema
                    else "none"
                )
            return {
                "source": str(raw_result.get("source") or "").strip(),
                "workflow_kind": str(raw_result.get("operation_kind") or "auth_login").strip(),
                "workflow_label": str(raw_result.get("operation_label") or "网页登录授权").strip(),
                "workflow_id": str(raw_result.get("task_id") or "").strip(),
                "task_id": str(raw_result.get("task_id") or "").strip(),
                "status": status,
                "status_label": str(raw_result.get("status_label") or "").strip(),
                "summary": str(raw_result.get("summary") or raw_result.get("next_step") or "").strip(),
                "message": str(raw_result.get("next_step") or raw_result.get("message") or "").strip(),
                "action_type": action_type,
                "authorization_url": authorization_url,
                "interaction_schema": interaction_schema,
                "resume_command": str(raw_result.get("resume_command") or "").strip(),
                "command": str(raw_result.get("command") or "").strip(),
            }
        return {}

    def _build_resume_context(
        self,
        *,
        tools: list[dict] | None,
        provider_id: str,
        model_name: str,
        temperature: float,
        role_ids: list[str] | None,
        local_connector: Any | None,
        local_connector_workspace_path: str,
        host_workspace_path: str,
        local_connector_sandbox_mode: str,
        prompt_version: str,
        assistant_workflow: dict[str, Any] | None,
        capability_routing: dict[str, Any] | None,
        workspace_trusted: bool = True,
        include_browser_tools: bool = False,
        browser_bridge_available: bool = False,
    ) -> dict[str, Any]:
        safe_tools = self._json_safe(list(tools or []))
        if not isinstance(safe_tools, list):
            safe_tools = []
        tool_priority = []
        if isinstance(assistant_workflow, dict):
            raw_priority = assistant_workflow.get("tool_priority")
            if isinstance(raw_priority, list):
                tool_priority = [
                    str(item or "").strip()
                    for item in raw_priority
                    if str(item or "").strip()
                ]
        tool_pool = DynamicToolPool.from_runtime_tools(
            [dict(item) for item in safe_tools if isinstance(item, dict)],
            tool_priority=tool_priority,
            context=default_plugin_registry_context(
                workspace_path=str(host_workspace_path or local_connector_workspace_path or "").strip(),
                workspace_trusted=workspace_trusted,
                include_browser_tools=include_browser_tools,
                browser_bridge_available=browser_bridge_available,
            ),
        )
        return {
            "provider_id": str(provider_id or "").strip(),
            "model_name": str(model_name or "").strip(),
            "temperature": float(temperature),
            "tools": tool_pool.openai_tools(),
            "tool_pool": tool_pool.summary(),
            "role_ids": [
                str(item or "").strip()
                for item in (role_ids or [])
                if str(item or "").strip()
            ],
            "local_connector_id": str(getattr(local_connector, "id", "") or "").strip(),
            "local_connector_workspace_path": str(local_connector_workspace_path or "").strip(),
            "host_workspace_path": str(host_workspace_path or "").strip(),
            "local_connector_sandbox_mode": (
                str(local_connector_sandbox_mode or "workspace-write").strip()
                or "workspace-write"
            ),
            "prompt_version": str(prompt_version or "").strip(),
            "assistant_workflow": dict(assistant_workflow or {}),
            "capability_routing": dict(capability_routing or {}),
        }

    async def run(
        self,
        session_id: str,
        user_message: str,
        tools: list[dict],
        provider_id: str,
        model_name: str,
        temperature: float,
        project_id: str,
        employee_id: str,
        cancel_event: asyncio.Event,
        username: str = "",
        chat_session_id: str = "",
        role_ids: list[str] | None = None,
        messages: list[dict] | None = None,
        local_connector: Any | None = None,
        local_connector_workspace_path: str = "",
        host_workspace_path: str = "",
        local_connector_sandbox_mode: str = "workspace-write",
        global_assistant_bridge_handler: Any | None = None,
        prompt_version: str = "",
        assistant_workflow: dict[str, Any] | None = None,
        capability_routing: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict, None]:
        workspace_path = (
            str(host_workspace_path or "").strip()
            or str(local_connector_workspace_path or "").strip()
        )
        workspace_trusted = True
        if workspace_path:
            workspace_trusted = TrustPolicy().ensure_workspace_trusted(workspace_path).trusted
        task_run = self._state_store.create(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            session_id=session_id,
            user_goal=user_message,
            metadata={
                "runtime": "agent_runtime_v2",
                "phase": "stage_0_delegating",
                "employee_id": str(employee_id or "").strip(),
                "provider_id": str(provider_id or "").strip(),
                "model_name": str(model_name or "").strip(),
                "tools_count": len(tools or []),
                "prompt_version": str(prompt_version or "").strip(),
                "assistant_workflow": dict(assistant_workflow or {}),
                "capability_routing": dict(capability_routing or {}),
                "resume_context": self._build_resume_context(
                    tools=tools,
                    provider_id=provider_id,
                    model_name=model_name,
                    temperature=temperature,
                    role_ids=role_ids,
                    local_connector=local_connector,
                    local_connector_workspace_path=local_connector_workspace_path,
                    host_workspace_path=host_workspace_path,
                    local_connector_sandbox_mode=local_connector_sandbox_mode,
                    prompt_version=prompt_version,
                    assistant_workflow=assistant_workflow,
                    capability_routing=capability_routing,
                    workspace_trusted=workspace_trusted,
                    include_browser_tools=global_assistant_bridge_handler is not None,
                    browser_bridge_available=global_assistant_bridge_handler is not None,
                ),
            },
        )
        self._transcript_store.append(
            task_run.run_id,
            "user_message",
            {"content": str(user_message or "").strip()},
        )
        self._transcript_store.append(
            task_run.run_id,
            "initial_messages",
            {
                "messages": list(messages or [])
                if messages
                else [{"role": "user", "content": str(user_message or "").strip()}],
            },
        )
        self._event_log.append(
            task_run.run_id,
            "run_started",
            {
                "project_id": task_run.project_id,
                "chat_session_id": task_run.chat_session_id,
                "session_id": task_run.session_id,
                "phase": "v2_query_engine",
            },
        )
        yield {
            "type": "runtime_status",
            "runtime": "agent_runtime_v2",
            "run_id": task_run.run_id,
            "status": task_run.status,
        }
        async for item in self._run_query_engine(
            task_run=task_run,
            session_id=session_id,
            user_message=user_message,
            tools=tools,
            provider_id=provider_id,
            model_name=model_name,
            temperature=temperature,
            project_id=project_id,
            employee_id=employee_id,
            username=username,
            chat_session_id=chat_session_id,
            role_ids=role_ids,
            messages=messages,
            local_connector=local_connector,
            local_connector_workspace_path=local_connector_workspace_path,
            host_workspace_path=host_workspace_path,
            local_connector_sandbox_mode=local_connector_sandbox_mode,
            global_assistant_bridge_handler=global_assistant_bridge_handler,
            assistant_workflow=assistant_workflow,
        ):
            yield item

    async def _run_query_engine(
        self,
        *,
        task_run,
        session_id: str,
        user_message: str,
        tools: list[dict],
        provider_id: str,
        model_name: str,
        temperature: float,
        project_id: str,
        employee_id: str,
        username: str,
        chat_session_id: str,
        role_ids: list[str] | None,
        messages: list[dict] | None,
        local_connector: Any | None,
        local_connector_workspace_path: str,
        host_workspace_path: str,
        local_connector_sandbox_mode: str,
        global_assistant_bridge_handler: Any | None,
        assistant_workflow: dict[str, Any] | None,
    ) -> AsyncGenerator[dict, None]:
        llm_service = self._resolve_llm_service()
        if llm_service is None:
            self._state_store.append_event(
                task_run,
                "query_engine_unavailable",
                {"reason": "llm service is missing"},
                status="blocked",
            )
            yield {
                "type": "error",
                "message": "agent_runtime_v2 query engine unavailable: llm service is missing",
            }
            return
        tool_priority = []
        if isinstance(assistant_workflow, dict):
            raw_priority = assistant_workflow.get("tool_priority")
            if isinstance(raw_priority, list):
                tool_priority = [
                    str(item or "").strip()
                    for item in raw_priority
                    if str(item or "").strip()
                ]
        workspace_path = (
            str(host_workspace_path or "").strip()
            or str(local_connector_workspace_path or "").strip()
        )
        workspace_trusted = True
        if workspace_path:
            workspace_trusted = TrustPolicy().ensure_workspace_trusted(workspace_path).trusted
        tool_pool = DynamicToolPool.from_runtime_tools(
            tools,
            tool_priority=tool_priority,
            context=default_plugin_registry_context(
                workspace_path=workspace_path,
                workspace_trusted=workspace_trusted,
                include_browser_tools=global_assistant_bridge_handler is not None,
                browser_bridge_available=global_assistant_bridge_handler is not None,
            ),
        )
        tool_executor = self._resolve_tool_executor(
            project_id=project_id,
            employee_id=employee_id,
            username=username,
            chat_session_id=chat_session_id,
            role_ids=role_ids,
            allowed_tool_names=tool_pool.names(),
            local_connector=local_connector,
            local_connector_workspace_path=local_connector_workspace_path,
            host_workspace_path=host_workspace_path,
            local_connector_sandbox_mode=local_connector_sandbox_mode,
            global_assistant_bridge_handler=global_assistant_bridge_handler,
        )
        engine = QueryEngine(
            llm_step=LLMStep(llm_service),
            tool_runner=ToolExecutionRunner(
                tool_executor,
                event_log=self._event_log,
                permission_policy=PermissionPolicy(),
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                workspace_trusted=workspace_trusted,
                tool_entries=tool_pool.available_entries(),
            ),
            state_store=self._state_store,
            transcript_store=self._transcript_store,
            event_log=self._event_log,
        )
        run_messages = list(messages or [])
        if not run_messages:
            run_messages = [{"role": "user", "content": user_message}]
        completion_gate = self._completion_gate_inputs(user_message)
        result = await engine.run(
            task_run,
            messages=run_messages,
            tools=tools,
            provider_id=provider_id,
            model_name=model_name,
            temperature=temperature,
            **completion_gate,
        )
        yield {
            "type": "runtime_status",
            "runtime": "agent_runtime_v2",
            "run_id": result.task_run.run_id,
            "status": result.task_run.status,
            "mode": "query_engine",
            "tool_pool": tool_pool.summary(),
            "completion_decision": (
                result.completion_decision.to_dict()
                if result.completion_decision is not None
                else None
            ),
        }
        done_payload = {
            "type": "done",
            "content": result.final_content,
            "agent_runtime": result.to_dict(),
            "tool_pool": tool_pool.summary(),
        }
        waiting_reason = self._query_engine_waiting_reason(result)
        if waiting_reason:
            operation_payload = self._background_operation_payload_from_observations(
                result.observations,
            )
            if operation_payload:
                done_payload.update(
                    {
                        key: value
                        for key, value in operation_payload.items()
                        if value not in ("", None)
                    }
                )
            done_payload["completed_reason"] = waiting_reason
            done_payload["guard_reason"] = waiting_reason
            done_payload["guard_message"] = (
                result.final_content or "等待你授权工具调用后继续。"
            )
        elif str(result.task_run.status or "").strip() == "failed":
            failed_reason = self._query_engine_blocked_reason(result)
            if failed_reason == "missing_final_response_after_tool":
                fallback_content = self._fallback_content_from_observations(
                    result.observations,
                )
                done_payload["content"] = fallback_content or "工具执行已完成。"
                done_payload["completed_reason"] = "completed"
                done_payload["agent_runtime_fallback_reason"] = failed_reason
                done_payload["guard_reason"] = ""
                done_payload["guard_message"] = ""
            elif result.final_content:
                done_payload["completed_reason"] = failed_reason
                done_payload["guard_reason"] = failed_reason
                done_payload["guard_message"] = result.final_content
            else:
                done_payload["completed_reason"] = failed_reason
                done_payload["guard_reason"] = failed_reason
        elif str(result.task_run.status or "").strip() == "blocked":
            blocked_reason = self._query_engine_blocked_reason(result)
            done_payload["completed_reason"] = blocked_reason
            done_payload["guard_reason"] = blocked_reason
            done_payload["guard_message"] = (
                result.final_content or "运行任务已暂停，等待处理阻塞项。"
            )
        yield done_payload

    def _query_engine_waiting_reason(self, result: QueryEngineResult) -> str:
        status = str(result.task_run.status or "").strip()
        decision = result.completion_decision
        if status == "waiting_user":
            return "waiting_user_action"
        if decision is not None and decision.action == "request_user":
            return "waiting_user_action"
        return ""

    def _query_engine_blocked_reason(self, result: QueryEngineResult) -> str:
        decision = result.completion_decision
        if decision is not None:
            for reason in decision.reasons:
                normalized = str(reason or "").strip()
                if normalized:
                    return normalized
        return "blocked"
