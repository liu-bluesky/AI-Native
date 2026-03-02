"""公共依赖 — 认证、Store 实例"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, Header

from auth import decode_token
from user_store import UserStore
from employee_store import EmployeeStore
from usage_store import UsageStore

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_DEV_DATABASE_URL = "postgresql://admin:changeme@127.0.0.1:5432/ai_employee"


def _build_database_url_from_env() -> str | None:
    database_url = str(os.environ.get("DATABASE_URL", "")).strip()
    if database_url:
        return database_url

    host = str(os.environ.get("DB_HOST", "")).strip()
    port = str(os.environ.get("DB_PORT", "5432")).strip() or "5432"
    user = str(os.environ.get("DB_USER", "")).strip()
    password = str(os.environ.get("DB_PASSWORD", "")).strip()
    db_name = str(os.environ.get("DB_NAME", "")).strip()
    if not (host and user and password and db_name):
        return DEFAULT_DEV_DATABASE_URL
    return f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{quote(db_name)}"


def _create_user_store() -> UserStore | Any:
    backend = str(os.environ.get("CORE_STORE_BACKEND", "postgres")).strip().lower()
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
        database_url = _build_database_url_from_env()
        if not database_url:
            raise RuntimeError(
                "CORE_STORE_BACKEND=postgres 但未提供有效数据库配置。"
                "请设置 DATABASE_URL 或 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME。"
            )
        return UserStorePostgres(database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {backend}")


def _create_employee_store() -> EmployeeStore | Any:
    backend = str(os.environ.get("CORE_STORE_BACKEND", "postgres")).strip().lower()
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
        database_url = _build_database_url_from_env()
        if not database_url:
            raise RuntimeError(
                "CORE_STORE_BACKEND=postgres 但未提供有效数据库配置。"
                "请设置 DATABASE_URL 或 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME。"
            )
        return EmployeeStorePostgres(database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {backend}")


def _create_usage_store() -> UsageStore | Any:
    backend = str(os.environ.get("USAGE_STORE_BACKEND", "postgres")).strip().lower()
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
        database_url = _build_database_url_from_env()
        if not database_url:
            raise RuntimeError(
                "USAGE_STORE_BACKEND=postgres 但未提供有效数据库配置。"
                "请设置 DATABASE_URL 或 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME。"
            )
        return UsageStorePostgres(database_url)
    raise RuntimeError(f"Unsupported USAGE_STORE_BACKEND: {backend}")


user_store = _create_user_store()
employee_store = _create_employee_store()
usage_store = _create_usage_store()


async def require_auth(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    payload = decode_token(authorization[7:])
    if payload is None:
        raise HTTPException(401, "Token expired or invalid")
    return payload
