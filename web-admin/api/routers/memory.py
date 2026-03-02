"""记忆管理路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from deps import require_auth
from stores import memory_store, serialize_memory
from models.requests import CompressReq

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


@router.post("/{employee_id}/compress")
async def compress_memories(employee_id: str, req: CompressReq):
    removed = memory_store.compress(employee_id, req.keep_top)
    return {"status": "compressed", "removed_count": removed}
