"""系统配置存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
from dataclasses import asdict

from psycopg import connect
from psycopg.rows import dict_row

from stores.json.system_config_store import SystemConfig, _now_iso


class SystemConfigStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS system_configs (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def get_global(self) -> SystemConfig:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM system_configs WHERE id = %s", ("global",))
            row = cur.fetchone()
        if row is None:
            return SystemConfig()
        return SystemConfig(**row["payload"])

    def save_global(self, config: SystemConfig) -> None:
        payload = json.dumps(asdict(config), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO system_configs (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (config.id, payload),
            )

    def patch_global(self, updates: dict) -> SystemConfig:
        current = self.get_global()
        payload = asdict(current)
        payload.update(updates)
        payload["updated_at"] = _now_iso()
        if not payload.get("created_at"):
            payload["created_at"] = _now_iso()
        updated = SystemConfig(**payload)
        self.save_global(updated)
        return updated
