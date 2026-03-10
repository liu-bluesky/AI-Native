"""公共依赖 — 认证、Store 实例"""

from __future__ import annotations

from fastapi import HTTPException, Header, Query

from core.auth import decode_token
from stores.factory import (
    employee_store,
    external_mcp_store,
    project_chat_store,
    project_store,
    role_store,
    system_config_store,
    usage_store,
    user_store,
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
