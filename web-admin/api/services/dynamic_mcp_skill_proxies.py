"""Skill proxy discovery helpers for dynamic MCP runtime."""

from __future__ import annotations

from pathlib import Path

from core.config import get_project_root
from core.deps import employee_store, project_store
from services.skill_import_service import read_manifest, read_skill_frontmatter, scan_proxy_entries
from stores.mcp_bridge import skill_store

_PROJECT_ROOT = get_project_root()
_EXECUTABLE_SUFFIXES = {".py", ".js"}
_RUNTIME_BY_SUFFIX = {
    ".py": "python",
    ".js": "node",
}


def _tool_token(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in str(value or "").strip().lower())
    text = "_".join(part for part in text.split("_") if part)
    if not text:
        return "tool"
    if text[0].isdigit():
        return f"t_{text}"
    return text


def _skill_package_path(skill) -> Path | None:
    package_dir = str(getattr(skill, "package_dir", "") or "").strip()
    if not package_dir:
        return None
    path = Path(package_dir)
    if not path.is_absolute():
        path = (_PROJECT_ROOT / path).resolve()
    else:
        path = path.resolve()
    if not path.exists() or not path.is_dir():
        return None
    return path


def _script_type_from_runtime(runtime: str, script_path: str = "") -> str:
    normalized_runtime = str(runtime or "").strip().lower()
    if normalized_runtime == "python":
        return "py"
    if normalized_runtime == "node":
        return "js"
    suffix = Path(script_path).suffix.lower()
    if suffix in _RUNTIME_BY_SUFFIX:
        return suffix.lstrip(".")
    return normalized_runtime or "command"


def _resolve_proxy_path(package_path: Path, raw_path: str, *, expect_dir: bool = False) -> str:
    path_text = str(raw_path or "").strip()
    if not path_text:
        return ""
    resolved = (package_path / path_text).resolve()
    if not resolved.exists():
        return ""
    if expect_dir and not resolved.is_dir():
        return ""
    if not expect_dir and not resolved.is_file():
        return ""
    return str(resolved)


def _spec_from_proxy_entry(skill, package_path: Path, entry) -> dict | None:
    command = [str(item).strip() for item in getattr(entry, "command", ()) if str(item).strip()]
    script_path = _resolve_proxy_path(package_path, getattr(entry, "path", ""))
    runtime = str(getattr(entry, "runtime", "") or "").strip().lower()
    if not runtime:
        runtime = _RUNTIME_BY_SUFFIX.get(Path(script_path).suffix.lower(), "command" if command else "")
    if runtime not in {"python", "node", "command"}:
        return None
    if not script_path and not command:
        return None
    entry_name = str(getattr(entry, "name", "") or "").strip()
    if not entry_name:
        return None
    description = str(getattr(entry, "description", "") or "").strip() or f"Proxy tool for {skill.id}:{entry_name}"
    args_schema = getattr(entry, "args_schema", {}) or {}
    return {
        "skill_id": skill.id,
        "skill_name": skill.name,
        "entry_name": entry_name,
        "script_path": script_path,
        "runtime": runtime,
        "script_type": _script_type_from_runtime(runtime, script_path),
        "command": command,
        "cwd": (
            _resolve_proxy_path(package_path, getattr(entry, "cwd", ""), expect_dir=True)
            if getattr(entry, "cwd", "")
            else ""
        ),
        "description": description,
        "parameters_schema": args_schema if isinstance(args_schema, dict) else {},
        "employee_id_flag": str(getattr(entry, "employee_id_flag", "--employee-id") or "").strip(),
        "api_key_flag": str(getattr(entry, "api_key_flag", "--api-key") or "").strip(),
    }


def _declared_proxy_entries(skill, package_path: Path):
    entries = tuple(getattr(skill, "proxy_entries", ()) or ())
    if entries:
        return entries
    manifest = read_manifest(package_path)
    frontmatter = read_skill_frontmatter(package_path)
    return scan_proxy_entries(package_path, manifest, frontmatter)


def _legacy_scan_proxy_specs(skill, package_path: Path) -> list[dict]:
    specs: list[dict] = []
    for base_dir in ("tools", "scripts"):
        root = package_path / base_dir
        if not root.exists():
            continue
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in _EXECUTABLE_SUFFIXES:
                continue
            rel_name = file.relative_to(root).with_suffix("").as_posix().replace("/", "-")
            runtime = _RUNTIME_BY_SUFFIX.get(file.suffix.lower(), "")
            specs.append(
                {
                    "skill_id": skill.id,
                    "skill_name": skill.name,
                    "entry_name": rel_name,
                    "script_path": str(file),
                    "runtime": runtime,
                    "script_type": file.suffix.lower().lstrip("."),
                    "command": [],
                    "cwd": "",
                    "description": f"Proxy tool for {skill.id}:{rel_name}",
                    "parameters_schema": {},
                    "employee_id_flag": "--employee-id",
                    "api_key_flag": "--api-key",
                }
            )
    return specs


def discover_skill_proxy_specs(skill) -> list[dict]:
    package_path = _skill_package_path(skill)
    if package_path is None:
        return []
    proxy_entries = []
    for entry in _declared_proxy_entries(skill, package_path):
        spec = _spec_from_proxy_entry(skill, package_path, entry)
        if spec is not None:
            proxy_entries.append(spec)
    return proxy_entries or _legacy_scan_proxy_specs(skill, package_path)


