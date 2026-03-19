"""Ownership helpers for user-created records."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from core.deps import is_admin_like


def current_username(auth_payload: dict | None) -> str:
    return str((auth_payload or {}).get("sub") or "").strip()


def created_by_username(item: Any) -> str:
    return str(getattr(item, "created_by", "") or "").strip()


def can_manage_record(item: Any, auth_payload: dict | None) -> bool:
    if is_admin_like(auth_payload or {}):
        return True
    username = current_username(auth_payload)
    created_by = created_by_username(item)
    return bool(username and created_by and username == created_by)


def ownership_payload(item: Any, auth_payload: dict | None) -> dict[str, Any]:
    created_by = created_by_username(item)
    username = current_username(auth_payload)
    is_owner = bool(username and created_by and username == created_by)
    can_manage = can_manage_record(item, auth_payload)
    return {
        "created_by": created_by,
        "is_owner": is_owner,
        "can_manage": can_manage,
        "is_shared": not created_by,
    }


def assert_can_manage_record(item: Any, auth_payload: dict | None, resource_label: str) -> None:
    if can_manage_record(item, auth_payload):
        return
    created_by = created_by_username(item)
    if not created_by:
        raise HTTPException(403, f"{resource_label} 为共享数据，仅可使用，不能编辑或删除")
    raise HTTPException(403, f"{resource_label} 不是你创建的，仅可使用，不能编辑或删除")
