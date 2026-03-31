"""更新日志存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from psycopg.rows import dict_row

from stores.postgres._connection import connect
from stores.json.changelog_entry_store import ChangelogEntry, _now_iso, sort_changelog_entries


class ChangelogEntryStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS changelog_entries (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def save(self, entry: ChangelogEntry) -> None:
        normalized = ChangelogEntry(**asdict(entry))
        if not normalized.created_at:
            normalized.created_at = _now_iso()
        normalized.updated_at = _now_iso()
        payload = json.dumps(asdict(normalized), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO changelog_entries (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (normalized.id, payload),
            )

    def get(self, entry_id: str) -> ChangelogEntry | None:
        normalized_id = str(entry_id or "").strip()
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM changelog_entries WHERE id = %s", (normalized_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return ChangelogEntry(**row["payload"])

    def list_all(self) -> list[ChangelogEntry]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM changelog_entries")
            rows = cur.fetchall()
        return sort_changelog_entries([ChangelogEntry(**row["payload"]) for row in rows])

    def list_public(self) -> list[ChangelogEntry]:
        return [item for item in self.list_all() if bool(item.published)]

    def delete(self, entry_id: str) -> bool:
        normalized_id = str(entry_id or "").strip()
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM changelog_entries WHERE id = %s", (normalized_id,))
            return cur.rowcount > 0

    def new_id(self) -> str:
        return f"clog-{uuid.uuid4().hex[:8]}"
