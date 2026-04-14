"""公共依赖 — 认证、Store 实例"""

from __future__ import annotations

from fastapi import HTTPException, Header, Query

from core.auth import decode_token
from core.role_permissions import has_permission as role_has_permission, resolve_role_permissions
from stores.factory import (
    agent_template_store,
    changelog_entry_store,
    employee_store,
    external_mcp_store,
    local_connector_store,
    project_chat_store,
    project_chat_task_store,
    project_material_store,
    project_studio_export_store,
    project_store,
    role_store,
    system_config_store,
    task_tree_evolution_store,
    usage_store,
    user_store,
    work_session_store,
)


async def require_auth(
    authorization: str | None = Header(None),
    token: str | None = Query(None),
) -> dict:
    raw_token = ""
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:]
    elif token:
        raw_token = str(token).strip()
    if not raw_token:
        raise HTTPException(401, "Missing or invalid token")
    payload = decode_token(raw_token)
    if payload is None:
        raise HTTPException(401, "Token expired or invalid")
    return payload


def get_auth_role_ids(auth_payload: dict | None) -> list[str]:
    payload = auth_payload if isinstance(auth_payload, dict) else {}
    normalized: list[str] = []
    seen: set[str] = set()
    raw_roles = payload.get("roles")
    if isinstance(raw_roles, list):
        for item in raw_roles:
            role_id = str(item or "").strip().lower()
            if not role_id or role_id in seen:
                continue
            seen.add(role_id)
            normalized.append(role_id)
    role_id = str(payload.get("role") or "").strip().lower()
    if role_id and role_id not in seen:
        normalized.append(role_id)
    return normalized


def get_primary_role_id(auth_payload: dict | None) -> str:
    role_ids = get_auth_role_ids(auth_payload)
    return role_ids[0] if role_ids else ""


def resolve_role_ids_permissions(role_ids: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    normalized_role_ids = [
        str(item or "").strip().lower()
        for item in (role_ids or [])
        if str(item or "").strip()
    ]
    if not normalized_role_ids:
        return []
    resolved: set[str] = set()
    for role_id in normalized_role_ids:
        try:
            role = role_store.get(role_id)
        except ValueError:
            role = None
        role_permissions = getattr(role, "permissions", None)
        current_permissions = resolve_role_permissions(role_permissions, role_id)
        if "*" in set(current_permissions):
            return ["*"]
        resolved.update(current_permissions)
    return sorted(resolved)


def _resolve_role_permissions_from_payload(auth_payload: dict | None) -> tuple[list[str], list[str]]:
    role_ids = get_auth_role_ids(auth_payload)
    return role_ids, resolve_role_ids_permissions(role_ids)


def ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_ids, role_permissions = _resolve_role_permissions_from_payload(auth_payload)
    primary_role_id = role_ids[0] if role_ids else ""
    if not role_has_permission(role_permissions, permission_key, role_id=primary_role_id):
        raise HTTPException(403, f"Permission denied: {permission_key}")


def ensure_any_permission(auth_payload: dict, permission_keys: list[str]) -> None:
    role_ids, role_permissions = _resolve_role_permissions_from_payload(auth_payload)
    primary_role_id = role_ids[0] if role_ids else ""
    if any(role_has_permission(role_permissions, key, role_id=primary_role_id) for key in permission_keys):
        return
    raise HTTPException(403, f"Permission denied: {permission_keys}")


def is_admin_like(auth_payload: dict) -> bool:
    _, permissions = _resolve_role_permissions_from_payload(auth_payload)
    return "*" in set(permissions)
