"""系统统一用户反馈存储层（PostgreSQL）。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from psycopg.rows import dict_row

from stores.json.user_feedback_store import UserFeedbackTicket, _now_iso, sort_user_feedback
from stores.postgres._connection import connect


class UserFeedbackStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_feedback_tickets (
                    id TEXT PRIMARY KEY,
                    reporter_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    assignee_id TEXT NOT NULL DEFAULT '',
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_user_feedback_reporter_created
                ON user_feedback_tickets (reporter_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_user_feedback_status_priority_created
                ON user_feedback_tickets (status, priority, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_user_feedback_category_updated
                ON user_feedback_tickets (category, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_user_feedback_project_created
                ON user_feedback_tickets (project_id, status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_user_feedback_assignee_updated
                ON user_feedback_tickets (assignee_id, status, updated_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_user_feedback_idempotency
                ON user_feedback_tickets (reporter_id, idempotency_key)
                WHERE idempotency_key <> '';
                """
            )

    @staticmethod
    def new_id() -> str:
        return f"ufb_{uuid.uuid4().hex[:12]}"

    def save(self, ticket: UserFeedbackTicket) -> None:
        normalized = UserFeedbackTicket(**asdict(ticket))
        normalized.updated_at = _now_iso()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_feedback_tickets (
                    id, reporter_id, category, status, priority, project_id,
                    assignee_id, idempotency_key, created_at, updated_at, payload
                ) VALUES (
                    %(id)s, %(reporter_id)s, %(category)s, %(status)s, %(priority)s,
                    %(project_id)s, %(assignee_id)s, %(idempotency_key)s,
                    %(created_at)s, NOW(), %(payload)s::jsonb
                )
                ON CONFLICT (id) DO UPDATE SET
                    category = EXCLUDED.category,
                    status = EXCLUDED.status,
                    priority = EXCLUDED.priority,
                    project_id = EXCLUDED.project_id,
                    assignee_id = EXCLUDED.assignee_id,
                    idempotency_key = EXCLUDED.idempotency_key,
                    updated_at = NOW(),
                    payload = EXCLUDED.payload
                """,
                {**asdict(normalized), "payload": json.dumps(asdict(normalized), ensure_ascii=False)},
            )

    def get(self, feedback_id: str) -> UserFeedbackTicket | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM user_feedback_tickets WHERE id = %s", (feedback_id,))
            row = cur.fetchone()
        return UserFeedbackTicket(**row["payload"]) if row else None

    def list_all(self) -> list[UserFeedbackTicket]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM user_feedback_tickets ORDER BY updated_at DESC")
            rows = cur.fetchall()
        return sort_user_feedback([UserFeedbackTicket(**row["payload"]) for row in rows])

    def find_idempotent(self, reporter_id: str, idempotency_key: str) -> UserFeedbackTicket | None:
        if not str(idempotency_key or "").strip():
            return None
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM user_feedback_tickets
                WHERE reporter_id = %s AND idempotency_key = %s
                """,
                (reporter_id, idempotency_key),
            )
            row = cur.fetchone()
        return UserFeedbackTicket(**row["payload"]) if row else None
