from core import config


def test_backend_agent_runtime_new_runs_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BACKEND_AGENT_RUNTIME_NEW_RUNS_ENABLED", raising=False)
    monkeypatch.setattr(config, "_file_env_values", lambda: {})
    config.get_settings.cache_clear()
    try:
        assert config.get_settings().backend_agent_runtime_new_runs_enabled is False
    finally:
        config.get_settings.cache_clear()


def test_backend_agent_runtime_new_runs_can_be_enabled_for_rollback(monkeypatch):
    monkeypatch.setenv("BACKEND_AGENT_RUNTIME_NEW_RUNS_ENABLED", "true")
    monkeypatch.setattr(config, "_file_env_values", lambda: {})
    config.get_settings.cache_clear()
    try:
        assert config.get_settings().backend_agent_runtime_new_runs_enabled is True
    finally:
        config.get_settings.cache_clear()
