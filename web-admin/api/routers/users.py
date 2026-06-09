"""系统登录用户管理路由"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from core.data_scope import can_view_username_data, data_scope_payload, filter_records_by_data_scope
from core.deps import department_store, ensure_any_permission, ensure_permission, is_admin_like, project_store, require_auth, role_store, user_store
from models.requests import UserCreateReq, UserPasswordUpdateReq, UserSettingsUpdateReq, UserUpdateReq
from services.providers.llm_provider_service import get_llm_provider_service
from stores.json.user_store import User, hash_password

router = APIRouter(prefix="/api/users", dependencies=[Depends(require_auth)])

_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}")
_EMAIL_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _sanitize_username(value: str) -> str:
    username = str(value or "").strip()
    if not username:
        raise HTTPException(400, "Username is required")
    if not (
        _USERNAME_PATTERN.fullmatch(username)
        or _EMAIL_USERNAME_PATTERN.fullmatch(username)
    ):
        raise HTTPException(400, "Invalid username format")
    return username


def _ensure_permission(auth_payload: dict, permission_key: str) -> None:
    ensure_permission(auth_payload, permission_key)


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


def _sanitize_display_name(value: str | None) -> str:
    display_name = str(value or "").strip()
    if len(display_name) > 64:
        raise HTTPException(400, "Display name must be <= 64 chars")
    return display_name


def _sanitize_role(value: str) -> tuple[str, object]:
    role = str(value or "user").strip().lower()
    role_item = role_store.get(role)
    if role_item is None:
        raise HTTPException(400, f"Role not found: {role}")
    return role, role_item


def _sanitize_role_ids(values: list[str] | None, *, fallback_role: str = "user") -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        role_id = str(item or "").strip().lower()
        if not role_id or role_id in seen:
            continue
        if role_store.get(role_id) is None:
            raise HTTPException(400, f"Role not found: {role_id}")
        seen.add(role_id)
        normalized.append(role_id)
    if normalized:
        return normalized
    role, _ = _sanitize_role(fallback_role)
    return [role]


def _role_names_payload(role_ids: list[str], roles: dict[str, object]) -> list[str]:
    return [str(getattr(roles.get(role_id), "name", role_id) or role_id) for role_id in role_ids]


def _existing_user_role_ids(user: User) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    raw_role_ids = list(getattr(user, "role_ids", []) or [])
    for item in [*raw_role_ids, user.role]:
        role_id = str(item or "").strip().lower()
        if not role_id or role_id in seen:
            continue
        seen.add(role_id)
        normalized.append(role_id)
    return normalized or ["user"]


def _user_role_payload(user: User, roles: dict[str, object] | None = None) -> dict:
    known_roles = roles if roles is not None else {item.id: item for item in role_store.list_all()}
    role_ids = _existing_user_role_ids(user)
    role_names = _role_names_payload(role_ids, known_roles)
    return {
        "role": role_ids[0],
        "role_name": role_names[0] if role_names else role_ids[0],
        "role_ids": role_ids,
        "role_names": role_names,
        "roles": [
            {
                "id": role_id,
                "name": role_name,
            }
            for role_id, role_name in zip(role_ids, role_names)
        ],
    }


def _user_department_payload(username: str) -> dict:
    memberships = department_store.list_user_memberships(username)
    departments = {item.id: item for item in department_store.list_departments()}
    return {
        "department_ids": [item.department_id for item in memberships],
        "primary_department_id": next(
            (item.department_id for item in memberships if bool(item.is_primary)),
            memberships[0].department_id if memberships else "",
        ),
        "departments": [
            {
                "id": item.department_id,
                "name": getattr(departments.get(item.department_id), "name", item.department_id),
                "is_primary": bool(item.is_primary),
            }
            for item in memberships
        ],
    }


@router.get("")
async def list_users(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.users")
    roles = {item.id: item for item in role_store.list_all()}
    users = filter_records_by_data_scope(user_store.list_all(), auth_payload)
    result = [
        {
            "username": user.username,
            "display_name": str(user.display_name or "").strip(),
            **_user_role_payload(user, roles),
            "created_by": str(getattr(user, "created_by", "") or "").strip(),
            "created_at": user.created_at,
            **_user_department_payload(user.username),
        }
        for user in users
    ]
    return {"users": result, "scope": data_scope_payload(auth_payload)}


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
            "display_name": str(user.display_name or "").strip(),
            **_user_role_payload(user),
            "created_at": user.created_at,
            **_user_department_payload(user.username),
        }
        for user in filter_records_by_data_scope(user_store.list_all(), auth_payload)
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
            "display_name": str(user.display_name or "").strip(),
            **_user_role_payload(user),
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
        display_name=user.display_name,
        role=user.role,
        role_ids=user.role_ids,
        default_ai_provider_id=provider_id,
        created_by=user.created_by,
        created_at=user.created_at,
    )
    user_store.save(updated)
    return {
        "status": "updated",
        "settings": {
            "username": updated.username,
            "display_name": str(updated.display_name or "").strip(),
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
    role_ids = _sanitize_role_ids(req.role_ids, fallback_role=req.role)
    role, _ = _sanitize_role(role_ids[0])
    if user_store.get(username) is not None:
        raise HTTPException(409, "Username already exists")
    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=_sanitize_display_name(req.display_name),
        role=role,
        role_ids=role_ids,
        created_by=str(auth_payload.get("sub") or "").strip(),
    )
    user_store.save(user)
    if req.department_ids:
        _ensure_permission(auth_payload, "button.departments.assign_users")
        department_store.set_user_memberships(
            username,
            req.department_ids,
            primary_department_id=req.primary_department_id,
        )
    return {
        "status": "created",
        "user": {
            "username": user.username,
            "display_name": str(user.display_name or "").strip(),
            **_user_role_payload(user),
            "created_at": user.created_at,
            **_user_department_payload(user.username),
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
    if not can_view_username_data(auth_payload, normalized_username):
        raise HTTPException(404, "User not found")
    requested_role = str(req.role or "").strip().lower()
    if normalized_username == current_username:
        requested_role_ids = _sanitize_role_ids(req.role_ids, fallback_role=existing.role) if req.role_ids else []
        if requested_role and requested_role != existing.role:
            raise HTTPException(400, "Cannot change current login user role")
        if requested_role_ids and requested_role_ids != list(existing.role_ids or [existing.role]):
            raise HTTPException(400, "Cannot change current login user role")
        role, _ = _sanitize_role(existing.role)
        role_ids = list(existing.role_ids or [role])
    else:
        role_ids = _sanitize_role_ids(req.role_ids, fallback_role=req.role or existing.role)
        role, _ = _sanitize_role(role_ids[0])
    password_hash = existing.password_hash
    next_password = str(req.password or "")
    if next_password.strip():
        password_hash = hash_password(_sanitize_password(next_password))
    updated = User(
        username=existing.username,
        password_hash=password_hash,
        display_name=(
            _sanitize_display_name(req.display_name)
            if req.display_name is not None
            else existing.display_name
        ),
        role=role,
        role_ids=role_ids,
        default_ai_provider_id=existing.default_ai_provider_id,
        created_by=existing.created_by,
        created_at=existing.created_at,
    )
    user_store.save(updated)
    if req.department_ids is not None:
        _ensure_permission(auth_payload, "button.departments.assign_users")
        department_store.set_user_memberships(
            updated.username,
            req.department_ids,
            primary_department_id=req.primary_department_id,
        )
    return {
        "status": "updated",
        "user": {
            "username": updated.username,
            "display_name": str(updated.display_name or "").strip(),
            **_user_role_payload(updated),
            "created_by": str(updated.created_by or "").strip(),
            "created_at": updated.created_at,
            **_user_department_payload(updated.username),
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
    if not can_view_username_data(auth_payload, normalized_username):
        raise HTTPException(404, "User not found")
    updated = User(
        username=existing.username,
        password_hash=hash_password(password),
        display_name=existing.display_name,
        role=existing.role,
        role_ids=existing.role_ids,
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
    if not can_view_username_data(auth_payload, normalized_username):
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
    try:
        department_store.remove_user_from_all_departments(normalized_username)
    except Exception:
        pass
    return {"status": "deleted", "username": normalized_username}
