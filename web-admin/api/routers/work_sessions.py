"""工作会话轨迹查看路由"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query

from core.deps import employee_store, ensure_permission, project_store, require_auth, work_session_store
from stores.mcp_bridge import memory_store
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


def _normalize_project_token(value: object) -> str:
    return str(value or "").strip().lower()


def _project_name_to_id_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in project_store.list_all():
        project_id = _normalize_text(getattr(item, "id", ""), 80)
        project_name = _normalize_text(getattr(item, "name", ""), 120)
        if project_id:
            mapping[_normalize_project_token(project_id)] = project_id
        if project_name:
            mapping[_normalize_project_token(project_name)] = project_id
    return mapping


def _normalize_purpose_tags(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item or "").strip().lower() for item in value if str(item or "").strip())
    return ()


def _memory_minute_bucket(value: object) -> str:
    return _normalize_text(value, 19)[:16]


def _build_memory_backed_session_item(memory, *, project_id: str, session_id: str) -> dict:
    created_at = _normalize_text(getattr(memory, "created_at", ""), 40)
    return {
        "id": _normalize_text(getattr(memory, "id", ""), 80),
        "project_id": project_id,
        "project_name": _normalize_text(getattr(memory, "project_name", ""), 120),
        "employee_id": _normalize_text(getattr(memory, "employee_id", ""), 80),
        "session_id": session_id,
        "source_kind": "project-memory",
        "event_type": _normalize_text(getattr(getattr(memory, "type", ""), "value", getattr(memory, "type", "")), 40),
        "phase": "",
        "step": "",
        "status": "saved",
        "goal": "",
        "content": _normalize_text(getattr(memory, "content", ""), 4000),
        "facts": [],
        "changed_files": [],
        "verification": [],
        "risks": [],
        "next_steps": [],
        "created_at": created_at,
        "updated_at": created_at,
    }


def _build_memory_backed_session_summary(memory, *, project_id: str, session_id: str, duplicate_count: int) -> dict:
    created_at = _normalize_text(getattr(memory, "created_at", ""), 40)
    event_type = _normalize_text(getattr(getattr(memory, "type", ""), "value", getattr(memory, "type", "")), 40)
    return {
        "session_id": session_id,
        "project_id": project_id,
        "project_name": _normalize_text(getattr(memory, "project_name", ""), 120),
        "employee_id": _normalize_text(getattr(memory, "employee_id", ""), 80),
        "latest_status": "saved",
        "latest_event_type": event_type,
        "goal": "",
        "phases": [],
        "steps": [],
        "event_types": [event_type] if event_type else [],
        "changed_files": [],
        "verification": [],
        "risks": [],
        "next_steps": [],
        "event_count": max(1, duplicate_count),
        "updated_at": created_at,
        "created_at": created_at,
    }


def _list_accessible_memories() -> list[object]:
    list_all = getattr(memory_store, "list_all", None)
    if callable(list_all):
        return list(list_all())
    list_by_employee = getattr(memory_store, "list_by_employee", None)
    if not callable(list_by_employee):
        return []
    seen_memory_ids: set[str] = set()
    memories: list[object] = []
    for employee in employee_store.list_all():
        normalized_employee_id = _normalize_text(getattr(employee, "id", ""), 80)
        if not normalized_employee_id:
            continue
        for memory in list_by_employee(normalized_employee_id) or []:
            memory_id = _normalize_text(getattr(memory, "id", ""), 80)
            dedupe_key = memory_id or json.dumps(
                [
                    normalized_employee_id,
                    _normalize_text(getattr(memory, "project_name", ""), 120),
                    _normalize_text(getattr(memory, "created_at", ""), 40),
                    _normalize_text(getattr(memory, "content", ""), 4000),
                ],
                ensure_ascii=False,
            )
            if dedupe_key in seen_memory_ids:
                continue
            seen_memory_ids.add(dedupe_key)
            memories.append(memory)
    return memories


def _list_memory_backed_sessions(
    *,
    project_id: str = "",
    employee_id: str = "",
    query: str = "",
    limit: int = 200,
) -> list[dict]:
    normalized_project_id = _normalize_text(project_id, 80)
    normalized_employee_id = _normalize_text(employee_id, 80)
    keyword = _normalize_text(query, 200).lower()
    project_lookup = _project_name_to_id_map()
    grouped: dict[str, dict] = {}
    for memory in _list_accessible_memories():
        purpose_tags = _normalize_purpose_tags(getattr(memory, "purpose_tags", ()))
        if "query-mcp" not in purpose_tags or "manual-write" not in purpose_tags:
            continue
        memory_employee_id = _normalize_text(getattr(memory, "employee_id", ""), 80)
        if normalized_employee_id and memory_employee_id != normalized_employee_id:
            continue
        memory_project_name = _normalize_text(getattr(memory, "project_name", ""), 120)
        resolved_project_id = project_lookup.get(_normalize_project_token(memory_project_name), "")
        if normalized_project_id and normalized_project_id not in {resolved_project_id, memory_project_name}:
            continue
        content = _normalize_text(getattr(memory, "content", ""), 4000)
        event_type = _normalize_text(getattr(getattr(memory, "type", ""), "value", getattr(memory, "type", "")), 40)
        if keyword:
            haystack = "\n".join(
                [
                    memory_project_name,
                    resolved_project_id,
                    memory_employee_id,
                    event_type,
                    content,
                ]
            ).lower()
            if keyword not in haystack:
                continue
        group_seed = json.dumps(
            [
                resolved_project_id,
                memory_project_name,
                event_type,
                content,
                _memory_minute_bucket(getattr(memory, "created_at", "")),
            ],
            ensure_ascii=False,
        )
        session_id = f"memory-{hashlib.sha1(group_seed.encode('utf-8')).hexdigest()[:12]}"
        created_at = _normalize_text(getattr(memory, "created_at", ""), 40)
        existing = grouped.get(session_id)
        if existing is None or created_at > existing["created_at"]:
            grouped[session_id] = {
                "created_at": created_at,
                "memory": memory,
                "summary": _build_memory_backed_session_summary(
                    memory,
                    project_id=resolved_project_id,
                    session_id=session_id,
                    duplicate_count=(existing or {}).get("duplicate_count", 0) + 1,
                ),
                "item": _build_memory_backed_session_item(
                    memory,
                    project_id=resolved_project_id,
                    session_id=session_id,
                ),
                "duplicate_count": (existing or {}).get("duplicate_count", 0) + 1,
            }
            grouped[session_id]["summary"]["event_count"] = grouped[session_id]["duplicate_count"]
        else:
            existing["duplicate_count"] += 1
            existing["summary"]["event_count"] = existing["duplicate_count"]
    items = [item for item in grouped.values()]
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items[: _coerce_limit(limit, default=200, maximum=500)]


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
    synthetic_sessions = [
        item["summary"]
        for item in _list_memory_backed_sessions(
            project_id=_normalize_text(project_id, 80),
            employee_id=_normalize_text(employee_id, 80),
            query=_normalize_text(query, 200),
            limit=_coerce_limit(limit, default=200, maximum=500),
        )
    ]
    sessions.extend(synthetic_sessions)
    sessions.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {"items": sessions[: _coerce_limit(limit)]}


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
        synthetic_sessions = _list_memory_backed_sessions(
            project_id=_normalize_text(project_id, 80),
            employee_id=_normalize_text(employee_id, 80),
            limit=_coerce_limit(limit, default=200, maximum=500),
        )
        matched = next(
            (item for item in synthetic_sessions if item["summary"]["session_id"] == normalized_session_id),
            None,
        )
        if matched is None:
            raise HTTPException(404, "Work session not found")
        return {
            "session": matched["summary"],
            "items": [matched["item"]],
        }
    ordered = sorted(events, key=lambda item: (item.created_at, item.id), reverse=True)
    return {
        "session": _session_summary(ordered),
        "items": [asdict(item) for item in ordered],
    }
