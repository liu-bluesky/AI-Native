"""Project member profile helpers for dynamic MCP runtime."""

from __future__ import annotations

from core.deps import employee_store, project_store
from stores.mcp_bridge import rule_store, serialize_rule, skill_store


def _normalize_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _matches_rule_keyword(rule, keyword: str) -> bool:
    kw = str(keyword or "").strip().lower()
    if not kw:
        return True
    return any(
        kw in str(value or "").strip().lower()
        for value in (
            getattr(rule, "id", ""),
            getattr(rule, "title", ""),
            getattr(rule, "domain", ""),
            getattr(rule, "content", ""),
        )
    )


def query_rules_by_employee(employee, keyword: str = "") -> list:
    rule_ids = [
        str(item or "").strip()
        for item in (getattr(employee, "rule_ids", []) or [])
        if str(item or "").strip()
    ]
    kw = str(keyword or "").strip().lower()
    if rule_ids:
        seen: set[str] = set()
        results = []
        for rule_id in rule_ids:
            if rule_id in seen:
                continue
            seen.add(rule_id)
            rule = rule_store.get(rule_id)
            if rule is None:
                continue
            if kw and kw not in rule.title.lower() and kw not in rule.content.lower():
                continue
            results.append(rule)
        return results

    domains = {_normalize_domain(d) for d in employee.rule_domains or [] if str(d).strip()}
    if not domains:
        return []
    results = []
    for rule in rule_store.list_all():
        if _normalize_domain(rule.domain) not in domains:
            continue
        if kw and kw not in rule.title.lower() and kw not in rule.content.lower():
            continue
        results.append(rule)
    return results


def query_project_ui_rules_runtime(project_id: str, keyword: str = "") -> list[dict]:
    project = project_store.get(project_id)
    if project is None:
        return []
    results: list[dict] = []
    seen_rule_ids: set[str] = set()
    for item in getattr(project, "ui_rule_ids", []) or []:
        rule_id = str(item or "").strip()
        if not rule_id or rule_id in seen_rule_ids:
            continue
        seen_rule_ids.add(rule_id)
        rule = rule_store.get(rule_id)
        if rule is None or not _matches_rule_keyword(rule, keyword):
            continue
        payload = serialize_rule(rule)
        payload["binding_scope"] = "project_ui"
        results.append(payload)
    return results


def project_ui_rule_summary(project_id: str, limit: int = 50) -> list[dict[str, str]]:
    items = query_project_ui_rules_runtime(project_id)
    summary: list[dict[str, str]] = []
    for rule in items[:limit]:
        summary.append(
            {
                "id": str(rule.get("id") or "").strip(),
                "title": str(rule.get("title") or rule.get("id") or "").strip(),
                "domain": str(rule.get("domain") or "").strip(),
            }
        )
    return summary


def employee_rule_summary(employee, limit: int = 50) -> list[dict[str, str]]:
    rules = query_rules_by_employee(employee)
    rule_bindings: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for rule in rules:
        if len(rule_bindings) >= limit:
            break
        rid = str(getattr(rule, "id", "") or "").strip()
        if not rid or rid in seen_ids:
            continue
        seen_ids.add(rid)
        rule_bindings.append(
            {
                "id": rid,
                "title": str(getattr(rule, "title", "") or "").strip(),
                "domain": str(getattr(rule, "domain", "") or "").strip(),
            }
        )
    return rule_bindings


def _employee_skill_summary(employee) -> tuple[list[str], list[str]]:
    skill_ids: list[str] = []
    skill_names: list[str] = []
    seen: set[str] = set()
    for item in getattr(employee, "skills", []) or []:
        skill_id = str(item or "").strip()
        if not skill_id or skill_id in seen:
            continue
        seen.add(skill_id)
        skill_ids.append(skill_id)
        skill = skill_store.get(skill_id)
        skill_name = str(getattr(skill, "name", "") or "").strip() or skill_id
        skill_names.append(skill_name)
    if not skill_names:
        skill_names = list(skill_ids)
    return skill_ids, skill_names


