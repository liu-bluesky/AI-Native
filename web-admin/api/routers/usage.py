"""使用统计路由"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from deps import require_auth, usage_store
from models.requests import CreateApiKeyReq

router = APIRouter(prefix="/api/usage", dependencies=[Depends(require_auth)])


@router.post("/keys")
async def create_key(req: CreateApiKeyReq):
    return usage_store.create_key(req.developer_name, req.created_by)


@router.get("/keys")
async def list_keys():
    return {"keys": usage_store.list_keys()}


@router.delete("/keys/{key}")
async def deactivate_key(key: str):
    if not usage_store.deactivate_key(key):
        raise HTTPException(404, "Key not found")
    return {"ok": True}


@router.get("/employees/{employee_id}/stats")
async def employee_stats(employee_id: str, days: int = 7):
    return usage_store.get_stats(employee_id, days)
