"""在线用户状态路由"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from core.deps import require_auth
from core.redis_client import get_redis_client
from models.requests import OnlineUserHeartbeatReq


router = APIRouter(prefix="/api/system/online-users", dependencies=[Depends(require_auth)])
public_router = None

_ONLINE_USER_SET_KEY = "online-users:members"
_ONLINE_USER_KEY_PREFIX = "online-users:user:"
_ONLINE_USER_TTL_SECONDS = 150


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _presence_key(username: str) -> str:
    return f"{_ONLINE_USER_KEY_PREFIX}{username}"


def _ensure_super_admin(auth_payload: dict) -> None:
    role = _normalize_text(auth_payload.get("role", ""), 40).lower()
    if role != "admin":
        raise HTTPException(403, "Super admin only")


def _extract_client_ip(request: Request) -> str:
    forwarded = _normalize_text(request.headers.get("x-forwarded-for", ""), 200)
    if forwarded:
        return _normalize_text(forwarded.split(",")[0], 80)
    return _normalize_text(getattr(getattr(request, "client", None), "host", ""), 80)


async def _list_online_presence_items(redis_client) -> list[dict]:
    usernames = sorted(
        _normalize_text(item, 80)
        for item in (await redis_client.smembers(_ONLINE_USER_SET_KEY) or set())
        if _normalize_text(item, 80)
    )
    if not usernames:
        return []
    raw_items = await redis_client.mget([_presence_key(username) for username in usernames])
    stale_usernames: list[str] = []
    items: list[dict] = []
    for username, raw in zip(usernames, raw_items):
        if not raw:
            stale_usernames.append(username)
            continue
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            stale_usernames.append(username)
            continue
        items.append(
            {
                "username": _normalize_text(data.get("username", username), 80) or username,
                "role": _normalize_text(data.get("role", ""), 40) or "user",
                "current_path": _normalize_text(data.get("current_path", ""), 240),
                "client_ip": _normalize_text(data.get("client_ip", ""), 80),
                "user_agent": _normalize_text(data.get("user_agent", ""), 240),
                "first_seen_at": _normalize_text(data.get("first_seen_at", ""), 40),
                "last_seen_at": _normalize_text(data.get("last_seen_at", ""), 40),
            }
        )
    if stale_usernames:
        await redis_client.srem(_ONLINE_USER_SET_KEY, *stale_usernames)
    items.sort(key=lambda item: (item.get("last_seen_at") or "", item.get("username") or ""), reverse=True)
    return items


@router.post("/heartbeat")
async def heartbeat_online_user_presence(
    req: OnlineUserHeartbeatReq,
    request: Request,
    auth_payload: dict = Depends(require_auth),
):
    username = _normalize_text(auth_payload.get("sub", ""), 80)
    if not username:
        raise HTTPException(401, "Missing user identity")
    role = _normalize_text(auth_payload.get("role", ""), 40).lower() or "user"
    redis_client = await get_redis_client()
    existing_raw = await redis_client.get(_presence_key(username))
    existing: dict = {}
    if existing_raw:
        if isinstance(existing_raw, bytes):
            existing_raw = existing_raw.decode("utf-8")
        try:
            existing = json.loads(existing_raw)
        except (TypeError, ValueError):
            existing = {}
    now_iso = _now_iso()
    payload = {
        "username": username,
        "role": role,
        "current_path": _normalize_text(req.current_path, 240),
        "client_ip": _extract_client_ip(request),
        "user_agent": _normalize_text(request.headers.get("user-agent", ""), 240),
        "first_seen_at": _normalize_text(existing.get("first_seen_at", ""), 40) or now_iso,
        "last_seen_at": now_iso,
    }
    await redis_client.set(
        _presence_key(username),
        json.dumps(payload, ensure_ascii=False),
        ex=_ONLINE_USER_TTL_SECONDS,
    )
    await redis_client.sadd(_ONLINE_USER_SET_KEY, username)
    return {
        "status": "ok",
        "item": payload,
        "ttl_seconds": _ONLINE_USER_TTL_SECONDS,
    }


@router.get("")
async def list_online_users(auth_payload: dict = Depends(require_auth)):
    _ensure_super_admin(auth_payload)
    redis_client = await get_redis_client()
    items = await _list_online_presence_items(redis_client)
    return {
        "items": items,
        "ttl_seconds": _ONLINE_USER_TTL_SECONDS,
    }
