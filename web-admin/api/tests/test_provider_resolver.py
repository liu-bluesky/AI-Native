import pytest
from fastapi import HTTPException

from services.runtime import provider_resolver


class _FakeProviderService:
    def __init__(self, providers):
        self.providers = providers

    def list_providers(
        self,
        enabled_only=False,
        *,
        owner_username="",
        include_all=False,
        include_shared=False,
    ):
        return list(self.providers)


@pytest.mark.asyncio
async def test_resolve_provider_runtime_uses_requested_provider(monkeypatch):
    monkeypatch.setattr(
        provider_resolver.llm_provider_service,
        "get_llm_provider_service",
        lambda: _FakeProviderService(
            [
                {
                    "id": "provider-default",
                    "default_model": "default-model",
                    "models": ["default-model"],
                    "is_default": True,
                    "enabled": True,
                },
                {
                    "id": "provider-picked",
                    "default_model": "solver-v2",
                    "models": ["solver-v2"],
                    "is_default": False,
                    "enabled": True,
                },
            ]
        ),
    )

    runtime = await provider_resolver.resolve_provider_runtime(
        "provider-picked",
        {"sub": "tester", "role": "admin"},
        resolve_local_connector=lambda connector_id: None,
    )
    runtime = provider_resolver.finalize_resolved_provider_runtime(
        runtime,
        missing_model_message="model_name is required",
    )

    assert runtime.provider_mode == "provider"
    assert runtime.provider_id == "provider-picked"
    assert runtime.model_name == "solver-v2"
    assert runtime.source == "requested_provider"


@pytest.mark.asyncio
async def test_resolve_provider_runtime_supports_local_connector(monkeypatch):
    connector = type(
        "Connector",
        (),
        {
            "id": "connector-a",
            "connector_name": "本地机",
            "owner_username": "tester",
            "advertised_url": "http://localhost:8765",
            "connector_token": "",
        },
    )()

    async def _fake_list_connector_llm_models(item):
        assert item is connector
        return {
            "enabled": True,
            "default_model": "qwen-coder",
            "models": ["qwen-coder", "glm-4.7"],
        }

    monkeypatch.setattr(
        provider_resolver,
        "list_connector_llm_models",
        _fake_list_connector_llm_models,
    )

    runtime = await provider_resolver.resolve_provider_runtime(
        "local-connector:connector-a",
        {"sub": "tester", "role": "admin"},
        resolve_local_connector=lambda connector_id: connector if connector_id == "connector-a" else None,
    )
    runtime = provider_resolver.finalize_resolved_provider_runtime(
        runtime,
        missing_model_message="model_name is required",
    )

    assert runtime.provider_mode == "local_connector"
    assert runtime.connector_id == "connector-a"
    assert runtime.provider_id == "local-connector:connector-a"
    assert runtime.model_name == "qwen-coder"
    assert runtime.provider["models"] == ["qwen-coder", "glm-4.7"]


def test_finalize_resolved_provider_runtime_uses_fallback_model_name():
    runtime = provider_resolver.ResolvedProviderRuntime(
        provider_mode="provider",
        provider={"id": "provider-a", "default_model": "", "models": []},
        providers=[],
        provider_id="provider-a",
    )

    finalized = provider_resolver.finalize_resolved_provider_runtime(
        runtime,
        "",
        "fallback-model",
        missing_model_message="未找到可用模型",
    )

    assert finalized.model_name == "fallback-model"


def test_finalize_resolved_provider_runtime_rejects_missing_model():
    runtime = provider_resolver.ResolvedProviderRuntime(
        provider_mode="provider",
        provider={"id": "provider-a", "default_model": "", "models": []},
        providers=[],
        provider_id="provider-a",
    )

    with pytest.raises(HTTPException) as exc_info:
        provider_resolver.finalize_resolved_provider_runtime(
            runtime,
            missing_model_message="未找到可用模型",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "未找到可用模型"
