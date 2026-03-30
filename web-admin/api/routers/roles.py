"""角色管理路由"""

from __future__ import annotations

import re
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from core.deps import require_auth, role_store, user_store
from models.requests import RoleCreateReq, RoleUpdateReq
from core.role_permissions import has_permission, permission_catalog, resolve_role_permissions
from stores.json.role_store import RoleConfig

router = APIRouter(prefix="/api/roles", dependencies=[Depends(require_auth)])


def _normalize_role_id(raw: str) -> str:
    role_id = str(raw or "").strip().lower()
    if not role_id:
        raise HTTPException(400, "Role id is required")
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,31}", role_id):
        raise HTTPException(400, "Invalid role id format")
    return role_id


def _ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    role_permissions = getattr(role, "permissions", None)
    if not has_permission(role_permissions, permission_key, role_id=role_id):
        raise HTTPException(403, f"Permission denied: {permission_key}")


@router.get("")
async def list_roles(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.roles")
    roles = role_store.list_all()
    return {"roles": [asdict(item) for item in roles]}


@router.get("/catalog")
async def get_role_catalog(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.roles")
    return permission_catalog()


@router.get("/{role_id}")
async def get_role(role_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.roles")
    normalized_role_id = _normalize_role_id(role_id)
    role = role_store.get(normalized_role_id)
    if role is None:
        raise HTTPException(404, "Role not found")
    return {"role": asdict(role)}


@router.post("")
async def create_role(req: RoleCreateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "button.roles.create")
    role_id = _normalize_role_id(req.id)
    if role_store.get(role_id) is not None:
        raise HTTPException(409, "Role already exists")
    name = str(req.name or "").strip()
    if not name:
        raise HTTPException(400, "Role name is required")
    role = RoleConfig(
        id=role_id,
        name=name,
        description=str(req.description or "").strip(),
        permissions=resolve_role_permissions(req.permissions, role_id),
        built_in=False,
        created_by=str(auth_payload.get("sub") or "").strip(),
    )
    role_store.save(role)
    return {"status": "created", "role": asdict(role_store.get(role_id))}


@router.put("/{role_id}")
async def update_role(role_id: str, req: RoleUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "button.roles.update")
    normalized_role_id = _normalize_role_id(role_id)
    existing = role_store.get(normalized_role_id)
    if existing is None:
        raise HTTPException(404, "Role not found")
    payload = asdict(existing)
    updates = req.model_dump(exclude_none=True)
    if "name" in updates:
        name = str(updates.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "Role name is required")
        payload["name"] = name
    if "description" in updates:
        payload["description"] = str(updates.get("description") or "").strip()
    if "permissions" in updates:
        payload["permissions"] = resolve_role_permissions(
            updates.get("permissions"),
            normalized_role_id,
        )
    role_store.save(RoleConfig(**payload))
    return {"status": "updated", "role": asdict(role_store.get(normalized_role_id))}


@router.delete("/{role_id}")
async def delete_role(role_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "button.roles.delete")
    normalized_role_id = _normalize_role_id(role_id)
    role = role_store.get(normalized_role_id)
    if role is None:
        raise HTTPException(404, "Role not found")
    if bool(role.built_in):
        raise HTTPException(400, "Built-in role cannot be deleted")
    user_count = sum(
        1 for item in user_store.list_all() if str(item.role or "").strip().lower() == normalized_role_id
    )
    if user_count > 0:
        raise HTTPException(400, f"Role is used by {user_count} users")
    if not role_store.delete(normalized_role_id):
        raise HTTPException(404, "Role not found")
    return {"status": "deleted", "role_id": normalized_role_id}
