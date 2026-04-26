"""Realtime fanout for project chat events."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from core.redis_client import get_redis_client


logger = logging.getLogger(__name__)

PROJECT_CHAT_REALTIME_CHANNEL = "project-chat:realtime-events"

_connections: dict[tuple[str, str], set[WebSocket]] = defaultdict(set)
_connection_lock = asyncio.Lock()
_subscriber_task: asyncio.Task | None = None


def _connection_key(project_id: str, username: str) -> tuple[str, str]:
    return (str(project_id or "").strip(), str(username or "").strip())


async def register_project_chat_ws(
    *,
    project_id: str,
    username: str,
    websocket: WebSocket,
) -> None:
    key = _connection_key(project_id, username)
    if not key[0] or not key[1]:
        return
    async with _connection_lock:
        _connections[key].add(websocket)


async def unregister_project_chat_ws(
    *,
    project_id: str,
    username: str,
    websocket: WebSocket,
) -> None:
    key = _connection_key(project_id, username)
    async with _connection_lock:
        sockets = _connections.get(key)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            _connections.pop(key, None)


async def broadcast_project_chat_realtime_event(payload: dict[str, Any]) -> None:
    project_id = str(payload.get("project_id") or "").strip()
    username = str(payload.get("username") or "").strip()
    if not project_id or not username:
        return
    async with _connection_lock:
        sockets = list(_connections.get(_connection_key(project_id, username)) or [])
    stale: list[WebSocket] = []
    for websocket in sockets:
        try:
            await websocket.send_json(payload)
        except Exception:
            stale.append(websocket)
    if stale:
        async with _connection_lock:
            current = _connections.get(_connection_key(project_id, username))
            if current:
                for websocket in stale:
                    current.discard(websocket)
                if not current:
                    _connections.pop(_connection_key(project_id, username), None)


async def publish_project_chat_realtime_event(payload: dict[str, Any]) -> None:
    event = dict(payload or {})
    event.setdefault("event_id", f"project-chat-event-{uuid.uuid4().hex[:16]}")
    try:
        redis_client = await get_redis_client()
        await redis_client.publish(
            PROJECT_CHAT_REALTIME_CHANNEL,
            json.dumps(event, ensure_ascii=False),
        )
    except Exception as exc:
        logger.warning("project chat realtime redis publish failed: %s", exc)
        await broadcast_project_chat_realtime_event(event)


async def _subscriber_loop() -> None:
    while True:
        pubsub = None
        try:
            redis_client = await get_redis_client()
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(PROJECT_CHAT_REALTIME_CHANNEL)
            async for message in pubsub.listen():
                if str(message.get("type") or "") != "message":
                    continue
                raw = message.get("data")
                try:
                    payload = json.loads(str(raw or "{}"))
                except Exception:
                    continue
                if isinstance(payload, dict):
                    await broadcast_project_chat_realtime_event(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("project chat realtime subscriber error: %s", exc)
            await asyncio.sleep(2)
        finally:
            if pubsub is not None:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe(PROJECT_CHAT_REALTIME_CHANNEL)
                with contextlib.suppress(Exception):
                    await pubsub.close()


def start_project_chat_realtime_subscriber() -> asyncio.Task | None:
    global _subscriber_task
    if _subscriber_task is not None and not _subscriber_task.done():
        return _subscriber_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    _subscriber_task = loop.create_task(_subscriber_loop())
    return _subscriber_task


async def stop_project_chat_realtime_subscriber() -> None:
    global _subscriber_task
    task = _subscriber_task
    _subscriber_task = None
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
