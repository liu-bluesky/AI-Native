"""Shared resume entrypoints for agent_runtime_v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from services.agent_runtime.v2.operation_resume import (
    OperationResumeCoordinator,
    ResumeOperationResult,
)
from services.agent_runtime.v2.run_inspector import AgentRuntimeInspector
from services.tool_executor import ToolExecutor


ResolveLocalConnector = Callable[[str], Any | None]
ResolveLLMService = Callable[[dict[str, Any]], Awaitable[Any | None]]


@dataclass
class AgentRuntimeResumeRequest:
    project_id: str
    username: str
    run_id: str
    call_id: str
    tool_name: str
    chat_session_id: str = ""
    employee_id: str = ""
    role_ids: list[str] | None = None
    project_workspace_path: str = ""
    workspace_trusted: bool = True


class AgentRuntimeResumeService:
    def __init__(
        self,
        *,
        inspector: AgentRuntimeInspector | None = None,
        coordinator: OperationResumeCoordinator | None = None,
        resolve_local_connector: ResolveLocalConnector | None = None,
        resolve_llm_service: ResolveLLMService | None = None,
    ):
        self._inspector = inspector or AgentRuntimeInspector()
        self._coordinator = coordinator or OperationResumeCoordinator()
        self._resolve_local_connector = resolve_local_connector
        self._resolve_llm_service = resolve_llm_service

    async def resume_permission_tool_call(
        self,
        request: AgentRuntimeResumeRequest,
    ) -> ResumeOperationResult:
        snapshot = self._inspector.get_run_snapshot(request.run_id)
        if snapshot is None:
            return ResumeOperationResult(
                run_id=request.run_id,
                status="not_found",
                resumed=False,
                reason="task_run_not_found",
            )
        run = dict(snapshot.get("run") or {})
        if run.get("project_id") != request.project_id or run.get("username") != request.username:
            return ResumeOperationResult(
                run_id=request.run_id,
                status=str(run.get("status") or "not_found"),
                resumed=False,
                reason="task_run_not_found",
            )
        metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
        resume_context = (
            metadata.get("resume_context")
            if isinstance(metadata.get("resume_context"), dict)
            else {}
        )
        resume_context = dict(resume_context or {})
        resume_tools = self._resume_tools(resume_context, request.tool_name)
        resume_tool_names = self._tool_names(resume_tools)
        connector = None
        connector_id = str(resume_context.get("local_connector_id") or "").strip()
        if connector_id and self._resolve_local_connector is not None:
            connector = self._resolve_local_connector(connector_id)
        llm_service = None
        if self._resolve_llm_service is not None:
            llm_service = await self._resolve_llm_service(resume_context)
        chat_session_id = (
            str(request.chat_session_id or "").strip()
            or str(run.get("chat_session_id") or "").strip()
        )
        employee_id = (
            str(request.employee_id or "").strip()
            or str(metadata.get("employee_id") or "").strip()
        )
        tool_executor = ToolExecutor(
            request.project_id,
            employee_id=employee_id,
            username=request.username,
            chat_session_id=chat_session_id,
            role_ids=list(request.role_ids or []),
            allowed_tool_names=resume_tool_names,
            local_connector=connector,
            local_connector_workspace_path=str(
                resume_context.get("local_connector_workspace_path") or ""
            ).strip(),
            host_workspace_path=(
                str(resume_context.get("host_workspace_path") or "").strip()
                or str(request.project_workspace_path or "").strip()
            ),
            local_connector_sandbox_mode=str(
                resume_context.get("local_connector_sandbox_mode") or "workspace-write"
            ).strip()
            or "workspace-write",
        )
        return await self._coordinator.resume_permission_action(
            run_id=request.run_id,
            call_id=request.call_id,
            tool_name=request.tool_name,
            tool_executor=tool_executor,
            project_id=request.project_id,
            username=request.username,
            chat_session_id=chat_session_id,
            workspace_trusted=request.workspace_trusted,
            llm_service=llm_service,
            tools=resume_tools,
            provider_id=str(resume_context.get("provider_id") or "").strip(),
            model_name=str(resume_context.get("model_name") or "").strip(),
            temperature=self._coerce_float(resume_context.get("temperature"), 0.2),
        )

    async def resume_background_operation(
        self,
        request: AgentRuntimeResumeRequest,
        *,
        operation_task: dict[str, Any],
    ) -> ResumeOperationResult:
        snapshot = self._inspector.get_run_snapshot(request.run_id)
        if snapshot is None:
            return ResumeOperationResult(
                run_id=request.run_id,
                status="not_found",
                resumed=False,
                reason="task_run_not_found",
            )
        run = dict(snapshot.get("run") or {})
        if run.get("project_id") != request.project_id or run.get("username") != request.username:
            return ResumeOperationResult(
                run_id=request.run_id,
                status=str(run.get("status") or "not_found"),
                resumed=False,
                reason="task_run_not_found",
            )
        metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
        resume_context = (
            metadata.get("resume_context")
            if isinstance(metadata.get("resume_context"), dict)
            else {}
        )
        resume_context = dict(resume_context or {})
        resume_tools = self._resume_tools(resume_context, request.tool_name)
        resume_tool_names = self._tool_names(resume_tools)
        connector = None
        connector_id = str(resume_context.get("local_connector_id") or "").strip()
        if connector_id and self._resolve_local_connector is not None:
            connector = self._resolve_local_connector(connector_id)
        llm_service = None
        if self._resolve_llm_service is not None:
            llm_service = await self._resolve_llm_service(resume_context)
        chat_session_id = (
            str(request.chat_session_id or "").strip()
            or str(run.get("chat_session_id") or "").strip()
        )
        employee_id = (
            str(request.employee_id or "").strip()
            or str(metadata.get("employee_id") or "").strip()
        )
        tool_executor = ToolExecutor(
            request.project_id,
            employee_id=employee_id,
            username=request.username,
            chat_session_id=chat_session_id,
            role_ids=list(request.role_ids or []),
            allowed_tool_names=resume_tool_names,
            local_connector=connector,
            local_connector_workspace_path=str(
                resume_context.get("local_connector_workspace_path") or ""
            ).strip(),
            host_workspace_path=(
                str(resume_context.get("host_workspace_path") or "").strip()
                or str(request.project_workspace_path or "").strip()
            ),
            local_connector_sandbox_mode=str(
                resume_context.get("local_connector_sandbox_mode") or "workspace-write"
            ).strip()
            or "workspace-write",
        )
        return await self._coordinator.resume_background_operation(
            run_id=request.run_id,
            tool_executor=tool_executor,
            operation_task=dict(operation_task or {}),
            project_id=request.project_id,
            username=request.username,
            chat_session_id=chat_session_id,
            workspace_trusted=request.workspace_trusted,
            llm_service=llm_service,
            tools=resume_tools,
            provider_id=str(resume_context.get("provider_id") or "").strip(),
            model_name=str(resume_context.get("model_name") or "").strip(),
            temperature=self._coerce_float(resume_context.get("temperature"), 0.2),
        )

    def _resume_tools(
        self,
        resume_context: dict[str, Any],
        fallback_tool_name: str,
    ) -> list[dict[str, Any]]:
        tools = resume_context.get("tools") if isinstance(resume_context, dict) else []
        normalized = [dict(item) for item in (tools or []) if isinstance(item, dict)]
        if normalized:
            return normalized
        fallback = str(fallback_tool_name or "").strip()
        return [{"tool_name": fallback}] if fallback else []

    def _tool_names(self, tools: list[dict[str, Any]]) -> list[str]:
        names: list[str] = []
        for item in tools or []:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name") or item.get("name") or "").strip()
            if tool_name and tool_name not in names:
                names.append(tool_name)
        return names

    def _coerce_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _coerce_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
