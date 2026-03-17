"""LLM provider storage (PostgreSQL only)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg import connect
from psycopg.rows import dict_row


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


class LlmProviderStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_providers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider_type TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    default_model TEXT NOT NULL DEFAULT '',
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_llm_providers_enabled_updated
                ON llm_providers (enabled, updated_at DESC);

                CREATE TABLE IF NOT EXISTS feedback_reflection_configs (
                    project_id TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    temperature DOUBLE PRECISION NOT NULL DEFAULT 0.2,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL,
                    PRIMARY KEY (project_id, employee_id)
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_reflection_configs_provider
                ON feedback_reflection_configs (provider_id, updated_at DESC);
                """
            )

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    def new_provider_id(self) -> str:
        return self._new_id("lmp")

    @staticmethod
    def _mask_secret(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) <= 8:
            return "*" * len(text)
        return f"{text[:4]}***{text[-3:]}"

    def save_provider(self, provider: dict[str, Any]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO llm_providers (
                    id, name, provider_type, base_url, default_model, enabled, created_at, updated_at, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET name = EXCLUDED.name,
                    provider_type = EXCLUDED.provider_type,
                    base_url = EXCLUDED.base_url,
                    default_model = EXCLUDED.default_model,
                    enabled = EXCLUDED.enabled,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                (
                    provider["id"],
                    provider["name"],
                    provider["provider_type"],
                    provider["base_url"],
                    provider["default_model"],
                    bool(provider.get("enabled", True)),
                    provider["created_at"],
                    provider["updated_at"],
                    _json_dumps(provider),
                ),
            )

    def create_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now_iso()
        provider = {
            "id": self.new_provider_id(),
            "name": str(payload.get("name") or "").strip(),
            "provider_type": str(payload.get("provider_type") or "openai-compatible").strip().lower(),
            "base_url": str(payload.get("base_url") or "").strip().rstrip("/"),
            "api_key": str(payload.get("api_key") or "").strip(),
            "models": payload.get("models") or [],
            "default_model": str(payload.get("default_model") or "").strip(),
            "enabled": bool(payload.get("enabled", True)),
            "extra_headers": payload.get("extra_headers") or {},
            "owner_username": str(payload.get("owner_username") or "").strip(),
            "shared_usernames": payload.get("shared_usernames") or [],
            "created_at": now,
            "updated_at": now,
        }
        self.save_provider(provider)
        return provider

    def get_provider(self, provider_id: str, include_secret: bool = False) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM llm_providers WHERE id = %s", (provider_id,))
            row = cur.fetchone()
        if row is None:
            return None
        provider = row["payload"]
        if include_secret:
            return provider
        masked = dict(provider)
        masked["api_key_masked"] = self._mask_secret(str(masked.get("api_key") or ""))
        masked["api_key"] = ""
        return masked

    def patch_provider(self, provider_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        provider = self.get_provider(provider_id, include_secret=True)
        if provider is None:
            return None
        provider.update(updates)
        provider["updated_at"] = _now_iso()
        self.save_provider(provider)
        return provider

    def list_providers(self, include_secret: bool = False, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT payload FROM llm_providers"
        params: list[Any] = []
        if enabled_only:
            sql += " WHERE enabled = TRUE"
        sql += " ORDER BY updated_at DESC"
        with self._conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        providers: list[dict[str, Any]] = []
        for row in rows:
            provider = row["payload"]
            if include_secret:
                providers.append(provider)
            else:
                masked = dict(provider)
                masked["api_key_masked"] = self._mask_secret(str(masked.get("api_key") or ""))
                masked["api_key"] = ""
                providers.append(masked)
        return providers

    def delete_provider(self, provider_id: str) -> bool:
        with self._conn.transaction():
            with self._conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM feedback_reflection_configs WHERE provider_id = %s",
                    (provider_id,),
                )
                cur.execute("DELETE FROM llm_providers WHERE id = %s", (provider_id,))
                return bool(cur.rowcount and cur.rowcount > 0)

    def get_reflection_config(self, project_id: str, employee_id: str) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM feedback_reflection_configs
                WHERE project_id = %s AND employee_id = %s
                """,
                (project_id, employee_id),
            )
            row = cur.fetchone()
        return row["payload"] if row else None

    def save_reflection_config(self, config: dict[str, Any]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback_reflection_configs (
                    project_id, employee_id, provider_id, model_name, temperature, updated_at, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (project_id, employee_id) DO UPDATE
                SET provider_id = EXCLUDED.provider_id,
                    model_name = EXCLUDED.model_name,
                    temperature = EXCLUDED.temperature,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                (
                    config["project_id"],
                    config["employee_id"],
                    config["provider_id"],
                    config["model_name"],
                    float(config.get("temperature") or 0.2),
                    config["updated_at"],
                    _json_dumps(config),
                ),
            )

    def upsert_reflection_config(self, project_id: str, employee_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now_iso()
        config = {
            "project_id": project_id,
            "employee_id": employee_id,
            "provider_id": str(payload.get("provider_id") or "").strip(),
            "model_name": str(payload.get("model_name") or "").strip(),
            "temperature": float(payload.get("temperature") if payload.get("temperature") is not None else 0.2),
            "updated_at": now,
        }
        self.save_reflection_config(config)
        return config
