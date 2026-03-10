"""技能管理路由"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
import io
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from core.deps import require_auth, usage_store
from stores.mcp_bridge import (
    skill_store, binding_store, serialize_skill, EmployeeSkillBinding,
    Skill, ToolDef, ResourceDef, skills_now_iso,
)
from models.requests import SkillInstallReq, SkillCreateReq, SkillUpdateReq

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TOOL_SUFFIXES = {".py", ".js"}
_MAX_ZIP_SIZE = 20 * 1024 * 1024


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:64]


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


def _read_manifest(source_dir: Path) -> dict[str, Any]:
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


def _read_skill_frontmatter(source_dir: Path) -> dict[str, Any]:
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
        return tuple(str(t).strip() for t in raw if str(t).strip())
    if isinstance(raw, str):
        return tuple(t.strip() for t in raw.split(",") if t.strip())
    return ()


def _resolve_source_dir(source_dir: str) -> Path:
    raw = source_dir.strip()
    if not raw:
        raise HTTPException(400, "source_dir is required")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (_PROJECT_ROOT / path).resolve()
    else:
        path = path.resolve()
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


def _scan_tools(source_dir: Path, manifest: dict[str, Any]) -> tuple[ToolDef, ...]:
    tools_dir = source_dir / "tools"
    desc_map = _manifest_tool_desc(manifest)
    scanned: list[ToolDef] = []
    if tools_dir.exists():
        for file in sorted(tools_dir.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in _TOOL_SUFFIXES:
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
        if not name:
            continue
        scanned.append(ToolDef(name=name, description=description or "Imported from manifest"))
    return tuple(scanned)


def _scan_resources(source_dir: Path) -> tuple[ResourceDef, ...]:
    resources_dir = source_dir / "resources"
    if not resources_dir.exists():
        return ()
    resources = []
    for item in sorted(resources_dir.iterdir()):
        resources.append(
            ResourceDef(
                name=item.name,
                description="Directory resource" if item.is_dir() else "File resource",
            )
        )
    return tuple(resources)


def _looks_like_skill_dir(path: Path) -> bool:
    return (
        (path / "SKILL.md").exists()
        or (path / "manifest.yaml").exists()
        or (path / "manifest.yml").exists()
        or (path / "manifest.json").exists()
        or (path / "tools").exists()
    )


def _pick_extracted_skill_dir(extract_dir: Path) -> Path:
    children = [
        p for p in extract_dir.iterdir()
        if p.name != "__MACOSX" and not p.name.startswith(".")
    ]
    if len(children) == 1 and children[0].is_dir() and _looks_like_skill_dir(children[0]):
        return children[0]
    if _looks_like_skill_dir(extract_dir):
        return extract_dir
    for child in children:
        if child.is_dir() and _looks_like_skill_dir(child):
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


def _import_skill_from_dir(req: SkillCreateReq) -> Skill:
    source_dir = _resolve_source_dir(req.source_dir)
    manifest = _read_manifest(source_dir)
    frontmatter = _read_skill_frontmatter(source_dir)
    fields_set = req.model_fields_set

    name = req.name.strip() or str(manifest.get("name") or frontmatter.get("name") or source_dir.name)
    description = req.description.strip() or str(
        manifest.get("description") or frontmatter.get("description") or ""
    )
    version = (
        req.version.strip() if "version" in fields_set and req.version.strip()
        else str(manifest.get("version") or "1.0.0")
    )
    mcp_service = (
        req.mcp_service.strip() if "mcp_service" in fields_set and req.mcp_service.strip()
        else str(manifest.get("mcp_service") or "")
    )
    tags = (
        tuple(t for t in req.tags if t.strip())
        if "tags" in fields_set
        else _as_tags(manifest.get("tags", frontmatter.get("tags", [])))
    )

    skill_id = _allocate_skill_id(source_dir, manifest, frontmatter, name)
    package_path = skill_store.package_path(skill_id)
    if package_path.exists():
        raise HTTPException(409, f"Skill package already exists: {package_path}")
    try:
        shutil.copytree(source_dir, package_path)
    except Exception as e:
        raise HTTPException(400, f"Failed to import skill directory: {e}") from e

    skill = Skill(
        id=skill_id,
        name=name,
        version=version,
        description=description,
        mcp_service=mcp_service,
        package_dir=str(package_path.relative_to(_PROJECT_ROOT)),
        tools=_scan_tools(source_dir, manifest),
        resources=_scan_resources(source_dir),
        tags=tags,
        mcp_enabled=req.mcp_enabled,
    )
    try:
        skill_store.save(skill)
    except Exception:
        shutil.rmtree(package_path, ignore_errors=True)
        raise
    return skill


@router.get("/skills")
async def list_skills():
    skills = skill_store.list_all()
    return {"skills": [serialize_skill(s) for s in skills]}


@router.get("/skills/query/{domain}")
async def query_skills(domain: str):
    results = skill_store.query(domain=domain)
    return {"skills": [serialize_skill(s) for s in results]}


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str):
    s = skill_store.get(skill_id)
    if s is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    return {"skill": serialize_skill(s)}


@router.get("/employees/{employee_id}/skills")
async def employee_skills(employee_id: str):
    bindings = binding_store.get_bindings(employee_id)
    items = []
    for b in bindings:
        s = skill_store.get(b.skill_id)
        items.append({
            "skill_id": b.skill_id,
            "skill_name": s.name if s else b.skill_id,
            "enabled_tools": list(b.enabled_tools),
            "installed_at": b.installed_at,
        })
    return {"bindings": items}


@router.post("/employees/{employee_id}/skills")
async def install_skill(employee_id: str, req: SkillInstallReq):
    if skill_store.get(req.skill_id) is None:
        raise HTTPException(404, f"Skill {req.skill_id} not found")
    binding = EmployeeSkillBinding(
        employee_id=employee_id,
        skill_id=req.skill_id,
        enabled_tools=tuple(req.enabled_tools),
    )
    binding_store.add(binding)
    return {"status": "installed", "skill_id": req.skill_id}


@router.post("/skills")
async def create_skill(req: SkillCreateReq):
    skill = _import_skill_from_dir(req)
    return {"status": "created", "skill": serialize_skill(skill)}


@router.post("/skills/import")
async def import_skill(req: SkillCreateReq):
    skill = _import_skill_from_dir(req)
    return {"status": "created", "skill": serialize_skill(skill)}


@router.post("/skills/import-file")
async def import_skill_file(
    file: UploadFile = File(...),
    name: str = Form(""),
    version: str = Form(""),
    description: str = Form(""),
    mcp_service: str = Form(""),
    tags: str = Form(""),
    mcp_enabled: bool = Form(False),
):
    filename = (file.filename or "").lower()
    if not filename.endswith(".zip"):
        raise HTTPException(400, "Only .zip skill package is supported")
    content = await file.read()
    await file.close()
    if not content:
        raise HTTPException(400, "Uploaded file is empty")
    if len(content) > _MAX_ZIP_SIZE:
        raise HTTPException(400, "Skill package is too large (max 20MB)")

    with tempfile.TemporaryDirectory(prefix="skill-upload-") as temp_dir:
        root = Path(temp_dir)
        zip_path = root / "skill.zip"
        extract_dir = root / "extracted"
        zip_path.write_bytes(content)
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for info in zf.infolist():
                    rel = Path(info.filename)
                    if rel.is_absolute() or ".." in rel.parts:
                        raise HTTPException(400, "ZIP contains unsafe path entries")
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as e:
            raise HTTPException(400, "Invalid zip file") from e

        source_dir = _pick_extracted_skill_dir(extract_dir)
        payload: dict[str, Any] = {"source_dir": str(source_dir), "mcp_enabled": mcp_enabled}
        if name.strip():
            payload["name"] = name.strip()
        if version.strip():
            payload["version"] = version.strip()
        if description.strip():
            payload["description"] = description.strip()
        if mcp_service.strip():
            payload["mcp_service"] = mcp_service.strip()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            payload["tags"] = tag_list
        skill = _import_skill_from_dir(SkillCreateReq(**payload))
    return {"status": "created", "skill": serialize_skill(skill)}

@router.get("/skills/{skill_id}/export")
async def export_skill(skill_id: str):
    skill = skill_store.get(skill_id)
    if skill is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
        
    # Find the skill package directory
    # skill.package_dir is something like "mcp-skills/knowledge/skill-packages/db-query"
    # We resolve it relative to the global project root
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    package_path = project_root / skill.package_dir
    
    if not package_path.exists() or not package_path.is_dir():
        raise HTTPException(404, f"Skill package directory for {skill_id} not found")

    # Create an in-memory zip file
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in package_path.rglob("*"):
            if file_path.is_file() and "__pycache__" not in file_path.parts:
                arcname = file_path.relative_to(package_path)
                zf.write(file_path, arcname)

    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={skill_id}.zip"}
    )


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, req: SkillUpdateReq):
    s = skill_store.get(skill_id)
    if s is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    updates = {k: v for k, v in req.model_dump(exclude_unset=True).items()}
    if "tags" in updates:
        updates["tags"] = tuple(updates["tags"])
    updates["updated_at"] = skills_now_iso()
    updated = replace(s, **updates)
    skill_store.save(updated)
    return {"status": "updated", "skill": serialize_skill(updated)}


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    if skill_store.get(skill_id) is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    package_path = skill_store.package_path(skill_id)
    if package_path.exists():
        shutil.rmtree(package_path, ignore_errors=True)
    if not skill_store.delete(skill_id):
        raise HTTPException(404, f"Skill {skill_id} not found")
    return {"status": "deleted", "skill_id": skill_id}


@router.delete("/employees/{employee_id}/skills/{skill_id}")
async def uninstall_skill(employee_id: str, skill_id: str):
    if not binding_store.remove(employee_id, skill_id):
        raise HTTPException(404, "Binding not found")
    return {"status": "uninstalled", "skill_id": skill_id}


@router.get("/skills/{skill_id}/configs")
async def list_skill_configs(skill_id: str):
    skill = skill_store.get(skill_id)
    if skill is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    package_path = _PROJECT_ROOT / skill.package_dir
    if not package_path.exists():
        return {"configs": []}
    configs = []
    keys_map = {k["key"]: k["developer_name"] for k in usage_store.list_keys()}
    for f in sorted(package_path.glob(".db-config*.json")):
        name = f.stem  # e.g. .db-config-ak-xxx
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        # 识别用户
        user = "默认"
        for key_val, dev_name in keys_map.items():
            if key_val in name:
                user = dev_name
                break
        safe = {k: v for k, v in data.items() if k != "password"}
        safe["password"] = "***"
        configs.append({"user": user, "file": f.name, "config": safe})
    return {"configs": configs}
