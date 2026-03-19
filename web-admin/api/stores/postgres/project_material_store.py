"""项目素材库存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from psycopg import connect
from psycopg.rows import dict_row

from stores.json.project_material_store import ProjectMaterialAsset


def _to_iso(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    text = str(value or "").strip()
    return text


class ProjectMaterialStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_material_assets (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_project_material_assets_project
                ON project_material_assets (project_id, updated_at DESC);
                """
            )

    def new_id(self) -> str:
        return f"asset-{uuid.uuid4().hex[:8]}"

    def list_by_project(self, project_id: str) -> list[ProjectMaterialAsset]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_material_assets
                WHERE project_id = %s
                ORDER BY updated_at DESC
                """,
                (str(project_id or "").strip(),),
            )
            rows = cur.fetchall()
        items: list[ProjectMaterialAsset] = []
        for row in rows:
            payload = row.get("payload") if isinstance(row, dict) else None
            if not isinstance(payload, dict):
                continue
            payload["created_at"] = _to_iso(payload.get("created_at"))
            payload["updated_at"] = _to_iso(payload.get("updated_at"))
            try:
                items.append(ProjectMaterialAsset(**payload))
            except TypeError:
                continue
        return items

    def get(self, project_id: str, asset_id: str) -> ProjectMaterialAsset | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM project_material_assets
                WHERE project_id = %s AND id = %s
                """,
                (str(project_id or "").strip(), str(asset_id or "").strip()),
            )
            row = cur.fetchone()
        if row is None or not isinstance(row.get("payload"), dict):
            return None
        payload = dict(row["payload"])
        payload["created_at"] = _to_iso(payload.get("created_at"))
        payload["updated_at"] = _to_iso(payload.get("updated_at"))
        return ProjectMaterialAsset(**payload)

    def save(self, asset: ProjectMaterialAsset) -> None:
        payload = json.dumps(asdict(asset), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_material_assets (id, project_id, payload, updated_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload,
                    project_id = EXCLUDED.project_id,
                    updated_at = NOW()
                """,
                (asset.id, asset.project_id, payload),
            )

    def delete(self, project_id: str, asset_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM project_material_assets
                WHERE project_id = %s AND id = %s
                """,
                (str(project_id or "").strip(), str(asset_id or "").strip()),
            )
            return cur.rowcount > 0
