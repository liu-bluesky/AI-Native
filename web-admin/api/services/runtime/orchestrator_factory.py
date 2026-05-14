"""Helpers for building chat orchestrators from runtime settings."""

from __future__ import annotations

from typing import Any

from services.agent_orchestrator import AgentOrchestrator


def _resolve_runtime_int(
    source: dict[str, Any],
    key: str,
    default: int,
) -> int:
    value = source.get(key)
    if value is None:
      return default
    try:
      return int(value)
    except (TypeError, ValueError):
      return default


def resolve_orchestrator_runtime_settings(
    runtime_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    source = runtime_settings if isinstance(runtime_settings, dict) else {}
    return {
        "max_loops": _resolve_runtime_int(source, "max_loop_rounds", 20),
        "max_tool_rounds": _resolve_runtime_int(source, "max_tool_rounds", 6),
        "repeated_tool_call_threshold": _resolve_runtime_int(
            source, "repeated_tool_call_threshold", 2
        ),
        "tool_only_threshold": _resolve_runtime_int(source, "tool_only_threshold", 3),
        "tool_budget_strategy": str(source.get("tool_budget_strategy") or "finalize"),
        "max_tool_calls_per_round": _resolve_runtime_int(
            source, "max_tool_calls_per_round", 6
        ),
        "tool_timeout_sec": _resolve_runtime_int(source, "tool_timeout_sec", 0),
        "tool_retry_count": _resolve_runtime_int(source, "tool_retry_count", 0),
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
