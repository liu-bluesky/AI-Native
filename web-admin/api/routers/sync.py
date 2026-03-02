"""同步管理路由"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from deps import require_auth
from stores import sync_store, serialize_sync_event

router = APIRouter(prefix="/api/sync", dependencies=[Depends(require_auth)])


@router.get("/{employee_id}")
async def sync_events(employee_id: str, limit: int = 20):
    events = sync_store.list_by_employee(employee_id, limit)
    return {"events": [serialize_sync_event(e) for e in events]}


@router.get("/{employee_id}/stats")
async def sync_stats(employee_id: str):
    return {
        "total": sync_store.count(employee_id),
        "pending": sync_store.pending_count(employee_id),
    }
