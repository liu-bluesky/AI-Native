"""技能存储层 — 数据模型与 CRUD"""

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
class ToolDef:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceDef:
    name: str
    description: str


@dataclass(frozen=True)
class ProxyEntryDef:
    name: str
    path: str = ""
    runtime: str = ""
    description: str = ""
    source: str = "declared"
    args_schema: dict = field(default_factory=dict)
    command: tuple[str, ...] = ()
    cwd: str = ""
    employee_id_flag: str = "--employee-id"
    api_key_flag: str = "--api-key"


@dataclass(frozen=True)
class Dependency:
    skill_id: str
    version: str = ">=1.0.0"
    required: bool = False


@dataclass(frozen=True)
class Skill:
    id: str
    version: str
    name: str
    description: str
    mcp_service: str
    created_by: str = ""
    share_scope: str = "private"
    shared_with_usernames: tuple[str, ...] = ()
    package_dir: str = ""
    tools: tuple[ToolDef, ...] = ()
    resources: tuple[ResourceDef, ...] = ()
    proxy_entries: tuple[ProxyEntryDef, ...] = ()
    dependencies: tuple[Dependency, ...] = ()
    tags: tuple[str, ...] = ()
    mcp_enabled: bool = False
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class EmployeeSkillBinding:
    employee_id: str
    skill_id: str
    enabled_tools: tuple[str, ...] = ()
    installed_at: str = field(default_factory=_now_iso)


# ── Serialization ──

def _serialize_skill(s: Skill) -> dict:
    d = asdict(s)
    d["tools"] = [asdict(t) for t in s.tools]
    d["resources"] = [asdict(r) for r in s.resources]
    d["proxy_entries"] = [asdict(entry) for entry in s.proxy_entries]
    d["dependencies"] = [asdict(dep) for dep in s.dependencies]
    d["tags"] = list(s.tags)
    return d


def _deserialize_skill(data: dict) -> Skill:
    return Skill(
        id=data["id"], version=data["version"],
        name=data["name"], description=data["description"],
        mcp_service=data.get("mcp_service", ""),
        created_by=data.get("created_by", ""),
        share_scope=data.get("share_scope", "private"),
        shared_with_usernames=tuple(data.get("shared_with_usernames", [])),
        package_dir=data.get("package_dir", data.get("source_dir", "")),
        tools=tuple(ToolDef(**t) for t in data.get("tools", [])),
        resources=tuple(ResourceDef(**r) for r in data.get("resources", [])),
        proxy_entries=tuple(
            ProxyEntryDef(
                name=entry.get("name", ""),
                path=entry.get("path", ""),
                runtime=entry.get("runtime", ""),
                description=entry.get("description", ""),
                source=entry.get("source", "declared"),
                args_schema=entry.get("args_schema", {}) or {},
                command=tuple(entry.get("command", []) or ()),
                cwd=entry.get("cwd", ""),
                employee_id_flag=entry.get("employee_id_flag", "--employee-id"),
                api_key_flag=entry.get("api_key_flag", "--api-key"),
            )
            for entry in data.get("proxy_entries", [])
        ),
        dependencies=tuple(Dependency(**d) for d in data.get("dependencies", [])),
        tags=tuple(data.get("tags", [])),
        mcp_enabled=data.get("mcp_enabled", False),
        created_at=data.get("created_at", _now_iso()),
        updated_at=data.get("updated_at", _now_iso()),
    )


# ── SkillStore ──

class SkillStore:
    """基于 JSON 文件的技能存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "skills"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._packages_dir = data_dir / "skill-packages"
        self._packages_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, skill_id: str) -> Path:
        return self._dir / f"{skill_id}.json"

    def package_path(self, skill_id: str) -> Path:
        return self._packages_dir / skill_id

    def save(self, skill: Skill) -> None:
        self._path(skill.id).write_text(
            json.dumps(_serialize_skill(skill), ensure_ascii=False, indent=2))

    def get(self, skill_id: str) -> Optional[Skill]:
        p = self._path(skill_id)
        if not p.exists():
            return None
        return _deserialize_skill(json.loads(p.read_text()))

    def list_all(self) -> list[Skill]:
        return [_deserialize_skill(json.loads(p.read_text()))
                for p in sorted(self._dir.glob("*.json"))]

    def query(self, tags: Optional[list[str]] = None,
              domain: Optional[str] = None) -> list[Skill]:
        results = self.list_all()
        if tags:
            tag_set = {t.lower() for t in tags}
            results = [s for s in results
                       if tag_set & {t.lower() for t in s.tags}]
        if domain:
            d = domain.lower()
            results = [s for s in results
                       if d in {t.lower() for t in s.tags}
                       or d in s.description.lower()]
        return results

    def delete(self, skill_id: str) -> bool:
        path = self._path(skill_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def new_id(self) -> str:
        return f"skill-{uuid.uuid4().hex[:8]}"


# ── BindingStore ──

class BindingStore:
    """员工-技能绑定存储"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "bindings"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, employee_id: str) -> Path:
        return self._dir / f"{employee_id}.json"

    def get_bindings(self, employee_id: str) -> list[EmployeeSkillBinding]:
        p = self._path(employee_id)
        if not p.exists():
            return []
        data = json.loads(p.read_text())
        return [EmployeeSkillBinding(**b) for b in data]

    def add(self, binding: EmployeeSkillBinding) -> None:
        bindings = self.get_bindings(binding.employee_id)
        bindings = [b for b in bindings if b.skill_id != binding.skill_id]
        bindings.append(binding)
        self._save(binding.employee_id, bindings)

    def remove(self, employee_id: str, skill_id: str) -> bool:
        bindings = self.get_bindings(employee_id)
        new = [b for b in bindings if b.skill_id != skill_id]
        if len(new) == len(bindings):
            return False
        self._save(employee_id, new)
        return True

    def _save(self, employee_id: str, bindings: list[EmployeeSkillBinding]) -> None:
        self._path(employee_id).write_text(
            json.dumps([asdict(b) for b in bindings], ensure_ascii=False, indent=2))
