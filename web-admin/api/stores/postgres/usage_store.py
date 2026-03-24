"""使用统计存储层 — PostgreSQL 实现"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from stores.postgres._connection import connect
from psycopg.rows import dict_row


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    developer_name TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    developer_name TEXT NOT NULL DEFAULT 'anonymous',
    event_type TEXT NOT NULL,
    tool_name TEXT NOT NULL DEFAULT '',
    client_ip TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_employee ON usage_records(employee_id);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_records(created_at);
"""


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        else:
            normalized[key] = value
    return normalized


class UsageStorePostgres:

    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)

    # ── API Key 管理 ──

    def create_key(self, developer_name: str, created_by: str = "") -> dict:
        key = f"ak-{secrets.token_hex(16)}"
        now = _now_iso()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_keys (key, developer_name, created_by, is_active, created_at)
                VALUES (%s, %s, %s, TRUE, %s)
                """,
                (key, developer_name, created_by, now),
            )
        return {"key": key, "developer_name": developer_name, "created_by": created_by, "created_at": now}

    def list_keys(self, created_by: str | None = None) -> list[dict]:
        owner = str(created_by or "").strip()
        with self._conn.cursor() as cur:
            if owner:
                cur.execute(
                    "SELECT * FROM api_keys WHERE created_by = %s ORDER BY created_at DESC",
                    (owner,),
                )
            else:
                cur.execute("SELECT * FROM api_keys ORDER BY created_at DESC")
            rows = cur.fetchall()
        return [_normalize_row(r) for r in rows]

    def get_key(self, key: str) -> dict | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM api_keys WHERE key = %s", (key,))
            row = cur.fetchone()
        return _normalize_row(row) if row else None

    def delete_key(self, key: str, created_by: str | None = None) -> bool:
        owner = str(created_by or "").strip()
        with self._conn.cursor() as cur:
            if owner:
                cur.execute(
                    "DELETE FROM api_keys WHERE key = %s AND created_by = %s",
                    (key, owner),
                )
            else:
                cur.execute("DELETE FROM api_keys WHERE key = %s", (key,))
            return cur.rowcount > 0

    def validate_key(self, key: str) -> str | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT developer_name FROM api_keys WHERE key = %s AND is_active = TRUE",
                (key,),
            )
            row = cur.fetchone()
        return row["developer_name"] if row else None

    # ── 使用记录 ──

    def record_event(
        self,
        employee_id: str,
        api_key: str,
        developer_name: str,
        event_type: str,
        tool_name: str = "",
        client_ip: str = "",
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usage_records
                    (id, employee_id, api_key, developer_name, event_type, tool_name, client_ip, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    f"ur-{uuid.uuid4().hex[:8]}",
                    employee_id,
                    api_key,
                    developer_name,
                    event_type,
                    tool_name,
                    client_ip,
                    _now_iso(),
                ),
            )

    def get_stats(self, employee_id: str, days: int = 7) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        params = (employee_id, cutoff)

        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM usage_records WHERE employee_id = %s AND created_at >= %s",
                params,
            )
            total_events = int(cur.fetchone()["cnt"])

            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM usage_records
                WHERE employee_id = %s AND created_at >= %s AND event_type = 'tool_call'
                """,
                params,
            )
            tool_calls = int(cur.fetchone()["cnt"])

            cur.execute(
                """
                SELECT COUNT(DISTINCT api_key) AS cnt
                FROM usage_records
                WHERE employee_id = %s AND created_at >= %s AND api_key != ''
                """,
                params,
            )
            active_developers = int(cur.fetchone()["cnt"])

            cur.execute(
                """
                SELECT api_key, developer_name, COUNT(*) AS cnt, MAX(created_at) AS last_seen
                FROM usage_records
                WHERE employee_id = %s AND created_at >= %s AND api_key != ''
                GROUP BY api_key, developer_name
                ORDER BY cnt DESC
                """,
                params,
            )
            by_developer = [_normalize_row(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT tool_name, COUNT(*) AS cnt
                FROM usage_records
                WHERE employee_id = %s AND created_at >= %s
                  AND event_type = 'tool_call' AND tool_name != ''
                GROUP BY tool_name
                ORDER BY cnt DESC
                """,
                params,
            )
            by_tool = [_normalize_row(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT *
                FROM usage_records
                WHERE employee_id = %s AND created_at >= %s
                ORDER BY created_at DESC
                LIMIT 20
                """,
                params,
            )
            recent = [_normalize_row(r) for r in cur.fetchall()]

        return {
            "total_events": total_events,
            "tool_calls": tool_calls,
            "active_developers": active_developers,
            "by_developer": by_developer,
            "by_tool": by_tool,
            "recent": recent,
        }
