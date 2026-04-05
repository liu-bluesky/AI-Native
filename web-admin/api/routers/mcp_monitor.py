"""MCP 连接监控路由"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from core.deps import external_mcp_store, require_auth
from routers.mcp_modules import run_external_mcp_connection_test
from services.project_mcp_presence import list_active_project_mcp_presence, list_active_system_mcp_presence


router = APIRouter(prefix="/api/system/mcp-monitor", dependencies=[Depends(require_auth)])
public_router = None


def _normalize_text(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _ensure_super_admin(auth_payload: dict) -> None:
    role = _normalize_text(auth_payload.get("role", ""), 40).lower()
    if role != "admin":
        raise HTTPException(403, "Super admin only")


def _serialize_monitor_module(module) -> dict:
    data = asdict(module)
    endpoint_http = _normalize_text(data.get("endpoint_http", ""))
    endpoint_sse = _normalize_text(data.get("endpoint_sse", ""))
    project_id = _normalize_text(data.get("project_id", ""), 120)
    endpoints = []
    if endpoint_http:
        endpoints.append({"transport": "http", "url": endpoint_http})
    if endpoint_sse:
        endpoints.append({"transport": "sse", "url": endpoint_sse})
    data["scope"] = "project" if project_id else "global"
    data["primary_endpoint"] = endpoints[0]["url"] if endpoints else ""
    data["transport_types"] = [item["transport"] for item in endpoints]
    data["endpoints"] = endpoints
    return data


@router.get("/project-activity")
async def list_project_mcp_activity(auth_payload: dict = Depends(require_auth)):
    _ensure_super_admin(auth_payload)
    return await list_active_project_mcp_presence()


@router.get("/activity")
async def list_system_mcp_activity(auth_payload: dict = Depends(require_auth)):
    _ensure_super_admin(auth_payload)
    return await list_active_system_mcp_presence()


def _match_modules(project_id: str, include_disabled: bool) -> list[dict]:
    normalized_project_id = _normalize_text(project_id, 120)
    items: list[dict] = []
    for module in external_mcp_store.list_all():
        module_project_id = _normalize_text(getattr(module, "project_id", ""), 120)
        if normalized_project_id and module_project_id and module_project_id != normalized_project_id:
            continue
        if not include_disabled and not bool(getattr(module, "enabled", True)):
            continue
        items.append(_serialize_monitor_module(module))
    items.sort(
        key=lambda item: (
            0 if not item.get("project_id") else 1,
            item.get("project_id", ""),
            item.get("name", ""),
            item.get("id", ""),
        )
    )
    return items


@router.get("/modules")
async def list_monitored_mcp_modules(
    project_id: str = Query("", description="项目 ID（为空表示查询全部范围）"),
    include_disabled: bool = Query(True, description="是否包含停用模块"),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_super_admin(auth_payload)
    items = _match_modules(project_id, include_disabled)
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "enabled_total": sum(1 for item in items if bool(item.get("enabled"))),
            "disabled_total": sum(1 for item in items if not bool(item.get("enabled"))),
            "global_total": sum(1 for item in items if item.get("scope") == "global"),
            "project_total": sum(1 for item in items if item.get("scope") == "project"),
        },
    }


@router.post("/modules/{module_id}/test")
async def test_monitored_mcp_module(
    module_id: str,
    timeout_sec: int = Query(8, description="测试超时时间（秒）"),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_super_admin(auth_payload)
    module = external_mcp_store.get(module_id)
    if module is None:
        raise HTTPException(404, f"External MCP module {module_id} not found")
    result = run_external_mcp_connection_test(
        getattr(module, "endpoint_http", ""),
        getattr(module, "endpoint_sse", ""),
        timeout_sec,
    )
    result["module"] = _serialize_monitor_module(module)
    return result
