"""Project MCP context query helpers."""

from __future__ import annotations

from dataclasses import asdict

from core.deps import employee_store, external_mcp_store, project_store
from services.dynamic_mcp_profiles import (
    employee_rule_summary,
    list_project_member_profiles_runtime,
    project_ui_rule_summary,
    query_project_rules_runtime,
)
from services.dynamic_mcp_skill_proxies import list_project_proxy_tools_runtime
from stores.mcp_bridge import rule_store, skill_store


def _serialize_employee_detail_runtime(employee) -> dict:
    payload = asdict(employee)
    skill_names: list[str] = []
    for skill_id in payload.get("skills", []) or []:
        normalized_skill_id = str(skill_id or "").strip()
        if not normalized_skill_id:
            continue
        skill = skill_store.get(normalized_skill_id)
        skill_name = str(getattr(skill, "name", "") or "").strip() if skill else ""
        skill_names.append(skill_name or normalized_skill_id)
    payload["skill_names"] = skill_names
    payload["rule_bindings"] = employee_rule_summary(employee, limit=200)
    return payload


def get_project_detail_runtime(project_id: str) -> dict:
    project = project_store.get(project_id)
    if project is None:
        return {"error": f"项目 {project_id} 不存在"}

    members = project_store.list_members(project_id)
    user_members = project_store.list_user_members(project_id)
    payload = asdict(project)
    payload["members"] = [asdict(item) for item in members]
    payload["user_members"] = [asdict(item) for item in user_members]
    payload["member_count"] = len(members)
    payload["active_member_count"] = sum(1 for item in members if bool(getattr(item, "enabled", True)))
    payload["user_count"] = len(user_members)
    payload["active_user_count"] = sum(1 for item in user_members if bool(getattr(item, "enabled", True)))
    payload["ui_rule_ids"] = [
        str(item or "").strip()
        for item in (getattr(project, "ui_rule_ids", []) or [])
        if str(item or "").strip()
    ]
    payload["ui_rule_bindings"] = project_ui_rule_summary(project_id, limit=100)
    return payload


def get_project_employee_detail_runtime(project_id: str, employee_id: str) -> dict:
    project = project_store.get(project_id)
    if project is None:
        return {"error": f"项目 {project_id} 不存在"}

    employee_id_value = str(employee_id or "").strip()
    if not employee_id_value:
        return {"error": "employee_id is required"}

    member = project_store.get_member(project_id, employee_id_value)
    if member is None:
        return {"error": f"Employee {employee_id_value} is not a member of project {project_id}"}

    employee = employee_store.get(employee_id_value)
    result = {
        "project_id": project_id,
        "project_name": str(getattr(project, "name", "") or ""),
        "employee_id": employee_id_value,
        "member": asdict(member),
    }
    if employee is None:
        result["employee_exists"] = False
        result["employee"] = None
        return result

    result["employee_exists"] = True
    result["employee"] = _serialize_employee_detail_runtime(employee)
    return result


def query_project_mcp_modules_runtime(project_id: str, keyword: str = "", limit: int = 20) -> dict:
    project = project_store.get(project_id)
    if project is None:
        return {"error": f"项目 {project_id} 不存在"}

    keyword_lower = str(keyword or "").strip().lower()
    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 20
    limit_value = max(1, min(limit_value, 100))

    def _matches(values: list[str]) -> bool:
        if not keyword_lower:
            return True
        for value in values:
            if keyword_lower in str(value or "").strip().lower():
                return True
        return False

    project_related: list[dict] = []
    for item in list_project_proxy_tools_runtime(project_id, ""):
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            continue
        values = [
            tool_name,
            str(item.get("description") or ""),
            str(item.get("skill_id") or ""),
            str(item.get("entry_name") or ""),
        ]
        if not _matches(values):
            continue
        project_related.append(
            {
                "name": tool_name,
                "module_type": "builtin_tool" if bool(item.get("builtin")) else "project_skill_tool",
                "tool_name": tool_name,
                "employee_id": str(item.get("employee_id") or ""),
                "description": str(item.get("description") or ""),
            }
        )
    project_related = project_related[:limit_value]

    system_global: list[dict] = []
    for item in project_store.list_all():
        if not bool(getattr(item, "mcp_enabled", True)):
            continue
        name = str(getattr(item, "name", "") or getattr(item, "id", "") or "")
        values = [name, str(getattr(item, "description", "") or ""), str(getattr(item, "id", "") or ""), "project_mcp_service"]
        if not _matches(values):
            continue
        system_global.append(
            {
                "name": name,
                "module_type": "project_mcp_service",
                "resource_id": str(getattr(item, "id", "") or ""),
            }
        )

    for item in employee_store.list_all():
        if not bool(getattr(item, "mcp_enabled", True)):
            continue
        name = str(getattr(item, "name", "") or getattr(item, "id", "") or "")
        values = [name, str(getattr(item, "description", "") or ""), str(getattr(item, "id", "") or ""), "employee_mcp_service"]
        if not _matches(values):
            continue
        system_global.append(
            {
                "name": name,
                "module_type": "employee_mcp_service",
                "resource_id": str(getattr(item, "id", "") or ""),
            }
        )

    for item in skill_store.list_all():
        if not bool(getattr(item, "mcp_enabled", False)):
            continue
        name = str(getattr(item, "name", "") or getattr(item, "id", "") or "")
        values = [name, str(getattr(item, "description", "") or ""), str(getattr(item, "id", "") or ""), "skill_mcp_service"]
        if not _matches(values):
            continue
        system_global.append(
            {
                "name": name,
                "module_type": "skill_mcp_service",
                "resource_id": str(getattr(item, "id", "") or ""),
            }
        )

    for item in rule_store.list_all():
        if not bool(getattr(item, "mcp_enabled", False)):
            continue
        name = str(getattr(item, "title", "") or getattr(item, "id", "") or "")
        values = [name, str(getattr(item, "content", "") or ""), str(getattr(item, "id", "") or ""), "rule_mcp_service"]
        if not _matches(values):
            continue
        system_global.append(
            {
                "name": name,
                "module_type": "rule_mcp_service",
                "resource_id": str(getattr(item, "id", "") or ""),
            }
        )
    system_global = system_global[:limit_value]

    external_modules: list[dict] = []
    for item in external_mcp_store.list_all():
        if not bool(getattr(item, "enabled", True)):
            continue
        module_project_id = str(getattr(item, "project_id", "") or "").strip()
        if module_project_id and module_project_id != project_id:
            continue
        name = str(getattr(item, "name", "") or getattr(item, "id", "") or "")
        values = [
            name,
            str(getattr(item, "description", "") or ""),
            str(getattr(item, "endpoint_http", "") or ""),
            str(getattr(item, "endpoint_sse", "") or ""),
            "external_mcp_service",
        ]
        if not _matches(values):
            continue
        external_modules.append(
            {
                "name": name,
                "module_type": "external_mcp_service",
                "project_id": module_project_id,
                "endpoint_http": str(getattr(item, "endpoint_http", "") or ""),
                "endpoint_sse": str(getattr(item, "endpoint_sse", "") or ""),
            }
        )
    external_modules = external_modules[:limit_value]

    return {
        "project_id": project_id,
        "project_name": str(getattr(project, "name", "") or ""),
        "system": {
            "project_related": project_related,
            "system_global": system_global,
        },
        "external": {"modules": external_modules},
        "summary": {
            "system_project_related_total": len(project_related),
            "system_global_total": len(system_global),
            "external_total": len(external_modules),
        },
    }


