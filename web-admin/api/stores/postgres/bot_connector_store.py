"""Bot connector store (PostgreSQL implementation)."""

from __future__ import annotations

import json

from psycopg.rows import dict_row

from stores.json.system_config_store import normalize_bot_platform_connectors
from stores.postgres._connection import connect


class BotConnectorStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_connectors (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def list_all(self) -> list[dict[str, object]]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM bot_connectors WHERE id = %s", ("global",))
            row = cur.fetchone()
        if row is None:
            return []
        payload = row["payload"] if isinstance(row["payload"], dict) else {}
        return normalize_bot_platform_connectors(payload.get("items"))

    def replace_all(self, items: object) -> list[dict[str, object]]:
        normalized = normalize_bot_platform_connectors(items)
        payload = json.dumps({"items": normalized}, ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bot_connectors (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                ("global", payload),
            )
        return normalized
