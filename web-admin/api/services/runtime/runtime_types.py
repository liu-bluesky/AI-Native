"""Shared runtime datatypes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.runtime.provider_resolver import ResolvedProviderRuntime


@dataclass
class ChatRuntimeContext:
    project_id: str
    username: str
    chat_session_id: str
    employee_id: str = ""
    selected_employee_ids: tuple[str, ...] = ()
    workspace_path: str = ""
    skill_resource_directory: str = ""
    chat_surface: str = "main-chat"
    history: list[dict[str, Any]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    task_tree_payload: dict[str, Any] | None = None
    task_tree_prompt: str = ""
    task_tree_health: dict[str, Any] | None = None
    feedback_signals: dict[str, Any] | None = None
    chat_settings: dict[str, Any] = field(default_factory=dict)
    resolved_provider: ResolvedProviderRuntime | None = None
    resolved_tools: tuple[dict[str, Any], ...] = ()
    resolved_messages: tuple[dict[str, Any], ...] = ()
    runtime_snapshot: dict[str, Any] | None = None
    local_connector: Any | None = None
    local_connector_sandbox_mode: str = "workspace-write"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def provider_id(self) -> str:
        return str((self.resolved_provider or {}).provider_id if self.resolved_provider else "").strip()

    @property
    def model_name(self) -> str:
        return str((self.resolved_provider or {}).model_name if self.resolved_provider else "").strip()

