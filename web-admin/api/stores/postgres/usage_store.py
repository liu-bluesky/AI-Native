"""使用统计存储层 — PostgreSQL 实现"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row

from stores.postgres._connection import connect


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
    duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    provider_id TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    client_ip TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_employee ON usage_records(employee_id);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_records(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_project ON usage_records(project_id);
CREATE INDEX IF NOT EXISTS idx_usage_request ON usage_records(request_id);
CREATE INDEX IF NOT EXISTS idx_usage_status ON usage_records(status);
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
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS scope_id TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS project_name TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS chat_session_id TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS request_id TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS error_message TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS provider_id TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS model_name TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS prompt_version TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS input_tokens INTEGER NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS output_tokens INTEGER NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS cached_input_tokens INTEGER NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS total_tokens INTEGER NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_project ON usage_records(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_request ON usage_records(request_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_status ON usage_records(status)")

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
        with self._conn.cursor() as cur:
            cur.execute(
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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            updates.append(f"{column} = %s")
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
            updates.append("duration_ms = %s")
            params.append(_safe_float(duration_ms))
        if input_tokens is not None:
            updates.append("input_tokens = %s")
            params.append(_safe_int(input_tokens))
        if output_tokens is not None:
            updates.append("output_tokens = %s")
            params.append(_safe_int(output_tokens))
        if cached_input_tokens is not None:
            updates.append("cached_input_tokens = %s")
            params.append(_safe_int(cached_input_tokens))
        if total_tokens is not None:
            updates.append("total_tokens = %s")
            params.append(_safe_int(total_tokens))
        if cost_usd is not None:
            updates.append("cost_usd = %s")
            params.append(_safe_float(cost_usd))
        if not updates:
            return False

        params.append(normalized_id)
        with self._conn.cursor() as cur:
            cur.execute(
                f"UPDATE usage_records SET {', '.join(updates)} WHERE id = %s",
                tuple(params),
            )
            return cur.rowcount > 0

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

    def get_overview(self, days: int = 7, project_id: str = "") -> dict:
        normalized_days = max(1, min(int(days or 7), 365))
        cutoff = datetime.now(timezone.utc) - timedelta(days=normalized_days)
        normalized_project_id = _normalize_text(project_id, 120)
        where_clauses = ["created_at >= %s"]
        params: list[object] = [cutoff]
        if normalized_project_id:
            where_clauses.append("project_id = %s")
            params.append(normalized_project_id)
        where_sql = " AND ".join(where_clauses)
        query_params = tuple(params)

        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total_events,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call') AS tool_calls,
                    COUNT(*) FILTER (WHERE event_type = 'connection') AS connections,
                    COUNT(*) FILTER (WHERE event_type = 'model_call') AS model_calls,
                    COUNT(DISTINCT developer_name) FILTER (WHERE developer_name != '') AS active_developers,
                    COUNT(DISTINCT employee_id) FILTER (WHERE employee_id LIKE 'emp-%%') AS active_employees,
                    COUNT(DISTINCT tool_name) FILTER (WHERE tool_name != '') AS active_tools,
                    COUNT(DISTINCT project_id) FILTER (WHERE project_id != '') AS active_projects,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call' AND status = 'success') AS successful_tool_calls,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call' AND status IN ('failed', 'error')) AS failed_tool_calls,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call' AND status = 'timeout') AS timeout_tool_calls,
                    AVG(duration_ms) FILTER (WHERE event_type = 'tool_call' AND duration_ms > 0) AS avg_tool_duration_ms,
                    SUM(input_tokens) AS total_input_tokens,
                    SUM(output_tokens) AS total_output_tokens,
                    SUM(cached_input_tokens) AS total_cached_input_tokens,
                    SUM(total_tokens) AS total_tokens,
                    SUM(cost_usd) AS total_cost_usd,
                    COUNT(DISTINCT provider_id) FILTER (WHERE provider_id != '') AS active_providers,
                    COUNT(DISTINCT model_name) FILTER (WHERE model_name != '') AS active_models,
                    COUNT(DISTINCT prompt_version) FILTER (WHERE prompt_version != '') AS active_prompt_versions,
                    COUNT(*) FILTER (WHERE prompt_version != '') AS prompt_version_records,
                    COUNT(DISTINCT scope_id) FILTER (WHERE scope_id != '') AS active_scopes,
                    COUNT(*) FILTER (WHERE scope_id = 'mcp:query') AS query_scope_events,
                    COUNT(*) FILTER (WHERE scope_id = 'mcp:query' AND event_type = 'tool_call') AS query_tool_calls
                FROM usage_records
                WHERE {where_sql}
                """,
                query_params,
            )
            summary_row = cur.fetchone() or {}

            cur.execute(
                f"""
                SELECT
                    tool_name,
                    COUNT(*) AS cnt,
                    COUNT(*) FILTER (WHERE status = 'success') AS success_calls,
                    COUNT(*) FILTER (WHERE status IN ('failed', 'error')) AS failed_calls,
                    COUNT(*) FILTER (WHERE status = 'timeout') AS timeout_calls,
                    AVG(duration_ms) FILTER (WHERE duration_ms > 0) AS avg_duration_ms,
                    MAX(duration_ms) FILTER (WHERE duration_ms > 0) AS max_duration_ms
                FROM usage_records
                WHERE {where_sql} AND event_type = 'tool_call' AND tool_name != ''
                GROUP BY tool_name
                ORDER BY cnt DESC, tool_name ASC
                LIMIT 10
                """,
                query_params,
            )
            top_tools = [_normalize_row(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT
                    employee_id,
                    COUNT(*) AS cnt,
                    COUNT(*) FILTER (WHERE status = 'success') AS success_calls,
                    COUNT(*) FILTER (WHERE status IN ('failed', 'error')) AS failed_calls,
                    COUNT(*) FILTER (WHERE status = 'timeout') AS timeout_calls,
                    AVG(duration_ms) FILTER (WHERE duration_ms > 0) AS avg_duration_ms
                FROM usage_records
                WHERE {where_sql} AND employee_id LIKE 'emp-%%'
                GROUP BY employee_id
                ORDER BY cnt DESC, employee_id ASC
                LIMIT 10
                """,
                query_params,
            )
            top_employees = [_normalize_row(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT
                    scope_id,
                    COUNT(*) AS cnt,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call') AS tool_calls,
                    COUNT(*) FILTER (WHERE status = 'success') AS success_calls,
                    COUNT(*) FILTER (WHERE status IN ('failed', 'error')) AS failed_calls,
                    COUNT(*) FILTER (WHERE status = 'timeout') AS timeout_calls,
                    AVG(duration_ms) FILTER (WHERE duration_ms > 0) AS avg_duration_ms,
                    MAX(created_at) AS last_seen_at,
                    COUNT(DISTINCT employee_id) FILTER (WHERE employee_id LIKE 'emp-%%') AS attributed_employee_count,
                    COUNT(DISTINCT project_id) FILTER (WHERE project_id != '') AS project_count
                FROM usage_records
                WHERE {where_sql} AND scope_id != ''
                GROUP BY scope_id
                ORDER BY cnt DESC, scope_id ASC
                LIMIT 10
                """,
                query_params,
            )
            top_scopes = [_normalize_row(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT developer_name, COUNT(*) AS cnt
                FROM usage_records
                WHERE {where_sql} AND developer_name != ''
                GROUP BY developer_name
                ORDER BY cnt DESC, developer_name ASC
                LIMIT 10
                """,
                query_params,
            )
            top_developers = [_normalize_row(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT provider_id, COUNT(*) AS cnt, SUM(total_tokens) AS total_tokens, SUM(cost_usd) AS total_cost_usd
                FROM usage_records
                WHERE {where_sql} AND provider_id != ''
                GROUP BY provider_id
                ORDER BY cnt DESC, provider_id ASC
                LIMIT 8
                """,
                query_params,
            )
            top_providers = [_normalize_row(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT model_name, COUNT(*) AS cnt, SUM(total_tokens) AS total_tokens, SUM(cost_usd) AS total_cost_usd
                FROM usage_records
                WHERE {where_sql} AND model_name != ''
                GROUP BY model_name
                ORDER BY cnt DESC, model_name ASC
                LIMIT 8
                """,
                query_params,
            )
            top_models = [_normalize_row(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT prompt_version, COUNT(*) AS cnt
                FROM usage_records
                WHERE {where_sql} AND prompt_version != ''
                GROUP BY prompt_version
                ORDER BY cnt DESC, prompt_version ASC
                LIMIT 8
                """,
                query_params,
            )
            top_prompt_versions = [_normalize_row(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT
                    project_id,
                    project_name,
                    COUNT(*) AS cnt,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call') AS tool_calls,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call' AND status = 'success') AS success_calls,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call' AND status IN ('failed', 'error')) AS failed_calls,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call' AND status = 'timeout') AS timeout_calls,
                    COUNT(DISTINCT developer_name) FILTER (WHERE developer_name != '') AS developer_count,
                    AVG(duration_ms) FILTER (WHERE event_type = 'tool_call' AND duration_ms > 0) AS avg_duration_ms,
                    MAX(created_at) AS last_seen_at
                FROM usage_records
                WHERE {where_sql} AND project_id != ''
                GROUP BY project_id, project_name
                ORDER BY cnt DESC, project_name ASC
                LIMIT 10
                """,
                query_params,
            )
            top_projects = [_normalize_row(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT
                    TO_CHAR(DATE_TRUNC('day', created_at AT TIME ZONE 'UTC'), 'YYYY-MM-DD') AS date,
                    COUNT(*) AS total_events,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call') AS tool_calls,
                    COUNT(*) FILTER (WHERE event_type = 'connection') AS connections,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call' AND status = 'success') AS success_calls,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call' AND status IN ('failed', 'error')) AS failed_calls,
                    COUNT(*) FILTER (WHERE event_type = 'tool_call' AND status = 'timeout') AS timeout_calls
                FROM usage_records
                WHERE {where_sql}
                GROUP BY DATE_TRUNC('day', created_at AT TIME ZONE 'UTC')
                ORDER BY DATE_TRUNC('day', created_at AT TIME ZONE 'UTC') ASC
                """,
                query_params,
            )
            daily = [_normalize_row(row) for row in cur.fetchall()]

            cur.execute(
                f"""
                SELECT *
                FROM usage_records
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT 20
                """,
                query_params,
            )
            recent = [_normalize_row(row) for row in cur.fetchall()]

        successful_tool_calls = int(summary_row.get("successful_tool_calls") or 0)
        failed_tool_calls = int(summary_row.get("failed_tool_calls") or 0)
        timeout_tool_calls = int(summary_row.get("timeout_tool_calls") or 0)
        finalized_tool_calls = successful_tool_calls + failed_tool_calls + timeout_tool_calls
        tool_success_rate = round((successful_tool_calls / finalized_tool_calls) * 100, 1) if finalized_tool_calls else 0.0

        return {
            "days": normalized_days,
            "summary": {
                "total_events": int(summary_row.get("total_events") or 0),
                "tool_calls": int(summary_row.get("tool_calls") or 0),
                "connections": int(summary_row.get("connections") or 0),
                "model_calls": int(summary_row.get("model_calls") or 0),
                "active_developers": int(summary_row.get("active_developers") or 0),
                "active_employees": int(summary_row.get("active_employees") or 0),
                "active_tools": int(summary_row.get("active_tools") or 0),
                "active_projects": int(summary_row.get("active_projects") or 0),
                "successful_tool_calls": successful_tool_calls,
                "failed_tool_calls": failed_tool_calls,
                "timeout_tool_calls": timeout_tool_calls,
                "finalized_tool_calls": finalized_tool_calls,
                "tool_success_rate": tool_success_rate,
                "avg_tool_duration_ms": round(_safe_float(summary_row.get("avg_tool_duration_ms")), 1),
                "total_input_tokens": int(summary_row.get("total_input_tokens") or 0),
                "total_output_tokens": int(summary_row.get("total_output_tokens") or 0),
                "total_cached_input_tokens": int(summary_row.get("total_cached_input_tokens") or 0),
                "total_tokens": int(summary_row.get("total_tokens") or 0),
                "total_cost_usd": round(_safe_float(summary_row.get("total_cost_usd")), 4),
                "active_providers": int(summary_row.get("active_providers") or 0),
                "active_models": int(summary_row.get("active_models") or 0),
                "active_prompt_versions": int(summary_row.get("active_prompt_versions") or 0),
                "prompt_version_records": int(summary_row.get("prompt_version_records") or 0),
                "active_scopes": int(summary_row.get("active_scopes") or 0),
                "query_scope_events": int(summary_row.get("query_scope_events") or 0),
                "query_tool_calls": int(summary_row.get("query_tool_calls") or 0),
            },
            "tool_health": {
                "successful_calls": successful_tool_calls,
                "failed_calls": failed_tool_calls,
                "timeout_calls": timeout_tool_calls,
                "finalized_calls": finalized_tool_calls,
                "success_rate": tool_success_rate,
                "avg_duration_ms": round(_safe_float(summary_row.get("avg_tool_duration_ms")), 1),
            },
            "daily": [
                {
                    "date": str(row.get("date") or ""),
                    "total_events": int(row.get("total_events") or 0),
                    "tool_calls": int(row.get("tool_calls") or 0),
                    "connections": int(row.get("connections") or 0),
                    "success_calls": int(row.get("success_calls") or 0),
                    "failed_calls": int(row.get("failed_calls") or 0),
                    "timeout_calls": int(row.get("timeout_calls") or 0),
                }
                for row in daily
            ],
            "top_tools": [
                {
                    **row,
                    "avg_duration_ms": round(_safe_float(row.get("avg_duration_ms")), 1),
                    "max_duration_ms": round(_safe_float(row.get("max_duration_ms")), 1),
                    "success_rate": round(
                        (_safe_int(row.get("success_calls")) / max(
                            1,
                            _safe_int(row.get("success_calls")) + _safe_int(row.get("failed_calls")) + _safe_int(row.get("timeout_calls")),
                        )) * 100,
                        1,
                    ),
                }
                for row in top_tools
            ],
            "top_employees": [
                {
                    **row,
                    "avg_duration_ms": round(_safe_float(row.get("avg_duration_ms")), 1),
                }
                for row in top_employees
            ],
            "top_scopes": [
                {
                    **row,
                    "avg_duration_ms": round(_safe_float(row.get("avg_duration_ms")), 1),
                }
                for row in top_scopes
            ],
            "top_developers": top_developers,
            "top_providers": top_providers,
            "top_models": top_models,
            "top_prompt_versions": top_prompt_versions,
            "top_projects": [
                {
                    **row,
                    "avg_duration_ms": round(_safe_float(row.get("avg_duration_ms")), 1),
                }
                for row in top_projects
            ],
            "recent": recent,
        }
