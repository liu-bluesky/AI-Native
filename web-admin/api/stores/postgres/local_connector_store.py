"""Local connector store (PostgreSQL implementation)."""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from psycopg import connect
from psycopg.rows import dict_row

from stores.json.local_connector_store import (
    LocalConnectorPairCode,
    LocalConnectorRecord,
    LocalConnectorWorkspacePickSession,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalConnectorStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS local_connector_pair_codes (
                    code TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS local_connectors (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS local_connector_workspace_pick_sessions (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def new_connector_id(self) -> str:
        return f"lc-{uuid.uuid4().hex[:12]}"

    def new_connector_token(self) -> str:
        return f"lct-{secrets.token_hex(24)}"

    def new_workspace_pick_session_id(self) -> str:
        return f"lcwps-{uuid.uuid4().hex[:12]}"

    def new_workspace_pick_session_token(self) -> str:
        return f"lcwpt-{secrets.token_hex(24)}"

    def create_pair_code(
        self,
        owner_username: str,
        note: str = "",
        ttl_minutes: int = 10,
        permanent: bool = False,
    ) -> LocalConnectorPairCode:
        permanent_flag = bool(permanent)
        safe_ttl = max(1, min(int(ttl_minutes or 10), 60 * 24 * 365))
        now = datetime.now(timezone.utc)
        item = LocalConnectorPairCode(
            code=f"LC-{secrets.token_hex(3).upper()}",
            owner_username=str(owner_username or "").strip(),
            note=str(note or "").strip()[:200],
            ttl_minutes=0 if permanent_flag else safe_ttl,
            permanent=permanent_flag,
            expires_at="" if permanent_flag else (now + timedelta(minutes=safe_ttl)).isoformat(),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        self.save_pair_code(item)
        return item

    def save_pair_code(self, item: LocalConnectorPairCode) -> None:
        payload = json.dumps(asdict(item), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO local_connector_pair_codes (code, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (code) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (item.code, payload),
            )

    def get_pair_code(self, code: str) -> Optional[LocalConnectorPairCode]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM local_connector_pair_codes WHERE code = %s",
                (str(code or "").strip(),),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return LocalConnectorPairCode(**row["payload"])

    def list_pair_codes(self, owner_username: str = "") -> list[LocalConnectorPairCode]:
        normalized_owner = str(owner_username or "").strip()
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM local_connector_pair_codes ORDER BY updated_at DESC")
            rows = cur.fetchall()
        items = [LocalConnectorPairCode(**row["payload"]) for row in rows]
        if normalized_owner:
            items = [item for item in items if item.owner_username == normalized_owner]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def is_pair_code_expired(self, item: LocalConnectorPairCode) -> bool:
        if bool(getattr(item, "permanent", False)):
            return False
        raw = str(item.expires_at or "").strip()
        if not raw:
            return False
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        except ValueError:
            return True

    def consume_pair_code(self, code: str, connector_id: str) -> Optional[LocalConnectorPairCode]:
        item = self.get_pair_code(code)
        if item is None:
            return None
        now = _now_iso()
        item.used_at = now
        item.connector_id = str(connector_id or "").strip()
        item.updated_at = now
        self.save_pair_code(item)
        return item

    def create_workspace_pick_session(
        self,
        *,
        owner_username: str,
        connector_id: str,
        ttl_seconds: int = 60,
    ) -> LocalConnectorWorkspacePickSession:
        safe_ttl = max(15, min(int(ttl_seconds or 60), 300))
        now = datetime.now(timezone.utc)
        item = LocalConnectorWorkspacePickSession(
            id=self.new_workspace_pick_session_id(),
            token=self.new_workspace_pick_session_token(),
            owner_username=str(owner_username or "").strip(),
            connector_id=str(connector_id or "").strip(),
            expires_at=(now + timedelta(seconds=safe_ttl)).isoformat(),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        self.save_workspace_pick_session(item)
        return item

    def save_workspace_pick_session(self, item: LocalConnectorWorkspacePickSession) -> None:
        payload = json.dumps(asdict(item), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO local_connector_workspace_pick_sessions (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (item.id, payload),
            )

    def get_workspace_pick_session(self, session_id: str) -> Optional[LocalConnectorWorkspacePickSession]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM local_connector_workspace_pick_sessions WHERE id = %s",
                (str(session_id or "").strip(),),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return LocalConnectorWorkspacePickSession(**row["payload"])

    def is_workspace_pick_session_expired(self, item: LocalConnectorWorkspacePickSession) -> bool:
        raw = str(item.expires_at or "").strip()
        if not raw:
            return True
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        except ValueError:
            return True

    def consume_workspace_pick_session(self, session_id: str) -> Optional[LocalConnectorWorkspacePickSession]:
        item = self.get_workspace_pick_session(session_id)
        if item is None:
            return None
        now = _now_iso()
        item.used_at = now
        item.updated_at = now
        self.save_workspace_pick_session(item)
        return item

    def save_connector(self, item: LocalConnectorRecord) -> None:
        payload = json.dumps(asdict(item), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO local_connectors (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (item.id, payload),
            )

    def get_connector(self, connector_id: str) -> Optional[LocalConnectorRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM local_connectors WHERE id = %s",
                (str(connector_id or "").strip(),),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return LocalConnectorRecord(**row["payload"])

    def list_connectors(self, owner_username: str = "") -> list[LocalConnectorRecord]:
        normalized_owner = str(owner_username or "").strip()
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM local_connectors ORDER BY updated_at DESC")
            rows = cur.fetchall()
        items = [LocalConnectorRecord(**row["payload"]) for row in rows]
        if normalized_owner:
            items = [item for item in items if item.owner_username == normalized_owner]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items

    def get_connector_by_token(self, connector_token: str) -> Optional[LocalConnectorRecord]:
        expected = str(connector_token or "").strip()
        if not expected:
            return None
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM local_connectors")
            rows = cur.fetchall()
        for row in rows:
            item = LocalConnectorRecord(**row["payload"])
            if item.connector_token == expected:
                return item
        return None

    def delete_connector(self, connector_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM local_connectors WHERE id = %s",
                (str(connector_id or "").strip(),),
            )
            return cur.rowcount > 0
