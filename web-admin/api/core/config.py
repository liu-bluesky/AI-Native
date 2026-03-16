"""运行配置（环境变量统一入口）"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

DEFAULT_DEV_DATABASE_URL = "postgresql://admin:changeme@127.0.0.1:5432/ai_employee"
_API_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE_NAMES = (".env", ".env.local")


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].strip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


@lru_cache(maxsize=1)
def _file_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for filename in _ENV_FILE_NAMES:
        env_path = _API_ROOT / filename
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(raw_line)
            if parsed is None:
                continue
            key, value = parsed
            values[key] = value
    return values


def _get_env(env_name: str, default: str = "") -> str:
    if env_name in os.environ:
        return str(os.environ.get(env_name, default))
    return str(_file_env_values().get(env_name, default))


def _split_env_list(env_name: str, default: list[str]) -> list[str]:
    raw = _get_env(env_name, "").strip()
    if not raw:
        return default
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or default


def _env_bool(env_name: str, default: bool) -> bool:
    raw = _get_env(env_name, "").strip()
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _build_database_url_from_env() -> str:
    database_url = _get_env("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    host = _get_env("DB_HOST", "").strip()
    port = _get_env("DB_PORT", "5432").strip() or "5432"
    user = _get_env("DB_USER", "").strip()
    password = _get_env("DB_PASSWORD", "").strip()
    db_name = _get_env("DB_NAME", "").strip()
    if not (host and user and password and db_name):
        return DEFAULT_DEV_DATABASE_URL
    return f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{quote(db_name)}"


@dataclass(frozen=True)
class Settings:
    api_host: str
    api_port: int
    api_reload: bool
    api_cors_allow_origins: list[str]
    api_cors_allow_methods: list[str]
    api_cors_allow_headers: list[str]
    api_cors_allow_credentials: bool
    core_store_backend: str
    usage_store_backend: str
    feedback_upgrade_enabled_global: bool
    database_url: str
    # Redis
    redis_host: str
    redis_port: int
    redis_db: int
    # 会话
    session_ttl: int
    max_messages: int
    compression_threshold: int
    # 工具
    tool_timeout: int
    max_tool_retries: int
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        api_host=_get_env("API_HOST", "0.0.0.0"),
        api_port=int(_get_env("API_PORT", "8000")),
        api_reload=_env_bool("API_RELOAD", True),
        api_cors_allow_origins=_split_env_list("API_CORS_ALLOW_ORIGINS", ["*"]),
        api_cors_allow_methods=_split_env_list("API_CORS_ALLOW_METHODS", ["*"]),
        api_cors_allow_headers=_split_env_list("API_CORS_ALLOW_HEADERS", ["*"]),
        api_cors_allow_credentials=_env_bool("API_CORS_ALLOW_CREDENTIALS", False),
        core_store_backend=_get_env("CORE_STORE_BACKEND", "postgres").strip().lower(),
        usage_store_backend=_get_env("USAGE_STORE_BACKEND", "postgres").strip().lower(),
        feedback_upgrade_enabled_global=_env_bool("FEEDBACK_UPGRADE_ENABLED_GLOBAL", True),
        database_url=_build_database_url_from_env(),
        redis_host=_get_env("REDIS_HOST", "localhost"),
        redis_port=int(_get_env("REDIS_PORT", "6379")),
        redis_db=int(_get_env("REDIS_DB", "0")),
        session_ttl=int(_get_env("SESSION_TTL", "3600")),
        max_messages=int(_get_env("MAX_MESSAGES", "20")),
        compression_threshold=int(_get_env("COMPRESSION_THRESHOLD", "15")),
        tool_timeout=int(_get_env("TOOL_TIMEOUT", "60")),
        max_tool_retries=int(_get_env("MAX_TOOL_RETRIES", "3")),
    )
