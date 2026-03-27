"""Ownership and sharing helpers for user-created records."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from core.deps import is_admin_like

VALID_SHARE_SCOPES = {"private", "selected_users", "all_users"}


def current_username(auth_payload: dict | None) -> str:
    payload = auth_payload if isinstance(auth_payload, dict) else {}
    return str(payload.get("sub") or "").strip()


def created_by_username(item: Any) -> str:
    return str(getattr(item, "created_by", "") or "").strip()


def normalize_share_scope(value: Any) -> str:
    scope = str(value or "").strip().lower()
    if scope in VALID_SHARE_SCOPES:
        return scope
    return "private"


def normalize_shared_usernames(value: Any, *, owner_username: str = "") -> list[str]:
    owner = str(owner_username or "").strip()
    raw_items = value if isinstance(value, list) else []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        username = str(item or "").strip()
        if not username or username == owner or username in seen:
            continue
        seen.add(username)
        normalized.append(username)
    return normalized


def share_scope(item: Any) -> str:
    return normalize_share_scope(getattr(item, "share_scope", "private"))


def shared_usernames(item: Any) -> list[str]:
    return normalize_shared_usernames(
        getattr(item, "shared_with_usernames", []),
        owner_username=created_by_username(item),
    )


def can_view_record(item: Any, auth_payload: dict | None) -> bool:
    if isinstance(auth_payload, dict) and is_admin_like(auth_payload):
        return True
    created_by = created_by_username(item)
    if not created_by:
        return True
    username = current_username(auth_payload)
    if not username:
        return False
    if username == created_by:
        return True
    scope = share_scope(item)
    if scope == "all_users":
        return True
    if scope == "selected_users" and username in shared_usernames(item):
        return True
    return False


def can_manage_record(item: Any, auth_payload: dict | None) -> bool:
    if isinstance(auth_payload, dict) and is_admin_like(auth_payload):
        return True
    username = current_username(auth_payload)
    created_by = created_by_username(item)
    return bool(username and created_by and username == created_by)


def ownership_payload(item: Any, auth_payload: dict | None) -> dict[str, Any]:
    created_by = created_by_username(item)
    username = current_username(auth_payload)
    is_owner = bool(username and created_by and username == created_by)
    scope = share_scope(item)
    shared_with = shared_usernames(item)
    can_manage = can_manage_record(item, auth_payload)
    return {
        "created_by": created_by,
        "is_owner": is_owner,
        "can_manage": can_manage,
        "share_scope": scope,
        "shared_with_usernames": shared_with,
        "shared_with_all": scope == "all_users",
        "shared_with_current_user": bool(
            can_view_record(item, auth_payload) and not is_owner and created_by
        ),
        "is_shared": (not created_by) or scope != "private" or bool(shared_with),
    }


def assert_can_view_record(item: Any, auth_payload: dict | None, resource_label: str) -> None:
    if can_view_record(item, auth_payload):
        return
    raise HTTPException(404, f"{resource_label} not found")


def assert_can_manage_record(item: Any, auth_payload: dict | None, resource_label: str) -> None:
    if can_manage_record(item, auth_payload):
        return
    created_by = created_by_username(item)
    if not created_by:
        raise HTTPException(403, f"{resource_label} 为共享数据，仅可使用，不能编辑或删除")
    raise HTTPException(403, f"{resource_label} 不是你创建的，仅可使用，不能编辑或删除")
