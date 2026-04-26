"""Helpers for building AgentOrchestrator.run kwargs."""

from __future__ import annotations

from typing import Any

from services.runtime.runtime_context import runtime_messages, runtime_tools
from services.runtime.runtime_types import ChatRuntimeContext


def build_orchestrator_run_kwargs(
    *,
    session_id: str,
    user_message: str,
    runtime_context: ChatRuntimeContext,
    temperature: float,
    max_tokens: int,
    cancel_event: Any,
    role_ids: list[str] | None = None,
    global_assistant_bridge_handler: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": session_id,
        "user_message": user_message,
        "tools": runtime_tools(runtime_context),
        "provider_id": runtime_context.provider_id,
        "model_name": runtime_context.model_name,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "project_id": runtime_context.project_id,
        "employee_id": runtime_context.employee_id,
        "username": runtime_context.username,
        "chat_session_id": runtime_context.chat_session_id,
        "cancel_event": cancel_event,
        "messages": runtime_messages(runtime_context),
        "local_connector": runtime_context.local_connector,
        "local_connector_workspace_path": runtime_context.workspace_path,
        "host_workspace_path": runtime_context.host_workspace_path or runtime_context.workspace_path,
        "local_connector_sandbox_mode": runtime_context.local_connector_sandbox_mode,
    }
    if role_ids is not None:
        payload["role_ids"] = list(role_ids)
    if global_assistant_bridge_handler is not None:
        payload["global_assistant_bridge_handler"] = global_assistant_bridge_handler
    payload["prompt_version"] = str((runtime_context.metadata or {}).get("prompt_version") or "").strip()
    return payload
