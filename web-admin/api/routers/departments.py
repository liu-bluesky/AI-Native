"""Department management routes."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from core.data_scope import (
    can_view_username_data,
    data_scope_payload,
    visible_department_ids_for,
    visible_usernames_for,
)
from core.deps import department_store, ensure_permission, require_auth, role_store, user_store
from models.requests import (
    DepartmentCreateReq,
    DepartmentUpdateReq,
    DepartmentUserAssignReq,
    UserDepartmentAssignReq,
)
from stores.json.department_store import Department

router = APIRouter(prefix="/api/departments", dependencies=[Depends(require_auth)])

_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}")
_EMAIL_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _normalize_username(value: str) -> str:
    username = str(value or "").strip()
    if not username:
        return ""
    if not (
        _USERNAME_PATTERN.fullmatch(username)
        or _EMAIL_USERNAME_PATTERN.fullmatch(username)
    ):
        raise HTTPException(400, "Invalid username")
    return username


def _ensure_user_exists(username: str, *, field: str = "username") -> None:
    normalized = _normalize_username(username)
    if normalized and user_store.get(normalized) is None:
        raise HTTPException(404, f"{field} not found: {normalized}")


def _save_department_or_400(department: Department) -> Department:
    try:
        return department_store.save_department(department)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _department_member_usernames(
    department_id: str,
    *,
    visible_usernames: set[str] | None = None,
) -> list[str]:
    usernames = [
        item.username
        for item in department_store.list_department_memberships(department_id)
        if bool(item.enabled)
    ]
    if visible_usernames is not None:
        usernames = [username for username in usernames if username in visible_usernames]
    return usernames


def _department_depths() -> dict[str, int]:
    departments = department_store.list_departments()
    by_id = {item.id: item for item in departments}
    depths: dict[str, int] = {}

    def depth_for(department_id: str, seen: set[str] | None = None) -> int:
        if department_id in depths:
            return depths[department_id]
        seen = seen or set()
        if department_id in seen:
            return 0
        seen.add(department_id)
        item = by_id.get(department_id)
        if item is None or not item.parent_id:
            depths[department_id] = 0
            return 0
        depths[department_id] = depth_for(item.parent_id, seen) + 1
        return depths[department_id]

    for department in departments:
        depth_for(department.id)
    return depths


def _serialize_department(
    department: Department,
    *,
    include_members: bool = True,
    visible_usernames: set[str] | None = None,
) -> dict[str, Any]:
    payload = asdict(department)
    usernames = _department_member_usernames(
        department.id,
        visible_usernames=visible_usernames,
    )
    payload["member_count"] = len(usernames)
    if include_members:
        payload["usernames"] = usernames
    return payload


def _serialize_user_department_payload(username: str) -> dict[str, Any]:
    memberships = department_store.list_user_memberships(username)
    departments = {item.id: item for item in department_store.list_departments()}
    return {
        "username": username,
        "department_ids": [item.department_id for item in memberships],
        "primary_department_id": next(
            (item.department_id for item in memberships if bool(item.is_primary)),
            memberships[0].department_id if memberships else "",
        ),
        "departments": [
            {
                **asdict(departments[item.department_id]),
                "is_primary": bool(item.is_primary),
            }
            for item in memberships
            if item.department_id in departments
        ],
    }


def _visible_departments(auth_payload: dict) -> list[Department]:
    department_ids = visible_department_ids_for(auth_payload)
    departments = department_store.list_departments()
    if department_ids is None:
        return departments
    return [item for item in departments if item.id in department_ids]


@router.get("/user-options")
async def list_department_user_options(auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.departments")
    visible_usernames = visible_usernames_for(auth_payload)
    roles = {item.id: item for item in role_store.list_all()}
    users = user_store.list_all()
    if visible_usernames is not None:
        users = [item for item in users if str(item.username or "").strip() in visible_usernames]
    return {
        "users": [
            {
                "username": item.username,
                "role": item.role,
                "role_name": getattr(roles.get(item.role), "name", item.role),
            }
            for item in users
            if str(item.username or "").strip()
        ]
    }


@router.get("")
async def list_departments(auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.departments")
    departments = _visible_departments(auth_payload)
    depths = _department_depths()
    visible_usernames = visible_usernames_for(auth_payload)
    serialized = []
    for item in departments:
        payload = _serialize_department(item, visible_usernames=visible_usernames)
        payload["depth"] = depths.get(item.id, 0)
        serialized.append(payload)
    return {
        "departments": serialized,
        "scope": data_scope_payload(auth_payload),
    }


@router.get("/tree")
async def get_department_tree(auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.departments")
    visible_usernames = visible_usernames_for(auth_payload)
    departments = [
        _serialize_department(item, visible_usernames=visible_usernames)
        for item in _visible_departments(auth_payload)
    ]
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for item in departments:
        item["children"] = []
        by_parent.setdefault(str(item.get("parent_id") or ""), []).append(item)

    def attach(parent_id: str) -> list[dict[str, Any]]:
        children = by_parent.get(parent_id, [])
        for child in children:
            child["children"] = attach(str(child.get("id") or ""))
        return children

    return {"tree": attach("")}


@router.get("/options")
async def list_department_options(auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.departments")
    departments = _visible_departments(auth_payload)
    depths = _department_depths()
    return {
        "departments": [
            {
                "id": item.id,
                "name": item.name,
                "parent_id": item.parent_id,
                "manager_username": item.manager_username,
                "enabled": item.enabled,
                "depth": depths.get(item.id, 0),
            }
            for item in departments
        ]
    }


@router.post("")
async def create_department(req: DepartmentCreateReq, auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "button.departments.create")
    manager_username = _normalize_username(req.manager_username)
    if manager_username:
        _ensure_user_exists(manager_username, field="manager_username")
    department = _save_department_or_400(
        Department(
            id=department_store.new_id(),
            name=req.name,
            parent_id=req.parent_id,
            manager_username=manager_username,
            description=req.description,
            enabled=bool(req.enabled),
            sort_order=int(req.sort_order or 100),
        )
    )
    if req.user_names:
        ensure_permission(auth_payload, "button.departments.assign_users")
        for username in req.user_names:
            _ensure_user_exists(username)
        department_store.set_department_members(department.id, req.user_names)
    return {"status": "created", "department": _serialize_department(department)}


@router.put("/{department_id}")
async def update_department(
    department_id: str,
    req: DepartmentUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "button.departments.update")
    existing = department_store.get_department(department_id)
    if existing is None:
        raise HTTPException(404, "Department not found")
    updates = req.model_dump(exclude_none=True)
    manager_username = updates.get("manager_username", existing.manager_username)
    manager_username = _normalize_username(str(manager_username or ""))
    if manager_username:
        _ensure_user_exists(manager_username, field="manager_username")
    department = _save_department_or_400(
        Department(
            id=existing.id,
            name=str(updates.get("name", existing.name) or "").strip(),
            parent_id=str(updates.get("parent_id", existing.parent_id) or "").strip(),
            manager_username=manager_username,
            description=str(updates.get("description", existing.description) or "").strip(),
            enabled=bool(updates.get("enabled", existing.enabled)),
            sort_order=int(updates.get("sort_order", existing.sort_order) or 100),
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )
    )
    if "user_names" in updates:
        ensure_permission(auth_payload, "button.departments.assign_users")
        usernames = updates.get("user_names") or []
        for username in usernames:
            _ensure_user_exists(username)
        department_store.set_department_members(department.id, usernames)
    return {"status": "updated", "department": _serialize_department(department)}


@router.delete("/{department_id}")
async def delete_department(department_id: str, auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "button.departments.delete")
    try:
        deleted = department_store.delete_department(department_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not deleted:
        raise HTTPException(404, "Department not found")
    return {"status": "deleted", "department_id": department_id}


@router.put("/{department_id}/users")
async def assign_department_users(
    department_id: str,
    req: DepartmentUserAssignReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "button.departments.assign_users")
    for username in req.usernames:
        _ensure_user_exists(username)
    try:
        memberships = department_store.set_department_members(department_id, req.usernames)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "status": "updated",
        "department_id": department_id,
        "memberships": [asdict(item) for item in memberships],
    }


@router.get("/users/{username}")
async def get_user_departments(username: str, auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.departments")
    normalized_username = _normalize_username(username)
    _ensure_user_exists(normalized_username)
    if not can_view_username_data(auth_payload, normalized_username):
        raise HTTPException(404, "User not found")
    return {"user": _serialize_user_department_payload(normalized_username)}


@router.put("/users/{username}")
async def assign_user_departments(
    username: str,
    req: UserDepartmentAssignReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "button.departments.assign_users")
    normalized_username = _normalize_username(username)
    _ensure_user_exists(normalized_username)
    try:
        memberships = department_store.set_user_memberships(
            normalized_username,
            req.department_ids,
            primary_department_id=req.primary_department_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "status": "updated",
        "user": _serialize_user_department_payload(normalized_username),
        "memberships": [asdict(item) for item in memberships],
    }
