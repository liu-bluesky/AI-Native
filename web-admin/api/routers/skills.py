"""技能管理路由"""

from __future__ import annotations

import fnmatch
import io
import json
import shutil
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from core.deps import employee_store, ensure_permission, require_auth, usage_store
from core.ownership import assert_can_manage_record, ownership_payload
from models.requests import SkillCreateReq, SkillInstallReq, SkillUpdateReq
from services.dynamic_mcp_skill_proxies import discover_skill_proxy_specs
from services.skill_import_service import (
    PROJECT_ROOT,
    SENSITIVE_SKILL_FILE_PATTERNS,
    backfill_existing_skill_packages,
    import_skill_from_dir,
    pick_extracted_skill_dir,
    read_manifest,
    read_skill_frontmatter,
    scan_declared_proxy_entries,
    scan_proxy_entries,
)
from stores.mcp_bridge import (
    EmployeeSkillBinding,
    Skill,
    binding_store,
    serialize_skill,
    skill_store,
    skills_now_iso,
)

def _require_skill_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.skills")


router = APIRouter(
    prefix="/api",
    dependencies=[Depends(require_auth), Depends(_require_skill_permission)],
)
_MAX_ZIP_SIZE = 20 * 1024 * 1024
_MAX_FILE_PREVIEW_SIZE = 200 * 1024


def _ensure_historical_skills_registered() -> None:
    backfill_existing_skill_packages()


def _cleanup_employee_skill_references(skill_id: str) -> list[str]:
    cleaned_employee_ids: list[str] = []
    normalized_skill_id = str(skill_id or "").strip()
    if not normalized_skill_id:
        return cleaned_employee_ids
    for employee in employee_store.list_all():
        current_skills = [
            str(item or "").strip()
            for item in (getattr(employee, "skills", []) or [])
            if str(item or "").strip()
        ]
        next_skills = [item for item in current_skills if item != normalized_skill_id]
        if next_skills == current_skills:
            continue
        employee.skills = next_skills
        employee.updated_at = skills_now_iso()
        employee_store.save(employee)
        cleaned_employee_ids.append(str(getattr(employee, "id", "") or "").strip())
    return cleaned_employee_ids


def _upsert_employee_skill_reference(employee_id: str, skill_id: str) -> bool:
    employee = employee_store.get(employee_id)
    if employee is None:
        raise HTTPException(404, f"Employee {employee_id} not found")
    normalized_skill_id = str(skill_id or "").strip()
    if not normalized_skill_id:
        raise HTTPException(400, "skill_id is required")
    current_skills = [
        str(item or "").strip()
        for item in (getattr(employee, "skills", []) or [])
        if str(item or "").strip()
    ]
    if normalized_skill_id in current_skills:
        return False
    employee.skills = [*current_skills, normalized_skill_id]
    employee.updated_at = skills_now_iso()
    employee_store.save(employee)
    return True


def _remove_employee_skill_reference(employee_id: str, skill_id: str) -> bool:
    employee = employee_store.get(employee_id)
    if employee is None:
        return False
    normalized_skill_id = str(skill_id or "").strip()
    current_skills = [
        str(item or "").strip()
        for item in (getattr(employee, "skills", []) or [])
        if str(item or "").strip()
    ]
    next_skills = [item for item in current_skills if item != normalized_skill_id]
    if next_skills == current_skills:
        return False
    employee.skills = next_skills
    employee.updated_at = skills_now_iso()
    employee_store.save(employee)
    return True


def _resolve_skill_package_path(skill: Skill) -> Path | None:
    package_dir = str(getattr(skill, "package_dir", "") or "").strip()
    if not package_dir:
        return None
    package_path = Path(package_dir)
    if not package_path.is_absolute():
        package_path = PROJECT_ROOT / package_path
    package_path = package_path.resolve()
    if not package_path.exists() or not package_path.is_dir():
        return None
    return package_path


