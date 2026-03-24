"""外部 MCP 模块存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from stores.postgres._connection import connect
from psycopg.rows import dict_row

from stores.json.external_mcp_store import ExternalMcpModule


class ExternalMcpStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS external_mcp_modules (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def save(self, module: ExternalMcpModule) -> None:
        payload = json.dumps(asdict(module), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO external_mcp_modules (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (module.id, payload),
            )

    def get(self, module_id: str) -> ExternalMcpModule | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM external_mcp_modules WHERE id = %s", (module_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return ExternalMcpModule(**row["payload"])

    def list_all(self) -> list[ExternalMcpModule]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM external_mcp_modules ORDER BY id")
            rows = cur.fetchall()
        return [ExternalMcpModule(**row["payload"]) for row in rows]

    def delete(self, module_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM external_mcp_modules WHERE id = %s", (module_id,))
            return cur.rowcount > 0

    def new_id(self) -> str:
        return f"xmcp-{uuid.uuid4().hex[:8]}"
