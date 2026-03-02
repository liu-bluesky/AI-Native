"""AI 员工存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from psycopg import connect
from psycopg.rows import dict_row

from employee_store import EmployeeConfig


class EmployeeStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS employees (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def save(self, emp: EmployeeConfig) -> None:
        payload = json.dumps(asdict(emp), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (emp.id, payload),
            )

    def get(self, eid: str) -> EmployeeConfig | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM employees WHERE id = %s", (eid,))
            row = cur.fetchone()
        if row is None:
            return None
        return EmployeeConfig(**row["payload"])

    def list_all(self) -> list[EmployeeConfig]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM employees ORDER BY id")
            rows = cur.fetchall()
        return [EmployeeConfig(**r["payload"]) for r in rows]

    def delete(self, eid: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM employees WHERE id = %s", (eid,))
            return cur.rowcount > 0

    def new_id(self) -> str:
        return f"emp-{uuid.uuid4().hex[:8]}"
