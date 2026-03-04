"""记忆管理路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from deps import require_auth
from stores import memory_store, serialize_memory
from models.requests import CompressReq, MemoryBatchDeleteReq

router = APIRouter(prefix="/api/memory", dependencies=[Depends(require_auth)])


@router.get("/{employee_id}")
async def list_memories(employee_id: str, query: str = "", limit: int = 20):
    if query:
        mems = memory_store.recall(employee_id, query, limit)
    else:
        mems = memory_store.recent(employee_id, limit)
    return {"memories": [serialize_memory(m) for m in mems]}


@router.get("/{employee_id}/important")
async def important_memories(employee_id: str, limit: int = 10):
    mems = memory_store.important(employee_id, limit)
    return {"memories": [serialize_memory(m) for m in mems]}


@router.get("/{employee_id}/count")
async def memory_count(employee_id: str):
    return {"count": memory_store.count(employee_id)}


@router.delete("/item/{memory_id}")
async def delete_memory(memory_id: str):
    if not memory_store.delete(memory_id):
        raise HTTPException(404, f"Memory {memory_id} not found")
    return {"status": "deleted"}


@router.post("/batch-delete")
async def batch_delete_memories(req: MemoryBatchDeleteReq):
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
async def compress_memories(employee_id: str, req: CompressReq):
    removed = memory_store.compress(employee_id, req.keep_top)
    return {"status": "compressed", "removed_count": removed}
