"""记忆管理路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from core.deps import employee_store, is_admin_like, project_store, require_auth
from core.ownership import assert_can_view_record, current_username
from stores.mcp_bridge import memory_store, serialize_memory
from models.requests import CompressReq, MemoryBatchDeleteReq

router = APIRouter(prefix="/api/memory", dependencies=[Depends(require_auth)])


def _normalize_project_token(value: str | None) -> str:
    return str(value or "").strip().lower()


def _ensure_employee_view_access(employee_id: str, auth_payload: dict):
    employee = employee_store.get(employee_id)
    if employee is None:
        raise HTTPException(404, f"Employee {employee_id} not found")
    assert_can_view_record(employee, auth_payload, "Employee")
    return employee


def _visible_project_tokens(auth_payload: dict) -> set[str] | None:
    if is_admin_like(auth_payload):
        return None
    username = current_username(auth_payload)
    if not username:
        return set()
    tokens: set[str] = set()
    for project in project_store.list_all():
        member = project_store.get_user_member(project.id, username)
        if member is None or not bool(getattr(member, "enabled", True)):
            continue
        project_id_token = _normalize_project_token(getattr(project, "id", ""))
        project_name_token = _normalize_project_token(getattr(project, "name", ""))
        if project_id_token:
            tokens.add(project_id_token)
        if project_name_token:
            tokens.add(project_name_token)
    return tokens


def _can_view_memory(memory, auth_payload: dict, *, requested_project_name: str = "") -> bool:
    visible_projects = _visible_project_tokens(auth_payload)
    memory_project = _normalize_project_token(getattr(memory, "project_name", ""))
    requested_project = _normalize_project_token(requested_project_name)
    if requested_project and memory_project != requested_project:
        return False
    if visible_projects is None:
        return True
    if not memory_project:
        return not requested_project
    return memory_project in visible_projects


def _list_visible_memories(
    employee_id: str,
    auth_payload: dict,
    *,
    query: str = "",
    project_name: str = "",
) -> list:
    _ensure_employee_view_access(employee_id, auth_payload)
    query_text = str(query or "").strip().lower()
    visible = []
    for memory in memory_store.list_by_employee(employee_id):
        if not _can_view_memory(memory, auth_payload, requested_project_name=project_name):
            continue
        if query_text and query_text not in str(getattr(memory, "content", "") or "").lower():
            continue
        visible.append(memory)
    return visible


def _ensure_memory_view_access(memory_id: str, auth_payload: dict):
    memory = memory_store.get(memory_id)
    if memory is None:
        raise HTTPException(404, f"Memory {memory_id} not found")
    _ensure_employee_view_access(str(getattr(memory, "employee_id", "")), auth_payload)
    if not _can_view_memory(memory, auth_payload):
        raise HTTPException(404, f"Memory {memory_id} not found")
    return memory


@router.get("/{employee_id}")
async def list_memories(
    employee_id: str,
    query: str = "",
    project_name: str = "",
    limit: int = 20,
    auth_payload: dict = Depends(require_auth),
):
    safe_limit = max(1, min(int(limit), 200))
    mems = _list_visible_memories(employee_id, auth_payload, query=query, project_name=project_name)
    if query:
        mems = sorted(mems, key=lambda item: float(getattr(item, "importance", 0.0) or 0.0), reverse=True)
    else:
        mems = sorted(mems, key=lambda item: str(getattr(item, "created_at", "") or ""), reverse=True)
    mems = mems[:safe_limit]
    return {"memories": [serialize_memory(m) for m in mems]}


@router.get("/{employee_id}/important")
async def important_memories(
    employee_id: str,
    project_name: str = "",
    limit: int = 10,
    auth_payload: dict = Depends(require_auth),
):
    safe_limit = max(1, min(int(limit), 200))
    mems = [
        item
        for item in _list_visible_memories(employee_id, auth_payload, project_name=project_name)
        if float(getattr(item, "importance", 0.0) or 0.0) >= 0.7
    ]
    mems = sorted(mems, key=lambda item: float(getattr(item, "importance", 0.0) or 0.0), reverse=True)[:safe_limit]
    return {"memories": [serialize_memory(m) for m in mems]}


@router.get("/{employee_id}/count")
async def memory_count(
    employee_id: str,
    project_name: str = "",
    auth_payload: dict = Depends(require_auth),
):
    mems = _list_visible_memories(employee_id, auth_payload, project_name=project_name)
    return {"count": len(mems)}


@router.delete("/item/{memory_id}")
async def delete_memory(memory_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_memory_view_access(memory_id, auth_payload)
    if not memory_store.delete(memory_id):
        raise HTTPException(404, f"Memory {memory_id} not found")
    return {"status": "deleted"}


@router.post("/batch-delete")
async def batch_delete_memories(req: MemoryBatchDeleteReq, auth_payload: dict = Depends(require_auth)):
    requested_ids = [str(item or "").strip() for item in (req.memory_ids or [])]
    requested_ids = [item for item in requested_ids if item]
    seen: set[str] = set()
    normalized_ids: list[str] = []
    for item in requested_ids:
        if item in seen:
            continue
        seen.add(item)
        normalized_ids.append(item)
    if not normalized_ids:
        raise HTTPException(400, "memory_ids is required")

    employee_id = str(req.employee_id or "").strip()
    deleted_ids: list[str] = []
    missing_ids: list[str] = []
    skipped_ids: list[str] = []
    for memory_id in normalized_ids:
        memory = memory_store.get(memory_id)
        if memory is None:
            missing_ids.append(memory_id)
            continue
        try:
            _ensure_memory_view_access(memory_id, auth_payload)
        except HTTPException:
            skipped_ids.append(memory_id)
            continue
        if employee_id and str(getattr(memory, "employee_id", "")) != employee_id:
            skipped_ids.append(memory_id)
            continue
        if memory_store.delete(memory_id):
            deleted_ids.append(memory_id)
        else:
            skipped_ids.append(memory_id)
    return {
        "status": "deleted",
        "requested_count": len(normalized_ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "missing_ids": missing_ids,
        "skipped_ids": skipped_ids,
    }


@router.post("/{employee_id}/compress")
async def compress_memories(
    employee_id: str,
    req: CompressReq,
    project_name: str = "",
    auth_payload: dict = Depends(require_auth),
):
    keep_top = max(0, int(req.keep_top))
    mems = _list_visible_memories(employee_id, auth_payload, project_name=project_name)
    if len(mems) <= keep_top:
        return {"status": "compressed", "removed_count": 0}
    sorted_mems = sorted(mems, key=lambda item: float(getattr(item, "importance", 0.0) or 0.0), reverse=True)
    removed = 0
    for memory in sorted_mems[keep_top:]:
        if memory_store.delete(str(getattr(memory, "id", ""))):
            removed += 1
    return {"status": "compressed", "removed_count": removed}
