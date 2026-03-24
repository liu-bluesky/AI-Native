"""系统配置路由"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from core.deps import ensure_any_permission, ensure_permission, require_auth, system_config_store
from models.requests import SystemConfigUpdateReq
from services.system_mcp_discovery import list_system_mcp_skills
from stores.json.system_config_store import (
    normalize_employee_external_skill_sites,
    normalize_dictionaries,
    normalize_skill_registry_sources,
    normalize_system_mcp_config,
)

def _require_system_config_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.system.config")


def _require_system_config_read_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_any_permission(
        auth_payload,
        ["menu.system.config", "menu.ai.chat", "menu.projects", "menu.employees"],
    )


router = APIRouter(prefix="/api/system-config", dependencies=[Depends(require_auth)])


@router.get("")
async def get_system_config(
    _: None = Depends(_require_system_config_read_permission),
):
    cfg = system_config_store.get_global()
    return {"config": asdict(cfg)}


@router.get("/mcp-skills")
async def get_system_mcp_skills(
    _: None = Depends(_require_system_config_permission),
):
    cfg = system_config_store.get_global()
    servers = list_system_mcp_skills(getattr(cfg, "mcp_config", {}))
    return {"servers": servers, "total": len(servers)}


@router.patch("")
async def patch_system_config(
    req: SystemConfigUpdateReq,
    _: None = Depends(_require_system_config_permission),
):
    updates = req.model_dump(exclude_none=True)
    if not updates:
        cfg = system_config_store.get_global()
        return {"status": "no_change", "config": asdict(cfg)}

    allowed = {
        "enable_project_manual_generation",
        "enable_employee_manual_generation",
        "enable_user_register",
        "chat_upload_max_limit",
        "chat_max_tokens",
        "default_chat_system_prompt",
        "employee_auto_rule_generation_enabled",
        "employee_auto_rule_generation_source_filters",
        "employee_auto_rule_generation_max_count",
        "employee_auto_rule_generation_prompt",
        "employee_external_skill_sites",
        "skill_registry_sources",
        "dictionaries",
        "mcp_config",
    }
    invalid = [key for key in updates.keys() if key not in allowed]
    if invalid:
        raise HTTPException(400, f"Invalid system config keys: {invalid}")

    if "chat_upload_max_limit" in updates:
        try:
            value = int(updates["chat_upload_max_limit"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "chat_upload_max_limit must be an integer") from exc
        if value < 1 or value > 20:
            raise HTTPException(400, "chat_upload_max_limit must be between 1 and 20")
        updates["chat_upload_max_limit"] = value

    if "chat_max_tokens" in updates:
        try:
            value = int(updates["chat_max_tokens"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "chat_max_tokens must be an integer") from exc
        if value < 128 or value > 8192:
            raise HTTPException(400, "chat_max_tokens must be between 128 and 8192")
        updates["chat_max_tokens"] = value

    if "default_chat_system_prompt" in updates:
        updates["default_chat_system_prompt"] = str(updates["default_chat_system_prompt"] or "").strip()[:8000]

    if "employee_auto_rule_generation_source_filters" in updates:
        raw_filters = updates["employee_auto_rule_generation_source_filters"]
        if raw_filters is None:
            normalized_filters = ["prompts_chat_curated"]
        elif not isinstance(raw_filters, list):
            raise HTTPException(400, "employee_auto_rule_generation_source_filters must be an array")
        else:
            normalized_filters = []
            seen: set[str] = set()
            for item in raw_filters:
                value = str(item or "").strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                normalized_filters.append(value)
            if not normalized_filters:
                normalized_filters = ["prompts_chat_curated"]
        allowed_filters = {"prompts_chat_curated"}
        invalid_filters = [value for value in normalized_filters if value not in allowed_filters]
        if invalid_filters:
            raise HTTPException(400, f"Invalid employee auto rule sources: {invalid_filters}")
        updates["employee_auto_rule_generation_source_filters"] = normalized_filters

    if "employee_auto_rule_generation_max_count" in updates:
        try:
            value = int(updates["employee_auto_rule_generation_max_count"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "employee_auto_rule_generation_max_count must be an integer") from exc
        if value < 1 or value > 6:
            raise HTTPException(400, "employee_auto_rule_generation_max_count must be between 1 and 6")
        updates["employee_auto_rule_generation_max_count"] = value

    if "employee_auto_rule_generation_prompt" in updates:
        updates["employee_auto_rule_generation_prompt"] = (
            str(updates["employee_auto_rule_generation_prompt"] or "").strip()[:8000]
        )

    if "employee_external_skill_sites" in updates:
        updates["employee_external_skill_sites"] = normalize_employee_external_skill_sites(
            updates["employee_external_skill_sites"]
        )

    if "skill_registry_sources" in updates:
        updates["skill_registry_sources"] = normalize_skill_registry_sources(
            updates["skill_registry_sources"]
        )

    if "dictionaries" in updates:
        if not isinstance(updates["dictionaries"], dict):
            raise HTTPException(400, "dictionaries must be a JSON object")
        updates["dictionaries"] = normalize_dictionaries(updates["dictionaries"])

    if "mcp_config" in updates:
        if not isinstance(updates["mcp_config"], dict):
            raise HTTPException(400, "mcp_config must be a JSON object")
        updates["mcp_config"] = normalize_system_mcp_config(updates["mcp_config"])

    updated = system_config_store.patch_global(updates)
    return {"status": "updated", "config": asdict(updated)}
