"""使用统计存储层 — SQLite 实现"""

from __future__ import annotations

import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


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
    scope_id TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    developer_name TEXT NOT NULL DEFAULT 'anonymous',
    event_type TEXT NOT NULL,
    tool_name TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    project_name TEXT NOT NULL DEFAULT '',
    chat_session_id TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    duration_ms REAL NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    provider_id TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    client_ip TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_employee ON usage_records(employee_id);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_records(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_project ON usage_records(project_id);
CREATE INDEX IF NOT EXISTS idx_usage_request ON usage_records(request_id);
CREATE INDEX IF NOT EXISTS idx_usage_status ON usage_records(status);
"""


class UsageStore:

    def __init__(self, db_path: Path) -> None:
        self._db = sqlite3.connect(str(db_path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._ensure_usage_schema()

    def _ensure_usage_schema(self) -> None:
        existing = {
            str(row["name"] or "").strip()
            for row in self._db.execute("PRAGMA table_info(usage_records)").fetchall()
        }
        required_columns = {
            "scope_id": "TEXT NOT NULL DEFAULT ''",
            "project_id": "TEXT NOT NULL DEFAULT ''",
            "project_name": "TEXT NOT NULL DEFAULT ''",
            "chat_session_id": "TEXT NOT NULL DEFAULT ''",
            "request_id": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT ''",
            "duration_ms": "REAL NOT NULL DEFAULT 0",
            "error_message": "TEXT NOT NULL DEFAULT ''",
            "provider_id": "TEXT NOT NULL DEFAULT ''",
            "model_name": "TEXT NOT NULL DEFAULT ''",
            "prompt_version": "TEXT NOT NULL DEFAULT ''",
            "input_tokens": "INTEGER NOT NULL DEFAULT 0",
            "output_tokens": "INTEGER NOT NULL DEFAULT 0",
            "cached_input_tokens": "INTEGER NOT NULL DEFAULT 0",
            "total_tokens": "INTEGER NOT NULL DEFAULT 0",
            "cost_usd": "REAL NOT NULL DEFAULT 0",
        }
        for column_name, ddl in required_columns.items():
            if column_name in existing:
                continue
            self._db.execute(f"ALTER TABLE usage_records ADD COLUMN {column_name} {ddl}")
        self._db.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_usage_project ON usage_records(project_id);
            CREATE INDEX IF NOT EXISTS idx_usage_request ON usage_records(request_id);
            CREATE INDEX IF NOT EXISTS idx_usage_status ON usage_records(status);
            """
        )
        self._db.commit()

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

    def list_keys(self, created_by: str | None = None) -> list[dict]:
        owner = str(created_by or "").strip()
        if owner:
            rows = self._db.execute(
                "SELECT * FROM api_keys WHERE created_by = ? ORDER BY created_at DESC",
                (owner,),
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM api_keys ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_key(self, key: str) -> dict | None:
        row = self._db.execute("SELECT * FROM api_keys WHERE key = ?", (key,)).fetchone()
        return dict(row) if row else None

    def delete_key(self, key: str, created_by: str | None = None) -> bool:
        owner = str(created_by or "").strip()
        if owner:
            cur = self._db.execute(
                "DELETE FROM api_keys WHERE key = ? AND created_by = ?",
                (key, owner),
            )
        else:
            cur = self._db.execute("DELETE FROM api_keys WHERE key = ?", (key,))
        self._db.commit()
        return cur.rowcount > 0

    def validate_key(self, key: str) -> str | None:
        row = self._db.execute(
            "SELECT developer_name FROM api_keys WHERE key = ? AND is_active = 1", (key,)
        ).fetchone()
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
        *,
        scope_id: str = "",
        project_id: str = "",
        project_name: str = "",
        chat_session_id: str = "",
        request_id: str = "",
        status: str = "",
        duration_ms: float | None = None,
        error_message: str = "",
        provider_id: str = "",
        model_name: str = "",
        prompt_version: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
        total_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> str:
        event_id = f"ur-{uuid.uuid4().hex[:12]}"
        self._db.execute(
            """
            INSERT INTO usage_records (
                id,
                employee_id,
                scope_id,
                api_key,
                developer_name,
                event_type,
                tool_name,
                project_id,
                project_name,
                chat_session_id,
                request_id,
                status,
                duration_ms,
                error_message,
                provider_id,
                model_name,
                prompt_version,
                input_tokens,
                output_tokens,
                cached_input_tokens,
                total_tokens,
                cost_usd,
                client_ip,
                created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id,
                _normalize_text(employee_id, 120),
                _normalize_text(scope_id, 120),
                _normalize_text(api_key, 120),
                _normalize_text(developer_name, 120) or "anonymous",
                _normalize_text(event_type, 40),
                _normalize_text(tool_name, 160),
                _normalize_text(project_id, 120),
                _normalize_text(project_name, 160),
                _normalize_text(chat_session_id, 160),
                _normalize_text(request_id, 120),
                _normalize_text(status, 40),
                _safe_float(duration_ms),
                _normalize_text(error_message, 500),
                _normalize_text(provider_id, 160),
                _normalize_text(model_name, 160),
                _normalize_text(prompt_version, 160),
                _safe_int(input_tokens),
                _safe_int(output_tokens),
                _safe_int(cached_input_tokens),
                _safe_int(total_tokens),
                _safe_float(cost_usd),
                _normalize_text(client_ip, 80),
                _now_iso(),
            ),
        )
        self._db.commit()
        return event_id

    def finalize_event(
        self,
        event_id: str,
        *,
        employee_id: str = "",
        project_id: str = "",
        project_name: str = "",
        chat_session_id: str = "",
        request_id: str = "",
        status: str = "",
        duration_ms: float | None = None,
        error_message: str = "",
        provider_id: str = "",
        model_name: str = "",
        prompt_version: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cached_input_tokens: int | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> bool:
        normalized_id = _normalize_text(event_id, 120)
        if not normalized_id:
            return False

        updates: list[str] = []
        params: list[object] = []

        def add_text(column: str, value: str, limit: int = 160) -> None:
            normalized_value = _normalize_text(value, limit)
            if not normalized_value:
                return
            updates.append(f"{column} = ?")
            params.append(normalized_value)

        add_text("employee_id", employee_id, 120)
        add_text("project_id", project_id, 120)
        add_text("project_name", project_name, 160)
        add_text("chat_session_id", chat_session_id, 160)
        add_text("request_id", request_id, 120)
        add_text("status", status, 40)
        add_text("error_message", error_message, 500)
        add_text("provider_id", provider_id, 160)
        add_text("model_name", model_name, 160)
        add_text("prompt_version", prompt_version, 160)
        if duration_ms is not None:
            updates.append("duration_ms = ?")
            params.append(_safe_float(duration_ms))
        if input_tokens is not None:
            updates.append("input_tokens = ?")
            params.append(_safe_int(input_tokens))
        if output_tokens is not None:
            updates.append("output_tokens = ?")
            params.append(_safe_int(output_tokens))
        if cached_input_tokens is not None:
            updates.append("cached_input_tokens = ?")
            params.append(_safe_int(cached_input_tokens))
        if total_tokens is not None:
            updates.append("total_tokens = ?")
            params.append(_safe_int(total_tokens))
        if cost_usd is not None:
            updates.append("cost_usd = ?")
            params.append(_safe_float(cost_usd))
        if not updates:
            return False

        params.append(normalized_id)
        cur = self._db.execute(
            f"UPDATE usage_records SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
        self._db.commit()
        return cur.rowcount > 0

    def get_stats(self, employee_id: str, days: int = 7) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        base = "SELECT {} FROM usage_records WHERE employee_id = ? AND created_at >= ?"
        params = (employee_id, cutoff)

        total_events = self._db.execute(
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
            "total_events": total_events,
            "tool_calls": tool_calls,
            "active_developers": developers,
            "by_developer": [dict(r) for r in by_developer],
            "by_tool": [dict(r) for r in by_tool],
            "recent": [dict(r) for r in recent],
        }

    def get_overview(self, days: int = 7, project_id: str = "") -> dict:
        normalized_days = max(1, min(int(days or 7), 365))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=normalized_days)).isoformat()
        normalized_project_id = _normalize_text(project_id, 120)
        where_clauses = ["created_at >= ?"]
        params: list[object] = [cutoff]
        if normalized_project_id:
            where_clauses.append("project_id = ?")
            params.append(normalized_project_id)
        where_sql = " AND ".join(where_clauses)
        query_params = tuple(params)

        summary_row = self._db.execute(
            f"""
            SELECT
                COUNT(*) AS total_events,
                SUM(CASE WHEN event_type = 'tool_call' THEN 1 ELSE 0 END) AS tool_calls,
                SUM(CASE WHEN event_type = 'connection' THEN 1 ELSE 0 END) AS connections,
                SUM(CASE WHEN event_type = 'model_call' THEN 1 ELSE 0 END) AS model_calls,
                COUNT(DISTINCT CASE WHEN developer_name != '' THEN developer_name END) AS active_developers,
                COUNT(DISTINCT CASE WHEN employee_id LIKE 'emp-%' THEN employee_id END) AS active_employees,
                COUNT(DISTINCT CASE WHEN tool_name != '' THEN tool_name END) AS active_tools,
                COUNT(DISTINCT CASE WHEN project_id != '' THEN project_id END) AS active_projects,
                SUM(CASE WHEN event_type = 'tool_call' AND status = 'success' THEN 1 ELSE 0 END) AS successful_tool_calls,
                SUM(CASE WHEN event_type = 'tool_call' AND status IN ('failed', 'error') THEN 1 ELSE 0 END) AS failed_tool_calls,
                SUM(CASE WHEN event_type = 'tool_call' AND status = 'timeout' THEN 1 ELSE 0 END) AS timeout_tool_calls,
                AVG(CASE WHEN event_type = 'tool_call' AND duration_ms > 0 THEN duration_ms END) AS avg_tool_duration_ms,
                SUM(input_tokens) AS total_input_tokens,
                SUM(output_tokens) AS total_output_tokens,
                SUM(cached_input_tokens) AS total_cached_input_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(cost_usd) AS total_cost_usd,
                COUNT(DISTINCT CASE WHEN provider_id != '' THEN provider_id END) AS active_providers,
                COUNT(DISTINCT CASE WHEN model_name != '' THEN model_name END) AS active_models,
                COUNT(DISTINCT CASE WHEN prompt_version != '' THEN prompt_version END) AS active_prompt_versions,
                SUM(CASE WHEN prompt_version != '' THEN 1 ELSE 0 END) AS prompt_version_records,
                COUNT(DISTINCT CASE WHEN scope_id != '' THEN scope_id END) AS active_scopes,
                SUM(CASE WHEN scope_id = 'mcp:query' THEN 1 ELSE 0 END) AS query_scope_events,
                SUM(CASE WHEN scope_id = 'mcp:query' AND event_type = 'tool_call' THEN 1 ELSE 0 END) AS query_tool_calls
            FROM usage_records
            WHERE {where_sql}
            """,
            query_params,
        ).fetchone()

        by_tool_rows = self._db.execute(
            f"""
            SELECT
                tool_name,
                COUNT(*) AS cnt,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_calls,
                SUM(CASE WHEN status IN ('failed', 'error') THEN 1 ELSE 0 END) AS failed_calls,
                SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) AS timeout_calls,
                AVG(CASE WHEN duration_ms > 0 THEN duration_ms END) AS avg_duration_ms,
                MAX(CASE WHEN duration_ms > 0 THEN duration_ms ELSE 0 END) AS max_duration_ms
            FROM usage_records
            WHERE {where_sql} AND event_type = 'tool_call' AND tool_name != ''
            GROUP BY tool_name
            ORDER BY cnt DESC, tool_name ASC
            LIMIT 10
            """,
            query_params,
        ).fetchall()
        by_employee_rows = self._db.execute(
            f"""
            SELECT
                employee_id,
                COUNT(*) AS cnt,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_calls,
                SUM(CASE WHEN status IN ('failed', 'error') THEN 1 ELSE 0 END) AS failed_calls,
                SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) AS timeout_calls,
                AVG(CASE WHEN duration_ms > 0 THEN duration_ms END) AS avg_duration_ms
            FROM usage_records
            WHERE {where_sql} AND employee_id LIKE 'emp-%'
            GROUP BY employee_id
            ORDER BY cnt DESC, employee_id ASC
            LIMIT 10
            """,
            query_params,
        ).fetchall()
        by_scope_rows = self._db.execute(
            f"""
            SELECT
                scope_id,
                COUNT(*) AS cnt,
                SUM(CASE WHEN event_type = 'tool_call' THEN 1 ELSE 0 END) AS tool_calls,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_calls,
                SUM(CASE WHEN status IN ('failed', 'error') THEN 1 ELSE 0 END) AS failed_calls,
                SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) AS timeout_calls,
                AVG(CASE WHEN duration_ms > 0 THEN duration_ms END) AS avg_duration_ms,
                MAX(created_at) AS last_seen_at,
                COUNT(DISTINCT CASE WHEN employee_id LIKE 'emp-%' THEN employee_id END) AS attributed_employee_count,
                COUNT(DISTINCT CASE WHEN project_id != '' THEN project_id END) AS project_count
            FROM usage_records
            WHERE {where_sql} AND scope_id != ''
            GROUP BY scope_id
            ORDER BY cnt DESC, scope_id ASC
            LIMIT 10
            """,
            query_params,
        ).fetchall()
        by_developer_rows = self._db.execute(
            f"""
            SELECT developer_name, COUNT(*) AS cnt
            FROM usage_records
            WHERE {where_sql} AND developer_name != ''
            GROUP BY developer_name
            ORDER BY cnt DESC, developer_name ASC
            LIMIT 10
            """,
            query_params,
        ).fetchall()
        by_provider_rows = self._db.execute(
            f"""
            SELECT provider_id, COUNT(*) AS cnt, SUM(total_tokens) AS total_tokens, SUM(cost_usd) AS total_cost_usd
            FROM usage_records
            WHERE {where_sql} AND provider_id != ''
            GROUP BY provider_id
            ORDER BY cnt DESC, provider_id ASC
            LIMIT 8
            """,
            query_params,
        ).fetchall()
        by_model_rows = self._db.execute(
            f"""
            SELECT model_name, COUNT(*) AS cnt, SUM(total_tokens) AS total_tokens, SUM(cost_usd) AS total_cost_usd
            FROM usage_records
            WHERE {where_sql} AND model_name != ''
            GROUP BY model_name
            ORDER BY cnt DESC, model_name ASC
            LIMIT 8
            """,
            query_params,
        ).fetchall()
        by_prompt_version_rows = self._db.execute(
            f"""
            SELECT prompt_version, COUNT(*) AS cnt
            FROM usage_records
            WHERE {where_sql} AND prompt_version != ''
            GROUP BY prompt_version
            ORDER BY cnt DESC, prompt_version ASC
            LIMIT 8
            """,
            query_params,
        ).fetchall()
        by_project_rows = self._db.execute(
            f"""
            SELECT
                project_id,
                project_name,
                COUNT(*) AS cnt,
                SUM(CASE WHEN event_type = 'tool_call' THEN 1 ELSE 0 END) AS tool_calls,
                SUM(CASE WHEN event_type = 'tool_call' AND status = 'success' THEN 1 ELSE 0 END) AS success_calls,
                SUM(CASE WHEN event_type = 'tool_call' AND status IN ('failed', 'error') THEN 1 ELSE 0 END) AS failed_calls,
                SUM(CASE WHEN event_type = 'tool_call' AND status = 'timeout' THEN 1 ELSE 0 END) AS timeout_calls,
                COUNT(DISTINCT CASE WHEN developer_name != '' THEN developer_name END) AS developer_count,
                AVG(CASE WHEN event_type = 'tool_call' AND duration_ms > 0 THEN duration_ms END) AS avg_duration_ms,
                MAX(created_at) AS last_seen_at
            FROM usage_records
            WHERE {where_sql} AND project_id != ''
            GROUP BY project_id, project_name
            ORDER BY cnt DESC, project_name ASC
            LIMIT 10
            """,
            query_params,
        ).fetchall()
        daily_rows = self._db.execute(
            f"""
            SELECT
                substr(created_at, 1, 10) AS date,
                COUNT(*) AS total_events,
                SUM(CASE WHEN event_type = 'tool_call' THEN 1 ELSE 0 END) AS tool_calls,
                SUM(CASE WHEN event_type = 'connection' THEN 1 ELSE 0 END) AS connections,
                SUM(CASE WHEN event_type = 'tool_call' AND status = 'success' THEN 1 ELSE 0 END) AS success_calls,
                SUM(CASE WHEN event_type = 'tool_call' AND status IN ('failed', 'error') THEN 1 ELSE 0 END) AS failed_calls,
                SUM(CASE WHEN event_type = 'tool_call' AND status = 'timeout' THEN 1 ELSE 0 END) AS timeout_calls
            FROM usage_records
            WHERE {where_sql}
            GROUP BY substr(created_at, 1, 10)
            ORDER BY date ASC
            """,
            query_params,
        ).fetchall()
        recent_rows = self._db.execute(
            f"""
            SELECT *
            FROM usage_records
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT 20
            """,
            query_params,
        ).fetchall()

        successful_tool_calls = int(summary_row["successful_tool_calls"] or 0)
        failed_tool_calls = int(summary_row["failed_tool_calls"] or 0)
        timeout_tool_calls = int(summary_row["timeout_tool_calls"] or 0)
        finalized_tool_calls = successful_tool_calls + failed_tool_calls + timeout_tool_calls
        tool_success_rate = round((successful_tool_calls / finalized_tool_calls) * 100, 1) if finalized_tool_calls else 0.0

        return {
            "days": normalized_days,
            "summary": {
                "total_events": int(summary_row["total_events"] or 0),
                "tool_calls": int(summary_row["tool_calls"] or 0),
                "connections": int(summary_row["connections"] or 0),
                "model_calls": int(summary_row["model_calls"] or 0),
                "active_developers": int(summary_row["active_developers"] or 0),
                "active_employees": int(summary_row["active_employees"] or 0),
                "active_tools": int(summary_row["active_tools"] or 0),
                "active_projects": int(summary_row["active_projects"] or 0),
                "successful_tool_calls": successful_tool_calls,
                "failed_tool_calls": failed_tool_calls,
                "timeout_tool_calls": timeout_tool_calls,
                "finalized_tool_calls": finalized_tool_calls,
                "tool_success_rate": tool_success_rate,
                "avg_tool_duration_ms": round(_safe_float(summary_row["avg_tool_duration_ms"]), 1),
                "total_input_tokens": int(summary_row["total_input_tokens"] or 0),
                "total_output_tokens": int(summary_row["total_output_tokens"] or 0),
                "total_cached_input_tokens": int(summary_row["total_cached_input_tokens"] or 0),
                "total_tokens": int(summary_row["total_tokens"] or 0),
                "total_cost_usd": round(_safe_float(summary_row["total_cost_usd"]), 4),
                "active_providers": int(summary_row["active_providers"] or 0),
                "active_models": int(summary_row["active_models"] or 0),
                "active_prompt_versions": int(summary_row["active_prompt_versions"] or 0),
                "prompt_version_records": int(summary_row["prompt_version_records"] or 0),
                "active_scopes": int(summary_row["active_scopes"] or 0),
                "query_scope_events": int(summary_row["query_scope_events"] or 0),
                "query_tool_calls": int(summary_row["query_tool_calls"] or 0),
            },
            "tool_health": {
                "successful_calls": successful_tool_calls,
                "failed_calls": failed_tool_calls,
                "timeout_calls": timeout_tool_calls,
                "finalized_calls": finalized_tool_calls,
                "success_rate": tool_success_rate,
                "avg_duration_ms": round(_safe_float(summary_row["avg_tool_duration_ms"]), 1),
            },
            "daily": [
                {
                    "date": row["date"],
                    "total_events": int(row["total_events"] or 0),
                    "tool_calls": int(row["tool_calls"] or 0),
                    "connections": int(row["connections"] or 0),
                    "success_calls": int(row["success_calls"] or 0),
                    "failed_calls": int(row["failed_calls"] or 0),
                    "timeout_calls": int(row["timeout_calls"] or 0),
                }
                for row in daily_rows
            ],
            "top_tools": [
                {
                    **dict(row),
                    "avg_duration_ms": round(_safe_float(row["avg_duration_ms"]), 1),
                    "max_duration_ms": round(_safe_float(row["max_duration_ms"]), 1),
                    "success_rate": round(
                        (_safe_int(row["success_calls"]) / max(
                            1,
                            _safe_int(row["success_calls"]) + _safe_int(row["failed_calls"]) + _safe_int(row["timeout_calls"]),
                        )) * 100,
                        1,
                    ),
                }
                for row in by_tool_rows
            ],
            "top_employees": [
                {
                    **dict(row),
                    "avg_duration_ms": round(_safe_float(row["avg_duration_ms"]), 1),
                }
                for row in by_employee_rows
            ],
            "top_scopes": [
                {
                    **dict(row),
                    "avg_duration_ms": round(_safe_float(row["avg_duration_ms"]), 1),
                }
                for row in by_scope_rows
            ],
            "top_developers": [dict(row) for row in by_developer_rows],
            "top_providers": [dict(row) for row in by_provider_rows],
            "top_models": [dict(row) for row in by_model_rows],
            "top_prompt_versions": [dict(row) for row in by_prompt_version_rows],
            "top_projects": [
                {
                    **dict(row),
                    "avg_duration_ms": round(_safe_float(row["avg_duration_ms"]), 1),
                }
                for row in by_project_rows
            ],
            "recent": [dict(row) for row in recent_rows],
        }
