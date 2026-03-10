"""使用统计存储层 — SQLite 实现"""

from __future__ import annotations

import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    developer_name TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    developer_name TEXT NOT NULL DEFAULT 'anonymous',
    event_type TEXT NOT NULL,
    tool_name TEXT NOT NULL DEFAULT '',
    client_ip TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_employee ON usage_records(employee_id);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_records(created_at);
"""


class UsageStore:

    def __init__(self, db_path: Path) -> None:
        self._db = sqlite3.connect(str(db_path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    # ── API Key 管理 ──

    def create_key(self, developer_name: str, created_by: str = "") -> dict:
        key = f"ak-{secrets.token_hex(16)}"
        now = _now_iso()
        self._db.execute(
            "INSERT INTO api_keys (key, developer_name, created_by, is_active, created_at) VALUES (?,?,?,1,?)",
            (key, developer_name, created_by, now),
        )
        self._db.commit()
        return {"key": key, "developer_name": developer_name, "created_by": created_by, "created_at": now}

    def list_keys(self) -> list[dict]:
        rows = self._db.execute("SELECT * FROM api_keys ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def deactivate_key(self, key: str) -> bool:
        cur = self._db.execute("UPDATE api_keys SET is_active = 0 WHERE key = ?", (key,))
        self._db.commit()
        return cur.rowcount > 0

    def validate_key(self, key: str) -> str | None:
        row = self._db.execute(
            "SELECT developer_name FROM api_keys WHERE key = ? AND is_active = 1", (key,)
        ).fetchone()
        return row["developer_name"] if row else None

    # ── 使用记录 ──

    def record_event(self, employee_id: str, api_key: str, developer_name: str,
                     event_type: str, tool_name: str = "", client_ip: str = "") -> None:
        self._db.execute(
            "INSERT INTO usage_records (id, employee_id, api_key, developer_name, event_type, tool_name, client_ip, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (f"ur-{uuid.uuid4().hex[:8]}", employee_id, api_key, developer_name, event_type, tool_name, client_ip, _now_iso()),
        )
        self._db.commit()

    def get_stats(self, employee_id: str, days: int = 7) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        base = "SELECT {} FROM usage_records WHERE employee_id = ? AND created_at >= ?"
        params = (employee_id, cutoff)

        connections = self._db.execute(
            base.format("COUNT(*)"), params
        ).fetchone()[0]

        tool_calls = self._db.execute(
            base.format("COUNT(*)") + " AND event_type = 'tool_call'", params
        ).fetchone()[0]

        developers = self._db.execute(
            base.format("COUNT(DISTINCT api_key)") + " AND api_key != ''", params
        ).fetchone()[0]

        by_developer = self._db.execute(
            base.format("api_key, developer_name, COUNT(*) as cnt, MAX(created_at) as last_seen")
            + " AND api_key != '' GROUP BY api_key ORDER BY cnt DESC",
            params,
        ).fetchall()

        by_tool = self._db.execute(
            base.format("tool_name, COUNT(*) as cnt")
            + " AND event_type = 'tool_call' AND tool_name != '' GROUP BY tool_name ORDER BY cnt DESC",
            params,
        ).fetchall()

        recent = self._db.execute(
            base.format("*") + " ORDER BY created_at DESC LIMIT 20", params
        ).fetchall()

        return {
            "total_events": connections,
            "tool_calls": tool_calls,
            "active_developers": developers,
            "by_developer": [dict(r) for r in by_developer],
            "by_tool": [dict(r) for r in by_tool],
            "recent": [dict(r) for r in recent],
        }
