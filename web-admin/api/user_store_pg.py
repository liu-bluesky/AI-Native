"""用户存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json

from psycopg import connect
from psycopg.rows import dict_row

from user_store import User


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

    def save(self, user: User) -> None:
        payload = json.dumps(
            {
                "username": user.username,
                "password_hash": user.password_hash,
                "role": user.role,
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
        return User(**row["payload"])

    def has_any(self) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM users")
            row = cur.fetchone()
        return bool(row and int(row["cnt"]) > 0)
