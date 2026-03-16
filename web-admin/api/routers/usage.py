"""使用统计路由"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from core.deps import require_auth, role_store, usage_store
from models.requests import CreateApiKeyReq
from core.role_permissions import has_permission

router = APIRouter(prefix="/api/usage", dependencies=[Depends(require_auth)])
_LEGACY_DELETABLE_KEY_OWNERS = {"", "unknown", "system-external-agent"}


def _ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    role_permissions = getattr(role, "permissions", None)
    if not has_permission(role_permissions, permission_key, role_id=role_id):
        raise HTTPException(403, f"Permission denied: {permission_key}")


def _current_username(auth_payload: dict) -> str:
    return str(auth_payload.get("sub") or "").strip()


def _can_delete_key_record(record: dict | None, owner: str) -> bool:
    if not record:
        return False
    record_owner = str(record.get("created_by") or "").strip()
    if owner and record_owner == owner:
        return True
    return record_owner in _LEGACY_DELETABLE_KEY_OWNERS


@router.post("/keys")
async def create_key(req: CreateApiKeyReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "button.apikey.create")
    developer_name = str(req.developer_name or "").strip()
    if not developer_name:
        raise HTTPException(400, "developer_name is required")
    created_by = str(auth_payload.get("sub") or "").strip() or "unknown"
    return usage_store.create_key(developer_name, created_by)


@router.get("/keys")
async def list_keys(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.usage.keys")
    return {"keys": usage_store.list_keys(created_by=_current_username(auth_payload))}


@router.delete("/keys/{key}")
async def delete_key(key: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "button.apikey.deactivate")
    owner = _current_username(auth_payload)
    if usage_store.delete_key(key, created_by=owner):
        return {"ok": True}
    record = usage_store.get_key(key)
    if not _can_delete_key_record(record, owner):
        raise HTTPException(404, "Key not found")
    if not usage_store.delete_key(key):
        raise HTTPException(404, "Key not found")
    return {"ok": True}


@router.get("/employees/{employee_id}/stats")
async def employee_stats(employee_id: str, days: int = 7):
    return usage_store.get_stats(employee_id, days)
