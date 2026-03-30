"""用户存储 — JSON 文件 + bcrypt"""

from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: bytes | None = None) -> str:
    """PBKDF2-SHA256 密码哈希（不依赖 bcrypt 外部库）"""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, dk_hex = stored.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


@dataclass(frozen=True)
class User:
    username: str
    password_hash: str
    role: str = "admin"
    default_ai_provider_id: str = ""
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)


class UserStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "users"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _normalize_username(self, username: str) -> str:
        value = str(username or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}", value):
            raise ValueError("Invalid username")
        return value

    def _path(self, username: str) -> Path:
        normalized = self._normalize_username(username)
        return self._dir / f"{normalized}.json"

    def save(self, user: User) -> None:
        payload = {
            "username": user.username,
            "password_hash": user.password_hash,
            "role": user.role,
            "default_ai_provider_id": str(user.default_ai_provider_id or "").strip(),
            "created_by": str(user.created_by or "").strip(),
            "created_at": user.created_at,
        }
        self._path(user.username).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2))

    def get(self, username: str) -> User | None:
        p = self._path(username)
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        return self._to_user(data)

    def has_any(self) -> bool:
        return any(self._dir.glob("*.json"))

    def list_all(self) -> list[User]:
        users: list[User] = []
        for path in self._dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                users.append(self._to_user(data))
            except Exception:
                continue
        users.sort(key=lambda item: str(item.created_at or ""), reverse=True)
        return users

    def delete(self, username: str) -> bool:
        p = self._path(username)
        if not p.exists():
            return False
        p.unlink()
        return True

    def _to_user(self, data: dict) -> User:
        return User(
            username=str(data.get("username") or ""),
            password_hash=str(data.get("password_hash") or ""),
            role=str(data.get("role") or "user"),
            default_ai_provider_id=str(data.get("default_ai_provider_id") or "").strip(),
            created_by=str(data.get("created_by") or "").strip(),
            created_at=str(data.get("created_at") or _now_iso()),
        )
