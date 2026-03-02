"""用户存储 — JSON 文件 + bcrypt"""

from __future__ import annotations

import json
import hashlib
import hmac
import os
from dataclasses import dataclass, asdict, field
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
    created_at: str = field(default_factory=_now_iso)


class UserStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "users"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, username: str) -> Path:
        return self._dir / f"{username}.json"

    def save(self, user: User) -> None:
        self._path(user.username).write_text(
            json.dumps(asdict(user), ensure_ascii=False, indent=2))

    def get(self, username: str) -> User | None:
        p = self._path(username)
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        return User(**data)

    def has_any(self) -> bool:
        return any(self._dir.glob("*.json"))
