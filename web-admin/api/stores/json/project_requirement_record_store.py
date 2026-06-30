"""项目需求记录存储层（JSON 实现）。"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


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


@dataclass
class ProjectRequirementRecord:
    id: str
    project_id: str
    username: str
    chat_session_id: str
    source_chat_session_id: str = ""
    title: str = ""
    root_goal: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, 80)
        self.project_id = _normalize_text(self.project_id, 80)
        self.username = _normalize_text(self.username, 80)
        self.chat_session_id = _normalize_text(self.chat_session_id, 120)
        self.source_chat_session_id = _normalize_text(self.source_chat_session_id, 120)
        self.root_goal = _normalize_text(self.root_goal, 2000)
        self.title = _normalize_text(self.title, 200) or self.root_goal[:200]
        self.created_at = _normalize_text(self.created_at or _now_iso(), 40) or _now_iso()
        self.updated_at = _normalize_text(self.updated_at or _now_iso(), 40) or _now_iso()


class ProjectRequirementRecordStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "project-requirement-records"
        self._root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        return self._root / _safe_token(project_id)

    def _path(self, project_id: str, username: str, record_id: str) -> Path:
        return (
            self._project_dir(project_id)
            / f"{_safe_token(username, max_len=64)}.{_safe_token(record_id, max_len=120)}.json"
        )

    def save(self, record: ProjectRequirementRecord) -> ProjectRequirementRecord:
        normalized = ProjectRequirementRecord(**asdict(record))
        if not normalized.id:
            normalized.id = self.new_record_id()
        if not normalized.project_id or not normalized.username or not normalized.chat_session_id:
            raise ValueError("project_id, username and chat_session_id are required")
        normalized.updated_at = _now_iso()
        project_dir = self._project_dir(normalized.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        self._path(normalized.project_id, normalized.username, normalized.id).write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return normalized

    def get(self, project_id: str, username: str, record_id: str) -> ProjectRequirementRecord | None:
        if not project_id or not username or not record_id:
            return None
        path = self._path(project_id, username, record_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        try:
            return ProjectRequirementRecord(**raw)
        except Exception:
            return None

    def list_by_project(self, project_id: str, limit: int = 200) -> list[ProjectRequirementRecord]:
        safe_limit = max(1, min(int(limit or 200), 500))
        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            return []
        records: list[ProjectRequirementRecord] = []
        for path in project_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            try:
                records.append(ProjectRequirementRecord(**raw))
            except Exception:
                continue
        records.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        return records[:safe_limit]

    def delete(self, project_id: str, username: str, record_id: str) -> int:
        if not project_id or not username or not record_id:
            return 0
        path = self._path(project_id, username, record_id)
        if not path.exists():
            return 0
        path.unlink()
        return 1

    def delete_by_id(self, project_id: str, record_id: str) -> int:
        if not project_id or not record_id:
            return 0
        removed = 0
        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            return 0
        suffix = f".{_safe_token(record_id, max_len=120)}.json"
        for path in project_dir.glob(f"*{suffix}"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    def new_record_id(self) -> str:
        return f"req-{uuid.uuid4().hex[:12]}"
