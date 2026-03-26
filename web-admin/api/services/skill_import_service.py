"""Reusable helpers for importing skill packages into the local skill store."""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.config import get_project_root
from core.ownership import current_username, normalize_share_scope, normalize_shared_usernames
from models.requests import SkillCreateReq
from stores.mcp_bridge import ProxyEntryDef, ResourceDef, Skill, ToolDef, skill_store

PROJECT_ROOT = get_project_root()
TOOL_SUFFIXES = {".py", ".js"}
SCRIPT_RUNTIME_BY_SUFFIX = {
    ".py": "python",
    ".js": "node",
}
SUPPORTED_PROXY_RUNTIMES = {"python", "node", "command"}
SENSITIVE_SKILL_FILE_PATTERNS = (".db-config*.json",)


@dataclass(frozen=True)
class SkillImportResult:
    skill: Skill
    already_exists: bool = False


@dataclass(frozen=True)
class SkillBackfillResult:
    created: tuple[Skill, ...] = ()


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized[:64]


def _parse_yaml_text(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        data: dict[str, Any] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip("\"'")
        return data


def read_manifest(source_dir: Path) -> dict[str, Any]:
    for filename in ("manifest.yaml", "manifest.yml", "manifest.json"):
        path = source_dir / filename
        if not path.exists():
            continue
        if filename.endswith(".json"):
            try:
                data = json.loads(path.read_text())
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return _parse_yaml_text(path.read_text())
    return {}


def read_skill_frontmatter(source_dir: Path) -> dict[str, Any]:
    skill_md = source_dir / "SKILL.md"
    if not skill_md.exists():
        return {}
    text = skill_md.read_text()
    match = re.match(r"^---\s*\n(.*?)\n---", text, flags=re.DOTALL)
    if not match:
        return {}
    return _parse_yaml_text(match.group(1))


def _as_tags(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, list):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    if isinstance(raw, str):
        return tuple(item.strip() for item in raw.split(",") if item.strip())
    return ()


def _as_command(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, list):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    if isinstance(raw, str):
        text = raw.strip()
        return (text,) if text else ()
    return ()


def _normalize_proxy_runtime(raw: Any, *, path: str = "", command: tuple[str, ...] = ()) -> str:
    runtime = str(raw or "").strip().lower()
    if runtime in {"py", "python3"}:
        return "python"
    if runtime in {"js", "nodejs"}:
        return "node"
    if runtime:
        return runtime
    suffix = Path(path).suffix.lower()
    if suffix in SCRIPT_RUNTIME_BY_SUFFIX:
        return SCRIPT_RUNTIME_BY_SUFFIX[suffix]
    if command:
        return "command"
    return ""


def _normalize_proxy_entries(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        raw = raw.get("entries", [])
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append({"path": text})
            continue
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def scan_declared_proxy_entries(
    source_dir: Path,
    manifest: dict[str, Any],
    frontmatter: dict[str, Any] | None = None,
) -> tuple[ProxyEntryDef, ...]:
    frontmatter = frontmatter or {}
    raw_entries = manifest.get(
        "proxy_entries",
        manifest.get("proxyEntries", frontmatter.get("proxy_entries", frontmatter.get("proxyEntries", []))),
    )
    seen_names: set[str] = set()
    entries: list[ProxyEntryDef] = []
    for item in _normalize_proxy_entries(raw_entries):
        path = str(item.get("path") or item.get("script") or item.get("entry") or "").strip()
        command = _as_command(item.get("command"))
        runtime = _normalize_proxy_runtime(item.get("runtime"), path=path, command=command)
        if runtime not in SUPPORTED_PROXY_RUNTIMES:
            continue
        if not path and not command:
            continue
        if path:
            resolved = (source_dir / path).resolve()
            if not resolved.exists() or not resolved.is_file():
                continue
        entry_name = str(item.get("name") or "").strip()
        if not entry_name:
            if path:
                entry_name = Path(path).with_suffix("").as_posix().replace("/", "-")
            elif command:
                entry_name = Path(command[-1]).stem or Path(command[0]).name
        if not entry_name or entry_name in seen_names:
            continue
        seen_names.add(entry_name)
        args_schema = item.get("args_schema", item.get("parameters_schema", {}))
        entries.append(
            ProxyEntryDef(
                name=entry_name,
                path=path,
                runtime=runtime,
                description=str(item.get("description") or "").strip(),
                source="declared",
                args_schema=args_schema if isinstance(args_schema, dict) else {},
                command=command,
                cwd=str(item.get("cwd") or "").strip(),
                employee_id_flag=str(item.get("employee_id_flag", "--employee-id") or "").strip(),
                api_key_flag=str(item.get("api_key_flag", "--api-key") or "").strip(),
            )
        )
    return tuple(entries)


def infer_proxy_entries(
    source_dir: Path,
    manifest: dict[str, Any],
    frontmatter: dict[str, Any] | None = None,
) -> tuple[ProxyEntryDef, ...]:
    frontmatter = frontmatter or {}
    desc_map = _manifest_tool_desc(manifest)
    entries: list[ProxyEntryDef] = []
    for base_dir in ("tools", "scripts"):
        root = source_dir / base_dir
        if not root.exists():
            continue
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in TOOL_SUFFIXES:
                continue
            rel = file.relative_to(root).with_suffix("").as_posix()
            entry_name = rel.replace("/", "-")
            description = (
                desc_map.get(entry_name, "")
                or desc_map.get(file.stem, "")
                or f"Auto inferred proxy entry from {base_dir}/{file.name}"
            )
            entries.append(
                ProxyEntryDef(
                    name=entry_name,
                    path=file.relative_to(source_dir).as_posix(),
                    runtime=_normalize_proxy_runtime("", path=file.name),
                    description=description,
                    source="inferred",
                )
            )
    return tuple(entries)


def scan_proxy_entries(
    source_dir: Path,
    manifest: dict[str, Any],
    frontmatter: dict[str, Any] | None = None,
) -> tuple[ProxyEntryDef, ...]:
    declared = scan_declared_proxy_entries(source_dir, manifest, frontmatter)
    if declared:
        return declared
    return infer_proxy_entries(source_dir, manifest, frontmatter)


def _resolve_package_dir_for_storage(source_dir: Path) -> str:
    try:
        return str(source_dir.resolve().relative_to(PROJECT_ROOT).as_posix())
    except ValueError:
        return str(source_dir.resolve())


def _existing_skill_package_paths() -> set[Path]:
    paths: set[Path] = set()
    for item in skill_store.list_all():
        package_dir = str(getattr(item, "package_dir", "") or "").strip()
        if not package_dir:
            continue
        path = Path(package_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        paths.add(path.resolve())
    return paths


def _preferred_skill_id(
    source_dir: Path,
    manifest: dict[str, Any],
    frontmatter: dict[str, Any],
    name: str,
) -> str:
    for raw in (
        manifest.get("id"),
        frontmatter.get("slug"),
        source_dir.name,
        frontmatter.get("name"),
        name,
    ):
        candidate = _slugify(str(raw or ""))
        if candidate:
            return candidate
    return ""


def _allocate_backfill_skill_id(
    source_dir: Path,
    manifest: dict[str, Any],
    frontmatter: dict[str, Any],
    name: str,
) -> str:
    base = _preferred_skill_id(source_dir, manifest, frontmatter, name)
    if not base:
        return skill_store.new_id()
    skill_id = base
    suffix = 2
    while skill_store.get(skill_id) is not None:
        skill_id = f"{base}-{suffix}"
        suffix += 1
    return skill_id


def build_skill_record_from_package_dir(
    source_dir: Path,
    *,
    skill_id: str | None = None,
    created_by: str = "",
) -> Skill:
    manifest = read_manifest(source_dir)
    frontmatter = read_skill_frontmatter(source_dir)
    name = str(manifest.get("name") or frontmatter.get("name") or source_dir.name).strip() or source_dir.name
    description = str(manifest.get("description") or frontmatter.get("description") or "").strip()
    version = str(manifest.get("version") or frontmatter.get("version") or "1.0.0").strip() or "1.0.0"
    mcp_service = str(manifest.get("mcp_service") or frontmatter.get("mcp_service") or "").strip()
    tags = _as_tags(manifest.get("tags", frontmatter.get("tags", [])))
    resolved_skill_id = str(skill_id or "").strip() or _allocate_backfill_skill_id(
        source_dir,
        manifest,
        frontmatter,
        name,
    )
    return Skill(
        id=resolved_skill_id,
        name=name,
        version=version,
        description=description,
        mcp_service=mcp_service,
        created_by=created_by,
        package_dir=_resolve_package_dir_for_storage(source_dir),
        tools=scan_tools(source_dir, manifest, frontmatter),
        resources=scan_resources(source_dir),
        proxy_entries=scan_proxy_entries(source_dir, manifest, frontmatter),
        tags=tags,
        mcp_enabled=bool(manifest.get("mcp_enabled", False)),
    )


def resolve_source_dir(source_dir: str) -> Path:
    raw = str(source_dir or "").strip()
    if not raw:
        raise HTTPException(400, "source_dir is required")
    path = Path(raw).expanduser()
    path = (PROJECT_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(400, f"Skill directory not found: {path}")
    return path


def _manifest_tool_desc(manifest: dict[str, Any]) -> dict[str, str]:
    tools = manifest.get("tools", [])
    if not isinstance(tools, list):
        return {}
    result: dict[str, str] = {}
    for item in tools:
        if isinstance(item, str):
            result[item.strip()] = ""
            continue
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        result[name] = str(item.get("description", "")).strip()
    return result


def scan_tools(
    source_dir: Path,
    manifest: dict[str, Any],
    frontmatter: dict[str, Any] | None = None,
) -> tuple[ToolDef, ...]:
    tools_dir = source_dir / "tools"
    desc_map = _manifest_tool_desc(manifest)
    scanned: list[ToolDef] = []
    seen_names: set[str] = set()
    if tools_dir.exists():
        for file in sorted(tools_dir.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in TOOL_SUFFIXES:
                continue
            rel = file.relative_to(tools_dir).with_suffix("").as_posix()
            tool_name = rel.replace("/", "-")
            seen_names.add(tool_name)
            description = (
                desc_map.pop(tool_name, "")
                or desc_map.pop(file.stem, "")
                or f"Imported tool from {file.name}"
            )
            scanned.append(ToolDef(name=tool_name, description=description))
    for entry in scan_proxy_entries(source_dir, manifest, frontmatter):
        if entry.name in seen_names:
            continue
        seen_names.add(entry.name)
        scanned.append(
            ToolDef(
                name=entry.name,
                description=entry.description or "Imported proxy entry from manifest",
                parameters=entry.args_schema,
            )
        )
    for name, description in desc_map.items():
        if name and name not in seen_names:
            seen_names.add(name)
            scanned.append(
                ToolDef(name=name, description=description or "Imported from manifest")
            )
    return tuple(scanned)


def scan_resources(source_dir: Path) -> tuple[ResourceDef, ...]:
    resources_dir = source_dir / "resources"
    if not resources_dir.exists():
        return ()
    resources: list[ResourceDef] = []
    for item in sorted(resources_dir.iterdir()):
        resources.append(
            ResourceDef(
                name=item.name,
                description="Directory resource" if item.is_dir() else "File resource",
            )
        )
    return tuple(resources)


def looks_like_skill_dir(path: Path) -> bool:
    return (
        (path / "SKILL.md").exists()
        or (path / "manifest.yaml").exists()
        or (path / "manifest.yml").exists()
        or (path / "manifest.json").exists()
        or (path / "tools").exists()
    )


def backfill_existing_skill_packages() -> SkillBackfillResult:
    packages_root = skill_store.package_path("__backfill__").parent
    if not packages_root.exists() or not packages_root.is_dir():
        return SkillBackfillResult()

    existing_paths = _existing_skill_package_paths()
    created: list[Skill] = []
    for source_dir in sorted(path for path in packages_root.iterdir() if path.is_dir()):
        resolved = source_dir.resolve()
        if resolved in existing_paths:
            continue
        if not looks_like_skill_dir(source_dir):
            continue
        skill = build_skill_record_from_package_dir(source_dir)
        skill_store.save(skill)
        existing_paths.add(resolved)
        created.append(skill)
    return SkillBackfillResult(created=tuple(created))


def pick_extracted_skill_dir(extract_dir: Path) -> Path:
    children = [
        path
        for path in extract_dir.iterdir()
        if path.name != "__MACOSX" and not path.name.startswith(".")
    ]
    if len(children) == 1 and children[0].is_dir() and looks_like_skill_dir(children[0]):
        return children[0]
    if looks_like_skill_dir(extract_dir):
        return extract_dir
    for child in children:
        if child.is_dir() and looks_like_skill_dir(child):
            return child
    raise HTTPException(
        400,
        "ZIP 中未找到技能目录，请确保包含 SKILL.md/manifest.* 或 tools/ 目录。",
    )


def _allocate_skill_id(source_dir: Path, manifest: dict[str, Any], frontmatter: dict[str, Any], name: str) -> str:
    base = _slugify(
        str(manifest.get("id") or frontmatter.get("name") or name or source_dir.name)
    )
    if not base:
        return skill_store.new_id()
    skill_id = base
    suffix = 2
    while skill_store.get(skill_id) is not None:
        skill_id = f"{base}-{suffix}"
        suffix += 1
    return skill_id


def _skill_copy_ignore(_: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for pattern in SENSITIVE_SKILL_FILE_PATTERNS:
        ignored.update(fnmatch.filter(names, pattern))
    return ignored


def copy_skill_dir(source_dir: Path, target_dir: Path) -> Path:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir, dirs_exist_ok=True, ignore=_skill_copy_ignore)
    return target_dir


def import_skill_from_dir(
    req: SkillCreateReq,
    auth_payload: dict | None = None,
    *,
    dedupe_if_same_version: bool = False,
) -> SkillImportResult:
    source_dir = resolve_source_dir(req.source_dir)
    manifest = read_manifest(source_dir)
    frontmatter = read_skill_frontmatter(source_dir)
    fields_set = req.model_fields_set

    name = req.name.strip() or str(manifest.get("name") or frontmatter.get("name") or source_dir.name)
    description = req.description.strip() or str(
        manifest.get("description") or frontmatter.get("description") or ""
    )
    version = (
        req.version.strip()
        if "version" in fields_set and req.version.strip()
        else str(manifest.get("version") or "1.0.0")
    )
    mcp_service = (
        req.mcp_service.strip()
        if "mcp_service" in fields_set and req.mcp_service.strip()
        else str(manifest.get("mcp_service") or "")
    )
    tags = (
        tuple(tag for tag in req.tags if tag.strip())
        if "tags" in fields_set
        else _as_tags(manifest.get("tags", frontmatter.get("tags", [])))
    )

    preferred_id = _slugify(
        str(manifest.get("id") or frontmatter.get("name") or name or source_dir.name)
    )
    if dedupe_if_same_version and preferred_id:
        existing = skill_store.get(preferred_id)
        if existing is not None and str(existing.version or "").strip() == version:
            return SkillImportResult(skill=existing, already_exists=True)

    skill_id = _allocate_skill_id(source_dir, manifest, frontmatter, name)
    package_path = skill_store.package_path(skill_id)
    if package_path.exists():
        raise HTTPException(409, f"Skill package already exists: {package_path}")
    try:
        copy_skill_dir(source_dir, package_path)
    except Exception as exc:
        raise HTTPException(400, f"Failed to import skill directory: {exc}") from exc

    skill = Skill(
        id=skill_id,
        name=name,
        version=version,
        description=description,
        mcp_service=mcp_service,
        created_by=current_username(auth_payload),
        share_scope=normalize_share_scope(req.share_scope),
        shared_with_usernames=tuple(
            normalize_shared_usernames(
                req.shared_with_usernames,
                owner_username=current_username(auth_payload),
            )
        ),
        package_dir=str(package_path.relative_to(PROJECT_ROOT)),
        tools=scan_tools(source_dir, manifest, frontmatter),
        resources=scan_resources(source_dir),
        proxy_entries=scan_proxy_entries(source_dir, manifest, frontmatter),
        tags=tags,
        mcp_enabled=req.mcp_enabled,
    )
    try:
        skill_store.save(skill)
    except Exception:
        shutil.rmtree(package_path, ignore_errors=True)
        raise
    return SkillImportResult(skill=skill, already_exists=False)
