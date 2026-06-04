"""Shared bot connector persistence helpers."""

from __future__ import annotations

from stores.factory import bot_connector_store, system_config_store
from stores.json.system_config_store import normalize_bot_platform_connectors


def list_bot_connectors() -> list[dict[str, object]]:
    items = normalize_bot_platform_connectors(bot_connector_store.list_all())
    if items:
        return items
    legacy_items = normalize_bot_platform_connectors(
        getattr(system_config_store.get_global(), "bot_platform_connectors", [])
    )
    if legacy_items:
        bot_connector_store.replace_all(legacy_items)
    return legacy_items


def replace_bot_connectors(items: object) -> list[dict[str, object]]:
    normalized = normalize_bot_platform_connectors(items)
    bot_connector_store.replace_all(normalized)
    return normalized


def get_bot_connector(connector_id: str) -> dict[str, object] | None:
    normalized_id = str(connector_id or "").strip().lower()
    if not normalized_id:
        return None
    for item in list_bot_connectors():
        if str(item.get("id") or "").strip().lower() == normalized_id:
            return dict(item)
    return None
