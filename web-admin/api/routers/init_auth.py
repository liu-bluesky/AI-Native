"""初始化与认证路由"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from core.auth import create_token
from core.deps import require_auth, role_store, system_config_store, user_store
from core.role_permissions import resolve_role_permissions
from stores.json.user_store import User, hash_password, verify_password
from models.requests import InitSetupReq, LoginReq, RegisterReq

router = APIRouter(prefix="/api")


def _sanitize_username(username: str) -> str:
    value = str(username or "").strip()
    if not value:
        raise HTTPException(400, "Username is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}", value):
        raise HTTPException(400, "Invalid username format")
    return value


def _load_permissions(role_id: str) -> list[str]:
    role = role_store.get(role_id)
    role_permissions = getattr(role, "permissions", [])
    return resolve_role_permissions(role_permissions, role_id)


@router.get("/init/status")
async def init_status():
    cfg = system_config_store.get_global()
    return {
        "initialized": user_store.has_any(),
        "enable_user_register": bool(getattr(cfg, "enable_user_register", True)),
    }


@router.post("/init/setup")
async def init_setup(req: InitSetupReq):
    if user_store.has_any():
        raise HTTPException(400, "Already initialized")
    username = _sanitize_username(req.username)
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be >= 6 chars")
    user = User(username=username, password_hash=hash_password(req.password))
    user_store.save(user)
    return {"status": "ok", "username": username}


@router.post("/auth/login")
async def login(req: LoginReq):
    username = _sanitize_username(req.username)
    user = user_store.get(username)
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user.username, user.role)
    permissions = _load_permissions(user.role)
    return {
        "token": token,
        "username": user.username,
        "role": user.role,
        "permissions": permissions,
    }


@router.get("/auth/me")
async def auth_me(auth_payload: dict = Depends(require_auth)):
    username = _sanitize_username(str(auth_payload.get("sub") or ""))
    user = user_store.get(username)
    if user is None:
        raise HTTPException(404, "User not found")
    permissions = _load_permissions(user.role)
    return {
        "username": user.username,
        "role": user.role,
        "default_ai_provider_id": str(user.default_ai_provider_id or "").strip(),
        "permissions": permissions,
    }


@router.post("/auth/register")
async def register(req: RegisterReq):
    if not user_store.has_any():
        raise HTTPException(400, "System not initialized")
    cfg = system_config_store.get_global()
    if not bool(getattr(cfg, "enable_user_register", True)):
        raise HTTPException(403, "User registration is disabled")
    username = _sanitize_username(req.username)
    if len(req.password or "") < 6:
        raise HTTPException(400, "Password must be >= 6 chars")
    if user_store.get(username) is not None:
        raise HTTPException(409, "Username already exists")
    role_item = role_store.get("user")
    if role_item is None:
        raise HTTPException(500, "Role user not initialized")
    user = User(username=username, password_hash=hash_password(req.password), role=role_item.id)
    user_store.save(user)
    return {"status": "ok", "username": user.username, "role": user.role}
