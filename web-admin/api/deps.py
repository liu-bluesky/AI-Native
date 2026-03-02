"""公共依赖 — 认证、Store 实例"""

from __future__ import annotations

from pathlib import Path
from fastapi import HTTPException, Header

from auth import decode_token
from user_store import UserStore
from employee_store import EmployeeStore

DATA_DIR = Path(__file__).parent / "data"
user_store = UserStore(DATA_DIR)
employee_store = EmployeeStore(DATA_DIR)


async def require_auth(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    payload = decode_token(authorization[7:])
    if payload is None:
        raise HTTPException(401, "Token expired or invalid")
    return payload
