"""Minimal runtime context builders."""

from __future__ import annotations

from typing import Any

from services.runtime.provider_resolver import ResolvedProviderRuntime
from services.runtime.runtime_types import ChatRuntimeContext


def build_chat_runtime_context(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    employee_id: str = "",
    selected_employee_ids: list[str] | None = None,
    workspace_path: str = "",
    skill_resource_directory: str = "",
    chat_surface: str = "main-chat",
    history: list[dict] | None = None,
    images: list[str] | None = None,
    task_tree_payload: dict[str, Any] | None = None,
    task_tree_prompt: str = "",
    task_tree_health: dict[str, Any] | None = None,
    feedback_signals: dict[str, Any] | None = None,
    chat_settings: dict[str, Any] | None = None,
    resolved_provider: ResolvedProviderRuntime | None = None,
    tools: list[dict[str, Any]] | None = None,
    messages: list[dict[str, Any]] | None = None,
    runtime_snapshot: dict[str, Any] | None = None,
    local_connector: Any | None = None,
    local_connector_sandbox_mode: str = "workspace-write",
    metadata: dict[str, Any] | None = None,
) -> ChatRuntimeContext:
    return ChatRuntimeContext(
        project_id=str(project_id or "").strip(),
        username=str(username or "").strip(),
        chat_session_id=str(chat_session_id or "").strip(),
        employee_id=str(employee_id or "").strip(),
        selected_employee_ids=tuple(
            str(item or "").strip()
            for item in (selected_employee_ids or [])
            if str(item or "").strip()
        ),
        workspace_path=str(workspace_path or "").strip(),
        skill_resource_directory=str(skill_resource_directory or "").strip(),
        chat_surface=str(chat_surface or "main-chat").strip() or "main-chat",
        history=list(history or []),
        images=[str(item or "").strip() for item in (images or []) if str(item or "").strip()],
        task_tree_payload=task_tree_payload if isinstance(task_tree_payload, dict) else None,
        task_tree_prompt=str(task_tree_prompt or "").strip(),
        task_tree_health=task_tree_health if isinstance(task_tree_health, dict) else None,
        feedback_signals=feedback_signals if isinstance(feedback_signals, dict) else None,
        chat_settings=dict(chat_settings or {}),
        resolved_provider=resolved_provider,
        resolved_tools=tuple(dict(item) for item in (tools or [])),
        resolved_messages=tuple(dict(item) for item in (messages or [])),
        runtime_snapshot=runtime_snapshot if isinstance(runtime_snapshot, dict) else None,
        local_connector=local_connector,
        local_connector_sandbox_mode=str(local_connector_sandbox_mode or "workspace-write").strip()
        or "workspace-write",
        metadata=dict(metadata or {}),
    )
