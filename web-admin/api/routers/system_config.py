"""系统配置路由"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from core.deps import require_auth, system_config_store
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
        "enable_user_register",
        "chat_upload_max_limit",
        "chat_max_tokens",
    }
    invalid = [key for key in updates.keys() if key not in allowed]
    if invalid:
        raise HTTPException(400, f"Invalid system config keys: {invalid}")

    if "chat_upload_max_limit" in updates:
        try:
            value = int(updates["chat_upload_max_limit"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "chat_upload_max_limit must be an integer") from exc
        if value < 1 or value > 20:
            raise HTTPException(400, "chat_upload_max_limit must be between 1 and 20")
        updates["chat_upload_max_limit"] = value

    if "chat_max_tokens" in updates:
        try:
            value = int(updates["chat_max_tokens"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "chat_max_tokens must be an integer") from exc
        if value < 128 or value > 8192:
            raise HTTPException(400, "chat_max_tokens must be between 128 and 8192")
        updates["chat_max_tokens"] = value

    updated = system_config_store.patch_global(updates)
    return {"status": "updated", "config": asdict(updated)}
