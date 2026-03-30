"""系统登录用户管理路由"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from core.deps import ensure_any_permission, is_admin_like, project_store, require_auth, role_store, user_store
from models.requests import UserCreateReq, UserPasswordUpdateReq, UserSettingsUpdateReq, UserUpdateReq
from core.role_permissions import has_permission
from services.llm_provider_service import get_llm_provider_service
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


def _current_username(auth_payload: dict) -> str:
    return _sanitize_username(str(auth_payload.get("sub") or ""))


def _ensure_self_or_permission(auth_payload: dict, target_username: str, permission_key: str) -> None:
    if _current_username(auth_payload) == target_username:
        return
    _ensure_permission(auth_payload, permission_key)


def _sanitize_password(value: str) -> str:
    password = str(value or "")
    if len(password) < 6:
        raise HTTPException(400, "Password must be >= 6 chars")
    return password


def _sanitize_role(value: str) -> tuple[str, object]:
    role = str(value or "user").strip().lower()
    role_item = role_store.get(role)
    if role_item is None:
        raise HTTPException(400, f"Role not found: {role}")
    return role, role_item


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
            "created_by": str(getattr(user, "created_by", "") or "").strip(),
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


@router.get("/share-options")
async def list_user_share_options(auth_payload: dict = Depends(require_auth)):
    ensure_any_permission(
        auth_payload,
        ["menu.users", "menu.employees", "menu.rules", "menu.skills", "menu.llm.providers"],
    )
    current_username = _sanitize_username(str(auth_payload.get("sub") or ""))
    users = [
        {
            "username": user.username,
            "role": user.role,
            "created_at": user.created_at,
        }
        for user in user_store.list_all()
        if str(user.username or "").strip() and str(user.username or "").strip() != current_username
    ]
    return {"users": users}


@router.get("/me/settings")
async def get_current_user_settings(auth_payload: dict = Depends(require_auth)):
    username = _sanitize_username(str(auth_payload.get("sub") or ""))
    user = user_store.get(username)
    if user is None:
        raise HTTPException(404, "User not found")
    providers = get_llm_provider_service().list_providers(
        enabled_only=True,
        owner_username=username,
        include_all=is_admin_like(auth_payload),
        include_shared=True,
    )
    return {
        "settings": {
            "username": user.username,
            "role": user.role,
            "default_ai_provider_id": str(user.default_ai_provider_id or "").strip(),
            "created_at": user.created_at,
        },
        "providers": providers,
    }


@router.put("/me/settings")
async def update_current_user_settings(
    req: UserSettingsUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    username = _sanitize_username(str(auth_payload.get("sub") or ""))
    user = user_store.get(username)
    if user is None:
        raise HTTPException(404, "User not found")
    provider_id = str(req.default_ai_provider_id or "").strip()
    if provider_id:
        providers = get_llm_provider_service().list_providers(
            enabled_only=True,
            owner_username=username,
            include_all=is_admin_like(auth_payload),
            include_shared=True,
        )
        if not any(str(item.get("id") or "").strip() == provider_id for item in providers):
            raise HTTPException(400, "default_ai_provider_id is invalid or not accessible")
    updated = User(
        username=user.username,
        password_hash=user.password_hash,
        role=user.role,
        default_ai_provider_id=provider_id,
        created_by=user.created_by,
        created_at=user.created_at,
    )
    user_store.save(updated)
    return {
        "status": "updated",
        "settings": {
            "username": updated.username,
            "role": updated.role,
            "default_ai_provider_id": updated.default_ai_provider_id,
            "created_at": updated.created_at,
        },
    }


@router.post("")
async def create_user(req: UserCreateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "button.users.create")
    username = _sanitize_username(req.username)
    password = _sanitize_password(req.password)
    role, role_item = _sanitize_role(req.role)
    if user_store.get(username) is not None:
        raise HTTPException(409, "Username already exists")
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        created_by=str(auth_payload.get("sub") or "").strip(),
    )
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


@router.put("/{username}")
async def update_user(username: str, req: UserUpdateReq, auth_payload: dict = Depends(require_auth)):
    normalized_username = _sanitize_username(username)
    current_username = _current_username(auth_payload)
    _ensure_self_or_permission(auth_payload, normalized_username, "button.users.update")
    existing = user_store.get(normalized_username)
    if existing is None:
        raise HTTPException(404, "User not found")
    requested_role = str(req.role or "").strip().lower()
    if normalized_username == current_username:
        if requested_role and requested_role != existing.role:
            raise HTTPException(400, "Cannot change current login user role")
        role, role_item = _sanitize_role(existing.role)
    else:
        role, role_item = _sanitize_role(req.role)
    password_hash = existing.password_hash
    next_password = str(req.password or "")
    if next_password.strip():
        password_hash = hash_password(_sanitize_password(next_password))
    updated = User(
        username=existing.username,
        password_hash=password_hash,
        role=role,
        default_ai_provider_id=existing.default_ai_provider_id,
        created_by=existing.created_by,
        created_at=existing.created_at,
    )
    user_store.save(updated)
    return {
        "status": "updated",
        "user": {
            "username": updated.username,
            "role": updated.role,
            "role_name": role_item.name,
            "created_by": str(updated.created_by or "").strip(),
            "created_at": updated.created_at,
        },
    }


@router.put("/{username}/password")
async def update_password(username: str, req: UserPasswordUpdateReq, auth_payload: dict = Depends(require_auth)):
    normalized_username = _sanitize_username(username)
    password = _sanitize_password(req.password)
    _ensure_self_or_permission(auth_payload, normalized_username, "button.users.update_password")
    existing = user_store.get(normalized_username)
    if existing is None:
        raise HTTPException(404, "User not found")
    updated = User(
        username=existing.username,
        password_hash=hash_password(password),
        role=existing.role,
        default_ai_provider_id=existing.default_ai_provider_id,
        created_by=existing.created_by,
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
