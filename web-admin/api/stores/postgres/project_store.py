"""项目存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from psycopg import connect
from psycopg.rows import dict_row

from stores.json.project_store import ProjectConfig, ProjectMember


class ProjectStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS project_members (
                    project_id TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (project_id, employee_id)
                );

                CREATE INDEX IF NOT EXISTS idx_project_members_project
                ON project_members (project_id, joined_at DESC);
                """
            )

    def save(self, project: ProjectConfig) -> None:
        payload = json.dumps(asdict(project), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (project.id, payload),
            )

    def get(self, project_id: str) -> ProjectConfig | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM projects WHERE id = %s", (project_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return ProjectConfig(**row["payload"])

    def list_all(self) -> list[ProjectConfig]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM projects ORDER BY id")
            rows = cur.fetchall()
        return [ProjectConfig(**row["payload"]) for row in rows]

    def delete(self, project_id: str) -> bool:
        with self._conn.transaction():
            with self._conn.cursor() as cur:
                cur.execute("DELETE FROM project_members WHERE project_id = %s", (project_id,))
                cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
                return cur.rowcount > 0

    def new_id(self) -> str:
        return f"proj-{uuid.uuid4().hex[:8]}"

    def list_members(self, project_id: str) -> list[ProjectMember]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM project_members WHERE project_id = %s ORDER BY joined_at DESC",
                (project_id,),
            )
            rows = cur.fetchall()
        return [ProjectMember(**row["payload"]) for row in rows]

    def get_member(self, project_id: str, employee_id: str) -> ProjectMember | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM project_members WHERE project_id = %s AND employee_id = %s",
                (project_id, employee_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return ProjectMember(**row["payload"])

    def upsert_member(self, member: ProjectMember) -> None:
        payload = json.dumps(asdict(member), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_members (project_id, employee_id, payload, joined_at)
                VALUES (%s, %s, %s::jsonb, %s)
                ON CONFLICT (project_id, employee_id) DO UPDATE
                SET payload = EXCLUDED.payload, joined_at = EXCLUDED.joined_at
                """,
                (member.project_id, member.employee_id, payload, member.joined_at),
            )

    def remove_member(self, project_id: str, employee_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM project_members WHERE project_id = %s AND employee_id = %s",
                (project_id, employee_id),
            )
            return cur.rowcount > 0
