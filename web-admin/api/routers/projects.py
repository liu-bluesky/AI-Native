"""项目管理路由"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict, replace
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
import asyncio
from services.agent_orchestrator import AgentOrchestrator
from services.conversation_manager import ConversationManager
from core.redis_client import get_redis_client

# from ai_decision import ai_decide_action, execute_db_query, recommend_better_project  # 已废弃
from core.auth import decode_token
from core.deps import employee_store, external_mcp_store, is_admin_like, local_connector_store, project_chat_store, project_store, require_auth, role_store, system_config_store, user_store
from services.feedback_service import get_feedback_service
from services.local_connector_service import (
    LocalConnectorLlmAdapter,
    build_local_connector_provider_id,
    chat_completion_via_connector,
    connector_base_url,
    list_connector_llm_models,
    parse_local_connector_provider_id,
)
from models.requests import (
    ProjectAiEntryFileUpdateReq,
    ProjectChatHistoryTruncateReq,
    ProjectChatReq,
    ProjectChatSettingsUpdateReq,
    ProjectCreateReq,
    ProjectMemberAddReq,
    ProjectUserAddReq,
    ProjectUpdateReq,
    WorkspaceDirectoryPickReq,
    WorkspaceFilePickReq,
)
from stores.json.project_chat_store import ProjectChatMessage
from stores.json.project_store import ProjectConfig, ProjectMember, ProjectUserMember, _now_iso
from core.role_permissions import has_permission, resolve_role_permissions
from stores.mcp_bridge import rule_store, skill_store

router = APIRouter(prefix="/api/projects", dependencies=[Depends(require_auth)])


_PROJECT_CHAT_SETTINGS_DEFAULTS: dict[str, Any] = {
    "chat_mode": "system",
    "local_connector_id": "",
    "connector_workspace_path": "",
    "connector_sandbox_mode": "workspace-write",
    "connector_sandbox_mode_explicit": False,
    "selected_employee_id": "",
    "selected_employee_ids": [],
    "provider_id": "",
    "model_name": "",
    "temperature": 0.1,
    "max_tokens": 512,
    "system_prompt": "",
    "auto_use_tools": True,
    "enabled_project_tool_names": [],
    "tool_priority": [],
    "max_tool_calls_per_round": 6,
    "max_loop_rounds": 20,
    "max_tool_rounds": 6,
    "repeated_tool_call_threshold": 2,
    "tool_only_threshold": 3,
    "tool_budget_strategy": "finalize",
    "history_limit": 20,
    "upload_file_limit": 6,
    "max_file_size_mb": 15,
    "doc_max_chars_per_file": 1200,
    "doc_max_chars_total": 3000,
    "allowed_file_types": [
        "image/*",
        ".wps",
        ".doc",
        ".docx",
        ".pdf",
        ".txt",
        ".csv",
        ".xlsx",
        ".xls",
    ],
    "high_risk_tool_confirm": True,
    "tool_timeout_sec": 60,
    "tool_retry_count": 0,
    "allow_shell_tools": True,
    "allow_file_write_tools": True,
    "answer_style": "concise",
    "prefer_conclusion_first": True,
}


def _serialize_project(project: ProjectConfig) -> dict:
    data = asdict(project)
    data.pop("chat_settings", None)
    data["member_count"] = len(project_store.list_members(project.id))
    data["user_count"] = len(project_store.list_user_members(project.id))
    return data


def _to_unique_string_list(values: Any, *, max_items: int = 100, max_item_len: int = 120) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        if len(text) > max_item_len:
            text = text[:max_item_len]
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _coerce_float(value: Any, default: float, *, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _normalize_project_chat_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    settings = dict(_PROJECT_CHAT_SETTINGS_DEFAULTS)
    settings["chat_mode"] = "system"
    sandbox_mode_explicit = _coerce_bool(
        source.get(
            "connector_sandbox_mode_explicit",
            source.get(
                "external_agent_sandbox_mode_explicit",
                settings["connector_sandbox_mode_explicit"],
            ),
        ),
        settings["connector_sandbox_mode_explicit"],
    )
    sandbox_mode = str(
        source.get(
            "connector_sandbox_mode",
            source.get(
                "external_agent_sandbox_mode",
                settings["connector_sandbox_mode"],
            ),
        )
        or ""
    ).strip().lower()
    normalized_sandbox_mode = sandbox_mode if sandbox_mode in {"read-only", "workspace-write"} else settings["connector_sandbox_mode"]
    if normalized_sandbox_mode == "read-only" and not sandbox_mode_explicit:
        normalized_sandbox_mode = settings["connector_sandbox_mode"]
    settings["connector_sandbox_mode"] = normalized_sandbox_mode
    settings["connector_sandbox_mode_explicit"] = sandbox_mode_explicit
    settings["local_connector_id"] = str(source.get("local_connector_id", settings["local_connector_id"]) or "").strip()
    settings["connector_workspace_path"] = str(source.get("connector_workspace_path", settings["connector_workspace_path"]) or "").strip()
    settings["selected_employee_id"] = str(source.get("selected_employee_id", settings["selected_employee_id"]) or "").strip()
    settings["selected_employee_ids"] = _to_unique_string_list(source.get("selected_employee_ids"), max_items=200, max_item_len=120)
    if not settings["selected_employee_ids"] and settings["selected_employee_id"]:
        settings["selected_employee_ids"] = [settings["selected_employee_id"]]
    settings["provider_id"] = str(source.get("provider_id", settings["provider_id"]) or "").strip()
    settings["model_name"] = str(source.get("model_name", settings["model_name"]) or "").strip()
    settings["temperature"] = _coerce_float(source.get("temperature"), settings["temperature"], min_value=0.0, max_value=2.0)
    settings["max_tokens"] = _coerce_int(source.get("max_tokens"), settings["max_tokens"], min_value=128, max_value=8192)
    settings["system_prompt"] = str(source.get("system_prompt", settings["system_prompt"]) or "").strip()[:4000]
    settings["auto_use_tools"] = _coerce_bool(source.get("auto_use_tools"), settings["auto_use_tools"])
    settings["enabled_project_tool_names"] = _to_unique_string_list(source.get("enabled_project_tool_names"), max_items=200, max_item_len=160)
    settings["tool_priority"] = _to_unique_string_list(source.get("tool_priority"), max_items=200, max_item_len=160)
    settings["max_tool_calls_per_round"] = _coerce_int(source.get("max_tool_calls_per_round"), settings["max_tool_calls_per_round"], min_value=1, max_value=30)
    settings["max_loop_rounds"] = _coerce_int(source.get("max_loop_rounds"), settings["max_loop_rounds"], min_value=1, max_value=60)
    settings["max_tool_rounds"] = _coerce_int(source.get("max_tool_rounds"), settings["max_tool_rounds"], min_value=1, max_value=30)
    settings["repeated_tool_call_threshold"] = _coerce_int(source.get("repeated_tool_call_threshold"), settings["repeated_tool_call_threshold"], min_value=1, max_value=10)
    settings["tool_only_threshold"] = _coerce_int(source.get("tool_only_threshold"), settings["tool_only_threshold"], min_value=1, max_value=10)
    strategy = str(source.get("tool_budget_strategy", settings["tool_budget_strategy"]) or "").strip().lower()
    settings["tool_budget_strategy"] = strategy if strategy in {"stop", "finalize"} else settings["tool_budget_strategy"]
    settings["history_limit"] = _coerce_int(source.get("history_limit"), settings["history_limit"], min_value=1, max_value=50)
    settings["upload_file_limit"] = _coerce_int(source.get("upload_file_limit"), settings["upload_file_limit"], min_value=1, max_value=20)
    settings["max_file_size_mb"] = _coerce_int(source.get("max_file_size_mb"), settings["max_file_size_mb"], min_value=1, max_value=100)
    settings["doc_max_chars_per_file"] = _coerce_int(source.get("doc_max_chars_per_file"), settings["doc_max_chars_per_file"], min_value=100, max_value=20000)
    settings["doc_max_chars_total"] = _coerce_int(source.get("doc_max_chars_total"), settings["doc_max_chars_total"], min_value=500, max_value=100000)
    settings["allowed_file_types"] = _to_unique_string_list(source.get("allowed_file_types"), max_items=40, max_item_len=20)
    settings["high_risk_tool_confirm"] = _coerce_bool(source.get("high_risk_tool_confirm"), settings["high_risk_tool_confirm"])
    settings["tool_timeout_sec"] = _coerce_int(source.get("tool_timeout_sec"), settings["tool_timeout_sec"], min_value=1, max_value=600)
    settings["tool_retry_count"] = _coerce_int(source.get("tool_retry_count"), settings["tool_retry_count"], min_value=0, max_value=5)
    settings["allow_shell_tools"] = _coerce_bool(source.get("allow_shell_tools"), settings["allow_shell_tools"])
    settings["allow_file_write_tools"] = _coerce_bool(source.get("allow_file_write_tools"), settings["allow_file_write_tools"])
    style = str(source.get("answer_style", settings["answer_style"]) or "").strip().lower()
    settings["answer_style"] = style if style in {"concise", "balanced", "detailed"} else settings["answer_style"]
    settings["prefer_conclusion_first"] = _coerce_bool(source.get("prefer_conclusion_first"), settings["prefer_conclusion_first"])
    return settings


def _public_project_chat_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    return _normalize_project_chat_settings(raw)


def _merge_project_chat_settings_overrides(
    persisted_settings: dict[str, Any] | None,
    *,
    local_connector_id: str = "",
    connector_workspace_path: str = "",
) -> dict[str, Any]:
    merged = dict(_normalize_project_chat_settings(persisted_settings))
    normalized_connector_id = str(local_connector_id or "").strip()
    normalized_workspace_path = str(connector_workspace_path or "").strip()
    if normalized_connector_id:
        merged["local_connector_id"] = normalized_connector_id
    if normalized_workspace_path:
        merged["connector_workspace_path"] = normalized_workspace_path
    return _normalize_project_chat_settings(merged)


def _sync_feedback_project_flag(project_id: str, enabled: bool) -> None:
    try:
        get_feedback_service().update_project_config(project_id, enabled=enabled)
    except Exception:
        # 反馈升级能力在非 PG/禁用场景可能不可用；项目主流程不阻断。
        return


def _normalize_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _resolve_employee_rule_bindings(employee: Any) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    rule_ids = [str(item or "").strip() for item in (getattr(employee, "rule_ids", []) or []) if str(item or "").strip()]
    if rule_ids:
        seen_ids: set[str] = set()
        for rule_id in rule_ids:
            if rule_id in seen_ids:
                continue
            seen_ids.add(rule_id)
            rule = rule_store.get(rule_id)
            if rule is None:
                bindings.append({"id": rule_id, "title": f"{rule_id}（规则不存在）", "domain": ""})
                continue
            bindings.append(
                {
                    "id": str(getattr(rule, "id", "") or ""),
                    "title": str(getattr(rule, "title", "") or ""),
                    "domain": str(getattr(rule, "domain", "") or ""),
                }
            )
        return bindings

    domains = {_normalize_domain(item) for item in (getattr(employee, "rule_domains", []) or []) if str(item or "").strip()}
    if not domains:
        return bindings
    seen_ids: set[str] = set()
    for rule in rule_store.list_all():
        domain = _normalize_domain(getattr(rule, "domain", ""))
        if not domain or domain not in domains:
            continue
        rule_id = str(getattr(rule, "id", "") or "").strip()
        if not rule_id or rule_id in seen_ids:
            continue
        seen_ids.add(rule_id)
        bindings.append(
            {
                "id": rule_id,
                "title": str(getattr(rule, "title", "") or ""),
                "domain": str(getattr(rule, "domain", "") or ""),
            }
        )
    return bindings


def _collect_rule_domains(rule_bindings: list[dict[str, str]]) -> list[str]:
    seen: set[str] = set()
    domains: list[str] = []
    for item in rule_bindings:
        domain = str(item.get("domain", "") or "").strip()
        key = _normalize_domain(domain)
        if not key or key in seen:
            continue
        seen.add(key)
        domains.append(domain)
    return domains


def _project_member_details(project_id: str) -> list[dict]:
    items: list[dict] = []
    for member in project_store.list_members(project_id):
        employee = employee_store.get(member.employee_id)
        if employee is None:
            continue
        skill_items = []
        for skill_id in employee.skills or []:
            skill = skill_store.get(skill_id)
            skill_items.append(
                {
                    "id": skill_id,
                    "name": getattr(skill, "name", "") or skill_id,
                    "description": getattr(skill, "description", "") if skill else "",
                }
            )
        rule_bindings = _resolve_employee_rule_bindings(employee)
        items.append(
            {
                "member": member,
                "employee": employee,
                "skills": skill_items,
                "rule_bindings": rule_bindings,
            }
        )
    return items


def _assert_project_manual_generation_enabled() -> None:
    cfg = system_config_store.get_global()
    if not bool(getattr(cfg, "enable_project_manual_generation", False)):
        raise HTTPException(403, "Project manual generation is disabled by system config")


def _ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", None)
    if not has_permission(permissions, permission_key, role_id=role_id):
        raise HTTPException(403, f"Permission denied: {permission_key}")


def _ensure_any_permission(auth_payload: dict, permission_keys: list[str]) -> None:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", None)
    if any(has_permission(permissions, key, role_id=role_id) for key in permission_keys):
        return
    raise HTTPException(403, f"Permission denied: {permission_keys}")


def _project_chat_employee_candidates(project_id: str) -> list[dict[str, Any]]:
    from services.dynamic_mcp_runtime import list_project_member_profiles_runtime

    profiles = list_project_member_profiles_runtime(
        project_id,
        include_disabled=False,
        include_missing=False,
        rule_limit=30,
    )
    candidates: list[dict[str, Any]] = []
    for item in profiles:
        candidates.append(
            {
                "id": str(item.get("id") or item.get("employee_id") or ""),
                "name": str(item.get("name") or item.get("employee_name") or ""),
                "description": str(item.get("description") or ""),
                "role": str(item.get("role") or "member"),
                "enabled": bool(item.get("enabled", True)),
                "skills": list(item.get("skills") or []),
                "skill_names": list(item.get("skill_names") or []),
                "rule_bindings": list(item.get("rule_bindings") or []),
                "tone": str(item.get("tone") or ""),
                "verbosity": str(item.get("verbosity") or ""),
                "language": str(item.get("language") or ""),
                "mcp_enabled": bool(item.get("mcp_enabled", False)),
                "feedback_upgrade_enabled": bool(item.get("feedback_upgrade_enabled", False)),
            }
        )
    return candidates


def _resolve_project_chat_employee(project_id: str, expected_employee_id: str = "") -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    candidates = _project_chat_employee_candidates(project_id)
    if not candidates:
        return None, []
    expected = str(expected_employee_id or "").strip()
    if expected:
        matched = next((item for item in candidates if item["id"] == expected), None)
        if matched is not None:
            return matched, candidates
        # 项目聊天设置是项目级共享配置。多人协作时，某个用户删除/禁用成员后，
        # 其他用户本地或项目设置里残留的 selected_employee_id 不应直接打断整轮对话。
        return None, candidates
    # 未显式指定执行员工时，不做后端“智能默认选人”。
    # 由模型在项目可用工具/员工能力范围内自行决策。
    return None, candidates


def _resolve_project_chat_employees(
    project_id: str,
    expected_employee_ids: list[str] | None = None,
    expected_employee_id: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = _project_chat_employee_candidates(project_id)
    if not candidates:
        return [], []
    by_id = {str(item.get("id") or ""): item for item in candidates if str(item.get("id") or "")}
    expected_list = [str(item or "").strip() for item in (expected_employee_ids or []) if str(item or "").strip()]
    if not expected_list:
        single = str(expected_employee_id or "").strip()
        if single:
            expected_list = [single]
    if not expected_list:
        return [], candidates
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for employee_id in expected_list:
        if employee_id in seen:
            continue
        seen.add(employee_id)
        item = by_id.get(employee_id)
        if item is not None:
            selected.append(item)
            continue
        missing.append(employee_id)
    # 对于多人共享的项目聊天配置，失效成员自动忽略并回退。
    # 这样不会因为某个残留 employee_id 直接让整个聊天入口不可用。
    return selected, candidates


def _cleanup_project_chat_employee_selection(project_id: str, employee_id: str) -> bool:
    pid = str(project_id or "").strip()
    eid = str(employee_id or "").strip()
    if not pid or not eid:
        return False
    project = project_store.get(pid)
    if project is None:
        return False
    chat_settings = dict(getattr(project, "chat_settings", {}) or {})
    selected_ids = [
        str(item or "").strip()
        for item in (chat_settings.get("selected_employee_ids") or [])
        if str(item or "").strip()
    ]
    selected_id = str(chat_settings.get("selected_employee_id") or "").strip()
    next_selected_ids = [item for item in selected_ids if item != eid]
    next_selected_id = "" if selected_id == eid else selected_id
    if next_selected_id and next_selected_id not in next_selected_ids:
        next_selected_ids.append(next_selected_id)
    if next_selected_ids == selected_ids and next_selected_id == selected_id:
        return False
    chat_settings["selected_employee_ids"] = next_selected_ids
    chat_settings["selected_employee_id"] = next_selected_id
    project.chat_settings = chat_settings
    project.updated_at = _now_iso()
    project_store.save(project)
    return True


def _pick_chat_provider(provider_id: str, auth_payload: dict) -> tuple[dict, list[dict]]:
    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
    )
    if not providers:
        raise HTTPException(400, "未配置可用的 LLM 提供商")
    expected = str(provider_id or "").strip()
    if expected:
        selected = next((item for item in providers if str(item.get("id") or "") == expected), None)
        if selected is None:
            raise HTTPException(404, f"LLM provider not found: {expected}")
        return selected, providers
    default_provider = next((item for item in providers if bool(item.get("is_default"))), providers[0])
    return default_provider, providers


async def _build_connector_chat_provider(connector: Any) -> dict[str, Any] | None:
    connector_id = str(getattr(connector, "id", "") or "").strip()
    if not connector_id or not connector_base_url(connector):
        return None
    try:
        llm_info = await list_connector_llm_models(connector)
    except Exception:
        llm_info = {
            "enabled": False,
            "default_model": "",
            "models": [],
        }
    if not bool(llm_info.get("enabled")):
        return None
    models = [
        str(item or "").strip()
        for item in (llm_info.get("models") or [])
        if str(item or "").strip()
    ]
    default_model = str(llm_info.get("default_model") or "").strip()
    if default_model and default_model not in models:
        models = [default_model, *models]
    if not models:
        return None
    connector_name = str(getattr(connector, "connector_name", "") or "").strip() or connector_id
    connector_owner = str(getattr(connector, "owner_username", "") or "").strip()
    provider_name = (
        f"本地连接器 · {connector_name} · {connector_owner}"
        if connector_owner
        else f"本地连接器 · {connector_name}"
    )
    return {
        "id": build_local_connector_provider_id(connector_id),
        "name": provider_name,
        "provider_type": "local-connector",
        "base_url": connector_base_url(connector),
        "models": models,
        "default_model": default_model or models[0],
        "enabled": True,
        "is_default": False,
        "connector_id": connector_id,
        "connector_name": connector_name,
        "connector_owner_username": connector_owner,
    }


async def _resolve_provider_runtime_target(
    provider_id: str,
    auth_payload: dict,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    connector_id = parse_local_connector_provider_id(provider_id)
    if connector_id:
        connector = _resolve_accessible_local_connector_for_llm(connector_id, auth_payload)
        if connector is None:
            raise HTTPException(404, "Local connector not found")
        provider = await _build_connector_chat_provider(connector)
        if provider is None:
            raise HTTPException(400, "当前本地连接器未配置可用模型")
        return "local_connector", provider, [provider]
    provider, providers = _pick_chat_provider(provider_id, auth_payload)
    return "provider", provider, providers


def _project_tool_display_name(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    if normalized == "query_project_rules":
        return "查询项目规则"
    if normalized == "query_project_members":
        return "查询项目成员"
    if normalized == "search_project_context":
        return "搜索项目上下文"
    return normalized


def _build_project_related_mcp_modules(project_id: str) -> list[dict[str, Any]]:
    from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime

    candidates = _project_chat_employee_candidates(project_id)
    employee_name_map = {
        str(item.get("id") or ""): str(item.get("name") or item.get("id") or "")
        for item in candidates
        if str(item.get("id") or "")
    }
    modules: list[dict[str, Any]] = []
    for tool in list_project_proxy_tools_runtime(project_id, ""):
        tool_name = str(tool.get("tool_name") or "").strip()
        if not tool_name:
            continue
        employee_id = str(tool.get("employee_id") or "").strip()
        builtin = bool(tool.get("builtin", False))
        modules.append(
            {
                "id": f"project-tool:{tool_name}",
                "name": _project_tool_display_name(tool_name),
                "provider": "system",
                "scope": "project_related",
                "module_type": "builtin_tool" if builtin else "project_skill_tool",
                "description": str(tool.get("description") or "").strip(),
                "tool_name": tool_name,
                "employee_id": employee_id,
                "employee_name": employee_name_map.get(employee_id, ""),
                "skill_id": str(tool.get("skill_id") or "").strip(),
                "entry_name": str(tool.get("entry_name") or "").strip(),
                "script_type": str(tool.get("script_type") or "").strip(),
            }
        )
    modules.sort(key=lambda item: (str(item.get("module_type") or ""), str(item.get("name") or "")))
    return modules


def _build_system_global_mcp_modules(current_project_id: str) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []

    for project in project_store.list_all():
        if not bool(getattr(project, "mcp_enabled", True)):
            continue
        modules.append(
            {
                "id": f"project-service:{project.id}",
                "name": str(getattr(project, "name", "") or project.id),
                "provider": "system",
                "scope": "system_global",
                "module_type": "project_mcp_service",
                "description": str(getattr(project, "description", "") or ""),
                "resource_id": str(project.id),
                "resource_kind": "project",
                "endpoint_http": f"/mcp/projects/{project.id}/mcp?key=YOUR_API_KEY",
                "endpoint_sse": f"/mcp/projects/{project.id}/sse?key=YOUR_API_KEY",
                "is_current_project": str(project.id) == current_project_id,
            }
        )

    for employee in employee_store.list_all():
        if not bool(getattr(employee, "mcp_enabled", True)):
            continue
        modules.append(
            {
                "id": f"employee-service:{employee.id}",
                "name": str(getattr(employee, "name", "") or employee.id),
                "provider": "system",
                "scope": "system_global",
                "module_type": "employee_mcp_service",
                "description": str(getattr(employee, "description", "") or ""),
                "resource_id": str(employee.id),
                "resource_kind": "employee",
                "endpoint_http": f"/mcp/employees/{employee.id}/mcp?key=YOUR_API_KEY&project_id={current_project_id}",
                "endpoint_sse": f"/mcp/employees/{employee.id}/sse?key=YOUR_API_KEY&project_id={current_project_id}",
            }
        )

    for skill in skill_store.list_all():
        if not bool(getattr(skill, "mcp_enabled", False)):
            continue
        modules.append(
            {
                "id": f"skill-service:{skill.id}",
                "name": str(getattr(skill, "name", "") or skill.id),
                "provider": "system",
                "scope": "system_global",
                "module_type": "skill_mcp_service",
                "description": str(getattr(skill, "description", "") or ""),
                "resource_id": str(skill.id),
                "resource_kind": "skill",
                "endpoint_http": f"/mcp/skills/{skill.id}/mcp",
                "endpoint_sse": f"/mcp/skills/{skill.id}/sse",
            }
        )

    for rule in rule_store.list_all():
        if not bool(getattr(rule, "mcp_enabled", False)):
            continue
        modules.append(
            {
                "id": f"rule-service:{rule.id}",
                "name": str(getattr(rule, "title", "") or rule.id),
                "provider": "system",
                "scope": "system_global",
                "module_type": "rule_mcp_service",
                "description": str(getattr(rule, "domain", "") or ""),
                "resource_id": str(rule.id),
                "resource_kind": "rule",
                "endpoint_http": f"/mcp/rules/{rule.id}/mcp",
                "endpoint_sse": f"/mcp/rules/{rule.id}/sse",
            }
        )

    modules.sort(
        key=lambda item: (
            0 if bool(item.get("is_current_project")) else 1,
            str(item.get("module_type") or ""),
            str(item.get("name") or ""),
        )
    )
    return modules


def _build_chat_mcp_modules(project_id: str) -> dict[str, Any]:
    system_project_related = _build_project_related_mcp_modules(project_id)
    system_global = _build_system_global_mcp_modules(project_id)
    external_modules: list[dict[str, Any]] = []
    for module in external_mcp_store.list_all():
        if not bool(getattr(module, "enabled", True)):
            continue
        module_project_id = str(getattr(module, "project_id", "") or "").strip()
        if module_project_id and module_project_id != project_id:
            continue
        external_modules.append(
            {
                "id": str(getattr(module, "id", "") or ""),
                "name": str(getattr(module, "name", "") or ""),
                "provider": "external",
                "scope": "external",
                "module_type": "external_mcp_service",
                "description": str(getattr(module, "description", "") or ""),
                "endpoint_http": str(getattr(module, "endpoint_http", "") or ""),
                "endpoint_sse": str(getattr(module, "endpoint_sse", "") or ""),
                "auth_type": str(getattr(module, "auth_type", "") or ""),
                "project_id": module_project_id,
                "enabled": bool(getattr(module, "enabled", True)),
            }
        )
    external_modules.sort(key=lambda item: (0 if item.get("project_id") == project_id else 1, str(item.get("name") or ""), str(item.get("id") or "")))
    return {
        "system": {
            "project_related": system_project_related,
            "system_global": system_global,
        },
        "external": {
            "modules": external_modules,
        },
        "summary": {
            "system_project_related_total": len(system_project_related),
            "system_global_total": len(system_global),
            "external_total": len(external_modules),
        },
    }


def _normalize_chat_history(history: list[dict] | None, *, limit: int = 20) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content})
    safe_limit = max(1, min(int(limit or 20), 100))
    return normalized[-safe_limit:]


def _filter_project_tools_by_names(
    tools: list[dict[str, Any]],
    enabled_tool_names: list[str] | None,
    *,
    explicit_filter: bool,
) -> list[dict[str, Any]]:
    normalized = [str(item or "").strip() for item in (enabled_tool_names or []) if str(item or "").strip()]
    allowed = set(normalized)
    if not allowed:
        return tools
    filtered = []
    for item in tools:
        tool_name = str(item.get("tool_name") or "").strip()
        if tool_name in allowed:
            filtered.append(item)
    return filtered


def _sort_tools_by_priority(tools: list[dict[str, Any]], tool_priority: list[str] | None) -> list[dict[str, Any]]:
    normalized = [str(item or "").strip() for item in (tool_priority or []) if str(item or "").strip()]
    if not normalized:
        return tools
    priority_map = {name: idx for idx, name in enumerate(normalized)}
    return sorted(
        tools,
        key=lambda item: (
            priority_map.get(str(item.get("tool_name") or "").strip(), 10**9),
            str(item.get("tool_name") or "").strip(),
        ),
    )


def _is_shell_like_tool(tool: dict[str, Any]) -> bool:
    merged = " ".join(
        [
            str(tool.get("tool_name") or ""),
            str(tool.get("entry_name") or ""),
            str(tool.get("description") or ""),
        ]
    ).lower()
    keywords = ("shell", "bash", "terminal", "command", "exec", "run_cmd", "run command")
    return any(word in merged for word in keywords)


def _is_file_write_like_tool(tool: dict[str, Any]) -> bool:
    merged = " ".join(
        [
            str(tool.get("tool_name") or ""),
            str(tool.get("entry_name") or ""),
            str(tool.get("description") or ""),
        ]
    ).lower()
    keywords = (
        "write",
        "save",
        "update",
        "delete",
        "remove",
        "create",
        "edit",
        "patch",
        "rename",
        "mkdir",
        "touch",
        "file",
    )
    return any(word in merged for word in keywords)


def _apply_tool_safety_filters(
    tools: list[dict[str, Any]],
    *,
    allow_shell_tools: bool,
    allow_file_write_tools: bool,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in tools:
        if not allow_shell_tools and _is_shell_like_tool(item):
            continue
        if not allow_file_write_tools and _is_file_write_like_tool(item):
            continue
        filtered.append(item)
    return filtered


def _collect_runtime_tools(
    project_id: str,
    *,
    selected_employee_ids: list[str] | None,
    enabled_tool_names: list[str] | None,
    explicit_tool_filter: bool,
    tool_priority: list[str] | None,
    allow_shell_tools: bool,
    allow_file_write_tools: bool,
) -> list[dict[str, Any]]:
    from services.dynamic_mcp_runtime import list_project_external_tools_runtime, list_project_proxy_tools_runtime

    internal_tools = list_project_proxy_tools_runtime(project_id, "")
    internal_tools = _filter_project_tools_by_employee_ids(internal_tools, selected_employee_ids)
    internal_tools = _filter_project_tools_by_names(
        internal_tools,
        enabled_tool_names,
        explicit_filter=explicit_tool_filter,
    )

    external_tools = list_project_external_tools_runtime(project_id)
    tools = internal_tools + external_tools
    tools = _sort_tools_by_priority(tools, list(tool_priority or []))
    tools = _apply_tool_safety_filters(
        tools,
        allow_shell_tools=allow_shell_tools,
        allow_file_write_tools=allow_file_write_tools,
    )
    return tools


def _summarize_effective_tools(
    tools: list[dict[str, Any]] | None,
    *,
    max_items: int = 24,
) -> tuple[list[dict[str, str]], int]:
    source_tools = tools if isinstance(tools, list) else []
    summarized: list[dict[str, str]] = []
    for item in source_tools[:max_items]:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            continue
        module_type = str(item.get("module_type") or "").strip().lower()
        if tool_name.startswith("local_connector_"):
            source = "local_connector"
        elif module_type == "external_mcp_tool":
            source = "external_mcp"
        elif module_type == "system_mcp_tool":
            source = "system_mcp"
        elif bool(item.get("builtin")) or str(item.get("skill_id") or "").strip() == "__builtin__":
            source = "builtin"
        elif str(item.get("employee_id") or "").strip():
            source = "project_skill"
        else:
            source = "project_tool"
        summarized.append(
            {
                "tool_name": tool_name,
                "source": source,
                "description": str(item.get("description") or "").strip(),
            }
        )
    return summarized, len(source_tools)


def _resolve_chat_runtime_settings(req: ProjectChatReq, project: ProjectConfig) -> dict[str, Any]:
    base = _normalize_project_chat_settings(getattr(project, "chat_settings", {}) or {})
    merged = dict(base)
    override = {
        "chat_mode": req.chat_mode,
        "local_connector_id": req.local_connector_id,
        "connector_workspace_path": req.connector_workspace_path,
        "connector_sandbox_mode": req.connector_sandbox_mode,
        "connector_sandbox_mode_explicit": req.connector_sandbox_mode_explicit,
        "selected_employee_id": req.employee_id,
        "selected_employee_ids": req.employee_ids,
        "provider_id": req.provider_id,
        "model_name": req.model_name,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "system_prompt": req.system_prompt,
        "enabled_project_tool_names": req.enabled_project_tool_names,
        "auto_use_tools": req.auto_use_tools,
        "tool_priority": req.tool_priority,
        "max_tool_calls_per_round": req.max_tool_calls_per_round,
        "max_loop_rounds": req.max_loop_rounds,
        "max_tool_rounds": req.max_tool_rounds,
        "repeated_tool_call_threshold": req.repeated_tool_call_threshold,
        "tool_only_threshold": req.tool_only_threshold,
        "tool_budget_strategy": req.tool_budget_strategy,
        "history_limit": req.history_limit,
        "tool_timeout_sec": req.tool_timeout_sec,
        "tool_retry_count": req.tool_retry_count,
        "allow_shell_tools": req.allow_shell_tools,
        "allow_file_write_tools": req.allow_file_write_tools,
        "answer_style": req.answer_style,
        "prefer_conclusion_first": req.prefer_conclusion_first,
    }
    for key, value in override.items():
        if key in req.model_fields_set and value is not None:
            merged[key] = value
    return _normalize_project_chat_settings(merged)


def _filter_project_tools_by_employee_ids(
    tools: list[dict[str, Any]],
    employee_ids: list[str] | None,
) -> list[dict[str, Any]]:
    normalized = [str(item or "").strip() for item in (employee_ids or []) if str(item or "").strip()]
    allowed = set(normalized)
    if not allowed:
        return tools
    filtered: list[dict[str, Any]] = []
    for item in tools:
        employee_id = str(item.get("employee_id") or "").strip()
        # builtin / global tool keeps empty employee_id
        if not employee_id or employee_id in allowed:
            filtered.append(item)
    return filtered


def _normalize_image_inputs(images: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for item in images or []:
        value = str(item or "").strip()
        if not value:
            continue
        lower = value.lower()
        if re.match(r"^data:image/[a-z0-9.+-]+;base64,", lower):
            normalized.append(value)
            continue
        if lower.startswith("http://") or lower.startswith("https://"):
            normalized.append(value)
    return normalized


def _normalize_skill_resource_directory(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    return normalized[:1000]


def _build_skill_resource_prompt_block(skill_resource_directory: str) -> str:
    normalized = _normalize_skill_resource_directory(skill_resource_directory)
    if not normalized:
        return ""
    return (
        f"\n\n当前已为本轮对话指定本地技能目录: {normalized}\n"
        "当用户提到缺少技能、查找技能模板、下载技能、安装技能或复用本地 skill 时，优先把这个目录视为当前可参考的本地技能来源。"
        "\n如果当前模式或工具链能够访问该目录，请优先读取其中的 SKILL.md、模板和脚本后再回答或执行。"
        "\n如果当前模式无法直接访问该目录，请先明确说明限制，再给出下一步操作建议。"
        "\n除非用户明确要求，不要把该目录中的技能自动导入系统。"
    )


def _build_project_chat_messages(
    project: ProjectConfig,
    user_message: str,
    history: list[dict] | None,
    images: list[str] | None = None,
    selected_employee: dict[str, Any] | None = None,
    tools: list[dict] | None = None,
    custom_system_prompt: str | None = None,
    history_limit: int = 20,
    answer_style: str = "concise",
    prefer_conclusion_first: bool = True,
    workspace_path: str = "",
    skill_resource_directory: str = "",
) -> list[dict[str, Any]]:
    workspace_info = ""
    effective_workspace_path = str(workspace_path or project.workspace_path or "").strip()
    if effective_workspace_path:
        workspace_info = f"\n\n当前项目工作区路径: {effective_workspace_path}\n请在此目录下进行代码开发和文件操作。"
    ai_entry_info = ""
    ai_entry_file = str(project.ai_entry_file or "").strip()
    if ai_entry_file:
        ai_entry_path = Path(ai_entry_file).expanduser()
        if effective_workspace_path and not ai_entry_path.is_absolute():
            resolved_entry_hint = str(Path(effective_workspace_path) / ai_entry_file)
            ai_entry_info = (
                f"\n\n当前项目 AI 入口文件: {ai_entry_file}"
                f"\n该入口文件相对于项目工作区，对应路径: {resolved_entry_hint}"
                "\n在开始分析、编码、调用工具或回答项目前，优先读取这个入口文件，并按其中约定理解项目规则、目录结构、实现约束和执行顺序。"
                "\n仅当该入口文件不存在、无法访问或信息不足时，再自行补充读取项目内其他相关规则文件。"
            )
        else:
            ai_entry_info = (
                f"\n\n当前项目 AI 入口文件: {ai_entry_file}"
                "\n在开始分析、编码、调用工具或回答项目前，优先读取这个入口文件，并按其中约定理解项目规则、目录结构、实现约束和执行顺序。"
                "\n仅当该入口文件不存在、无法访问或信息不足时，再自行补充读取项目内其他相关规则文件。"
            )

    tool_names = [t.get("tool_name", "") for t in (tools or [])] if tools else []
    tool_list_text = f"可用工具({len(tool_names)}个): {', '.join(tool_names)}" if tool_names else "当前无可用工具"

    base_prompt = (custom_system_prompt or "").strip()
    if not base_prompt:
        base_prompt = "你是项目开发助手。"
        base_prompt += "\n可按需调用工具检索最新项目上下文并完成用户请求。"
        base_prompt += "\n当用户询问项目信息、员工信息、规则、MCP 服务时，优先调用 search_project_context 再回答。"
        base_prompt += "\n当用户询问当前项目有哪些员工、成员、规则、工具或 MCP 能力时，不要先说无法获取；先调用 query_project_members、query_project_rules 或 search_project_context。"

    style_hint = {
        "concise": "输出风格：简洁，避免冗长。",
        "balanced": "输出风格：平衡，先结论后关键步骤。",
        "detailed": "输出风格：详细，覆盖关键前提、步骤与风险。",
    }.get(str(answer_style or "concise").strip().lower(), "输出风格：简洁，避免冗长。")
    order_hint = "回答顺序：先给结论再给步骤。" if prefer_conclusion_first else "回答顺序：按自然推理顺序给出。"
    skill_resource_prompt = _build_skill_resource_prompt_block(
        skill_resource_directory,
    )
    system_prompt = (
        f"{base_prompt}\n{workspace_info}{ai_entry_info}\n\n{tool_list_text}\n{order_hint}\n{style_hint}"
        f"{skill_resource_prompt}"
    )
    if selected_employee:
        rule_bindings = list(selected_employee.get("rule_bindings") or [])
        rule_titles = [str(item.get("title") or item.get("id") or "").strip() for item in rule_bindings]
        rule_titles = [item for item in rule_titles if item]
        rule_domains = _collect_rule_domains(rule_bindings)
        workflow = [str(item or "").strip() for item in (selected_employee.get("default_workflow") or []) if str(item or "").strip()]
        system_prompt += (
            f"\n当前执行员工：{selected_employee.get('name') or selected_employee.get('id')} "
            f"({selected_employee.get('id')})，"
            f"goal={str(selected_employee.get('goal') or '-').strip() or '-'}，"
            f"skills={', '.join(selected_employee.get('skill_names') or []) or '-'}，"
            f"rule_titles={', '.join(rule_titles) or '-'}，"
            f"rule_domains={', '.join(rule_domains) or '-'}。"
        )
        if workflow:
            system_prompt += f"\n默认工作流：{' -> '.join(workflow)}。"
        tool_usage_policy = str(selected_employee.get("tool_usage_policy") or "").strip()
        if tool_usage_policy:
            system_prompt += f"\n工具使用策略：{tool_usage_policy}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "system",
            "content": (
                f"当前项目: id={project.id}, name={project.name}, description={project.description or '-'}"
            ),
        },
        *_normalize_chat_history(history, limit=history_limit),
    ]
    normalized_images = _normalize_image_inputs(images)
    if normalized_images:
        content = [{"type": "text", "text": user_message or "请基于图片给建议。"}]
        for img in normalized_images:
            content.append({"type": "image_url", "image_url": {"url": img}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})
    return messages


def _build_global_chat_messages(
    user_message: str,
    history: list[dict] | None,
    images: list[str] | None = None,
    *,
    custom_system_prompt: str | None = None,
    history_limit: int = 20,
    answer_style: str = "concise",
    prefer_conclusion_first: bool = True,
    skill_resource_directory: str = "",
) -> list[dict[str, Any]]:
    base_prompt = (custom_system_prompt or "").strip()
    if not base_prompt:
        base_prompt = "你是通用 AI 助手。"
        base_prompt += "\n当前没有选中项目，请基于通用知识直接回答。"
        base_prompt += "\n如果用户问题依赖项目、代码库、员工、MCP 或规则配置，请明确提示需要先选择项目后再继续。"

    style_hint = {
        "concise": "输出风格：简洁，避免冗长。",
        "balanced": "输出风格：平衡，先结论后关键步骤。",
        "detailed": "输出风格：详细，覆盖关键前提、步骤与风险。",
    }.get(str(answer_style or "concise").strip().lower(), "输出风格：简洁，避免冗长。")
    order_hint = "回答顺序：先给结论再给步骤。" if prefer_conclusion_first else "回答顺序：按自然推理顺序给出。"
    skill_resource_prompt = _build_skill_resource_prompt_block(
        skill_resource_directory,
    )
    system_prompt = (
        f"{base_prompt}\n\n当前模式：通用对话（未选择项目）。\n{order_hint}\n{style_hint}"
        f"{skill_resource_prompt}"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *_normalize_chat_history(history, limit=history_limit),
    ]
    normalized_images = _normalize_image_inputs(images)
    if normalized_images:
        content = [{"type": "text", "text": user_message or "请基于图片给建议。"}]
        for img in normalized_images:
            content.append({"type": "image_url", "image_url": {"url": img}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})
    return messages


def _resolve_default_chat_system_prompt(custom_system_prompt: Any = None) -> str | None:
    custom_prompt = str(custom_system_prompt or "").strip()
    if custom_prompt:
        return custom_prompt
    cfg = system_config_store.get_global()
    default_prompt = str(getattr(cfg, "default_chat_system_prompt", "") or "").strip()
    return default_prompt or None


def _resolve_chat_max_tokens(request_max_tokens: int | None) -> int:
    cfg = system_config_store.get_global()
    configured = int(getattr(cfg, "chat_max_tokens", 512) or 512)
    configured = max(128, min(configured, 8192))
    if request_max_tokens is None:
        return configured
    try:
        request_value = int(request_max_tokens)
    except (TypeError, ValueError):
        return configured
    if request_value <= 0:
        return configured
    return max(128, min(request_value, 8192))


def _normalize_project_username(value: Any) -> str:
    username = str(value or "").strip()
    if not username:
        raise HTTPException(400, "username is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}", username):
        raise HTTPException(400, "Invalid username format")
    return username


def _current_username(auth_payload: dict) -> str:
    username = str(auth_payload.get("sub") or "").strip()
    return username or "unknown"


def _current_role_id(auth_payload: dict) -> str:
    return str(auth_payload.get("role") or "").strip().lower()


def _is_admin_like(auth_payload: dict) -> bool:
    role_id = _current_role_id(auth_payload)
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", [])
    resolved = resolve_role_permissions(permissions, role_id)
    return "*" in set(resolved)


def _normalize_text_list(value: Any, *, limit: int = 80) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        item = str(raw_item or "").strip()[:limit]
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _connector_llm_shared_with_usernames(item: Any) -> list[str]:
    return _normalize_text_list(getattr(item, "llm_shared_with_usernames", []), limit=64)


def _connector_llm_shared_with_roles(item: Any) -> list[str]:
    return [item.lower() for item in _normalize_text_list(getattr(item, "llm_shared_with_roles", []), limit=64)]


def _connector_llm_accessible(item: Any, auth_payload: dict) -> bool:
    if _is_admin_like(auth_payload):
        return True
    username = _current_username(auth_payload)
    if str(getattr(item, "owner_username", "") or "").strip() == username:
        return True
    if username in _connector_llm_shared_with_usernames(item):
        return True
    return _current_role_id(auth_payload) in _connector_llm_shared_with_roles(item)


def _connector_workspace_accessible(item: Any, auth_payload: dict) -> bool:
    if _is_admin_like(auth_payload):
        return True
    return str(getattr(item, "owner_username", "") or "").strip() == _current_username(auth_payload)


def _list_accessible_local_connectors(auth_payload: dict) -> list[Any]:
    return [
        item
        for item in local_connector_store.list_connectors()
        if _connector_workspace_accessible(item, auth_payload)
    ]


def _resolve_accessible_local_connector(
    connector_id: str,
    auth_payload: dict,
) -> Any | None:
    normalized = str(connector_id or "").strip()
    if not normalized:
        return None
    item = local_connector_store.get_connector(normalized)
    if item is None:
        return None
    return item if _connector_workspace_accessible(item, auth_payload) else None


def _list_accessible_local_connectors_for_llm(auth_payload: dict) -> list[Any]:
    return [
        item
        for item in local_connector_store.list_connectors()
        if _connector_llm_accessible(item, auth_payload)
    ]


def _resolve_accessible_local_connector_for_llm(
    connector_id: str,
    auth_payload: dict,
) -> Any | None:
    normalized = str(connector_id or "").strip()
    if not normalized:
        return None
    item = local_connector_store.get_connector(normalized)
    if item is None:
        return None
    return item if _connector_llm_accessible(item, auth_payload) else None


def _serialize_chat_connector(item: Any) -> dict[str, Any]:
    payload = {
        "id": str(getattr(item, "id", "") or "").strip(),
        "connector_name": str(getattr(item, "connector_name", "") or "").strip(),
        "owner_username": str(getattr(item, "owner_username", "") or "").strip(),
        "platform": str(getattr(item, "platform", "") or "").strip(),
        "app_version": str(getattr(item, "app_version", "") or "").strip(),
        "advertised_url": str(getattr(item, "advertised_url", "") or "").strip(),
        "status": str(getattr(item, "status", "") or "").strip(),
        "last_error": str(getattr(item, "last_error", "") or "").strip(),
        "last_seen_at": str(getattr(item, "last_seen_at", "") or "").strip(),
        "capabilities": getattr(item, "capabilities", {}) if isinstance(getattr(item, "capabilities", {}), dict) else {},
        "health": getattr(item, "health", {}) if isinstance(getattr(item, "health", {}), dict) else {},
        "manifest": getattr(item, "manifest", {}) if isinstance(getattr(item, "manifest", {}), dict) else {},
        "online": False,
    }
    last_seen_raw = payload["last_seen_at"]
    if last_seen_raw:
        try:
            last_seen = datetime.fromisoformat(last_seen_raw.replace("Z", "+00:00"))
            payload["online"] = (datetime.now(timezone.utc) - last_seen).total_seconds() <= 90
        except ValueError:
            payload["online"] = False
    return payload


def _resolve_project_workspace_for_chat(
    project: ProjectConfig,
    settings: dict[str, Any],
) -> str:
    return str(project.workspace_path or "").strip()


def _resolve_local_connector_coding_tools(
    auth_payload: dict,
    settings: dict[str, Any],
    workspace_path: str,
) -> tuple[list[dict[str, Any]], Any | None, str]:
    _ = (auth_payload, settings, workspace_path)
    return [], None, ""


def _get_project_user_member(project_id: str, username: str) -> ProjectUserMember | None:
    normalized_project_id = str(project_id or "").strip()
    normalized_username = str(username or "").strip()
    if not normalized_project_id or not normalized_username:
        return None
    try:
        return project_store.get_user_member(normalized_project_id, normalized_username)
    except Exception:
        return None


def _ensure_project_access(project_id: str, auth_payload: dict) -> ProjectConfig:
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    if _is_admin_like(auth_payload):
        return project
    username = _current_username(auth_payload)
    member = _get_project_user_member(project_id, username)
    if member is None or not bool(getattr(member, "enabled", True)):
        raise HTTPException(403, f"Project access denied: {project_id}")
    return project


def _ensure_project_manage_access(project_id: str, auth_payload: dict) -> ProjectConfig:
    project = _ensure_project_access(project_id, auth_payload)
    if _is_admin_like(auth_payload):
        return project
    username = _current_username(auth_payload)
    member = _get_project_user_member(project_id, username)
    if member is None:
        raise HTTPException(403, f"Project manage access denied: {project_id}")
    member_role = str(getattr(member, "role", "") or "").strip().lower()
    if member_role != "owner":
        raise HTTPException(403, f"Project manage access denied: {project_id}")
    return project


def _serialize_project_user_member(member: ProjectUserMember) -> dict[str, Any]:
    user = user_store.get(member.username)
    return {
        **asdict(member),
        "user_exists": user is not None,
        "user_role": str(getattr(user, "role", "") or ""),
    }


def _append_chat_record(
    *,
    project_id: str,
    username: str,
    role: str,
    content: str,
    message_id: str = "",
    chat_session_id: str = "",
    display_mode: str = "",
    attachments: list[str] | None = None,
    images: list[str] | None = None,
) -> None:
    text = str(content or "").strip()
    if not text:
        return
    try:
        project_chat_store.append_message(
            ProjectChatMessage(
                id=str(message_id or "").strip(),
                project_id=project_id,
                username=username,
                role=role,
                content=text,
                chat_session_id=str(chat_session_id or "").strip(),
                display_mode=str(display_mode or "").strip(),
                attachments=attachments or [],
                images=images or [],
            )
        )
    except Exception:
        pass


@router.post("/chat/global")
async def chat_without_project(
    req: ProjectChatReq,
    auth_payload: dict = Depends(require_auth),
):
    # 预留接口：当前前端默认关闭“未选择项目时的普通对话”入口，
    # 但保留这条通用对话链路，后续如产品重新开放可直接复用。
    from services.llm_provider_service import get_llm_provider_service

    _ensure_permission(auth_payload, "menu.ai.chat")

    user_message = str(req.message or "").strip()
    normalized_images = _normalize_image_inputs(req.images)
    attachment_names = [
        str(name or "").strip()
        for name in (req.attachment_names or [])
        if str(name or "").strip()
    ]
    if not user_message and not normalized_images and not attachment_names:
        raise HTTPException(400, "message is required")

    runtime_settings = _normalize_project_chat_settings(
        {
            "provider_id": req.provider_id,
            "model_name": req.model_name,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "system_prompt": req.system_prompt,
            "history_limit": req.history_limit,
            "answer_style": req.answer_style,
            "prefer_conclusion_first": req.prefer_conclusion_first,
        }
    )
    provider_mode, selected_provider, _ = await _resolve_provider_runtime_target(
        str(runtime_settings.get("provider_id") or ""),
        auth_payload,
    )
    provider_id = str(selected_provider.get("id") or "").strip()
    model_name = str(
        runtime_settings.get("model_name")
        or selected_provider.get("default_model")
        or (selected_provider.get("models") or [""])[0]
    ).strip()
    if not provider_id or not model_name:
        raise HTTPException(400, "未找到可用模型")

    effective_user_message = user_message
    if not effective_user_message and attachment_names:
        effective_user_message = (
            f"我上传了附件：{'、'.join(attachment_names)}。请先给我处理建议。"
        )
    messages = _build_global_chat_messages(
        effective_user_message,
        req.history,
        normalized_images,
        custom_system_prompt=_resolve_default_chat_system_prompt(
            runtime_settings.get("system_prompt")
        ),
        history_limit=int(runtime_settings.get("history_limit") or 20),
        answer_style=str(runtime_settings.get("answer_style") or "concise"),
        prefer_conclusion_first=bool(
            runtime_settings.get("prefer_conclusion_first", True)
        ),
        skill_resource_directory=req.skill_resource_directory,
    )

    llm_service = get_llm_provider_service()
    try:
        if provider_mode == "local_connector":
            connector = _resolve_accessible_local_connector_for_llm(
                parse_local_connector_provider_id(provider_id),
                auth_payload,
            )
            if connector is None:
                raise HTTPException(404, "Local connector not found")
            result = await chat_completion_via_connector(
                connector,
                model_name=model_name,
                messages=messages,
                temperature=float(runtime_settings.get("temperature") or 0.1),
                max_tokens=_resolve_chat_max_tokens(runtime_settings.get("max_tokens")),
                timeout=120,
            )
        else:
            result = await llm_service.chat_completion(
                provider_id=provider_id,
                model_name=model_name,
                messages=messages,
                temperature=float(runtime_settings.get("temperature") or 0.1),
                max_tokens=_resolve_chat_max_tokens(runtime_settings.get("max_tokens")),
                timeout=120,
            )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Global chat failed: {exc}") from exc

    answer = str(result.get("content") or "").strip() or "模型未返回有效内容。"
    return {
        "content": answer,
        "provider_id": provider_id,
        "model_name": model_name,
    }


def _extract_ws_auth_payload(websocket: WebSocket) -> dict | None:
    token = str(websocket.query_params.get("token") or "").strip()
    if token:
        payload = decode_token(token)
        if payload is not None:
            return payload
    auth_header = str(websocket.headers.get("authorization") or "").strip()
    if auth_header.startswith("Bearer "):
        return decode_token(auth_header[7:])
    return None


def _pick_directory_via_native_dialog(
    initial_path: str = "",
    title: str = "选择工作区目录",
) -> str:
    normalized_title = str(title or "选择工作区目录").strip() or "选择工作区目录"
    initial = Path(str(initial_path or "").strip()).expanduser()
    initial_dir = initial if initial.is_dir() else (initial.parent if str(initial_path or "").strip() else None)

    if sys.platform == "darwin":
        osa_args = ["osascript"]
        if initial_dir and initial_dir.exists():
            osa_args.extend(
                [
                    "-e",
                    f'set chosenFolder to choose folder with prompt "{normalized_title.replace(chr(34), chr(92) + chr(34))}" default location POSIX file "{str(initial_dir).replace(chr(34), chr(92) + chr(34))}"',
                ]
            )
        else:
            osa_args.extend(
                [
                    "-e",
                    f'set chosenFolder to choose folder with prompt "{normalized_title.replace(chr(34), chr(92) + chr(34))}"',
                ]
            )
        osa_args.extend(["-e", "POSIX path of chosenFolder"])
        result = subprocess.run(osa_args, capture_output=True, text=True)
        if result.returncode != 0:
            message = str(result.stderr or result.stdout or "").strip()
            if "User canceled" in message or "(-128)" in message:
                return ""
            raise RuntimeError(message or "macOS 原生目录选择失败")
        return str(result.stdout or "").strip().rstrip("/") or ""

    if sys.platform.startswith("win"):
        ps_command = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f'$dialog.Description = "{normalized_title.replace(chr(34), chr(92) + chr(34))}"; '
        )
        if initial_dir and initial_dir.exists():
            ps_command += (
                f'$dialog.SelectedPath = "{str(initial_dir).replace(chr(34), chr(92) + chr(34))}"; '
            )
        ps_command += (
            'if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) '
            '{ [Console]::Write($dialog.SelectedPath) }'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = str(result.stderr or result.stdout or "").strip()
            raise RuntimeError(message or "Windows 原生目录选择失败")
        return str(result.stdout or "").strip()

    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--directory",
                f"--title={normalized_title}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return ""
        if result.returncode != 0:
            raise RuntimeError(str(result.stderr or result.stdout or "").strip() or "zenity 目录选择失败")
        return str(result.stdout or "").strip()

    if shutil.which("kdialog"):
        args = ["kdialog", "--getexistingdirectory"]
        if initial_dir and initial_dir.exists():
            args.append(str(initial_dir))
        args.extend(["--title", normalized_title])
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 1:
            return ""
        if result.returncode != 0:
            raise RuntimeError(str(result.stderr or result.stdout or "").strip() or "kdialog 目录选择失败")
        return str(result.stdout or "").strip()

    raise RuntimeError("当前服务端环境不支持原生目录选择器，或运行在无桌面界面的 headless 模式")


def _pick_file_via_native_dialog(
    initial_path: str = "",
    title: str = "选择文件",
) -> str:
    normalized_title = str(title or "选择文件").strip() or "选择文件"
    initial = Path(str(initial_path or "").strip()).expanduser()
    initial_dir = initial.parent if initial.is_file() else (initial if initial.is_dir() else (initial.parent if str(initial_path or "").strip() else None))

    if sys.platform == "darwin":
        osa_args = ["osascript"]
        if initial_dir and initial_dir.exists():
            osa_args.extend(
                [
                    "-e",
                    f'set chosenFile to choose file with prompt "{normalized_title.replace(chr(34), chr(92) + chr(34))}" default location POSIX file "{str(initial_dir).replace(chr(34), chr(92) + chr(34))}"',
                ]
            )
        else:
            osa_args.extend(
                [
                    "-e",
                    f'set chosenFile to choose file with prompt "{normalized_title.replace(chr(34), chr(92) + chr(34))}"',
                ]
            )
        osa_args.extend(["-e", "POSIX path of chosenFile"])
        result = subprocess.run(osa_args, capture_output=True, text=True)
        if result.returncode != 0:
            message = str(result.stderr or result.stdout or "").strip()
            if "User canceled" in message or "(-128)" in message:
                return ""
            raise RuntimeError(message or "macOS 原生文件选择失败")
        return str(result.stdout or "").strip()

    if sys.platform.startswith("win"):
        ps_command = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
            f'$dialog.Title = "{normalized_title.replace(chr(34), chr(92) + chr(34))}"; '
        )
        if initial_dir and initial_dir.exists():
            ps_command += (
                f'$dialog.InitialDirectory = "{str(initial_dir).replace(chr(34), chr(92) + chr(34))}"; '
            )
        ps_command += (
            'if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) '
            '{ [Console]::Write($dialog.FileName) }'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = str(result.stderr or result.stdout or "").strip()
            raise RuntimeError(message or "Windows 原生文件选择失败")
        return str(result.stdout or "").strip()

    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                f"--title={normalized_title}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return ""
        if result.returncode != 0:
            raise RuntimeError(str(result.stderr or result.stdout or "").strip() or "zenity 文件选择失败")
        return str(result.stdout or "").strip()

    if shutil.which("kdialog"):
        args = ["kdialog", "--getopenfilename"]
        if initial_dir and initial_dir.exists():
            args.append(str(initial_dir))
        args.extend(["--title", normalized_title])
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 1:
            return ""
        if result.returncode != 0:
            raise RuntimeError(str(result.stderr or result.stdout or "").strip() or "kdialog 文件选择失败")
        return str(result.stdout or "").strip()

    raise RuntimeError("当前服务端环境不支持原生文件选择器，或运行在无桌面界面的 headless 模式")


def _chunk_text(content: str, chunk_size: int = 42) -> list[str]:
    text = str(content or "")
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _sse_payload(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _is_project_meta_query(message: str) -> bool:
    # 关闭固定模板直出，统一走模型+工具决策。
    _ = message
    return False


def _is_mcp_modules_query(message: str) -> bool:
    # 关闭固定模板直出，统一走模型+工具决策。
    _ = message
    return False


def _extract_tool_probe_name(message: str) -> str:
    # 关闭固定模板直出，统一走模型+工具决策。
    _ = message
    return ""


def _build_tool_probe_reply(
    project_id: str,
    employee_id: str,
    tool_name: str,
    enabled_project_tool_names: list[str] | None,
    *,
    explicit_filter: bool,
) -> str:
    from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime

    tools = list_project_proxy_tools_runtime(project_id, employee_id)
    tools = _filter_project_tools_by_names(
        tools,
        enabled_project_tool_names,
        explicit_filter=explicit_filter,
    )
    available_names = [
        str(item.get("tool_name") or "").strip()
        for item in tools
        if str(item.get("tool_name") or "").strip()
    ]
    available_set = set(available_names)
    can_use = tool_name in available_set
    status = "可以使用" if can_use else "当前不可用"
    preview = "、".join(available_names[:12]) if available_names else "无"
    return (
        f"`{tool_name}` {status}。\n"
        f"- 本轮可用工具数：{len(available_names)}\n"
        f"- 本轮可用工具：{preview}"
    )


def _build_mcp_modules_reply(project_id: str) -> str:
    payload = _build_chat_mcp_modules(project_id)
    project_related = list(payload.get("system", {}).get("project_related") or [])
    system_global = list(payload.get("system", {}).get("system_global") or [])
    external_modules = list(payload.get("external", {}).get("modules") or [])

    def _names(items: list[dict[str, Any]], limit: int = 12) -> str:
        values: list[str] = []
        for item in items[:limit]:
            name = str(item.get("name") or item.get("tool_name") or item.get("id") or "").strip()
            if name:
                values.append(name)
        return "、".join(values) if values else "无"

    lines = [
        f"当前项目 `{project_id}` 的 MCP 模块清单：",
        f"1. 系统提供-项目关联：{len(project_related)} 个",
        f"   { _names(project_related) }",
        f"2. 系统提供-系统全局：{len(system_global)} 个",
        f"   { _names(system_global) }",
        f"3. 外部模块：{len(external_modules)} 个",
        f"   { _names(external_modules) }",
    ]
    return "\n".join(lines)


def _should_enable_chat_tools(message: str, attachment_names: list[str], images: list[str]) -> bool:
    text = str(message or "").strip()
    if not text and not attachment_names and not images:
        return False
    return True


def _build_project_meta_reply(project: ProjectConfig, selected_employee: dict[str, Any] | None, candidates: list[dict[str, Any]]) -> str:
    lines = [
        f"- 当前绑定项目：`{project.name}`",
        f"- 项目 ID：`{project.id}`",
        f"- 项目描述：`{project.description or '-'}`",
    ]
    if project.workspace_path:
        lines.append(f"- 工作区路径：`{project.workspace_path}`")
    lines.append(f"- 成员数：`{len(candidates)}`")
    if selected_employee:
        lines.append(
            f"- 当前执行员工：`{selected_employee.get('name') or selected_employee.get('id')}` "
            f"(`{selected_employee.get('id')}`)"
        )
    if candidates:
        preview = "、".join(
            f"{item.get('name') or item.get('id')}({item.get('role') or 'member'})" for item in candidates[:5]
        )
        lines.append(f"- 项目成员：{preview}")
    lines.append("（以上为系统绑定的项目元数据，不是目录扫描结果）")
    return "\n".join(lines)


@router.get("")
async def list_projects(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    projects = project_store.list_all()
    if _is_admin_like(auth_payload):
        visible_projects = projects
    else:
        username = _current_username(auth_payload)
        visible_projects = []
        for item in projects:
            member = _get_project_user_member(item.id, username)
            if member is not None and bool(getattr(member, "enabled", True)):
                visible_projects.append(item)
    return {"projects": [_serialize_project(item) for item in visible_projects]}


@router.post("/workspace-directory/pick")
async def pick_workspace_directory(
    req: WorkspaceDirectoryPickReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_any_permission(auth_payload, ["menu.projects", "menu.ai.chat"])
    try:
        selected = await run_in_threadpool(
            _pick_directory_via_native_dialog,
            str(req.initial_path or "").strip(),
            str(req.title or "选择工作区目录").strip() or "选择工作区目录",
        )
    except RuntimeError as exc:
        raise HTTPException(501, str(exc)) from exc
    if not selected:
        return {"path": "", "cancelled": True, "source": "native_dialog"}
    return {"path": selected, "cancelled": False, "source": "native_dialog"}


@router.post("/workspace-file/pick")
async def pick_workspace_file(
    req: WorkspaceFilePickReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_any_permission(auth_payload, ["menu.projects", "menu.ai.chat"])
    try:
        selected = await run_in_threadpool(
            _pick_file_via_native_dialog,
            str(req.initial_path or "").strip(),
            str(req.title or "选择文件").strip() or "选择文件",
        )
    except RuntimeError as exc:
        raise HTTPException(501, str(exc)) from exc
    if not selected:
        return {"path": "", "cancelled": True, "source": "native_dialog"}
    return {"path": selected, "cancelled": False, "source": "native_dialog"}


@router.post("")
async def create_project(req: ProjectCreateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    project = ProjectConfig(
        id=project_store.new_id(),
        name=str(req.name or "").strip(),
        description=req.description,
        workspace_path=_normalize_workspace_path_for_save(req.workspace_path),
        ai_entry_file=_normalize_ai_entry_file_for_save(req.ai_entry_file),
        mcp_enabled=req.mcp_enabled,
        feedback_upgrade_enabled=req.feedback_upgrade_enabled,
    )
    if not project.name:
        raise HTTPException(400, "name is required")
    project_store.save(project)
    creator_username = _normalize_project_username(_current_username(auth_payload))
    project_store.upsert_user_member(
        ProjectUserMember(
            project_id=project.id,
            username=creator_username,
            role="owner",
            enabled=True,
            joined_at=_now_iso(),
        )
    )
    _sync_feedback_project_flag(project.id, project.feedback_upgrade_enabled)
    return {"status": "created", "project": _serialize_project(project)}


@router.get("/{project_id}")
async def get_project(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    project = _ensure_project_access(project_id, auth_payload)
    return {"project": _serialize_project(project)}


@router.post("/{project_id}/smart-query")
async def smart_query_project(project_id: str, request: dict, auth_payload: dict = Depends(require_auth)):
    """AI 智能查询端点：自动决策调用数据库或工具"""
    from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime
    from services.llm_provider_service import get_llm_provider_service
    from starlette.concurrency import run_in_threadpool
    import json

    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)

    user_message = request.get("message", "")
    if not user_message:
        raise HTTPException(400, "message is required")

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
    )
    if not providers:
        raise HTTPException(400, "No LLM provider configured")

    provider = providers[0]
    provider_id = provider.get("id", "")
    model_name = provider.get("default_model", "")

    from services.dynamic_mcp_runtime import invoke_project_tool_runtime, list_project_external_tools_runtime, list_project_proxy_tools_runtime

    tools = list_project_proxy_tools_runtime(project_id, "") + list_project_external_tools_runtime(project_id)
    decision = await ai_decide_action(llm_service, provider_id, model_name, user_message, project_id, tools)

    if not decision or decision.get("action") == "chat":
        return {"status": "no_action", "message": "请使用普通对话"}

    action = decision.get("action")

    if action == "query_db":
        result = await run_in_threadpool(execute_db_query, decision.get("query", ""))
        return {"status": "ok", "action": "query_db", "result": result, "reason": decision.get("reason")}

    if action == "call_tool":
        tool_result = await run_in_threadpool(
            invoke_project_tool_runtime, project_id, decision.get("tool", ""), "", decision.get("args", {}), "{}", 60
        )
        return {"status": "ok", "action": "call_tool", "result": tool_result, "reason": decision.get("reason")}

    if action == "recommend_project":
        recommendation = recommend_better_project(user_message, project_id)
        return {"status": "ok", "action": "recommend_project", "result": recommendation}

    return {"status": "unknown_action"}


def _normalize_workspace_path_for_save(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise HTTPException(400, "workspace_path 必须是绝对路径，例如 /Users/name/project")
    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(400, f"workspace_path 不存在或不是目录：{candidate}")
    return str(candidate.resolve())


def _normalize_ai_entry_file_for_save(value: Any) -> str:
    return str(value or "").strip()[:500]


def _apply_project_update(project_id: str, req: ProjectUpdateReq) -> dict:
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "project": _serialize_project(project)}
    if "name" in updates:
        updates["name"] = str(updates["name"] or "").strip()
        if not updates["name"]:
            raise HTTPException(400, "name cannot be empty")
    if "workspace_path" in updates:
        updates["workspace_path"] = _normalize_workspace_path_for_save(updates.get("workspace_path"))
    if "ai_entry_file" in updates:
        updates["ai_entry_file"] = _normalize_ai_entry_file_for_save(updates.get("ai_entry_file"))
    updates["updated_at"] = _now_iso()
    updated = replace(project, **updates)
    project_store.save(updated)
    if "feedback_upgrade_enabled" in updates:
        _sync_feedback_project_flag(updated.id, bool(updated.feedback_upgrade_enabled))
    return {"status": "updated", "project": _serialize_project(updated)}


@router.put("/{project_id}")
async def update_project(project_id: str, req: ProjectUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    return _apply_project_update(project_id, req)


@router.patch("/{project_id}")
async def patch_project(project_id: str, req: ProjectUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    return _apply_project_update(project_id, req)


@router.delete("/{project_id}")
async def delete_project(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    if not project_store.delete(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    try:
        project_chat_store.clear_project(project_id)
    except Exception:
        pass
    return {"status": "deleted", "project_id": project_id}


@router.get("/{project_id}/users")
async def list_project_users(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    roles = {item.id: item for item in role_store.list_all()}
    project_user_members = project_store.list_user_members(project_id)
    can_manage = _is_admin_like(auth_payload) or str(
        getattr(_get_project_user_member(project_id, _current_username(auth_payload)), "role", "") or ""
    ).strip().lower() == "owner"
    member_map = {
        str(item.username or "").strip(): item
        for item in project_user_members
        if str(item.username or "").strip()
    }
    all_users = []
    if can_manage:
        for user in user_store.list_all():
            member = member_map.get(user.username)
            all_users.append(
                {
                    "username": user.username,
                    "role": user.role,
                    "role_name": getattr(roles.get(user.role), "name", user.role),
                    "assigned": member is not None,
                    "enabled_in_project": bool(getattr(member, "enabled", False)),
                }
            )
    return {
        "members": [_serialize_project_user_member(item) for item in project_user_members],
        "all_users": all_users,
        "can_manage": can_manage,
    }


@router.post("/{project_id}/users")
async def add_project_user(project_id: str, req: ProjectUserAddReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    username = _normalize_project_username(req.username)
    user = user_store.get(username)
    if user is None:
        raise HTTPException(404, f"User {username} not found")
    existing = project_store.get_user_member(project_id, username)
    if existing is not None:
        return {
            "status": "exists",
            "message": f"User {username} already exists in project {project_id}",
            "member": _serialize_project_user_member(existing),
        }
    member = ProjectUserMember(
        project_id=project_id,
        username=username,
        role=str(req.role or "member").strip() or "member",
        enabled=bool(req.enabled),
        joined_at=_now_iso(),
    )
    project_store.upsert_user_member(member)
    return {"status": "created", "member": _serialize_project_user_member(member)}


@router.delete("/{project_id}/users/{username}")
async def remove_project_user(project_id: str, username: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    normalized_username = _normalize_project_username(username)
    member = project_store.get_user_member(project_id, normalized_username)
    if member is None:
        raise HTTPException(404, f"User {normalized_username} is not a member of project {project_id}")
    owner_count = sum(
        1
        for item in project_store.list_user_members(project_id)
        if bool(getattr(item, "enabled", True))
        and str(getattr(item, "role", "") or "").strip().lower() == "owner"
    )
    if str(getattr(member, "role", "") or "").strip().lower() == "owner" and owner_count <= 1:
        raise HTTPException(400, "Cannot remove the last project owner")
    if not project_store.remove_user_member(project_id, normalized_username):
        raise HTTPException(404, f"User {normalized_username} is not a member of project {project_id}")
    return {
        "status": "deleted",
        "project_id": project_id,
        "username": normalized_username,
    }


@router.get("/{project_id}/members")
async def list_project_members(project_id: str, auth_payload: dict = Depends(require_auth)):
    from services.dynamic_mcp_runtime import list_project_member_profiles_runtime

    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)

    profiles = list_project_member_profiles_runtime(
        project_id,
        include_disabled=True,
        include_missing=True,
        rule_limit=30,
    )
    by_employee_id = {
        str(item.get("employee_id") or ""): item
        for item in profiles
        if str(item.get("employee_id") or "")
    }
    members: list[dict[str, Any]] = []
    for member in project_store.list_members(project_id):
        profile = by_employee_id.get(member.employee_id, {})
        members.append(
            {
                **asdict(member),
                "employee_exists": bool(profile.get("employee_exists", False)),
                "employee_name": str(profile.get("employee_name") or ""),
                "employee_mcp_enabled": bool(profile.get("mcp_enabled", False)),
                "skills": list(profile.get("skills") or []),
                "skill_names": list(profile.get("skill_names") or []),
                "rule_bindings": list(profile.get("rule_bindings") or []),
            }
        )
    return {"members": members}


@router.post("/{project_id}/members")
async def add_project_member(project_id: str, req: ProjectMemberAddReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)

    employee_id = str(req.employee_id or "").strip()
    if not employee_id:
        raise HTTPException(400, "employee_id is required")
    employee = employee_store.get(employee_id)
    if employee is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    existing = project_store.get_member(project_id, employee_id)
    if existing is not None:
        return {
            "status": "exists",
            "message": f"Employee {employee_id} already exists in project {project_id}",
            "member": asdict(existing),
        }
    member = ProjectMember(
        project_id=project_id,
        employee_id=employee_id,
        role=str(req.role or "member").strip() or "member",
        enabled=bool(req.enabled),
        joined_at=_now_iso(),
    )
    project_store.upsert_member(member)
    return {"status": "created", "member": asdict(member)}


@router.delete("/{project_id}/members/{employee_id}")
async def remove_project_member(project_id: str, employee_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    if not project_store.remove_member(project_id, employee_id):
        raise HTTPException(404, f"Employee {employee_id} is not a member of project {project_id}")
    cleaned = _cleanup_project_chat_employee_selection(project_id, employee_id)
    return {
        "status": "deleted",
        "project_id": project_id,
        "employee_id": employee_id,
        "cleaned_chat_settings": cleaned,
    }


@router.get("/{project_id}/chat/providers")
async def list_project_chat_providers(
    project_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    from services.dynamic_mcp_runtime import list_project_external_tools_runtime

    project = _ensure_project_access(project_id, auth_payload)
    try:
        selected_provider, providers = _pick_chat_provider("", auth_payload)
    except HTTPException as exc:
        if exc.status_code != 400:
            raise
        selected_provider, providers = {}, []
    default_employee, candidates = _resolve_project_chat_employee(project_id, "")
    mcp_modules = _build_chat_mcp_modules(project_id)
    persisted_chat_settings = _normalize_project_chat_settings(getattr(project, "chat_settings", {}) or {})
    chat_settings = dict(persisted_chat_settings)
    runtime_external_tools = list_project_external_tools_runtime(project_id)
    effective_workspace_path = _resolve_project_workspace_for_chat(project, chat_settings)

    return {
        "project_id": project_id,
        "workspace_path": effective_workspace_path,
        "project_workspace_path": str(project.workspace_path or "").strip(),
        "project_ai_entry_file": str(project.ai_entry_file or "").strip(),
        "chat_modes": [{"id": "system", "label": "系统对话"}],
        "providers": providers,
        "default_provider_id": str(selected_provider.get("id") or ""),
        "default_model_name": str(selected_provider.get("default_model") or ""),
        "employees": candidates,
        "default_employee_id": str((default_employee or {}).get("id") or ""),
        "mcp_modules": mcp_modules,
        "runtime_external_tools": runtime_external_tools,
        "chat_settings": _public_project_chat_settings(persisted_chat_settings),
    }


def _serialize_chat_session(item: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(item, "id", "") or "").strip(),
        "project_id": str(getattr(item, "project_id", "") or "").strip(),
        "username": str(getattr(item, "username", "") or "").strip(),
        "title": str(getattr(item, "title", "新对话") or "新对话"),
        "preview": str(getattr(item, "preview", "") or ""),
        "message_count": int(getattr(item, "message_count", 0) or 0),
        "created_at": str(getattr(item, "created_at", "") or ""),
        "updated_at": str(getattr(item, "updated_at", "") or ""),
        "last_message_at": str(getattr(item, "last_message_at", "") or ""),
    }


@router.get("/{project_id}/chat/settings")
async def get_project_chat_settings(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)
    return {"project_id": project_id, "settings": _public_project_chat_settings(getattr(project, "chat_settings", {}) or {})}


@router.put("/{project_id}/chat/settings")
async def update_project_chat_settings(project_id: str, req: ProjectChatSettingsUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)
    normalized = _public_project_chat_settings(req.settings or {})
    updated = replace(project, chat_settings=normalized, updated_at=_now_iso())
    project_store.save(updated)
    persisted = project_store.get(project_id)
    persisted_settings = _public_project_chat_settings(getattr(persisted, "chat_settings", {}) or {}) if persisted else normalized
    return {"status": "updated", "project_id": project_id, "settings": persisted_settings}


@router.patch("/{project_id}/chat/ai-entry-file")
async def update_project_chat_ai_entry_file(
    project_id: str,
    req: ProjectAiEntryFileUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)
    normalized = _normalize_ai_entry_file_for_save(req.ai_entry_file)
    updated = replace(project, ai_entry_file=normalized, updated_at=_now_iso())
    project_store.save(updated)
    return {
        "status": "updated",
        "project_id": project_id,
        "ai_entry_file": normalized,
    }


@router.get("/{project_id}/chat/history")
async def list_project_chat_history(
    project_id: str,
    limit: int = 200,
    offset: int = 0,
    chat_session_id: str = "",
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    records = project_chat_store.list_messages(
        project_id,
        username,
        limit=limit,
        offset=offset,
        chat_session_id=str(chat_session_id or "").strip(),
    )
    return {"messages": [asdict(item) for item in records]}


@router.delete("/{project_id}/chat/history")
async def clear_project_chat_history(
    project_id: str,
    chat_session_id: str = "",
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    removed = project_chat_store.clear_messages(
        project_id,
        username,
        str(chat_session_id or "").strip(),
    )
    return {"status": "cleared", "removed_count": int(removed)}


@router.post("/{project_id}/chat/history/truncate")
async def truncate_project_chat_history(
    project_id: str,
    req: ProjectChatHistoryTruncateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    message_id = str(req.message_id or "").strip()
    if not message_id:
        raise HTTPException(400, "message_id is required")
    removed = project_chat_store.truncate_messages(
        project_id,
        username,
        message_id,
        str(req.chat_session_id or "").strip(),
    )
    if removed <= 0:
        raise HTTPException(404, "message not found in chat session")
    return {"status": "truncated", "removed_count": int(removed)}


@router.get("/{project_id}/chat/sessions")
async def list_project_chat_sessions(
    project_id: str,
    limit: int = 50,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    records = project_chat_store.list_sessions(project_id, username, limit=limit)
    return {"sessions": [_serialize_chat_session(item) for item in records]}


@router.post("/{project_id}/chat/sessions")
async def create_project_chat_session(
    project_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    item = project_chat_store.create_session(project_id, username, "新对话")
    return {"session": _serialize_chat_session(item)}


@router.websocket("/{project_id}/chat/ws")
async def ws_project_chat(project_id: str, websocket: WebSocket):
    auth_payload = _extract_ws_auth_payload(websocket)
    if auth_payload is None:
        await websocket.close(code=4401, reason="Missing or invalid token")
        return
    try:
        _ensure_permission(auth_payload, "menu.ai.chat")
    except HTTPException:
        await websocket.close(code=4403, reason="Permission denied")
        return

    try:
        project = _ensure_project_access(project_id, auth_payload)
    except HTTPException as exc:
        code = 4404 if exc.status_code == 404 else 4403
        await websocket.close(code=code, reason=str(exc.detail))
        return

    await websocket.accept()
    username = _current_username(auth_payload)
    await websocket.send_json(
        {
            "type": "ready",
            "project_id": project_id,
            "message": "connected",
        }
    )

    active_tasks: dict[str, asyncio.Task] = {}
    cancel_events: dict[str, asyncio.Event] = {}

    async def handle_request(payload: dict):
        nonlocal active_tasks, cancel_events
        request_id = str(payload.get("request_id") or "").strip()
        if str(payload.get("type") or "").strip().lower() == "ping":
            await websocket.send_json({"type": "pong", "request_id": request_id})
            return

        if str(payload.get("type") or "").strip().lower() == "cancel":
            if request_id in cancel_events:
                cancel_events[request_id].set()
            return

        try:
            req = ProjectChatReq.model_validate(payload)
        except Exception as exc:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": f"Invalid payload: {str(exc)}"})
            return

        user_message = str(req.message or "").strip()
        normalized_images = _normalize_image_inputs(req.images)
        attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
        if not user_message and not normalized_images and not attachment_names:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": "message is required"})
            return

        effective_user_message = user_message
        chat_session_id = str(req.chat_session_id or "").strip()
        if not effective_user_message and attachment_names:
            effective_user_message = f"我上传了附件：{', '.join(attachment_names)}。请先给我处理建议。"
        elif not effective_user_message and normalized_images:
            effective_user_message = "请基于我上传的图片给建议。"
        record_content = user_message or ("（发送了图片）" if normalized_images else "（发送了附件）")
        _append_chat_record(
            project_id=project_id, username=username, role="user", content=record_content,
            message_id=str(req.message_id or "").strip(),
            chat_session_id=chat_session_id,
            attachments=attachment_names, images=normalized_images,
        )

        cancel_event = asyncio.Event()
        cancel_events[request_id] = cancel_event

        try:
            runtime_settings = _resolve_chat_runtime_settings(req, project)
            selected_employees, candidates = _resolve_project_chat_employees(
                project_id,
                list(runtime_settings.get("selected_employee_ids") or []),
                str(runtime_settings.get("selected_employee_id") or ""),
            )
            selected_employee = selected_employees[0] if len(selected_employees) == 1 else None
            selected_employee_ids = [str(item.get("id") or "") for item in selected_employees if str(item.get("id") or "")]
            employee_id_val = selected_employee_ids[0] if len(selected_employee_ids) == 1 else ""

            enabled_tool_names = list(runtime_settings.get("enabled_project_tool_names") or [])
            explicit_tool_filter = bool(enabled_tool_names)
            if _is_project_meta_query(effective_user_message):
                direct_answer = _build_project_meta_reply(project, selected_employee, candidates)
                await websocket.send_json(
                    {
                        "type": "start",
                        "request_id": request_id,
                        "project_id": project_id,
                        "provider_id": "",
                        "model_name": "direct-project-meta",
                        "employee_id": employee_id_val,
                        "employee_name": str((selected_employee or {}).get("name") or ""),
                        "tools_enabled": False,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "done",
                        "request_id": request_id,
                        "content": direct_answer,
                        "provider_id": "",
                        "model_name": "direct-project-meta",
                    }
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=direct_answer,
                    chat_session_id=chat_session_id,
                )
                return

            tool_probe_name = _extract_tool_probe_name(effective_user_message)
            if tool_probe_name:
                direct_answer = _build_tool_probe_reply(
                    project_id,
                    employee_id_val,
                    tool_probe_name,
                    enabled_tool_names,
                    explicit_filter=explicit_tool_filter,
                )
                await websocket.send_json(
                    {
                        "type": "start",
                        "request_id": request_id,
                        "project_id": project_id,
                        "provider_id": "",
                        "model_name": "direct-tool-probe",
                        "employee_id": employee_id_val,
                        "employee_name": str((selected_employee or {}).get("name") or ""),
                        "tools_enabled": False,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "done",
                        "request_id": request_id,
                        "content": direct_answer,
                        "provider_id": "",
                        "model_name": "direct-tool-probe",
                    }
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=direct_answer,
                    chat_session_id=chat_session_id,
                )
                return

            if _is_mcp_modules_query(effective_user_message):
                direct_answer = _build_mcp_modules_reply(project_id)
                await websocket.send_json(
                    {
                        "type": "start",
                        "request_id": request_id,
                        "project_id": project_id,
                        "provider_id": "",
                        "model_name": "direct-mcp-modules",
                        "employee_id": employee_id_val,
                        "employee_name": str((selected_employee or {}).get("name") or ""),
                        "tools_enabled": False,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "done",
                        "request_id": request_id,
                        "content": direct_answer,
                        "provider_id": "",
                        "model_name": "direct-mcp-modules",
                    }
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=direct_answer,
                    chat_session_id=chat_session_id,
                )
                return

            provider_mode, selected_provider, _ = await _resolve_provider_runtime_target(
                str(runtime_settings.get("provider_id") or ""),
                auth_payload,
            )
            provider_id = str(selected_provider.get("id") or "")
            model_name = str(runtime_settings.get("model_name") or "").strip() or str(selected_provider.get("default_model") or "")
            if not model_name:
                raise ValueError("model_name is required")
            max_tokens = _resolve_chat_max_tokens(runtime_settings.get("max_tokens"))
            temperature = float(runtime_settings.get("temperature") if runtime_settings.get("temperature") is not None else 0.1)
            temperature = max(0.0, min(temperature, 2.0))
            effective_workspace_path = _resolve_project_workspace_for_chat(project, runtime_settings)

            tools: list[dict] = []
            local_connector_tools: list[dict] = []
            selected_local_connector = None
            local_connector_sandbox_mode = ""
            tools_enabled = bool(runtime_settings.get("auto_use_tools")) and _should_enable_chat_tools(
                effective_user_message, attachment_names, normalized_images
            )
            if tools_enabled:
                tools = _collect_runtime_tools(
                    project_id,
                    selected_employee_ids=selected_employee_ids,
                    enabled_tool_names=enabled_tool_names,
                    explicit_tool_filter=explicit_tool_filter,
                    tool_priority=list(runtime_settings.get("tool_priority") or []),
                    allow_shell_tools=bool(runtime_settings.get("allow_shell_tools", True)),
                    allow_file_write_tools=bool(runtime_settings.get("allow_file_write_tools", True)),
                )
            (
                local_connector_tools,
                selected_local_connector,
                local_connector_sandbox_mode,
            ) = _resolve_local_connector_coding_tools(
                auth_payload,
                runtime_settings,
                effective_workspace_path,
            )
            if local_connector_tools:
                tools.extend(local_connector_tools)
            effective_tools, effective_tool_total = _summarize_effective_tools(tools)
            messages = _build_project_chat_messages(
                project, effective_user_message, req.history, normalized_images,
                selected_employee=selected_employee,
                tools=tools,
                custom_system_prompt=_resolve_default_chat_system_prompt(runtime_settings.get("system_prompt")),
                history_limit=int(runtime_settings.get("history_limit") or 20),
                answer_style=str(runtime_settings.get("answer_style") or "concise"),
                prefer_conclusion_first=bool(runtime_settings.get("prefer_conclusion_first", True)),
                workspace_path=effective_workspace_path,
                skill_resource_directory=req.skill_resource_directory,
            )
            
        except Exception as exc:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
            return

        await websocket.send_json({
            "type": "start", "request_id": request_id, "project_id": project_id,
            "provider_id": provider_id, "model_name": model_name,
            "chat_mode": "system",
            "employee_id": employee_id_val,
            "employee_name": str((selected_employee or {}).get("name") or ""),
            "employee_ids": selected_employee_ids,
            "tools_enabled": bool(tools),
            "effective_tools": effective_tools,
            "effective_tool_total": effective_tool_total,
        })

        try:
            from services.llm_provider_service import get_llm_provider_service

            final_answer = ""
            stream_error = ""
            llm_service = get_llm_provider_service()

            if provider_mode == "local_connector":
                connector = _resolve_accessible_local_connector_for_llm(
                    parse_local_connector_provider_id(provider_id),
                    auth_payload,
                )
                if connector is None:
                    raise ValueError("Local connector not found")
                llm_service = LocalConnectorLlmAdapter(connector)

            # 创建会话和编排器
            redis_client = await get_redis_client()
            conv_manager = ConversationManager(redis_client)
            session_id = await conv_manager.create_session(project_id, employee_id_val)
            orchestrator = AgentOrchestrator(
                llm_service,
                conv_manager,
                max_loops=int(runtime_settings.get("max_loop_rounds") or 20),
                max_tool_rounds=int(runtime_settings.get("max_tool_rounds") or 6),
                repeated_tool_call_threshold=int(runtime_settings.get("repeated_tool_call_threshold") or 2),
                tool_only_threshold=int(runtime_settings.get("tool_only_threshold") or 3),
                tool_budget_strategy=str(runtime_settings.get("tool_budget_strategy") or "finalize"),
                max_tool_calls_per_round=int(runtime_settings.get("max_tool_calls_per_round") or 6),
                tool_timeout_sec=int(runtime_settings.get("tool_timeout_sec") or 60),
                tool_retry_count=int(runtime_settings.get("tool_retry_count") or 0),
            )

            async for chunk_data in orchestrator.run(
                session_id=session_id,
                user_message=effective_user_message,
                tools=tools,
                provider_id=provider_id,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                project_id=project_id,
                employee_id=employee_id_val,
                cancel_event=cancel_event,
                messages=messages,
                local_connector=selected_local_connector,
                local_connector_workspace_path=effective_workspace_path,
                local_connector_sandbox_mode=local_connector_sandbox_mode,
            ):
                chunk_data["request_id"] = request_id
                await websocket.send_json(chunk_data)
                if chunk_data.get("type") == "done":
                    final_answer = chunk_data.get("content", "")
                if chunk_data.get("type") == "error":
                    stream_error = str(chunk_data.get("message") or "未知错误")

            if stream_error:
                _append_chat_record(
                    project_id=project_id, username=username, role="assistant", content=f"对话失败：{stream_error}",
                    chat_session_id=chat_session_id,
                )
            else:
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=final_answer or "模型未返回有效内容。",
                    chat_session_id=chat_session_id,
                )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=f"对话失败：{str(exc)}",
                chat_session_id=chat_session_id,
            )
            await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
        finally:
            cancel_events.pop(request_id, None)
            active_tasks.pop(request_id, None)

    while True:
        try:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                await websocket.send_json({"type": "error", "message": "Invalid payload type"})
                continue
                
            request_id = str(payload.get("request_id") or "").strip()
            payload_type = str(payload.get("type") or "").strip().lower()
            if payload_type == "cancel":
                if request_id in cancel_events:
                    cancel_events[request_id].set()
                continue

            task = asyncio.create_task(handle_request(payload))
            if request_id:
                active_tasks[request_id] = task
                
        except WebSocketDisconnect:
            for ev in cancel_events.values():
                ev.set()
            for t in active_tasks.values():
                t.cancel()
            break
        except Exception:
            await websocket.send_json({"type": "error", "message": "Invalid JSON payload"})
            continue

@router.post("/{project_id}/chat/stream")
async def stream_project_chat(
    project_id: str,
    req: ProjectChatReq,
    auth_payload: dict = Depends(require_auth),
):
    from services.llm_provider_service import get_llm_provider_service

    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)

    user_message = str(req.message or "").strip()
    normalized_images = _normalize_image_inputs(req.images)
    attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
    if not user_message and not normalized_images and not attachment_names:
        raise HTTPException(400, "message is required")

    effective_user_message = user_message
    chat_session_id = str(req.chat_session_id or "").strip()
    if not effective_user_message and attachment_names:
        effective_user_message = f"我上传了附件：{', '.join(attachment_names)}。请先给我处理建议。"
    elif not effective_user_message and normalized_images:
        effective_user_message = "请基于我上传的图片给建议。"
    record_content = user_message or ("（发送了图片）" if normalized_images else "（发送了附件）")
    _append_chat_record(
        project_id=project_id,
        username=username,
        role="user",
        content=record_content,
        message_id=str(req.message_id or "").strip(),
        chat_session_id=chat_session_id,
        attachments=attachment_names,
        images=normalized_images,
    )

    runtime_settings = _resolve_chat_runtime_settings(req, project)
    try:
        selected_employees, candidates = _resolve_project_chat_employees(
            project_id,
            list(runtime_settings.get("selected_employee_ids") or []),
            str(runtime_settings.get("selected_employee_id") or ""),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    selected_employee = selected_employees[0] if len(selected_employees) == 1 else None
    selected_employee_ids = [str(item.get("id") or "") for item in selected_employees if str(item.get("id") or "")]
    employee_id_val = selected_employee_ids[0] if len(selected_employee_ids) == 1 else ""
    enabled_tool_names = list(runtime_settings.get("enabled_project_tool_names") or [])
    explicit_tool_filter = bool(enabled_tool_names)
    if _is_project_meta_query(effective_user_message):
        answer = _build_project_meta_reply(project, selected_employee, candidates)

        async def direct_event_stream() -> AsyncIterator[str]:
            yield _sse_payload(
                "message",
                {
                    "type": "start",
                    "project_id": project_id,
                    "provider_id": "",
                    "model_name": "direct-project-meta",
                    "employee_id": employee_id_val,
                    "employee_name": str((selected_employee or {}).get("name") or ""),
                    "tools_enabled": False,
                },
            )
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload(
                "message",
                {"type": "done", "content": answer, "provider_id": "", "model_name": "direct-project-meta"},
            )
            _append_chat_record(project_id=project_id, username=username, role="assistant", content=answer, chat_session_id=chat_session_id)

        return StreamingResponse(
            direct_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    tool_probe_name = _extract_tool_probe_name(effective_user_message)
    if tool_probe_name:
        answer = _build_tool_probe_reply(
            project_id,
            employee_id_val,
            tool_probe_name,
            enabled_tool_names,
            explicit_filter=explicit_tool_filter,
        )

        async def direct_tool_event_stream() -> AsyncIterator[str]:
            yield _sse_payload(
                "message",
                {
                    "type": "start",
                    "project_id": project_id,
                    "provider_id": "",
                    "model_name": "direct-tool-probe",
                    "employee_id": employee_id_val,
                    "employee_name": str((selected_employee or {}).get("name") or ""),
                    "tools_enabled": False,
                },
            )
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload(
                "message",
                {"type": "done", "content": answer, "provider_id": "", "model_name": "direct-tool-probe"},
            )
            _append_chat_record(project_id=project_id, username=username, role="assistant", content=answer, chat_session_id=chat_session_id)

        return StreamingResponse(
            direct_tool_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if _is_mcp_modules_query(effective_user_message):
        answer = _build_mcp_modules_reply(project_id)

        async def direct_mcp_event_stream() -> AsyncIterator[str]:
            yield _sse_payload(
                "message",
                {
                    "type": "start",
                    "project_id": project_id,
                    "provider_id": "",
                    "model_name": "direct-mcp-modules",
                    "employee_id": employee_id_val,
                    "employee_name": str((selected_employee or {}).get("name") or ""),
                    "tools_enabled": False,
                },
            )
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload(
                "message",
                {"type": "done", "content": answer, "provider_id": "", "model_name": "direct-mcp-modules"},
            )
            _append_chat_record(project_id=project_id, username=username, role="assistant", content=answer, chat_session_id=chat_session_id)

        return StreamingResponse(
            direct_mcp_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    provider_mode, selected_provider, _ = await _resolve_provider_runtime_target(
        str(runtime_settings.get("provider_id") or ""),
        auth_payload,
    )
    provider_id = str(selected_provider.get("id") or "")
    model_name = str(runtime_settings.get("model_name") or "").strip() or str(selected_provider.get("default_model") or "")
    if not model_name:
        raise HTTPException(400, "model_name is required")

    max_tokens = _resolve_chat_max_tokens(runtime_settings.get("max_tokens"))
    temperature = float(runtime_settings.get("temperature") if runtime_settings.get("temperature") is not None else 0.1)
    temperature = max(0.0, min(temperature, 2.0))

    tools: list[dict] = []
    local_connector_tools: list[dict] = []
    selected_local_connector = None
    local_connector_sandbox_mode = ""
    tools_enabled = bool(runtime_settings.get("auto_use_tools")) and _should_enable_chat_tools(
        effective_user_message, attachment_names, normalized_images
    )
    if tools_enabled:
        tools = _collect_runtime_tools(
            project_id,
            selected_employee_ids=selected_employee_ids,
            enabled_tool_names=enabled_tool_names,
            explicit_tool_filter=explicit_tool_filter,
            tool_priority=list(runtime_settings.get("tool_priority") or []),
            allow_shell_tools=bool(runtime_settings.get("allow_shell_tools", True)),
            allow_file_write_tools=bool(runtime_settings.get("allow_file_write_tools", True)),
        )

    effective_workspace_path = _resolve_project_workspace_for_chat(project, runtime_settings)
    (
        local_connector_tools,
        selected_local_connector,
        local_connector_sandbox_mode,
    ) = _resolve_local_connector_coding_tools(
        auth_payload,
        runtime_settings,
        effective_workspace_path,
    )
    if local_connector_tools:
        tools.extend(local_connector_tools)
    effective_tools, effective_tool_total = _summarize_effective_tools(tools)

    llm_service = get_llm_provider_service()
    messages = _build_project_chat_messages(
        project,
        effective_user_message,
        req.history,
        normalized_images,
        selected_employee=selected_employee,
        tools=tools,
        custom_system_prompt=_resolve_default_chat_system_prompt(runtime_settings.get("system_prompt")),
        history_limit=int(runtime_settings.get("history_limit") or 20),
        answer_style=str(runtime_settings.get("answer_style") or "concise"),
        prefer_conclusion_first=bool(runtime_settings.get("prefer_conclusion_first", True)),
        workspace_path=effective_workspace_path,
        skill_resource_directory=req.skill_resource_directory,
    )

    async def event_stream() -> AsyncIterator[str]:
        yield _sse_payload(
            "message",
            {
                "type": "start",
                "project_id": project_id,
                "provider_id": provider_id,
                "model_name": model_name,
                "employee_id": str((selected_employee or {}).get("id") or ""),
                "employee_name": str((selected_employee or {}).get("name") or ""),
                "employee_ids": selected_employee_ids,
                "tools_enabled": bool(tools),
                "effective_tools": effective_tools,
                "effective_tool_total": effective_tool_total,
            },
        )
        try:
            if provider_mode == "local_connector":
                connector = _resolve_accessible_local_connector_for_llm(
                    parse_local_connector_provider_id(provider_id),
                    auth_payload,
                )
                if connector is None:
                    raise HTTPException(404, "Local connector not found")
                llm_service_runtime = LocalConnectorLlmAdapter(connector)
            else:
                llm_service_runtime = llm_service

            redis_client = await get_redis_client()
            conv_manager = ConversationManager(redis_client)
            session_id = await conv_manager.create_session(project_id, employee_id_val)
            orchestrator = AgentOrchestrator(
                llm_service_runtime,
                conv_manager,
                max_loops=int(runtime_settings.get("max_loop_rounds") or 20),
                max_tool_rounds=int(runtime_settings.get("max_tool_rounds") or 6),
                repeated_tool_call_threshold=int(runtime_settings.get("repeated_tool_call_threshold") or 2),
                tool_only_threshold=int(runtime_settings.get("tool_only_threshold") or 3),
                tool_budget_strategy=str(runtime_settings.get("tool_budget_strategy") or "finalize"),
                max_tool_calls_per_round=int(runtime_settings.get("max_tool_calls_per_round") or 6),
                tool_timeout_sec=int(runtime_settings.get("tool_timeout_sec") or 60),
                tool_retry_count=int(runtime_settings.get("tool_retry_count") or 0),
            )

            final_answer = ""
            stream_error = ""
            cancel_event = asyncio.Event()
            async for chunk_data in orchestrator.run(
                session_id=session_id,
                user_message=effective_user_message,
                tools=tools,
                provider_id=provider_id,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                project_id=project_id,
                employee_id=employee_id_val,
                cancel_event=cancel_event,
                messages=messages,
                local_connector=selected_local_connector,
                local_connector_workspace_path=effective_workspace_path,
                local_connector_sandbox_mode=local_connector_sandbox_mode,
            ):
                yield _sse_payload("message", chunk_data)
                if chunk_data.get("type") == "done":
                    final_answer = str(chunk_data.get("content") or "")
                if chunk_data.get("type") == "error":
                    stream_error = str(chunk_data.get("message") or "未知错误")

            if stream_error:
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=f"对话失败：{stream_error}",
                    chat_session_id=chat_session_id,
                )
            else:
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=final_answer or "模型未返回有效内容。",
                    chat_session_id=chat_session_id,
                )
        except Exception as exc:
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=f"对话失败：{str(exc)}",
                chat_session_id=chat_session_id,
            )
            yield _sse_payload("message", {"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _build_project_manual_template_payload(project_id: str) -> dict[str, Any]:
    """获取项目手册提示词模板（供用户复制到其他 AI 使用）"""
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    member_items = _project_member_details(project_id)
    member_lines = []
    all_domains: set[str] = set()
    unique_skills: dict[str, dict] = {}
    for item in member_items:
        employee = item["employee"]
        member = item["member"]
        rule_bindings = list(item["rule_bindings"] or [])
        domains = _collect_rule_domains(rule_bindings)
        skills = item["skills"]
        for domain in domains:
            all_domains.add(str(domain))
        for skill in skills:
            unique_skills[str(skill["id"])] = skill
        member_lines.append(
            f"- {employee.name} ({employee.id}) role={member.role} "
            f"skills={len(skills)} domains={len(domains)}"
        )

    members_text = "\n".join(member_lines) if member_lines else "无"
    skills_text = (
        "\n".join(f"- {s['name']}:{s.get('description', '')}" for s in unique_skills.values())
        if unique_skills
        else "无"
    )
    domains_text = "\n".join(f"- {d}" for d in sorted(all_domains)) if all_domains else "无"
    employee_template_lines: list[str] = []
    for item in member_items:
        employee = item["employee"]
        member = item["member"]
        skills = item["skills"]
        domains = _collect_rule_domains(list(item["rule_bindings"] or []))
        style_hints = list(getattr(employee, "style_hints", []) or [])
        employee_skills_text = (
            "\n".join(f"  - {s['name']}:{s.get('description', '')}" for s in skills)
            if skills
            else "  - 无"
        )
        employee_domains_text = (
            "\n".join(f"  - {d}" for d in domains)
            if domains
            else "  - 无"
        )
        style_text = (
            "\n".join(f"  - {text}" for text in style_hints)
            if style_hints
            else "  - 无"
        )
        workflow_text = (
            "\n".join(f"  - {text}" for text in (getattr(employee, "default_workflow", []) or []))
            if (getattr(employee, "default_workflow", []) or [])
            else "  - 无"
        )
        employee_template_lines.append(
            f"""### {employee.name}（{employee.id}）
