"""项目 AI 对话运行态快照存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from stores.json.project_chat_store import _now_iso
from stores.postgres._connection import connect


def _to_iso(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    text = str(value or "").strip()
    return text or _now_iso()


class ProjectChatRuntimeStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_chat_runtime_snapshots (
                    project_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    chat_session_id TEXT NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (project_id, username, chat_session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_project_chat_runtime_lookup
                ON project_chat_runtime_snapshots (project_id, username, updated_at DESC);
                """
            )

    def get_snapshot(self, project_id: str, username: str, chat_session_id: str) -> dict[str, Any] | None:
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_session_id:
            return None
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT project_id, username, chat_session_id, payload, updated_at
                FROM project_chat_runtime_snapshots
                WHERE project_id = %s AND username = %s AND chat_session_id = %s
                """,
                (str(project_id or "").strip(), str(username or "").strip(), normalized_session_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        payload = row.get("payload")
        return {
            "project_id": str(row.get("project_id") or project_id).strip(),
            "username": str(row.get("username") or username).strip(),
            "chat_session_id": str(row.get("chat_session_id") or normalized_session_id).strip(),
            "payload": payload if isinstance(payload, dict) else {},
            "updated_at": _to_iso(row.get("updated_at")),
        }

    def save_snapshot(
        self,
        project_id: str,
        username: str,
        chat_session_id: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_project_id or not normalized_username or not normalized_session_id:
            raise ValueError("project_id, username and chat_session_id are required")
        normalized_payload = payload if isinstance(payload, dict) else {}
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_chat_runtime_snapshots (
                    project_id, username, chat_session_id, payload, updated_at
                )
                VALUES (%s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (project_id, username, chat_session_id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                RETURNING updated_at
                """,
                (
                    normalized_project_id,
                    normalized_username,
                    normalized_session_id,
                    json.dumps(normalized_payload, ensure_ascii=False),
                ),
            )
            row = cur.fetchone()
        return {
            "project_id": normalized_project_id,
            "username": normalized_username,
            "chat_session_id": normalized_session_id,
            "payload": normalized_payload,
            "updated_at": _to_iso(row.get("updated_at") if isinstance(row, dict) else None),
        }

    def delete_snapshot(self, project_id: str, username: str, chat_session_id: str = "") -> int:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_project_id or not normalized_username:
            return 0
        with self._conn.cursor() as cur:
            if normalized_session_id:
                cur.execute(
                    """
                    DELETE FROM project_chat_runtime_snapshots
                    WHERE project_id = %s AND username = %s AND chat_session_id = %s
                    """,
                    (normalized_project_id, normalized_username, normalized_session_id),
                )
            else:
                cur.execute(
                    """
                    DELETE FROM project_chat_runtime_snapshots
                    WHERE project_id = %s AND username = %s
                    """,
                    (normalized_project_id, normalized_username),
                )
            return max(0, int(cur.rowcount or 0))

    def clear_project(self, project_id: str) -> int:
        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            return 0
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM project_chat_runtime_snapshots
                WHERE project_id = %s
                """,
                (normalized_project_id,),
            )
            return max(0, int(cur.rowcount or 0))
