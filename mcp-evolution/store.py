"""进化引擎存储层 — 数据模型与 CRUD"""

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
class EvolutionCandidate:
    id: str
    employee_id: str
    title: str
    description: str
    pattern_id: str = ""
    confidence: float = 0.0
    risk_domain: str = "low"
    status: str = "pending"  # pending | approved | rejected
    source_type: str = "auto-evolved"
    proposed_rule: dict = field(default_factory=dict)
    block_reasons: tuple[str, ...] = ()
    reviewed_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class EvolutionEvent:
    id: str
    employee_id: str
    event_type: str  # rule_promoted | candidate_created | candidate_rejected
    target_id: str = ""
    detail: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class UsageLog:
    id: str
    employee_id: str
    action: str  # rule_applied | rule_rejected | correction | query
    rule_id: str = ""
    context: str = ""
    corrected: bool = False
    created_at: str = field(default_factory=_now_iso)


# ── Serialization ──

def serialize_candidate(c: EvolutionCandidate) -> dict:
    d = asdict(c)
    d["block_reasons"] = list(c.block_reasons)
    return d


def _deserialize_candidate(data: dict) -> EvolutionCandidate:
    return EvolutionCandidate(
        id=data["id"], employee_id=data["employee_id"],
        title=data["title"], description=data["description"],
        pattern_id=data.get("pattern_id", ""),
        confidence=data.get("confidence", 0.0),
        risk_domain=data.get("risk_domain", "low"),
        status=data.get("status", "pending"),
        source_type=data.get("source_type", "auto-evolved"),
        proposed_rule=data.get("proposed_rule", {}),
        block_reasons=tuple(data.get("block_reasons", [])),
        reviewed_by=data.get("reviewed_by", ""),
        created_at=data.get("created_at", _now_iso()),
        updated_at=data.get("updated_at", _now_iso()),
    )


# ── CandidateStore ──

class CandidateStore:
    """基于 JSON 文件的候选规则存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "candidates"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, cid: str) -> Path:
        return self._dir / f"{cid}.json"

    def save(self, c: EvolutionCandidate) -> None:
        self._path(c.id).write_text(
            json.dumps(serialize_candidate(c), ensure_ascii=False, indent=2))

    def get(self, cid: str) -> Optional[EvolutionCandidate]:
        path = self._path(cid)
        if not path.exists():
            return None
        return _deserialize_candidate(json.loads(path.read_text()))

    def list_by_employee(self, employee_id: str,
                         status: str = "") -> list[EvolutionCandidate]:
        results = []
        for p in sorted(self._dir.glob("*.json")):
            data = json.loads(p.read_text())
            if data.get("employee_id") != employee_id:
                continue
            if status and data.get("status") != status:
                continue
            results.append(_deserialize_candidate(data))
        return sorted(results, key=lambda c: c.created_at, reverse=True)

    def list_pending(self, min_confidence: float = 0.0,
                     limit: int = 200) -> list[EvolutionCandidate]:
        results = []
        for p in sorted(self._dir.glob("*.json")):
            data = json.loads(p.read_text())
            if data.get("status") != "pending":
                continue
            if data.get("confidence", 0.0) >= min_confidence:
                results.append(_deserialize_candidate(data))
        results.sort(key=lambda c: c.confidence, reverse=True)
        return results[:limit]

    def delete(self, cid: str) -> bool:
        path = self._path(cid)
        if path.exists():
            path.unlink()
            return True
        return False

    def new_id(self) -> str:
        return f"cand-{uuid.uuid4().hex[:8]}"


# ── EventStore ──

class EventStore:
    """进化事件日志存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "events"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, eid: str) -> Path:
        return self._dir / f"{eid}.json"

    def save(self, e: EvolutionEvent) -> None:
        self._path(e.id).write_text(
            json.dumps(asdict(e), ensure_ascii=False, indent=2))

    def list_by_employee(self, employee_id: str,
                         limit: int = 50) -> list[EvolutionEvent]:
        results = []
        for p in sorted(self._dir.glob("*.json"), reverse=True):
            data = json.loads(p.read_text())
            if data.get("employee_id") == employee_id:
                results.append(EvolutionEvent(**data))
            if len(results) >= limit:
                break
        return results

    def new_id(self) -> str:
        return f"evt-{uuid.uuid4().hex[:8]}"


# ── UsageLogStore ──

class UsageLogStore:
    """使用日志存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "usage_logs"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, lid: str) -> Path:
        return self._dir / f"{lid}.json"

    def save(self, log: UsageLog) -> None:
        self._path(log.id).write_text(
            json.dumps(asdict(log), ensure_ascii=False, indent=2))

    def list_by_employee(self, employee_id: str,
                         limit: int = 500) -> list[UsageLog]:
        results = []
        for p in sorted(self._dir.glob("*.json"), reverse=True):
            data = json.loads(p.read_text())
            if data.get("employee_id") == employee_id:
                results.append(UsageLog(**data))
            if len(results) >= limit:
                break
        return results

    def new_id(self) -> str:
        return f"log-{uuid.uuid4().hex[:8]}"
