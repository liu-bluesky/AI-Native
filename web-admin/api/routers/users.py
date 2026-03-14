"""系统登录用户管理路由"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from core.deps import project_store, require_auth, role_store, user_store
from models.requests import UserCreateReq, UserPasswordUpdateReq
from core.role_permissions import has_permission
from stores.json.user_store import User, hash_password

router = APIRouter(prefix="/api/users", dependencies=[Depends(require_auth)])


def _sanitize_username(value: str) -> str:
    username = str(value or "").strip()
    if not username:
        raise HTTPException(400, "Username is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}", username):
        raise HTTPException(400, "Invalid username format")
    return username


def _ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    role_permissions = getattr(role, "permissions", None)
    if not has_permission(role_permissions, permission_key, role_id=role_id):
        raise HTTPException(403, f"Permission denied: {permission_key}")


@router.get("")
async def list_users(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.users")
    roles = {item.id: item for item in role_store.list_all()}
    users = user_store.list_all()
    result = [
        {
            "username": user.username,
            "role": user.role,
            "role_name": getattr(roles.get(user.role), "name", user.role),
            "created_at": user.created_at,
        }
        for user in users
    ]
    return {"users": result}


@router.get("/role-options")
async def list_user_role_options(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.users")
    roles = role_store.list_all()
    return {
        "roles": [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
            }
            for item in roles
        ]
    }


@router.post("")
async def create_user(req: UserCreateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "button.users.create")
    username = _sanitize_username(req.username)
    if len(req.password or "") < 6:
        raise HTTPException(400, "Password must be >= 6 chars")
    role = str(req.role or "user").strip().lower()
    role_item = role_store.get(role)
    if role_item is None:
        raise HTTPException(400, f"Role not found: {role}")
    if user_store.get(username) is not None:
        raise HTTPException(409, "Username already exists")
    user = User(username=username, password_hash=hash_password(req.password), role=role)
    user_store.save(user)
    return {
        "status": "created",
        "user": {
            "username": user.username,
            "role": user.role,
            "role_name": role_item.name,
            "created_at": user.created_at,
        },
    }


@router.put("/{username}/password")
async def update_password(username: str, req: UserPasswordUpdateReq, auth_payload: dict = Depends(require_auth)):
    normalized_username = _sanitize_username(username)
    if len(req.password or "") < 6:
        raise HTTPException(400, "Password must be >= 6 chars")
    current_username = _sanitize_username(str(auth_payload.get("sub") or ""))
    if current_username != normalized_username:
        _ensure_permission(auth_payload, "button.users.update_password")
    existing = user_store.get(normalized_username)
    if existing is None:
        raise HTTPException(404, "User not found")
    updated = User(
        username=existing.username,
        password_hash=hash_password(req.password),
        role=existing.role,
        created_at=existing.created_at,
    )
    user_store.save(updated)
    return {"status": "updated", "username": updated.username}


@router.delete("/{username}")
async def delete_user(username: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "button.users.delete")
    normalized_username = _sanitize_username(username)
    current_username = _sanitize_username(str(auth_payload.get("sub") or ""))
    if normalized_username == current_username:
        raise HTTPException(400, "Cannot delete current login user")
    target = user_store.get(normalized_username)
    if target is None:
        raise HTTPException(404, "User not found")
    if str(target.role or "").strip().lower() == "admin":
        admin_count = sum(
            1
            for user in user_store.list_all()
            if str(user.role or "").strip().lower() == "admin"
        )
        if admin_count <= 1:
            raise HTTPException(400, "Cannot delete the last admin")
    if not user_store.delete(normalized_username):
        raise HTTPException(404, "User not found")
    try:
        project_store.remove_user_from_all_projects(normalized_username)
    except Exception:
        pass
    return {"status": "deleted", "username": normalized_username}
