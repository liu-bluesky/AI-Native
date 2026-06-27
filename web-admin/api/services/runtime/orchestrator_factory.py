"""Helpers for building v2 chat runtimes from runtime settings."""

from __future__ import annotations

from typing import Any

from services.agent_runtime.v2 import AgentTaskRuntime


def resolve_orchestrator_runtime_settings(
    runtime_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    return {}


def should_enable_agent_runtime_v2(runtime_settings: dict[str, Any] | None) -> bool:
    """Return whether the v2 runtime is enabled.

    Stage 6 removes the v1 implementation. The old runtime_settings/env
    switches remain accepted for configuration compatibility, but they can no
    longer disable the v2 runtime.
    """

    return True


def build_agent_orchestrator(
    llm_service: Any,
    conversation_manager: Any,
    runtime_settings: dict[str, Any] | None,
    *,
    orchestrator_cls: Any | None = None,
) -> AgentTaskRuntime:
    should_enable_agent_runtime_v2(runtime_settings)
    return AgentTaskRuntime(
        llm_service=llm_service,
        conversation_manager=conversation_manager,
        runtime_options=resolve_orchestrator_runtime_settings(runtime_settings),
    )
