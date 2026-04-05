"""工作会话轨迹存储层（JSON 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, limit: int = 4000) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def _normalize_list(values: list[str] | None, *, item_limit: int = 240, max_items: int = 40) -> list[str]:
    items: list[str] = []
    for item in values or []:
        normalized = _normalize_text(item, item_limit)
        if normalized and normalized not in items:
            items.append(normalized)
        if len(items) >= max_items:
            break
    return items


def _timestamp_for_sort(value: object) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    normalized = raw.replace(" ", "T").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return 0.0


@dataclass
class WorkSessionEvent:
    id: str
    project_id: str
    project_name: str = ""
    employee_id: str = ""
    session_id: str = ""
    task_tree_session_id: str = ""
    task_tree_chat_session_id: str = ""
    task_node_id: str = ""
    task_node_title: str = ""
    source_kind: str = ""
    event_type: str = ""
    phase: str = ""
    step: str = ""
    status: str = ""
    goal: str = ""
    content: str = ""
    facts: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, 80)
        self.project_id = _normalize_text(self.project_id, 80)
        self.project_name = _normalize_text(self.project_name, 120)
        self.employee_id = _normalize_text(self.employee_id, 80)
        self.session_id = _normalize_text(self.session_id, 80)
        self.task_tree_session_id = _normalize_text(self.task_tree_session_id, 80)
        self.task_tree_chat_session_id = _normalize_text(self.task_tree_chat_session_id, 80)
        self.task_node_id = _normalize_text(self.task_node_id, 80)
        self.task_node_title = _normalize_text(self.task_node_title, 200)
        self.source_kind = _normalize_text(self.source_kind, 40)
        self.event_type = _normalize_text(self.event_type, 40)
        self.phase = _normalize_text(self.phase, 80)
        self.step = _normalize_text(self.step, 80)
        self.status = _normalize_text(self.status, 40)
        self.goal = _normalize_text(self.goal, 400)
        self.content = _normalize_text(self.content, 4000)
        self.facts = _normalize_list(self.facts, item_limit=400, max_items=50)
        self.changed_files = _normalize_list(self.changed_files, item_limit=240, max_items=50)
        self.verification = _normalize_list(self.verification, item_limit=400, max_items=50)
        self.risks = _normalize_list(self.risks, item_limit=400, max_items=30)
        self.next_steps = _normalize_list(self.next_steps, item_limit=400, max_items=30)
        self.created_at = _normalize_text(self.created_at or _now_iso(), 40) or _now_iso()
        self.updated_at = _normalize_text(self.updated_at or _now_iso(), 40) or _now_iso()


class WorkSessionStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "work-session-events"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, event_id: str) -> Path:
        return self._dir / f"{str(event_id or '').strip()}.json"

    def save(self, event: WorkSessionEvent) -> None:
        normalized = WorkSessionEvent(**asdict(event))
        if not normalized.id:
            raise ValueError("Work session event id is required")
        if not normalized.project_id:
            raise ValueError("Work session event project_id is required")
        if not normalized.session_id:
            raise ValueError("Work session event session_id is required")
        if not normalized.created_at:
            normalized.created_at = _now_iso()
        normalized.updated_at = _now_iso()
        self._path(normalized.id).write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, event_id: str) -> WorkSessionEvent | None:
        path = self._path(event_id)
        if not path.exists():
            return None
        return WorkSessionEvent(**json.loads(path.read_text(encoding="utf-8")))

    def list_all(self) -> list[WorkSessionEvent]:
        items: list[WorkSessionEvent] = []
        for path in self._dir.glob("*.json"):
            items.append(WorkSessionEvent(**json.loads(path.read_text(encoding="utf-8"))))
        items.sort(key=lambda item: (_timestamp_for_sort(item.created_at), item.id), reverse=True)
        return items

    def list_events(
        self,
        *,
        project_id: str = "",
        employee_id: str = "",
        session_id: str = "",
        task_tree_session_id: str = "",
        task_tree_chat_session_id: str = "",
        task_node_id: str = "",
        query: str = "",
        limit: int = 200,
    ) -> list[WorkSessionEvent]:
        normalized_project_id = _normalize_text(project_id, 80)
        normalized_employee_id = _normalize_text(employee_id, 80)
        normalized_session_id = _normalize_text(session_id, 80)
        normalized_task_tree_session_id = _normalize_text(task_tree_session_id, 80)
        normalized_task_tree_chat_session_id = _normalize_text(task_tree_chat_session_id, 80)
        normalized_task_node_id = _normalize_text(task_node_id, 80)
        keyword = _normalize_text(query, 200).lower()
        try:
            limit_value = max(1, min(int(limit or 200), 500))
        except (TypeError, ValueError):
            limit_value = 200
        items: list[WorkSessionEvent] = []
        for item in self.list_all():
            if normalized_project_id and item.project_id != normalized_project_id:
                continue
            if normalized_employee_id and item.employee_id != normalized_employee_id:
                continue
            if normalized_session_id and item.session_id != normalized_session_id:
                continue
            if normalized_task_tree_session_id and item.task_tree_session_id != normalized_task_tree_session_id:
                continue
            if (
                normalized_task_tree_chat_session_id
                and item.task_tree_chat_session_id != normalized_task_tree_chat_session_id
            ):
                continue
            if normalized_task_node_id and item.task_node_id != normalized_task_node_id:
                continue
            if keyword:
                haystack = "\n".join(
                    [
                        item.project_name,
                        item.employee_id,
                        item.session_id,
                        item.task_tree_session_id,
                        item.task_tree_chat_session_id,
                        item.task_node_id,
                        item.task_node_title,
                        item.source_kind,
                        item.event_type,
                        item.phase,
                        item.step,
                        item.status,
                        item.goal,
                        item.content,
                        *item.facts,
                        *item.changed_files,
                        *item.verification,
                        *item.risks,
                        *item.next_steps,
                    ]
                ).lower()
                if keyword not in haystack:
                    continue
            items.append(item)
            if len(items) >= limit_value:
                break
        return items

    def delete_by_session(self, session_id: str, *, project_id: str = "") -> int:
        normalized_session_id = _normalize_text(session_id, 80)
        normalized_project_id = _normalize_text(project_id, 80)
        deleted = 0
        for item in self.list_all():
            if item.session_id != normalized_session_id:
                continue
            if normalized_project_id and item.project_id != normalized_project_id:
                continue
            path = self._path(item.id)
            if path.exists():
                path.unlink()
                deleted += 1
        return deleted

    def new_id(self) -> str:
        return f"wse-{uuid.uuid4().hex[:8]}"
