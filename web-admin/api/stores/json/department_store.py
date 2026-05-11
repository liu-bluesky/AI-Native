"""Department store for hierarchical data scope."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}")
_EMAIL_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class Department:
    id: str
    name: str
    parent_id: str = ""
    manager_username: str = ""
    description: str = ""
    enabled: bool = True
    sort_order: int = 100
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class UserDepartmentMembership:
    username: str
    department_id: str
    is_primary: bool = False
    enabled: bool = True
    joined_at: str = field(default_factory=_now_iso)


class DepartmentStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "departments"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._departments_path = self._dir / "departments.json"
        self._memberships_path = self._dir / "memberships.json"

    def new_id(self) -> str:
        return f"dept-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _normalize_department_id(value: str) -> str:
        department_id = str(value or "").strip()
        if not department_id:
            raise ValueError("Department id is required")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}", department_id):
            raise ValueError("Invalid department id")
        return department_id

    @staticmethod
    def _normalize_username(value: str) -> str:
        username = str(value or "").strip()
        if not username:
            return ""
        if not (
            _USERNAME_PATTERN.fullmatch(username)
            or _EMAIL_USERNAME_PATTERN.fullmatch(username)
        ):
            raise ValueError("Invalid username")
        return username

    def _read_departments(self) -> list[dict]:
        if not self._departments_path.exists():
            return []
        data = json.loads(self._departments_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []

    def _write_departments(self, items: list[Department]) -> None:
        items = sorted(items, key=lambda item: (int(item.sort_order), item.name, item.id))
        self._departments_path.write_text(
            json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_memberships(self) -> list[dict]:
        if not self._memberships_path.exists():
            return []
        data = json.loads(self._memberships_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []

    def _write_memberships(self, items: list[UserDepartmentMembership]) -> None:
        items = sorted(items, key=lambda item: (item.username, item.department_id))
        self._memberships_path.write_text(
            json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_departments(self) -> list[Department]:
        departments: list[Department] = []
        for item in self._read_departments():
            try:
                departments.append(
                    Department(
                        id=str(item.get("id") or ""),
                        name=str(item.get("name") or ""),
                        parent_id=str(item.get("parent_id") or ""),
                        manager_username=str(item.get("manager_username") or ""),
                        description=str(item.get("description") or ""),
                        enabled=bool(item.get("enabled", True)),
                        sort_order=int(item.get("sort_order", 100) or 100),
                        created_at=str(item.get("created_at") or _now_iso()),
                        updated_at=str(item.get("updated_at") or _now_iso()),
                    )
                )
            except Exception:
                continue
        departments.sort(key=lambda item: (int(item.sort_order), item.name, item.id))
        return departments

    def get_department(self, department_id: str) -> Department | None:
        normalized_id = self._normalize_department_id(department_id)
        for item in self.list_departments():
            if item.id == normalized_id:
                return item
        return None

    def _would_create_cycle(self, department_id: str, parent_id: str) -> bool:
        if not parent_id:
            return False
        if department_id == parent_id:
            return True
        by_id = {item.id: item for item in self.list_departments()}
        current = by_id.get(parent_id)
        seen: set[str] = set()
        while current is not None:
            if current.id == department_id:
                return True
            if current.id in seen:
                return True
            seen.add(current.id)
            current = by_id.get(current.parent_id)
        return False

    def save_department(self, department: Department) -> Department:
        department_id = self._normalize_department_id(department.id)
        parent_id = str(department.parent_id or "").strip()
        if parent_id:
            self._normalize_department_id(parent_id)
            if self.get_department(parent_id) is None:
                raise ValueError("Parent department not found")
        if self._would_create_cycle(department_id, parent_id):
            raise ValueError("Department hierarchy cycle is not allowed")
        name = str(department.name or "").strip()
        if not name:
            raise ValueError("Department name is required")
        manager_username = self._normalize_username(department.manager_username)
        existing = self.get_department(department_id)
        now = _now_iso()
        normalized = Department(
            id=department_id,
            name=name,
            parent_id=parent_id,
            manager_username=manager_username,
            description=str(department.description or "").strip(),
            enabled=bool(department.enabled),
            sort_order=int(department.sort_order or 100),
            created_at=existing.created_at if existing else (department.created_at or now),
            updated_at=now,
        )
        items = [item for item in self.list_departments() if item.id != department_id]
        items.append(normalized)
        self._write_departments(items)
        return normalized

    def delete_department(self, department_id: str) -> bool:
        normalized_id = self._normalize_department_id(department_id)
        items = self.list_departments()
        if not any(item.id == normalized_id for item in items):
            return False
        if any(item.parent_id == normalized_id for item in items):
            raise ValueError("Cannot delete department with child departments")
        self._write_departments([item for item in items if item.id != normalized_id])
        self._write_memberships(
            [item for item in self.list_memberships() if item.department_id != normalized_id]
        )
        return True

    def list_memberships(self) -> list[UserDepartmentMembership]:
        memberships: list[UserDepartmentMembership] = []
        for item in self._read_memberships():
            try:
                username = self._normalize_username(str(item.get("username") or ""))
                department_id = self._normalize_department_id(str(item.get("department_id") or ""))
                if not username:
                    continue
                memberships.append(
                    UserDepartmentMembership(
                        username=username,
                        department_id=department_id,
                        is_primary=bool(item.get("is_primary", False)),
                        enabled=bool(item.get("enabled", True)),
                        joined_at=str(item.get("joined_at") or _now_iso()),
                    )
                )
            except Exception:
                continue
        return memberships

    def list_user_memberships(self, username: str) -> list[UserDepartmentMembership]:
        normalized_username = self._normalize_username(username)
        if not normalized_username:
            return []
        return [
            item
            for item in self.list_memberships()
            if item.username == normalized_username and bool(item.enabled)
        ]

    def list_department_memberships(self, department_id: str) -> list[UserDepartmentMembership]:
        normalized_id = self._normalize_department_id(department_id)
        return [
            item
            for item in self.list_memberships()
            if item.department_id == normalized_id and bool(item.enabled)
        ]

    def set_user_memberships(
        self,
        username: str,
        department_ids: list[str],
        *,
        primary_department_id: str = "",
    ) -> list[UserDepartmentMembership]:
        normalized_username = self._normalize_username(username)
        if not normalized_username:
            raise ValueError("Username is required")
        known_ids = {item.id for item in self.list_departments()}
        normalized_department_ids: list[str] = []
        seen: set[str] = set()
        for raw_id in department_ids:
            department_id = self._normalize_department_id(raw_id)
            if department_id not in known_ids:
                raise ValueError(f"Department not found: {department_id}")
            if department_id in seen:
                continue
            seen.add(department_id)
            normalized_department_ids.append(department_id)
        primary_id = str(primary_department_id or "").strip()
        if primary_id and primary_id not in normalized_department_ids:
            primary_id = ""
        if not primary_id and normalized_department_ids:
            primary_id = normalized_department_ids[0]
        current = [
            item for item in self.list_memberships() if item.username != normalized_username
        ]
        now = _now_iso()
        next_items = [
            UserDepartmentMembership(
                username=normalized_username,
                department_id=department_id,
                is_primary=department_id == primary_id,
                enabled=True,
                joined_at=now,
            )
            for department_id in normalized_department_ids
        ]
        self._write_memberships([*current, *next_items])
        return next_items

    def set_department_members(
        self,
        department_id: str,
        usernames: list[str],
    ) -> list[UserDepartmentMembership]:
        normalized_id = self._normalize_department_id(department_id)
        if self.get_department(normalized_id) is None:
            raise ValueError("Department not found")
        normalized_usernames: list[str] = []
        seen: set[str] = set()
        for raw_username in usernames:
            username = self._normalize_username(raw_username)
            if not username or username in seen:
                continue
            seen.add(username)
            normalized_usernames.append(username)
        current = [
            item for item in self.list_memberships() if item.department_id != normalized_id
        ]
        existing_by_user = {
            item.username: item
            for item in self.list_memberships()
            if item.department_id == normalized_id
        }
        now = _now_iso()
        next_items: list[UserDepartmentMembership] = []
        for username in normalized_usernames:
            existing = existing_by_user.get(username)
            next_items.append(
                UserDepartmentMembership(
                    username=username,
                    department_id=normalized_id,
                    is_primary=bool(existing.is_primary) if existing else False,
                    enabled=True,
                    joined_at=existing.joined_at if existing else now,
                )
            )
        self._write_memberships([*current, *next_items])
        return next_items

    def remove_user_from_all_departments(self, username: str) -> list[str]:
        normalized_username = self._normalize_username(username)
        removed = [
            item.department_id
            for item in self.list_memberships()
            if item.username == normalized_username
        ]
        if not removed:
            return []
        self._write_memberships(
            [item for item in self.list_memberships() if item.username != normalized_username]
        )
        return removed

    def list_managed_department_ids(self, username: str) -> list[str]:
        normalized_username = self._normalize_username(username)
        if not normalized_username:
            return []
        return [
            item.id
            for item in self.list_departments()
            if bool(item.enabled) and item.manager_username == normalized_username
        ]

    def list_descendant_department_ids(self, department_id: str, *, include_self: bool = True) -> list[str]:
        normalized_id = self._normalize_department_id(department_id)
        departments = [item for item in self.list_departments() if bool(item.enabled)]
        children_by_parent: dict[str, list[str]] = {}
        for item in departments:
            children_by_parent.setdefault(item.parent_id, []).append(item.id)
        result: list[str] = []
        queue = [normalized_id]
        seen: set[str] = set()
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if include_self or current != normalized_id:
                result.append(current)
            queue.extend(children_by_parent.get(current, []))
        return result

    def list_usernames_for_departments(self, department_ids: list[str]) -> list[str]:
        normalized_ids = {self._normalize_department_id(item) for item in department_ids if item}
        usernames: list[str] = []
        seen: set[str] = set()
        for item in self.list_memberships():
            if not bool(item.enabled) or item.department_id not in normalized_ids:
                continue
            if item.username in seen:
                continue
            seen.add(item.username)
            usernames.append(item.username)
        return sorted(usernames)
