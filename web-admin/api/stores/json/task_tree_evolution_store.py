"""任务树演进样本存储层（JSON 实现）"""

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


def _normalize_list(values: list[str] | None, *, item_limit: int = 240, max_items: int = 20) -> list[str]:
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
class TaskTreeEvolutionSample:
    id: str
    project_id: str
    chat_session_id: str = ""
    task_tree_session_id: str = ""
    source_kind: str = ""
    root_goal: str = ""
    detected_intent: str = ""
    wrong_template: str = ""
    corrected_template: str = ""
    issue_code: str = ""
    issue_message: str = ""
    user_visible: bool = False
    manually_corrected: bool = False
    rebuild_successful: bool = False
    evidence: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, 80)
        self.project_id = _normalize_text(self.project_id, 80)
        self.chat_session_id = _normalize_text(self.chat_session_id, 80)
        self.task_tree_session_id = _normalize_text(self.task_tree_session_id, 80)
        self.source_kind = _normalize_text(self.source_kind, 40)
        self.root_goal = _normalize_text(self.root_goal, 1000)
        self.detected_intent = _normalize_text(self.detected_intent, 80)
        self.wrong_template = _normalize_text(self.wrong_template, 120)
        self.corrected_template = _normalize_text(self.corrected_template, 120)
        self.issue_code = _normalize_text(self.issue_code, 80)
        self.issue_message = _normalize_text(self.issue_message, 500)
        self.user_visible = bool(self.user_visible)
        self.manually_corrected = bool(self.manually_corrected)
        self.rebuild_successful = bool(self.rebuild_successful)
        self.evidence = _normalize_list(self.evidence, item_limit=240, max_items=20)
        self.created_at = _normalize_text(self.created_at or _now_iso(), 40) or _now_iso()
        self.updated_at = _normalize_text(self.updated_at or _now_iso(), 40) or _now_iso()


class TaskTreeEvolutionStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "task-tree-evolution"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, sample_id: str) -> Path:
        return self._dir / f"{str(sample_id or '').strip()}.json"

    def save(self, sample: TaskTreeEvolutionSample) -> None:
        normalized = TaskTreeEvolutionSample(**asdict(sample))
        if not normalized.id:
            raise ValueError("Task tree evolution sample id is required")
        if not normalized.project_id:
            raise ValueError("Task tree evolution sample project_id is required")
        if not normalized.created_at:
            normalized.created_at = _now_iso()
        normalized.updated_at = _now_iso()
        self._path(normalized.id).write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, sample_id: str) -> TaskTreeEvolutionSample | None:
        path = self._path(sample_id)
        if not path.exists():
            return None
        return TaskTreeEvolutionSample(**json.loads(path.read_text(encoding="utf-8")))

    def list_samples(
        self,
        *,
        project_id: str = "",
        chat_session_id: str = "",
        task_tree_session_id: str = "",
        issue_code: str = "",
        source_kind: str = "",
        limit: int = 200,
    ) -> list[TaskTreeEvolutionSample]:
        normalized_project_id = _normalize_text(project_id, 80)
        normalized_chat_session_id = _normalize_text(chat_session_id, 80)
        normalized_task_tree_session_id = _normalize_text(task_tree_session_id, 80)
        normalized_issue_code = _normalize_text(issue_code, 80)
        normalized_source_kind = _normalize_text(source_kind, 40)
        try:
            limit_value = max(1, min(int(limit or 200), 500))
        except (TypeError, ValueError):
            limit_value = 200
        items: list[TaskTreeEvolutionSample] = []
        for path in self._dir.glob("*.json"):
            items.append(TaskTreeEvolutionSample(**json.loads(path.read_text(encoding="utf-8"))))
        items.sort(key=lambda item: (_timestamp_for_sort(item.created_at), item.id), reverse=True)
        filtered: list[TaskTreeEvolutionSample] = []
        for item in items:
            if normalized_project_id and item.project_id != normalized_project_id:
                continue
            if normalized_chat_session_id and item.chat_session_id != normalized_chat_session_id:
                continue
            if normalized_task_tree_session_id and item.task_tree_session_id != normalized_task_tree_session_id:
                continue
            if normalized_issue_code and item.issue_code != normalized_issue_code:
                continue
            if normalized_source_kind and item.source_kind != normalized_source_kind:
                continue
            filtered.append(item)
            if len(filtered) >= limit_value:
                break
        return filtered

    def new_id(self) -> str:
        return f"ttes-{uuid.uuid4().hex[:8]}"
