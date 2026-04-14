"""Shared runtime helpers for provider/model resolution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from fastapi import HTTPException

from core.deps import is_admin_like
from services.llm_model_type_catalog import DEFAULT_MODEL_TYPE
from services import llm_provider_service
from services.local_connector_service import (
    LocalConnectorLlmAdapter,
    build_local_connector_provider_id,
    connector_base_url,
    list_connector_llm_models,
    parse_local_connector_provider_id,
)


@dataclass(frozen=True)
class ResolvedProviderRuntime:
    provider_mode: str
    provider: dict[str, Any]
    providers: list[dict[str, Any]]
    provider_id: str
    model_name: str = ""
    connector_id: str = ""
    source: str = ""


def list_visible_chat_providers(
    auth_payload: dict[str, Any],
    *,
    include_all_providers: bool = False,
) -> list[dict[str, Any]]:
    llm_service = llm_provider_service.get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=include_all_providers or is_admin_like(auth_payload),
        include_shared=True,
    )
    return list(providers or [])


def pick_provider_from_candidates(
    provider_id: str,
    providers: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    visible_providers = list(providers or [])
    if not visible_providers:
        raise HTTPException(400, "未配置可用的 LLM 提供商")
    expected = str(provider_id or "").strip()
    if expected:
        selected = next(
            (item for item in visible_providers if str(item.get("id") or "").strip() == expected),
            None,
        )
        if selected is None:
            raise HTTPException(404, f"LLM provider not found: {expected}")
        return selected, visible_providers, "requested_provider"
    default_provider = next(
        (item for item in visible_providers if bool(item.get("is_default"))),
        visible_providers[0],
    )
    return default_provider, visible_providers, "default_provider"


def resolve_provider_model_name(provider: dict[str, Any], *candidates: str) -> str:
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if normalized:
            return normalized
    default_model = str(provider.get("default_model") or "").strip()
    if default_model:
        return default_model
    models = provider.get("models") or []
    return str(models[0] or "").strip() if models else ""


async def build_connector_chat_provider(connector: Any) -> dict[str, Any] | None:
    connector_id = str(getattr(connector, "id", "") or "").strip()
    base_url = connector_base_url(connector)
    if not connector_id or not base_url:
        return None
    try:
        llm_info = await list_connector_llm_models(connector)
    except Exception:
        llm_info = {
            "enabled": False,
            "default_model": "",
            "models": [],
        }
    if not bool(llm_info.get("enabled")):
        return None
    models = [
        str(item or "").strip()
        for item in (llm_info.get("models") or [])
        if str(item or "").strip()
    ]
    default_model = str(llm_info.get("default_model") or "").strip()
    if default_model and default_model not in models:
        models = [default_model, *models]
    if not models:
        return None
    connector_name = str(getattr(connector, "connector_name", "") or "").strip() or connector_id
    connector_owner = str(getattr(connector, "owner_username", "") or "").strip()
    provider_name = (
        f"本地连接器 · {connector_name} · {connector_owner}"
        if connector_owner
        else f"本地连接器 · {connector_name}"
    )
    return {
        "id": build_local_connector_provider_id(connector_id),
        "name": provider_name,
        "provider_type": "local-connector",
        "base_url": base_url,
        "models": models,
        "model_configs": [
            {
                "name": model_name,
                "model_type": DEFAULT_MODEL_TYPE,
            }
            for model_name in models
        ],
        "default_model": default_model or models[0],
        "enabled": True,
        "is_default": False,
        "connector_id": connector_id,
        "connector_name": connector_name,
        "connector_owner_username": connector_owner,
    }


async def resolve_provider_runtime(
    provider_id: str,
    auth_payload: dict[str, Any],
    *,
    resolve_local_connector: Callable[[str], Any | None],
    include_all_providers: bool = False,
) -> ResolvedProviderRuntime:
    connector_id = parse_local_connector_provider_id(provider_id)
    if connector_id:
        connector = resolve_local_connector(connector_id)
        if connector is None:
            raise HTTPException(404, "Local connector not found")
        provider = await build_connector_chat_provider(connector)
        if provider is None:
            raise HTTPException(400, "当前本地连接器未配置可用模型")
        provider_id = str(provider.get("id") or "").strip()
        return ResolvedProviderRuntime(
            provider_mode="local_connector",
            provider=provider,
            providers=[provider],
            provider_id=provider_id,
            connector_id=connector_id,
            source="local_connector",
        )
    selected_provider, providers, source = pick_provider_from_candidates(
        provider_id,
        list_visible_chat_providers(
            auth_payload,
            include_all_providers=include_all_providers,
        ),
    )
    resolved_provider_id = str(selected_provider.get("id") or "").strip()
    return ResolvedProviderRuntime(
        provider_mode="provider",
        provider=selected_provider,
        providers=providers,
        provider_id=resolved_provider_id,
        source=source,
    )


def finalize_resolved_provider_runtime(
    runtime: ResolvedProviderRuntime,
    *model_candidates: str,
    missing_model_message: str = "",
) -> ResolvedProviderRuntime:
    model_name = resolve_provider_model_name(runtime.provider, *model_candidates)
    if missing_model_message and not model_name:
        raise HTTPException(400, missing_model_message)
    return replace(runtime, model_name=model_name)


def resolve_runtime_llm_service(
    base_llm_service: Any,
    runtime: ResolvedProviderRuntime,
    *,
    resolve_local_connector: Callable[[str], Any | None],
) -> Any:
    if runtime.provider_mode != "local_connector":
        return base_llm_service
    connector = resolve_local_connector(runtime.connector_id)
    if connector is None:
        raise HTTPException(404, "Local connector not found")
    return LocalConnectorLlmAdapter(connector)
