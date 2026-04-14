from unittest.mock import MagicMock

from services.runtime.orchestrator_factory import (
    build_agent_orchestrator,
    resolve_orchestrator_runtime_settings,
)


def test_resolve_orchestrator_runtime_settings_uses_runtime_values():
    settings = resolve_orchestrator_runtime_settings(
        {
            "max_loop_rounds": 11,
            "max_tool_rounds": 7,
            "repeated_tool_call_threshold": 4,
            "tool_only_threshold": 5,
            "tool_budget_strategy": "stop",
            "max_tool_calls_per_round": 8,
            "tool_timeout_sec": 90,
            "tool_retry_count": 2,
        }
    )

    assert settings == {
        "max_loops": 11,
        "max_tool_rounds": 7,
        "repeated_tool_call_threshold": 4,
        "tool_only_threshold": 5,
        "tool_budget_strategy": "stop",
        "max_tool_calls_per_round": 8,
        "tool_timeout_sec": 90,
        "tool_retry_count": 2,
    }


def test_build_agent_orchestrator_applies_runtime_settings():
    orchestrator = build_agent_orchestrator(
        MagicMock(),
        MagicMock(),
        {
            "max_loop_rounds": 9,
            "max_tool_rounds": 4,
            "repeated_tool_call_threshold": 3,
            "tool_only_threshold": 4,
            "tool_budget_strategy": "stop",
            "max_tool_calls_per_round": 5,
            "tool_timeout_sec": 33,
            "tool_retry_count": 1,
        },
    )

    assert orchestrator._max_loops == 9
    assert orchestrator._max_tool_rounds == 4
    assert orchestrator._repeated_tool_call_threshold == 3
    assert orchestrator._tool_only_threshold == 4
    assert orchestrator._tool_budget_strategy == "stop"
    assert orchestrator._max_tool_calls_per_round == 5
    assert orchestrator._tool_timeout_sec == 33
    assert orchestrator._tool_retry_count == 1
