"""外部 MCP 模块管理路由"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from fastapi import APIRouter, Depends, HTTPException, Query

from core.deps import external_mcp_store, require_auth
from stores.json.external_mcp_store import ExternalMcpModule, _now_iso
from models.requests import ExternalMcpModuleCreateReq, ExternalMcpModuleTestReq, ExternalMcpModuleUpdateReq

router = APIRouter(prefix="/api/mcp/modules", dependencies=[Depends(require_auth)])


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def _ensure_endpoint_valid(endpoint_http: str, endpoint_sse: str) -> None:
    if _normalize_text(endpoint_http) or _normalize_text(endpoint_sse):
        return
    raise HTTPException(400, "endpoint_http or endpoint_sse is required")


def _ensure_url_http_scheme(url: str, field_name: str) -> str:
    normalized = _normalize_text(url)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, f"{field_name} must be a valid http(s) url")
    return normalized


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp_timeout_sec(timeout_sec: object) -> int:
    try:
        value = int(timeout_sec)
    except (TypeError, ValueError):
        value = 8
    return max(3, min(value, 20))


def _probe_http_endpoint(url: str, timeout_sec: int) -> dict:
    headers = {
        "Accept": "application/json, text/event-stream;q=0.9, */*;q=0.8",
        "Content-Type": "application/json",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": "probe",
        "method": "tools/list",
        "params": {},
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=(3, timeout_sec))
    except requests.RequestException as exc:
        return {
            "transport": "http",
            "url": url,
            "ok": False,
            "message": f"连接失败: {exc}",
        }

    status_code = int(response.status_code)
    content_type = str(response.headers.get("content-type") or "")
    ok = (200 <= status_code < 500 and status_code != 404) or "json" in content_type.lower()
    if ok:
        message = f"HTTP 端点可达，返回状态 {status_code}"
    else:
        message = f"HTTP 端点返回异常状态 {status_code}"
    return {
        "transport": "http",
        "url": url,
        "ok": ok,
        "status_code": status_code,
        "content_type": content_type,
        "message": message,
    }


def _probe_sse_endpoint(url: str, timeout_sec: int) -> dict:
    headers = {
        "Accept": "text/event-stream, */*;q=0.8",
        "Cache-Control": "no-cache",
    }
    try:
        response = requests.get(url, headers=headers, timeout=(3, timeout_sec), stream=True)
    except requests.RequestException as exc:
        return {
            "transport": "sse",
            "url": url,
            "ok": False,
            "message": f"连接失败: {exc}",
        }

    status_code = int(response.status_code)
    content_type = str(response.headers.get("content-type") or "")
    ok = status_code in {200, 401, 403, 405} or "text/event-stream" in content_type.lower()
    if ok:
        message = f"SSE 端点可达，返回状态 {status_code}"
    else:
        message = f"SSE 端点返回异常状态 {status_code}"
    response.close()
    return {
        "transport": "sse",
        "url": url,
        "ok": ok,
        "status_code": status_code,
        "content_type": content_type,
        "message": message,
    }


def _serialize_module(module: ExternalMcpModule) -> dict:
    return asdict(module)


def run_external_mcp_connection_test(
    endpoint_http: str | None,
    endpoint_sse: str | None,
    timeout_sec: object = 8,
) -> dict:
    normalized_http = _ensure_url_http_scheme(endpoint_http, "endpoint_http")
    normalized_sse = _ensure_url_http_scheme(endpoint_sse, "endpoint_sse")
    _ensure_endpoint_valid(normalized_http, normalized_sse)

    clamped_timeout_sec = _clamp_timeout_sec(timeout_sec)

    results = []
    if normalized_http:
        results.append(_probe_http_endpoint(normalized_http, clamped_timeout_sec))
    if normalized_sse:
        results.append(_probe_sse_endpoint(normalized_sse, clamped_timeout_sec))

    ok = any(bool(item.get("ok")) for item in results)
    success_count = sum(1 for item in results if bool(item.get("ok")))
    summary = f"已测试 {len(results)} 个端点，成功 {success_count} 个"
    if ok:
        summary = f"连接测试通过：{summary}"
    else:
        summary = f"连接测试未通过：{summary}"
    return {
        "ok": ok,
        "summary": summary,
        "tested_at": _utc_now_iso(),
        "results": results,
    }


@router.get("")
async def list_external_mcp_modules(
    project_id: str = Query("", description="项目 ID（为空表示查询全局 + 所有项目）"),
    include_disabled: bool = Query(False, description="是否包含停用模块"),
):
    normalized_project_id = _normalize_text(project_id)
    items = []
    for module in external_mcp_store.list_all():
        module_project_id = _normalize_text(getattr(module, "project_id", ""))
        if normalized_project_id and module_project_id and module_project_id != normalized_project_id:
            continue
        if not include_disabled and not bool(getattr(module, "enabled", True)):
            continue
        items.append(_serialize_module(module))
    items.sort(key=lambda item: (0 if item.get("project_id") == normalized_project_id else 1, item.get("name", ""), item.get("id", "")))
    return {"modules": items, "total": len(items)}


@router.post("")
async def create_external_mcp_module(req: ExternalMcpModuleCreateReq):
    name = _normalize_text(req.name)
    if not name:
        raise HTTPException(400, "name is required")
    endpoint_http = _normalize_text(req.endpoint_http)
    endpoint_sse = _normalize_text(req.endpoint_sse)
    _ensure_endpoint_valid(endpoint_http, endpoint_sse)

    now = _now_iso()
    module = ExternalMcpModule(
        id=external_mcp_store.new_id(),
        name=name,
        description=_normalize_text(req.description),
        endpoint_http=endpoint_http,
        endpoint_sse=endpoint_sse,
        auth_type=_normalize_text(req.auth_type) or "none",
        project_id=_normalize_text(req.project_id),
        enabled=bool(req.enabled),
        created_at=now,
        updated_at=now,
    )
    external_mcp_store.save(module)
    return {"status": "created", "module": _serialize_module(module)}


@router.post("/test")
async def test_external_mcp_module(req: ExternalMcpModuleTestReq):
    return run_external_mcp_connection_test(
        req.endpoint_http,
        req.endpoint_sse,
        req.timeout_sec,
    )


@router.patch("/{module_id}")
async def patch_external_mcp_module(module_id: str, req: ExternalMcpModuleUpdateReq):
    module = external_mcp_store.get(module_id)
    if module is None:
        raise HTTPException(404, f"External MCP module {module_id} not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "module": _serialize_module(module)}

    payload = asdict(module)
    for key, value in updates.items():
        if key in {"name", "description", "endpoint_http", "endpoint_sse", "auth_type", "project_id"}:
            payload[key] = _normalize_text(value)
        elif key == "enabled":
            payload[key] = bool(value)

    if not _normalize_text(payload.get("name")):
        raise HTTPException(400, "name cannot be empty")
    _ensure_endpoint_valid(_normalize_text(payload.get("endpoint_http")), _normalize_text(payload.get("endpoint_sse")))
    payload["updated_at"] = _now_iso()
    updated = ExternalMcpModule(**payload)
    external_mcp_store.save(updated)
    return {"status": "updated", "module": _serialize_module(updated)}


@router.delete("/{module_id}")
async def delete_external_mcp_module(module_id: str):
    if not external_mcp_store.delete(module_id):
        raise HTTPException(404, f"External MCP module {module_id} not found")
    return {"status": "deleted", "module_id": module_id}
