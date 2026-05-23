"""CLI plugin user profile store (PostgreSQL implementation)."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Optional

from psycopg.rows import dict_row

from stores.json.cli_plugin_profile_store import CliPluginUserProfileRecord
from stores.postgres._connection import connect


class CliPluginProfileStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cli_plugin_user_profiles (
                    plugin_id TEXT NOT NULL,
                    owner_username TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (plugin_id, owner_username)
                );
                CREATE INDEX IF NOT EXISTS idx_cli_plugin_user_profiles_owner_updated
                ON cli_plugin_user_profiles (owner_username, updated_at DESC);
                """
            )

    def save_profile(self, item: CliPluginUserProfileRecord) -> None:
        payload = json.dumps(asdict(item), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cli_plugin_user_profiles (plugin_id, owner_username, payload, updated_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT (plugin_id, owner_username) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (item.plugin_id, item.owner_username, payload),
            )

    def get_profile(
        self,
        plugin_id: str,
        owner_username: str,
    ) -> Optional[CliPluginUserProfileRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM cli_plugin_user_profiles
                WHERE plugin_id = %s AND owner_username = %s
                """,
                (str(plugin_id or "").strip(), str(owner_username or "").strip()),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return CliPluginUserProfileRecord(**row["payload"])

    def list_profiles(
        self,
        *,
        plugin_id: str = "",
        owner_username: str = "",
    ) -> list[CliPluginUserProfileRecord]:
        normalized_plugin_id = str(plugin_id or "").strip()
        normalized_owner = str(owner_username or "").strip()
        clauses: list[str] = []
        params: list[str] = []
        if normalized_plugin_id:
            clauses.append("plugin_id = %s")
            params.append(normalized_plugin_id)
        if normalized_owner:
            clauses.append("owner_username = %s")
            params.append(normalized_owner)
        sql = "SELECT payload FROM cli_plugin_user_profiles"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"
        with self._conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [CliPluginUserProfileRecord(**row["payload"]) for row in rows]

    def delete_profile(self, plugin_id: str, owner_username: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM cli_plugin_user_profiles
                WHERE plugin_id = %s AND owner_username = %s
                """,
                (str(plugin_id or "").strip(), str(owner_username or "").strip()),
            )
            return bool(cur.rowcount and cur.rowcount > 0)
