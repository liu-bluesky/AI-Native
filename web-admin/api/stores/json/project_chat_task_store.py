"""项目聊天任务树存储层（JSON 实现）"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_TASK_STATUS_VALUES = {"pending", "in_progress", "blocked", "verifying", "done"}
_TASK_LIFECYCLE_VALUES = {"active", "archived"}
_TASK_NODE_KIND_VALUES = {"goal", "plan_step", "repair_step"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_token(value: str, max_len: int = 128) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    token = token.strip("._-")
    if not token:
        raise ValueError("invalid token")
    return token[:max_len]


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


def _normalize_status(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _TASK_STATUS_VALUES else "pending"


def _normalize_lifecycle(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _TASK_LIFECYCLE_VALUES else "active"


def _normalize_node_kind(value: object, *, fallback: str = "plan_step") -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _TASK_NODE_KIND_VALUES else fallback


@dataclass
class ProjectChatTaskNode:
    id: str
    session_id: str
    parent_id: str = ""
    node_kind: str = "plan_step"
    stage_key: str = ""
    title: str = ""
    description: str = ""
    objective: str = ""
    level: int = 0
    sort_order: int = 0
    status: str = "pending"
    done_definition: str = ""
    completion_criteria: str = ""
    verification_items: list[str] = field(default_factory=list)
    verification_method: list[str] = field(default_factory=list)
    verification_result: str = ""
    summary_for_model: str = ""
    latest_outcome: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, 80)
        self.session_id = _normalize_text(self.session_id, 80)
        self.parent_id = _normalize_text(self.parent_id, 80)
        fallback_kind = "goal" if not self.parent_id else "plan_step"
        self.node_kind = _normalize_node_kind(self.node_kind, fallback=fallback_kind)
        self.stage_key = _normalize_text(self.stage_key, 80)
        self.title = _normalize_text(self.title, 200)
        self.description = _normalize_text(self.description, 2000)
        self.objective = _normalize_text(self.objective, 2000)
        try:
            self.level = max(0, min(int(self.level or 0), 20))
        except (TypeError, ValueError):
            self.level = 0
        try:
            self.sort_order = max(0, min(int(self.sort_order or 0), 1000))
        except (TypeError, ValueError):
            self.sort_order = 0
        self.status = _normalize_status(self.status)
        self.done_definition = _normalize_text(self.done_definition, 500)
        self.completion_criteria = _normalize_text(self.completion_criteria, 500)
        self.verification_items = _normalize_list(self.verification_items, item_limit=300, max_items=12)
        self.verification_method = _normalize_list(self.verification_method, item_limit=300, max_items=12)
        self.verification_result = _normalize_text(self.verification_result, 2000)
        self.summary_for_model = _normalize_text(self.summary_for_model, 1000)
        self.latest_outcome = _normalize_text(self.latest_outcome, 1000)
        if not self.objective:
            self.objective = self.description
        if not self.description:
            self.description = self.objective
        if not self.completion_criteria:
            self.completion_criteria = self.done_definition
        if not self.done_definition:
            self.done_definition = self.completion_criteria
        if not self.verification_method:
            self.verification_method = list(self.verification_items)
        if not self.verification_items:
            self.verification_items = list(self.verification_method)
        if not self.latest_outcome:
            self.latest_outcome = self.summary_for_model or self.verification_result
        if not self.summary_for_model:
            self.summary_for_model = self.latest_outcome
        self.created_at = _normalize_text(self.created_at or _now_iso(), 40) or _now_iso()
        self.updated_at = _normalize_text(self.updated_at or _now_iso(), 40) or _now_iso()


@dataclass
class ProjectChatTaskSession:
    id: str
    project_id: str
    username: str
    chat_session_id: str
    source_chat_session_id: str = ""
    record_kind: str = "requirement"
    source_session_id: str = ""
    round_index: int = 1
    title: str = ""
    root_goal: str = ""
    status: str = "pending"
    lifecycle_status: str = "active"
    archived_reason: str = ""
    archived_at: str = ""
    current_node_id: str = ""
    progress_percent: int = 0
    nodes: list[ProjectChatTaskNode] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, 80)
        self.project_id = _normalize_text(self.project_id, 80)
        self.username = _normalize_text(self.username, 80)
        self.chat_session_id = _normalize_text(self.chat_session_id, 80)
        self.source_chat_session_id = _normalize_text(self.source_chat_session_id, 80)
        self.record_kind = _normalize_text(self.record_kind, 40).lower() or "requirement"
        if self.record_kind not in {"requirement", "repair"}:
            self.record_kind = "requirement"
        self.source_session_id = _normalize_text(self.source_session_id, 80)
        try:
            self.round_index = max(1, min(int(self.round_index or 1), 999))
        except (TypeError, ValueError):
            self.round_index = 1
        self.title = _normalize_text(self.title, 200)
        self.root_goal = _normalize_text(self.root_goal, 1000)
        self.status = _normalize_status(self.status)
        self.lifecycle_status = _normalize_lifecycle(self.lifecycle_status)
        self.archived_reason = _normalize_text(self.archived_reason, 200)
        self.archived_at = _normalize_text(self.archived_at or "", 40)
        self.current_node_id = _normalize_text(self.current_node_id, 80)
        try:
            self.progress_percent = max(0, min(int(self.progress_percent or 0), 100))
        except (TypeError, ValueError):
            self.progress_percent = 0
        normalized_nodes: list[ProjectChatTaskNode] = []
        for item in self.nodes or []:
            if isinstance(item, ProjectChatTaskNode):
                normalized_nodes.append(ProjectChatTaskNode(**asdict(item)))
            elif isinstance(item, dict):
                normalized_nodes.append(ProjectChatTaskNode(**item))
        self.nodes = normalized_nodes
        self.created_at = _normalize_text(self.created_at or _now_iso(), 40) or _now_iso()
        self.updated_at = _normalize_text(self.updated_at or _now_iso(), 40) or _now_iso()


class ProjectChatTaskStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "project-chat-task-tree"
        self._root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        return self._root / _safe_token(project_id)

    def _path(self, project_id: str, username: str, chat_session_id: str) -> Path:
        project_dir = self._project_dir(project_id)
        filename = (
            f"{_safe_token(username, max_len=64)}"
            f".{_safe_token(chat_session_id, max_len=80)}.json"
        )
        return project_dir / filename

    def save(self, session: ProjectChatTaskSession) -> ProjectChatTaskSession:
        normalized = ProjectChatTaskSession(**asdict(session))
        if not normalized.id:
            normalized.id = self.new_session_id()
        if not normalized.project_id or not normalized.username or not normalized.chat_session_id:
            raise ValueError("project_id, username and chat_session_id are required")
        normalized.updated_at = _now_iso()
        project_dir = self._project_dir(normalized.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        self._path(
            normalized.project_id,
            normalized.username,
            normalized.chat_session_id,
        ).write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return normalized

    def get(self, project_id: str, username: str, chat_session_id: str) -> ProjectChatTaskSession | None:
        if not project_id or not username or not chat_session_id:
            return None
        path = self._path(project_id, username, chat_session_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        return ProjectChatTaskSession(**raw)

    def list_by_project(self, project_id: str, limit: int = 200) -> list[ProjectChatTaskSession]:
        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            return []
        project_dir = self._project_dir(normalized_project_id)
        if not project_dir.exists():
            return []
        sessions: list[ProjectChatTaskSession] = []
        safe_limit = max(1, min(int(limit or 200), 500))
        for path in sorted(project_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            try:
                sessions.append(ProjectChatTaskSession(**raw))
            except Exception:
                continue
            if len(sessions) >= safe_limit:
                break
        return sessions

    def delete(self, project_id: str, username: str, chat_session_id: str) -> int:
        if not project_id or not username or not chat_session_id:
            return 0
        deleted = 0
        deleted += self.delete_exact(project_id, username, chat_session_id)
        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            return deleted
        for candidate in project_dir.glob(f"{_safe_token(username, max_len=64)}.*.json"):
            if not candidate.exists():
                continue
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            if _normalize_text(raw.get("source_chat_session_id"), 80) != _normalize_text(chat_session_id, 80):
                continue
            candidate.unlink()
            deleted += 1
        return deleted

    def delete_exact(self, project_id: str, username: str, chat_session_id: str) -> int:
        if not project_id or not username or not chat_session_id:
            return 0
        path = self._path(project_id, username, chat_session_id)
        if not path.exists():
            return 0
        path.unlink()
        return 1

    def clear_project(self, project_id: str) -> int:
        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            return 0
        deleted = 0
        for path in project_dir.glob("*.json"):
            path.unlink()
            deleted += 1
        return deleted

    def new_session_id(self) -> str:
        return f"tts-{uuid.uuid4().hex[:10]}"

    def new_node_id(self) -> str:
        return f"ttn-{uuid.uuid4().hex[:10]}"

    def new_archive_chat_session_id(self, source_chat_session_id: str) -> str:
        base = _safe_token(source_chat_session_id or self.new_session_id(), max_len=48)
        return f"{base}.archived.{uuid.uuid4().hex[:8]}"
