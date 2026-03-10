"""使用统计路由"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from core.deps import require_auth, role_store, usage_store
from models.requests import CreateApiKeyReq
from core.role_permissions import has_permission

router = APIRouter(prefix="/api/usage", dependencies=[Depends(require_auth)])


def _ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    role_permissions = getattr(role, "permissions", [])
    if not has_permission(role_permissions, permission_key):
        raise HTTPException(403, f"Permission denied: {permission_key}")


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
    return {"keys": usage_store.list_keys()}


@router.delete("/keys/{key}")
async def deactivate_key(key: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "button.apikey.deactivate")
    if not usage_store.deactivate_key(key):
        raise HTTPException(404, "Key not found")
    return {"ok": True}


@router.get("/employees/{employee_id}/stats")
async def employee_stats(employee_id: str, days: int = 7):
    return usage_store.get_stats(employee_id, days)
