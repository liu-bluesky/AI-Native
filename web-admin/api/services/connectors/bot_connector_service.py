"""Shared bot connector persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_bot_connector(connector_id: str) -> dict[str, object] | None:
    normalized_id = str(connector_id or "").strip().lower()
    if not normalized_id:
        return None
    for item in list_bot_connectors():
        if str(item.get("id") or "").strip().lower() == normalized_id:
            return dict(item)
    return None


def _save_bot_connector_scanned_chats(connector_id: str, items: list[dict[str, Any]]) -> None:
    normalized_id = str(connector_id or "").strip().lower()
    if not normalized_id:
        return
    scanned_at = _now_iso()
    connectors = list_bot_connectors()
    updated: list[dict[str, object]] = []
    changed = False
    for raw in connectors:
        connector = dict(raw or {})
        if str(connector.get("id") or "").strip().lower() == normalized_id:
            connector["scanned_chats"] = [
                {
                    **dict(item),
                    "scanned_at": scanned_at,
                }
                for item in items
            ]
            changed = True
        updated.append(connector)
    if changed:
        replace_bot_connectors(updated)


def save_bot_connector_scanned_chat(connector_id: str, item: dict[str, Any]) -> None:
    normalized_id = str(connector_id or "").strip().lower()
    chat_id = str((item or {}).get("chat_id") or "").strip()
    if not normalized_id or not chat_id:
        return
    scanned_at = _now_iso()
    connectors = list_bot_connectors()
    updated: list[dict[str, object]] = []
    changed = False
    for raw in connectors:
        connector = dict(raw or {})
        if str(connector.get("id") or "").strip().lower() == normalized_id:
            existing = connector.get("scanned_chats")
            chats = [dict(chat) for chat in existing if isinstance(chat, dict)] if isinstance(existing, list) else []
            next_chat = {
                **dict(item),
                "connector_id": connector.get("id") or connector_id,
                "chat_id": chat_id,
                "scanned_at": scanned_at,
            }
            replaced = False
            for index, chat in enumerate(chats):
                if str(chat.get("chat_id") or "").strip() == chat_id:
                    chats[index] = {**chat, **next_chat}
                    replaced = True
                    break
            if not replaced:
                chats.insert(0, next_chat)
            connector["scanned_chats"] = chats
            changed = True
        updated.append(connector)
    if changed:
        replace_bot_connectors(updated)


def scan_bot_connector_chats(connector_id: str) -> dict[str, Any]:
    connector = get_bot_connector(connector_id)
    normalized_id = str(connector_id or "").strip()
    if connector is None:
        return {
            "status": "missing_connector",
            "connector_id": normalized_id,
            "platform": "",
            "items": [],
            "count": 0,
            "missing": ["bot_connector"],
            "message": "机器人连接器不存在，请先保存机器人配置",
        }
    platform = str(connector.get("platform") or "").strip().lower()
    if connector.get("enabled") is False:
        return {
            "status": "disabled",
            "connector_id": connector.get("id") or normalized_id,
            "platform": platform,
            "items": [],
            "count": 0,
            "missing": ["enabled_connector"],
            "message": "机器人连接器已停用，请启用后再扫描群列表",
        }
    app_id = str(connector.get("app_id") or "").strip()
    app_secret = str(connector.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        return {
            "status": "missing_credentials",
            "connector_id": connector.get("id") or normalized_id,
            "platform": platform,
            "items": [],
            "count": 0,
            "missing": [key for key, present in (("app_id", app_id), ("app_secret", app_secret)) if not present],
            "message": "缺少机器人平台 App ID 或 App Secret",
        }
    if platform == "feishu":
        from services.feishu.feishu_bot_service import list_feishu_bot_joined_chats

        result = list_feishu_bot_joined_chats(dict(connector))
        items = [
            {
                "platform": "feishu",
                "connector_id": connector.get("id") or normalized_id,
                "chat_id": str(item.get("chat_id") or "").strip(),
                "chat_name": str(item.get("chat_name") or item.get("name") or "").strip(),
                "chat_type": str(item.get("chat_type") or "").strip(),
                "chat_mode": str(item.get("chat_mode") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "source": result.get("source") or "feishu.im.v1.chats",
            }
            for item in result.get("items") or []
            if str(item.get("chat_id") or "").strip()
        ]
        _save_bot_connector_scanned_chats(str(connector.get("id") or normalized_id), items)
        return {
            "status": "scanned",
            "connector_id": connector.get("id") or normalized_id,
            "platform": "feishu",
            "items": items,
            "count": len(items),
            "missing": [],
            "message": f"扫描到 {len(items)} 个飞书群",
        }
    return {
        "status": "unsupported",
        "connector_id": connector.get("id") or normalized_id,
        "platform": platform,
        "items": [],
        "count": 0,
        "missing": ["platform_chat_list_api"],
        "message": f"{platform or '当前平台'} 暂未实现机器人所在群全量扫描",
    }
