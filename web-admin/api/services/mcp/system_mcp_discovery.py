"""System-level MCP server discovery helpers."""

from __future__ import annotations

import json
import secrets
from typing import Any
from urllib.parse import urlparse

import requests

from stores.json.system_config_store import normalize_system_mcp_config


def _normalize_url_for_match(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    host = str(parsed.netloc or "").strip().lower()
    path = str(parsed.path or "").strip().rstrip("/").lower()
    return f"{host}{path}"


_PROMPTS_CHAT_MATCHERS = {
    "prompts.chat/api/mcp",
}


def _prompts_chat_fallback_manifest(url: str) -> dict[str, Any]:
    return {
        "provider": "prompts.chat",
        "source": "documentation_fallback",
        "url": url,
        "tools": [
            {"type": "tool", "name": "search_prompts", "description": "Search for AI prompts by keyword."},
            {"type": "tool", "name": "get_prompt", "description": "Get a prompt by ID with variable elicitation support."},
            {"type": "tool", "name": "save_prompt", "description": "Save a new prompt (requires API key authentication)."},
            {"type": "tool", "name": "improve_prompt", "description": "Transform a basic prompt into a well-structured prompt using AI."},
            {"type": "tool", "name": "save_skill", "description": "Save a new Agent Skill with multiple files (requires API key authentication)."},
            {"type": "tool", "name": "add_file_to_skill", "description": "Add a file to an existing Agent Skill (requires API key authentication)."},
            {"type": "tool", "name": "update_skill_file", "description": "Update an existing file in an Agent Skill (requires API key authentication)."},
            {"type": "tool", "name": "remove_file_from_skill", "description": "Remove a file from an existing Agent Skill (requires API key authentication)."},
            {"type": "tool", "name": "get_skill", "description": "Get an Agent Skill by ID with all its files."},
            {"type": "tool", "name": "search_skills", "description": "Search for Agent Skills by keyword."},
        ],
        "prompts": [
            {
                "type": "prompt",
                "name": "public prompts catalog",
                "description": "All public prompts are available through prompts/list and prompts/get.",
            }
        ],
        "resources": [],
        "message": "实时探测失败，当前展示的是 prompts.chat 文档声明的能力。",
    }


def _builtin_manifest(server_name: str, url: str) -> dict[str, Any] | None:
    normalized_name = str(server_name or "").strip().lower()
    normalized_url = _normalize_url_for_match(url)
    if normalized_name in {"prompts.chat", "prompts-chat"} or normalized_url in _PROMPTS_CHAT_MATCHERS:
        return _prompts_chat_fallback_manifest(url)
    return None


def _shorten_text(value: object, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _parse_sse_json_payload(body: str) -> dict[str, Any]:
    blocks = [block.strip() for block in str(body or "").split("\n\n") if block.strip()]
    for block in blocks:
        data_lines: list[str] = []
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("data:"):
                data_lines.append(stripped[5:].strip())
        if not data_lines:
            continue
        payload = "\n".join(part for part in data_lines if part)
        if not payload:
            continue
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError("event-stream 中未找到可解析的 JSON data")


def _parse_rpc_body(body: str, content_type: str) -> dict[str, Any]:
    normalized_type = str(content_type or "").lower()
    text = str(body or "").strip()
    if "text/event-stream" in normalized_type:
        return _parse_sse_json_payload(text)
    if not text:
        raise RuntimeError("响应体为空")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("JSON-RPC 响应不是对象")
    return parsed


def _build_meta(response: requests.Response) -> dict[str, Any]:
    return {
        "status_code": int(response.status_code),
        "content_type": str(response.headers.get("content-type") or "").strip(),
        "body_preview": _shorten_text(response.text, 240),
        "session_id": str(response.headers.get("mcp-session-id") or "").strip(),
    }


def _rpc_request(
    url: str,
    method: str,
    params: dict[str, Any] | None = None,
    timeout_sec: int = 12,
    extra_headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    headers = {
        "Accept": "application/json, text/event-stream;q=0.9, */*;q=0.8",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    response = requests.post(
        url,
        json={
            "jsonrpc": "2.0",
            "id": f"system-{secrets.token_hex(4)}",
            "method": method,
            "params": params or {},
        },
        headers=headers,
        timeout=(3, timeout_sec),
    )

    meta = _build_meta(response)

    if int(response.status_code) >= 400:
        raise RuntimeError(
            f"HTTP {response.status_code}，content-type={meta['content_type'] or '-'}，响应片段：{meta['body_preview'] or '-'}"
        )

    try:
        data = _parse_rpc_body(response.text, meta["content_type"])
    except Exception as exc:
        raise RuntimeError(
            f"返回内容不是 JSON，content-type={meta['content_type'] or '-'}，"
            f"响应片段：{meta['body_preview'] or '-'}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError("Invalid JSON-RPC response body")
    if data.get("error"):
        error = data["error"]
        if isinstance(error, dict):
            raise RuntimeError(str(error.get("message") or error))
        raise RuntimeError(str(error))
    return data, meta


def _rpc_notify(
    url: str,
    method: str,
    params: dict[str, Any] | None = None,
    timeout_sec: int = 12,
    extra_headers: dict[str, str] | None = None,
) -> None:
    headers = {
        "Accept": "application/json, text/event-stream;q=0.9, */*;q=0.8",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    requests.post(
        url,
        json={
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        },
        headers=headers,
        timeout=(3, timeout_sec),
    )


def _extract_skill_items(values: object, skill_type: str) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    items: list[dict[str, str]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("uri") or item.get("id") or "").strip()
        if not name:
            continue
        description = str(item.get("description") or item.get("title") or "").strip()
        items.append(
            {
                "type": skill_type,
                "name": name,
                "description": description,
            }
        )
    return items


def _probe_initialize(url: str, timeout_sec: int = 12) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    payload, meta = _rpc_request(
        url,
        "initialize",
        params={
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "ai-employee-factory",
                "version": "1.0.0",
            },
        },
        timeout_sec=timeout_sec,
    )
    headers: dict[str, str] = {}
    if meta.get("session_id"):
        headers["mcp-session-id"] = str(meta["session_id"])
    try:
        _rpc_notify(url, "notifications/initialized", timeout_sec=timeout_sec, extra_headers=headers)
    except Exception:
        pass
    return payload, meta, headers


def _supports_capability(capabilities: object, key: str) -> bool | None:
    if not isinstance(capabilities, dict):
        return None
    if key not in capabilities:
        return False
    value = capabilities.get(key)
    if isinstance(value, dict):
        return True
    return bool(value)


def _discover_server_skills(server_name: str, server_config: object, timeout_sec: int = 12) -> dict[str, Any]:
    config = dict(server_config) if isinstance(server_config, dict) else {}
    url = str(config.get("url") or "").strip()
    enabled = bool(config.get("enabled", True))
    result: dict[str, Any] = {
        "name": server_name,
        "url": url,
        "enabled": enabled,
        "tools": [],
        "prompts": [],
        "resources": [],
        "skills": [],
        "summary": "未配置可探测的 URL",
        "errors": [],
        "checks": [],
        "source": "runtime_probe",
        "notice": "",
        "capabilities": {},
    }

    if not url:
        result["errors"] = ["当前仅支持通过 url 探测远程 MCP 服务"]
        return result

    if not enabled:
        result["summary"] = "已停用"
        result["notice"] = "该 MCP 服务已在系统配置中停用，不会参与能力探测或工具注入。"
        return result

    errors: list[str] = []
    extra_headers: dict[str, str] = {}
    capabilities: dict[str, Any] = {}

    try:
        init_payload, init_meta, extra_headers = _probe_initialize(url, timeout_sec=timeout_sec)
        init_result = init_payload.get("result")
        capabilities = dict(init_result.get("capabilities") or {}) if isinstance(init_result, dict) else {}
        result["capabilities"] = capabilities
        result["checks"].append(
            {
                "method": "initialize",
                "ok": True,
                "status_code": init_meta["status_code"],
                "content_type": init_meta["content_type"],
                "body_preview": init_meta["body_preview"],
                "message": (
                    f"HTTP {init_meta['status_code']}，"
                    f"content-type={init_meta['content_type'] or '-'}"
                ),
            }
        )
    except Exception as exc:
        message = str(exc)
        errors.append(f"initialize: {message}")
        result["checks"].append(
            {
                "method": "initialize",
                "ok": False,
                "message": message,
            }
        )

    methods_to_probe: list[tuple[str, str, str]] = []
    capability_map = (
        ("tools", "tools/list", "tools", "tool"),
        ("prompts", "prompts/list", "prompts", "prompt"),
        ("resources", "resources/list", "resources", "resource"),
    )
    for capability_name, method, key, skill_type in capability_map:
        support = _supports_capability(capabilities, capability_name)
        if support is False:
            result["checks"].append(
                {
                    "method": method,
                    "ok": True,
                    "message": f"服务未声明 {capability_name} capability，已跳过",
                    "skipped": True,
                }
            )
            continue
        methods_to_probe.append((method, key, skill_type))

    if not methods_to_probe:
        methods_to_probe = [(method, key, skill_type) for _, method, key, skill_type in capability_map]

    for method, key, skill_type in methods_to_probe:
        try:
            payload, meta = _rpc_request(url, method, timeout_sec=timeout_sec, extra_headers=extra_headers)
            rpc_result = payload.get("result")
            items = rpc_result.get(key) if isinstance(rpc_result, dict) else []
            result[key] = _extract_skill_items(items, skill_type)
            result["checks"].append(
                {
                    "method": method,
                    "ok": True,
                    "status_code": meta["status_code"],
                    "content_type": meta["content_type"],
                    "body_preview": meta["body_preview"],
                    "message": (
                        f"HTTP {meta['status_code']}，"
                        f"content-type={meta['content_type'] or '-'}"
                    ),
                }
            )
        except Exception as exc:
            message = str(exc)
            errors.append(f"{method}: {message}")
            result["checks"].append(
                {
                    "method": method,
                    "ok": False,
                    "message": message,
                }
            )

    skills = [*result["tools"], *result["prompts"], *result["resources"]]
    result["skills"] = skills
    fallback = _builtin_manifest(server_name, url)
    if not skills and fallback is not None:
        result["tools"] = fallback["tools"]
        result["prompts"] = fallback["prompts"]
        result["resources"] = fallback["resources"]
        result["skills"] = [*result["tools"], *result["prompts"], *result["resources"]]
        result["source"] = str(fallback.get("source") or "fallback")
        result["notice"] = str(fallback.get("message") or "").strip()

    result["summary"] = (
        f"共 {len(result['skills'])} 项能力"
        f"（tools {len(result['tools'])} / prompts {len(result['prompts'])} / resources {len(result['resources'])}）"
    )
    result["errors"] = errors
    return result


def list_system_mcp_skills(mcp_config: object, timeout_sec: int = 12) -> list[dict[str, Any]]:
    normalized = normalize_system_mcp_config(mcp_config)
    servers = normalized.get("mcpServers")
    if not isinstance(servers, dict):
        return []
    return [
        _discover_server_skills(str(name), config, timeout_sec=timeout_sec)
        for name, config in sorted(servers.items(), key=lambda item: str(item[0]))
    ]
