"""Agent template store (PostgreSQL)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from psycopg import connect
from psycopg.rows import dict_row

from stores.json.agent_template_store import AgentTemplate


class AgentTemplateStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_templates (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """,
            )

    def save(self, template: AgentTemplate) -> None:
        payload = json.dumps(asdict(template), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_templates (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (template.id, payload),
            )

    def get(self, template_id: str) -> AgentTemplate | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM agent_templates WHERE id = %s",
                (template_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return AgentTemplate(**row["payload"])

    def list_all(self) -> list[AgentTemplate]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM agent_templates ORDER BY id")
            rows = cur.fetchall()
        return [AgentTemplate(**row["payload"]) for row in rows]

    def delete(self, template_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM agent_templates WHERE id = %s", (template_id,))
            return cur.rowcount > 0

    def new_id(self) -> str:
        return f"agtpl-{uuid.uuid4().hex[:8]}"