def _serialize_project_member_profile(
    member,
    employee,
    *,
    project_id: str,
    rule_limit: int,
) -> dict:
    employee_id = str(getattr(member, "employee_id", "") or "").strip()
    if employee is None:
        return {
            "project_id": project_id,
            "employee_id": employee_id,
            "id": employee_id,
            "employee_name": "",
            "name": "",
            "description": "",
            "goal": "",
            "role": str(getattr(member, "role", "member") or "member"),
            "enabled": bool(getattr(member, "enabled", True)),
            "joined_at": str(getattr(member, "joined_at", "") or ""),
            "skills": [],
            "skill_names": [],
            "rule_bindings": [],
            "tone": "",
            "verbosity": "",
            "language": "",
            "default_workflow": [],
            "tool_usage_policy": "",
            "mcp_enabled": False,
            "feedback_upgrade_enabled": False,
            "employee_exists": False,
        }

    resolved_employee_id = str(getattr(employee, "id", "") or employee_id).strip()
    employee_name = str(getattr(employee, "name", "") or "").strip()
    skill_ids, skill_names = _employee_skill_summary(employee)
    rule_bindings = employee_rule_summary(employee, limit=rule_limit)
    return {
        "project_id": project_id,
        "employee_id": resolved_employee_id,
        "id": resolved_employee_id,
        "employee_name": employee_name,
        "name": employee_name,
        "description": str(getattr(employee, "description", "") or ""),
        "goal": str(getattr(employee, "goal", "") or ""),
        "role": str(getattr(member, "role", "member") or "member"),
        "enabled": bool(getattr(member, "enabled", True)),
        "joined_at": str(getattr(member, "joined_at", "") or ""),
        "skills": skill_ids,
        "skill_names": skill_names,
        "rule_bindings": rule_bindings,
        "tone": str(getattr(employee, "tone", "") or ""),
        "verbosity": str(getattr(employee, "verbosity", "") or ""),
        "language": str(getattr(employee, "language", "") or ""),
        "default_workflow": list(getattr(employee, "default_workflow", []) or []),
        "tool_usage_policy": str(getattr(employee, "tool_usage_policy", "") or ""),
        "mcp_enabled": bool(getattr(employee, "mcp_enabled", False)),
        "feedback_upgrade_enabled": bool(getattr(employee, "feedback_upgrade_enabled", False)),
        "employee_exists": True,
    }


def list_project_member_profiles_runtime(
    project_id: str,
    *,
    include_disabled: bool = True,
    include_missing: bool = True,
    rule_limit: int = 30,
) -> list[dict]:
    project = project_store.get(project_id)
    if project is None:
        return []
    profiles: list[dict] = []
    for member in project_store.list_members(project_id):
        if not include_disabled and not bool(getattr(member, "enabled", True)):
            continue
        employee = employee_store.get(member.employee_id)
        if employee is None and not include_missing:
            continue
        profiles.append(
            _serialize_project_member_profile(
                member,
                employee,
                project_id=project_id,
                rule_limit=rule_limit,
            )
        )
    return profiles


def query_project_members_runtime(project_id: str) -> dict:
    project = project_store.get(project_id)
    if project is None:
        return {"error": f"项目 {project_id} 不存在"}
    members = list_project_member_profiles_runtime(
        project_id,
        include_disabled=True,
        include_missing=True,
        rule_limit=20,
    )
    return {
        "project_id": project_id,
        "project_name": project.name,
        "members": members,
        "total": len(members),
    }


def query_project_rules_runtime(project_id: str, keyword: str = "", employee_id: str = "") -> list[dict]:
    project = project_store.get(project_id)
    if project is None:
        return []
    keyword_value = str(keyword or "").strip()
    keyword_lower = keyword_value.lower()
    employee_id_value = str(employee_id or "").strip()
    results: list[dict] = list(query_project_ui_rules_runtime(project_id, keyword=keyword_value))
    seen_rule_ids: set[str] = {
        str(item.get("id") or "").strip() for item in results if str(item.get("id") or "").strip()
    }
    selected_employees = []
    for member in project_store.list_members(project_id):
        member_employee_id = str(getattr(member, "employee_id", "") or "").strip()
        if not member_employee_id:
            continue
        if employee_id_value and member_employee_id != employee_id_value:
            continue
        employee = employee_store.get(member_employee_id)
        if employee is None:
            continue
        selected_employees.append(employee)
    for employee in selected_employees:
        for rule in query_rules_by_employee(employee, keyword_value):
            rid = str(getattr(rule, "id", "") or "").strip()
            if rid and rid in seen_rule_ids:
                continue
            if rid:
                seen_rule_ids.add(rid)
            payload = serialize_rule(rule)
            payload["binding_scope"] = "employee"
            results.append(payload)

    if results:
        return results

    if employee_id_value:
        return []

    fallback_rules = (
        rule_store.query(keyword_value)
        if keyword_value and hasattr(rule_store, "query")
        else rule_store.list_all()
    )
    for rule in fallback_rules:
        title_lower = str(getattr(rule, "title", "") or "").lower()
        content_lower = str(getattr(rule, "content", "") or "").lower()
        if keyword_lower and keyword_lower not in title_lower and keyword_lower not in content_lower:
            continue
        rid = str(getattr(rule, "id", "") or "").strip()
        if rid and rid in seen_rule_ids:
            continue
        if rid:
            seen_rule_ids.add(rid)
        payload = serialize_rule(rule)
        payload["binding_scope"] = "catalog"
        results.append(payload)
    return results
