"""系统配置路由"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from deps import require_auth, system_config_store
from models.requests import SystemConfigUpdateReq

router = APIRouter(prefix="/api/system-config", dependencies=[Depends(require_auth)])


@router.get("")
async def get_system_config():
    cfg = system_config_store.get_global()
    return {"config": asdict(cfg)}


@router.patch("")
async def patch_system_config(req: SystemConfigUpdateReq):
    updates = req.model_dump(exclude_none=True)
    if not updates:
        cfg = system_config_store.get_global()
        return {"status": "no_change", "config": asdict(cfg)}

    allowed = {
        "enable_project_manual_generation",
        "enable_employee_manual_generation",
    }
    invalid = [key for key in updates.keys() if key not in allowed]
    if invalid:
        raise HTTPException(400, f"Invalid system config keys: {invalid}")

    updated = system_config_store.patch_global(updates)
    return {"status": "updated", "config": asdict(updated)}