def _build_employee_proxy_specs(employee) -> dict[str, dict]:
    name_counter: dict[str, int] = {}
    employee_specs: dict[str, dict] = {}
    for skill_id in employee.skills or []:
        skill = skill_store.get(skill_id)
        if not skill:
            continue
        for spec in discover_skill_proxy_specs(skill):
            base_name = f"{_tool_token(skill.id)}__{_tool_token(spec['entry_name'])}"
            idx = name_counter.get(base_name, 0) + 1
            name_counter[base_name] = idx
            tool_name = base_name if idx == 1 else f"{base_name}_{idx}"
            employee_specs[tool_name] = {
                **spec,
                "employee_id": employee.id,
                "tool_name": tool_name,
                "base_tool_name": tool_name,
                "scoped_tool_name": f"{_tool_token(employee.id)}__{tool_name}",
            }
    return employee_specs


def build_employee_proxy_specs(employee_id: str) -> dict[str, dict]:
    employee = employee_store.get(employee_id)
    if employee is None:
        return {}
    return _build_employee_proxy_specs(employee)


def active_project_member_employees(project_id: str) -> list[tuple[object, object]]:
    project = project_store.get(project_id)
    if not project:
        return []
    members = []
    for member in project_store.list_members(project_id):
        if not bool(getattr(member, "enabled", True)):
            continue
        employee = employee_store.get(member.employee_id)
        if not employee:
            continue
        members.append((member, employee))
    return members


def build_project_proxy_specs(project_id: str) -> tuple[dict[str, dict], dict[str, dict[str, dict]]]:
    by_scoped_name: dict[str, dict] = {}
    by_employee_base_name: dict[str, dict[str, dict]] = {}
    for _member, employee in active_project_member_employees(project_id):
        employee_map = by_employee_base_name.setdefault(employee.id, {})
        for base_key, wrapped in _build_employee_proxy_specs(employee).items():
            by_scoped_name[wrapped["scoped_tool_name"]] = wrapped
            employee_map[base_key] = wrapped
    return by_scoped_name, by_employee_base_name


def resolve_project_proxy_tool_spec(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
) -> tuple[dict | None, str]:
    scoped_proxy_specs, employee_proxy_specs = build_project_proxy_specs(project_id)
    normalized_tool_name = str(tool_name or "").strip()
    employee_id_value = str(employee_id or "").strip()
    if not normalized_tool_name:
        return None, "tool_name is required"

    if employee_id_value:
        employee_specs = employee_proxy_specs.get(employee_id_value, {})
        if normalized_tool_name in employee_specs:
            return employee_specs[normalized_tool_name], ""
        scoped_name = f"{_tool_token(employee_id_value)}__{normalized_tool_name}"
        scoped_spec = scoped_proxy_specs.get(scoped_name)
        if scoped_spec:
            return scoped_spec, ""
        return None, f"Tool not found for employee {employee_id_value}: {normalized_tool_name}"

    if normalized_tool_name in scoped_proxy_specs:
        return scoped_proxy_specs[normalized_tool_name], ""

    matched: list[dict] = []
    for specs in employee_proxy_specs.values():
        if normalized_tool_name in specs:
            matched.append(specs[normalized_tool_name])
    if not matched:
        return None, f"Tool not found: {normalized_tool_name}"
    if len(matched) > 1:
        employee_ids = sorted({item["employee_id"] for item in matched})
        return None, f"Ambiguous tool_name, provide employee_id. Candidates: {employee_ids}"
    return matched[0], ""


def list_project_proxy_tools_runtime(project_id: str, employee_id: str = "") -> list[dict]:
    scoped_proxy_specs, employee_proxy_specs = build_project_proxy_specs(project_id)
    employee_id_value = str(employee_id or "").strip()
    tools: list[dict] = []
    if employee_id_value:
        specs = employee_proxy_specs.get(employee_id_value, {})
        for base_tool_name, spec in sorted(specs.items()):
            tools.append(
                {
                    "tool_name": base_tool_name,
                    "employee_id": spec["employee_id"],
                    "base_tool_name": spec["base_tool_name"],
                    "scoped_tool_name": spec["scoped_tool_name"],
                    "skill_id": spec["skill_id"],
                    "skill_name": spec["skill_name"],
                    "entry_name": spec["entry_name"],
                    "runtime": spec.get("runtime", spec["script_type"]),
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                    "parameters_schema": spec.get("parameters_schema", {}),
                }
            )
    else:
        for scoped_tool_name, spec in sorted(scoped_proxy_specs.items()):
            tools.append(
                {
                    "tool_name": scoped_tool_name,
                    "employee_id": spec["employee_id"],
                    "base_tool_name": spec["base_tool_name"],
                    "scoped_tool_name": spec["scoped_tool_name"],
                    "skill_id": spec["skill_id"],
                    "skill_name": spec["skill_name"],
                    "entry_name": spec["entry_name"],
                    "runtime": spec.get("runtime", spec["script_type"]),
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                    "parameters_schema": spec.get("parameters_schema", {}),
                }
            )
    return tools
