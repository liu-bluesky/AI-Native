"""项目 AI 对话记录存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from stores.postgres._connection import connect
from psycopg.rows import dict_row

from stores.json.project_chat_store import (
    ProjectChatMessage,
    ProjectChatSession,
    _normalize_chat_context_text,
    _normalize_chat_source_type,
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

                ALTER TABLE project_chat_sessions
                    ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS platform TEXT NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS connector_id TEXT NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS external_chat_id TEXT NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS external_chat_name TEXT NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS thread_key TEXT NOT NULL DEFAULT '';
                """
            )

    def create_session(
        self,
        project_id: str,
        username: str,
        title: str = "新对话",
        source_context: dict | None = None,
        session_id: str = "",
    ) -> ProjectChatSession:
        context = source_context if isinstance(source_context, dict) else {}
        normalized_session_id = str(session_id or "").strip()
        normalized = ProjectChatSession(
            id=normalized_session_id or f"chat-session-{uuid.uuid4().hex[:12]}",
            project_id=str(project_id or "").strip(),
            username=str(username or "").strip(),
            title=str(title or "新对话").strip() or "新对话",
            source_type=_normalize_chat_source_type(context.get("source_type")),
            platform=_normalize_chat_context_text(context.get("platform"), 40).lower(),
            connector_id=_normalize_chat_context_text(context.get("connector_id"), 120),
            external_chat_id=_normalize_chat_context_text(context.get("external_chat_id"), 200),
            external_chat_name=_normalize_chat_context_text(context.get("external_chat_name"), 200),
            thread_key=_normalize_chat_context_text(context.get("thread_key"), 240),
        )
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_chat_sessions (
                    id, project_id, username, title, preview, message_count,
                    source_type, platform, connector_id, external_chat_id, external_chat_name, thread_key,
                    created_at, updated_at, last_message_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    project_id = EXCLUDED.project_id,
                    username = EXCLUDED.username,
                    title = EXCLUDED.title,
                    source_type = EXCLUDED.source_type,
                    platform = EXCLUDED.platform,
                    connector_id = EXCLUDED.connector_id,
                    external_chat_id = EXCLUDED.external_chat_id,
                    external_chat_name = EXCLUDED.external_chat_name,
                    thread_key = EXCLUDED.thread_key,
                    updated_at = NOW()
                """,
                (
                    normalized.id,
                    normalized.project_id,
                    normalized.username,
                    normalized.title,
                    normalized.preview,
                    normalized.message_count,
                    normalized.source_type,
                    normalized.platform,
                    normalized.connector_id,
                    normalized.external_chat_id,
                    normalized.external_chat_name,
                    normalized.thread_key,
                ),
            )
        return normalized

    def update_session(
        self,
        project_id: str,
        username: str,
        chat_session_id: str,
        *,
        title: str | None = None,
        source_context: dict | None = None,
    ) -> ProjectChatSession | None:
        existing = self.get_session(project_id, username, chat_session_id)
        if existing is None or existing.id == "legacy":
            return None
        context = source_context if isinstance(source_context, dict) else {}
        next_title = str(title if title is not None else existing.title or "").strip() or existing.title
        next_source_type = existing.source_type
        next_platform = existing.platform
        next_connector_id = existing.connector_id
        next_external_chat_id = existing.external_chat_id
        next_external_chat_name = existing.external_chat_name
        next_thread_key = existing.thread_key
        if context:
            next_source_type = _normalize_chat_source_type(context.get("source_type")) or next_source_type
            next_platform = _normalize_chat_context_text(context.get("platform") or next_platform, 40).lower()
            next_connector_id = _normalize_chat_context_text(context.get("connector_id") or next_connector_id, 120)
            next_external_chat_id = _normalize_chat_context_text(context.get("external_chat_id") or next_external_chat_id, 200)
            next_external_chat_name = _normalize_chat_context_text(context.get("external_chat_name") or next_external_chat_name, 200)
            next_thread_key = _normalize_chat_context_text(context.get("thread_key") or next_thread_key, 240)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE project_chat_sessions
                SET title = %s,
                    source_type = %s,
                    platform = %s,
                    connector_id = %s,
                    external_chat_id = %s,
                    external_chat_name = %s,
                    thread_key = %s,
                    updated_at = NOW()
                WHERE project_id = %s AND username = %s AND id = %s
                """,
                (
                    next_title,
                    next_source_type,
                    next_platform,
                    next_connector_id,
                    next_external_chat_id,
                    next_external_chat_name,
                    next_thread_key,
                    project_id,
                    username,
                    existing.id,
                ),
            )
        return self.get_session(project_id, username, existing.id)

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
            source_type=str(getattr(last_item, "source_type", "") or ""),
            platform=str(getattr(last_item, "platform", "") or ""),
            connector_id=str(getattr(last_item, "connector_id", "") or ""),
            external_chat_id=str(getattr(last_item, "external_chat_id", "") or ""),
            external_chat_name=str(getattr(last_item, "external_chat_name", "") or ""),
            thread_key=str(getattr(last_item, "thread_key", "") or ""),
            created_at=str(messages[0].created_at or _now_iso()),
            updated_at=str(last_item.created_at or _now_iso()),
            last_message_at=str(last_item.created_at or _now_iso()),
        )

    def list_sessions(self, project_id: str, username: str, limit: int = 50) -> list[ProjectChatSession]:
        safe_limit = max(1, min(int(limit or 50), 200))
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, project_id, username, title, preview, message_count,
                       source_type, platform, connector_id, external_chat_id, external_chat_name, thread_key,
                       created_at, updated_at, last_message_at
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
                source_type=str(row.get("source_type") or ""),
                platform=str(row.get("platform") or ""),
                connector_id=str(row.get("connector_id") or ""),
                external_chat_id=str(row.get("external_chat_id") or ""),
                external_chat_name=str(row.get("external_chat_name") or ""),
                thread_key=str(row.get("thread_key") or ""),
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

    def get_session(self, project_id: str, username: str, chat_session_id: str) -> ProjectChatSession | None:
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_session_id:
            return None
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, project_id, username, title, preview, message_count,
                       source_type, platform, connector_id, external_chat_id, external_chat_name, thread_key,
                       created_at, updated_at, last_message_at
                FROM project_chat_sessions
                WHERE project_id = %s AND username = %s AND id = %s
                """,
                (project_id, username, normalized_session_id),
            )
            row = cur.fetchone()
        if not row:
            return None
        return ProjectChatSession(
            id=str(row["id"] or ""),
            project_id=str(row["project_id"] or project_id),
            username=str(row["username"] or username),
            title=str(row["title"] or "新对话"),
            preview=str(row["preview"] or ""),
            message_count=max(0, int(row["message_count"] or 0)),
            source_type=str(row.get("source_type") or ""),
            platform=str(row.get("platform") or ""),
            connector_id=str(row.get("connector_id") or ""),
            external_chat_id=str(row.get("external_chat_id") or ""),
            external_chat_name=str(row.get("external_chat_name") or ""),
            thread_key=str(row.get("thread_key") or ""),
            created_at=_to_iso(row.get("created_at")),
            updated_at=_to_iso(row.get("updated_at")),
            last_message_at=_to_iso(row.get("last_message_at")),
        )

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
                    source_type=_normalize_chat_source_type(payload.get("source_type")),
                    platform=_normalize_chat_context_text(payload.get("platform"), 40).lower(),
                    connector_id=_normalize_chat_context_text(payload.get("connector_id"), 120),
                    external_chat_id=_normalize_chat_context_text(payload.get("external_chat_id"), 200),
                    external_chat_name=_normalize_chat_context_text(payload.get("external_chat_name"), 200),
                    external_message_id=_normalize_chat_context_text(payload.get("external_message_id"), 200),
                    sender_id=_normalize_chat_context_text(payload.get("sender_id"), 200),
                    sender_name=_normalize_chat_context_text(payload.get("sender_name"), 120),
                    thread_key=_normalize_chat_context_text(payload.get("thread_key"), 240),
                    attachments=_normalize_attachments(payload.get("attachments")),
                    images=_normalize_attachments(payload.get("images")),
                    videos=_normalize_attachments(payload.get("videos")),
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
        chat_session_id = str(message.chat_session_id or "").strip()
        existing_session = self.get_session(project_id, username, chat_session_id)
        normalized = ProjectChatMessage(
            id=str(message.id or f"chat-{uuid.uuid4().hex[:12]}"),
            project_id=project_id,
            username=username,
            role=role,
            content=content,
            chat_session_id=chat_session_id,
            display_mode=str(message.display_mode or "").strip(),
            source_type=_normalize_chat_source_type(message.source_type or getattr(existing_session, "source_type", "")),
            platform=_normalize_chat_context_text(message.platform or getattr(existing_session, "platform", ""), 40).lower(),
            connector_id=_normalize_chat_context_text(message.connector_id or getattr(existing_session, "connector_id", ""), 120),
            external_chat_id=_normalize_chat_context_text(message.external_chat_id or getattr(existing_session, "external_chat_id", ""), 200),
            external_chat_name=_normalize_chat_context_text(message.external_chat_name or getattr(existing_session, "external_chat_name", ""), 200),
            external_message_id=_normalize_chat_context_text(message.external_message_id, 200),
            sender_id=_normalize_chat_context_text(message.sender_id, 200),
            sender_name=_normalize_chat_context_text(message.sender_name, 120),
            thread_key=_normalize_chat_context_text(message.thread_key or getattr(existing_session, "thread_key", ""), 240),
            attachments=_normalize_attachments(message.attachments),
            images=_normalize_attachments(message.images),
            videos=_normalize_attachments(message.videos),
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
                        id, project_id, username, title, preview, message_count,
                        source_type, platform, connector_id, external_chat_id, external_chat_name, thread_key,
                        created_at, updated_at, last_message_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE
                    SET preview = EXCLUDED.preview,
                        updated_at = NOW(),
                        last_message_at = NOW(),
                        message_count = project_chat_sessions.message_count + 1,
                        source_type = COALESCE(NULLIF(project_chat_sessions.source_type, ''), EXCLUDED.source_type),
                        platform = COALESCE(NULLIF(project_chat_sessions.platform, ''), EXCLUDED.platform),
                        connector_id = COALESCE(NULLIF(project_chat_sessions.connector_id, ''), EXCLUDED.connector_id),
                        external_chat_id = COALESCE(NULLIF(project_chat_sessions.external_chat_id, ''), EXCLUDED.external_chat_id),
                        external_chat_name = COALESCE(NULLIF(project_chat_sessions.external_chat_name, ''), EXCLUDED.external_chat_name),
                        thread_key = COALESCE(NULLIF(project_chat_sessions.thread_key, ''), EXCLUDED.thread_key),
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
                        normalized.source_type,
                        normalized.platform,
                        normalized.connector_id,
                        normalized.external_chat_id,
                        normalized.external_chat_name,
                        normalized.thread_key,
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