def search_project_context_runtime(
    project_id: str,
    scope: str = "all",
    keyword: str = "",
    employee_id: str = "",
    limit: int = 20,
) -> dict:
    project = project_store.get(project_id)
    if project is None:
        return {"error": f"项目 {project_id} 不存在"}

    scope_value = str(scope or "all").strip().lower() or "all"
    if scope_value not in {"all", "project", "members", "rules", "mcp"}:
        return {"error": f"Invalid scope: {scope_value}. Valid: ['all','project','members','rules','mcp']"}

    keyword_value = str(keyword or "").strip()
    keyword_lower = keyword_value.lower()
    employee_id_value = str(employee_id or "").strip()
    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 20
    limit_value = max(1, min(limit_value, 100))

    def _matches_text(values: list[str]) -> bool:
        if not keyword_lower:
            return True
        for value in values:
            if keyword_lower in str(value or "").strip().lower():
                return True
        return False

    result: dict[str, object] = {
        "project_id": project_id,
        "scope": scope_value,
        "keyword": keyword_value,
        "employee_id": employee_id_value,
    }

    if scope_value in {"all", "project"}:
        project_ui_rules = project_ui_rule_summary(project_id, limit=limit_value)
        result["project"] = {
            "id": project_id,
            "name": str(getattr(project, "name", "") or ""),
            "description": str(getattr(project, "description", "") or ""),
            "workspace_path": str(getattr(project, "workspace_path", "") or ""),
            "mcp_enabled": bool(getattr(project, "mcp_enabled", True)),
            "feedback_upgrade_enabled": bool(getattr(project, "feedback_upgrade_enabled", False)),
            "ui_rule_ids": [
                str(item or "").strip()
                for item in (getattr(project, "ui_rule_ids", []) or [])
                if str(item or "").strip()
            ],
            "ui_rule_bindings": project_ui_rules,
            "ui_rule_count": len(project_ui_rules),
        }

    if scope_value in {"all", "members"}:
        profiles = list_project_member_profiles_runtime(
            project_id,
            include_disabled=True,
            include_missing=True,
            rule_limit=50,
        )
        filtered_profiles: list[dict] = []
        for item in profiles:
            item_employee_id = str(item.get("employee_id") or "").strip()
            if employee_id_value and item_employee_id != employee_id_value:
                continue
            rule_bindings = list(item.get("rule_bindings") or [])
            values = [
                item_employee_id,
                str(item.get("name") or ""),
                str(item.get("description") or ""),
                " ".join(str(value or "") for value in (item.get("skill_names") or [])),
                " ".join(str(value.get("title") or value.get("id") or "") for value in rule_bindings),
                " ".join(str(value.get("domain") or "") for value in rule_bindings),
            ]
            if not _matches_text(values):
                continue
            filtered_profiles.append(item)
        result["members"] = filtered_profiles[:limit_value]
        result["members_total"] = len(filtered_profiles)

    if scope_value in {"all", "rules"}:
        rules = query_project_rules_runtime(project_id, keyword=keyword_value, employee_id=employee_id_value)
        result["rules"] = rules[:limit_value]
        result["rules_total"] = len(rules)

    if scope_value in {"all", "mcp"}:
        mcp_modules = query_project_mcp_modules_runtime(project_id, keyword=keyword_value, limit=limit_value)
        result["mcp_modules"] = mcp_modules

    return result
