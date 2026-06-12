"""Project deployment artifact and run store (PostgreSQL implementation)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from psycopg.rows import dict_row

from stores.json.project_chat_store import _now_iso, _safe_token
from stores.json.project_deploy_store import ProjectDeployArtifact, ProjectDeployRun
from stores.postgres._connection import connect

_DeployItem = TypeVar("_DeployItem", ProjectDeployArtifact, ProjectDeployRun)


def _to_iso(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return str(value or "").strip()


def _coerce_payload(row: dict[str, Any] | None, cls: type[_DeployItem]) -> _DeployItem | None:
    if row is None or not isinstance(row.get("payload"), dict):
        return None
    payload = dict(row["payload"])
    for key in ("uploaded_at", "ready_at", "created_at", "updated_at"):
        if key in payload:
            payload[key] = _to_iso(payload.get(key))
    try:
        return cls(**payload)
    except TypeError:
        return None


class ProjectDeployStorePostgres:
    def __init__(self, database_url: str, data_dir: Path) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._files_dir = data_dir / "project-deploy" / "files"
        self._files_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @property
    def files_dir(self) -> Path:
        return self._files_dir

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_deploy_artifacts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_project_deploy_artifacts_project
                ON project_deploy_artifacts (project_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS project_deploy_runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_project_deploy_runs_project
                ON project_deploy_runs (project_id, updated_at DESC);
                """
            )

    def new_artifact_id(self) -> str:
        return f"artifact-{uuid.uuid4().hex[:12]}"

    def new_run_id(self) -> str:
        return f"deploy-{uuid.uuid4().hex[:12]}"

    def artifact_file_dir(self, project_id: str, artifact_id: str) -> Path:
        return self._files_dir / _safe_token(project_id) / _safe_token(artifact_id)

    def save_artifact(self, artifact: ProjectDeployArtifact) -> ProjectDeployArtifact:
        payload = json.dumps(asdict(artifact), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_deploy_artifacts (id, project_id, payload, updated_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload,
                    project_id = EXCLUDED.project_id,
                    updated_at = NOW()
                """,
                (artifact.id, artifact.project_id, payload),
            )
        return artifact

    def get_artifact(self, project_id: str, artifact_id: str) -> ProjectDeployArtifact | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_deploy_artifacts
                WHERE project_id = %s AND id = %s
                """,
                (str(project_id or "").strip(), str(artifact_id or "").strip()),
            )
            row = cur.fetchone()
        return _coerce_payload(row, ProjectDeployArtifact)

    def list_artifacts(self, project_id: str, *, limit: int = 50) -> list[ProjectDeployArtifact]:
        query = """
            SELECT payload
            FROM project_deploy_artifacts
            WHERE project_id = %s
            ORDER BY updated_at DESC
        """
        params: list[object] = [str(project_id or "").strip()]
        if limit and limit > 0:
            query += " LIMIT %s"
            params.append(int(limit))
        with self._conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
        return [
            item
            for row in rows
            if (item := _coerce_payload(row, ProjectDeployArtifact)) is not None
        ]

    def save_run(self, run: ProjectDeployRun) -> ProjectDeployRun:
        run.updated_at = _now_iso()
        payload = json.dumps(asdict(run), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_deploy_runs (id, project_id, payload, updated_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload,
                    project_id = EXCLUDED.project_id,
                    updated_at = NOW()
                """,
                (run.id, run.project_id, payload),
            )
        return run

    def get_run(self, project_id: str, run_id: str) -> ProjectDeployRun | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_deploy_runs
                WHERE project_id = %s AND id = %s
                """,
                (str(project_id or "").strip(), str(run_id or "").strip()),
            )
            row = cur.fetchone()
        return _coerce_payload(row, ProjectDeployRun)

    def list_runs(self, project_id: str, *, limit: int = 50) -> list[ProjectDeployRun]:
        query = """
            SELECT payload
            FROM project_deploy_runs
            WHERE project_id = %s
            ORDER BY updated_at DESC
        """
        params: list[object] = [str(project_id or "").strip()]
        if limit and limit > 0:
            query += " LIMIT %s"
            params.append(int(limit))
        with self._conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
        return [item for row in rows if (item := _coerce_payload(row, ProjectDeployRun)) is not None]
