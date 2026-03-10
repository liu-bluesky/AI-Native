"""角色存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json

from psycopg import connect
from psycopg.rows import dict_row

from core.role_permissions import DEFAULT_USER_PERMISSION_KEYS, resolve_role_permissions
from stores.json.role_store import RoleConfig, _now_iso, default_roles


class RoleStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()
        self._ensure_defaults()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS roles (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def _ensure_defaults(self) -> None:
        for item in default_roles():
            existing = self.get(item.id)
            if existing is not None:
                if item.id == "user" and bool(existing.built_in):
                    merged = sorted(set(existing.permissions or []) | set(DEFAULT_USER_PERMISSION_KEYS))
                    if merged != sorted(existing.permissions or []):
                        existing.permissions = merged
                        self.save(existing)
                continue
            self.save(item)

    def save(self, role: RoleConfig) -> None:
        role_id = str(role.id or "").strip().lower()
        created_at = role.created_at or _now_iso()
        updated_at = _now_iso()
        payload = json.dumps(
            {
                "id": role_id,
                "name": role.name,
                "description": role.description,
                "permissions": resolve_role_permissions(role.permissions, role_id),
                "built_in": bool(role.built_in),
                "created_at": created_at,
                "updated_at": updated_at,
            },
            ensure_ascii=False,
        )
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO roles (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (role_id, payload),
            )

    def get(self, role_id: str) -> RoleConfig | None:
        normalized = str(role_id or "").strip().lower()
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM roles WHERE id = %s", (normalized,))
            row = cur.fetchone()
        if row is None:
            return None
        payload = row["payload"]
        payload["permissions"] = resolve_role_permissions(payload.get("permissions"), normalized)
        return RoleConfig(**payload)

    def list_all(self) -> list[RoleConfig]:
        self._ensure_defaults()
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM roles ORDER BY id")
            rows = cur.fetchall()
        results: list[RoleConfig] = []
        for row in rows:
            payload = row["payload"]
            payload["permissions"] = resolve_role_permissions(
                payload.get("permissions"),
                payload.get("id", ""),
            )
            results.append(RoleConfig(**payload))
        return results

    def delete(self, role_id: str) -> bool:
        role = self.get(role_id)
        if role is None or bool(role.built_in):
            return False
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM roles WHERE id = %s", (role.id,))
            return cur.rowcount > 0
