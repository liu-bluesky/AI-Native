from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
import json
import redis.asyncio as redis
from config import get_settings

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
        meta_key = f"session:{session_id}:meta"
        if not await self._redis.exists(meta_key):
            return []
        messages = await self._load_messages(session_id)

        # 触发压缩
        if len(messages) > self._compression_threshold:
            messages = await self._compress_history(session_id, messages)

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

    async def _save_session(self, session: ConversationSession) -> None:
        key = f"session:{session.id}:meta"
        await self._redis.set(key, json.dumps({
            "id": session.id,
            "project_id": session.project_id,
            "employee_id": session.employee_id,
            "status": session.status,
            "created_at": session.created_at,
            "last_active_at": session.last_active_at,
            "message_count": session.message_count,
            "compressed_at": session.compressed_at
        }), ex=self._session_ttl)

    async def _load_messages(self, session_id: str) -> list[dict]:
        key = f"session:{session_id}:messages"
        raw_messages = await self._redis.lrange(key, 0, -1)
        return [json.loads(m) for m in raw_messages]
