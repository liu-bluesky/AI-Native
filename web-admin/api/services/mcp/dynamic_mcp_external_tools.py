"""External and system-level MCP tool discovery and invocation helpers."""

from __future__ import annotations

import json
import secrets
from typing import Any

import requests

from core.deps import external_mcp_store, system_config_store
from stores.json.system_config_store import normalize_system_mcp_config

_external_mcp_tool_cache: dict[str, list[dict]] = {}
_external_mcp_tool_signatures: dict[str, tuple] = {}


def _tool_token(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in str(value or "").strip().lower())
    text = "_".join(part for part in text.split("_") if part)
    if not text:
        return "tool"
    if text[0].isdigit():
        return f"t_{text}"
    return text


def _extract_text_nodes(node: object) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        out: list[str] = []
        for item in node:
            out.extend(_extract_text_nodes(item))
        return out
    if isinstance(node, dict):
        out: list[str] = []
        text = node.get("text")
        if isinstance(text, str) and text.strip():
            out.append(text)
        for key in ("content", "value", "message", "data"):
            if key in node:
                out.extend(_extract_text_nodes(node.get(key)))
        return out
    return []


def _join_text_nodes(node: object) -> str:
    parts = [part.strip() for part in _extract_text_nodes(node) if str(part).strip()]
    return "\n".join(parts)


def _shorten_text(value: object, limit: int = 300) -> str:
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
        "body_preview": _shorten_text(response.text, 300),
        "session_id": str(response.headers.get("mcp-session-id") or "").strip(),
    }


