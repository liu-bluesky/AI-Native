"""市场目录只读路由"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from core.auth import decode_token
from core.deps import employee_store, require_auth
from models.requests import (
    CliPluginInstallReq,
    CliPluginProfileInitReq,
    CliPluginProfileLoginReq,
    CliPluginProfileLogoutReq,
    CliPluginProfileSharingUpdateReq,
)
from services.cli_plugin_install_task_service import (
    create_install_task,
    get_install_task,
    list_install_tasks,
    subscribe_install_task_events,
)
from services.operation_wait_task_service import (
    create_login_task,
    get_login_task,
    list_login_tasks,
    subscribe_login_task_events,
)
from services.cli_plugin_market_service import install_cli_plugin, list_cli_plugins
from services.cli_plugin_profile_service import (
    _default_cli_plugin_login_command,
    _default_cli_plugin_logout_command,
    _default_cli_plugin_test_command,
    ensure_cli_plugin_profile,
    execute_cli_plugin_profile_command,
    serialize_cli_plugin_profile,
    update_cli_plugin_profile,
)
from stores.mcp_bridge import rule_store, skill_store

router = APIRouter(prefix="/api/market", dependencies=[Depends(require_auth)])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _build_cli_plugin_runtime_diagnostics(item: dict[str, Any]) -> dict[str, Any]:
    install_status = (
        item.get("install_status")
        if isinstance(item.get("install_status"), dict)
        else {}
    )
    my_profile = item.get("my_profile") if isinstance(item.get("my_profile"), dict) else {}
    toolchain = (
        install_status.get("toolchain")
        if isinstance(install_status.get("toolchain"), dict)
        else {}
    )
    health = (
        install_status.get("health")
        if isinstance(install_status.get("health"), dict)
        else {}
    )
    toolchain_root = str(toolchain.get("toolchain_root") or "").strip()
    toolchain_bin_dir = str(toolchain.get("toolchain_bin_dir") or "").strip()
    preferred_binary_path = str(
        install_status.get("preferred_binary_path")
        or toolchain.get("plugin_binary_path")
        or ""
    ).strip()
    runtime_root = str(my_profile.get("runtime_root") or "").strip()
    home_dir = str(my_profile.get("home_dir") or "").strip()
    config_dir = str(my_profile.get("config_dir") or "").strip()
    cache_dir = str(my_profile.get("cache_dir") or "").strip()
    installed = install_status.get("installed") is True
    locked_version = str(install_status.get("locked_version") or "").strip()
    health_status = str(health.get("status") or "").strip()
    health_status_label = str(health.get("status_label") or "").strip()
    health_checks = health.get("checks") if isinstance(health.get("checks"), list) else []
    missing_required = (
        health.get("missing_required")
        if isinstance(health.get("missing_required"), list)
        else []
    )

    summary_parts: list[str] = []
    if toolchain_root:
        summary_parts.append(f"共享工具链目录 {toolchain_root}")
    if runtime_root:
        summary_parts.append(f"当前用户隔离目录 {runtime_root}")
    if locked_version:
        summary_parts.append(f"锁定版本 {locked_version}")
    if health_status_label:
        summary_parts.append(f"健康状态 {health_status_label}")

    return {
        "mode": "shared_toolchain_per_user_runtime",
        "mode_label": "共享安装 + 用户隔离",
        "installed": installed,
        "locked_version": locked_version,
        "lock_source": str(install_status.get("lock_source") or "").strip(),
        "health_status": health_status,
        "health_status_label": health_status_label,
        "health_checks": health_checks,
        "missing_required": missing_required,
        "toolchain_root": toolchain_root,
        "toolchain_bin_dir": toolchain_bin_dir,
        "preferred_binary_path": preferred_binary_path,
        "runtime_root": runtime_root,
        "home_dir": home_dir,
        "config_dir": config_dir,
        "cache_dir": cache_dir,
        "summary": "；".join(summary_parts),
    }


def _attach_cli_plugin_profile(items: list[dict[str, Any]], username: str) -> list[dict[str, Any]]:
    normalized_username = _current_username({"sub": username})
    if not normalized_username:
        return items
    hydrated: list[dict[str, Any]] = []
    for item in items:
        plugin_id = str(item.get("id") or "").strip()
        if not plugin_id:
            hydrated.append(dict(item))
            continue
        current = dict(item)
        try:
            current["my_profile"] = serialize_cli_plugin_profile(
                plugin_id,
                normalized_username,
                auth_payload={"sub": normalized_username},
            )
        except ValueError:
            current["my_profile"] = None
        current["runtime_diagnostics"] = _build_cli_plugin_runtime_diagnostics(current)
        hydrated.append(current)
    return hydrated


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
async def get_market_catalog(auth_payload: dict = Depends(require_auth)):
    rules = _sort_records(rule_store.list_all())
    employees = _sort_records(employee_store.list_all())
    skills = _sort_records(skill_store.list_all())
    cli_plugins = await run_in_threadpool(list_cli_plugins)
    cli_plugins = _attach_cli_plugin_profile(cli_plugins, _current_username(auth_payload))

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
async def get_cli_plugin_catalog(auth_payload: dict = Depends(require_auth)):
    items = await run_in_threadpool(list_cli_plugins)
    items = _attach_cli_plugin_profile(items, _current_username(auth_payload))
    return {
        "items": items,
        "meta": {
            "cli_plugin_count": len(items),
        },
    }


@router.get("/cli-plugins/{plugin_id}/profiles/me")
async def get_market_cli_plugin_my_profile(
    plugin_id: str,
    auth_payload: dict = Depends(require_auth),
):
    username = _current_username(auth_payload)
    if not username:
        raise HTTPException(401, "Missing or invalid token")
    try:
        profile = await run_in_threadpool(
            serialize_cli_plugin_profile,
            str(plugin_id or "").strip(),
            username,
            auth_payload=auth_payload,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"profile": profile}


@router.post("/cli-plugins/{plugin_id}/profiles/me/init")
async def init_market_cli_plugin_my_profile(
    plugin_id: str,
    req: CliPluginProfileInitReq,
    auth_payload: dict = Depends(require_auth),
):
    username = _current_username(auth_payload)
    normalized_plugin_id = str(req.plugin_id or plugin_id or "").strip()
    try:
        await run_in_threadpool(
            ensure_cli_plugin_profile,
            normalized_plugin_id,
            username,
            actor_username=username,
        )
        profile = await run_in_threadpool(
            serialize_cli_plugin_profile,
            normalized_plugin_id,
            username,
            auth_payload=auth_payload,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "initialized", "profile": profile}


@router.post("/cli-plugins/{plugin_id}/profiles/me/login")
async def login_market_cli_plugin_my_profile(
    plugin_id: str,
    req: CliPluginProfileLoginReq,
    auth_payload: dict = Depends(require_auth),
):
    try:
        task = await run_in_threadpool(
            create_login_task,
            str(req.plugin_id or plugin_id or "").strip(),
            username=_current_username(auth_payload),
            login_command=str(req.login_command or "").strip(),
            metadata=dict(req.metadata or {}),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "status": "accepted",
        "task": task,
    }


@router.post("/cli-plugins/{plugin_id}/profiles/me/logout")
async def logout_market_cli_plugin_my_profile(
    plugin_id: str,
    req: CliPluginProfileLogoutReq,
    auth_payload: dict = Depends(require_auth),
):
    username = _current_username(auth_payload)
    normalized_plugin_id = str(req.plugin_id or plugin_id or "").strip()
    command = str(req.logout_command or "").strip() or _default_cli_plugin_logout_command(normalized_plugin_id)
    try:
        execution = await run_in_threadpool(
            execute_cli_plugin_profile_command,
            normalized_plugin_id,
            username,
            command=command,
        )
        await run_in_threadpool(
            update_cli_plugin_profile,
            normalized_plugin_id,
            username,
            status="ready" if execution.get("ok") else "authenticated",
            status_label="已退出" if execution.get("ok") else "退出失败",
            logout_command=command,
            last_logout_at=str(req.metadata.get("last_logout_at") or "").strip() or _now_iso(),
            last_error="" if execution.get("ok") else str(execution.get("stderr") or execution.get("stdout") or "").strip(),
            metadata={**dict(req.metadata or {}), "last_execution": execution},
        )
        profile = await run_in_threadpool(
            serialize_cli_plugin_profile,
            normalized_plugin_id,
            username,
            auth_payload=auth_payload,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "logged_out" if execution.get("ok") else "failed", "profile": profile, "execution": execution}


@router.post("/cli-plugins/{plugin_id}/profiles/me/test")
async def test_market_cli_plugin_my_profile(
    plugin_id: str,
    auth_payload: dict = Depends(require_auth),
):
    username = _current_username(auth_payload)
    normalized_plugin_id = str(plugin_id or "").strip()
    command = _default_cli_plugin_test_command(normalized_plugin_id)
    try:
        execution = await run_in_threadpool(
            execute_cli_plugin_profile_command,
            normalized_plugin_id,
            username,
            command=command,
        )
        await run_in_threadpool(
            update_cli_plugin_profile,
            normalized_plugin_id,
            username,
            status="authenticated" if execution.get("ok") else "authenticated",
            status_label="可用" if execution.get("ok") else "检测失败",
            test_command=command,
            last_test_at=_now_iso(),
            last_test_ok=bool(execution.get("ok")),
            last_error="" if execution.get("ok") else str(execution.get("stderr") or execution.get("stdout") or "").strip(),
            metadata={"last_execution": execution},
        )
        profile = await run_in_threadpool(
            serialize_cli_plugin_profile,
            normalized_plugin_id,
            username,
            auth_payload=auth_payload,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "ok" if execution.get("ok") else "failed", "profile": profile, "execution": execution}


@router.patch("/cli-plugins/{plugin_id}/profiles/me/sharing")
async def update_market_cli_plugin_my_profile_sharing(
    plugin_id: str,
    req: CliPluginProfileSharingUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    username = _current_username(auth_payload)
    normalized_plugin_id = str(plugin_id or "").strip()
    try:
        await run_in_threadpool(
            update_cli_plugin_profile,
            normalized_plugin_id,
            username,
            share_scope=req.share_scope,
            shared_with_usernames=list(req.shared_with_usernames or []),
        )
        profile = await run_in_threadpool(
            serialize_cli_plugin_profile,
            normalized_plugin_id,
            username,
            auth_payload=auth_payload,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "updated", "profile": profile}


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


@router.post("/cli-plugins/login-tasks", status_code=202)
async def create_market_cli_plugin_login_task(
    req: CliPluginProfileLoginReq,
    auth_payload: dict = Depends(require_auth),
):
    try:
        task = await run_in_threadpool(
            create_login_task,
            str(req.plugin_id or "").strip(),
            username=_current_username(auth_payload),
            login_command=str(req.login_command or "").strip(),
            metadata=dict(req.metadata or {}),
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


@router.get("/cli-plugins/login-tasks")
async def list_market_cli_plugin_login_tasks(
    limit: int = Query(default=20, ge=1, le=200),
    auth_payload: dict = Depends(require_auth),
):
    items = await run_in_threadpool(
        list_login_tasks,
        username=_current_username(auth_payload),
        limit=limit,
    )
    return {
        "items": items,
        "meta": {
            "count": len(items),
        },
    }


@router.get("/cli-plugins/login-tasks/{task_id}")
async def get_market_cli_plugin_login_task(
    task_id: str,
    auth_payload: dict = Depends(require_auth),
):
    task = await run_in_threadpool(get_login_task, task_id)
    if task is None:
        raise HTTPException(404, "Login task not found")
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


@router.websocket("/cli-plugins/login-tasks/ws")
async def ws_market_cli_plugin_login_tasks(websocket: WebSocket):
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
    unsubscribe = subscribe_login_task_events(
        username,
        lambda payload: loop.call_soon_threadsafe(queue.put_nowait, payload),
    )

    initial_items = await run_in_threadpool(
        list_login_tasks,
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
                    list_login_tasks,
                    username=username,
                    limit=20,
                )
                await websocket.send_json({"type": "task_snapshot", "items": items})
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe()
        sender_task.cancel()
