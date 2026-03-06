"""项目 AI 对话记录存储层（JSON 实现）"""

from __future__ import annotations

import json
import re
import shutil
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


def _normalize_attachments(values: list[str] | None) -> list[str]:
    return [
        str(item or "").strip()
        for item in (values or [])
        if str(item or "").strip()
    ]


@dataclass
class ProjectChatMessage:
    project_id: str
    username: str
    role: str
    content: str
    attachments: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"chat-{uuid.uuid4().hex[:12]}")
    created_at: str = field(default_factory=_now_iso)


class ProjectChatStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "project-chat"
        self._root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        return self._root / _safe_token(project_id)

    def _messages_path(self, project_id: str, username: str) -> Path:
        return self._project_dir(project_id) / f"{_safe_token(username, max_len=64)}.json"

    def _read_messages(self, project_id: str, username: str) -> list[ProjectChatMessage]:
        path = self._messages_path(project_id, username)
        if not path.exists():
            return []
        try:
            raw_list = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        messages: list[ProjectChatMessage] = []
        for raw in raw_list if isinstance(raw_list, list) else []:
            if not isinstance(raw, dict):
                continue
            role = str(raw.get("role") or "").strip().lower()
            if role not in {"user", "assistant", "system"}:
                continue
            content = str(raw.get("content") or "").strip()
            if not content:
                continue
            messages.append(
                ProjectChatMessage(
                    id=str(raw.get("id") or f"chat-{uuid.uuid4().hex[:12]}"),
                    project_id=str(raw.get("project_id") or project_id),
                    username=str(raw.get("username") or username),
                    role=role,
                    content=content,
                    attachments=_normalize_attachments(raw.get("attachments")),
                    images=_normalize_attachments(raw.get("images")),
                    created_at=str(raw.get("created_at") or _now_iso()),
                )
            )
        messages.sort(key=lambda item: str(item.created_at or ""))
        return messages

    def list_messages(self, project_id: str, username: str, limit: int = 200) -> list[ProjectChatMessage]:
        safe_limit = max(1, min(int(limit or 200), 1000))
        messages = self._read_messages(project_id, username)
        if len(messages) <= safe_limit:
            return messages
        return messages[-safe_limit:]

    def append_message(self, message: ProjectChatMessage) -> ProjectChatMessage:
        project_id = str(message.project_id or "").strip()
        username = str(message.username or "").strip()
        if not project_id or not username:
            raise ValueError("project_id and username are required")
        role = str(message.role or "").strip().lower()
        if role not in {"user", "assistant", "system"}:
            raise ValueError("role must be user/assistant/system")
        content = str(message.content or "").strip()
        if not content:
            raise ValueError("content is required")
        project_dir = self._project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        path = self._messages_path(project_id, username)

        normalized = ProjectChatMessage(
            id=str(message.id or f"chat-{uuid.uuid4().hex[:12]}"),
            project_id=project_id,
            username=username,
            role=role,
            content=content,
            attachments=_normalize_attachments(message.attachments),
            images=_normalize_attachments(message.images),
            created_at=str(message.created_at or _now_iso()),
        )
        current = self._read_messages(project_id, username)
        current.append(normalized)
        if len(current) > 1000:
            current = current[-1000:]
        path.write_text(
            json.dumps([asdict(item) for item in current], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return normalized

    def clear_messages(self, project_id: str, username: str) -> int:
        path = self._messages_path(project_id, username)
        if not path.exists():
            return 0
        try:
            messages = self._read_messages(project_id, username)
            count = len(messages)
        except Exception:
            count = 0
        path.unlink()
        return count

    def clear_project(self, project_id: str) -> int:
        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            return 0
        count = len(list(project_dir.glob("*.json")))
        shutil.rmtree(project_dir, ignore_errors=True)
        return count

