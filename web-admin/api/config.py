"""运行配置（环境变量统一入口）"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote

DEFAULT_DEV_DATABASE_URL = "postgresql://admin:changeme@127.0.0.1:5432/ai_employee"


def _split_env_list(env_name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or default


def _env_bool(env_name: str, default: bool) -> bool:
    raw = os.environ.get(env_name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _build_database_url_from_env() -> str:
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
    # 外部 Agent
    external_agent_codex_bin: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        api_host=os.environ.get("API_HOST", "0.0.0.0"),
        api_port=int(os.environ.get("API_PORT", "8000")),
        api_reload=_env_bool("API_RELOAD", True),
        api_cors_allow_origins=_split_env_list("API_CORS_ALLOW_ORIGINS", ["*"]),
        api_cors_allow_methods=_split_env_list("API_CORS_ALLOW_METHODS", ["*"]),
        api_cors_allow_headers=_split_env_list("API_CORS_ALLOW_HEADERS", ["*"]),
        api_cors_allow_credentials=_env_bool("API_CORS_ALLOW_CREDENTIALS", False),
        core_store_backend=str(os.environ.get("CORE_STORE_BACKEND", "postgres")).strip().lower(),
        usage_store_backend=str(os.environ.get("USAGE_STORE_BACKEND", "postgres")).strip().lower(),
        feedback_upgrade_enabled_global=_env_bool("FEEDBACK_UPGRADE_ENABLED_GLOBAL", True),
        database_url=_build_database_url_from_env(),
        redis_host=os.environ.get("REDIS_HOST", "localhost"),
        redis_port=int(os.environ.get("REDIS_PORT", "6379")),
        redis_db=int(os.environ.get("REDIS_DB", "0")),
        session_ttl=int(os.environ.get("SESSION_TTL", "3600")),
        max_messages=int(os.environ.get("MAX_MESSAGES", "20")),
        compression_threshold=int(os.environ.get("COMPRESSION_THRESHOLD", "15")),
        tool_timeout=int(os.environ.get("TOOL_TIMEOUT", "60")),
        max_tool_retries=int(os.environ.get("MAX_TOOL_RETRIES", "3")),
        external_agent_codex_bin=str(os.environ.get("EXTERNAL_AGENT_CODEX_BIN", "")).strip(),
    )
