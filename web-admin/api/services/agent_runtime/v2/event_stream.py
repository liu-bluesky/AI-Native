"""Runtime event stream adapters for agent_runtime_v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from services.agent_runtime.core.event_log import RuntimeEvent


RuntimeEventPublisher = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class EventStream:
    project_id: str
    username: str
    chat_session_id: str
    publisher: RuntimeEventPublisher | None = None
    emitted: list[dict[str, Any]] = field(default_factory=list)

    def event_payload(self, event: RuntimeEvent) -> dict[str, Any]:
        # 中文注释：推给前端/CLI 的事件使用带 session_id 的统一信封，外层 wrapper 继续兼容旧字段。
        payload = event.to_agent_event(session_id=self.chat_session_id)
        return {
            "type": "agent_runtime_event",
            "project_id": str(self.project_id or "").strip(),
            "username": str(self.username or "").strip(),
            "chat_session_id": str(self.chat_session_id or "").strip(),
            "run_id": event.run_id,
            "event_type": event.event_type,
            "event": payload,
        }

    async def publish(self, event: RuntimeEvent) -> dict[str, Any]:
        payload = self.event_payload(event)
        self.emitted.append(payload)
        if self.publisher is not None:
            await self.publisher(payload)
        return payload


def runtime_event_public_payload(event: RuntimeEvent, *, session_id: str = "") -> dict[str, Any]:
    payload = event.to_agent_event(session_id=session_id)
    return {
        "type": "agent_runtime_event",
        "run_id": event.run_id,
        "event_type": event.event_type,
        "event": payload,
    }
