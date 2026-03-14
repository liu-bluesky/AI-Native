"""规则存储层 — 数据模型与 CRUD"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Enums ──

class Severity(str, Enum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class RiskDomain(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Data Models ──

@dataclass(frozen=True)
class SemanticVersion:
    major: int = 1
    minor: int = 0
    patch: int = 0

    def bump_major(self) -> SemanticVersion:
        return SemanticVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> SemanticVersion:
        return SemanticVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> SemanticVersion:
        return SemanticVersion(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ChangelogEntry:
    version: str
    date: str
    author: str
    change: str


@dataclass(frozen=True)
class Rule:
    id: str
    domain: str
    title: str
    content: str
    severity: Severity = Severity.RECOMMENDED
    risk_domain: RiskDomain = RiskDomain.LOW
    version: SemanticVersion = field(default_factory=SemanticVersion)
    confidence: float = 0.5
    use_count: int = 0
    adopt_count: int = 0
    changelog: tuple[ChangelogEntry, ...] = ()
    bound_employees: tuple[str, ...] = ()
    mcp_enabled: bool = False
    mcp_service: str = ""
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


# ── Serialization ──

def _serialize_rule(r: Rule) -> dict:
    d = asdict(r)
    d["severity"] = r.severity.value
    d["risk_domain"] = r.risk_domain.value
    d["version"] = str(r.version)
    d["changelog"] = [asdict(c) for c in r.changelog]
    d["bound_employees"] = list(r.bound_employees)
    return d


def _parse_version(v) -> SemanticVersion:
    if isinstance(v, dict):
        return SemanticVersion(v.get("major", 1), v.get("minor", 0), v.get("patch", 0))
    if isinstance(v, str):
        parts = v.split(".")
        return SemanticVersion(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0,
                               int(parts[2]) if len(parts) > 2 else 0)
    return SemanticVersion()


def _deserialize_rule(data: dict) -> Rule:
    cl = [ChangelogEntry(**c) for c in data.get("changelog", [])]
    return Rule(
        id=data["id"], domain=data["domain"],
        title=data["title"], content=data["content"],
        severity=Severity(data.get("severity", "recommended")),
        risk_domain=RiskDomain(data.get("risk_domain", "low")),
        version=_parse_version(data.get("version", {})),
        confidence=data.get("confidence", 0.5),
        use_count=data.get("use_count", 0),
        adopt_count=data.get("adopt_count", 0),
        changelog=tuple(cl),
        bound_employees=tuple(data.get("bound_employees", [])),
        mcp_enabled=data.get("mcp_enabled", False),
        mcp_service=data.get("mcp_service", ""),
        created_by=data.get("created_by", ""),
        created_at=data.get("created_at", _now_iso()),
        updated_at=data.get("updated_at", _now_iso()),
    )


# ── RuleStore ──

class RuleStore:
    """基于 JSON 文件的规则存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "rules"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, rule_id: str) -> Path:
        return self._dir / f"{rule_id}.json"

    def save(self, r: Rule) -> None:
        self._path(r.id).write_text(
            json.dumps(_serialize_rule(r), ensure_ascii=False, indent=2))

    def get(self, rule_id: str) -> Optional[Rule]:
        path = self._path(rule_id)
        if not path.exists():
            return None
        return _deserialize_rule(json.loads(path.read_text()))

    def delete(self, rule_id: str) -> bool:
        path = self._path(rule_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_all(self) -> list[Rule]:
        return [_deserialize_rule(json.loads(p.read_text()))
                for p in sorted(self._dir.glob("*.json"))]

    def list_by_project(self, project_id: str) -> list[Rule]:
        """兼容接口：当前规则模型未按 project 维度存储，先返回全量规则。"""
        _ = project_id
        return self.list_all()

    def query(self, keyword: str, domain: str = None) -> list[Rule]:
        kw = keyword.lower()
        results = []
        for r in self.list_all():
            if domain and r.domain != domain:
                continue
            if kw in r.title.lower() or kw in r.content.lower():
                results.append(r)
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def domains(self) -> list[str]:
        return sorted({r.domain for r in self.list_all()})

    def record_usage(self, rule_id: str, adopted: bool) -> None:
        r = self.get(rule_id)
        if r is None:
            return
        from dataclasses import replace
        new_use = r.use_count + 1
        new_adopt = r.adopt_count + (1 if adopted else 0)
        new_conf = round(new_adopt / new_use, 2) if new_use > 0 else r.confidence
        updated = replace(r, use_count=new_use, adopt_count=new_adopt,
                          confidence=new_conf, updated_at=_now_iso())
        self.save(updated)

    def new_id(self) -> str:
        return f"rule-{uuid.uuid4().hex[:8]}"
