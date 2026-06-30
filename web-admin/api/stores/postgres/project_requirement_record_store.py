"""项目需求记录存储层（PostgreSQL 实现）。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from psycopg.rows import dict_row

from stores.json.project_requirement_record_store import ProjectRequirementRecord, _now_iso
from stores.postgres._connection import connect


class ProjectRequirementRecordStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_requirement_records (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    chat_session_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_project_requirement_records_project_updated
                    ON project_requirement_records (project_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_project_requirement_records_scope
                    ON project_requirement_records (project_id, username, id);
                """
            )

    def save(self, record: ProjectRequirementRecord) -> ProjectRequirementRecord:
        normalized = ProjectRequirementRecord(**asdict(record))
        if not normalized.id:
            normalized.id = self.new_record_id()
        normalized.updated_at = _now_iso()
        payload = json.dumps(asdict(normalized), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_requirement_records (
                    id, project_id, username, chat_session_id, payload, updated_at
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET project_id = EXCLUDED.project_id,
                    username = EXCLUDED.username,
                    chat_session_id = EXCLUDED.chat_session_id,
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                """,
                (
                    normalized.id,
                    normalized.project_id,
                    normalized.username,
                    normalized.chat_session_id,
                    payload,
                ),
            )
        return normalized

    def get(self, project_id: str, username: str, record_id: str) -> ProjectRequirementRecord | None:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_record_id = str(record_id or "").strip()
        if not normalized_project_id or not normalized_username or not normalized_record_id:
            return None
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_requirement_records
                WHERE project_id = %s AND username = %s AND id = %s
                """,
                (normalized_project_id, normalized_username, normalized_record_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return ProjectRequirementRecord(**row["payload"])

    def list_by_project(self, project_id: str, limit: int = 200) -> list[ProjectRequirementRecord]:
        normalized_project_id = str(project_id or "").strip()
        safe_limit = max(1, min(int(limit or 200), 500))
        if not normalized_project_id:
            return []
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_requirement_records
                WHERE project_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (normalized_project_id, safe_limit),
            )
            rows = cur.fetchall() or []
        records: list[ProjectRequirementRecord] = []
        for row in rows:
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            try:
                records.append(ProjectRequirementRecord(**payload))
            except Exception:
                continue
        return records

    def delete(self, project_id: str, username: str, record_id: str) -> int:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_record_id = str(record_id or "").strip()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM project_requirement_records
                WHERE project_id = %s AND username = %s AND id = %s
                """,
                (normalized_project_id, normalized_username, normalized_record_id),
            )
            return cur.rowcount

    def delete_by_id(self, project_id: str, record_id: str) -> int:
        normalized_project_id = str(project_id or "").strip()
        normalized_record_id = str(record_id or "").strip()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM project_requirement_records
                WHERE project_id = %s AND id = %s
                """,
                (normalized_project_id, normalized_record_id),
            )
            return cur.rowcount

    def new_record_id(self) -> str:
        return f"req-{uuid.uuid4().hex[:12]}"
