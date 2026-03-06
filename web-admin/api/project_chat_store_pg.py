"""项目 AI 对话记录存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from psycopg import connect
from psycopg.rows import dict_row

from project_chat_store import ProjectChatMessage, _normalize_attachments, _now_iso


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

                CREATE INDEX IF NOT EXISTS idx_project_chat_lookup
                ON project_chat_messages (project_id, username, created_at DESC);
                """
            )

    def list_messages(self, project_id: str, username: str, limit: int = 200) -> list[ProjectChatMessage]:
        safe_limit = max(1, min(int(limit or 200), 1000))
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_chat_messages
                WHERE project_id = %s AND username = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (project_id, username, safe_limit),
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
        return normalized

    def clear_messages(self, project_id: str, username: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM project_chat_messages WHERE project_id = %s AND username = %s",
                (project_id, username),
            )
            return int(cur.rowcount or 0)

    def clear_project(self, project_id: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM project_chat_messages WHERE project_id = %s",
                (project_id,),
            )
            return int(cur.rowcount or 0)

