"""Helpers for calling user-owned local connectors."""

from __future__ import annotations

from typing import Any

import httpx

LOCAL_CONNECTOR_PROVIDER_PREFIX = "local-connector:"


def build_local_connector_provider_id(connector_id: str) -> str:
    normalized = str(connector_id or "").strip()
    return f"{LOCAL_CONNECTOR_PROVIDER_PREFIX}{normalized}" if normalized else ""


def parse_local_connector_provider_id(provider_id: str) -> str:
    normalized = str(provider_id or "").strip()
    if not normalized.startswith(LOCAL_CONNECTOR_PROVIDER_PREFIX):
        return ""
    return normalized[len(LOCAL_CONNECTOR_PROVIDER_PREFIX) :].strip()


def connector_base_url(connector: Any) -> str:
    return str(getattr(connector, "advertised_url", "") or "").strip().rstrip("/")


def connector_headers(connector: Any) -> dict[str, str]:
    token = str(getattr(connector, "connector_token", "") or "").strip()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Connector-Token"] = token
    return headers


async def _request_json(
    connector: Any,
    method: str,
    path: str,
    *,
    timeout: float = 10.0,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = connector_base_url(connector)
    if not base_url:
        raise RuntimeError("Local connector is missing advertised_url")
    url = f"{base_url}{path if path.startswith('/') else f'/{path}'}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method.upper(),
            url,
            headers=connector_headers(connector),
            json=json_body,
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
    return payload if isinstance(payload, dict) else {}


async def list_connector_llm_models(connector: Any) -> dict[str, Any]:
    payload = await _request_json(connector, "GET", "/llm/models", timeout=12.0)
    models = [
        str(item or "").strip()
        for item in (payload.get("models") or [])
        if str(item or "").strip()
    ]
    default_model = str(payload.get("default_model") or "").strip()
    if default_model and default_model not in models:
        models = [default_model, *models]
    return {
        "enabled": bool(payload.get("enabled")),
        "base_url": str(payload.get("base_url") or "").strip(),
        "default_model": default_model or (models[0] if models else ""),
        "models": models,
    }


async def probe_connector_workspace(
    connector: Any,
    workspace_path: str,
    sandbox_mode: str = "workspace-write",
) -> dict[str, Any]:
    payload = await _request_json(
        connector,
        "POST",
        "/probe-workspace",
        timeout=12.0,
        json_body={
            "workspace_path": str(workspace_path or "").strip(),
            "sandbox_mode": str(sandbox_mode or "workspace-write").strip()
            or "workspace-write",
        },
    )
    payload["source"] = "local_connector"
    return payload


async def materialize_connector_workspace(
    connector: Any,
    workspace_path: str,
    sandbox_mode: str,
    files: list[dict[str, Any]] | None,
    copies: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload = await _request_json(
        connector,
        "POST",
        "/workspace/materialize",
        timeout=20.0,
        json_body={
            "workspace_path": str(workspace_path or "").strip(),
            "sandbox_mode": str(sandbox_mode or "workspace-write").strip()
            or "workspace-write",
            "files": list(files or []),
            "copies": list(copies or []),
        },
    )
    if isinstance(payload.get("workspace_access"), dict):
        payload["workspace_access"]["source"] = "local_connector"
    return payload


async def chat_completion_via_connector(
    connector: Any,
    *,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: int | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": str(model_name or "").strip(),
        "messages": list(messages or []),
        "temperature": float(temperature or 0.0),
        "stream": False,
    }
    if max_tokens is not None:
        body["max_tokens"] = int(max_tokens)
    payload = await _request_json(
        connector,
        "POST",
        "/llm/chat/completions",
        timeout=timeout,
        json_body=body,
    )
    return {
        "content": str(payload.get("content") or "").strip(),
        "model": str(payload.get("model") or model_name or "").strip(),
        "raw": payload.get("raw"),
    }


def connector_agent_available(connector: Any, agent_type: str) -> bool:
    health = getattr(connector, "health", None)
    payload = health if isinstance(health, dict) else {}
    normalized = str(agent_type or "").strip().lower()
    mapping = {
        "codex_cli": "codex_available",
        "claude_cli": "claude_available",
        "gemini_cli": "gemini_available",
    }
    key = mapping.get(normalized)
    return bool(payload.get(key)) if key else False
