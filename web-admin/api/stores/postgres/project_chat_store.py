"""项目 AI 对话记录存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from psycopg import connect
from psycopg.rows import dict_row

from stores.json.project_chat_store import (
    ProjectChatMessage,
    ProjectChatSession,
    _normalize_attachments,
    _now_iso,
)


def _session_title_from_content(content: str) -> str:
    text = " ".join(str(content or "").strip().split())
    if not text:
        return "新对话"
    return text[:24] + ("..." if len(text) > 24 else "")


def _to_iso(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    text = str(value or "").strip()
    return text or _now_iso()


class ProjectChatStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_chat_messages (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS project_chat_sessions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '新对话',
                    preview TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_project_chat_lookup
                ON project_chat_messages (project_id, username, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_project_chat_sessions_lookup
                ON project_chat_sessions (project_id, username, updated_at DESC);
                """
            )

    def create_session(self, project_id: str, username: str, title: str = "新对话") -> ProjectChatSession:
        normalized = ProjectChatSession(
            id=f"chat-session-{uuid.uuid4().hex[:12]}",
            project_id=str(project_id or "").strip(),
            username=str(username or "").strip(),
            title=str(title or "新对话").strip() or "新对话",
        )
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_chat_sessions (
                    id, project_id, username, title, preview, message_count, created_at, updated_at, last_message_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
                """,
                (
                    normalized.id,
                    normalized.project_id,
                    normalized.username,
                    normalized.title,
                    normalized.preview,
                    normalized.message_count,
                ),
            )
        return normalized

    def _legacy_session(self, project_id: str, username: str) -> ProjectChatSession | None:
        messages = self.list_messages(project_id, username, limit=0, chat_session_id="legacy")
        if not messages:
            return None
        first_user = next((item for item in messages if item.role == "user"), messages[0])
        last_item = messages[-1]
        return ProjectChatSession(
            id="legacy",
            project_id=project_id,
            username=username,
            title=_session_title_from_content(first_user.content) or "历史会话",
            preview=str(last_item.content or "")[:80],
            message_count=len(messages),
            created_at=str(messages[0].created_at or _now_iso()),
            updated_at=str(last_item.created_at or _now_iso()),
            last_message_at=str(last_item.created_at or _now_iso()),
        )

    def list_sessions(self, project_id: str, username: str, limit: int = 50) -> list[ProjectChatSession]:
        safe_limit = max(1, min(int(limit or 50), 200))
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, project_id, username, title, preview, message_count, created_at, updated_at, last_message_at
                FROM project_chat_sessions
                WHERE project_id = %s AND username = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (project_id, username, safe_limit),
            )
            rows = cur.fetchall()
        sessions = [
            ProjectChatSession(
                id=str(row["id"] or ""),
                project_id=str(row["project_id"] or project_id),
                username=str(row["username"] or username),
                title=str(row["title"] or "新对话"),
                preview=str(row["preview"] or ""),
                message_count=max(0, int(row["message_count"] or 0)),
                created_at=_to_iso(row.get("created_at")),
                updated_at=_to_iso(row.get("updated_at")),
                last_message_at=_to_iso(row.get("last_message_at")),
            )
            for row in rows
            if str(row.get("id") or "").strip()
        ]
        legacy = self._legacy_session(project_id, username)
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
        normalized_session_id = str(chat_session_id or "").strip()
        with self._conn.cursor() as cur:
            if normalized_session_id == "legacy":
                if safe_limit is None:
                    cur.execute(
                        """
                        SELECT payload
                        FROM project_chat_messages
                        WHERE project_id = %s
                          AND username = %s
                          AND COALESCE(payload->>'chat_session_id', '') = ''
                        ORDER BY created_at DESC
                        OFFSET %s
                        """,
                        (project_id, username, safe_offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT payload
                        FROM project_chat_messages
                        WHERE project_id = %s
                          AND username = %s
                          AND COALESCE(payload->>'chat_session_id', '') = ''
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (project_id, username, safe_limit, safe_offset),
                    )
            elif normalized_session_id:
                if safe_limit is None:
                    cur.execute(
                        """
                        SELECT payload
                        FROM project_chat_messages
                        WHERE project_id = %s
                          AND username = %s
                          AND COALESCE(payload->>'chat_session_id', '') = %s
                        ORDER BY created_at DESC
                        OFFSET %s
                        """,
                        (project_id, username, normalized_session_id, safe_offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT payload
                        FROM project_chat_messages
                        WHERE project_id = %s
                          AND username = %s
                          AND COALESCE(payload->>'chat_session_id', '') = %s
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (project_id, username, normalized_session_id, safe_limit, safe_offset),
                    )
            else:
                if safe_limit is None:
                    cur.execute(
                        """
                        SELECT payload
                        FROM project_chat_messages
                        WHERE project_id = %s AND username = %s
                        ORDER BY created_at DESC
                        OFFSET %s
                        """,
                        (project_id, username, safe_offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT payload
                        FROM project_chat_messages
                        WHERE project_id = %s AND username = %s
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (project_id, username, safe_limit, safe_offset),
                    )
            rows = cur.fetchall()
        items: list[ProjectChatMessage] = []
        for row in reversed(rows):
            payload = row["payload"] or {}
            items.append(
                ProjectChatMessage(
                    id=str(payload.get("id") or f"chat-{uuid.uuid4().hex[:12]}"),
                    project_id=str(payload.get("project_id") or project_id),
                    username=str(payload.get("username") or username),
                    role=str(payload.get("role") or "assistant"),
                    content=str(payload.get("content") or ""),
                    chat_session_id=str(payload.get("chat_session_id") or "").strip(),
                    display_mode=str(payload.get("display_mode") or "").strip(),
                    attachments=_normalize_attachments(payload.get("attachments")),
                    images=_normalize_attachments(payload.get("images")),
                    created_at=str(payload.get("created_at") or _now_iso()),
                )
            )
        return items

    def append_message(self, message: ProjectChatMessage) -> ProjectChatMessage:
        project_id = str(message.project_id or "").strip()
        username = str(message.username or "").strip()
        role = str(message.role or "").strip().lower()
        content = str(message.content or "").strip()
        if not project_id or not username or not role or not content:
            raise ValueError("project_id/username/role/content are required")
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
        payload = json.dumps(asdict(normalized), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_chat_messages (id, project_id, username, payload, created_at)
                VALUES (%s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, created_at = NOW()
                """,
                (normalized.id, normalized.project_id, normalized.username, payload),
            )
            if normalized.chat_session_id:
                title = (
                    _session_title_from_content(normalized.content)
                    if normalized.role == "user"
                    else "新对话"
                )
                cur.execute(
                    """
                    INSERT INTO project_chat_sessions (
                        id, project_id, username, title, preview, message_count, created_at, updated_at, last_message_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 1, NOW(), NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE
                    SET preview = EXCLUDED.preview,
                        updated_at = NOW(),
                        last_message_at = NOW(),
                        message_count = project_chat_sessions.message_count + 1,
                        title = CASE
                            WHEN project_chat_sessions.title = '新对话' AND %s = 'user'
                                THEN %s
                            ELSE project_chat_sessions.title
                        END
                    """,
                    (
                        normalized.chat_session_id,
                        normalized.project_id,
                        normalized.username,
                        title,
                        str(normalized.content or "")[:80],
                        normalized.role,
                        _session_title_from_content(normalized.content),
                    ),
                )
        return normalized

    def clear_messages(self, project_id: str, username: str, chat_session_id: str = "") -> int:
        normalized_session_id = str(chat_session_id or "").strip()
        with self._conn.cursor() as cur:
            if normalized_session_id == "legacy":
                cur.execute(
                    """
                    DELETE FROM project_chat_messages
                    WHERE project_id = %s
                      AND username = %s
                      AND COALESCE(payload->>'chat_session_id', '') = ''
                    """,
                    (project_id, username),
                )
                return int(cur.rowcount or 0)
            if normalized_session_id:
                cur.execute(
                    """
                    DELETE FROM project_chat_messages
                    WHERE project_id = %s
                      AND username = %s
                      AND COALESCE(payload->>'chat_session_id', '') = %s
                    """,
                    (project_id, username, normalized_session_id),
                )
                removed = int(cur.rowcount or 0)
                cur.execute(
                    """
                    DELETE FROM project_chat_sessions
                    WHERE project_id = %s AND username = %s AND id = %s
                    """,
                    (project_id, username, normalized_session_id),
                )
                return removed
            cur.execute(
                "DELETE FROM project_chat_messages WHERE project_id = %s AND username = %s",
                (project_id, username),
            )
            removed = int(cur.rowcount or 0)
            cur.execute(
                "DELETE FROM project_chat_sessions WHERE project_id = %s AND username = %s",
                (project_id, username),
            )
            return removed

    def truncate_messages(self, project_id: str, username: str, message_id: str, chat_session_id: str = "") -> int:
        normalized_message_id = str(message_id or "").strip()
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_message_id:
            return 0
        records = self.list_messages(
            project_id,
            username,
            limit=0,
            chat_session_id=normalized_session_id,
        )
        target_index = next(
            (index for index, item in enumerate(records) if str(item.id or "").strip() == normalized_message_id),
            -1,
        )
        if target_index < 0:
            return 0
        removable_ids = [
            str(item.id or "").strip()
            for item in records[target_index:]
            if str(item.id or "").strip()
        ]
        if not removable_ids:
            return 0
        remaining = records[:target_index]
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM project_chat_messages
                WHERE project_id = %s
                  AND username = %s
                  AND id = ANY(%s)
                """,
                (project_id, username, removable_ids),
            )
            removed = int(cur.rowcount or 0)
            if normalized_session_id and normalized_session_id != "legacy":
                if not remaining:
                    cur.execute(
                        """
                        DELETE FROM project_chat_sessions
                        WHERE project_id = %s AND username = %s AND id = %s
                        """,
                        (project_id, username, normalized_session_id),
                    )
                else:
                    last_item = remaining[-1]
                    cur.execute(
                        """
                        UPDATE project_chat_sessions
                        SET preview = %s,
                            message_count = %s,
                            updated_at = NOW(),
                            last_message_at = %s::timestamptz
                        WHERE project_id = %s AND username = %s AND id = %s
                        """,
                        (
                            str(last_item.content or "")[:80],
                            len(remaining),
                            str(last_item.created_at or _now_iso()),
                            project_id,
                            username,
                            normalized_session_id,
                        ),
                    )
            return removed

    def delete_session(self, project_id: str, username: str, chat_session_id: str) -> int:
        return self.clear_messages(project_id, username, chat_session_id)

    def clear_project(self, project_id: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM project_chat_messages WHERE project_id = %s",
                (project_id,),
            )
            removed = int(cur.rowcount or 0)
            cur.execute(
                "DELETE FROM project_chat_sessions WHERE project_id = %s",
                (project_id,),
            )
            return removed