def _rpc_request(
    url: str,
    method: str,
    params: dict[str, Any] | None = None,
    timeout_sec: int = 15,
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
            "id": f"ext-{secrets.token_hex(4)}",
            "method": method,
            "params": params or {},
        },
        headers=headers,
        timeout=(3, timeout_sec),
    )
    meta = _build_meta(response)
    if meta["status_code"] >= 400:
        raise RuntimeError(
            f"HTTP {meta['status_code']}，content-type={meta['content_type'] or '-'}，"
            f"响应片段：{meta['body_preview'] or '-'}"
        )
    try:
        data = _parse_rpc_body(response.text, meta["content_type"])
    except Exception as exc:
        raise RuntimeError(
            f"返回内容不是 JSON-RPC，content-type={meta['content_type'] or '-'}，"
            f"响应片段：{meta['body_preview'] or '-'}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError("Invalid JSON-RPC response body")
    if data.get("error"):
        error = data.get("error")
        if isinstance(error, dict):
            raise RuntimeError(str(error.get("message") or error))
        raise RuntimeError(str(error))
    return data, meta


def _rpc_notify(
    url: str,
    method: str,
    params: dict[str, Any] | None = None,
    timeout_sec: int = 15,
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


def _initialize_endpoint(endpoint: str, timeout_sec: int = 15) -> tuple[dict[str, Any], dict[str, str]]:
    payload, meta = _rpc_request(
        endpoint,
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
        _rpc_notify(endpoint, "notifications/initialized", timeout_sec=timeout_sec, extra_headers=headers)
    except Exception:
        pass
    result = payload.get("result")
    capabilities = dict(result.get("capabilities") or {}) if isinstance(result, dict) else {}
    return capabilities, headers


def _supports_capability(capabilities: object, key: str) -> bool | None:
    if not isinstance(capabilities, dict):
        return None
    if key not in capabilities:
        return False
    value = capabilities.get(key)
    if isinstance(value, dict):
        return True
    return bool(value)


def _system_mcp_modules() -> list[dict[str, Any]]:
    cfg = system_config_store.get_global()
    normalized = normalize_system_mcp_config(getattr(cfg, "mcp_config", {}))
    servers = normalized.get("mcpServers")
    if not isinstance(servers, dict):
        return []
    modules: list[dict[str, Any]] = []
    for server_name, raw_server in sorted(servers.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_server, dict):
            continue
        modules.append(
            {
                "id": f"sysmcp::{server_name}",
                "name": str(server_name),
                "source_type": "system_config",
                "enabled": bool(raw_server.get("enabled", True)),
                "endpoint_http": str(raw_server.get("url") or "").strip(),
                "endpoint_sse": "",
                "project_id": "",
                "updated_at": str(getattr(cfg, "updated_at", "") or ""),
                "config": dict(raw_server),
            }
        )
    return modules


def _list_visible_external_mcp_modules(project_id: str) -> list[object]:
    visible: list[object] = []
    project_id_value = str(project_id or "").strip()
    for module in external_mcp_store.list_all():
        if not bool(getattr(module, "enabled", True)):
            continue
        module_project_id = str(getattr(module, "project_id", "") or "").strip()
        if module_project_id and module_project_id != project_id_value:
            continue
        visible.append(module)
    for module in _system_mcp_modules():
        if not bool(module.get("enabled", True)):
            continue
        visible.append(module)
    return visible


def _resolve_visible_mcp_module(project_id: str, module_id: str) -> object | None:
    normalized_module_id = str(module_id or "").strip()
    if not normalized_module_id:
        return None
    for module in _list_visible_external_mcp_modules(project_id):
        current_id = str(module.get("id") if isinstance(module, dict) else getattr(module, "id", "") or "").strip()
        if current_id == normalized_module_id:
            return module
    return None


def _external_mcp_signature(module: object) -> tuple:
    if isinstance(module, dict):
        config = module.get("config") if isinstance(module.get("config"), dict) else {}
        return (
            str(module.get("source_type") or ""),
            str(module.get("updated_at") or ""),
            str(module.get("endpoint_http") or ""),
            str(module.get("endpoint_sse") or ""),
            str(module.get("project_id") or ""),
            bool(module.get("enabled", True)),
            json.dumps(config, ensure_ascii=False, sort_keys=True),
        )
    return (
        str(getattr(module, "updated_at", "") or ""),
        str(getattr(module, "endpoint_http", "") or ""),
        str(getattr(module, "endpoint_sse", "") or ""),
        str(getattr(module, "project_id", "") or ""),
        bool(getattr(module, "enabled", True)),
    )


def _external_mcp_candidate_endpoints(module: object) -> list[tuple[str, str]]:
    endpoints: list[tuple[str, str]] = []
    endpoint_http = str(module.get("endpoint_http") if isinstance(module, dict) else getattr(module, "endpoint_http", "") or "").strip()
    endpoint_sse = str(module.get("endpoint_sse") if isinstance(module, dict) else getattr(module, "endpoint_sse", "") or "").strip()
    if endpoint_http:
        endpoints.append(("http", endpoint_http))
    if endpoint_sse:
        endpoints.append(("sse", endpoint_sse))
    return endpoints


def _normalize_parameters_schema(schema: object) -> dict:
    if isinstance(schema, dict) and str(schema.get("type") or "").strip():
        return schema
    if isinstance(schema, dict):
        normalized = dict(schema)
        normalized.setdefault("type", "object")
        normalized.setdefault("properties", {})
        return normalized
    return {"type": "object", "properties": {}}


def _extract_external_mcp_tools_payload(module: object, timeout_sec: int = 15) -> list[dict]:
    errors: list[str] = []
    module_name = str(module.get("name") if isinstance(module, dict) else getattr(module, "name", "") or getattr(module, "id", "") or "external")
    module_id = str(module.get("id") if isinstance(module, dict) else getattr(module, "id", "") or "")
    source_type = str(module.get("source_type") if isinstance(module, dict) else "external_store" or "external_store")
    for transport, endpoint in _external_mcp_candidate_endpoints(module):
        try:
            capabilities, headers = _initialize_endpoint(endpoint, timeout_sec=timeout_sec)
            tools_supported = _supports_capability(capabilities, "tools")
            if tools_supported is False:
                return []
            payload, _meta = _rpc_request(endpoint, "tools/list", {}, timeout_sec=timeout_sec, extra_headers=headers)
            result = payload.get("result")
            tools = result.get("tools") if isinstance(result, dict) else None
            if not isinstance(tools, list):
                raise RuntimeError("tools/list missing tools array")
            items: list[dict] = []
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                remote_name = str(tool.get("name") or "").strip()
                if not remote_name:
                    continue
                prefix = "system_mcp" if source_type == "system_config" else "external"
                tool_name = f"{prefix}__{_tool_token(module_id or module_name)}__{_tool_token(remote_name)}"
                items.append(
                    {
                        "tool_name": tool_name,
                        "remote_tool_name": remote_name,
                        "module_id": module_id,
                        "module_name": module_name,
                        "module_source": source_type,
                        "employee_id": "",
                        "base_tool_name": remote_name,
                        "scoped_tool_name": tool_name,
                        "entry_name": remote_name,
                        "script_type": f"{prefix}_{transport}",
                        "description": f"{'系统' if source_type == 'system_config' else '外部'} MCP[{module_name}]：{str(tool.get('description') or remote_name)}",
                        "parameters_schema": _normalize_parameters_schema(tool.get("inputSchema") or tool.get("parameters")),
                        "module_type": "system_mcp_tool" if source_type == "system_config" else "external_mcp_tool",
                        "builtin": False,
                    }
                )
            return items
        except Exception as exc:
            errors.append(f"{transport}:{exc}")
    if errors:
        return [
            {
                "tool_name": f"external__{_tool_token(module_id or module_name)}__unavailable",
                "remote_tool_name": "",
                "module_id": module_id,
                "module_name": module_name,
                "module_source": source_type,
                "employee_id": "",
                "base_tool_name": "",
                "scoped_tool_name": "",
                "entry_name": "",
                "script_type": "external_error",
                "description": f"{'系统' if source_type == 'system_config' else '外部'} MCP[{module_name}] 暂不可用：{' | '.join(errors)}",
                "parameters_schema": {"type": "object", "properties": {}},
                "module_type": "system_mcp_tool" if source_type == "system_config" else "external_mcp_tool",
                "builtin": False,
                "disabled": True,
            }
        ]
    return []


def list_project_external_tools_runtime(project_id: str) -> list[dict]:
    tools: list[dict] = []
    for module in _list_visible_external_mcp_modules(project_id):
        module_id = str(module.get("id") if isinstance(module, dict) else getattr(module, "id", "") or "")
        signature = _external_mcp_signature(module)
        cached = _external_mcp_tool_cache.get(module_id)
        if cached is None or _external_mcp_tool_signatures.get(module_id) != signature:
            cached = _extract_external_mcp_tools_payload(module)
            _external_mcp_tool_cache[module_id] = cached
            _external_mcp_tool_signatures[module_id] = signature
        tools.extend(item for item in cached if not bool(item.get("disabled")))
    return tools


def resolve_external_tool_spec(project_id: str, tool_name: str) -> tuple[dict | None, str]:
    normalized_tool_name = str(tool_name or "").strip()
    if not normalized_tool_name:
        return None, "tool_name is required"
    for item in list_project_external_tools_runtime(project_id):
        if str(item.get("tool_name") or "").strip() == normalized_tool_name:
            return item, ""
    return None, f"External tool not found: {normalized_tool_name}"


def invoke_external_mcp_tool_runtime(
    project_id: str,
    tool_name: str,
    args: dict | None = None,
    args_json: str = "{}",
    timeout_sec: int = 30,
) -> dict:
    spec, err = resolve_external_tool_spec(project_id, tool_name)
    if spec is None:
        return {"error": err}

    if args is not None:
        if not isinstance(args, dict):
            return {"error": "args must be an object"}
        payload = args
    else:
        try:
            payload = json.loads(args_json or "{}")
        except Exception as exc:
            return {"error": f"Invalid args_json: {exc}"}
        if not isinstance(payload, dict):
            return {"error": "args_json must be a JSON object"}

    try:
        timeout_value = max(3, min(int(timeout_sec), 120))
    except (TypeError, ValueError):
        timeout_value = 30

    module_id = str(spec.get("module_id") or "")
    module = _resolve_visible_mcp_module(project_id, module_id)
    if module is None:
        return {"error": f"External MCP module {module_id or '-'} not found"}

    errors: list[str] = []
    for _transport, endpoint in _external_mcp_candidate_endpoints(module):
        try:
            _capabilities, headers = _initialize_endpoint(endpoint, timeout_sec=timeout_value)
            rpc_payload, _meta = _rpc_request(
                endpoint,
                "tools/call",
                {
                    "name": str(spec.get("remote_tool_name") or tool_name),
                    "arguments": payload,
                },
                timeout_sec=timeout_value,
                extra_headers=headers,
            )
            result = rpc_payload.get("result")
            if isinstance(result, dict) and bool(result.get("isError")):
                return {
                    "error": _join_text_nodes(result.get("content")) or str(result),
                    "tool_name": tool_name,
                    "module_id": module_id,
                    "module_name": str(spec.get("module_name") or ""),
                    "remote_tool_name": str(spec.get("remote_tool_name") or tool_name),
                    "module_source": str(spec.get("module_source") or ""),
                }
            response = {
                "tool_name": tool_name,
                "module_id": module_id,
                "module_name": str(spec.get("module_name") or ""),
                "remote_tool_name": str(spec.get("remote_tool_name") or tool_name),
                "module_source": str(spec.get("module_source") or ""),
                "result": result,
            }
            if isinstance(result, dict):
                text = _join_text_nodes(result.get("content"))
                if text:
                    response["text"] = text
            return response
        except Exception as exc:
            errors.append(str(exc))
    return {"error": f"External MCP call failed: {' | '.join(errors)}"}
