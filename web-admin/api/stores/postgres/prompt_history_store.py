"""提示词生成历史存储层（PostgreSQL）"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from stores.postgres._connection import connect
from psycopg.rows import dict_row


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromptHistoryStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_history (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    created_by TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_prompt_history_employee ON prompt_history(employee_id);
                CREATE INDEX IF NOT EXISTS idx_prompt_history_created ON prompt_history(created_at DESC);
                """
            )

    def save(self, record: dict) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prompt_history (id, employee_id, prompt, provider, model, created_at, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record["id"],
                    record["employee_id"],
                    record["prompt"],
                    record["provider"],
                    record["model"],
                    record.get("created_at", _now_iso()),
                    record.get("created_by", ""),
                ),
            )

    def list_by_employee(self, employee_id: str, limit: int = 20) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, employee_id, prompt, provider, model, created_at, created_by
                FROM prompt_history
                WHERE employee_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (employee_id, limit),
            )
            return cur.fetchall()

    def get(self, record_id: str) -> dict | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, employee_id, prompt, provider, model, created_at, created_by
                FROM prompt_history
                WHERE id = %s
                """,
                (record_id,),
            )
            return cur.fetchone()

    def delete(self, record_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM prompt_history WHERE id = %s", (record_id,))
            return cur.rowcount > 0
