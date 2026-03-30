from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from uuid import uuid4
import json
import redis.asyncio as redis
from core.config import get_settings

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class ConversationSession:
    id: str
    project_id: str
    employee_id: str
    status: str
    created_at: str
    last_active_at: str
    message_count: int
    compressed_at: str | None = None

class ConversationManager:
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client
        settings = get_settings()
        self._max_messages = settings.max_messages
        self._compression_threshold = settings.compression_threshold
        self._session_ttl = settings.session_ttl

    async def create_session(self, project_id: str, employee_id: str) -> str:
        session_id = f"sess-{uuid4().hex[:8]}"
        session = ConversationSession(
            id=session_id,
            project_id=project_id,
            employee_id=employee_id,
            status="active",
            created_at=_now_iso(),
            last_active_at=_now_iso(),
            message_count=0
        )
        await self._save_session(session)
        return session_id

    async def get_context(self, session_id: str, max_tokens: int) -> list[dict]:
        session = await self._load_session(session_id)
        if session is None:
            return []
        messages = await self._load_messages(session_id)

        # 触发压缩
        if len(messages) > self._compression_threshold:
            messages = await self._compress_history(session_id, messages)

        await self._touch_session(session_id)
        return messages[-self._max_messages:]

    async def _compress_history(self, session_id: str, messages: list[dict]) -> list[dict]:
        system_msgs = [m for m in messages if m.get("role") == "system"]
        recent_msgs = messages[-5:]
        middle_msgs = messages[len(system_msgs):-5]

        if len(middle_msgs) < 5:
            return messages

        # 生成摘要
        summary = await self._generate_summary(middle_msgs)
        compressed = system_msgs + [{"role": "system", "content": f"[历史摘要] {summary}"}] + recent_msgs

        # 更新缓存
        key = f"session:{session_id}:messages"
        await self._redis.delete(key)
        for msg in compressed:
            await self._redis.rpush(key, json.dumps(msg, ensure_ascii=False))
        await self._redis.expire(key, self._session_ttl)
        await self._touch_session(session_id, compressed=True)

        return compressed

    async def _generate_summary(self, messages: list[dict]) -> str:
        # 简化实现：拼接内容
        content_parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if content:
                content_parts.append(f"{role}: {content[:100]}")
        return " | ".join(content_parts[:10])

    async def append_message(self, session_id: str, message: dict) -> None:
        key = f"session:{session_id}:messages"
        await self._redis.rpush(key, json.dumps(message, ensure_ascii=False))
        await self._redis.expire(key, self._session_ttl)
        await self._touch_session(session_id, message_delta=1)

    async def _save_session(self, session: ConversationSession) -> None:
        key = f"session:{session.id}:meta"
        await self._redis.set(key, json.dumps(asdict(session)), ex=self._session_ttl)

    async def _load_messages(self, session_id: str) -> list[dict]:
        key = f"session:{session_id}:messages"
        raw_messages = await self._redis.lrange(key, 0, -1)
        return [json.loads(m) for m in raw_messages]

    async def _load_session(self, session_id: str) -> ConversationSession | None:
        key = f"session:{session_id}:meta"
        raw = await self._redis.get(key)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return ConversationSession(
            id=str(data.get("id") or session_id),
            project_id=str(data.get("project_id") or ""),
            employee_id=str(data.get("employee_id") or ""),
            status=str(data.get("status") or "active"),
            created_at=str(data.get("created_at") or _now_iso()),
            last_active_at=str(data.get("last_active_at") or data.get("created_at") or _now_iso()),
            message_count=max(0, int(data.get("message_count") or 0)),
            compressed_at=str(data.get("compressed_at") or "") or None,
        )

    async def _touch_session(
        self,
        session_id: str,
        *,
        message_delta: int = 0,
        compressed: bool = False,
    ) -> None:
        session = await self._load_session(session_id)
        if session is None:
            return
        updated = replace(
            session,
            last_active_at=_now_iso(),
            message_count=max(0, int(session.message_count or 0)) + max(0, int(message_delta or 0)),
            compressed_at=_now_iso() if compressed else session.compressed_at,
        )
        await self._save_session(updated)