def _scan_proxy_candidate_files(package_path: Path) -> dict[str, Any]:
    candidate_files: list[str] = []
    tools_dir_exists = (package_path / "tools").exists()
    scripts_dir_exists = (package_path / "scripts").exists()
    for base_dir in ("tools", "scripts"):
        root = package_path / base_dir
        if not root.exists():
            continue
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in {".py", ".js"}:
                continue
            candidate_files.append(file.relative_to(package_path).as_posix())
    return {
        "tools_dir_exists": tools_dir_exists,
        "scripts_dir_exists": scripts_dir_exists,
        "candidate_files": candidate_files,
    }


def _collect_skill_proxy_state(skill: Skill) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    package_path = _resolve_skill_package_path(skill)
    resolved_entries = list(getattr(skill, "proxy_entries", ()) or ())
    declared_entries = []
    diagnostics: dict[str, Any] = {
        "package_exists": bool(package_path),
        "tools_dir_exists": False,
        "scripts_dir_exists": False,
        "candidate_files": [],
        "guidance": [],
        "can_refresh": bool(package_path),
    }
    if package_path is not None:
        manifest = read_manifest(package_path)
        frontmatter = read_skill_frontmatter(package_path)
        declared_entries = list(scan_declared_proxy_entries(package_path, manifest, frontmatter))
        resolved_entries = list(scan_proxy_entries(package_path, manifest, frontmatter))
        diagnostics.update(_scan_proxy_candidate_files(package_path))

    effective_specs = discover_skill_proxy_specs(skill)
    declaration_status = "none"
    if resolved_entries:
        declaration_status = (
            "declared"
            if any(str(getattr(entry, "source", "") or "") == "declared" for entry in resolved_entries)
            else "auto_inferred"
        )

    guidance: list[str] = []
    if package_path is None:
        guidance.append("技能包目录不存在或不可读取，先修复 package_dir。")
    elif not diagnostics["candidate_files"] and not declared_entries:
        if not diagnostics["tools_dir_exists"] and not diagnostics["scripts_dir_exists"]:
            guidance.append("在技能包下新增 scripts/ 或 tools/ 目录，并放入 .py/.js 可执行文件。")
        else:
            guidance.append("在现有 scripts/ 或 tools/ 目录下添加 .py/.js 可执行文件。")
        guidance.append("或者在 manifest.json / SKILL.md frontmatter 中显式声明 proxy_entries。")
    elif resolved_entries and not effective_specs:
        guidance.append("已解析到代理入口，但当前运行时未暴露成功，建议点击“重扫声明”后再检查项目/员工绑定。")
    elif effective_specs:
        guidance.append("技能入口已生效；如项目中仍不可见，请确认技能已安装到员工且员工已加入项目。")
    diagnostics["guidance"] = guidance

    proxy_entries_payload = [
        {
            "name": str(getattr(entry, "name", "") or ""),
            "path": str(getattr(entry, "path", "") or ""),
            "runtime": str(getattr(entry, "runtime", "") or ""),
            "description": str(getattr(entry, "description", "") or ""),
            "source": str(getattr(entry, "source", "declared") or "declared"),
            "args_schema": getattr(entry, "args_schema", {}) or {},
            "command": list(getattr(entry, "command", ()) or ()),
            "cwd": str(getattr(entry, "cwd", "") or ""),
            "employee_id_flag": str(getattr(entry, "employee_id_flag", "--employee-id") or ""),
            "api_key_flag": str(getattr(entry, "api_key_flag", "--api-key") or ""),
        }
        for entry in resolved_entries
    ]
    proxy_status = {
        "declaration_status": declaration_status,
        "declared_count": len(declared_entries),
        "resolved_count": len(resolved_entries),
        "effective_count": len(effective_specs),
        "has_explicit_declaration": bool(declared_entries),
        "has_proxy_entries": bool(resolved_entries),
        "is_executable": bool(effective_specs),
        "effective_entry_names": [str(item.get("entry_name") or "") for item in effective_specs],
        "summary": (
            "已显式声明代理入口"
            if declaration_status == "declared"
            else "上传时自动推断代理入口"
            if declaration_status == "auto_inferred"
            else "未发现代理入口"
        ),
        "diagnostics": diagnostics,
    }
    return proxy_entries_payload, proxy_status