- 角色:{member.role}
- 核心目标:{getattr(employee, "goal", "-") or "-"}
- 语调:{getattr(employee, "tone", "-")} / 风格:{getattr(employee, "verbosity", "-")} / 语言:{getattr(employee, "language", "-")}
- 记忆:scope={getattr(employee, "memory_scope", "-")}，保留{getattr(employee, "memory_retention_days", "-")}天

技能:
{employee_skills_text}

规则领域:
{employee_domains_text}

风格提示:
{style_text}

默认工作流:
{workflow_text}

工具使用策略:
  - {str(getattr(employee, "tool_usage_policy", "") or "").strip() or "无"}
"""
        )
    employee_templates_text = "\n".join(employee_template_lines) if employee_template_lines else "无成员"

    template = f"""请根据以下信息，为"{project.name}"AI 项目模块生成一份完整的使用手册。

## 项目基本信息

- **项目 ID**：`{project.id}`
- **项目名称**：{project.name}
- **项目定位**：{project.description or "AI 开发团队"}
- **反馈升级**：{"已启用" if project.feedback_upgrade_enabled else "未启用"}

## 项目成员

{employee_templates_text}

---

## 手册生成要求

**重要：自动记忆规则**

在生成的使用手册中，必须在开头添加以下强制规则：

