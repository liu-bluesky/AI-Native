"""市场目录只读路由"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from core.auth import decode_token
from core.deps import employee_store, require_auth
from models.requests import CliPluginInstallReq
from services.cli_plugin_install_task_service import (
    create_install_task,
    get_install_task,
    list_install_tasks,
    subscribe_install_task_events,
)
from services.cli_plugin_market_service import install_cli_plugin, list_cli_plugins
from stores.mcp_bridge import rule_store, skill_store

router = APIRouter(prefix="/api/market", dependencies=[Depends(require_auth)])


def _normalize_tokens(values: list[str] | tuple[str, ...] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values or []:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _normalize_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _extract_ws_auth_payload(websocket: WebSocket) -> dict | None:
    token = str(websocket.query_params.get("token") or "").strip()
    if token:
        payload = decode_token(token)
        if payload is not None:
            return payload
    auth_header = str(websocket.headers.get("authorization") or "").strip()
    if auth_header.startswith("Bearer "):
        return decode_token(auth_header[7:])
    return None


def _current_username(auth_payload: dict | None) -> str:
    return str((auth_payload or {}).get("sub") or "").strip()


def _sort_records(items: list[Any]) -> list[Any]:
    return sorted(
        items,
        key=lambda item: (
            str(getattr(item, "updated_at", "") or ""),
            str(getattr(item, "created_at", "") or ""),
            str(getattr(item, "id", "") or ""),
        ),
        reverse=True,
    )


def _build_rule_domain_map() -> dict[str, list[str]]:
    domain_map: dict[str, list[str]] = defaultdict(list)
    for rule in rule_store.list_all():
        rule_id = str(getattr(rule, "id", "") or "").strip()
        domain_key = _normalize_domain(getattr(rule, "domain", ""))
        if not rule_id or not domain_key:
            continue
        domain_map[domain_key].append(rule_id)
    return domain_map


def _resolve_employee_rule_ids(employee: Any, domain_map: dict[str, list[str]]) -> list[str]:
    explicit_rule_ids = _normalize_tokens(getattr(employee, "rule_ids", []) or [])
    if explicit_rule_ids:
        return explicit_rule_ids

    inferred_rule_ids: list[str] = []
    for domain in _normalize_tokens(getattr(employee, "rule_domains", []) or []):
        inferred_rule_ids.extend(domain_map.get(_normalize_domain(domain), []))
    return _normalize_tokens(inferred_rule_ids)


def _serialize_market_skill(skill: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(skill, "id", "") or ""),
        "name": str(getattr(skill, "name", "") or ""),
        "description": str(getattr(skill, "description", "") or ""),
        "version": str(getattr(skill, "version", "") or ""),
        "tags": _normalize_tokens(getattr(skill, "tags", []) or []),
        "tool_count": len(getattr(skill, "tools", []) or []),
        "mcp_enabled": bool(getattr(skill, "mcp_enabled", False)),
        "updated_at": str(getattr(skill, "updated_at", "") or ""),
        "created_at": str(getattr(skill, "created_at", "") or ""),
    }


def _serialize_market_employee(employee: Any) -> dict[str, Any]:
    skill_names: list[str] = []
    for skill_id in _normalize_tokens(getattr(employee, "skills", []) or []):
        skill = skill_store.get(skill_id)
        skill_name = str(getattr(skill, "name", "") or "").strip() if skill else ""
        skill_names.append(skill_name or skill_id)

    return {
        "id": str(getattr(employee, "id", "") or ""),
        "name": str(getattr(employee, "name", "") or ""),
        "description": str(getattr(employee, "description", "") or ""),
        "goal": str(getattr(employee, "goal", "") or ""),
        "tone": str(getattr(employee, "tone", "") or ""),
        "verbosity": str(getattr(employee, "verbosity", "") or ""),
        "skill_ids": _normalize_tokens(getattr(employee, "skills", []) or []),
        "skill_names": skill_names,
        "feedback_upgrade_enabled": bool(getattr(employee, "feedback_upgrade_enabled", False)),
        "updated_at": str(getattr(employee, "updated_at", "") or ""),
        "created_at": str(getattr(employee, "created_at", "") or ""),
    }


def _serialize_market_rule(rule: Any, bound_employee_names: list[str]) -> dict[str, Any]:
    severity = getattr(rule, "severity", "")
    risk_domain = getattr(rule, "risk_domain", "")
    return {
        "id": str(getattr(rule, "id", "") or ""),
        "title": str(getattr(rule, "title", "") or ""),
        "domain": str(getattr(rule, "domain", "") or ""),
        "severity": str(getattr(severity, "value", severity) or ""),
        "risk_domain": str(getattr(risk_domain, "value", risk_domain) or ""),
        "confidence": float(getattr(rule, "confidence", 0) or 0),
        "version": str(getattr(rule, "version", "") or ""),
        "bound_employee_count": len(bound_employee_names),
        "bound_employee_names": bound_employee_names,
        "updated_at": str(getattr(rule, "updated_at", "") or ""),
        "created_at": str(getattr(rule, "created_at", "") or ""),
    }


@router.get("/catalog")
async def get_market_catalog():
    rules = _sort_records(rule_store.list_all())
    employees = _sort_records(employee_store.list_all())
    skills = _sort_records(skill_store.list_all())
    cli_plugins = await run_in_threadpool(list_cli_plugins)

    rule_domain_map = _build_rule_domain_map()
    employees_by_rule: dict[str, list[str]] = defaultdict(list)
    for employee in employees:
        employee_name = str(getattr(employee, "name", "") or "").strip()
        if not employee_name:
            continue
        for rule_id in _resolve_employee_rule_ids(employee, rule_domain_map):
            employees_by_rule[rule_id].append(employee_name)

    return {
        "catalog": {
            "skills": [_serialize_market_skill(skill) for skill in skills],
            "employees": [_serialize_market_employee(employee) for employee in employees],
            "rules": [
                _serialize_market_rule(
                    rule,
                    _normalize_tokens(employees_by_rule.get(str(getattr(rule, "id", "") or "").strip(), [])),
                )
                for rule in rules
            ],
            "cli_plugins": cli_plugins,
        },
        "meta": {
            "skill_count": len(skills),
            "employee_count": len(employees),
            "rule_count": len(rules),
            "cli_plugin_count": len(cli_plugins),
        },
    }


@router.get("/cli-plugins")
async def get_cli_plugin_catalog():
    items = await run_in_threadpool(list_cli_plugins)
    return {
        "items": items,
        "meta": {
            "cli_plugin_count": len(items),
        },
    }


@router.post("/cli-plugins/install")
async def install_market_cli_plugin(req: CliPluginInstallReq):
    try:
        result = await run_in_threadpool(
            install_cli_plugin,
            str(req.plugin_id or "").strip(),
            timeout_sec=max(30, min(int(req.timeout_sec or 180), 900)),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(500, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {
        "status": "installed" if bool(result.get("ok")) else "failed",
        **result,
    }


@router.post("/cli-plugins/install-tasks", status_code=202)
async def create_market_cli_plugin_install_task(
    req: CliPluginInstallReq,
    auth_payload: dict = Depends(require_auth),
):
    try:
        task = await run_in_threadpool(
            create_install_task,
            str(req.plugin_id or "").strip(),
            username=_current_username(auth_payload),
            timeout_sec=max(30, min(int(req.timeout_sec or 1800), 7200)),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "status": "accepted",
        "task": task,
    }


@router.get("/cli-plugins/install-tasks")
async def list_market_cli_plugin_install_tasks(
    limit: int = Query(default=20, ge=1, le=200),
    auth_payload: dict = Depends(require_auth),
):
    items = await run_in_threadpool(
        list_install_tasks,
        username=_current_username(auth_payload),
        limit=limit,
    )
    return {
        "items": items,
        "meta": {
            "count": len(items),
        },
    }


@router.get("/cli-plugins/install-tasks/{task_id}")
async def get_market_cli_plugin_install_task(
    task_id: str,
    auth_payload: dict = Depends(require_auth),
):
    task = await run_in_threadpool(get_install_task, task_id)
    if task is None:
        raise HTTPException(404, "Install task not found")
    if str(task.get("created_by") or "").strip() != _current_username(auth_payload):
        raise HTTPException(403, "Permission denied")
    return {
        "task": task,
    }


@router.websocket("/cli-plugins/install-tasks/ws")
async def ws_market_cli_plugin_install_tasks(websocket: WebSocket):
    auth_payload = _extract_ws_auth_payload(websocket)
    if auth_payload is None:
        await websocket.close(code=4401, reason="Missing or invalid token")
        return

    username = _current_username(auth_payload)
    if not username:
        await websocket.close(code=4401, reason="Missing or invalid token")
        return

    await websocket.accept()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    unsubscribe = subscribe_install_task_events(
        username,
        lambda payload: loop.call_soon_threadsafe(queue.put_nowait, payload),
    )

    initial_items = await run_in_threadpool(
        list_install_tasks,
        username=username,
        limit=20,
    )
    await websocket.send_json(
        {
            "type": "ready",
            "message": "connected",
            "items": initial_items,
        }
    )

    async def send_updates() -> None:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)

    sender_task = asyncio.create_task(send_updates())
    try:
        while True:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                await websocket.send_json({"type": "error", "message": "Invalid payload type"})
                continue
            message_type = str(payload.get("type") or "").strip().lower()
            if message_type == "ping":
                await websocket.send_json(
                    {"type": "pong", "request_id": str(payload.get("request_id") or "").strip()}
                )
                continue
            if message_type == "snapshot":
                items = await run_in_threadpool(
                    list_install_tasks,
                    username=username,
                    limit=20,
                )
                await websocket.send_json({"type": "task_snapshot", "items": items})
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe()
        sender_task.cancel()
