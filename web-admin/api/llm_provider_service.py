"""LLM provider service for feedback reflection."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
import requests
from starlette.concurrency import run_in_threadpool

from config import get_settings
from llm_provider_store_pg import LlmProviderStorePostgres

LOCAL_STATIC_PROVIDER_ID = "lmp-local-static-codex"
LOCAL_STATIC_PROVIDER_NAME = "local-static-codex"
LOCAL_STATIC_PROVIDER_TYPE = "openai-compatible"
LOCAL_STATIC_BASE_URL = "https://code.newcli.com/codex/v1"
LOCAL_STATIC_DEFAULT_MODEL = "gpt-5.3-codex"
LOCAL_STATIC_API_KEY = (
    "sk-ant-oat01-X659tZ5JEmzVlwRMBlWrva7D3mjlcvkh_NOp2f6oyWZJylQm2CUHFYREqEHqhW3s5DLxaJxNx6GHmYm4ZVrfMXdYR9lS9AA"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LlmProviderService:
    def __init__(self, store: LlmProviderStorePostgres) -> None:
        self._store = store

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

        models = self._normalize_models(payload.get("models") or [])
        default_model = str(payload.get("default_model") or "").strip()
        if not default_model and models:
            default_model = models[0]

        return {
            "name": name,
            "provider_type": self._normalize_provider_type(payload.get("provider_type")),
            "base_url": base_url,
            "api_key": str(payload.get("api_key") or "").strip(),
            "models": models,
            "default_model": default_model,
            "enabled": bool(payload.get("enabled", True)),
            "extra_headers": self._normalize_headers(payload.get("extra_headers") or {}),
        }

    def _validate_update_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "name" in payload and payload.get("name") is not None:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("name cannot be empty")
            updates["name"] = name
        if "provider_type" in payload and payload.get("provider_type") is not None:
            updates["provider_type"] = self._normalize_provider_type(payload.get("provider_type"))
        if "base_url" in payload and payload.get("base_url") is not None:
            base_url = self._normalize_base_url(str(payload.get("base_url") or ""))
            if not base_url:
                raise ValueError("base_url cannot be empty")
            updates["base_url"] = base_url
        if "api_key" in payload and payload.get("api_key") is not None:
            updates["api_key"] = str(payload.get("api_key") or "").strip()
        if "models" in payload and payload.get("models") is not None:
            updates["models"] = self._normalize_models(payload.get("models"))
        if "default_model" in payload and payload.get("default_model") is not None:
            updates["default_model"] = str(payload.get("default_model") or "").strip()
        if "enabled" in payload and payload.get("enabled") is not None:
            updates["enabled"] = bool(payload.get("enabled"))
        if "extra_headers" in payload and payload.get("extra_headers") is not None:
            updates["extra_headers"] = self._normalize_headers(payload.get("extra_headers"))
        return updates

    @staticmethod
    def _pick_default_model(provider: dict[str, Any]) -> str:
        default_model = str(provider.get("default_model") or "").strip()
        if default_model:
            return default_model
        models = provider.get("models") or []
        return str(models[0]).strip() if models else ""

    def list_providers(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        return self._store.list_providers(include_secret=False, enabled_only=enabled_only)

    def create_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = self._store.create_provider(self._validate_create_payload(payload))
        return self._store.get_provider(provider["id"], include_secret=False) or provider

    def update_provider(self, provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        updates = self._validate_update_payload(payload)
        updated = self._store.patch_provider(provider_id, updates)
        if updated is None:
            raise LookupError(f"LLM provider {provider_id} not found")
        return self._store.get_provider(provider_id, include_secret=False) or updated

    def delete_provider(self, provider_id: str) -> bool:
        return self._store.delete_provider(provider_id)

    def get_provider_raw(self, provider_id: str) -> dict[str, Any] | None:
        return self._store.get_provider(provider_id, include_secret=True)

    def ensure_local_static_provider(self) -> None:
        existing = self._store.get_provider(LOCAL_STATIC_PROVIDER_ID, include_secret=True) or {}
        now = _now_iso()
        provider = {
            "id": LOCAL_STATIC_PROVIDER_ID,
            "name": LOCAL_STATIC_PROVIDER_NAME,
            "provider_type": LOCAL_STATIC_PROVIDER_TYPE,
            "base_url": LOCAL_STATIC_BASE_URL,
            "api_key": LOCAL_STATIC_API_KEY,
            "models": [LOCAL_STATIC_DEFAULT_MODEL],
            "default_model": LOCAL_STATIC_DEFAULT_MODEL,
            "enabled": True,
            "extra_headers": {},
            "created_at": str(existing.get("created_at") or now),
            "updated_at": now,
        }
        self._store.save_provider(provider)

    def get_reflection_config(self, project_id: str, employee_id: str) -> dict[str, Any] | None:
        return self._store.get_reflection_config(project_id, employee_id)

    def upsert_reflection_config(
        self,
        project_id: str,
        employee_id: str,
        provider_id: str,
        model_name: str = "",
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if not employee_id:
            raise ValueError("employee_id is required")
        provider = self.get_provider_raw(provider_id)
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

    def list_reflection_options(self) -> dict[str, Any]:
        providers = self.list_providers(enabled_only=True)
        options: list[dict[str, Any]] = []
        for provider in providers:
            provider_id = str(provider.get("id") or "").strip()
            provider_name = str(provider.get("name") or "").strip() or provider_id
            default_model = str(provider.get("default_model") or "").strip()
            models = self._normalize_models(provider.get("models") or [])
            if default_model and default_model not in models:
                models = [default_model, *models]
            for model in models:
                options.append(
                    {
                        "provider_id": provider_id,
                        "provider_name": provider_name,
                        "provider_type": str(provider.get("provider_type") or ""),
                        "model_name": model,
                        "is_default": model == default_model,
                    }
                )
        return {"providers": providers, "options": options}

    def resolve_reflection_target(
        self,
        project_id: str,
        employee_id: str,
        preferred_provider_id: str = "",
        preferred_model_name: str = "",
        preferred_temperature: float | None = None,
    ) -> dict[str, Any] | None:
        provider_id = str(preferred_provider_id or "").strip()
        model_name = str(preferred_model_name or "").strip()
        temperature = self._clamp_temperature(preferred_temperature if preferred_temperature is not None else 0.2)

        if provider_id:
            provider = self.get_provider_raw(provider_id)
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
            fallback_provider = self.get_provider_raw(LOCAL_STATIC_PROVIDER_ID)
            if fallback_provider and bool(fallback_provider.get("enabled", True)):
                chosen_model = model_name or self._pick_default_model(fallback_provider)
                if chosen_model:
                    return {
                        "provider": fallback_provider,
                        "provider_id": LOCAL_STATIC_PROVIDER_ID,
                        "model_name": chosen_model,
                        "temperature": temperature,
                        "from_config": False,
                    }
            return None

        cfg_provider_id = str(config.get("provider_id") or "").strip()
        provider = self.get_provider_raw(cfg_provider_id)
        if provider is None or not bool(provider.get("enabled", True)):
            fallback_provider = self.get_provider_raw(LOCAL_STATIC_PROVIDER_ID)
            if fallback_provider and bool(fallback_provider.get("enabled", True)):
                chosen_model = model_name or self._pick_default_model(fallback_provider)
                if chosen_model:
                    return {
                        "provider": fallback_provider,
                        "provider_id": LOCAL_STATIC_PROVIDER_ID,
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
        max_tokens: int,
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
                "max_output_tokens": normalized_max_tokens,
            }
            payload = self._request_json("POST", endpoint, self._build_headers(provider), body=body, timeout=timeout)
        else:
            endpoint = self._build_chat_completion_url(str(provider.get("base_url") or ""))
            if not endpoint:
                raise ValueError("provider base_url is empty")
            body = {
                "model": chosen_model,
                "temperature": normalized_temperature,
                "messages": normalized_messages,
                "max_tokens": normalized_max_tokens,
                "stream": False,
            }
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
        max_tokens: int = 1024,
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
        }
        if tools:
            body["tools"] = tools

        async for chunk in self._stream_request(endpoint, self._build_headers(provider), body, timeout):
            yield chunk

    @staticmethod
    async def _stream_request(url: str, headers: dict[str, str], body: dict[str, Any], timeout: int = 120):
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

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    error_text = await resp.aread()
                    raise RuntimeError(f"LLM stream request failed: HTTP {resp.status_code} {error_text.decode()[:300]}")

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
        if base.endswith("/chat/completions"):
            return f"{base[:-len('/chat/completions')]}/models"
        return f"{base}/v1/models"

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
    def _request_json(method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None = None, timeout: int = 45) -> dict[str, Any]:
        try:
            with requests.request(
                method.upper(),
                url,
                headers=headers,
                json=body if body is not None else None,
                timeout=timeout,
            ) as resp:
                raw = resp.text or ""
                if resp.status_code >= 400:
                    raise RuntimeError(f"LLM request failed: HTTP {resp.status_code} {raw[:300]}")
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
            with requests.request(
                method.upper(),
                url,
                headers=headers,
                json=body if body is not None else None,
                timeout=timeout,
                stream=stream,
            ) as resp:
                if resp.status_code >= 400:
                    raise RuntimeError(f"LLM request failed: HTTP {resp.status_code} {(resp.text or '')[:300]}")
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
        if isinstance(delta_content, list):
            parts: list[str] = []
            for item in delta_content:
                if isinstance(item, dict):
                    text = str(item.get("text") or "")
                    if text:
                        parts.append(text)
                else:
                    parts.append(str(item))
            if parts:
                return "".join(parts).strip()
        if isinstance(delta_content, str) and delta_content.strip():
            return delta_content.strip()
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
        return str(content or "").strip()

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

    def test_provider_connection(self, provider_id: str, model_name: str = "") -> dict[str, Any]:
        provider = self.get_provider_raw(provider_id)
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
    service = LlmProviderService(LlmProviderStorePostgres(settings.database_url))
    service.ensure_local_static_provider()
    return service