> **每次对话流程（强制执行）：**
> 1. 收到用户提问后，先检索相关记忆（`recall_project_memory`）
> 2. 解决问题过程中的关键信息会自动保存到记忆系统
> 3. 问题解决后，系统会自动记录本次对话的要点
> 
> **记忆自动保存的内容包括：**
> - 用户提出的问题
> - 使用的解决方案
> - 调用的工具和参数
> - 遇到的问题和解决方法
> - 重要的技术决策
> 
> **注意：**
> - 记忆系统会自动工作，无需手动调用保存
> - 如果遇到重要问题或发现 Bug，可手动提交反馈工单（`submit_project_feedback_bug`）用于规则进化

请按以下结构生成完整的使用手册：

### 第一部分：项目总览

#### 1. 项目简介
- **定位**：{project.name}是什么项目？解决什么问题？
- **适用场景**：什么时候应该使用这个项目？
- **能力边界**：项目能做什么，不能做什么？

#### 2. 核心工具说明

逐个说明以下工具的用途、参数、返回值和使用场景：

- **`list_project_members`**：列出项目所有成员
- **`get_project_profile`**：获取项目配置信息
- **`get_project_runtime_context`**：获取项目运行时上下文
- **`recall_project_memory`**：检索项目记忆
- **`query_project_rules`**：查询项目规则
- **`list_project_proxy_tools`**：列出项目可用技能工具
- **`invoke_project_skill_tool`**：调用项目技能
- **`submit_project_feedback_bug`**：提交反馈问题

