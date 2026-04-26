"""LLM provider service for feedback reflection."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
import requests
from starlette.concurrency import run_in_threadpool

from core.config import get_settings
from services.llm_model_type_catalog import DEFAULT_MODEL_TYPE, get_model_type_meta, normalize_model_type
from stores.postgres.llm_provider_store import LlmProviderStorePostgres


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LlmProviderService:
    def __init__(self, store: LlmProviderStorePostgres) -> None:
        self._store = store
        self._cleanup_legacy_static_provider()

    @staticmethod
    def _normalize_provider_type(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return "openai-compatible"
        aliases = {
            "openai": "openai-compatible",
            "openai_compatible": "openai-compatible",
            "openai-compatible": "openai-compatible",
            "response": "responses",
            "openai-responses": "responses",
            "responses": "responses",
            "custom": "custom",
        }
        return aliases.get(raw, raw)

    @classmethod
    def _is_responses_provider(cls, provider: dict[str, Any]) -> bool:
        return cls._normalize_provider_type(provider.get("provider_type")) == "responses"

    @staticmethod
    def _normalize_models(value: Any) -> list[str]:
        if isinstance(value, list):
            raw = [str(item or "").strip() for item in value]
        else:
            text = str(value or "")
            parts = text.replace("\n", ",").split(",")
            raw = [part.strip() for part in parts]
        models: list[str] = []
        seen: set[str] = set()
        for model in raw:
            if not model or model in seen:
                continue
            seen.add(model)
            models.append(model)
        return models

    @classmethod
    def _normalize_model_configs(
        cls,
        value: Any,
        fallback_models: Any = None,
    ) -> list[dict[str, str]]:
        raw_items: list[Any] = []
        if isinstance(value, list):
            raw_items.extend(value)
        if fallback_models is not None:
            raw_items.extend(cls._normalize_models(fallback_models))

        configs: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in raw_items:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("model_name") or "").strip()
                model_type = normalize_model_type(item.get("model_type"))
            else:
                name = str(item or "").strip()
                model_type = DEFAULT_MODEL_TYPE
            if not name or name in seen:
                continue
            seen.add(name)
            configs.append(
                {
                    "name": name,
                    "model_type": model_type,
                }
            )
        return configs

    @staticmethod
    def _model_names_from_configs(configs: list[dict[str, str]]) -> list[str]:
        return [str(item.get("name") or "").strip() for item in configs if str(item.get("name") or "").strip()]

    @classmethod
    def _ensure_default_model_config(
        cls,
        model_configs: list[dict[str, str]],
        default_model: str,
    ) -> list[dict[str, str]]:
        normalized_default = str(default_model or "").strip()
        if not normalized_default:
            return model_configs
        names = {str(item.get("name") or "").strip() for item in model_configs}
        if normalized_default in names:
            return model_configs
        return [
            {
                "name": normalized_default,
                "model_type": DEFAULT_MODEL_TYPE,
            },
            *model_configs,
        ]

    @staticmethod
    def _normalize_headers(value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        headers: dict[str, str] = {}
        for key, item in value.items():
            name = str(key or "").strip()
            if not name:
                continue
            headers[name] = str(item or "").strip()
        return headers

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        return str(value or "").strip().rstrip("/")

    @staticmethod
    def _clamp_temperature(value: Any) -> float:
        try:
            temp = float(value)
        except (TypeError, ValueError):
            temp = 0.2
        return max(0.0, min(temp, 2.0))

    @staticmethod
    def _requires_tool_role_compat(provider: dict[str, Any]) -> bool:
        # Some OpenAI-compatible gateways (e.g. Codex bridge) reject role=tool.
        base_url = str(provider.get("base_url") or "").strip().lower()
        return "code.newcli.com/codex" in base_url

    @staticmethod
    def _convert_tool_role_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for item in messages:
            if str(item.get("role") or "").strip().lower() != "tool":
                converted.append(item)
                continue
            tool_call_id = str(item.get("tool_call_id") or "").strip()
            content = str(item.get("content") or "")
            prefix = f"[tool_result:{tool_call_id}]" if tool_call_id else "[tool_result]"
            converted.append(
                {
                    "role": "user",
                    "content": f"{prefix}\n{content}",
                }
            )
        return converted

    def _validate_create_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        base_url = self._normalize_base_url(str(payload.get("base_url") or ""))
        if not base_url:
            raise ValueError("base_url is required")

        model_configs = self._normalize_model_configs(
            payload.get("model_configs"),
            payload.get("models"),
        )
        default_model = str(payload.get("default_model") or "").strip()
        if not default_model and model_configs:
            default_model = str(model_configs[0].get("name") or "").strip()
        model_configs = self._ensure_default_model_config(model_configs, default_model)
        models = self._model_names_from_configs(model_configs)
        if not default_model and models:
            default_model = models[0]

        return {
            "name": name,
            "provider_type": self._normalize_provider_type(payload.get("provider_type")),
            "base_url": base_url,
            "api_key": str(payload.get("api_key") or "").strip(),
            "models": models,
            "model_configs": model_configs,
            "default_model": default_model,
            "enabled": bool(payload.get("enabled", True)),
            "extra_headers": self._normalize_headers(payload.get("extra_headers") or {}),
        }

    @classmethod
    def _hydrate_provider_models(cls, provider: dict[str, Any]) -> dict[str, Any]:
        hydrated = dict(provider)
        default_model = str(hydrated.get("default_model") or "").strip()
        model_configs = cls._normalize_model_configs(
            hydrated.get("model_configs"),
            hydrated.get("models"),
        )
        model_configs = cls._ensure_default_model_config(model_configs, default_model)
        hydrated["model_configs"] = model_configs
        hydrated["models"] = cls._model_names_from_configs(model_configs)
        if not default_model and hydrated["models"]:
            hydrated["default_model"] = hydrated["models"][0]
        return hydrated

    @staticmethod
    def _pick_default_model(provider: dict[str, Any]) -> str:
        default_model = str(provider.get("default_model") or "").strip()
        if default_model:
            return default_model
        models = provider.get("models") or []
        return str(models[0]).strip() if models else ""

    @classmethod
    def get_model_config(cls, provider: dict[str, Any], model_name: str) -> dict[str, Any] | None:
        normalized_name = str(model_name or "").strip()
        if not normalized_name:
            normalized_name = cls._pick_default_model(provider)
        if not normalized_name:
            return None
        for item in cls._normalize_model_configs(provider.get("model_configs"), provider.get("models")):
            if str(item.get("name") or "").strip() == normalized_name:
                return {
                    **item,
                    **get_model_type_meta(item.get("model_type")),
                }
        return {
            "name": normalized_name,
            "model_type": DEFAULT_MODEL_TYPE,
            **get_model_type_meta(DEFAULT_MODEL_TYPE),
        }

    @staticmethod
    def _normalize_owner_username(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_shared_usernames(cls, value: Any) -> list[str]:
        raw_items = value if isinstance(value, list) else []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            username = cls._normalize_owner_username(item)
            if not username or username in seen:
                continue
            seen.add(username)
            normalized.append(username)
        return normalized

    @classmethod
    def _provider_owner_username(cls, provider: dict[str, Any]) -> str:
        return cls._normalize_owner_username(provider.get("owner_username"))

    @classmethod
    def _provider_shared_usernames(cls, provider: dict[str, Any]) -> list[str]:
        return cls._normalize_shared_usernames(provider.get("shared_usernames"))

    def _cleanup_legacy_static_provider(self) -> None:
        self._store.delete_provider("lmp-local-static-codex")

    def _resolve_default_provider_id(self, providers: list[dict[str, Any]], owner_username: str = "") -> str:
        if not providers:
            return ""
        from stores.factory import user_store

        configured_id = ""
        normalized_owner = self._normalize_owner_username(owner_username)
        if normalized_owner:
            user = user_store.get(normalized_owner)
            configured_id = str(getattr(user, "default_ai_provider_id", "") or "").strip() if user else ""
        if configured_id and any(str(item.get("id") or "").strip() == configured_id for item in providers):
            return configured_id
        return str(providers[0].get("id") or "").strip()

    def _filter_providers_for_actor(
        self,
        providers: list[dict[str, Any]],
        *,
        owner_username: str = "",
        include_all: bool = False,
        include_shared: bool = False,
        owner_only: bool = False,
    ) -> list[dict[str, Any]]:
        if include_all:
            return providers
        normalized_owner = self._normalize_owner_username(owner_username)
        if not normalized_owner:
            return []
        visible: list[dict[str, Any]] = []
        for provider in providers:
            provider_owner = self._provider_owner_username(provider)
            if provider_owner == normalized_owner:
                visible.append(provider)
                continue
            if owner_only or not include_shared:
                continue
            if normalized_owner in self._provider_shared_usernames(provider):
                visible.append(provider)
        return visible

    def list_providers(
        self,
        enabled_only: bool = False,
        *,
        owner_username: str = "",
        include_all: bool = False,
        include_shared: bool = False,
    ) -> list[dict[str, Any]]:
        providers = [
            self._hydrate_provider_models(item)
            for item in self._store.list_providers(include_secret=False, enabled_only=enabled_only)
        ]
        visible_providers = self._filter_providers_for_actor(
            providers,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=include_shared,
        )
        default_provider_id = self._resolve_default_provider_id(visible_providers, owner_username=owner_username)
        return [
            {
                **provider,
                "is_default": str(provider.get("id") or "").strip() == default_provider_id,
            }
            for provider in visible_providers
        ]

    def get_default_provider(
        self,
        include_secret: bool = True,
        *,
        owner_username: str = "",
        include_all: bool = False,
        include_shared: bool = True,
    ) -> dict[str, Any] | None:
        providers = [
            self._hydrate_provider_models(item)
            for item in self._store.list_providers(include_secret=include_secret, enabled_only=True)
        ]
        visible_providers = self._filter_providers_for_actor(
            providers,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=include_shared,
        )
        default_provider_id = self._resolve_default_provider_id(
            visible_providers,
            owner_username=owner_username,
        )
        if not default_provider_id:
            return None
        return next(
            (item for item in visible_providers if str(item.get("id") or "").strip() == default_provider_id),
            visible_providers[0] if visible_providers else None,
        )

    def create_provider(self, payload: dict[str, Any], *, owner_username: str) -> dict[str, Any]:
        validated = self._validate_create_payload(payload)
        validated["owner_username"] = self._normalize_owner_username(owner_username)
        validated["shared_usernames"] = self._normalize_shared_usernames(payload.get("shared_usernames"))
        provider = self._store.create_provider(validated)
        return self._hydrate_provider_models(self._store.get_provider(provider["id"], include_secret=False) or provider)

    def get_provider_raw(
        self,
        provider_id: str,
        *,
        owner_username: str = "",
        include_all: bool = True,
        include_shared: bool = True,
        owner_only: bool = False,
    ) -> dict[str, Any] | None:
        provider = self._store.get_provider(provider_id, include_secret=True)
        if provider is None:
            return None
        provider = self._hydrate_provider_models(provider)
        visible = self._filter_providers_for_actor(
            [provider],
            owner_username=owner_username,
            include_all=include_all,
            include_shared=include_shared,
            owner_only=owner_only,
        )
        return visible[0] if visible else None

    def update_provider(
        self,
        provider_id: str,
        payload: dict[str, Any],
        *,
        owner_username: str,
        include_all: bool = False,
    ) -> dict[str, Any]:
        current = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=False,
            owner_only=True,
        )
        if current is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        merged_payload = {
            **current,
            **payload,
        }
        if "model_configs" in payload and payload.get("model_configs") is not None and "models" not in payload:
            merged_payload["models"] = []
        updates = self._validate_create_payload(merged_payload)
        updates["owner_username"] = self._provider_owner_username(current)
        updates["shared_usernames"] = self._normalize_shared_usernames(
            payload.get("shared_usernames", current.get("shared_usernames")),
        )
        updated = self._store.patch_provider(provider_id, updates)
        if updated is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        return self._hydrate_provider_models(self._store.get_provider(provider_id, include_secret=False) or updated)

    def delete_provider(self, provider_id: str, *, owner_username: str, include_all: bool = False) -> bool:
        current = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=False,
            owner_only=True,
        )
        if current is None:
            return False
        return self._store.delete_provider(provider_id)

    def get_reflection_config(self, project_id: str, employee_id: str) -> dict[str, Any] | None:
        return self._store.get_reflection_config(project_id, employee_id)

    def upsert_reflection_config(
        self,
        project_id: str,
        employee_id: str,
        provider_id: str,
        model_name: str = "",
        temperature: float = 0.2,
        *,
        owner_username: str = "",
        include_all: bool = False,
    ) -> dict[str, Any]:
        if not employee_id:
            raise ValueError("employee_id is required")
        provider = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=True,
        )
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")

        final_model = str(model_name or "").strip() or self._pick_default_model(provider)
        if not final_model:
            raise ValueError("model_name is required")

        return self._store.upsert_reflection_config(
            project_id,
            employee_id,
            {
                "provider_id": provider_id,
                "model_name": final_model,
                "temperature": self._clamp_temperature(temperature),
            },
        )

    def list_reflection_options(self, *, owner_username: str = "", include_all: bool = False) -> dict[str, Any]:
        providers = self.list_providers(
            enabled_only=True,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=True,
        )
        options: list[dict[str, Any]] = []
        for provider in providers:
            provider_id = str(provider.get("id") or "").strip()
            provider_name = str(provider.get("name") or "").strip() or provider_id
            default_model = str(provider.get("default_model") or "").strip()
            models = self._normalize_models(provider.get("models") or [])
            if default_model and default_model not in models:
                models = [default_model, *models]
            for model in models:
                model_config = self.get_model_config(provider, model) or {}
                options.append(
                    {
                        "provider_id": provider_id,
                        "provider_name": provider_name,
                        "provider_type": str(provider.get("provider_type") or ""),
                        "model_name": model,
                        "model_type": str(model_config.get("model_type") or DEFAULT_MODEL_TYPE),
                        "is_default": model == default_model,
                    }
                )
        return {"providers": providers, "options": options}

    def resolve_reflection_target(
        self,
        project_id: str,
        employee_id: str,
        owner_username: str = "",
        include_all: bool = False,
        preferred_provider_id: str = "",
        preferred_model_name: str = "",
        preferred_temperature: float | None = None,
    ) -> dict[str, Any] | None:
        provider_id = str(preferred_provider_id or "").strip()
        model_name = str(preferred_model_name or "").strip()
        temperature = self._clamp_temperature(preferred_temperature if preferred_temperature is not None else 0.2)

        if provider_id:
            provider = self.get_provider_raw(
                provider_id,
                owner_username=owner_username,
                include_all=include_all,
                include_shared=True,
            )
            if provider is None:
                raise LookupError(f"LLM provider {provider_id} not found")
            if not bool(provider.get("enabled", True)):
                raise ValueError(f"LLM provider {provider_id} is disabled")
            chosen_model = model_name or self._pick_default_model(provider)
            if not chosen_model:
                raise ValueError("model_name is required")
            return {
                "provider": provider,
                "provider_id": provider_id,
                "model_name": chosen_model,
                "temperature": temperature,
                "from_config": False,
            }

        config = self.get_reflection_config(project_id, employee_id)
        if config is None:
            fallback_provider = self.get_default_provider(
                include_secret=True,
                owner_username=owner_username,
                include_all=include_all,
                include_shared=True,
            )
            if fallback_provider and bool(fallback_provider.get("enabled", True)):
                chosen_model = model_name or self._pick_default_model(fallback_provider)
                if chosen_model:
                    return {
                        "provider": fallback_provider,
                        "provider_id": str(fallback_provider.get("id") or "").strip(),
                        "model_name": chosen_model,
                        "temperature": temperature,
                        "from_config": False,
                    }
            return None

        cfg_provider_id = str(config.get("provider_id") or "").strip()
        provider = self.get_provider_raw(
            cfg_provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=True,
        )
        if provider is None or not bool(provider.get("enabled", True)):
            fallback_provider = self.get_default_provider(
                include_secret=True,
                owner_username=owner_username,
                include_all=include_all,
                include_shared=True,
            )
            if fallback_provider and bool(fallback_provider.get("enabled", True)):
                chosen_model = model_name or self._pick_default_model(fallback_provider)
                if chosen_model:
                    return {
                        "provider": fallback_provider,
                        "provider_id": str(fallback_provider.get("id") or "").strip(),
                        "model_name": chosen_model,
                        "temperature": temperature,
                        "from_config": False,
                    }
            return None

        chosen_model = model_name or str(config.get("model_name") or "").strip() or self._pick_default_model(provider)
        if not chosen_model:
            return None
        cfg_temp = config.get("temperature")
        final_temperature = self._clamp_temperature(preferred_temperature if preferred_temperature is not None else cfg_temp)
        return {
            "provider": provider,
            "provider_id": cfg_provider_id,
            "model_name": chosen_model,
            "temperature": final_temperature,
            "from_config": True,
        }

    @staticmethod
    def _normalize_chat_message_content(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            text = value.get("text")
            if isinstance(text, str):
                return text.strip()
            return str(value).strip()
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        parts.append(text)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                        continue
                    if item.get("type") == "text":
                        item_text = str(item.get("text") or "").strip()
                        if item_text:
                            parts.append(item_text)
            return "\n".join(parts).strip()
        return str(value or "").strip()

    @classmethod
    def _normalize_chat_messages(cls, messages: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in messages if isinstance(messages, list) else []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user").strip().lower()
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            
            if role == "tool":
                normalized.append({
                    "role": role,
                    "tool_call_id": str(item.get("tool_call_id") or ""),
                    "content": str(item.get("content") or "")
                })
                continue
                
            if role == "assistant" and "tool_calls" in item:
                msg = {"role": role, "tool_calls": item.get("tool_calls")}
                content = item.get("content")
                if content:
                    msg["content"] = str(content)
                normalized.append(msg)
                continue

            content = item.get("content")
            if isinstance(content, list):
                normalized.append({"role": role, "content": content})
                continue

            str_content = cls._normalize_chat_message_content(content)
            if not str_content:
                continue
            normalized.append({"role": role, "content": str_content})
        return normalized

    @staticmethod
    def _messages_to_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for message in messages:
            content = message.get("content")
            text_content = str(content) if isinstance(content, list) else str(content or "")
            converted.append(
                {
                    "role": message["role"],
                    "content": [{"type": "input_text", "text": text_content}],
                }
            )
        return converted

    def _chat_completion_sync(
        self,
        provider_id: str,
        model_name: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int | None,
        timeout: int,
    ) -> dict[str, Any]:
        provider = self.get_provider_raw(provider_id)
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")

        chosen_model = str(model_name or "").strip() or self._pick_default_model(provider)
        if not chosen_model:
            raise ValueError("model_name is required")

        normalized_messages = self._normalize_chat_messages(messages)
        if self._requires_tool_role_compat(provider):
            normalized_messages = self._convert_tool_role_messages(normalized_messages)
        if not normalized_messages:
            raise ValueError("messages is required")

        normalized_temperature = self._clamp_temperature(temperature)
        normalized_max_tokens: int | None
        if max_tokens is None:
            normalized_max_tokens = None
        else:
            try:
                normalized_max_tokens = int(max_tokens)
            except (TypeError, ValueError):
                normalized_max_tokens = 1024
            normalized_max_tokens = max(16, min(normalized_max_tokens, 8192))

        if self._is_responses_provider(provider):
            endpoint = self._build_responses_url(str(provider.get("base_url") or ""))
            if not endpoint:
                raise ValueError("provider base_url is empty")
            body = {
                "model": chosen_model,
                "temperature": normalized_temperature,
                "input": self._messages_to_responses_input(normalized_messages),
            }
            if normalized_max_tokens is not None:
                body["max_output_tokens"] = normalized_max_tokens
            payload = self._request_json("POST", endpoint, self._build_headers(provider), body=body, timeout=timeout)
        else:
            endpoint = self._build_chat_completion_url(str(provider.get("base_url") or ""))
            if not endpoint:
                raise ValueError("provider base_url is empty")
            body = {
                "model": chosen_model,
                "temperature": normalized_temperature,
                "messages": normalized_messages,
                "stream": False,
            }
            if normalized_max_tokens is not None:
                body["max_tokens"] = normalized_max_tokens
            payload = self._request_json("POST", endpoint, self._build_headers(provider), body=body, timeout=timeout)

        return {
            "content": self._extract_content(payload),
            "raw": payload,
            "provider_id": provider_id,
            "model_name": chosen_model,
        }

    async def chat_completion(
        self,
        provider_id: str,
        model_name: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int | None = 1024,
        timeout: int = 45,
    ) -> dict[str, Any]:
        return await run_in_threadpool(
            self._chat_completion_sync,
            provider_id,
            model_name,
            messages,
            temperature,
            max_tokens,
            timeout,
        )

    async def chat_completion_stream(
        self,
        provider_id: str,
        model_name: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout: int = 120,
        tools: list[dict[str, Any]] | None = None,
    ):
        provider = self.get_provider_raw(provider_id)
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")

        chosen_model = str(model_name or "").strip() or self._pick_default_model(provider)
        if not chosen_model:
            raise ValueError("model_name is required")

        normalized_messages = self._normalize_chat_messages(messages)
        if self._requires_tool_role_compat(provider):
            normalized_messages = self._convert_tool_role_messages(normalized_messages)
        if not normalized_messages:
            raise ValueError("messages is required")

        normalized_temperature = self._clamp_temperature(temperature)
        try:
            normalized_max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            normalized_max_tokens = 1024
        normalized_max_tokens = max(16, min(normalized_max_tokens, 8192))

        if self._is_responses_provider(provider):
            raise ValueError(f"Provider {provider_id} uses 'responses' mode which does not support streaming. Please use chat_completion() instead.")

        endpoint = self._build_chat_completion_url(str(provider.get("base_url") or ""))
        if not endpoint:
            raise ValueError("provider base_url is empty")

        body = {
            "model": chosen_model,
            "temperature": normalized_temperature,
            "messages": normalized_messages,
            "max_tokens": normalized_max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            body["tools"] = tools

        async for chunk in self._stream_request(
            endpoint,
            self._build_headers(provider),
            body,
            timeout,
            provider_id=provider_id,
            model_name=chosen_model,
        ):
            yield chunk

    @staticmethod
    def _normalize_usage_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        prompt_tokens = payload.get("prompt_tokens", payload.get("input_tokens"))
        completion_tokens = payload.get("completion_tokens", payload.get("output_tokens"))
        cached_tokens = payload.get("cached_input_tokens")
        if cached_tokens is None:
            prompt_details = payload.get("prompt_tokens_details")
            if isinstance(prompt_details, dict):
                cached_tokens = prompt_details.get("cached_tokens", prompt_details.get("cached_input_tokens"))
        total_tokens = payload.get("total_tokens")
        if total_tokens in (None, ""):
            try:
                total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0) - int(cached_tokens or 0)
            except (TypeError, ValueError):
                total_tokens = payload.get("total_tokens")
        normalized: dict[str, Any] = {}
        for key, value in (
            ("input_tokens", prompt_tokens),
            ("output_tokens", completion_tokens),
            ("cached_input_tokens", cached_tokens),
            ("total_tokens", total_tokens),
            ("cost_usd", payload.get("cost_usd", payload.get("cost"))),
        ):
            if value not in (None, ""):
                normalized[key] = value
        return normalized

    @staticmethod
    async def _stream_request(
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        timeout: int = 120,
        *,
        provider_id: str = "",
        model_name: str = "",
    ):
        import httpx
        import json
        import logging
        logger = logging.getLogger(__name__)
        tool_index_by_call_id: dict[str, int] = {}
        next_tool_index = 0

        def _normalize_arguments(value: Any) -> str:
            if isinstance(value, str):
                return value
            if isinstance(value, (dict, list)):
                try:
                    return json.dumps(value, ensure_ascii=False)
                except Exception:
                    return str(value)
            return str(value or "")

        def _tool_index(call_id: str) -> int:
            nonlocal next_tool_index
            existing = tool_index_by_call_id.get(call_id)
            if existing is not None:
                return existing
            tool_index_by_call_id[call_id] = next_tool_index
            next_tool_index += 1
            return tool_index_by_call_id[call_id]

        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    error_text = await resp.aread()
                    content_type = str(resp.headers.get("Content-Type") or "").strip()
                    summary, diagnostic = LlmProviderService._summarize_http_error_response(
                        error_text,
                        content_type=content_type,
                    )
                    logger.warning(
                        "LLM stream request failed: provider=%s model=%s status=%s content_type=%s body=%s",
                        provider_id or "-",
                        model_name or "-",
                        resp.status_code,
                        content_type or "-",
                        diagnostic,
                    )
                    raise RuntimeError(f"LLM stream request failed: HTTP {resp.status_code} {summary}")

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            finish_reason = choice.get("finish_reason")

                            # Build result dict
                            result = {}
                            if "content" in delta and delta["content"]:
                                result["content"] = delta["content"]
                            tool_calls: list[dict[str, Any]] = []
                            if "tool_calls" in delta and isinstance(delta["tool_calls"], list):
                                tool_calls.extend(delta["tool_calls"])

                            # Compatibility: some upstreams emit tool calls in top-level/item fields
                            # instead of OpenAI-style delta.tool_calls.
                            item = data.get("item")
                            if isinstance(item, dict):
                                call_id = str(item.get("call_id") or "").strip()
                                status = str(item.get("status") or "").strip().lower()
                                if call_id and status == "completed":
                                    tool_calls.append(
                                        {
                                            "index": _tool_index(call_id),
                                            "id": call_id,
                                            "type": "function",
                                            "function": {
                                                "name": str(item.get("name") or "").strip(),
                                                "arguments": _normalize_arguments(item.get("arguments")),
                                            },
                                        }
                                    )

                            top_call_id = str(data.get("call_id") or "").strip()
                            if top_call_id and ("arguments" in data or "name" in data):
                                tool_calls.append(
                                    {
                                        "index": _tool_index(top_call_id),
                                        "id": top_call_id,
                                        "type": "function",
                                        "function": {
                                            "name": str(data.get("name") or "").strip(),
                                            "arguments": _normalize_arguments(data.get("arguments")),
                                        },
                                    }
                                )
                            if tool_calls:
                                result["tool_calls"] = tool_calls
                            if finish_reason:
                                result["finish_reason"] = finish_reason
                            usage_payload = LlmProviderService._normalize_usage_payload(data.get("usage"))
                            if usage_payload:
                                result["usage"] = usage_payload
                                result["provider_id"] = str(provider_id or "").strip()
                                result["model_name"] = str(data.get("model") or model_name or "").strip()

                            if result:
                                yield result
                        except (json.JSONDecodeError, IndexError, KeyError) as e:
                            logger.warning(f"Failed to parse SSE line: {line[:100]}, error: {e}")
                            continue


    @staticmethod
    def _build_chat_completion_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        if base.endswith("/openai"):
            return f"{base}/chat/completions"
        if base.endswith("/api/paas/v4"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    @staticmethod
    def _build_responses_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/responses"):
            return base
        if base.endswith("/v1"):
            return f"{base}/responses"
        if base.endswith("/openai"):
            return f"{base}/responses"
        if base.endswith("/api/paas/v4"):
            return f"{base}/responses"
        if base.endswith("/chat/completions"):
            return f"{base[:-len('/chat/completions')]}/responses"
        return f"{base}/v1/responses"

    @staticmethod
    def _build_models_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/responses"):
            return f"{base[:-len('/responses')]}/models"
        if base.endswith("/v1"):
            return f"{base}/models"
        if base.endswith("/openai"):
            return f"{base}/models"
        if base.endswith("/api/paas/v4"):
            return f"{base}/models"
        if base.endswith("/chat/completions"):
            return f"{base[:-len('/chat/completions')]}/models"
        return f"{base}/v1/models"

    @staticmethod
    def _build_images_generation_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/images/generations"):
            return base
        if base.endswith("/v1"):
            return f"{base}/images/generations"
        if base.endswith("/openai"):
            return f"{base}/images/generations"
        if base.endswith("/api/paas/v4"):
            return f"{base}/images/generations"
        return f"{base}/v1/images/generations"

    @staticmethod
    def _build_videos_generation_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/videos/generations"):
            return base
        if base.endswith("/v1"):
            return f"{base}/videos/generations"
        if base.endswith("/openai"):
            return f"{base}/videos/generations"
        if base.endswith("/api/paas/v4"):
            return f"{base}/videos/generations"
        return f"{base}/v1/videos/generations"

    @staticmethod
    def _build_audio_speech_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/audio/speech"):
            return base
        if base.endswith("/v1"):
            return f"{base}/audio/speech"
        if base.endswith("/openai"):
            return f"{base}/audio/speech"
        if base.endswith("/api/paas/v4"):
            return f"{base}/audio/speech"
        return f"{base}/v1/audio/speech"

    @staticmethod
    def _build_audio_transcriptions_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/audio/transcriptions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/audio/transcriptions"
        if base.endswith("/openai"):
            return f"{base}/audio/transcriptions"
        if base.endswith("/api/paas/v4"):
            return f"{base}/audio/transcriptions"
        return f"{base}/v1/audio/transcriptions"

    @staticmethod
    def _build_voice_list_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/voice/list"):
            return base
        if base.endswith("/api/paas/v4"):
            return f"{base}/voice/list"
        if base.endswith("/v1"):
            return f"{base[:-len('/v1')]}/voice/list"
        return f"{base}/voice/list"

    @staticmethod
    def _build_voice_clone_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/voice/clone"):
            return base
        if base.endswith("/api/paas/v4"):
            return f"{base}/voice/clone"
        if base.endswith("/v1"):
            return f"{base[:-len('/v1')]}/voice/clone"
        return f"{base}/voice/clone"

    @staticmethod
    def _build_voice_delete_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/voice/delete"):
            return base
        if base.endswith("/api/paas/v4"):
            return f"{base}/voice/delete"
        if base.endswith("/v1"):
            return f"{base[:-len('/v1')]}/voice/delete"
        return f"{base}/voice/delete"

    @staticmethod
    def _build_files_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/files"):
            return base
        if base.endswith("/api/paas/v4"):
            return f"{base}/files"
        if base.endswith("/v1"):
            return f"{base[:-len('/v1')]}/files"
        return f"{base}/files"

    @staticmethod
    def _build_async_result_url(base_url: str, request_id: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        normalized_request_id = str(request_id or "").strip()
        if not base or not normalized_request_id:
            return ""
        if base.endswith("/async-result"):
            return f"{base}/{normalized_request_id}"
        if base.endswith("/v1"):
            return f"{base[:-len('/v1')]}/async-result/{normalized_request_id}"
        return f"{base}/async-result/{normalized_request_id}"

    @staticmethod
    def _is_bigmodel_provider(provider: dict[str, Any]) -> bool:
        base = str(provider.get("base_url") or "").strip().lower()
        return "bigmodel.cn" in base and "/api/paas/v4" in base

    @staticmethod
    def _looks_like_media_url(value: Any) -> bool:
        text = str(value or "").strip()
        return text.startswith(("http://", "https://", "data:"))

    @classmethod
    def _collect_named_values(cls, payload: Any, accepted_keys: set[str]) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()

        def visit(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    normalized_key = str(key or "").strip().lower()
                    if normalized_key in accepted_keys:
                        if normalized_key == "b64_json":
                            raw = str(value or "").strip()
                            if raw:
                                candidate = f"data:image/png;base64,{raw}"
                                if candidate not in seen:
                                    seen.add(candidate)
                                    values.append(candidate)
                            continue
                        if cls._looks_like_media_url(value):
                            candidate = str(value or "").strip()
                            if candidate not in seen:
                                seen.add(candidate)
                                values.append(candidate)
                            continue
                    if isinstance(value, (dict, list)):
                        visit(value)
            elif isinstance(node, list):
                for item in node:
                    visit(item)

        visit(payload)
        return values

    @classmethod
    def _extract_image_artifacts_from_payload(
        cls,
        payload: dict[str, Any],
        *,
        provider_id: str,
        model_name: str,
    ) -> list[dict[str, Any]]:
        image_urls = cls._collect_named_values(
            payload,
            {"url", "image_url", "content_url", "result_url", "b64_json"},
        )
        preview_urls = cls._collect_named_values(
            payload,
            {"preview_url", "thumbnail_url", "cover_url", "cover_image_url", "image_url", "url", "b64_json"},
        )
        artifacts: list[dict[str, Any]] = []
        for index, content_url in enumerate(image_urls):
            preview_url = preview_urls[index] if index < len(preview_urls) else content_url
            artifacts.append(
                {
                    "asset_type": "image",
                    "title": f"{model_name or provider_id} 图片 {index + 1}",
                    "preview_url": preview_url,
                    "content_url": content_url,
                    "mime_type": "image/png" if content_url.startswith("data:image/") else "",
                    "metadata": {
                        "provider_id": provider_id,
                        "model_name": model_name,
                    },
                }
            )
        return artifacts

    @classmethod
    def _extract_video_artifacts_from_payload(
        cls,
        payload: dict[str, Any],
        *,
        provider_id: str,
        model_name: str,
    ) -> list[dict[str, Any]]:
        video_urls = cls._collect_named_values(
            payload,
            {"video_url", "content_url", "result_url", "url", "source_url"},
        )
        preview_urls = cls._collect_named_values(
            payload,
            {"cover_image_url", "cover_url", "thumbnail_url", "preview_url", "image_url"},
        )
        filtered_video_urls = [
            item
            for item in video_urls
            if item.startswith("data:video/")
            or any(item.lower().split("?", 1)[0].endswith(ext) for ext in (".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"))
        ]
        artifacts: list[dict[str, Any]] = []
        for index, content_url in enumerate(filtered_video_urls):
            preview_url = preview_urls[index] if index < len(preview_urls) else ""
            artifacts.append(
                {
                    "asset_type": "video",
                    "title": f"{model_name or provider_id} 视频 {index + 1}",
                    "preview_url": preview_url,
                    "content_url": content_url,
                    "mime_type": "video/mp4",
                    "metadata": {
                        "provider_id": provider_id,
                        "model_name": model_name,
                    },
                }
            )
        return artifacts

    @staticmethod
    def _extract_error_message(payload: dict[str, Any]) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "").strip()
        if isinstance(error, str):
            return error.strip()
        return str(payload.get("message") or payload.get("detail") or payload.get("task_status") or "").strip()

    @staticmethod
    def _compact_error_text(value: Any, limit: int = 300) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[:limit]

    @classmethod
    def _summarize_http_error_response(
        cls,
        raw: bytes | str,
        *,
        content_type: str = "",
    ) -> tuple[str, str]:
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="ignore")
        else:
            text = str(raw or "")

        diagnostic = cls._compact_error_text(text, limit=500)
        normalized_content_type = str(content_type or "").strip().lower()
        lowered = diagnostic.lower()
        looks_like_html = (
            "text/html" in normalized_content_type
            or lowered.startswith("<!doctype html")
            or lowered.startswith("<html")
        )
        if looks_like_html:
            title_match = re.search(
                r"<title[^>]*>(.*?)</title>",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            title = (
                cls._compact_error_text(title_match.group(1), limit=120)
                if title_match
                else ""
            )
            summary = "upstream returned an HTML error page"
            if title:
                summary = f"{summary} ({title})"
            return summary, diagnostic

        if "json" in normalized_content_type or text.lstrip().startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                extracted = cls._extract_error_message(payload)
                if extracted:
                    return cls._compact_error_text(extracted), diagnostic

        if diagnostic:
            return cls._compact_error_text(diagnostic), diagnostic
        return "upstream returned an empty error response", diagnostic

    @staticmethod
    def _normalize_bigmodel_video_size(aspect_ratio: str) -> str:
        normalized = str(aspect_ratio or "").strip()
        return {
            "16:9": "1920x1080",
            "9:16": "1080x1920",
            "1:1": "1024x1024",
            "4:3": "1440x1080",
            "3:4": "1080x1440",
        }.get(normalized, "1920x1080")

    def _poll_async_media_result(
        self,
        provider: dict[str, Any],
        request_id: str,
        *,
        provider_id: str,
        model_name: str,
        asset_type: str,
        timeout_sec: int = 180,
        poll_interval_sec: int = 3,
    ) -> list[dict[str, Any]]:
        endpoint = self._build_async_result_url(str(provider.get("base_url") or ""), request_id)
        if not endpoint:
            raise RuntimeError("provider async result endpoint is empty")
        headers = self._build_headers(provider)
        deadline = time.monotonic() + max(15, timeout_sec)
        last_payload: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last_payload = self._request_json("GET", endpoint, headers, timeout=30)
            artifacts = (
                self._extract_video_artifacts_from_payload(last_payload, provider_id=provider_id, model_name=model_name)
                if asset_type == "video"
                else self._extract_image_artifacts_from_payload(last_payload, provider_id=provider_id, model_name=model_name)
            )
            if artifacts:
                return artifacts
            task_status = str(
                last_payload.get("task_status")
                or last_payload.get("status")
                or last_payload.get("state")
                or ""
            ).strip().upper()
            if task_status in {"SUCCESS", "SUCCEEDED", "FAILED", "FAILURE", "ERROR", "CANCELED", "CANCELLED"}:
                break
            time.sleep(max(1, poll_interval_sec))
        error_message = self._extract_error_message(last_payload) or f"{asset_type} generation timed out"
        raise RuntimeError(error_message)

    def _generate_media_artifacts_sync(
        self,
        provider: dict[str, Any],
        *,
        provider_id: str,
        model_name: str,
        prompt: str,
        image_urls: list[str] | None = None,
        image_size: str = "",
        video_aspect_ratio: str = "",
        video_duration_seconds: int | None = None,
    ) -> list[dict[str, Any]]:
        model_config = self.get_model_config(provider, model_name) or {}
        parameter_mode = str(model_config.get("chat_parameter_mode") or "text").strip().lower()
        if parameter_mode == "image":
            endpoint = self._build_images_generation_url(str(provider.get("base_url") or ""))
            normalized_image_urls = [
                str(item or "").strip()
                for item in (image_urls or [])
                if str(item or "").strip()
            ]
            effective_prompt = str(prompt or "").strip()
            if normalized_image_urls:
                effective_prompt = (
                    f"{effective_prompt}\n\n"
                    f"参考图输入：当前已提供 {len(normalized_image_urls)} 张角色参考图，请尽量保持同一人物形象、服装与发型一致。"
                ).strip()
            body = {
                "model": model_name,
                "prompt": effective_prompt,
            }
            if str(image_size or "").strip():
                body["size"] = str(image_size or "").strip()
            if normalized_image_urls and not self._is_bigmodel_provider(provider):
                body["image_urls"] = normalized_image_urls
            payload = self._request_json("POST", endpoint, self._build_headers(provider), body=body, timeout=120)
            artifacts = self._extract_image_artifacts_from_payload(payload, provider_id=provider_id, model_name=model_name)
            if artifacts:
                return artifacts
            request_id = str(payload.get("request_id") or payload.get("id") or "").strip()
            if request_id:
                return self._poll_async_media_result(
                    provider,
                    request_id,
                    provider_id=provider_id,
                    model_name=model_name,
                    asset_type="image",
                    timeout_sec=120,
                    poll_interval_sec=2,
                )
            raise RuntimeError(self._extract_error_message(payload) or "image generation returned no artifact")

        if parameter_mode == "video":
            endpoint = self._build_videos_generation_url(str(provider.get("base_url") or ""))
            body = {
                "model": model_name,
                "prompt": prompt,
                "size": self._normalize_bigmodel_video_size(video_aspect_ratio),
            }
            if video_duration_seconds:
                body["duration"] = int(video_duration_seconds)
            payload = self._request_json("POST", endpoint, self._build_headers(provider), body=body, timeout=60)
            artifacts = self._extract_video_artifacts_from_payload(payload, provider_id=provider_id, model_name=model_name)
            if artifacts:
                return artifacts
            request_id = str(payload.get("request_id") or payload.get("id") or "").strip()
            if request_id:
                return self._poll_async_media_result(
                    provider,
                    request_id,
                    provider_id=provider_id,
                    model_name=model_name,
                    asset_type="video",
                    timeout_sec=240,
                    poll_interval_sec=5,
                )
            raise RuntimeError(self._extract_error_message(payload) or "video generation returned no artifact")

        raise ValueError(f"model {model_name} is not an image/video generation model")

    async def generate_media_artifacts(
        self,
        provider_id: str,
        model_name: str,
        prompt: str,
        *,
        owner_username: str = "",
        include_all: bool = False,
        image_urls: list[str] | None = None,
        image_size: str = "",
        video_aspect_ratio: str = "",
        video_duration_seconds: int | None = None,
    ) -> list[dict[str, Any]]:
        provider = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=True,
        )
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")
        chosen_model = str(model_name or "").strip() or self._pick_default_model(provider)
        if not chosen_model:
            raise ValueError("model_name is required")
        return await run_in_threadpool(
            self._generate_media_artifacts_sync,
            provider,
            provider_id=provider_id,
            model_name=chosen_model,
            prompt=str(prompt or "").strip(),
            image_urls=[str(item or "").strip() for item in (image_urls or []) if str(item or "").strip()],
            image_size=str(image_size or "").strip(),
            video_aspect_ratio=str(video_aspect_ratio or "").strip(),
            video_duration_seconds=video_duration_seconds,
        )

    def _list_audio_voices_sync(self, provider: dict[str, Any]) -> list[dict[str, Any]]:
        if not self._is_bigmodel_provider(provider):
            raise ValueError("当前仅支持智谱 BigModel 音色列表接口")
        payload = self._request_json(
            "GET",
            self._build_voice_list_url(str(provider.get("base_url") or "")),
            self._build_headers(provider),
            timeout=30,
        )
        items = payload.get("voice_list")
        if not isinstance(items, list):
            return []
        voices: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            voice_id = str(item.get("voice") or "").strip()
            if not voice_id:
                continue
            voices.append(
                {
                    "voice": voice_id,
                    "voice_name": str(item.get("voice_name") or voice_id).strip(),
                    "voice_type": str(item.get("voice_type") or "").strip(),
                    "download_url": str(item.get("download_url") or "").strip(),
                    "create_time": str(item.get("create_time") or "").strip(),
                }
            )
        return voices

    def _create_audio_voice_clone_sync(
        self,
        provider: dict[str, Any],
        *,
        model_name: str,
        voice_name: str,
        input_text: str,
        transcript_text: str,
        sample_file_path: str,
        sample_filename: str,
        sample_mime_type: str = "",
    ) -> dict[str, Any]:
        if not self._is_bigmodel_provider(provider):
            raise ValueError("当前仅支持智谱 BigModel 音色复刻接口")
        headers = self._build_headers(provider)
        with open(sample_file_path, "rb") as handle:
            upload_payload = self._request_multipart_json(
                "POST",
                self._build_files_url(str(provider.get("base_url") or "")),
                headers,
                files={
                    "file": (
                        sample_filename,
                        handle,
                        sample_mime_type or "application/octet-stream",
                    ),
                },
                data={"purpose": "voice-clone-input"},
                timeout=120,
            )
        uploaded_file_id = str(upload_payload.get("id") or "").strip()
        if not uploaded_file_id:
            raise RuntimeError("音色复刻示例音频上传失败")
        request_id = f"voice-clone-{int(time.time() * 1000)}"
        clone_payload = self._request_json(
            "POST",
            self._build_voice_clone_url(str(provider.get("base_url") or "")),
            headers,
            body={
                "model": model_name,
                "voice_name": voice_name,
                "input": input_text,
                "file_id": uploaded_file_id,
                "text": transcript_text,
                "request_id": request_id,
            },
            timeout=120,
        )
        voice_id = str(clone_payload.get("voice") or "").strip()
        if not voice_id:
            raise RuntimeError(self._extract_error_message(clone_payload) or "音色复刻失败")
        return {
            **clone_payload,
            "input_file_id": uploaded_file_id,
            "input_file_purpose": str(upload_payload.get("purpose") or "").strip(),
        }

    def _delete_audio_voice_sync(self, provider: dict[str, Any], voice_id: str) -> dict[str, Any]:
        if not self._is_bigmodel_provider(provider):
            raise ValueError("当前仅支持智谱 BigModel 删除音色接口")
        return self._request_json(
            "POST",
            self._build_voice_delete_url(str(provider.get("base_url") or "")),
            self._build_headers(provider),
            body={
                "voice": str(voice_id or "").strip(),
                "request_id": f"voice-delete-{int(time.time() * 1000)}",
            },
            timeout=45,
        )

    def _generate_audio_speech_sync(
        self,
        provider: dict[str, Any],
        *,
        model_name: str,
        text: str,
        voice: str,
        response_format: str,
        speed: float,
    ) -> dict[str, Any]:
        raw, content_type = self._request_bytes(
            "POST",
            self._build_audio_speech_url(str(provider.get("base_url") or "")),
            self._build_headers(provider),
            body={
                "model": model_name,
                "input": text,
                "voice": voice,
                "response_format": response_format,
                "speed": speed,
            },
            timeout=120,
        )
        if not raw:
            raise RuntimeError("音频生成结果为空")
        return {
            "audio_bytes": raw,
            "content_type": content_type or ("audio/wav" if response_format == "wav" else "audio/pcm"),
        }

    @staticmethod
    def _extract_transcription_text(payload: dict[str, Any]) -> str:
        text = str(payload.get("text") or "").strip()
        if text:
            return text
        data = payload.get("data")
        if isinstance(data, dict):
            nested_text = str(data.get("text") or data.get("content") or "").strip()
            if nested_text:
                return nested_text
        segments = payload.get("segments")
        if isinstance(segments, list):
            normalized_segments = [
                str(item.get("text") or "").strip()
                for item in segments
                if isinstance(item, dict) and str(item.get("text") or "").strip()
            ]
            if normalized_segments:
                return " ".join(normalized_segments).strip()
        return ""

    def _transcribe_audio_sync(
        self,
        provider: dict[str, Any],
        *,
        model_name: str,
        file_path: str,
        filename: str,
        mime_type: str,
        language: str,
        prompt: str,
    ) -> dict[str, Any]:
        endpoint = self._build_audio_transcriptions_url(str(provider.get("base_url") or ""))
        if not endpoint:
            raise RuntimeError("provider transcription endpoint is empty")
        with open(file_path, "rb") as handle:
            payload = self._request_multipart_json(
                "POST",
                endpoint,
                self._build_headers(provider),
                files={
                    "file": (
                        filename,
                        handle,
                        mime_type or "application/octet-stream",
                    ),
                },
                data={
                    "model": model_name,
                    "response_format": "json",
                    **({"language": language} if language else {}),
                    **({"prompt": prompt} if prompt else {}),
                },
                timeout=120,
            )
        text = self._extract_transcription_text(payload)
        if not text:
            raise RuntimeError(self._extract_error_message(payload) or "语音转写结果为空")
        return {
            "text": text,
            "raw": payload,
        }

    async def list_audio_voices(
        self,
        provider_id: str,
        *,
        owner_username: str = "",
        include_all: bool = False,
    ) -> list[dict[str, Any]]:
        provider = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=True,
        )
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")
        return await run_in_threadpool(self._list_audio_voices_sync, provider)

    async def create_audio_voice_clone(
        self,
        provider_id: str,
        model_name: str,
        *,
        voice_name: str,
        input_text: str,
        transcript_text: str,
        sample_file_path: str,
        sample_filename: str,
        sample_mime_type: str = "",
        owner_username: str = "",
        include_all: bool = False,
    ) -> dict[str, Any]:
        provider = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=True,
        )
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")
        chosen_model = str(model_name or "").strip() or self._pick_default_model(provider)
        if not chosen_model:
            raise ValueError("model_name is required")
        return await run_in_threadpool(
            self._create_audio_voice_clone_sync,
            provider,
            model_name=chosen_model,
            voice_name=str(voice_name or "").strip(),
            input_text=str(input_text or "").strip(),
            transcript_text=str(transcript_text or "").strip(),
            sample_file_path=str(sample_file_path or "").strip(),
            sample_filename=str(sample_filename or "").strip(),
            sample_mime_type=str(sample_mime_type or "").strip(),
        )

    async def delete_audio_voice(
        self,
        provider_id: str,
        voice_id: str,
        *,
        owner_username: str = "",
        include_all: bool = False,
    ) -> dict[str, Any]:
        provider = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=True,
        )
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")
        return await run_in_threadpool(
            self._delete_audio_voice_sync,
            provider,
            str(voice_id or "").strip(),
        )

    async def generate_audio_speech(
        self,
        provider_id: str,
        model_name: str,
        *,
        text: str,
        voice: str,
        response_format: str = "wav",
        speed: float = 1.0,
        owner_username: str = "",
        include_all: bool = False,
    ) -> dict[str, Any]:
        provider = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=True,
        )
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")
        chosen_model = str(model_name or "").strip() or self._pick_default_model(provider)
        if not chosen_model:
            raise ValueError("model_name is required")
        return await run_in_threadpool(
            self._generate_audio_speech_sync,
            provider,
            model_name=chosen_model,
            text=str(text or "").strip(),
            voice=str(voice or "").strip(),
            response_format=str(response_format or "wav").strip() or "wav",
            speed=max(0.5, min(float(speed or 1.0), 2.0)),
        )

    async def transcribe_audio(
        self,
        provider_id: str,
        model_name: str,
        *,
        file_path: str,
        filename: str,
        mime_type: str = "",
        language: str = "",
        prompt: str = "",
        owner_username: str = "",
        include_all: bool = False,
    ) -> dict[str, Any]:
        provider = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
            include_shared=True,
        )
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")
        chosen_model = str(model_name or "").strip() or self._pick_default_model(provider)
        if not chosen_model:
            raise ValueError("model_name is required")
        return await run_in_threadpool(
            self._transcribe_audio_sync,
            provider,
            model_name=chosen_model,
            file_path=str(file_path or "").strip(),
            filename=str(filename or "").strip(),
            mime_type=str(mime_type or "").strip(),
            language=str(language or "").strip(),
            prompt=str(prompt or "").strip(),
        )

    @staticmethod
    def _build_headers(provider: dict[str, Any]) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = str(provider.get("api_key") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        extra_headers = provider.get("extra_headers") or {}
        if isinstance(extra_headers, dict):
            for key, value in extra_headers.items():
                name = str(key or "").strip()
                if not name:
                    continue
                headers[name] = str(value or "").strip()
        return headers

    @staticmethod
    def _request_bytes(
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> tuple[bytes, str]:
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.request(
                    method.upper(),
                    url,
                    headers=headers,
                    json=body if body is not None else None,
                    timeout=timeout,
                ) as resp:
                    raw = resp.content or b""
                    if resp.status_code >= 400:
                        summary, _ = LlmProviderService._summarize_http_error_response(
                            raw,
                            content_type=str(resp.headers.get("Content-Type") or "").strip(),
                        )
                        raise RuntimeError(f"LLM request failed: HTTP {resp.status_code} {summary}")
                    return raw, str(resp.headers.get("Content-Type") or "").strip()
        except requests.RequestException as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

    @staticmethod
    def _request_multipart_json(
        method: str,
        url: str,
        headers: dict[str, str],
        *,
        files: dict[str, Any],
        data: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> dict[str, Any]:
        request_headers = {
            key: value
            for key, value in headers.items()
            if str(key or "").strip().lower() != "content-type"
        }
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.request(
                    method.upper(),
                    url,
                    headers=request_headers,
                    files=files,
                    data=data or None,
                    timeout=timeout,
                ) as resp:
                    raw = resp.text or ""
                    if resp.status_code >= 400:
                        summary, _ = LlmProviderService._summarize_http_error_response(
                            raw,
                            content_type=str(resp.headers.get("Content-Type") or "").strip(),
                        )
                        raise RuntimeError(f"LLM request failed: HTTP {resp.status_code} {summary}")
        except requests.RequestException as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM response is not valid JSON: {raw[:300]}") from exc

    @staticmethod
    def _request_json(method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None = None, timeout: int = 45) -> dict[str, Any]:
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.request(
                    method.upper(),
                    url,
                    headers=headers,
                    json=body if body is not None else None,
                    timeout=timeout,
                ) as resp:
                    raw = resp.text or ""
                    if resp.status_code >= 400:
                        summary, _ = LlmProviderService._summarize_http_error_response(
                            raw,
                            content_type=str(resp.headers.get("Content-Type") or "").strip(),
                        )
                        raise RuntimeError(f"LLM request failed: HTTP {resp.status_code} {summary}")
        except requests.RequestException as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        if not raw.strip():
            return {}

        # 检测流式响应（SSE 格式）
        if raw.strip().startswith("data:"):
            content = LlmProviderService._parse_sse_content(raw)
            if content:
                return {"choices": [{"message": {"content": content}}]}
            raise RuntimeError(f"LLM SSE response parse failed: {raw[:300]}")

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM response is not valid JSON: {raw[:300]}") from exc

    @staticmethod
    def _request_text(
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
        timeout: int = 60,
        stream: bool = False,
    ) -> str:
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.request(
                    method.upper(),
                    url,
                    headers=headers,
                    json=body if body is not None else None,
                    timeout=timeout,
                    stream=stream,
                ) as resp:
                    if resp.status_code >= 400:
                        summary, _ = LlmProviderService._summarize_http_error_response(
                            resp.text or "",
                            content_type=str(resp.headers.get("Content-Type") or "").strip(),
                        )
                        raise RuntimeError(f"LLM request failed: HTTP {resp.status_code} {summary}")
                    if not stream:
                        return resp.text or ""
                    lines: list[str] = []
                    for line in resp.iter_lines(decode_unicode=True):
                        if line is None:
                            continue
                        if isinstance(line, bytes):
                            lines.append(line.decode("utf-8", errors="ignore"))
                        else:
                            lines.append(str(line))
                    return "\n".join(lines)
        except requests.RequestException as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

    @staticmethod
    def _extract_content(chat_payload: dict[str, Any]) -> str:
        def _extract_text_parts(value: Any) -> str:
            if isinstance(value, list):
                parts: list[str] = []
                for item in value:
                    if isinstance(item, dict):
                        text = str(item.get("text") or item.get("content") or "")
                        if text:
                            parts.append(text)
                    else:
                        parts.append(str(item))
                return "".join(parts).strip()
            return str(value or "").strip()

        output_text = str(chat_payload.get("output_text") or "").strip()
        if output_text:
            return output_text

        output = chat_payload.get("output") or []
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content_list = item.get("content") or []
                if not isinstance(content_list, list):
                    continue
                for part in content_list:
                    if not isinstance(part, dict):
                        continue
                    text = str(part.get("text") or "").strip()
                    if text:
                        parts.append(text)
            if parts:
                return "".join(parts).strip()

        choices = chat_payload.get("choices") or []
        if not choices:
            return ""
        delta = (choices[0] or {}).get("delta") or {}
        delta_content = delta.get("content")
        delta_text = _extract_text_parts(delta_content)
        if delta_text:
            return delta_text
        reasoning_text = _extract_text_parts(delta.get("reasoning_content"))
        if reasoning_text:
            return reasoning_text
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text") or ""))
                    else:
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return "".join(parts).strip()
        message_text = str(content or "").strip()
        if message_text:
            return message_text
        return _extract_text_parts(message.get("reasoning_content"))

    @staticmethod
    def _parse_sse_content(raw: str) -> str:
        parts: list[str] = []
        for line in str(raw or "").splitlines():
            text = line.strip()
            if not text or not text.startswith("data:"):
                continue
            payload_text = text[5:].strip()
            if not payload_text or payload_text == "[DONE]":
                continue
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                continue
            chunk = LlmProviderService._extract_content(payload)
            if chunk:
                parts.append(chunk)
        return "".join(parts).strip()

    @staticmethod
    def _build_sse_headers(headers: dict[str, str]) -> dict[str, str]:
        merged = dict(headers)
        merged["Accept"] = "text/event-stream"
        merged.setdefault("Cache-Control", "no-cache")
        merged.setdefault("Connection", "keep-alive")
        return merged

    @staticmethod
    def _extract_json_text(content: str) -> str:
        text = str(content or "").strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1]
        return text

    def _call_chat_completion_sse(
        self,
        provider: dict[str, Any],
        model_name: str,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        timeout: int,
    ) -> dict[str, Any]:
        endpoint = self._build_chat_completion_url(str(provider.get("base_url") or ""))
        if not endpoint:
            raise ValueError("provider base_url is empty")
        body = {
            "model": model_name,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "max_tokens": max_tokens,
        }
        raw = self._request_text(
            "POST",
            endpoint,
            self._build_sse_headers(self._build_headers(provider)),
            body=body,
            timeout=timeout,
            stream=True,
        )
        text = self._parse_sse_content(raw)
        if text:
            return {"choices": [{"message": {"content": text}}]}
        stripped = str(raw or "").strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"LLM SSE response parse failed: {stripped[:300]}")

    def _call_chat_completion(
        self,
        provider: dict[str, Any],
        model_name: str,
        temperature: float,
        bug: dict[str, Any],
    ) -> dict[str, Any]:
        endpoint = self._build_chat_completion_url(str(provider.get("base_url") or ""))
        if not endpoint:
            raise ValueError("provider base_url is empty")

        bug_payload = {
            "title": bug.get("title") or "",
            "symptom": bug.get("symptom") or "",
            "expected": bug.get("expected") or "",
            "severity": bug.get("severity") or "medium",
            "category": bug.get("category") or "general",
            "session_id": bug.get("session_id") or "",
            "rule_id": bug.get("rule_id") or "",
        }

        system_prompt = (
            "你是规则反馈反思助手。你必须只输出 JSON 对象，不要输出 markdown。"
            "JSON 字段必须包含: bug_type, summary, direct_cause, root_cause, next_action, confidence。"
            "confidence 取值范围 0~1。"
        )
        user_prompt = (
            "请基于以下反馈生成结构化反思，禁止编造不存在的上下文。\n"
            f"反馈数据: {json.dumps(bug_payload, ensure_ascii=False)}"
        )
        return self._call_chat_completion_sse(
            provider=provider,
            model_name=model_name,
            temperature=temperature,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=1024,
            timeout=60,
        )

    def _call_responses(
        self,
        provider: dict[str, Any],
        model_name: str,
        temperature: float,
        bug: dict[str, Any],
    ) -> dict[str, Any]:
        endpoint = self._build_responses_url(str(provider.get("base_url") or ""))
        if not endpoint:
            raise ValueError("provider base_url is empty")

        bug_payload = {
            "title": bug.get("title") or "",
            "symptom": bug.get("symptom") or "",
            "expected": bug.get("expected") or "",
            "severity": bug.get("severity") or "medium",
            "category": bug.get("category") or "general",
            "session_id": bug.get("session_id") or "",
            "rule_id": bug.get("rule_id") or "",
        }

        system_prompt = (
            "你是规则反馈反思助手。你必须只输出 JSON 对象，不要输出 markdown。"
            "JSON 字段必须包含: bug_type, summary, direct_cause, root_cause, next_action, confidence。"
            "confidence 取值范围 0~1。"
        )
        user_prompt = (
            "请基于以下反馈生成结构化反思，禁止编造不存在的上下文。\n"
            f"反馈数据: {json.dumps(bug_payload, ensure_ascii=False)}"
        )

        body = {
            "model": model_name,
            "temperature": temperature,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "max_output_tokens": 512,
        }
        return self._request_json("POST", endpoint, self._build_headers(provider), body=body, timeout=45)

    def _call_model_completion(
        self,
        provider: dict[str, Any],
        model_name: str,
        temperature: float,
        bug: dict[str, Any],
    ) -> dict[str, Any]:
        if self._is_responses_provider(provider):
            return self._call_responses(provider, model_name, temperature, bug)
        return self._call_chat_completion(provider, model_name, temperature, bug)

    def test_provider_connection(
        self,
        provider_id: str,
        model_name: str = "",
        *,
        owner_username: str = "",
        include_all: bool = False,
    ) -> dict[str, Any]:
        provider = self.get_provider_raw(
            provider_id,
            owner_username=owner_username,
            include_all=include_all,
        )
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")

        chosen_model = str(model_name or "").strip() or self._pick_default_model(provider)
        started = time.monotonic()
        models_ok = False
        models_message = "/models 已跳过（SSE 测试模式）"
        model_count = 0

        # Step 1: run a lightweight invocation probe.
        completion_ok = False
        completion_message = "未执行模型调用"
        if chosen_model:
            try:
                if self._is_responses_provider(provider):
                    endpoint = self._build_responses_url(str(provider.get("base_url") or ""))
                    body = {
                        "model": chosen_model,
                        "input": [
                            {
                                "role": "user",
                                "content": [{"type": "input_text", "text": "返回 ok"}],
                            }
                        ],
                        "max_output_tokens": 16,
                    }
                    completion_resp = self._request_json("POST", endpoint, self._build_headers(provider), body=body, timeout=25)
                    text = self._extract_content(completion_resp)
                    completion_ok = True
                    completion_message = f"/responses 可用: {(text or 'ok')[:120]}"
                else:
                    completion_resp = self._call_chat_completion_sse(
                        provider=provider,
                        model_name=chosen_model,
                        temperature=0,
                        system_prompt="你是连通性测试助手。",
                        user_prompt="返回 ok",
                        max_tokens=32,
                        timeout=35,
                    )
                    text = self._extract_content(completion_resp)
                    completion_ok = True
                    completion_message = f"/chat/completions(SSE) 可用: {(text or 'ok')[:120]}"
            except Exception as exc:
                if self._is_responses_provider(provider):
                    completion_message = f"/responses 失败: {exc}"
                else:
                    completion_message = f"/chat/completions(SSE) 失败: {exc}"
        else:
            completion_message = "未指定测试模型，跳过模型调用"

        latency_ms = int((time.monotonic() - started) * 1000)
        reachable = bool(completion_ok)
        if not reachable:
            raise RuntimeError(f"{models_message}; {completion_message}")
        return {
            "provider_id": provider_id,
            "provider_name": provider.get("name") or provider_id,
            "reachable": reachable,
            "models_ok": models_ok,
            "model_count": model_count,
            "model_tested": chosen_model,
            "completion_ok": completion_ok,
            "message": f"{models_message}; {completion_message}",
            "latency_ms": latency_ms,
            "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def reflect_bug(
        self,
        bug: dict[str, Any],
        provider_id: str,
        model_name: str,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        provider = self.get_provider_raw(provider_id)
        if provider is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        if not bool(provider.get("enabled", True)):
            raise ValueError(f"LLM provider {provider_id} is disabled")

        normalized_model = str(model_name or "").strip() or self._pick_default_model(provider)
        if not normalized_model:
            raise ValueError("model_name is required")

        chat_payload = self._call_model_completion(
            provider,
            normalized_model,
            self._clamp_temperature(temperature),
            bug,
        )
        content = self._extract_content(chat_payload)
        reflection_text = self._extract_json_text(content)

        try:
            parsed = json.loads(reflection_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM response content is not JSON object: {content[:300]}") from exc

        if not isinstance(parsed, dict):
            raise RuntimeError("LLM reflection output must be a JSON object")

        summary = str(parsed.get("summary") or "").strip()
        direct_cause = str(parsed.get("direct_cause") or "").strip()
        root_cause = str(parsed.get("root_cause") or "").strip()
        next_action = str(parsed.get("next_action") or "生成规则候选并进入审核").strip() or "生成规则候选并进入审核"
        bug_type = str(parsed.get("bug_type") or "rule_mismatch").strip() or "rule_mismatch"
        confidence = parsed.get("confidence")
        try:
            normalized_confidence = max(0.0, min(float(confidence), 1.0))
        except (TypeError, ValueError):
            normalized_confidence = 0.8

        if not direct_cause:
            direct_cause = "模型未给出直接原因"
        if not root_cause:
            root_cause = "模型未给出根因"

        if not summary:
            summary = f"反馈“{bug.get('title', '')}”存在输出与预期偏差。"

        evidence_refs = []
        if bug.get("session_id"):
            evidence_refs.append({"type": "session", "id": bug["session_id"]})
        if bug.get("rule_id"):
            evidence_refs.append({"type": "rule", "id": bug["rule_id"]})

        return {
            "bug_type": bug_type,
            "direct_cause": direct_cause,
            "root_cause": root_cause,
            "evidence_refs": evidence_refs,
            "confidence": normalized_confidence,
            "provider_id": provider_id,
            "model_name": f"{provider.get('name') or provider_id}/{normalized_model}",
            "reflection_output": {
                "summary": summary,
                "direct_cause": direct_cause,
                "root_cause": root_cause,
                "next_action": next_action,
                "provider": provider.get("name") or provider_id,
                "model": normalized_model,
            },
        }


@lru_cache(maxsize=1)
def get_llm_provider_service() -> LlmProviderService:
    settings = get_settings()
    if settings.core_store_backend != "postgres":
        raise RuntimeError("LLM provider module requires CORE_STORE_BACKEND=postgres")
    return LlmProviderService(LlmProviderStorePostgres(settings.database_url))
