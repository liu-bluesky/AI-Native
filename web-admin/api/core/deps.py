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
    project_material_store,
    project_studio_export_store,
    project_store,
    role_store,
    system_config_store,
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


def _resolve_role_permissions_from_payload(auth_payload: dict | None) -> tuple[str, list[str] | None]:
    payload = auth_payload if isinstance(auth_payload, dict) else {}
    role_id = str(payload.get("role") or "").strip().lower()
    if not role_id:
        return "", None
    try:
        role = role_store.get(role_id)
    except ValueError:
        return role_id, None
    return role_id, getattr(role, "permissions", None)


def ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_id, role_permissions = _resolve_role_permissions_from_payload(auth_payload)
    if not role_has_permission(role_permissions, permission_key, role_id=role_id):
        raise HTTPException(403, f"Permission denied: {permission_key}")


def ensure_any_permission(auth_payload: dict, permission_keys: list[str]) -> None:
    role_id, role_permissions = _resolve_role_permissions_from_payload(auth_payload)
    if any(role_has_permission(role_permissions, key, role_id=role_id) for key in permission_keys):
        return
    raise HTTPException(403, f"Permission denied: {permission_keys}")


def is_admin_like(auth_payload: dict) -> bool:
    role_id, permissions = _resolve_role_permissions_from_payload(auth_payload)
    resolved = resolve_role_permissions(permissions, role_id)
    return "*" in set(resolved)
