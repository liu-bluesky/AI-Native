"""External MCP tool discovery and invocation helpers."""

from __future__ import annotations

import json
import secrets

import requests

from core.deps import external_mcp_store

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
    return visible


def _external_mcp_signature(module: object) -> tuple:
    return (
        str(getattr(module, "updated_at", "") or ""),
        str(getattr(module, "endpoint_http", "") or ""),
        str(getattr(module, "endpoint_sse", "") or ""),
        str(getattr(module, "project_id", "") or ""),
        bool(getattr(module, "enabled", True)),
    )


def _external_mcp_candidate_endpoints(module: object) -> list[tuple[str, str]]:
    endpoints: list[tuple[str, str]] = []
    endpoint_http = str(getattr(module, "endpoint_http", "") or "").strip()
    endpoint_sse = str(getattr(module, "endpoint_sse", "") or "").strip()
    if endpoint_http:
        endpoints.append(("http", endpoint_http))
    if endpoint_sse:
        endpoints.append(("sse", endpoint_sse))
    return endpoints


def _external_mcp_request(url: str, method: str, params: dict | None = None, timeout_sec: int = 15) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": f"ext-{secrets.token_hex(4)}",
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    response = requests.post(
        url,
        json=payload,
        headers={
            "Accept": "application/json, text/event-stream;q=0.9, */*;q=0.8",
            "Content-Type": "application/json",
        },
        timeout=(3, timeout_sec),
    )
    status_code = int(response.status_code)
    if status_code >= 400:
        raise RuntimeError(f"HTTP {status_code}: {response.text[:300]}")
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON response: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Invalid JSON-RPC response body")
    if data.get("error"):
        error = data.get("error")
        if isinstance(error, dict):
            raise RuntimeError(str(error.get("message") or error))
        raise RuntimeError(str(error))
    return data


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
    module_name = str(getattr(module, "name", "") or getattr(module, "id", "") or "external")
    module_id = str(getattr(module, "id", "") or "")
    for transport, endpoint in _external_mcp_candidate_endpoints(module):
        try:
            payload = _external_mcp_request(endpoint, "tools/list", {}, timeout_sec=timeout_sec)
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
                tool_name = f"external__{_tool_token(module_id or module_name)}__{_tool_token(remote_name)}"
                items.append(
                    {
                        "tool_name": tool_name,
                        "remote_tool_name": remote_name,
                        "module_id": module_id,
                        "module_name": module_name,
                        "employee_id": "",
                        "base_tool_name": remote_name,
                        "scoped_tool_name": tool_name,
                        "entry_name": remote_name,
                        "script_type": f"external_{transport}",
                        "description": f"外部 MCP[{module_name}]：{str(tool.get('description') or remote_name)}",
                        "parameters_schema": _normalize_parameters_schema(tool.get("inputSchema") or tool.get("parameters")),
                        "module_type": "external_mcp_tool",
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
                "employee_id": "",
                "base_tool_name": "",
                "scoped_tool_name": "",
                "entry_name": "",
                "script_type": "external_error",
                "description": f"外部 MCP[{module_name}] 暂不可用：{' | '.join(errors)}",
                "parameters_schema": {"type": "object", "properties": {}},
                "module_type": "external_mcp_tool",
                "builtin": False,
                "disabled": True,
            }
        ]
    return []


def list_project_external_tools_runtime(project_id: str) -> list[dict]:
    tools: list[dict] = []
    for module in _list_visible_external_mcp_modules(project_id):
        module_id = str(getattr(module, "id", "") or "")
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
    module = external_mcp_store.get(module_id) if module_id else None
    if module is None:
        return {"error": f"External MCP module {module_id or '-'} not found"}

    errors: list[str] = []
    for _transport, endpoint in _external_mcp_candidate_endpoints(module):
        try:
            rpc_payload = _external_mcp_request(
                endpoint,
                "tools/call",
                {
                    "name": str(spec.get("remote_tool_name") or tool_name),
                    "arguments": payload,
                },
                timeout_sec=timeout_value,
            )
            result = rpc_payload.get("result")
            if isinstance(result, dict) and bool(result.get("isError")):
                return {
                    "error": _join_text_nodes(result.get("content")) or str(result),
                    "tool_name": tool_name,
                    "module_id": module_id,
                    "module_name": str(spec.get("module_name") or ""),
                    "remote_tool_name": str(spec.get("remote_tool_name") or tool_name),
                }
            response = {
                "tool_name": tool_name,
                "module_id": module_id,
                "module_name": str(spec.get("module_name") or ""),
                "remote_tool_name": str(spec.get("remote_tool_name") or tool_name),
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
