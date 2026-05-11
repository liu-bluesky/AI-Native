"""Department store (PostgreSQL implementation)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict

from psycopg.rows import dict_row

from stores.json.department_store import Department, UserDepartmentMembership, _now_iso
from stores.postgres._connection import connect


_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}")
_EMAIL_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class DepartmentStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS departments (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS department_memberships (
                    username TEXT NOT NULL,
                    department_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (username, department_id)
                );

                CREATE INDEX IF NOT EXISTS idx_department_memberships_department
                ON department_memberships (department_id);
                """
            )

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

    def _to_department(self, payload: dict) -> Department:
        return Department(
            id=str(payload.get("id") or ""),
            name=str(payload.get("name") or ""),
            parent_id=str(payload.get("parent_id") or ""),
            manager_username=str(payload.get("manager_username") or ""),
            description=str(payload.get("description") or ""),
            enabled=bool(payload.get("enabled", True)),
            sort_order=int(payload.get("sort_order", 100) or 100),
            created_at=str(payload.get("created_at") or _now_iso()),
            updated_at=str(payload.get("updated_at") or _now_iso()),
        )

    def _to_membership(self, payload: dict) -> UserDepartmentMembership:
        return UserDepartmentMembership(
            username=str(payload.get("username") or ""),
            department_id=str(payload.get("department_id") or ""),
            is_primary=bool(payload.get("is_primary", False)),
            enabled=bool(payload.get("enabled", True)),
            joined_at=str(payload.get("joined_at") or _now_iso()),
        )

    def list_departments(self) -> list[Department]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM departments
                ORDER BY COALESCE((payload->>'sort_order')::int, 100), payload->>'name', id
                """
            )
            rows = cur.fetchall() or []
        return [self._to_department(row["payload"]) for row in rows]

    def get_department(self, department_id: str) -> Department | None:
        normalized_id = self._normalize_department_id(department_id)
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM departments WHERE id = %s", (normalized_id,))
            row = cur.fetchone()
        return self._to_department(row["payload"]) if row else None

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
        payload = json.dumps(asdict(normalized), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO departments (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (normalized.id, payload),
            )
        return normalized

    def delete_department(self, department_id: str) -> bool:
        normalized_id = self._normalize_department_id(department_id)
        if any(item.parent_id == normalized_id for item in self.list_departments()):
            raise ValueError("Cannot delete department with child departments")
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM department_memberships WHERE department_id = %s", (normalized_id,))
            cur.execute("DELETE FROM departments WHERE id = %s", (normalized_id,))
            return cur.rowcount > 0

    def list_memberships(self) -> list[UserDepartmentMembership]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM department_memberships
                ORDER BY username ASC, department_id ASC
                """
            )
            rows = cur.fetchall() or []
        return [self._to_membership(row["payload"]) for row in rows]

    def list_user_memberships(self, username: str) -> list[UserDepartmentMembership]:
        normalized_username = self._normalize_username(username)
        if not normalized_username:
            return []
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM department_memberships WHERE username = %s",
                (normalized_username,),
            )
            rows = cur.fetchall() or []
        return [self._to_membership(row["payload"]) for row in rows if row["payload"].get("enabled", True)]

    def list_department_memberships(self, department_id: str) -> list[UserDepartmentMembership]:
        normalized_id = self._normalize_department_id(department_id)
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM department_memberships WHERE department_id = %s",
                (normalized_id,),
            )
            rows = cur.fetchall() or []
        return [self._to_membership(row["payload"]) for row in rows if row["payload"].get("enabled", True)]

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
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM department_memberships WHERE username = %s", (normalized_username,))
            for item in next_items:
                cur.execute(
                    """
                    INSERT INTO department_memberships (username, department_id, payload, updated_at)
                    VALUES (%s, %s, %s::jsonb, NOW())
                    ON CONFLICT (username, department_id) DO UPDATE
                    SET payload = EXCLUDED.payload, updated_at = NOW()
                    """,
                    (item.username, item.department_id, json.dumps(asdict(item), ensure_ascii=False)),
                )
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
        existing_by_user = {
            item.username: item for item in self.list_department_memberships(normalized_id)
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
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM department_memberships WHERE department_id = %s", (normalized_id,))
            for item in next_items:
                cur.execute(
                    """
                    INSERT INTO department_memberships (username, department_id, payload, updated_at)
                    VALUES (%s, %s, %s::jsonb, NOW())
                    ON CONFLICT (username, department_id) DO UPDATE
                    SET payload = EXCLUDED.payload, updated_at = NOW()
                    """,
                    (item.username, item.department_id, json.dumps(asdict(item), ensure_ascii=False)),
                )
        return next_items

    def remove_user_from_all_departments(self, username: str) -> list[str]:
        normalized_username = self._normalize_username(username)
        removed = [item.department_id for item in self.list_user_memberships(normalized_username)]
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM department_memberships WHERE username = %s", (normalized_username,))
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
        if not normalized_ids:
            return []
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
