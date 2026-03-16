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
    chat_session_id: str = ""
    display_mode: str = ""
    attachments: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"chat-{uuid.uuid4().hex[:12]}")
    created_at: str = field(default_factory=_now_iso)


@dataclass
class ProjectChatSession:
    id: str
    project_id: str
    username: str
    title: str = "新对话"
    preview: str = ""
    message_count: int = 0
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    last_message_at: str = field(default_factory=_now_iso)


def _session_title_from_content(content: str) -> str:
    text = " ".join(str(content or "").strip().split())
    if not text:
        return "新对话"
    return text[:24] + ("..." if len(text) > 24 else "")


class ProjectChatStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "project-chat"
        self._root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        return self._root / _safe_token(project_id)

    def _messages_path(self, project_id: str, username: str) -> Path:
        return self._project_dir(project_id) / f"{_safe_token(username, max_len=64)}.json"

    def _sessions_path(self, project_id: str, username: str) -> Path:
        return self._project_dir(project_id) / f"{_safe_token(username, max_len=64)}.sessions.json"

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
                    chat_session_id=str(raw.get("chat_session_id") or "").strip(),
                    display_mode=str(raw.get("display_mode") or "").strip(),
                    attachments=_normalize_attachments(raw.get("attachments")),
                    images=_normalize_attachments(raw.get("images")),
                    created_at=str(raw.get("created_at") or _now_iso()),
                )
            )
        messages.sort(key=lambda item: str(item.created_at or ""))
        return messages

    def _read_sessions(self, project_id: str, username: str) -> list[ProjectChatSession]:
        path = self._sessions_path(project_id, username)
        if not path.exists():
            return []
        try:
            raw_list = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        sessions: list[ProjectChatSession] = []
        for raw in raw_list if isinstance(raw_list, list) else []:
            if not isinstance(raw, dict):
                continue
            session_id = str(raw.get("id") or "").strip()
            if not session_id:
                continue
            sessions.append(
                ProjectChatSession(
                    id=session_id,
                    project_id=str(raw.get("project_id") or project_id),
                    username=str(raw.get("username") or username),
                    title=str(raw.get("title") or "新对话"),
                    preview=str(raw.get("preview") or ""),
                    message_count=max(0, int(raw.get("message_count") or 0)),
                    created_at=str(raw.get("created_at") or _now_iso()),
                    updated_at=str(raw.get("updated_at") or raw.get("created_at") or _now_iso()),
                    last_message_at=str(raw.get("last_message_at") or raw.get("updated_at") or raw.get("created_at") or _now_iso()),
                )
            )
        sessions.sort(key=lambda item: str(item.updated_at or ""), reverse=True)
        return sessions

    def _write_sessions(self, project_id: str, username: str, sessions: list[ProjectChatSession]) -> None:
        project_dir = self._project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        path = self._sessions_path(project_id, username)
        path.write_text(
            json.dumps([asdict(item) for item in sessions], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _rewrite_messages(self, project_id: str, username: str, messages: list[ProjectChatMessage]) -> None:
        project_dir = self._project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        path = self._messages_path(project_id, username)
        path.write_text(
            json.dumps([asdict(item) for item in messages], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if not messages and path.exists():
            path.unlink()

    def _refresh_session_snapshot(
        self,
        project_id: str,
        username: str,
        chat_session_id: str,
        messages: list[ProjectChatMessage],
    ) -> None:
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_session_id or normalized_session_id == "legacy":
            return
        sessions = self._read_sessions(project_id, username)
        remaining = [
            item
            for item in messages
            if str(item.chat_session_id or "").strip() == normalized_session_id
        ]
        sessions = [item for item in sessions if item.id != normalized_session_id]
        if not remaining:
            self._write_sessions(project_id, username, sessions)
            return
        first_user = next((item for item in remaining if item.role == "user"), remaining[0])
        last_item = remaining[-1]
        existing = next(
            (item for item in self._read_sessions(project_id, username) if item.id == normalized_session_id),
            None,
        )
        snapshot = ProjectChatSession(
            id=normalized_session_id,
            project_id=project_id,
            username=username,
            title=str(getattr(existing, "title", "") or "").strip() or _session_title_from_content(first_user.content),
            preview=str(last_item.content or "")[:80],
            message_count=len(remaining),
            created_at=str(getattr(existing, "created_at", "") or remaining[0].created_at or _now_iso()),
            updated_at=_now_iso(),
            last_message_at=str(last_item.created_at or _now_iso()),
        )
        sessions.append(snapshot)
        sessions.sort(key=lambda item: str(item.updated_at or ""), reverse=True)
        self._write_sessions(project_id, username, sessions)

    def create_session(self, project_id: str, username: str, title: str = "新对话") -> ProjectChatSession:
        normalized = ProjectChatSession(
            id=f"chat-session-{uuid.uuid4().hex[:12]}",
            project_id=str(project_id or "").strip(),
            username=str(username or "").strip(),
            title=str(title or "新对话").strip() or "新对话",
        )
        sessions = self._read_sessions(normalized.project_id, normalized.username)
        sessions = [item for item in sessions if item.id != normalized.id]
        sessions.insert(0, normalized)
        self._write_sessions(normalized.project_id, normalized.username, sessions)
        return normalized

    def _legacy_session(self, project_id: str, username: str, messages: list[ProjectChatMessage]) -> ProjectChatSession | None:
        legacy_messages = [item for item in messages if not str(item.chat_session_id or "").strip()]
        if not legacy_messages:
            return None
        first_user = next((item for item in legacy_messages if item.role == "user"), legacy_messages[0])
        last_item = legacy_messages[-1]
        return ProjectChatSession(
            id="legacy",
            project_id=project_id,
            username=username,
            title=_session_title_from_content(first_user.content) or "历史会话",
            preview=str(last_item.content or "")[:80],
            message_count=len(legacy_messages),
            created_at=str(legacy_messages[0].created_at or _now_iso()),
            updated_at=str(last_item.created_at or _now_iso()),
            last_message_at=str(last_item.created_at or _now_iso()),
        )

    def list_sessions(self, project_id: str, username: str, limit: int = 50) -> list[ProjectChatSession]:
        safe_limit = max(1, min(int(limit or 50), 200))
        sessions = self._read_sessions(project_id, username)
        legacy = self._legacy_session(project_id, username, self._read_messages(project_id, username))
        if legacy is not None:
            sessions.append(legacy)
        sessions.sort(key=lambda item: str(item.updated_at or ""), reverse=True)
        return sessions[:safe_limit]

    def list_messages(
        self,
        project_id: str,
        username: str,
        limit: int = 200,
        chat_session_id: str = "",
        offset: int = 0,
    ) -> list[ProjectChatMessage]:
        parsed_limit = int(limit or 0)
        safe_limit = None if parsed_limit <= 0 else max(1, min(parsed_limit, 1000))
        safe_offset = max(0, int(offset or 0))
        messages = self._read_messages(project_id, username)
        normalized_session_id = str(chat_session_id or "").strip()
        if normalized_session_id:
            if normalized_session_id == "legacy":
                messages = [
                    item for item in messages if not str(item.chat_session_id or "").strip()
                ]
            else:
                messages = [
                    item
                    for item in messages
                    if str(item.chat_session_id or "").strip() == normalized_session_id
                ]
        if safe_offset:
            if safe_offset >= len(messages):
                return []
            messages = messages[: len(messages) - safe_offset]
        if safe_limit is None or len(messages) <= safe_limit:
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
            chat_session_id=str(message.chat_session_id or "").strip(),
            display_mode=str(message.display_mode or "").strip(),
            attachments=_normalize_attachments(message.attachments),
            images=_normalize_attachments(message.images),
            created_at=str(message.created_at or _now_iso()),
        )
        current = self._read_messages(project_id, username)
        current.append(normalized)
        self._rewrite_messages(project_id, username, current)
        if normalized.chat_session_id:
            sessions = self._read_sessions(project_id, username)
            existing = next(
                (item for item in sessions if item.id == normalized.chat_session_id),
                None,
            )
            now = str(normalized.created_at or _now_iso())
            if existing is None:
                existing = ProjectChatSession(
                    id=normalized.chat_session_id,
                    project_id=project_id,
                    username=username,
                    title=_session_title_from_content(normalized.content)
                    if normalized.role == "user"
                    else "新对话",
                    preview=str(normalized.content or "")[:80],
                    message_count=1,
                    created_at=now,
                    updated_at=now,
                    last_message_at=now,
                )
                sessions.insert(0, existing)
            else:
                existing.preview = str(normalized.content or "")[:80]
                existing.message_count = max(0, int(existing.message_count or 0)) + 1
                existing.updated_at = now
                existing.last_message_at = now
                if (
                    normalized.role == "user"
                    and (not str(existing.title or "").strip() or str(existing.title or "").strip() == "新对话")
                ):
                    existing.title = _session_title_from_content(normalized.content)
            sessions = [item for item in sessions if item.id != existing.id] + [existing]
            sessions.sort(key=lambda item: str(item.updated_at or ""), reverse=True)
            self._write_sessions(project_id, username, sessions)
        return normalized

    def clear_messages(self, project_id: str, username: str, chat_session_id: str = "") -> int:
        normalized_session_id = str(chat_session_id or "").strip()
        path = self._messages_path(project_id, username)
        try:
            messages = self._read_messages(project_id, username)
        except Exception:
            messages = []
        if not normalized_session_id:
            count = len(messages)
            if path.exists():
                path.unlink()
            sessions_path = self._sessions_path(project_id, username)
            if sessions_path.exists():
                sessions_path.unlink()
            return count
        remaining: list[ProjectChatMessage] = []
        removed = 0
        for item in messages:
            item_session_id = str(item.chat_session_id or "").strip()
            if normalized_session_id == "legacy":
                matched = not item_session_id
            else:
                matched = item_session_id == normalized_session_id
            if matched:
                removed += 1
                continue
            remaining.append(item)
        self._rewrite_messages(project_id, username, remaining)
        if normalized_session_id != "legacy":
            sessions = [
                item
                for item in self._read_sessions(project_id, username)
                if item.id != normalized_session_id
            ]
            self._write_sessions(project_id, username, sessions)
        return removed

    def truncate_messages(self, project_id: str, username: str, message_id: str, chat_session_id: str = "") -> int:
        normalized_message_id = str(message_id or "").strip()
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_message_id:
            return 0
        messages = self._read_messages(project_id, username)
        remaining: list[ProjectChatMessage] = []
        removed = 0
        matched = False
        for item in messages:
            item_session_id = str(item.chat_session_id or "").strip()
            in_scope = (
                (normalized_session_id == "legacy" and not item_session_id)
                or (normalized_session_id and normalized_session_id != "legacy" and item_session_id == normalized_session_id)
                or (not normalized_session_id)
            )
            if not in_scope:
                remaining.append(item)
                continue
            if not matched and item.id == normalized_message_id:
                matched = True
            if matched:
                removed += 1
                continue
            remaining.append(item)
        if not matched:
            return 0
        self._rewrite_messages(project_id, username, remaining)
        self._refresh_session_snapshot(project_id, username, normalized_session_id, remaining)
        return removed

    def delete_session(self, project_id: str, username: str, chat_session_id: str) -> int:
        return self.clear_messages(project_id, username, chat_session_id)

    def clear_project(self, project_id: str) -> int:
        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            return 0
        count = len(list(project_dir.glob("*.json")))
        shutil.rmtree(project_dir, ignore_errors=True)
        return count
