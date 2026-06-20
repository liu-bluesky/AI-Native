from unittest.mock import MagicMock

from services.runtime.orchestrator_factory import (
    build_agent_orchestrator,
    resolve_orchestrator_runtime_settings,
    should_enable_agent_runtime_v2,
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
            "max_tool_calls_total": 13,
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
        "max_tool_calls_total": 13,
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
            "max_tool_calls_total": 12,
            "tool_timeout_sec": 33,
            "tool_retry_count": 1,
            "agent_runtime_enabled": False,
        },
    )

    assert orchestrator._runtime_options["max_loops"] == 9
    assert orchestrator._runtime_options["max_tool_rounds"] == 4
    assert orchestrator._runtime_options["repeated_tool_call_threshold"] == 3
    assert orchestrator._runtime_options["tool_only_threshold"] == 4
    assert orchestrator._runtime_options["tool_budget_strategy"] == "stop"
    assert orchestrator._runtime_options["max_tool_calls_per_round"] == 5
    assert orchestrator._runtime_options["max_tool_calls_total"] == 12
    assert orchestrator._runtime_options["tool_timeout_sec"] == 33
    assert orchestrator._runtime_options["tool_retry_count"] == 1


def test_resolve_orchestrator_runtime_settings_preserves_zero_timeout():
    settings = resolve_orchestrator_runtime_settings(
        {
            "tool_timeout_sec": 0,
            "tool_retry_count": 0,
        }
    )

    assert settings["tool_timeout_sec"] == 0
    assert settings["tool_retry_count"] == 0


def test_should_enable_agent_runtime_v2_defaults_to_true(monkeypatch):
    monkeypatch.delenv("AGENT_RUNTIME_V2_ENABLED", raising=False)

    assert should_enable_agent_runtime_v2({}) is True


def test_should_enable_agent_runtime_v2_ignores_explicit_disable(monkeypatch):
    monkeypatch.delenv("AGENT_RUNTIME_V2_ENABLED", raising=False)

    assert should_enable_agent_runtime_v2({"agent_runtime_enabled": False}) is True


def test_should_enable_agent_runtime_v2_supports_chat_setting(monkeypatch):
    monkeypatch.delenv("AGENT_RUNTIME_V2_ENABLED", raising=False)

    assert should_enable_agent_runtime_v2({"agent_runtime_enabled": True}) is True


def test_build_agent_orchestrator_uses_v2_wrapper_when_enabled():
    llm_service = MagicMock()
    conversation_manager = MagicMock()
    orchestrator = build_agent_orchestrator(
        llm_service,
        conversation_manager,
        {},
    )

    from services.agent_runtime.v2 import AgentTaskRuntime

    assert isinstance(orchestrator, AgentTaskRuntime)
    assert orchestrator._llm_service is llm_service
    assert orchestrator._conversation_manager is conversation_manager


def test_build_agent_orchestrator_ignores_removed_legacy_class_argument():
    calls = []

    class _RemovedOrchestrator:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

    orchestrator = build_agent_orchestrator(
        MagicMock(),
        MagicMock(),
        {"agent_runtime_enabled": True},
        orchestrator_cls=_RemovedOrchestrator,
    )

    from services.agent_runtime.v2 import AgentTaskRuntime

    assert isinstance(orchestrator, AgentTaskRuntime)
    assert calls == []


def test_agent_runtime_namespace_exposes_v2_entrypoint():
    from services.agent_runtime.v2 import AgentTaskRuntime

    assert AgentTaskRuntime.__name__ == "AgentTaskRuntime"
