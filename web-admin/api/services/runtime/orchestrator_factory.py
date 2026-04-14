"""Helpers for building chat orchestrators from runtime settings."""

from __future__ import annotations

from typing import Any

from services.agent_orchestrator import AgentOrchestrator


def resolve_orchestrator_runtime_settings(
    runtime_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    source = runtime_settings if isinstance(runtime_settings, dict) else {}
    return {
        "max_loops": int(source.get("max_loop_rounds") or 20),
        "max_tool_rounds": int(source.get("max_tool_rounds") or 6),
        "repeated_tool_call_threshold": int(
            source.get("repeated_tool_call_threshold") or 2
        ),
        "tool_only_threshold": int(source.get("tool_only_threshold") or 3),
        "tool_budget_strategy": str(source.get("tool_budget_strategy") or "finalize"),
        "max_tool_calls_per_round": int(source.get("max_tool_calls_per_round") or 6),
        "tool_timeout_sec": int(source.get("tool_timeout_sec") or 60),
        "tool_retry_count": int(source.get("tool_retry_count") or 0),
    }


def build_agent_orchestrator(
    llm_service: Any,
    conversation_manager: Any,
    runtime_settings: dict[str, Any] | None,
    *,
    orchestrator_cls: type[AgentOrchestrator] = AgentOrchestrator,
) -> AgentOrchestrator:
    return orchestrator_cls(
        llm_service,
        conversation_manager,
        **resolve_orchestrator_runtime_settings(runtime_settings),
    )