---

### 第二部分：项目成员能力清单

为每个成员详细说明：
- 职责定位
- 核心技能
- 规则领域
- 风格特点（如有）

---

### 第三部分：推荐工作流

#### 标准开发流程

```
1. 获取项目上下文 → get_project_runtime_context
2. 记忆检索 → recall_project_memory
3. 规则检索 → query_project_rules
4. 技能调用 → invoke_project_skill_tool
5. 反馈闭环 → submit_project_feedback_bug
```

#### 典型场景示例

**场景 1：新增数据库表**
1. 获取上下文
2. 检索记忆（"数据库表设计"）
3. 检索规则（"数据库设计"）
4. 查看现有表结构（db-query）
5. 提交反馈

**场景 2：开发新的 Vue 组件**
1. 获取上下文
2. 检索记忆（"Element Plus 表格组件"）
3. 检索规则（"UI 设计"）
4. 查询数据结构（db-query）
5. 提交反馈

**场景 3：跨端协作（前后端联调）**
1. 获取项目成员
2. 检索后端记忆（"API 接口设计"）
3. 检索前端记忆（"API 调用"）
4. 查看数据库结构（db-query）
5. 提交联调反馈

---

### 第四部分：常见问题与故障排查

#### Q1：数据库查询失败
- 首次使用需提供数据库配置
- 检查连接信息是否正确
- 仅支持 SELECT 语句
- 单次查询最多返回 1000 行