def _serialize_skill_payload(skill: Skill, auth_payload: dict | None = None) -> dict[str, Any]:
    payload = serialize_skill(skill)
    proxy_entries, proxy_status = _collect_skill_proxy_state(skill)
    payload["proxy_entries"] = proxy_entries
    payload["proxy_status"] = proxy_status
    payload.update(ownership_payload(skill, auth_payload))
    return payload


def _resolve_skill_package(skill_id: str) -> tuple[Skill, Path]:
    _ensure_historical_skills_registered()
    skill = skill_store.get(skill_id)
    if skill is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    package_path = PROJECT_ROOT / str(skill.package_dir or "").strip()
    if not package_path.exists() or not package_path.is_dir():
        raise HTTPException(404, f"Skill package directory for {skill_id} not found")
    return skill, package_path


def _is_sensitive_skill_path(rel_path: Path) -> bool:
    name = rel_path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in SENSITIVE_SKILL_FILE_PATTERNS)


def _is_hidden_skill_path(rel_path: Path) -> bool:
    return any(part.startswith(".") for part in rel_path.parts)


def _should_skip_skill_path(rel_path: Path) -> bool:
    return (
        "__pycache__" in rel_path.parts
        or _is_hidden_skill_path(rel_path)
        or _is_sensitive_skill_path(rel_path)
    )


