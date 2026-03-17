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

from core.ownership import current_username
from models.requests import SkillCreateReq
from stores.mcp_bridge import ResourceDef, Skill, ToolDef, skill_store

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOL_SUFFIXES = {".py", ".js"}
SENSITIVE_SKILL_FILE_PATTERNS = (".db-config*.json",)


@dataclass(frozen=True)
class SkillImportResult:
    skill: Skill
    already_exists: bool = False


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


def scan_tools(source_dir: Path, manifest: dict[str, Any]) -> tuple[ToolDef, ...]:
    tools_dir = source_dir / "tools"
    desc_map = _manifest_tool_desc(manifest)
    scanned: list[ToolDef] = []
    if tools_dir.exists():
        for file in sorted(tools_dir.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in TOOL_SUFFIXES:
                continue
            rel = file.relative_to(tools_dir).with_suffix("").as_posix()
            tool_name = rel.replace("/", "-")
            description = (
                desc_map.pop(tool_name, "")
                or desc_map.pop(file.stem, "")
                or f"Imported tool from {file.name}"
            )
            scanned.append(ToolDef(name=tool_name, description=description))
    for name, description in desc_map.items():
        if name:
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
        package_dir=str(package_path.relative_to(PROJECT_ROOT)),
        tools=scan_tools(source_dir, manifest),
        resources=scan_resources(source_dir),
        tags=tags,
        mcp_enabled=req.mcp_enabled,
    )
    try:
        skill_store.save(skill)
    except Exception:
        shutil.rmtree(package_path, ignore_errors=True)
        raise
    return SkillImportResult(skill=skill, already_exists=False)
