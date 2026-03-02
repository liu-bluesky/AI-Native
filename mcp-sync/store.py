"""同步推送存储层 — 数据模型与事件日志"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Data Models ──

@dataclass(frozen=True)
class SyncEvent:
    id: str
    employee_id: str
    event_type: str  # rule_update | memory_update | skill_update | persona_update | notification | full_sync
    target_id: str = ""
    version: str = ""
    level: str = "info"
    message: str = ""
    detail: dict = field(default_factory=dict)
    delivered: bool = False
    created_at: str = field(default_factory=_now_iso)


# ── Serialization ──

def serialize_event(e: SyncEvent) -> dict:
    return asdict(e)


def _deserialize_event(data: dict) -> SyncEvent:
    return SyncEvent(
        id=data["id"], employee_id=data["employee_id"],
        event_type=data["event_type"],
        target_id=data.get("target_id", ""),
        version=data.get("version", ""),
        level=data.get("level", "info"),
        message=data.get("message", ""),
        detail=data.get("detail", {}),
        delivered=data.get("delivered", False),
        created_at=data.get("created_at", _now_iso()),
    )


# ── SyncEventStore ──

class SyncEventStore:
    """基于 JSON 文件的同步事件存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "sync_events"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, eid: str) -> Path:
        return self._dir / f"{eid}.json"

    def save(self, e: SyncEvent) -> None:
        self._path(e.id).write_text(
            json.dumps(serialize_event(e), ensure_ascii=False, indent=2))

    def get(self, eid: str) -> Optional[SyncEvent]:
        path = self._path(eid)
        if not path.exists():
            return None
        return _deserialize_event(json.loads(path.read_text()))

    def list_by_employee(self, employee_id: str,
                         limit: int = 20) -> list[SyncEvent]:
        results = []
        for p in sorted(self._dir.glob("*.json"), reverse=True):
            data = json.loads(p.read_text())
            if data.get("employee_id") == employee_id:
                results.append(_deserialize_event(data))
            if len(results) >= limit:
                break
        return results

    def count(self, employee_id: str) -> int:
        total = 0
        for p in self._dir.glob("*.json"):
            data = json.loads(p.read_text())
            if data.get("employee_id") == employee_id:
                total += 1
        return total

    def pending_count(self, employee_id: str) -> int:
        total = 0
        for p in self._dir.glob("*.json"):
            data = json.loads(p.read_text())
            if data.get("employee_id") == employee_id and not data.get("delivered", False):
                total += 1
        return total

    def new_id(self) -> str:
        return f"sync-{uuid.uuid4().hex[:8]}"
