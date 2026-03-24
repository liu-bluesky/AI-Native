"""项目短片正式导出任务存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from stores.postgres._connection import connect
from psycopg.rows import dict_row

from stores.json.project_studio_export_store import ProjectStudioExportJob


def _to_iso(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return str(value or "").strip()


class ProjectStudioExportStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_studio_export_jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_project_studio_export_jobs_project
                ON project_studio_export_jobs (project_id, updated_at DESC);
                """
            )

    def new_id(self) -> str:
        return f"studio-export-{uuid.uuid4().hex[:8]}"

    def list_by_project(
        self,
        project_id: str,
        *,
        status: str = "",
        source_type: str = "",
        limit: int = 0,
    ) -> list[ProjectStudioExportJob]:
        query = """
            SELECT payload
            FROM project_studio_export_jobs
            WHERE project_id = %s
        """
        params: list[object] = [str(project_id or "").strip()]
        normalized_status = str(status or "").strip()
        if normalized_status:
            query += " AND payload->>'status' = %s"
            params.append(normalized_status)
        normalized_source_type = str(source_type or "").strip()
        if normalized_source_type:
            query += " AND payload->>'source_type' = %s"
            params.append(normalized_source_type)
        query += " ORDER BY updated_at DESC"
        if limit and limit > 0:
            query += " LIMIT %s"
            params.append(int(limit))
        with self._conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
        items: list[ProjectStudioExportJob] = []
        for row in rows:
            payload = row.get("payload") if isinstance(row, dict) else None
            if not isinstance(payload, dict):
                continue
            payload = dict(payload)
            payload["created_at"] = _to_iso(payload.get("created_at"))
            payload["updated_at"] = _to_iso(payload.get("updated_at"))
            payload["started_at"] = _to_iso(payload.get("started_at"))
            payload["finished_at"] = _to_iso(payload.get("finished_at"))
            try:
                items.append(ProjectStudioExportJob(**payload))
            except TypeError:
                continue
        return items

    def get(self, project_id: str, job_id: str) -> ProjectStudioExportJob | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_studio_export_jobs
                WHERE project_id = %s AND id = %s
                """,
                (str(project_id or "").strip(), str(job_id or "").strip()),
            )
            row = cur.fetchone()
        if row is None or not isinstance(row.get("payload"), dict):
            return None
        payload = dict(row["payload"])
        payload["created_at"] = _to_iso(payload.get("created_at"))
        payload["updated_at"] = _to_iso(payload.get("updated_at"))
        payload["started_at"] = _to_iso(payload.get("started_at"))
        payload["finished_at"] = _to_iso(payload.get("finished_at"))
        return ProjectStudioExportJob(**payload)

    def save(self, job: ProjectStudioExportJob) -> None:
        payload = json.dumps(asdict(job), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_studio_export_jobs (id, project_id, payload, updated_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload,
                    project_id = EXCLUDED.project_id,
                    updated_at = NOW()
                """,
                (job.id, job.project_id, payload),
            )

    def delete(self, project_id: str, job_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM project_studio_export_jobs
                WHERE project_id = %s AND id = %s
                """,
                (str(project_id or "").strip(), str(job_id or "").strip()),
            )
            return cur.rowcount > 0
