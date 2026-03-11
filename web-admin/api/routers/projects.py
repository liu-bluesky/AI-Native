"""项目管理路由"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from dataclasses import asdict, replace
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import asyncio
from services.agent_orchestrator import AgentOrchestrator
from services.conversation_manager import ConversationManager
from core.redis_client import get_redis_client
from core.config import get_settings

# from ai_decision import ai_decide_action, execute_db_query, recommend_better_project  # 已废弃
from core.auth import decode_token
from core.deps import employee_store, external_mcp_store, project_chat_store, project_store, require_auth, role_store, system_config_store, usage_store
from services.feedback_service import get_feedback_service
from services.external_agent_service import ExternalAgentSession, create_external_agent_session, detect_external_agent_risk_signals, has_meaningful_workspace_changes, list_external_agent_statuses, materialize_external_agent_workspace_context_async, normalize_external_agent_type, prepare_external_agent_workspace_context, probe_workspace_access, probe_workspace_access_effective_async, resolve_external_agent_status
from models.requests import (
    ProjectChatReq,
    ProjectChatSettingsUpdateReq,
    ProjectCreateReq,
    ProjectMemberAddReq,
    ProjectUpdateReq,
)
from stores.json.project_chat_store import ProjectChatMessage
from stores.json.project_store import ProjectConfig, ProjectMember, _now_iso
from core.role_permissions import has_permission
from stores.mcp_bridge import rule_store, skill_store

router = APIRouter(prefix="/api/projects", dependencies=[Depends(require_auth)])


_PROJECT_CHAT_SETTINGS_DEFAULTS: dict[str, Any] = {
    "chat_mode": "system",
    "external_agent_type": "codex_cli",
    "external_agent_sandbox_mode": "workspace-write",
    "external_agent_sandbox_mode_explicit": False,
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
    chat_mode = str(source.get("chat_mode", settings["chat_mode"]) or "").strip().lower()
    settings["chat_mode"] = chat_mode if chat_mode in {"system", "external_agent"} else settings["chat_mode"]
    agent_type = str(source.get("external_agent_type", settings["external_agent_type"]) or "").strip().lower()
    settings["external_agent_type"] = normalize_external_agent_type(agent_type)
    sandbox_mode_explicit = _coerce_bool(source.get("external_agent_sandbox_mode_explicit"), settings["external_agent_sandbox_mode_explicit"])
    sandbox_mode = str(source.get("external_agent_sandbox_mode", settings["external_agent_sandbox_mode"]) or "").strip().lower()
    normalized_sandbox_mode = sandbox_mode if sandbox_mode in {"read-only", "workspace-write"} else settings["external_agent_sandbox_mode"]
    if normalized_sandbox_mode == "read-only" and not sandbox_mode_explicit:
        normalized_sandbox_mode = settings["external_agent_sandbox_mode"]
    settings["external_agent_sandbox_mode"] = normalized_sandbox_mode
    settings["external_agent_sandbox_mode_explicit"] = sandbox_mode_explicit
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
    permissions = getattr(role, "permissions", [])
    if not has_permission(permissions, permission_key):
        raise HTTPException(403, f"Permission denied: {permission_key}")


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
        if matched is None:
            raise ValueError(f"employee_id is not an enabled member of project {project_id}: {expected}")
        return matched, candidates
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
        if item is None:
            missing.append(employee_id)
            continue
        selected.append(item)
    if missing:
        raise ValueError(f"employee_id is not an enabled member of project {project_id}: {', '.join(missing)}")
    return selected, candidates


def _pick_chat_provider(provider_id: str) -> tuple[dict, list[dict]]:
    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)
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
        return [] if explicit_filter else tools
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


def _resolve_chat_runtime_settings(req: ProjectChatReq, project: ProjectConfig) -> dict[str, Any]:
    base = _normalize_project_chat_settings(getattr(project, "chat_settings", {}) or {})
    merged = dict(base)
    override = {
        "chat_mode": req.chat_mode,
        "external_agent_type": req.external_agent_type,
        "external_agent_sandbox_mode": req.external_agent_sandbox_mode,
        "external_agent_sandbox_mode_explicit": req.external_agent_sandbox_mode_explicit,
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
) -> list[dict[str, Any]]:
    workspace_info = ""
    if project.workspace_path:
        workspace_info = f"\n\n当前项目工作区路径: {project.workspace_path}\n请在此目录下进行代码开发和文件操作。"

    tool_names = [t.get("tool_name", "") for t in (tools or [])] if tools else []
    tool_list_text = f"可用工具({len(tool_names)}个): {', '.join(tool_names)}" if tool_names else "当前无可用工具"

    base_prompt = (custom_system_prompt or "").strip()
    if not base_prompt:
        base_prompt = "你是项目开发助手。"
        base_prompt += "\n可按需调用工具检索最新项目上下文并完成用户请求。"
        base_prompt += "\n当用户询问项目信息、员工信息、规则、MCP 服务时，优先调用 search_project_context 再回答。"

    style_hint = {
        "concise": "输出风格：简洁，避免冗长。",
        "balanced": "输出风格：平衡，先结论后关键步骤。",
        "detailed": "输出风格：详细，覆盖关键前提、步骤与风险。",
    }.get(str(answer_style or "concise").strip().lower(), "输出风格：简洁，避免冗长。")
    order_hint = "回答顺序：先给结论再给步骤。" if prefer_conclusion_first else "回答顺序：按自然推理顺序给出。"
    system_prompt = f"{base_prompt}\n{workspace_info}\n\n{tool_list_text}\n{order_hint}\n{style_hint}"
    if selected_employee:
        rule_bindings = list(selected_employee.get("rule_bindings") or [])
        rule_titles = [str(item.get("title") or item.get("id") or "").strip() for item in rule_bindings]
        rule_titles = [item for item in rule_titles if item]
        rule_domains = _collect_rule_domains(rule_bindings)
        system_prompt += (
            f"\n当前执行员工：{selected_employee.get('name') or selected_employee.get('id')} "
            f"({selected_employee.get('id')})，"
            f"skills={', '.join(selected_employee.get('skill_names') or []) or '-'}，"
            f"rule_titles={', '.join(rule_titles) or '-'}，"
            f"rule_domains={', '.join(rule_domains) or '-'}。"
        )
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


def _current_username(auth_payload: dict) -> str:
    username = str(auth_payload.get("sub") or "").strip()
    return username or "unknown"


def _append_chat_record(
    *,
    project_id: str,
    username: str,
    role: str,
    content: str,
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
                project_id=project_id,
                username=username,
                role=role,
                content=text,
                display_mode=str(display_mode or "").strip(),
                attachments=attachments or [],
                images=images or [],
            )
        )
    except Exception:
        pass


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


def _build_external_agent_startup_context(
    project: ProjectConfig,
    *,
    agent_label: str,
    candidates: list[dict[str, Any]],
    selected_employees: list[dict[str, Any]],
    system_prompt: str,
    sandbox_mode: str,
) -> str:
    selected_names = [str(item.get("name") or item.get("id") or "").strip() for item in selected_employees]
    candidate_preview = [
        f"{str(item.get('name') or item.get('id') or '').strip()}({str(item.get('role') or 'member').strip() or 'member'})"
        for item in candidates[:8]
        if str(item.get("id") or "").strip()
    ]
    lines = [
        "你正在 AI 设计规范平台托管的外部 Agent 会话中运行。",
        f"当前 Agent：{agent_label or '外部 Agent'}。",
        f"当前项目：{project.name} ({project.id})。",
        f"工作目录：{project.workspace_path or '-'}。",
        f"沙箱模式：{sandbox_mode}。",
        "请优先使用中文输出，保持结论清晰、行动明确。",
        "当前阶段不接入平台审批流，也未桥接平台技能 MCP；请仅基于本地工作区与当前外部 Agent CLI 自身能力完成任务。",
        "如需修改文件或执行命令，请严格限制在当前工作区范围内。",
    ]
    if project.description:
        lines.append(f"项目说明：{project.description}")
    if selected_names:
        lines.append(f"当前选定成员：{', '.join(selected_names)}")
    elif candidate_preview:
        lines.append(f"项目成员参考：{', '.join(candidate_preview)}")
    if system_prompt:
        lines.append(f"补充上下文：{system_prompt}")
    return "\n".join(lines)


def _normalize_mcp_server_name(project_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", str(project_id or "").strip())
    normalized = normalized.strip("_") or "project"
    return f"project_{normalized}"


def _find_external_agent_bridge_key(project_id: str) -> str:
    expected_name = f"external-agent-{project_id}"
    try:
        keys = usage_store.list_keys()
    except Exception:
        return ""
    for item in keys:
        if not bool(item.get("is_active", True)):
            continue
        if str(item.get("developer_name") or "").strip() != expected_name:
            continue
        return str(item.get("key") or "").strip()
    return ""


def _build_external_agent_mcp_bridge(project: ProjectConfig, *, create_if_missing: bool = False) -> dict[str, Any]:
    if not bool(getattr(project, "mcp_enabled", True)):
        return {
            "enabled": False,
            "reason": "项目未启用 MCP",
            "server_name": _normalize_mcp_server_name(project.id),
            "config_overrides": [],
        }

    key = _find_external_agent_bridge_key(project.id)
    if not key and create_if_missing:
        try:
            created = usage_store.create_key(
                developer_name=f"external-agent-{project.id}",
                created_by="system-external-agent",
            )
            key = str(created.get("key") or "").strip()
        except Exception:
            key = ""

    server_name = _normalize_mcp_server_name(project.id)
    if not key:
        return {
            "enabled": False,
            "reason": "缺少可用 API Key，启动外部 Agent 时会自动补齐",
            "server_name": server_name,
            "config_overrides": [],
        }

    settings = get_settings()
    url = f"http://127.0.0.1:{int(settings.api_port)}/mcp/projects/{project.id}/sse?key={key}"
    override = f'mcp_servers.{server_name}={{type="sse",url={json.dumps(url, ensure_ascii=False)}}}'
    return {
        "enabled": True,
        "reason": "",
        "server_name": server_name,
        "url": url,
        "config_overrides": [override],
    }


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
async def list_projects():
    projects = project_store.list_all()
    return {"projects": [_serialize_project(item) for item in projects]}


@router.post("")
async def create_project(req: ProjectCreateReq):
    project = ProjectConfig(
        id=project_store.new_id(),
        name=str(req.name or "").strip(),
        description=req.description,
        workspace_path=_normalize_workspace_path_for_save(req.workspace_path),
        mcp_enabled=req.mcp_enabled,
        feedback_upgrade_enabled=req.feedback_upgrade_enabled,
    )
    if not project.name:
        raise HTTPException(400, "name is required")
    project_store.save(project)
    _sync_feedback_project_flag(project.id, project.feedback_upgrade_enabled)
    return {"status": "created", "project": _serialize_project(project)}


@router.get("/{project_id}")
async def get_project(project_id: str):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    return {"project": _serialize_project(project)}


@router.post("/{project_id}/smart-query")
async def smart_query_project(project_id: str, request: dict):
    """AI 智能查询端点：自动决策调用数据库或工具"""
    from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime
    from services.llm_provider_service import get_llm_provider_service
    from starlette.concurrency import run_in_threadpool
    import json

    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    user_message = request.get("message", "")
    if not user_message:
        raise HTTPException(400, "message is required")

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)
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
    updates["updated_at"] = _now_iso()
    updated = replace(project, **updates)
    project_store.save(updated)
    if "feedback_upgrade_enabled" in updates:
        _sync_feedback_project_flag(updated.id, bool(updated.feedback_upgrade_enabled))
    return {"status": "updated", "project": _serialize_project(updated)}


@router.put("/{project_id}")
async def update_project(project_id: str, req: ProjectUpdateReq):
    return _apply_project_update(project_id, req)


@router.patch("/{project_id}")
async def patch_project(project_id: str, req: ProjectUpdateReq):
    return _apply_project_update(project_id, req)


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    if not project_store.delete(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    try:
        project_chat_store.clear_project(project_id)
    except Exception:
        pass
    return {"status": "deleted", "project_id": project_id}


@router.get("/{project_id}/members")
async def list_project_members(project_id: str):
    from services.dynamic_mcp_runtime import list_project_member_profiles_runtime

    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

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
async def add_project_member(project_id: str, req: ProjectMemberAddReq):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

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
async def remove_project_member(project_id: str, employee_id: str):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    if not project_store.remove_member(project_id, employee_id):
        raise HTTPException(404, f"Employee {employee_id} is not a member of project {project_id}")
    return {"status": "deleted", "project_id": project_id, "employee_id": employee_id}


@router.get("/{project_id}/chat/providers")
async def list_project_chat_providers(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    try:
        selected_provider, providers = _pick_chat_provider("")
    except HTTPException as exc:
        if exc.status_code != 400:
            raise
        selected_provider, providers = {}, []
    default_employee, candidates = _resolve_project_chat_employee(project_id, "")
    mcp_modules = _build_chat_mcp_modules(project_id)
    chat_settings = _normalize_project_chat_settings(getattr(project, "chat_settings", {}) or {})
    selected_external_agent_type = normalize_external_agent_type(str(chat_settings.get("external_agent_type") or "codex_cli"))
    external_agent = resolve_external_agent_status(selected_external_agent_type)
    external_agent_bridge = _build_external_agent_mcp_bridge(project, create_if_missing=False)
    external_agent_context = prepare_external_agent_workspace_context(
        project_id=project_id,
        project_name=str(project.name or "").strip(),
        project_description=str(project.description or "").strip(),
        workspace_path=str(project.workspace_path or "").strip(),
        sandbox_mode=str(chat_settings.get("external_agent_sandbox_mode") or "workspace-write").strip() or "workspace-write",
        agent_type=selected_external_agent_type,
        selected_employee_names=[],
        candidate_preview=[
            f"{str(item.get('name') or item.get('id') or '').strip()}({str(item.get('role') or 'member').strip() or 'member'})"
            for item in candidates[:8]
            if str(item.get("id") or "").strip()
        ],
        system_prompt=str(chat_settings.get("system_prompt") or "").strip(),
        mcp_bridge=external_agent_bridge,
        write_files=False,
    )
    effective_workspace_access = await probe_workspace_access_effective_async(
        str(project.workspace_path or "").strip(),
        str(chat_settings.get("external_agent_sandbox_mode") or "workspace-write").strip() or "workspace-write",
    )

    return {
        "project_id": project_id,
        "workspace_path": str(project.workspace_path or ""),
        "chat_modes": [
            {"id": "system", "label": "系统对话"},
            {"id": "external_agent", "label": "外部 Agent"},
        ],
        "providers": providers,
        "default_provider_id": str(selected_provider.get("id") or ""),
        "default_model_name": str(selected_provider.get("default_model") or ""),
        "employees": candidates,
        "default_employee_id": str((default_employee or {}).get("id") or ""),
        "mcp_modules": mcp_modules,
        "chat_settings": chat_settings,
        "external_agent": {
            **external_agent,
            "workspace_path": str(project.workspace_path or ""),
            "context_root": str(external_agent_context.get("context_root") or ""),
            "support_dir": str(external_agent_context.get("support_dir") or ""),
            "support_files": list(external_agent_context.get("support_files") or []),
            "mcp_bridge_enabled": bool(external_agent_bridge.get("enabled")),
            "mcp_bridge_reason": str(external_agent_bridge.get("reason") or ""),
            "mcp_server_name": str(external_agent_bridge.get("server_name") or ""),
            "workspace_access": effective_workspace_access or external_agent_context.get("workspace_access") or probe_workspace_access(str(project.workspace_path or ""), str(chat_settings.get("external_agent_sandbox_mode") or "workspace-write")),
            "agent_types": list_external_agent_statuses(),
        },
    }


@router.get("/{project_id}/chat/settings")
async def get_project_chat_settings(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    return {"project_id": project_id, "settings": _normalize_project_chat_settings(getattr(project, "chat_settings", {}) or {})}


@router.put("/{project_id}/chat/settings")
async def update_project_chat_settings(project_id: str, req: ProjectChatSettingsUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    normalized = _normalize_project_chat_settings(req.settings or {})
    updated = replace(project, chat_settings=normalized, updated_at=_now_iso())
    project_store.save(updated)
    persisted = project_store.get(project_id)
    persisted_settings = _normalize_project_chat_settings(getattr(persisted, "chat_settings", {}) or {}) if persisted else normalized
    return {"status": "updated", "project_id": project_id, "settings": persisted_settings}


@router.get("/{project_id}/chat/history")
async def list_project_chat_history(
    project_id: str,
    limit: int = 200,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    username = _current_username(auth_payload)
    records = project_chat_store.list_messages(project_id, username, limit=limit)
    return {"messages": [asdict(item) for item in records]}


@router.delete("/{project_id}/chat/history")
async def clear_project_chat_history(
    project_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    username = _current_username(auth_payload)
    removed = project_chat_store.clear_messages(project_id, username)
    return {"status": "cleared", "removed_count": int(removed)}


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

    project = project_store.get(project_id)
    if project is None:
        await websocket.close(code=4404, reason=f"Project {project_id} not found")
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
    approval_waiters: dict[str, asyncio.Future] = {}
    review_waiters: dict[str, asyncio.Future] = {}
    external_session: Any = None

    async def ensure_external_agent_session(req: ProjectChatReq) -> dict[str, Any]:
        nonlocal external_session
        runtime_settings = _resolve_chat_runtime_settings(req, project)
        selected_employees, candidates = _resolve_project_chat_employees(
            project_id,
            list(runtime_settings.get("selected_employee_ids") or []),
            str(runtime_settings.get("selected_employee_id") or ""),
        )
        selected_employee = selected_employees[0] if len(selected_employees) == 1 else None
        selected_employee_ids = [
            str(item.get("id") or "")
            for item in selected_employees
            if str(item.get("id") or "")
        ]
        employee_id_val = selected_employee_ids[0] if len(selected_employee_ids) == 1 else ""
        agent_type = normalize_external_agent_type(str(runtime_settings.get("external_agent_type") or "codex_cli"))
        sandbox_mode = str(runtime_settings.get("external_agent_sandbox_mode") or "workspace-write").strip().lower() or "workspace-write"
        external_agent_bridge = _build_external_agent_mcp_bridge(project, create_if_missing=True)
        approval_risks = detect_external_agent_risk_signals(str(req.message or "").strip())
        selected_employee_names = [
            str(item.get("name") or item.get("id") or "").strip()
            for item in selected_employees
            if str(item.get("id") or "").strip()
        ]
        candidate_preview = [
            f"{str(item.get('name') or item.get('id') or '').strip()}({str(item.get('role') or 'member').strip() or 'member'})"
            for item in candidates[:8]
            if str(item.get("id") or "").strip()
        ]
        external_agent_context = prepare_external_agent_workspace_context(
            project_id=project_id,
            project_name=str(project.name or "").strip(),
            project_description=str(project.description or "").strip(),
            workspace_path=str(project.workspace_path or "").strip(),
            sandbox_mode=sandbox_mode,
            agent_type=agent_type,
            selected_employee_names=selected_employee_names,
            candidate_preview=candidate_preview,
            system_prompt=str(runtime_settings.get("system_prompt") or "").strip(),
            mcp_bridge=external_agent_bridge,
            write_files=False,
        )
        external_agent_context = await materialize_external_agent_workspace_context_async(external_agent_context)
        agent_status = resolve_external_agent_status(agent_type)
        startup_context = str(external_agent_context.get("startup_context") or "").strip() or _build_external_agent_startup_context(
            project,
            agent_label=str(agent_status.get("label") or agent_type),
            candidates=candidates,
            selected_employees=selected_employees,
            system_prompt=str(runtime_settings.get("system_prompt") or "").strip(),
            sandbox_mode=sandbox_mode,
        )
        session_overrides = list(external_agent_bridge.get("config_overrides") or [])
        if (
            external_session is None
            or str(getattr(external_session, "agent_type", "codex_cli") or "codex_cli") != agent_type
            or external_session.workspace_path != str(project.workspace_path or "").strip()
            or external_session.sandbox_mode != sandbox_mode
            or list(getattr(external_session, "codex_config_overrides", []) or []) != session_overrides
            or str(getattr(external_session, "startup_context", "") or "").strip() != startup_context
        ):
            if external_session is not None:
                await external_session.close()
            external_session = create_external_agent_session(
                project_id=project_id,
                project_name=str(project.name or "").strip(),
                username=username,
                workspace_path=str(project.workspace_path or "").strip(),
                startup_context=startup_context,
                agent_type=agent_type,
                sandbox_mode=sandbox_mode,
                codex_config_overrides=session_overrides,
            )
        await external_session.prepare_session()
        return {
            "runtime_settings": runtime_settings,
            "selected_employee": selected_employee,
            "selected_employee_ids": selected_employee_ids,
            "employee_id_val": employee_id_val,
            "agent_type": agent_type,
            "sandbox_mode": sandbox_mode,
            "external_agent_context": external_agent_context,
            "external_agent_bridge": external_agent_bridge,
            "approval_risks": approval_risks,
            "session": external_session,
            "agent_status": agent_status,
        }

    async def handle_request(payload: dict):
        nonlocal active_tasks, cancel_events, external_session
        request_id = str(payload.get("request_id") or "").strip()
        if str(payload.get("type") or "").strip().lower() == "ping":
            await websocket.send_json({"type": "pong", "request_id": request_id})
            return

        if str(payload.get("type") or "").strip().lower() == "cancel":
            if request_id in cancel_events:
                cancel_events[request_id].set()
            return

        if str(payload.get("type") or "").strip().lower() == "approval_response":
            approval_id = str(payload.get("approval_id") or "").strip()
            future = approval_waiters.get(approval_id)
            if future is not None and not future.done():
                future.set_result(bool(payload.get("approved")))
            return

        if str(payload.get("type") or "").strip().lower() == "terminal_mirror_start":
            try:
                req = ProjectChatReq.model_validate(payload)
                external_meta = await ensure_external_agent_session(req)
                session = external_meta["session"]
                async def _emit_terminal(event: dict[str, Any]) -> None:
                    event["project_id"] = project_id
                    await websocket.send_json(event)
                await session.start_terminal_mirror(on_event=_emit_terminal)
            except Exception as exc:
                await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
            return

        if str(payload.get("type") or "").strip().lower() == "terminal_mirror_input":
            try:
                req = ProjectChatReq.model_validate(payload)
                external_meta = await ensure_external_agent_session(req)
                session = external_meta["session"]
                if session is None:
                    raise RuntimeError("外部 Agent 会话未初始化")
                await session.start_terminal_mirror(on_event=None)
                await session.write_terminal_input(str(payload.get("content") or ""))
            except Exception as exc:
                await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
            return

        if str(payload.get("type") or "").strip().lower() == "terminal_mirror_stop":
            try:
                if external_session is not None:
                    await external_session.stop_terminal_mirror()
            except Exception as exc:
                await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
            return

        try:
            req = ProjectChatReq.model_validate(payload)
        except Exception as exc:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": f"Invalid payload: {str(exc)}"})
            return

        if str(payload.get("type") or "").strip().lower() == "agent_prepare":
            try:
                external_meta = await ensure_external_agent_session(req)
                session = external_meta["session"]
                external_agent_context = external_meta["external_agent_context"]
                external_agent_bridge = external_meta["external_agent_bridge"]
                agent_status = external_meta["agent_status"]
                agent_type = str(external_meta.get("agent_type") or "codex_cli")
                sandbox_mode = str(external_meta.get("sandbox_mode") or "workspace-write")
                await websocket.send_json(
                    {
                        "type": "agent_ready",
                        "request_id": request_id,
                        "project_id": project_id,
                        "chat_mode": "external_agent",
                        "agent_type": agent_type,
                        "agent_session_id": session.session_id,
                        "thread_id": session.thread_id,
                        "workspace_path": str(project.workspace_path or ""),
                        "sandbox_mode": sandbox_mode,
                        "model_name": str(agent_status.get("runtime_model_name") or agent_type),
                        "label": str(agent_status.get("label") or agent_type),
                        "support_dir": str(external_agent_context.get("support_dir") or ""),
                        "support_files": list(external_agent_context.get("support_files") or []),
                        "workspace_access": external_agent_context.get("workspace_access") or probe_workspace_access(str(project.workspace_path or ""), sandbox_mode),
                        "mcp_bridge_enabled": bool(external_agent_bridge.get("enabled")),
                        "mcp_server_name": str(external_agent_bridge.get("server_name") or ""),
                        "mcp_bridge_reason": str(external_agent_bridge.get("reason") or ""),
                        "command": str(agent_status.get("command") or ""),
                        "resolved_command": str(agent_status.get("resolved_command") or ""),
                        "command_source": str(agent_status.get("command_source") or "missing"),
                        "execution_mode": str(agent_status.get("execution_mode") or "local"),
                        "runner_url": str(agent_status.get("runner_url") or ""),
                        "implemented": bool(agent_status.get("implemented")),
                        "installed": bool(agent_status.get("installed")),
                        "reason": str(agent_status.get("reason") or ""),
                        "supports_terminal_mirror": bool(agent_status.get("supports_terminal_mirror")),
                        "supports_workspace_write": bool(agent_status.get("supports_workspace_write")),
                        "agent_types": list_external_agent_statuses(),
                        "materialized_by": str(external_agent_context.get("materialized_by") or ""),
                    }
                )
            except Exception as exc:
                await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
            return

        user_message = str(req.message or "").strip()
        normalized_images = _normalize_image_inputs(req.images)
        attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
        if not user_message and not normalized_images and not attachment_names:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": "message is required"})
            return

        effective_user_message = user_message
        if not effective_user_message and attachment_names:
            effective_user_message = f"我上传了附件：{', '.join(attachment_names)}。请先给我处理建议。"
        elif not effective_user_message and normalized_images:
            effective_user_message = "请基于我上传的图片给建议。"
        record_content = user_message or ("（发送了图片）" if normalized_images else "（发送了附件）")
        _append_chat_record(
            project_id=project_id, username=username, role="user", content=record_content,
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
            chat_mode = str(runtime_settings.get("chat_mode") or "system").strip().lower()
            if chat_mode == "external_agent":
                external_meta = await ensure_external_agent_session(req)
                sandbox_mode = str(external_meta.get("sandbox_mode") or "workspace-write")
                external_agent_bridge = external_meta["external_agent_bridge"]
                approval_risks = list(external_meta.get("approval_risks") or [])
                external_agent_context = external_meta["external_agent_context"]
                external_session = external_meta["session"]
                selected_employee = external_meta.get("selected_employee")
                selected_employee_ids = list(external_meta.get("selected_employee_ids") or [])
                employee_id_val = str(external_meta.get("employee_id_val") or "")
                agent_status = external_meta.get("agent_status") or {}
                if approval_risks:
                    approval_id = f"approval-{uuid.uuid4().hex[:10]}"
                    approval_future = asyncio.get_running_loop().create_future()
                    approval_waiters[approval_id] = approval_future
                    await websocket.send_json(
                        {
                            "type": "approval_required",
                            "request_id": request_id,
                            "approval_id": approval_id,
                            "chat_mode": "external_agent",
                            "title": "检测到高风险操作",
                            "message": "外部 Agent 请求命中高风险规则，需确认后才继续执行。",
                            "risk_signals": approval_risks,
                        }
                    )
                    approved = False
                    try:
                        while True:
                            if cancel_event.is_set():
                                break
                            try:
                                approved = bool(await asyncio.wait_for(asyncio.shield(approval_future), timeout=0.25))
                                break
                            except asyncio.TimeoutError:
                                continue
                    finally:
                        approval_waiters.pop(approval_id, None)
                    await websocket.send_json(
                        {
                            "type": "approval_resolved",
                            "request_id": request_id,
                            "approval_id": approval_id,
                            "approved": bool(approved),
                        }
                    )
                    if not approved:
                        denied_message = "已取消执行：审批未通过。"
                        await websocket.send_json(
                            {
                                "type": "done",
                                "request_id": request_id,
                                "content": denied_message,
                                "chat_mode": "external_agent",
                            }
                        )
                        _append_chat_record(
                            project_id=project_id,
                            username=username,
                            role="assistant",
                            content=denied_message,
                            display_mode="terminal",
                        )
                        return
                await websocket.send_json(
                    {
                        "type": "start",
                        "request_id": request_id,
                        "project_id": project_id,
                        "provider_id": "",
                        "chat_mode": "external_agent",
                        "agent_type": str(external_session.agent_type or "codex_cli"),
                        "agent_session_id": external_session.session_id,
                        "thread_id": external_session.thread_id,
                        "workspace_path": str(project.workspace_path or ""),
                        "sandbox_mode": sandbox_mode,
                        "model_name": str(resolve_external_agent_status(getattr(external_session, "agent_type", "codex_cli")).get("runtime_model_name") or getattr(external_session, "agent_type", "codex_cli")),
                        "support_dir": str(external_agent_context.get("support_dir") or ""),
                        "support_files": list(external_agent_context.get("support_files") or []),
                        "mcp_bridge_enabled": bool(external_agent_bridge.get("enabled")),
                        "mcp_server_name": str(external_agent_bridge.get("server_name") or ""),
                        "mcp_bridge_reason": str(external_agent_bridge.get("reason") or ""),
                        "employee_id": employee_id_val,
                        "employee_name": str((selected_employee or {}).get("name") or ""),
                        "employee_ids": selected_employee_ids,
                        "tools_enabled": False,
                        "command": str(agent_status.get("command") or ""),
                        "resolved_command": str(agent_status.get("resolved_command") or ""),
                        "command_source": str(agent_status.get("command_source") or "missing"),
                        "label": str(agent_status.get("label") or getattr(external_session, "agent_type", "codex_cli")),
                        "execution_mode": str(agent_status.get("execution_mode") or "local"),
                        "runner_url": str(agent_status.get("runner_url") or ""),
                        "implemented": bool(agent_status.get("implemented")),
                        "installed": bool(agent_status.get("installed")),
                        "reason": str(agent_status.get("reason") or ""),
                        "supports_terminal_mirror": bool(agent_status.get("supports_terminal_mirror")),
                        "supports_workspace_write": bool(agent_status.get("supports_workspace_write")),
                        "agent_types": list_external_agent_statuses(),
                    }
                )
                final_output = ""
                file_review_status = "not_required"
                approval_context = {
                    "mode": "websocket_confirm" if approval_risks else "none",
                    "status": "approved" if approval_risks else "not_required",
                }
                async for event in external_session.send_prompt(
                    effective_user_message,
                    cancel_event=cancel_event,
                    approval_context=approval_context,
                    history=req.history,
                ):
                    if str(event.get("type") or "") == "audit":
                        audit_payload = event.get("audit") if isinstance(event.get("audit"), dict) else {}
                        before_diff_summary = audit_payload.get("before_diff_summary") if isinstance(audit_payload.get("before_diff_summary"), dict) else {}
                        diff_summary = audit_payload.get("after_diff_summary") if isinstance(audit_payload.get("after_diff_summary"), dict) else {}
                        if has_meaningful_workspace_changes(before_diff_summary, diff_summary):
                            review_id = f"review-{uuid.uuid4().hex[:10]}"
                            review_future = asyncio.get_running_loop().create_future()
                            review_waiters[review_id] = review_future
                            event["request_id"] = request_id
                            event["chat_mode"] = "external_agent"
                            await websocket.send_json(event)
                            await websocket.send_json(
                                {
                                    "type": "file_review_required",
                                    "request_id": request_id,
                                    "review_id": review_id,
                                    "chat_mode": "external_agent",
                                    "title": "检测到文件改动",
                                    "message": "外部 Agent 已修改工作区文件，请先审查 Git diff 摘要后确认。",
                                    "diff_summary": diff_summary,
                                }
                            )
                            reviewed = False
                            try:
                                while True:
                                    if cancel_event.is_set():
                                        break
                                    try:
                                        reviewed = bool(await asyncio.wait_for(asyncio.shield(review_future), timeout=0.25))
                                        break
                                    except asyncio.TimeoutError:
                                        continue
                            finally:
                                review_waiters.pop(review_id, None)
                            file_review_status = "approved" if reviewed else "rejected"
                            await websocket.send_json(
                                {
                                    "type": "file_review_resolved",
                                    "request_id": request_id,
                                    "review_id": review_id,
                                    "approved": bool(reviewed),
                                }
                            )
                            continue
                    event["request_id"] = request_id
                    event["chat_mode"] = "external_agent"
                    if str(event.get("type") or "") == "audit":
                        audit_payload = event.get("audit") if isinstance(event.get("audit"), dict) else {}
                        audit_payload["file_review_status"] = file_review_status
                        event["audit"] = audit_payload
                    await websocket.send_json(event)
                    if str(event.get("type") or "") == "done":
                        final_output = str(event.get("content") or "")
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=final_output or "外部 Agent 未返回有效内容。",
                    display_mode="terminal",
                )
                return

            enabled_tool_names = list(runtime_settings.get("enabled_project_tool_names") or [])
            explicit_tool_filter = ("enabled_project_tool_names" in req.model_fields_set) or bool(enabled_tool_names)
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
                _append_chat_record(project_id=project_id, username=username, role="assistant", content=direct_answer)
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
                _append_chat_record(project_id=project_id, username=username, role="assistant", content=direct_answer)
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
                _append_chat_record(project_id=project_id, username=username, role="assistant", content=direct_answer)
                return

            selected_provider, _ = _pick_chat_provider(str(runtime_settings.get("provider_id") or ""))
            provider_id = str(selected_provider.get("id") or "")
            model_name = str(runtime_settings.get("model_name") or "").strip() or str(selected_provider.get("default_model") or "")
            if not model_name:
                raise ValueError("model_name is required")
            max_tokens = _resolve_chat_max_tokens(runtime_settings.get("max_tokens"))
            temperature = float(runtime_settings.get("temperature") if runtime_settings.get("temperature") is not None else 0.1)
            temperature = max(0.0, min(temperature, 2.0))

            tools: list[dict] = []
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

            messages = _build_project_chat_messages(
                project, effective_user_message, req.history, normalized_images,
                selected_employee=selected_employee,
                tools=tools,
                custom_system_prompt=str(runtime_settings.get("system_prompt") or "").strip() or None,
                history_limit=int(runtime_settings.get("history_limit") or 20),
                answer_style=str(runtime_settings.get("answer_style") or "concise"),
                prefer_conclusion_first=bool(runtime_settings.get("prefer_conclusion_first", True)),
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
        })

        try:
            from services.llm_provider_service import get_llm_provider_service

            final_answer = ""
            stream_error = ""
            llm_service = get_llm_provider_service()

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
                messages=messages
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
                )
            else:
                _append_chat_record(
                    project_id=project_id, username=username, role="assistant", content=final_answer or "模型未返回有效内容。",
                )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            _append_chat_record(
                project_id=project_id, username=username, role="assistant", content=f"对话失败：{str(exc)}",
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
            if payload_type == "approval_response":
                approval_id = str(payload.get("approval_id") or "").strip()
                future = approval_waiters.get(approval_id)
                if future is not None and not future.done():
                    future.set_result(bool(payload.get("approved")))
                continue
            if payload_type == "file_review_response":
                review_id = str(payload.get("review_id") or "").strip()
                future = review_waiters.get(review_id)
                if future is not None and not future.done():
                    future.set_result(bool(payload.get("approved")))
                continue

            task = asyncio.create_task(handle_request(payload))
            if request_id and payload_type != "agent_prepare":
                active_tasks[request_id] = task
                
        except WebSocketDisconnect:
            for ev in cancel_events.values():
                ev.set()
            for future in approval_waiters.values():
                if not future.done():
                    future.set_result(False)
            for future in review_waiters.values():
                if not future.done():
                    future.set_result(False)
            for t in active_tasks.values():
                t.cancel()
            if external_session is not None:
                await external_session.close()
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
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    username = _current_username(auth_payload)

    user_message = str(req.message or "").strip()
    normalized_images = _normalize_image_inputs(req.images)
    attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
    if not user_message and not normalized_images and not attachment_names:
        raise HTTPException(400, "message is required")

    effective_user_message = user_message
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
    explicit_tool_filter = ("enabled_project_tool_names" in req.model_fields_set) or bool(enabled_tool_names)
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
            _append_chat_record(project_id=project_id, username=username, role="assistant", content=answer)

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
            _append_chat_record(project_id=project_id, username=username, role="assistant", content=answer)

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
            _append_chat_record(project_id=project_id, username=username, role="assistant", content=answer)

        return StreamingResponse(
            direct_mcp_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    selected_provider, _ = _pick_chat_provider(str(runtime_settings.get("provider_id") or ""))
    provider_id = str(selected_provider.get("id") or "")
    model_name = str(runtime_settings.get("model_name") or "").strip() or str(selected_provider.get("default_model") or "")
    if not model_name:
        raise HTTPException(400, "model_name is required")

    max_tokens = _resolve_chat_max_tokens(runtime_settings.get("max_tokens"))
    temperature = float(runtime_settings.get("temperature") if runtime_settings.get("temperature") is not None else 0.1)
    temperature = max(0.0, min(temperature, 2.0))

    tools: list[dict] = []
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

    llm_service = get_llm_provider_service()
    messages = _build_project_chat_messages(
        project,
        effective_user_message,
        req.history,
        normalized_images,
        selected_employee=selected_employee,
        tools=tools,
        custom_system_prompt=str(runtime_settings.get("system_prompt") or "").strip() or None,
        history_limit=int(runtime_settings.get("history_limit") or 20),
        answer_style=str(runtime_settings.get("answer_style") or "concise"),
        prefer_conclusion_first=bool(runtime_settings.get("prefer_conclusion_first", True)),
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
            },
        )
        try:
            result = await llm_service.chat_completion(
                provider_id=provider_id,
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=120,
            )
            answer = str(result.get("content") or "").strip() or "模型未返回有效内容。"
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload(
                "message",
                {
                    "type": "done",
                    "content": answer,
                    "provider_id": provider_id,
                    "model_name": model_name,
                },
            )
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=answer,
            )
        except Exception as exc:
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=f"对话失败：{str(exc)}",
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


@router.post("/{project_id}/generate-manual")
async def generate_project_manual(project_id: str):
    """生成项目使用手册（面向接入方 AI 平台）"""
    from services.llm_provider_service import get_llm_provider_service

    _assert_project_manual_generation_enabled()

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)
    if not providers:
        raise HTTPException(400, "未配置 LLM 提供商")
    default_provider = next((p for p in providers if p.get("is_default")), providers[0])

    template_payload = await get_project_manual_template(project_id)
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
async def get_project_manual_template(project_id: str):
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
        employee_template_lines.append(
            f"""### {employee.name}（{employee.id}）
- 角色:{member.role}
- 语调:{getattr(employee, "tone", "-")} / 风格:{getattr(employee, "verbosity", "-")} / 语言:{getattr(employee, "language", "-")}
- 记忆:scope={getattr(employee, "memory_scope", "-")}，保留{getattr(employee, "memory_retention_days", "-")}天

技能:
{employee_skills_text}

规则领域:
{employee_domains_text}

风格提示:
{style_text}
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
    }
