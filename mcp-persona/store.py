"""人设存储层 — 数据模型与 CRUD"""

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
class DelegationScope:
    auto_approve: tuple[str, ...] = ()
    require_confirmation: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    principle: str = "delegation_cannot_escalate"


@dataclass(frozen=True)
class DecisionPolicy:
    priority_order: tuple[str, ...] = ("correctness", "security", "maintainability", "speed")
    risk_preference: str = "balanced"
    uncertain_action: str = "ask_for_confirmation"
    forbidden_goals: tuple[str, ...] = ()


@dataclass(frozen=True)
class DriftControl:
    enabled: bool = True
    window_days: int = 30
    max_drift_score: float = 0.25
    alert_on_drift: bool = True


@dataclass(frozen=True)
class CorpusRef:
    id: str
    user_id: str
    persona_id: str
    source_type: str = "chat"  # chat | document | email
    content_summary: str = ""
    consent_token: str = ""
    created_at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class PersonaSnapshot:
    id: str
    persona_id: str
    data: dict
    created_at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    created_by: str = ""
    tone: str = "professional"
    verbosity: str = "concise"
    language: str = "zh-CN"
    behaviors: tuple[str, ...] = ()
    style_hints: tuple[str, ...] = ()
    decision_policy: DecisionPolicy = field(default_factory=DecisionPolicy)
    delegation_scope: DelegationScope = field(default_factory=DelegationScope)
    drift_control: DriftControl = field(default_factory=DriftControl)
    expertise_primary: tuple[str, ...] = ()
    expertise_secondary: tuple[str, ...] = ()
    alignment_score: float = 0.0
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


# ── Serialization ──

def _serialize_persona(p: Persona) -> dict:
    d = asdict(p)
    d["behaviors"] = list(p.behaviors)
    d["style_hints"] = list(p.style_hints)
    d["decision_policy"]["priority_order"] = list(p.decision_policy.priority_order)
    d["decision_policy"]["forbidden_goals"] = list(p.decision_policy.forbidden_goals)
    d["delegation_scope"]["auto_approve"] = list(p.delegation_scope.auto_approve)
    d["delegation_scope"]["require_confirmation"] = list(p.delegation_scope.require_confirmation)
    d["delegation_scope"]["forbidden"] = list(p.delegation_scope.forbidden)
    d["expertise_primary"] = list(p.expertise_primary)
    d["expertise_secondary"] = list(p.expertise_secondary)
    return d


def _deserialize_persona(data: dict) -> Persona:
    dp = data.get("decision_policy", {})
    ds = data.get("delegation_scope", {})
    dc = data.get("drift_control", {})
    return Persona(
        id=data["id"], name=data["name"],
        created_by=data.get("created_by", ""),
        tone=data.get("tone", "professional"),
        verbosity=data.get("verbosity", "concise"),
        language=data.get("language", "zh-CN"),
        behaviors=tuple(data.get("behaviors", [])),
        style_hints=tuple(data.get("style_hints", [])),
        decision_policy=DecisionPolicy(
            priority_order=tuple(dp.get("priority_order", [])),
            risk_preference=dp.get("risk_preference", "balanced"),
            uncertain_action=dp.get("uncertain_action", "ask_for_confirmation"),
            forbidden_goals=tuple(dp.get("forbidden_goals", [])),
        ),
        delegation_scope=DelegationScope(
            auto_approve=tuple(ds.get("auto_approve", [])),
            require_confirmation=tuple(ds.get("require_confirmation", [])),
            forbidden=tuple(ds.get("forbidden", [])),
            principle=ds.get("principle", "delegation_cannot_escalate"),
        ),
        drift_control=DriftControl(
            enabled=dc.get("enabled", True),
            window_days=dc.get("window_days", 30),
            max_drift_score=dc.get("max_drift_score", 0.25),
            alert_on_drift=dc.get("alert_on_drift", True),
        ),
        expertise_primary=tuple(data.get("expertise_primary", [])),
        expertise_secondary=tuple(data.get("expertise_secondary", [])),
        alignment_score=data.get("alignment_score", 0.0),
        created_at=data.get("created_at", _now_iso()),
        updated_at=data.get("updated_at", _now_iso()),
    )


# ── PersonaStore ──

class PersonaStore:
    """基于 JSON 文件的人设存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "personas"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, persona_id: str) -> Path:
        return self._dir / f"{persona_id}.json"

    def save(self, p: Persona) -> None:
        self._path(p.id).write_text(
            json.dumps(_serialize_persona(p), ensure_ascii=False, indent=2))

    def get(self, persona_id: str) -> Optional[Persona]:
        path = self._path(persona_id)
        if not path.exists():
            return None
        return _deserialize_persona(json.loads(path.read_text()))

    def list_all(self) -> list[Persona]:
        return [_deserialize_persona(json.loads(p.read_text()))
                for p in sorted(self._dir.glob("*.json"))]

    def delete(self, persona_id: str) -> bool:
        path = self._path(persona_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def new_id(self) -> str:
        return f"persona-{uuid.uuid4().hex[:8]}"


# ── SnapshotStore ──

class SnapshotStore:
    """人设快照存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "snapshots"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, snap_id: str) -> Path:
        return self._dir / f"{snap_id}.json"

    def save(self, snap: PersonaSnapshot) -> None:
        self._path(snap.id).write_text(
            json.dumps(asdict(snap), ensure_ascii=False, indent=2))

    def list_by_persona(self, persona_id: str) -> list[PersonaSnapshot]:
        results = []
        for p in sorted(self._dir.glob("*.json")):
            data = json.loads(p.read_text())
            if data.get("persona_id") == persona_id:
                results.append(PersonaSnapshot(**data))
        return sorted(results, key=lambda s: s.created_at, reverse=True)

    def get(self, snap_id: str) -> Optional[PersonaSnapshot]:
        p = self._path(snap_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        return PersonaSnapshot(**data)

    def new_id(self) -> str:
        return f"snap-{uuid.uuid4().hex[:8]}"


# ── CorpusStore ──

class CorpusStore:
    """语料引用存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "corpus"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, cid: str) -> Path:
        return self._dir / f"{cid}.json"

    def save(self, c: CorpusRef) -> None:
        self._path(c.id).write_text(
            json.dumps(asdict(c), ensure_ascii=False, indent=2))

    def list_by_persona(self, persona_id: str) -> list[CorpusRef]:
        results = []
        for p in sorted(self._dir.glob("*.json")):
            data = json.loads(p.read_text())
            if data.get("persona_id") == persona_id:
                results.append(CorpusRef(**data))
        return results

    def new_id(self) -> str:
        return f"corpus-{uuid.uuid4().hex[:8]}"
