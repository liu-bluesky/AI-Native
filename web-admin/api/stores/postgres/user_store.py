"""用户存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json

from stores.postgres._connection import connect
from psycopg.rows import dict_row

from stores.json.user_store import User, _now_iso


class UserStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def _to_user(self, payload: dict) -> User:
        return User(
            username=str(payload.get("username") or ""),
            password_hash=str(payload.get("password_hash") or ""),
            role=str(payload.get("role") or "user"),
            default_ai_provider_id=str(payload.get("default_ai_provider_id") or "").strip(),
            created_by=str(payload.get("created_by") or "").strip(),
            created_at=str(payload.get("created_at") or _now_iso()),
        )

    def save(self, user: User) -> None:
        payload = json.dumps(
            {
                "username": user.username,
                "password_hash": user.password_hash,
                "role": user.role,
                "default_ai_provider_id": str(user.default_ai_provider_id or "").strip(),
                "created_by": str(user.created_by or "").strip(),
                "created_at": user.created_at,
            },
            ensure_ascii=False,
        )
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (username, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (username) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (user.username, payload),
            )

    def get(self, username: str) -> User | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
        if row is None:
            return None
        return self._to_user(row["payload"])

    def has_any(self) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM users")
            row = cur.fetchone()
        return bool(row and int(row["cnt"]) > 0)

    def list_all(self) -> list[User]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM users
                ORDER BY COALESCE(NULLIF(payload->>'created_at', '')::timestamptz, updated_at) DESC, username ASC
                """
            )
            rows = cur.fetchall() or []
        return [self._to_user(row["payload"]) for row in rows]

    def delete(self, username: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s", (username,))
            deleted = cur.rowcount > 0
        return deleted