def _build_skill_package_tree(root: Path, current: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in sorted(current.iterdir(), key=lambda path: (path.is_file(), path.name.lower())):
        rel_path = item.relative_to(root)
        if _should_skip_skill_path(rel_path):
            continue
        node: dict[str, Any] = {
            "label": item.name,
            "path": rel_path.as_posix(),
            "kind": "dir" if item.is_dir() else "file",
        }
        if item.is_dir():
            node["children"] = _build_skill_package_tree(root, item)
        else:
            node["size"] = item.stat().st_size
        items.append(node)
    return items


def _resolve_skill_file_path(package_path: Path, raw_path: str) -> tuple[Path, Path]:
    normalized = str(raw_path or "").strip()
    if not normalized:
        raise HTTPException(400, "path is required")
    rel_path = Path(normalized)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise HTTPException(400, "Invalid file path")
    if _should_skip_skill_path(rel_path):
        raise HTTPException(404, "Skill file not found")
    resolved = (package_path / rel_path).resolve()
    try:
        resolved.relative_to(package_path.resolve())
    except ValueError as exc:
        raise HTTPException(400, "Invalid file path") from exc
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(404, "Skill file not found")
    return rel_path, resolved


def _read_skill_file_preview(file_path: Path) -> tuple[str, bool, bool]:
    size = file_path.stat().st_size
    with file_path.open("rb") as handle:
        sample = handle.read(_MAX_FILE_PREVIEW_SIZE + 1)
    truncated = size > _MAX_FILE_PREVIEW_SIZE
    payload = sample[:_MAX_FILE_PREVIEW_SIZE]
    is_binary = b"\x00" in payload
    if is_binary:
        return "", True, truncated
    return payload.decode("utf-8", errors="replace"), False, truncated


@router.get("/skills")
async def list_skills(auth_payload: dict = Depends(require_auth)):
    _ensure_historical_skills_registered()
    skills = skill_store.list_all()
    return {"skills": [_serialize_skill_payload(skill, auth_payload) for skill in skills]}


@router.get("/skills/query/{domain}")
async def query_skills(domain: str, auth_payload: dict = Depends(require_auth)):
    _ensure_historical_skills_registered()
    results = skill_store.query(domain=domain)
    return {"skills": [_serialize_skill_payload(skill, auth_payload) for skill in results]}


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_historical_skills_registered()
    skill = skill_store.get(skill_id)
    if skill is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    return {"skill": _serialize_skill_payload(skill, auth_payload)}


@router.post("/skills/{skill_id}/refresh-proxy-entries")
async def refresh_skill_proxy_entries(skill_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_historical_skills_registered()
    skill = skill_store.get(skill_id)
    if skill is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    assert_can_manage_record(skill, auth_payload, "技能")
    package_path = _resolve_skill_package_path(skill)
    if package_path is None:
        raise HTTPException(404, f"Skill package directory for {skill_id} not found")
    manifest = read_manifest(package_path)
    frontmatter = read_skill_frontmatter(package_path)
    updated = replace(
        skill,
        proxy_entries=scan_proxy_entries(package_path, manifest, frontmatter),
        updated_at=skills_now_iso(),
    )
    skill_store.save(updated)
    return {"status": "updated", "skill": _serialize_skill_payload(updated, auth_payload)}


@router.get("/skills/{skill_id}/package-tree")
async def get_skill_package_tree(skill_id: str):
    _, package_path = _resolve_skill_package(skill_id)
    return {"tree": _build_skill_package_tree(package_path, package_path)}


@router.get("/skills/{skill_id}/package-file")
async def get_skill_package_file(skill_id: str, path: str):
    _, package_path = _resolve_skill_package(skill_id)
    rel_path, file_path = _resolve_skill_file_path(package_path, path)
    content, is_binary, truncated = _read_skill_file_preview(file_path)
    return {
        "file": {
            "name": file_path.name,
            "path": rel_path.as_posix(),
            "size": file_path.stat().st_size,
            "is_binary": is_binary,
            "truncated": truncated,
            "content": content,
        }
    }


@router.get("/employees/{employee_id}/skills")
async def employee_skills(employee_id: str):
    employee = employee_store.get(employee_id)
    bindings = binding_store.get_bindings(employee_id)
    binding_by_skill_id = {
        str(binding.skill_id or "").strip(): binding
        for binding in bindings
        if str(binding.skill_id or "").strip()
    }
    skill_ids: list[str] = []
    for skill_id in getattr(employee, "skills", []) if employee else []:
        normalized_skill_id = str(skill_id or "").strip()
        if normalized_skill_id and normalized_skill_id not in skill_ids:
            skill_ids.append(normalized_skill_id)
    for skill_id in binding_by_skill_id:
        if skill_id not in skill_ids:
            skill_ids.append(skill_id)

    items = []
    for skill_id in skill_ids:
        binding = binding_by_skill_id.get(skill_id)
        skill = skill_store.get(skill_id)
        enabled_tools = list(binding.enabled_tools) if binding else [tool.name for tool in getattr(skill, "tools", ()) or ()]
        items.append(
            {
                "skill_id": skill_id,
                "skill_name": skill.name if skill else skill_id,
                "enabled_tools": enabled_tools,
                "installed_at": binding.installed_at if binding else "",
                "source": "binding" if binding else "employee_profile",
            }
        )
    return {"bindings": items}


@router.post("/employees/{employee_id}/skills")
async def install_skill(employee_id: str, req: SkillInstallReq):
    employee = employee_store.get(employee_id)
    if employee is None:
        raise HTTPException(404, f"Employee {employee_id} not found")
    skill = skill_store.get(req.skill_id)
    if skill is None:
        raise HTTPException(404, f"Skill {req.skill_id} not found")
    enabled_tools = tuple(req.enabled_tools) or tuple(tool.name for tool in getattr(skill, "tools", ()) or ())
    binding = EmployeeSkillBinding(
        employee_id=employee_id,
        skill_id=req.skill_id,
        enabled_tools=enabled_tools,
    )
    binding_store.add(binding)
    _upsert_employee_skill_reference(employee.id, req.skill_id)
    return {
        "status": "installed",
        "skill_id": req.skill_id,
        "employee_id": employee.id,
        "enabled_tools": list(enabled_tools),
    }


@router.post("/skills")
async def create_skill(req: SkillCreateReq, auth_payload: dict = Depends(require_auth)):
    result = import_skill_from_dir(req, auth_payload)
    return {"status": "created", "skill": _serialize_skill_payload(result.skill, auth_payload)}


@router.post("/skills/import")
async def import_skill(req: SkillCreateReq, auth_payload: dict = Depends(require_auth)):
    result = import_skill_from_dir(req, auth_payload)
    return {"status": "created", "skill": _serialize_skill_payload(result.skill, auth_payload)}


@router.post("/skills/import-file")
async def import_skill_file(
    file: UploadFile = File(...),
    name: str = Form(""),
    version: str = Form(""),
    description: str = Form(""),
    mcp_service: str = Form(""),
    tags: str = Form(""),
    mcp_enabled: bool = Form(False),
    auth_payload: dict = Depends(require_auth),
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
        except zipfile.BadZipFile as exc:
            raise HTTPException(400, "Invalid zip file") from exc

        source_dir = pick_extracted_skill_dir(extract_dir)
        payload: dict[str, Any] = {"source_dir": str(source_dir), "mcp_enabled": mcp_enabled}
        if name.strip():
            payload["name"] = name.strip()
        if version.strip():
            payload["version"] = version.strip()
        if description.strip():
            payload["description"] = description.strip()
        if mcp_service.strip():
            payload["mcp_service"] = mcp_service.strip()
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if tag_list:
            payload["tags"] = tag_list
        result = import_skill_from_dir(SkillCreateReq(**payload), auth_payload)
    return {"status": "created", "skill": _serialize_skill_payload(result.skill, auth_payload)}


@router.get("/skills/{skill_id}/export")
async def export_skill(skill_id: str):
    _, package_path = _resolve_skill_package(skill_id)

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
        headers={"Content-Disposition": f"attachment; filename={skill_id}.zip"},
    )


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, req: SkillUpdateReq, auth_payload: dict = Depends(require_auth)):
    skill = skill_store.get(skill_id)
    if skill is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    assert_can_manage_record(skill, auth_payload, "技能")
    updates = {key: value for key, value in req.model_dump(exclude_unset=True).items()}
    if "tags" in updates:
        updates["tags"] = tuple(updates["tags"])
    updates["updated_at"] = skills_now_iso()
    updated = replace(skill, **updates)
    skill_store.save(updated)
    return {"status": "updated", "skill": _serialize_skill_payload(updated, auth_payload)}


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, auth_payload: dict = Depends(require_auth)):
    skill = skill_store.get(skill_id)
    if skill is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    assert_can_manage_record(skill, auth_payload, "技能")
    package_path = skill_store.package_path(skill_id)
    if package_path.exists():
        shutil.rmtree(package_path, ignore_errors=True)
    if not skill_store.delete(skill_id):
        raise HTTPException(404, f"Skill {skill_id} not found")
    cleaned_employee_ids = _cleanup_employee_skill_references(skill_id)
    return {
        "status": "deleted",
        "skill_id": skill_id,
        "cleaned_employee_skill_refs_count": len(cleaned_employee_ids),
        "cleaned_employee_skill_ref_ids": cleaned_employee_ids,
    }


