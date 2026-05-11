"""Hierarchical department data-scope helpers."""

from __future__ import annotations

from typing import Any

from core.deps import department_store, is_admin_like
from core.ownership import current_username


def _normalize_username(value: Any) -> str:
    return str(value or "").strip()


def visible_usernames_for(auth_payload: dict | None) -> set[str] | None:
    """Return visible usernames, or None for unrestricted admins."""

    if isinstance(auth_payload, dict) and is_admin_like(auth_payload):
        return None
    username = current_username(auth_payload)
    if not username:
        return set()

    visible: set[str] = {username}
    managed_department_ids = department_store.list_managed_department_ids(username)
    scoped_department_ids: set[str] = set()
    for department_id in managed_department_ids:
        scoped_department_ids.update(
            department_store.list_descendant_department_ids(department_id, include_self=True)
        )
    if scoped_department_ids:
        visible.update(department_store.list_usernames_for_departments(sorted(scoped_department_ids)))
    return visible


def visible_department_ids_for(auth_payload: dict | None) -> set[str] | None:
    """Return visible department ids, or None for unrestricted admins."""

    if isinstance(auth_payload, dict) and is_admin_like(auth_payload):
        return None
    username = current_username(auth_payload)
    if not username:
        return set()

    visible: set[str] = {
        item.department_id for item in department_store.list_user_memberships(username)
    }
    for department_id in department_store.list_managed_department_ids(username):
        visible.update(
            department_store.list_descendant_department_ids(department_id, include_self=True)
        )
    return visible


def can_view_username_data(auth_payload: dict | None, owner_username: str) -> bool:
    target = _normalize_username(owner_username)
    if not target:
        return True
    visible = visible_usernames_for(auth_payload)
    if visible is None:
        return True
    return target in visible


def can_manage_username_data(auth_payload: dict | None, owner_username: str) -> bool:
    if isinstance(auth_payload, dict) and is_admin_like(auth_payload):
        return True
    return bool(current_username(auth_payload) and current_username(auth_payload) == owner_username)


def filter_records_by_data_scope(records: list[Any], auth_payload: dict | None) -> list[Any]:
    visible = visible_usernames_for(auth_payload)
    if visible is None:
        return records
    filtered: list[Any] = []
    for item in records:
        owner = _normalize_username(
            getattr(item, "username", "")
            or getattr(item, "created_by", "")
            or (item.get("username", "") if isinstance(item, dict) else "")
            or (item.get("created_by", "") if isinstance(item, dict) else "")
        )
        if not owner or owner in visible:
            filtered.append(item)
    return filtered


def data_scope_payload(auth_payload: dict | None) -> dict[str, Any]:
    username = current_username(auth_payload)
    visible = visible_usernames_for(auth_payload)
    visible_department_ids = visible_department_ids_for(auth_payload)
    memberships = department_store.list_user_memberships(username) if username else []
    managed_department_ids = department_store.list_managed_department_ids(username) if username else []
    scoped_department_ids: set[str] = set()
    for department_id in managed_department_ids:
        scoped_department_ids.update(
            department_store.list_descendant_department_ids(department_id, include_self=True)
        )
    return {
        "username": username,
        "unrestricted": visible is None,
        "visible_usernames": sorted(visible) if visible is not None else [],
        "visible_department_ids": (
            sorted(visible_department_ids) if visible_department_ids is not None else []
        ),
        "department_ids": [item.department_id for item in memberships],
        "primary_department_id": next(
            (item.department_id for item in memberships if bool(item.is_primary)),
            memberships[0].department_id if memberships else "",
        ),
        "managed_department_ids": managed_department_ids,
        "scoped_department_ids": sorted(scoped_department_ids),
    }
