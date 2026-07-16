"""Retired backend agent runtime boundary."""

from __future__ import annotations

from typing import Any



class BackendAgentRuntimeRetiredError(RuntimeError):
    """Raised when a removed backend orchestration path is invoked."""


def build_agent_orchestrator(
    llm_service: Any,
    conversation_manager: Any,
    runtime_settings: dict[str, Any] | None,
    *,
    orchestrator_cls: Any | None = None,
) -> Any:
    del llm_service, conversation_manager, runtime_settings, orchestrator_cls
    raise BackendAgentRuntimeRetiredError(
        "Backend agent runtime has been removed; use the desktop liuagent runtime."
    )
