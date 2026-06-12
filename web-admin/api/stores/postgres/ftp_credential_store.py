"""Global FTP credential store (PostgreSQL implementation)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from stores.json.ftp_credential_store import FtpCredential
from stores.postgres._connection import connect


def _to_iso(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return str(value or "").strip()


def _coerce_credential(row: dict[str, Any] | None) -> FtpCredential | None:
    if row is None or not isinstance(row.get("payload"), dict):
        return None
    payload = dict(row["payload"])
    for key in ("created_at", "updated_at"):
        if key in payload:
            payload[key] = _to_iso(payload.get(key))
    try:
        return FtpCredential(**payload)
    except TypeError:
        return None


class FtpCredentialStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ftp_credentials (
                    id TEXT PRIMARY KEY,
                    created_by TEXT NOT NULL DEFAULT '',
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_ftp_credentials_created_by
                ON ftp_credentials (created_by, updated_at DESC);
                """
            )

    def new_id(self) -> str:
        return f"ftp-{uuid.uuid4().hex[:12]}"

    def list_all(self) -> list[FtpCredential]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM ftp_credentials
                ORDER BY updated_at DESC
                """
            )
            rows = cur.fetchall()
        return [item for row in rows if (item := _coerce_credential(row)) is not None]

    def get(self, credential_id: str) -> FtpCredential | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM ftp_credentials WHERE id = %s", (str(credential_id or "").strip(),))
            row = cur.fetchone()
        return _coerce_credential(row)

    def save(self, credential: FtpCredential) -> FtpCredential:
        payload = json.dumps(asdict(credential), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ftp_credentials (id, created_by, enabled, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE
                SET created_by = EXCLUDED.created_by,
                    enabled = EXCLUDED.enabled,
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                """,
                (credential.id, credential.created_by, credential.enabled, payload),
            )
        return credential

    def delete(self, credential_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM ftp_credentials WHERE id = %s", (str(credential_id or "").strip(),))
            return bool(cur.rowcount)
