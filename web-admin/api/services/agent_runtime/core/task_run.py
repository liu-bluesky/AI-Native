"""TaskRun model and identifiers for agent runtime implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    return f"run_{uuid4().hex[:16]}"


@dataclass
class TaskRun:
    run_id: str
    project_id: str
    username: str
    chat_session_id: str
    session_id: str
    status: str = "created"
    user_goal: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        username: str,
        chat_session_id: str,
        session_id: str,
        user_goal: str,
        metadata: dict[str, Any] | None = None,
    ) -> "TaskRun":
        return cls(
            run_id=new_run_id(),
            project_id=str(project_id or "").strip(),
            username=str(username or "").strip(),
            chat_session_id=str(chat_session_id or "").strip(),
            session_id=str(session_id or "").strip(),
            user_goal=str(user_goal or "").strip(),
            metadata=dict(metadata or {}),
        )

    def append_event(self, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "event_id": f"evt_{uuid4().hex[:16]}",
            "run_id": self.run_id,
            "type": str(event_type or "").strip() or "event",
            "created_at": utc_now_iso(),
            "payload": dict(payload or {}),
        }
        self.events.append(event)
        self.updated_at = utc_now_iso()
        return event

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "username": self.username,
            "chat_session_id": self.chat_session_id,
            "session_id": self.session_id,
            "status": self.status,
            "user_goal": self.user_goal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
            "events": list(self.events),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskRun":
        run = cls(
            run_id=str(payload.get("run_id") or "").strip(),
            project_id=str(payload.get("project_id") or "").strip(),
            username=str(payload.get("username") or "").strip(),
            chat_session_id=str(payload.get("chat_session_id") or "").strip(),
            session_id=str(payload.get("session_id") or "").strip(),
            status=str(payload.get("status") or "created").strip() or "created",
            user_goal=str(payload.get("user_goal") or "").strip(),
            created_at=str(payload.get("created_at") or utc_now_iso()).strip(),
            updated_at=str(payload.get("updated_at") or utc_now_iso()).strip(),
            metadata=dict(payload.get("metadata") or {}),
            events=list(payload.get("events") or []),
        )
        if not run.run_id:
            run.run_id = new_run_id()
        return run
