"""网络工具实现：http_get / http_post / download_file。

网络工具不自动携带本地凭据。headers 中的 Authorization、Cookie 等敏感头
会被记录到审计但不外传给模型。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from services.agent_runtime.builtin_tools.workspace import (
    WorkspacePathError,
    _bool_arg,
    _int_arg,
    _str_arg,
    resolve_workspace_path,
)

# 禁止自动携带的敏感请求头（用户显式传入的会保留，但不从环境注入）
_SENSITIVE_HEADER_PREFIXES = ("authorization", "cookie", "x-api-key", "x-auth")

_MAX_RESPONSE_CHARS = 20000


async def http_get(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """发起 HTTP GET 请求。"""
    url = _str_arg(args, "url")
    headers = dict(args.get("headers") or {})
    timeout_ms = _int_arg(args, "timeout_ms", 30000, minimum=1000, maximum=120000)

    if not url:
        return {"ok": False, "error": "url is required", "error_code": "tool.schema_invalid"}

    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "url must start with http:// or https://", "error_code": "tool.schema_invalid"}

    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        return {"ok": False, "error": f"request timeout after {timeout_ms}ms", "error_code": "network.failed"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"request failed: {exc}", "error_code": "network.failed"}

    content_type = response.headers.get("content-type", "")
    body = response.text
    body, truncated = _truncate_text(body, _MAX_RESPONSE_CHARS)

    return {
        "ok": True,
        "status_code": response.status_code,
        "content_type": content_type,
        "content": body,
        "truncated": truncated,
        "headers_summary": _summarize_headers(response.headers),
        "summary": f"GET {url} → {response.status_code} ({content_type})",
    }


async def http_post(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """发起 HTTP POST 请求。body 进入审计。"""
    url = _str_arg(args, "url")
    headers = dict(args.get("headers") or {})
    body = args.get("body")
    timeout_ms = _int_arg(args, "timeout_ms", 30000, minimum=1000, maximum=120000)

    if not url:
        return {"ok": False, "error": "url is required", "error_code": "tool.schema_invalid"}

    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "url must start with http:// or https://", "error_code": "tool.schema_invalid"}

    # 序列化 body
    if isinstance(body, (dict, list)):
        json_body = json.dumps(body, ensure_ascii=False)
        headers.setdefault("Content-Type", "application/json")
    else:
        json_body = str(body or "")

    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000.0) as client:
            response = await client.post(url, headers=headers, content=json_body)
    except httpx.TimeoutException:
        return {"ok": False, "error": f"request timeout after {timeout_ms}ms", "error_code": "network.failed"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"request failed: {exc}", "error_code": "network.failed"}

    content_type = response.headers.get("content-type", "")
    resp_body = response.text
    resp_body, truncated = _truncate_text(resp_body, _MAX_RESPONSE_CHARS)

    return {
        "ok": True,
        "status_code": response.status_code,
        "content_type": content_type,
        "content": resp_body,
        "truncated": truncated,
        "headers_summary": _summarize_headers(response.headers),
        "summary": f"POST {url} → {response.status_code} ({content_type})",
    }


async def download_file(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """下载文件到 workspace。"""
    url = _str_arg(args, "url")
    dest_path = _str_arg(args, "dest_path")
    overwrite = _bool_arg(args, "overwrite", False)
    timeout_ms = _int_arg(args, "timeout_ms", 30000, minimum=1000, maximum=300000)

    if not url:
        return {"ok": False, "error": "url is required", "error_code": "tool.schema_invalid"}

    if not dest_path:
        return {"ok": False, "error": "dest_path is required", "error_code": "tool.schema_invalid"}

    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "url must start with http:// or https://", "error_code": "tool.schema_invalid"}

    try:
        dest = resolve_workspace_path(workspace_path, dest_path, allow_create=True)
    except WorkspacePathError as exc:
        return {"ok": False, "error": str(exc), "error_code": "workspace.out_of_scope"}

    if dest.exists() and not overwrite:
        return {
            "ok": False,
            "error": f"file already exists: {dest_path} (set overwrite=true to replace)",
            "error_code": "tool.schema_invalid",
        }

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                total_bytes = 0
                with open(dest, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        total_bytes += len(chunk)
    except httpx.TimeoutException:
        return {"ok": False, "error": f"download timeout after {timeout_ms}ms", "error_code": "network.failed"}
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "error": f"download failed: HTTP {exc.response.status_code}", "error_code": "network.failed"}
    except (httpx.HTTPError, OSError) as exc:
        return {"ok": False, "error": f"download failed: {exc}", "error_code": "network.failed"}

    return {
        "ok": True,
        "dest_path": dest_path,
        "bytes": total_bytes,
        "content_type": content_type,
        "summary": f"下载 {url} → {dest_path}（{total_bytes} 字节）",
    }


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n... [truncated]", True


def _summarize_headers(headers: Any) -> dict[str, str]:
    """提取非敏感响应头摘要。"""
    summary: dict[str, str] = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower in ("content-type", "content-length", "date", "server", "cache-control"):
            summary[key] = str(value)[:100]
    return summary
