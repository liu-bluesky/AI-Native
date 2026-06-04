"""System MCP online presence tracking."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from core.redis_client import get_redis_client

_SYSTEM_MCP_PRESENCE_SET_KEY = "system-mcp:presence:members"
_SYSTEM_MCP_PRESENCE_KEY_PREFIX = "system-mcp:presence:item:"
_SYSTEM_MCP_PRESENCE_TTL_SECONDS = 180


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _presence_member_key(
    endpoint_type: str,
    entity_id: str,
    developer_name: str,
    client_ip: str,
) -> str:
    digest = hashlib.sha1(
        "|".join(
            [
                _normalize_text(endpoint_type, 40).lower(),
                _normalize_text(entity_id, 120).lower(),
                _normalize_text(developer_name, 160).lower(),
                _normalize_text(client_ip, 80).lower(),
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"{_SYSTEM_MCP_PRESENCE_KEY_PREFIX}{digest}"


def _mask_api_key(api_key: str) -> str:
    normalized = _normalize_text(api_key, 120)
    if len(normalized) <= 8:
        return normalized
    return f"{normalized[:4]}...{normalized[-4:]}"


async def touch_project_mcp_presence(
    *,
    endpoint_type: str = "project",
    entity_id: str = "",
    entity_name: str = "",
    project_id: str,
    project_name: str = "",
    developer_name: str = "",
    key_owner_username: str = "",
    api_key: str = "",
    client_ip: str = "",
    transport: str = "",
    method: str = "",
    path: str = "",
    session_id: str = "",
    redis_client=None,
) -> dict:
    normalized_endpoint_type = _normalize_text(endpoint_type, 40).lower() or "project"
    normalized_entity_id = _normalize_text(entity_id, 120) or _normalize_text(project_id, 120)
    if not normalized_entity_id:
        return {"status": "skipped", "reason": "missing_entity_id"}

    normalized_developer_name = _normalize_text(developer_name, 160) or "unknown"
    normalized_client_ip = _normalize_text(client_ip, 80) or "-"
    normalized_entity_name = _normalize_text(entity_name, 160) or normalized_entity_id
    normalized_project_id = _normalize_text(project_id, 120)
    normalized_project_name = _normalize_text(project_name, 160) or normalized_project_id
    normalized_key_owner_username = _normalize_text(key_owner_username, 120)
    normalized_transport = _normalize_text(transport, 40) or "unknown"
    normalized_method = _normalize_text(method, 16).upper()
    normalized_path = _normalize_text(path, 240)
    normalized_session_id = _normalize_text(session_id, 120)
    normalized_api_key = _mask_api_key(api_key)

    if redis_client is None:
        redis_client = await get_redis_client()

    key = _presence_member_key(
        normalized_endpoint_type,
        normalized_entity_id,
        normalized_developer_name,
        normalized_client_ip,
    )
    existing_raw = await redis_client.get(key)
    existing: dict = {}
    if existing_raw:
        if isinstance(existing_raw, bytes):
            existing_raw = existing_raw.decode("utf-8")
        try:
            existing = json.loads(existing_raw)
        except (TypeError, ValueError):
            existing = {}

    now_iso = _now_iso()
    try:
        request_count = int(existing.get("request_count") or 0) + 1
    except (TypeError, ValueError):
        request_count = 1

    payload = {
        "endpoint_type": normalized_endpoint_type,
        "entity_id": normalized_entity_id,
        "entity_name": normalized_entity_name,
        "project_id": normalized_project_id,
        "project_name": normalized_project_name,
        "developer_name": normalized_developer_name,
        "key_owner_username": normalized_key_owner_username,
        "api_key": normalized_api_key,
        "client_ip": normalized_client_ip,
        "transport": normalized_transport,
        "method": normalized_method,
        "path": normalized_path,
        "session_id": normalized_session_id or _normalize_text(existing.get("session_id", ""), 120),
        "first_seen_at": _normalize_text(existing.get("first_seen_at", ""), 40) or now_iso,
        "last_seen_at": now_iso,
        "request_count": request_count,
    }
    await redis_client.set(
        key,
        json.dumps(payload, ensure_ascii=False),
        ex=_SYSTEM_MCP_PRESENCE_TTL_SECONDS,
    )
    await redis_client.sadd(_SYSTEM_MCP_PRESENCE_SET_KEY, key)
    return payload


async def list_active_project_mcp_presence(redis_client=None) -> dict:
    result = await list_active_system_mcp_presence(redis_client=redis_client)
    project_items = [item for item in result["items"] if item.get("endpoint_type") == "project"]
    return {
        "items": project_items,
        "ttl_seconds": result["ttl_seconds"],
        "summary": {
            "active_projects": len(
                {item.get("project_id") for item in project_items if _normalize_text(item.get("project_id", ""), 120)}
            ),
            "active_developers": len(project_items),
            "active_sessions": len(
                {(item.get("project_id"), item.get("developer_name"), item.get("client_ip")) for item in project_items}
            ),
        },
    }


async def list_active_system_mcp_presence(redis_client=None) -> dict:
    if redis_client is None:
        redis_client = await get_redis_client()

    keys = sorted(
        _normalize_text(item, 120)
        for item in (await redis_client.smembers(_SYSTEM_MCP_PRESENCE_SET_KEY) or set())
        if _normalize_text(item, 120)
    )
    if not keys:
        return {
            "items": [],
            "ttl_seconds": _SYSTEM_MCP_PRESENCE_TTL_SECONDS,
            "summary": {
                "active_entries": 0,
                "active_endpoint_types": 0,
                "active_projects": 0,
                "active_developers": 0,
            },
        }

    raw_items = await redis_client.mget(keys)
    stale_keys: list[str] = []
    items: list[dict] = []
    for key, raw in zip(keys, raw_items):
        if not raw:
            stale_keys.append(key)
            continue
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            stale_keys.append(key)
            continue
        items.append(
            {
                "endpoint_type": _normalize_text(data.get("endpoint_type", ""), 40) or "project",
                "entity_id": _normalize_text(data.get("entity_id", ""), 120),
                "entity_name": _normalize_text(data.get("entity_name", ""), 160),
                "project_id": _normalize_text(data.get("project_id", ""), 120),
                "project_name": _normalize_text(data.get("project_name", ""), 160),
                "developer_name": _normalize_text(data.get("developer_name", ""), 160) or "unknown",
                "key_owner_username": _normalize_text(data.get("key_owner_username", ""), 120),
                "api_key": _normalize_text(data.get("api_key", ""), 120),
                "client_ip": _normalize_text(data.get("client_ip", ""), 80),
                "transport": _normalize_text(data.get("transport", ""), 40) or "unknown",
                "method": _normalize_text(data.get("method", ""), 16).upper(),
                "path": _normalize_text(data.get("path", ""), 240),
                "session_id": _normalize_text(data.get("session_id", ""), 120),
                "first_seen_at": _normalize_text(data.get("first_seen_at", ""), 40),
                "last_seen_at": _normalize_text(data.get("last_seen_at", ""), 40),
                "request_count": int(data.get("request_count") or 0),
            }
        )
    if stale_keys:
        await redis_client.srem(_SYSTEM_MCP_PRESENCE_SET_KEY, *stale_keys)
    items.sort(
        key=lambda item: (
            item.get("last_seen_at") or "",
            item.get("endpoint_type") or "",
            item.get("entity_name") or item.get("entity_id") or "",
            item.get("project_name") or item.get("project_id") or "",
            item.get("developer_name") or "",
        ),
        reverse=True,
    )
    return {
        "items": items,
        "ttl_seconds": _SYSTEM_MCP_PRESENCE_TTL_SECONDS,
        "summary": {
            "active_entries": len(items),
            "active_endpoint_types": len(
                {
                    item.get("endpoint_type")
                    for item in items
                    if _normalize_text(item.get("endpoint_type", ""), 40)
                }
            ),
            "active_projects": len(
                {
                    item.get("project_id")
                    for item in items
                    if _normalize_text(item.get("project_id", ""), 120)
                }
            ),
            "active_developers": len(
                {
                    (
                        item.get("endpoint_type"),
                        item.get("entity_id"),
                        item.get("developer_name"),
                        item.get("client_ip"),
                    )
                    for item in items
                }
            ),
        },
    }
