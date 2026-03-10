"""公共依赖 — 认证、Store 实例"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from threading import Lock

from fastapi import HTTPException, Header, Query

from auth import decode_token
from config import get_settings
from user_store import UserStore
from role_store import RoleStore
from employee_store import EmployeeStore
from project_store import ProjectStore
from project_chat_store import ProjectChatStore
from system_config_store import SystemConfigStore
from external_mcp_store import ExternalMcpStore
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


def _create_role_store() -> RoleStore | Any:
    settings = get_settings()
    backend = settings.core_store_backend
    if backend == "json":
        return RoleStore(DATA_DIR)
    if backend == "postgres":
        try:
            from role_store_pg import RoleStorePostgres
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "CORE_STORE_BACKEND=postgres 但未安装 PostgreSQL 驱动。"
                "请安装依赖: psycopg[binary]>=3.2。"
            ) from exc
        return RoleStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {backend}")


def _create_project_store() -> ProjectStore | Any:
    settings = get_settings()
    backend = settings.core_store_backend
    if backend == "json":
        return ProjectStore(DATA_DIR)
    if backend == "postgres":
        try:
            from project_store_pg import ProjectStorePostgres
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "CORE_STORE_BACKEND=postgres 但未安装 PostgreSQL 驱动。"
                "请安装依赖: psycopg[binary]>=3.2。"
            ) from exc
        return ProjectStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {backend}")


def _create_project_chat_store() -> ProjectChatStore | Any:
    settings = get_settings()
    backend = settings.core_store_backend
    if backend == "json":
        return ProjectChatStore(DATA_DIR)
    if backend == "postgres":
        try:
            from project_chat_store_pg import ProjectChatStorePostgres
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "CORE_STORE_BACKEND=postgres 但未安装 PostgreSQL 驱动。"
                "请安装依赖: psycopg[binary]>=3.2。"
            ) from exc
        return ProjectChatStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {backend}")


def _create_system_config_store() -> SystemConfigStore | Any:
    settings = get_settings()
    backend = settings.core_store_backend
    if backend == "json":
        return SystemConfigStore(DATA_DIR)
    if backend == "postgres":
        try:
            from system_config_store_pg import SystemConfigStorePostgres
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "CORE_STORE_BACKEND=postgres 但未安装 PostgreSQL 驱动。"
                "请安装依赖: psycopg[binary]>=3.2。"
            ) from exc
        return SystemConfigStorePostgres(settings.database_url)
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


def _create_external_mcp_store() -> ExternalMcpStore | Any:
    settings = get_settings()
    backend = settings.core_store_backend
    if backend == "json":
        return ExternalMcpStore(DATA_DIR)
    if backend == "postgres":
        try:
            from external_mcp_store_pg import ExternalMcpStorePostgres
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "CORE_STORE_BACKEND=postgres 但未安装 PostgreSQL 驱动。"
                "请安装依赖: psycopg[binary]>=3.2。"
            ) from exc
        return ExternalMcpStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {backend}")


user_store = _StoreProxy(_create_user_store)
role_store = _StoreProxy(_create_role_store)
employee_store = _StoreProxy(_create_employee_store)
project_store = _StoreProxy(_create_project_store)
project_chat_store = _StoreProxy(_create_project_chat_store)
system_config_store = _StoreProxy(_create_system_config_store)
usage_store = _StoreProxy(_create_usage_store)
external_mcp_store = _StoreProxy(_create_external_mcp_store)


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
