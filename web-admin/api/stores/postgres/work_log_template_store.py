"""Global work log template store (PostgreSQL)."""

from __future__ import annotations

import json
from dataclasses import asdict

from psycopg.rows import dict_row

from stores.json.work_log_template_store import WorkLogTemplate
from stores.postgres._connection import connect


class WorkLogTemplateStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS work_log_templates (
                    value TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """,
            )

    def save(self, template: WorkLogTemplate) -> None:
        payload = json.dumps(asdict(template), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO work_log_templates (value, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (value) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (template.value, payload),
            )

    def get(self, template_key: str) -> WorkLogTemplate | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM work_log_templates WHERE value = %s",
                (template_key,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return WorkLogTemplate(**row["payload"])

    def list_all(self) -> list[WorkLogTemplate]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM work_log_templates ORDER BY value")
            rows = cur.fetchall()
        return [WorkLogTemplate(**row["payload"]) for row in rows]
