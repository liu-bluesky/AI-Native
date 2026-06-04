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
        payload = event.to_dict()
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


def runtime_event_public_payload(event: RuntimeEvent) -> dict[str, Any]:
    payload = event.to_dict()
    return {
        "type": "agent_runtime_event",
        "run_id": event.run_id,
        "event_type": event.event_type,
        "event": payload,
    }