@router.delete("/employees/{employee_id}/skills/{skill_id}")
async def uninstall_skill(employee_id: str, skill_id: str):
    removed_binding = binding_store.remove(employee_id, skill_id)
    removed_skill_ref = _remove_employee_skill_reference(employee_id, skill_id)
    if not removed_binding and not removed_skill_ref:
        raise HTTPException(404, "Binding not found")
    return {
        "status": "uninstalled",
        "skill_id": skill_id,
        "employee_id": employee_id,
        "removed_binding": removed_binding,
        "removed_employee_skill": removed_skill_ref,
    }


@router.get("/skills/{skill_id}/configs")
async def list_skill_configs(skill_id: str):
    skill = skill_store.get(skill_id)
    if skill is None:
        raise HTTPException(404, f"Skill {skill_id} not found")
    package_path = PROJECT_ROOT / skill.package_dir
    if not package_path.exists():
        return {"configs": []}
    configs = []
    keys_map = {key["key"]: key["developer_name"] for key in usage_store.list_keys()}
    for file in sorted(package_path.glob(".db-config*.json")):
        name = file.stem
        try:
            data = json.loads(file.read_text())
        except Exception:
            continue
        user = "默认"
        for key_val, dev_name in keys_map.items():
            if key_val in name:
                user = dev_name
                break
        safe = {key: value for key, value in data.items() if key != "password"}
        safe["password"] = "***"
        configs.append({"user": user, "file": file.name, "config": safe})
    return {"configs": configs}
