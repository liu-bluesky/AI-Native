"""系统统一用户反馈存储层。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: object, limit: int) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


@dataclass
class UserFeedbackTicket:
    id: str
    reporter_id: str
    reporter_name_snapshot: str = ""
    category: str = "other"
    subcategory: str = ""
    title: str = ""
    description: str = ""
    expected_result: str = ""
    impact_level: str = "general"
    priority: str = "normal"
    frequency: str = "unknown"
    status: str = "submitted"
    source_entry: str = "global_menu"
    project_id: str = ""
    assignee_id: str = ""
    security_restricted: bool = False
    public_reply: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    ai_evidence: dict[str, Any] = field(default_factory=dict)
    diagnostic_consent: dict[str, bool] = field(default_factory=dict)
    comments: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    idempotency_key: str = ""
    resolved_at: str = ""
    closed_at: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.id = _text(self.id, 80)
        self.reporter_id = _text(self.reporter_id, 120)
        self.reporter_name_snapshot = _text(self.reporter_name_snapshot, 120)
        self.category = _text(self.category, 48).lower() or "other"
        self.subcategory = _text(self.subcategory, 80).lower()
        self.title = _text(self.title, 180)
        self.description = _text(self.description, 12000)
        self.expected_result = _text(self.expected_result, 4000)
        self.impact_level = _text(self.impact_level, 32).lower() or "general"
        self.priority = _text(self.priority, 32).lower() or "normal"
        self.frequency = _text(self.frequency, 32).lower() or "unknown"
        self.status = _text(self.status, 32).lower() or "submitted"
        self.source_entry = _text(self.source_entry, 48).lower() or "global_menu"
        self.project_id = _text(self.project_id, 100)
        self.assignee_id = _text(self.assignee_id, 120)
        self.security_restricted = bool(self.security_restricted)
        self.public_reply = _text(self.public_reply, 8000)
        self.context = self.context if isinstance(self.context, dict) else {}
        self.ai_evidence = self.ai_evidence if isinstance(self.ai_evidence, dict) else {}
        self.diagnostic_consent = (
            self.diagnostic_consent if isinstance(self.diagnostic_consent, dict) else {}
        )
        self.comments = self.comments if isinstance(self.comments, list) else []
        self.events = self.events if isinstance(self.events, list) else []
        self.idempotency_key = _text(self.idempotency_key, 160)
        self.resolved_at = _text(self.resolved_at, 48)
        self.closed_at = _text(self.closed_at, 48)
        self.created_at = _text(self.created_at or _now_iso(), 48) or _now_iso()
        self.updated_at = _text(self.updated_at or _now_iso(), 48) or _now_iso()


def sort_user_feedback(items: list[UserFeedbackTicket]) -> list[UserFeedbackTicket]:
    return sorted(items, key=lambda item: (item.updated_at, item.created_at, item.id), reverse=True)


class UserFeedbackStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "user-feedback"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, feedback_id: str) -> Path:
        return self._dir / f"{_text(feedback_id, 80)}.json"

    def new_id(self) -> str:
        return f"ufb_{uuid.uuid4().hex[:12]}"

    def save(self, ticket: UserFeedbackTicket) -> None:
        normalized = UserFeedbackTicket(**asdict(ticket))
        normalized.updated_at = _now_iso()
        self._path(normalized.id).write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, feedback_id: str) -> UserFeedbackTicket | None:
        path = self._path(feedback_id)
        if not path.exists():
            return None
        return UserFeedbackTicket(**json.loads(path.read_text(encoding="utf-8")))

    def list_all(self) -> list[UserFeedbackTicket]:
        items: list[UserFeedbackTicket] = []
        for path in self._dir.glob("*.json"):
            try:
                items.append(UserFeedbackTicket(**json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return sort_user_feedback(items)

    def find_idempotent(self, reporter_id: str, idempotency_key: str) -> UserFeedbackTicket | None:
        normalized_key = _text(idempotency_key, 160)
        if not normalized_key:
            return None
        return next(
            (
                item
                for item in self.list_all()
                if item.reporter_id == reporter_id and item.idempotency_key == normalized_key
            ),
            None,
        )
