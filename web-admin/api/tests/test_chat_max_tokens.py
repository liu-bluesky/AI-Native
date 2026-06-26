from routers import projects


def test_project_chat_max_tokens_are_not_capped_at_legacy_limit(monkeypatch):
    class Cfg:
        chat_max_tokens = 12000

    monkeypatch.setattr(projects.system_config_store, "get_global", lambda: Cfg())

    assert projects._resolve_chat_max_tokens(None) == 12000
    assert projects._resolve_chat_max_tokens(16000) == 16000
    assert projects._resolve_chat_max_tokens(64) == 128


def test_project_chat_settings_preserve_high_max_tokens():
    settings = projects._normalize_project_chat_settings({"max_tokens": 12000})

    assert settings["max_tokens"] == 12000

