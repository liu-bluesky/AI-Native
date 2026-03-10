"""角色存储层"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.role_permissions import DEFAULT_USER_PERMISSION_KEYS, resolve_role_permissions


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RoleConfig:
    id: str
    name: str
    description: str = ""
    permissions: list[str] = field(default_factory=list)
    built_in: bool = False
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


def default_roles() -> list[RoleConfig]:
    return [
        RoleConfig(
            id="admin",
            name="管理员",
            description="系统管理员，拥有全部权限",
            permissions=["*"],
            built_in=True,
        ),
        RoleConfig(
            id="user",
            name="普通用户",
            description="默认业务用户角色",
            permissions=list(DEFAULT_USER_PERMISSION_KEYS),
            built_in=True,
        ),
    ]


class RoleStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "roles"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ensure_defaults()

    def _normalize_role_id(self, role_id: str) -> str:
        value = str(role_id or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,31}", value):
            raise ValueError("Invalid role id")
        return value

    def _path(self, role_id: str) -> Path:
        return self._dir / f"{self._normalize_role_id(role_id)}.json"

    def _read(self, role_id: str) -> RoleConfig | None:
        path = self._path(role_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["permissions"] = resolve_role_permissions(data.get("permissions"), data.get("id", role_id))
        return RoleConfig(**data)

    def _ensure_defaults(self) -> None:
        for item in default_roles():
            existing = self._read(item.id)
            if existing is not None:
                if item.id == "user" and bool(existing.built_in):
                    merged = sorted(set(existing.permissions or []) | set(DEFAULT_USER_PERMISSION_KEYS))
                    if merged != sorted(existing.permissions or []):
                        existing.permissions = merged
                        self.save(existing)
                continue
            self.save(item)

    def save(self, role: RoleConfig) -> None:
        role_id = self._normalize_role_id(role.id)
        payload = asdict(role)
        payload["id"] = role_id
        payload["permissions"] = resolve_role_permissions(payload.get("permissions"), role_id)
        if not payload.get("created_at"):
            payload["created_at"] = _now_iso()
        payload["updated_at"] = _now_iso()
        self._path(role_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, role_id: str) -> RoleConfig | None:
        self._ensure_defaults()
        return self._read(role_id)

    def list_all(self) -> list[RoleConfig]:
        self._ensure_defaults()
        roles: list[RoleConfig] = []
        for path in sorted(self._dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            data["permissions"] = resolve_role_permissions(data.get("permissions"), data.get("id", ""))
            roles.append(RoleConfig(**data))
        return roles

    def delete(self, role_id: str) -> bool:
        role = self.get(role_id)
        if role is None:
            return False
        if bool(role.built_in):
            return False
        path = self._path(role.id)
        if not path.exists():
            return False
        path.unlink()
        return True
