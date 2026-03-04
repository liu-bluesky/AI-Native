"""AI 员工存储层"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EmployeeConfig:
    id: str
    name: str
    description: str = ""
    skills: list[str] = field(default_factory=list)
    rule_domains: list[str] = field(default_factory=list)
    memory_scope: str = "project"
    memory_retention_days: int = 90
    persona_id: str = ""
    tone: str = "professional"
    verbosity: str = "concise"
    language: str = "zh-CN"
    style_hints: list[str] = field(default_factory=list)
    auto_evolve: bool = True
    evolve_threshold: float = 0.8
    mcp_enabled: bool = True
    feedback_upgrade_enabled: bool = False
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class EmployeeStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "employees"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, eid: str) -> Path:
        return self._dir / f"{eid}.json"

    def save(self, emp: EmployeeConfig) -> None:
        self._path(emp.id).write_text(
            json.dumps(asdict(emp), ensure_ascii=False, indent=2))

    def get(self, eid: str) -> Optional[EmployeeConfig]:
        p = self._path(eid)
        if not p.exists():
            return None
        return EmployeeConfig(**json.loads(p.read_text()))

    def list_all(self) -> list[EmployeeConfig]:
        results = []
        for p in sorted(self._dir.glob("*.json")):
            results.append(EmployeeConfig(**json.loads(p.read_text())))
        return results

    def delete(self, eid: str) -> bool:
        p = self._path(eid)
        if p.exists():
            p.unlink()
            return True
        return False

    def new_id(self) -> str:
        return f"emp-{uuid.uuid4().hex[:8]}"
