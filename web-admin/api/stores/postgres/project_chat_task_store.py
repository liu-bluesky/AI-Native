"""项目聊天任务树存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from psycopg.rows import dict_row

from stores.json.project_chat_task_store import ProjectChatTaskSession, _now_iso
from stores.postgres._connection import connect


class ProjectChatTaskStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_chat_task_sessions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    chat_session_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_project_chat_task_session_scope
                    ON project_chat_task_sessions (project_id, username, chat_session_id);
                CREATE INDEX IF NOT EXISTS idx_project_chat_task_sessions_project_updated
                    ON project_chat_task_sessions (project_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_project_chat_task_sessions_project_source_session
                    ON project_chat_task_sessions (project_id, ((COALESCE(payload->>'source_session_id', ''))));
                CREATE INDEX IF NOT EXISTS idx_project_chat_task_sessions_project_source_chat
                    ON project_chat_task_sessions (project_id, ((COALESCE(payload->>'source_chat_session_id', ''))));
                """
            )

    def save(self, session: ProjectChatTaskSession) -> ProjectChatTaskSession:
        normalized = ProjectChatTaskSession(**asdict(session))
        if not normalized.id:
            normalized.id = self.new_session_id()
        normalized.updated_at = _now_iso()
        payload = json.dumps(asdict(normalized), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_chat_task_sessions (
                    id, project_id, username, chat_session_id, payload, updated_at
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (project_id, username, chat_session_id) DO UPDATE
                SET id = EXCLUDED.id,
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                """,
                (
                    normalized.id,
                    normalized.project_id,
                    normalized.username,
                    normalized.chat_session_id,
                    payload,
                ),
            )
        return normalized

    def get(self, project_id: str, username: str, chat_session_id: str) -> ProjectChatTaskSession | None:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_chat_session_id = str(chat_session_id or "").strip()
        if not normalized_project_id or not normalized_username or not normalized_chat_session_id:
            return None
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_chat_task_sessions
                WHERE project_id = %s AND username = %s AND chat_session_id = %s
                """,
                (normalized_project_id, normalized_username, normalized_chat_session_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return ProjectChatTaskSession(**row["payload"])

    def list_by_project(self, project_id: str, limit: int = 200) -> list[ProjectChatTaskSession]:
        normalized_project_id = str(project_id or "").strip()
        safe_limit = max(1, min(int(limit or 200), 500))
        if not normalized_project_id:
            return []
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_chat_task_sessions
                WHERE project_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (normalized_project_id, safe_limit),
            )
            rows = cur.fetchall() or []
        sessions: list[ProjectChatTaskSession] = []
        for row in rows:
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            try:
                sessions.append(ProjectChatTaskSession(**payload))
            except Exception:
                continue
        return sessions

    def delete(self, project_id: str, username: str, chat_session_id: str) -> int:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_chat_session_id = str(chat_session_id or "").strip()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM project_chat_task_sessions
                WHERE project_id = %s
                  AND username = %s
                  AND (
                    chat_session_id = %s
                    OR COALESCE(payload->>'source_chat_session_id', '') = %s
                  )
                """,
                (
                    normalized_project_id,
                    normalized_username,
                    normalized_chat_session_id,
                    normalized_chat_session_id,
                ),
            )
            return cur.rowcount

    def delete_exact(self, project_id: str, username: str, chat_session_id: str) -> int:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_chat_session_id = str(chat_session_id or "").strip()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM project_chat_task_sessions
                WHERE project_id = %s AND username = %s AND chat_session_id = %s
                """,
                (normalized_project_id, normalized_username, normalized_chat_session_id),
            )
            return cur.rowcount

    def clear_project(self, project_id: str) -> int:
        normalized_project_id = str(project_id or "").strip()
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM project_chat_task_sessions WHERE project_id = %s",
                (normalized_project_id,),
            )
            return cur.rowcount

    def new_session_id(self) -> str:
        return f"tts-{uuid.uuid4().hex[:10]}"

    def new_node_id(self) -> str:
        return f"ttn-{uuid.uuid4().hex[:10]}"

    def new_archive_chat_session_id(self, source_chat_session_id: str) -> str:
        base = "".join(
            ch if ch.isalnum() or ch in "._-" else "_"
            for ch in str(source_chat_session_id or self.new_session_id()).strip()
        ).strip("._-")[:48] or self.new_session_id()
        return f"{base}.archived.{uuid.uuid4().hex[:8]}"