#### Q2：记忆检索无结果
- 尝试更换关键词
- 检查 `project_name` 参数（必须是"{project.name}"）
- 确认记忆保留期（90 天）内是否有记录
- 尝试不指定 `employee_id` 进行全局检索

#### Q3：规则查询返回多条结果
- 优先使用最近更新的规则
- 根据 `domain` 字段筛选
- 可以同时参考多条规则

#### Q4：技能调用参数错误
- 查看错误信息中的参数提示
- 确认 `employee_id` 是否正确
- 确认技能名称是否正确
- 确认 `args` 参数格式正确（JSON 对象）

#### Q5：反馈提交失败
- 检查必填参数是否完整
- 确认项目反馈升级功能已启用
- 检查 `employee_id` 是否属于该项目成员

---

### 第五部分：最佳实践

#### 1. 参数规范
- 调用记忆时，必须传 `project_name="{project.name}"`
- 调用技能时，必须传 `employee_id`
- 提交反馈时，必须传 `employee_id`、`title`、`symptom`、`expected`

#### 2. 员工选择
- 根据任务类型选择合适的员工
- 跨端任务：分别调用相关员工的能力

#### 3. 记忆管理
- 定期检索记忆，避免重复踩坑
- 及时提交反馈，积累项目经验
- 使用精确的关键词提高检索准确率

