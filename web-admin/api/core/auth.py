"""JWT 认证工具"""

from __future__ import annotations

import time
import jwt
import os

SECRET_KEY = os.environ.get("JWT_SECRET", "ai-employee-factory-dev-secret")
ALGORITHM = "HS256"
EXPIRE_SECONDS = 3600 * 8  # 8 小时


def create_token(username: str, role: str = "admin", roles: list[str] | None = None) -> str:
    normalized_roles = [
        str(item or "").strip().lower()
        for item in (roles or [])
        if str(item or "").strip()
    ]
    if not normalized_roles:
        normalized_roles = [str(role or "admin").strip().lower() or "admin"]
    primary_role = normalized_roles[0]
    payload = {
        "sub": username,
        "role": primary_role,
        "roles": normalized_roles,
        "exp": int(time.time()) + EXPIRE_SECONDS,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
