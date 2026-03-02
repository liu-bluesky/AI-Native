"""实时同步 MCP 服务入口"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from store import (
    SyncEventStore, SyncEvent,
    serialize_event, _now_iso,
)

DATA_DIR = Path(__file__).parent / "knowledge"

mcp = FastMCP("sync-service")
event_store = SyncEventStore(DATA_DIR)

VALID_UPDATE_TYPES = {"rule", "memory", "skill", "persona"}
VALID_NOTIFICATION_LEVELS = {"info", "warning", "success"}


# ── Tools ──

@mcp.tool()
def push_update(
    update_type: str, target_id: str, version: str,
    employee_ids: str = "",
) -> dict:
    """推送更新到 AI 员工"""
    if update_type not in VALID_UPDATE_TYPES:
        return {"error": f"Invalid update_type: {update_type}. Valid: {sorted(VALID_UPDATE_TYPES)}"}
    targets = [e.strip() for e in employee_ids.split(",") if e.strip()] if employee_ids else []
    if not targets:
        return {"error": "employee_ids is required"}
    events = []
    for emp_id in targets:
        evt = SyncEvent(
            id=event_store.new_id(), employee_id=emp_id,
            event_type=f"{update_type}_update",
            target_id=target_id, version=version, delivered=True,
        )
        event_store.save(evt)
        events.append(evt.id)
    return {"status": "pushed", "pushed_count": len(events),
            "update_type": update_type, "event_ids": events}


@mcp.tool()
def sync_state(employee_id: str) -> dict:
    """同步 AI 员工的完整状态"""
    evt = SyncEvent(
        id=event_store.new_id(), employee_id=employee_id,
        event_type="full_sync", delivered=True,
    )
    event_store.save(evt)
    total = event_store.count(employee_id)
    pending = event_store.pending_count(employee_id)
    return {
        "synced": True, "employee_id": employee_id,
        "total_events": total, "pending_events": pending,
    }


@mcp.tool()
def notify_agent(
    employee_id: str, message: str, level: str = "info",
) -> dict:
    """发送通知给 AI 员工"""
    if level not in VALID_NOTIFICATION_LEVELS:
        return {"error": f"Invalid level: {level}. Valid: {sorted(VALID_NOTIFICATION_LEVELS)}"}
    evt = SyncEvent(
        id=event_store.new_id(), employee_id=employee_id,
        event_type="notification", level=level,
        message=message, delivered=True,
    )
    event_store.save(evt)
    return {"notified": True, "employee_id": employee_id, "event_id": evt.id}


# ── Resources ──

@mcp.resource("sync://status/{employee_id}")
def sync_status(employee_id: str) -> str:
    """AI 员工的同步状态"""
    total = event_store.count(employee_id)
    pending = event_store.pending_count(employee_id)
    recent = event_store.list_by_employee(employee_id, limit=1)
    last_sync = recent[0].created_at if recent else "无"
    return (
        f"员工: {employee_id}\n"
        f"事件总数: {total}\n"
        f"待处理: {pending}\n"
        f"最后同步: {last_sync}"
    )


@mcp.resource("sync://events/{employee_id}")
def recent_events(employee_id: str) -> str:
    """AI 员工最近收到的同步事件"""
    events = event_store.list_by_employee(employee_id, limit=20)
    if not events:
        return f"员工 {employee_id} 暂无事件"
    lines = [f"[{e.created_at}] {e.event_type}: {e.target_id or e.message}" for e in events]
    return "\n".join(lines)


# ── Entry Point ──

if __name__ == "__main__":
    mcp.run()