"""公共依赖 — 认证、Store 实例"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from threading import Lock

from fastapi import HTTPException, Header

from auth import decode_token
from config import get_settings
from user_store import UserStore
from employee_store import EmployeeStore
from usage_store import UsageStore

DATA_DIR = Path(__file__).parent / "data"


class _StoreProxy:
    """延迟初始化 store，避免模块导入时立即连库。"""

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._instance: Any = None
        self._lock = Lock()

    def _get_instance(self) -> Any:
        if self._instance is not None:
            return self._instance
        with self._lock:
            if self._instance is None:
                self._instance = self._factory()
        return self._instance

    def __getattr__(self, item: str) -> Any:
        return getattr(self._get_instance(), item)


def _create_user_store() -> UserStore | Any:
    settings = get_settings()
    backend = settings.core_store_backend
    if backend == "json":
        return UserStore(DATA_DIR)
    if backend == "postgres":
        try:
            from user_store_pg import UserStorePostgres
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "CORE_STORE_BACKEND=postgres 但未安装 PostgreSQL 驱动。"
                "请安装依赖: psycopg[binary]>=3.2。"
            ) from exc
        return UserStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {backend}")


def _create_employee_store() -> EmployeeStore | Any:
    settings = get_settings()
    backend = settings.core_store_backend
    if backend == "json":
        return EmployeeStore(DATA_DIR)
    if backend == "postgres":
        try:
            from employee_store_pg import EmployeeStorePostgres
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "CORE_STORE_BACKEND=postgres 但未安装 PostgreSQL 驱动。"
                "请安装依赖: psycopg[binary]>=3.2。"
            ) from exc
        return EmployeeStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {backend}")


def _create_usage_store() -> UsageStore | Any:
    settings = get_settings()
    backend = settings.usage_store_backend
    if backend == "sqlite":
        return UsageStore(DATA_DIR / "usage.db")
    if backend == "postgres":
        try:
            from usage_store_pg import UsageStorePostgres
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "USAGE_STORE_BACKEND=postgres 但未安装 PostgreSQL 驱动。"
                "请安装依赖: psycopg[binary]>=3.2。"
            ) from exc
        return UsageStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported USAGE_STORE_BACKEND: {backend}")


user_store = _StoreProxy(_create_user_store)
employee_store = _StoreProxy(_create_employee_store)
usage_store = _StoreProxy(_create_usage_store)


async def require_auth(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    payload = decode_token(authorization[7:])
    if payload is None:
        raise HTTPException(401, "Token expired or invalid")
    return payload
