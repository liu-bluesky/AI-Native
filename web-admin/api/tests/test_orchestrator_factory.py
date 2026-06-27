from unittest.mock import MagicMock

from services.runtime.orchestrator_factory import (
    build_agent_orchestrator,
    resolve_orchestrator_runtime_settings,
    should_enable_agent_runtime_v2,
)


def test_resolve_orchestrator_runtime_settings_ignores_budget_guard_values():
    settings = resolve_orchestrator_runtime_settings({"agent_runtime_enabled": False})

    assert settings == {}


def test_build_agent_orchestrator_applies_runtime_settings():
    orchestrator = build_agent_orchestrator(
        MagicMock(),
        MagicMock(),
        {"agent_runtime_enabled": False},
    )

    assert orchestrator._runtime_options == {}


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