#### 4. 规则遵循
- 开发前先检索相关规则
- 遵循规则中的最佳实践
- 发现规则不适用时及时反馈

#### 5. 技能使用
- 首次使用技能时注意配置要求
- 数据库查询注意安全限制
- 技能调用失败时查看详细错误信息

---

## 生成要求

1. **语言**：全部使用中文
2. **格式**：标准 Markdown
3. **完整性**：必须包含以上所有章节
4. **实用性**：提供具体的使用场景和示例
5. **清晰度**：每个工具的用途、参数、返回值都要说明清楚

请开始生成完整的使用手册。"""

    return {
        "status": "success",
        "template": template,
        "project_id": project.id,
        "project_name": project.name,
        "members_summary": members_text,
        "skills_summary": skills_text,
        "rule_domains_summary": domains_text,
    }


@router.post("/{project_id}/generate-manual")
async def generate_project_manual(project_id: str, auth_payload: dict = Depends(require_auth)):
    """生成项目使用手册（面向接入方 AI 平台）"""
    from services.llm_provider_service import get_llm_provider_service

    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    _assert_project_manual_generation_enabled()

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
    )
    if not providers:
        raise HTTPException(400, "未配置 LLM 提供商")
    default_provider = next((p for p in providers if p.get("is_default")), providers[0])

    template_payload = _build_project_manual_template_payload(project_id)
    template = str(template_payload.get("template") or "").strip()
    if not template:
        raise HTTPException(500, "项目手册模板为空，无法生成使用手册")

    project_name = str(template_payload.get("project_name") or "")
    system_prompt = (
        "你是技术文档撰写专家。请严格根据用户提供的手册模板要求生成最终使用手册，"
        "输出标准 Markdown，不要解释过程。"
    )

    try:
        result = await llm_service.chat_completion(
            provider_id=default_provider["id"],
            model_name=default_provider.get("default_model") or "gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": template},
            ],
            temperature=0.2,
            max_tokens=2800,
            timeout=60,
        )
        manual = str(result.get("content") or "").strip()
        return {
            "status": "success",
            "manual": manual,
            "template": template,
            "provider": default_provider["name"],
            "model": default_provider.get("default_model") or "gpt-4",
            "project_id": project_id,
            "project_name": project_name,
        }
    except Exception as exc:
        raise HTTPException(500, f"生成项目使用手册失败: {str(exc)}") from exc


@router.get("/{project_id}/manual-template")
async def get_project_manual_template(project_id: str, auth_payload: dict = Depends(require_auth)):
    """获取项目手册提示词模板（供用户复制到其他 AI 使用）"""
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    return _build_project_manual_template_payload(project_id)
