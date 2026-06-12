"""Global FTP credential store (JSON implementation)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from stores.json.project_chat_store import _now_iso, _safe_token


@dataclass
class FtpCredential:
    id: str
    name: str
    username: str
    host: str = ""
    port: str = ""
    password: str = ""
    enabled: bool = True
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


def normalize_ftp_credential_payload(
    value: dict[str, Any],
    *,
    existing: FtpCredential | None = None,
    created_by: str = "",
) -> FtpCredential:
    source = value if isinstance(value, dict) else {}
    now = _now_iso()
    credential_id = (
        str(source.get("id") or "").strip()
        or (existing.id if existing else "")
        or f"ftp-{uuid.uuid4().hex[:12]}"
    )
    password = str(source.get("password") or "").strip()
    if not password and existing is not None:
        password = existing.password
    owner = str(existing.created_by if existing else created_by or source.get("created_by") or "").strip()
    return FtpCredential(
        id=credential_id,
        name=str(source.get("name") or (existing.name if existing else "") or source.get("host") or source.get("username") or "").strip()[:160],
        host=str(source.get("host") or (existing.host if existing else "") or source.get("server") or "").strip()[:300],
        port=str(source.get("port") or (existing.port if existing else "") or "").strip()[:20],
        username=str(source.get("username") or (existing.username if existing else "") or "").strip()[:200],
        password=password[:1000],
        enabled=bool(source.get("enabled", existing.enabled if existing else True)),
        created_by=owner,
        created_at=str(existing.created_at if existing else source.get("created_at") or now),
        updated_at=now,
    )


class FtpCredentialStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "ftp-credentials"
        self._root.mkdir(parents=True, exist_ok=True)

    def new_id(self) -> str:
        return f"ftp-{uuid.uuid4().hex[:12]}"

    def _path(self, credential_id: str) -> Path:
        return self._root / f"{_safe_token(credential_id)}.json"

    def list_all(self) -> list[FtpCredential]:
        items: list[FtpCredential] = []
        for path in sorted(self._root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                items.append(FtpCredential(**payload))
            except Exception:
                continue
        return items

    def get(self, credential_id: str) -> FtpCredential | None:
        path = self._path(str(credential_id or "").strip())
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return FtpCredential(**payload)
        except Exception:
            return None

    def save(self, credential: FtpCredential) -> FtpCredential:
        credential.updated_at = _now_iso()
        self._path(credential.id).write_text(
            json.dumps(asdict(credential), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return credential

    def delete(self, credential_id: str) -> bool:
        path = self._path(str(credential_id or "").strip())
        if not path.exists():
            return False
        path.unlink()
        return True
