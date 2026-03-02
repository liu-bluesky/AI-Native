"""初始化与认证路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import create_token
from deps import user_store
from user_store import User, hash_password, verify_password
from models.requests import InitSetupReq, LoginReq

router = APIRouter(prefix="/api")


@router.get("/init/status")
async def init_status():
    return {"initialized": user_store.has_any()}


@router.post("/init/setup")
async def init_setup(req: InitSetupReq):
    if user_store.has_any():
        raise HTTPException(400, "Already initialized")
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be >= 6 chars")
    user = User(username=req.username, password_hash=hash_password(req.password))
    user_store.save(user)
    return {"status": "ok", "username": req.username}


@router.post("/auth/login")
async def login(req: LoginReq):
    user = user_store.get(req.username)
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user.username, user.role)
    return {"token": token, "username": user.username, "role": user.role}
