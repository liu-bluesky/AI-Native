"""JWT 认证工具"""

from __future__ import annotations

import time
import jwt
import os

SECRET_KEY = os.environ.get("JWT_SECRET", "ai-employee-factory-dev-secret")
ALGORITHM = "HS256"
EXPIRE_SECONDS = 3600 * 8  # 8 小时


def create_token(username: str, role: str = "admin") -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": int(time.time()) + EXPIRE_SECONDS,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
