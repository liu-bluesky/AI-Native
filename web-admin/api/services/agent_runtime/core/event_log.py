"""Append-only runtime event log for agent runtime."""

from __future__ import annotations

import json
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from core.config import get_project_root
from services.agent_runtime.core.task_run import utc_now_iso


@dataclass
class RuntimeEvent:
    event_id: str
    run_id: str
    event_type: str
    session_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        # 中文注释：保留 event_type 给旧代码使用，同时补 type/session_id 给新 Adapter 统一消费。
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "type": self.event_type,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "payload": dict(self.payload),
        }

    def to_agent_event(self, *, session_id: str = "") -> dict[str, Any]:
        """Return the cross-adapter event envelope used by CLI/Web/Desktop."""

        payload = self.to_dict()
        normalized_session_id = str(session_id or self.session_id or "").strip()
        payload["session_id"] = normalized_session_id
        return payload

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        session_id: str = "",
    ) -> "RuntimeEvent":
        return cls(
            event_id=f"evt_{uuid4().hex[:16]}",
            run_id=str(run_id or "").strip(),
            session_id=str(session_id or "").strip(),
            event_type=str(event_type or "").strip() or "event",
            payload=dict(payload or {}),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeEvent":
        return cls(
            event_id=str(payload.get("event_id") or f"evt_{uuid4().hex[:16]}").strip(),
            run_id=str(payload.get("run_id") or "").strip(),
            session_id=str(payload.get("session_id") or "").strip(),
            event_type=str(payload.get("event_type") or payload.get("type") or "event").strip(),
            created_at=str(payload.get("created_at") or utc_now_iso()).strip(),
            payload=dict(payload.get("payload") or {}),
        )


class RuntimeEventLog:
    def __init__(self, root_path: Path | None = None):
        self._root_path = root_path or (
            get_project_root() / ".ai-employee" / "agent-runtime-v2" / "events"
        )
        self._subscribers: list[Callable[[RuntimeEvent], None]] = []

    @property
    def root_path(self) -> Path:
        return self._root_path

    def _path_for(self, run_id: str) -> Path:
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            raise ValueError("run_id is required")
        return self._root_path / f"{normalized_run_id}.jsonl"

    def append(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        session_id: str = "",
    ) -> RuntimeEvent:
        event = RuntimeEvent.create(
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            session_id=session_id,
        )
        path = self._path_for(event.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        for subscriber in list(self._subscribers):
            try:
                subscriber(event)
            except Exception:
                continue
        return event

    def subscribe(self, callback: Callable[[RuntimeEvent], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def _unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._subscribers.remove(callback)

        return _unsubscribe

    def list_events(self, run_id: str) -> list[RuntimeEvent]:
        path = self._path_for(run_id)
        if not path.is_file():
            return []
        events: list[RuntimeEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(RuntimeEvent.from_dict(payload))
        return events
