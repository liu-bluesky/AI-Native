"""Local connector store (JSON implementation)."""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class LocalConnectorPairCode:
    code: str
    owner_username: str
    note: str = ""
    ttl_minutes: int = 10
    permanent: bool = False
    expires_at: str = ""
    used_at: str = ""
    connector_id: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class LocalConnectorRecord:
    id: str
    owner_username: str
    connector_token: str
    connector_name: str = ""
    platform: str = ""
    app_version: str = ""
    advertised_url: str = ""
    status: str = "paired"
    last_error: str = ""
    capabilities: dict[str, object] = field(default_factory=dict)
    manifest: dict[str, object] = field(default_factory=dict)
    health: dict[str, object] = field(default_factory=dict)
    paired_at: str = field(default_factory=_now_iso)
    last_seen_at: str = field(default_factory=_now_iso)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class LocalConnectorWorkspacePickSession:
    id: str
    token: str
    owner_username: str
    connector_id: str
    expires_at: str = ""
    used_at: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class LocalConnectorStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "local-connectors"
        self._connectors_dir = self._root / "connectors"
        self._pair_codes_dir = self._root / "pair-codes"
        self._workspace_pick_sessions_dir = self._root / "workspace-pick-sessions"
        self._connectors_dir.mkdir(parents=True, exist_ok=True)
        self._pair_codes_dir.mkdir(parents=True, exist_ok=True)
        self._workspace_pick_sessions_dir.mkdir(parents=True, exist_ok=True)

    def _connector_path(self, connector_id: str) -> Path:
        return self._connectors_dir / f"{connector_id}.json"

    def _pair_code_path(self, code: str) -> Path:
        return self._pair_codes_dir / f"{code}.json"

    def _workspace_pick_session_path(self, session_id: str) -> Path:
        return self._workspace_pick_sessions_dir / f"{session_id}.json"

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
        now = _utc_now()
        code = f"LC-{secrets.token_hex(3).upper()}"
        item = LocalConnectorPairCode(
            code=code,
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
        self._pair_code_path(item.code).write_text(
            json.dumps(asdict(item), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_pair_code(self, code: str) -> Optional[LocalConnectorPairCode]:
        path = self._pair_code_path(str(code or "").strip())
        if not path.exists():
            return None
        return LocalConnectorPairCode(**json.loads(path.read_text(encoding="utf-8")))

    def list_pair_codes(self, owner_username: str = "") -> list[LocalConnectorPairCode]:
        normalized_owner = str(owner_username or "").strip()
        items: list[LocalConnectorPairCode] = []
        for path in self._pair_codes_dir.glob("*.json"):
            try:
                item = LocalConnectorPairCode(**json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if normalized_owner and item.owner_username != normalized_owner:
                continue
            items.append(item)
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def is_pair_code_expired(self, item: LocalConnectorPairCode) -> bool:
        if bool(getattr(item, "permanent", False)):
            return False
        expires_at = _parse_iso(item.expires_at)
        if expires_at is None:
            return False
        return expires_at <= _utc_now()

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
        now = _utc_now()
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
        self._workspace_pick_session_path(item.id).write_text(
            json.dumps(asdict(item), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_workspace_pick_session(self, session_id: str) -> Optional[LocalConnectorWorkspacePickSession]:
        path = self._workspace_pick_session_path(str(session_id or "").strip())
        if not path.exists():
            return None
        return LocalConnectorWorkspacePickSession(**json.loads(path.read_text(encoding="utf-8")))

    def is_workspace_pick_session_expired(self, item: LocalConnectorWorkspacePickSession) -> bool:
        expires_at = _parse_iso(item.expires_at)
        if expires_at is None:
            return True
        return expires_at <= _utc_now()

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
        self._connector_path(item.id).write_text(
            json.dumps(asdict(item), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_connector(self, connector_id: str) -> Optional[LocalConnectorRecord]:
        path = self._connector_path(str(connector_id or "").strip())
        if not path.exists():
            return None
        return LocalConnectorRecord(**json.loads(path.read_text(encoding="utf-8")))

    def list_connectors(self, owner_username: str = "") -> list[LocalConnectorRecord]:
        normalized_owner = str(owner_username or "").strip()
        items: list[LocalConnectorRecord] = []
        for path in self._connectors_dir.glob("*.json"):
            try:
                item = LocalConnectorRecord(**json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if normalized_owner and item.owner_username != normalized_owner:
                continue
            items.append(item)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items

    def get_connector_by_token(self, connector_token: str) -> Optional[LocalConnectorRecord]:
        expected = str(connector_token or "").strip()
        if not expected:
            return None
        for item in self.list_connectors():
            if item.connector_token == expected:
                return item
        return None

    def delete_connector(self, connector_id: str) -> bool:
        path = self._connector_path(str(connector_id or "").strip())
        if not path.exists():
            return False
        path.unlink()
        return True
