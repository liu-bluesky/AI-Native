"""Helpers for building chat orchestrators from runtime settings."""

from __future__ import annotations

import os
from typing import Any

from services.agent_orchestrator import AgentOrchestrator
from services.agent_runtime_v2 import AgentTaskRuntime


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


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def should_enable_agent_runtime_v2(runtime_settings: dict[str, Any] | None) -> bool:
    source = runtime_settings if isinstance(runtime_settings, dict) else {}
    env_enabled = _coerce_bool(os.environ.get("AGENT_RUNTIME_V2_ENABLED", ""), True)
    return _coerce_bool(source.get("agent_runtime_enabled"), env_enabled)


def build_agent_orchestrator(
    llm_service: Any,
    conversation_manager: Any,
    runtime_settings: dict[str, Any] | None,
    *,
    orchestrator_cls: type[AgentOrchestrator] = AgentOrchestrator,
) -> Any:
    legacy_orchestrator = orchestrator_cls(
        llm_service,
        conversation_manager,
        **resolve_orchestrator_runtime_settings(runtime_settings),
    )
    if should_enable_agent_runtime_v2(runtime_settings):
        return AgentTaskRuntime(legacy_orchestrator)
    return legacy_orchestrator
