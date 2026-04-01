"""工作会话轨迹查看路由"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from core.deps import employee_store, ensure_permission, project_store, require_auth, work_session_store
from stores.json.work_session_store import WorkSessionEvent


router = APIRouter(prefix="/api/work-sessions")
public_router = None


def _require_work_session_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.system.work_sessions")


def _normalize_text(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _coerce_limit(value: int | None, *, default: int = 50, minimum: int = 1, maximum: int = 200) -> int:
    try:
        return max(minimum, min(int(value or default), maximum))
    except (TypeError, ValueError):
        return default


def _session_summary(events: list[WorkSessionEvent]) -> dict:
    if not events:
        return {}
    ordered = sorted(events, key=lambda item: (item.created_at, item.id), reverse=True)
    latest = ordered[0]
    phases: list[str] = []
    steps: list[str] = []
    changed_files: list[str] = []
    verification: list[str] = []
    risks: list[str] = []
    next_steps: list[str] = []
    event_types: list[str] = []
    for item in ordered:
        if item.phase and item.phase not in phases:
            phases.append(item.phase)
        if item.step and item.step not in steps:
            steps.append(item.step)
        if item.event_type and item.event_type not in event_types:
            event_types.append(item.event_type)
        for source, target in (
            (item.changed_files, changed_files),
            (item.verification, verification),
            (item.risks, risks),
            (item.next_steps, next_steps),
        ):
            for value in source:
                if value not in target:
                    target.append(value)
    return {
        "session_id": latest.session_id,
        "project_id": latest.project_id,
        "project_name": latest.project_name,
        "employee_id": latest.employee_id,
        "latest_status": latest.status,
        "latest_event_type": latest.event_type,
        "goal": latest.goal,
        "phases": phases,
        "steps": steps,
        "event_types": event_types,
        "changed_files": changed_files,
        "verification": verification,
        "risks": risks,
        "next_steps": next_steps,
        "event_count": len(ordered),
        "updated_at": latest.updated_at,
        "created_at": ordered[-1].created_at,
    }


@router.get("")
async def list_work_sessions(
    project_id: str = Query("", max_length=80),
    employee_id: str = Query("", max_length=80),
    query: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=200),
    _: None = Depends(_require_work_session_permission),
):
    events = work_session_store.list_events(
        project_id=_normalize_text(project_id, 80),
        employee_id=_normalize_text(employee_id, 80),
        query=_normalize_text(query, 200),
        limit=_coerce_limit(limit),
    )
    grouped: dict[str, list[WorkSessionEvent]] = {}
    for item in events:
        grouped.setdefault(item.session_id, []).append(item)
    sessions = [_session_summary(items) for items in grouped.values() if items]
    sessions.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {"items": sessions}


@router.get("/meta")
async def get_work_session_filter_meta(
    _: None = Depends(_require_work_session_permission),
):
    projects = [
        {
            "id": str(item.id or "").strip(),
            "name": str(item.name or "").strip(),
        }
        for item in project_store.list_all()
        if str(item.id or "").strip()
    ]
    employees = [
        {
            "id": str(item.id or "").strip(),
            "name": str(item.name or "").strip(),
        }
        for item in employee_store.list_all()
        if str(item.id or "").strip()
    ]
    projects.sort(key=lambda item: (item["name"] or item["id"], item["id"]))
    employees.sort(key=lambda item: (item["name"] or item["id"], item["id"]))
    return {"projects": projects, "employees": employees}


@router.get("/{session_id}")
async def get_work_session_detail(
    session_id: str,
    project_id: str = Query("", max_length=80),
    employee_id: str = Query("", max_length=80),
    limit: int = Query(200, ge=1, le=500),
    _: None = Depends(_require_work_session_permission),
):
    normalized_session_id = _normalize_text(session_id, 80)
    events = work_session_store.list_events(
        project_id=_normalize_text(project_id, 80),
        employee_id=_normalize_text(employee_id, 80),
        session_id=normalized_session_id,
        limit=_coerce_limit(limit, default=200, maximum=500),
    )
    if not events:
        raise HTTPException(404, "Work session not found")
    ordered = sorted(events, key=lambda item: (item.created_at, item.id), reverse=True)
    return {
        "session": _session_summary(ordered),
        "items": [asdict(item) for item in ordered],
    }
