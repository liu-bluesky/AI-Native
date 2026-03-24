"""员工管理路由"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Depends

from core.config import get_project_root
from core.ownership import assert_can_manage_record, current_username, ownership_payload
from core.deps import (
    employee_store,
    ensure_permission,
    is_admin_like,
    project_store,
    require_auth,
    role_store,
    system_config_store,
)
from core.role_permissions import has_permission
from services.external_rule_service import suggest_external_rules as build_external_rule_suggestions
from services.external_skill_service import suggest_external_skills as build_external_skill_suggestions
from services.employee_template_import_service import import_agent_templates
from stores.json.employee_store import EmployeeConfig, _now_iso
from services.system_mcp_discovery import list_system_mcp_skills
from stores.mcp_bridge import (
    ResourceDef,
    RiskDomain,
    Rule,
    Severity,
    Skill,
    ToolDef,
    rule_store,
    skill_store,
    skills_now_iso,
)
from models.requests import EmployeeAgentTemplateImportReq, EmployeeCreateReq, EmployeeDraftCreateReq, EmployeeDraftGenerateReq, EmployeeExternalRuleSuggestReq, EmployeeExternalSkillSuggestReq, EmployeeUpdateReq

def _require_employee_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.employees")


def _has_employee_action_permission(auth_payload: dict | None, permission_key: str) -> bool:
    payload = auth_payload or {}
    role_id = str(payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    role_permissions = getattr(role, "permissions", None)
    return has_permission(role_permissions, permission_key, role_id=role_id)


def _assert_can_manage_employee_action(
    employee: EmployeeConfig,
    auth_payload: dict | None,
    resource_label: str,
    permission_key: str,
) -> None:
    if _has_employee_action_permission(auth_payload, permission_key):
        return
    assert_can_manage_record(employee, auth_payload, resource_label)


router = APIRouter(
    prefix="/api/employees",
    dependencies=[Depends(require_auth), Depends(_require_employee_permission)],
)


_TOOL_SUFFIXES = {".py", ".js"}
_SYSTEM_MCP_SKILL_TAG = "system-mcp-import"


def _normalize_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_tokens(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values or []:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _normalize_text_value(value: Any, *, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _normalize_text_list(values: list[str] | None, *, limit: int = 20, item_limit: int = 240) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values or []:
        text = _normalize_text_value(item, limit=item_limit)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _normalize_match_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _slugify_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    token = re.sub(r"-{2,}", "-", token)
    return token[:48]


def _build_rule_lookup() -> tuple[dict[str, Any], dict[str, list[Any]]]:
    by_id: dict[str, Any] = {}
    by_domain: dict[str, list[Any]] = {}
    for rule in rule_store.list_all():
        rid = str(getattr(rule, "id", "") or "").strip()
        if rid:
            by_id[rid] = rule
        domain_key = _normalize_domain(getattr(rule, "domain", ""))
        if not domain_key:
            continue
        by_domain.setdefault(domain_key, []).append(rule)
    for items in by_domain.values():
        items.sort(key=lambda r: (str(getattr(r, "title", "") or ""), str(getattr(r, "id", "") or "")))
    return by_id, by_domain


def _resolve_rule_ids_and_domains(
    *,
    rule_ids: list[str] | None,
    rule_domains: list[str] | None,
) -> tuple[list[str], list[str]]:
    normalized_rule_ids = _normalize_tokens(rule_ids)
    normalized_rule_domains = _normalize_tokens(rule_domains)
    by_id, by_domain = _build_rule_lookup()

    if normalized_rule_ids:
        derived_domains: list[str] = []
        seen_domain_keys: set[str] = set()
        for rule_id in normalized_rule_ids:
            rule = by_id.get(rule_id)
            if rule is None:
                continue
            domain = str(getattr(rule, "domain", "") or "").strip()
            key = _normalize_domain(domain)
            if not key or key in seen_domain_keys:
                continue
            seen_domain_keys.add(key)
            derived_domains.append(domain)
        # rule_ids 是主绑定来源，rule_domains 由 rule_ids 聚合得到。
        return normalized_rule_ids, derived_domains

    derived_rule_ids: list[str] = []
    seen_rule_ids: set[str] = set()
    for domain in normalized_rule_domains:
        key = _normalize_domain(domain)
        for rule in by_domain.get(key, []):
            rid = str(getattr(rule, "id", "") or "").strip()
            if not rid or rid in seen_rule_ids:
                continue
            seen_rule_ids.add(rid)
            derived_rule_ids.append(rid)
    return derived_rule_ids, normalized_rule_domains


def _extract_rule_ids_and_domains_from_bindings(
    rule_bindings: list[dict[str, Any] | str] | None,
) -> tuple[list[str], list[str]]:
    rule_ids: list[str] = []
    rule_domains: list[str] = []
    for item in rule_bindings or []:
        if isinstance(item, str):
            value = str(item or "").strip()
            if value:
                rule_ids.append(value)
            continue
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("id", "") or "").strip()
        domain = str(item.get("domain", "") or "").strip()
        if rule_id:
            rule_ids.append(rule_id)
            continue
        if domain:
            rule_domains.append(domain)
    return _normalize_tokens(rule_ids), _normalize_tokens(rule_domains)


def _resolve_request_rule_payload(
    *,
    rule_bindings: list[dict[str, Any] | str] | None,
    rule_ids: list[str] | None,
    rule_domains: list[str] | None,
) -> tuple[list[str], list[str]]:
    binding_rule_ids, binding_rule_domains = _extract_rule_ids_and_domains_from_bindings(rule_bindings)
    if binding_rule_ids or binding_rule_domains or (rule_bindings is not None):
        return _resolve_rule_ids_and_domains(
            rule_ids=binding_rule_ids if binding_rule_ids else None,
            rule_domains=binding_rule_domains,
        )
    return _resolve_rule_ids_and_domains(rule_ids=rule_ids, rule_domains=rule_domains)


def _resolve_employee_rule_bindings(emp: EmployeeConfig) -> tuple[list[str], list[str], list[dict[str, str]], str]:
    raw_rule_ids = _normalize_tokens(getattr(emp, "rule_ids", []) or [])
    raw_rule_domains = _normalize_tokens(getattr(emp, "rule_domains", []) or [])
    by_id, by_domain = _build_rule_lookup()
    bindings: list[dict[str, str]] = []

    if raw_rule_ids:
        for rule_id in raw_rule_ids:
            rule = by_id.get(rule_id)
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
        _, normalized_domains = _resolve_rule_ids_and_domains(rule_ids=raw_rule_ids, rule_domains=raw_rule_domains)
        return raw_rule_ids, normalized_domains, bindings, "rule_ids"

    seen_ids: set[str] = set()
    inferred_ids: list[str] = []
    for domain in raw_rule_domains:
        key = _normalize_domain(domain)
        for rule in by_domain.get(key, []):
            rid = str(getattr(rule, "id", "") or "").strip()
            if not rid or rid in seen_ids:
                continue
            seen_ids.add(rid)
            inferred_ids.append(rid)
            bindings.append(
                {
                    "id": rid,
                    "title": str(getattr(rule, "title", "") or ""),
                    "domain": str(getattr(rule, "domain", "") or ""),
                }
            )
    return inferred_ids, raw_rule_domains, bindings, "rule_domains_legacy"


def _serialize_employee_payload(
    emp: EmployeeConfig,
    auth_payload: dict | None = None,
) -> dict[str, Any]:
    payload = dict(vars(emp))
    payload.pop("rule_ids", None)
    payload.pop("rule_domains", None)
    skill_names: list[str] = []
    for skill_id in payload.get("skills", []) or []:
        sid = str(skill_id or "").strip()
        if not sid:
            continue
        skill = skill_store.get(sid)
        name = str(getattr(skill, "name", "") or "").strip() if skill else ""
        skill_names.append(name or sid)
    payload["skill_names"] = skill_names
    _rule_ids, _rule_domains, rule_bindings, _rule_binding_mode = _resolve_employee_rule_bindings(emp)
    payload["rule_bindings"] = rule_bindings
    payload.update(ownership_payload(emp, auth_payload))
    return payload


def _remove_employee_project_memberships(employee_id: str) -> list[str]:
    remover = getattr(project_store, "remove_employee_from_all_projects", None)
    if callable(remover):
        removed = remover(employee_id)
        return [str(project_id or "").strip() for project_id in removed if str(project_id or "").strip()]

    removed_project_ids: list[str] = []
    for project in project_store.list_all():
        project_id = str(getattr(project, "id", "") or "").strip()
        if not project_id:
            continue
        if project_store.remove_member(project_id, employee_id):
            removed_project_ids.append(project_id)
    return removed_project_ids


def _cleanup_employee_chat_settings(employee_id: str, project_ids: list[str] | None = None) -> list[str]:
    cleaned_project_ids: list[str] = []
    targets = project_ids if project_ids is not None else [project.id for project in project_store.list_all()]
    for project_id in targets:
        pid = str(project_id or "").strip()
        if not pid:
            continue
        project = project_store.get(pid)
        if project is None:
            continue
        chat_settings = dict(getattr(project, "chat_settings", {}) or {})
        selected_ids = [
            str(item or "").strip()
            for item in (chat_settings.get("selected_employee_ids") or [])
            if str(item or "").strip()
        ]
        selected_id = str(chat_settings.get("selected_employee_id") or "").strip()
        next_selected_ids = [item for item in selected_ids if item != employee_id]
        next_selected_id = "" if selected_id == employee_id else selected_id
        if next_selected_id and next_selected_id not in next_selected_ids:
            next_selected_ids.append(next_selected_id)
        if next_selected_ids == selected_ids and next_selected_id == selected_id:
            continue
        chat_settings["selected_employee_ids"] = next_selected_ids
        chat_settings["selected_employee_id"] = next_selected_id
        project.chat_settings = chat_settings
        project.updated_at = _now_iso()
        project_store.save(project)
        cleaned_project_ids.append(pid)
    return cleaned_project_ids


def _scan_skill_entries(skill) -> tuple[int, list[str]]:
    package_dir = str(getattr(skill, "package_dir", "") or "").strip()
    if not package_dir:
        return 0, []
    package_path = Path(package_dir)
    if not package_path.is_absolute():
        package_path = get_project_root() / package_path
    package_path = package_path.resolve()
    if not package_path.exists() or not package_path.is_dir():
        return 0, []

    entries: list[str] = []
    for base_dir in ("tools", "scripts"):
        root = package_path / base_dir
        if not root.exists():
            continue
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in _TOOL_SUFFIXES:
                continue
            rel = file.relative_to(package_path).as_posix()
            entries.append(rel)
    return len(entries), entries[:8]


def _format_manual_skill_item(
    skill_id: str,
    name: str,
    description: str,
    *,
    entry_count: int = 0,
    sample_entries: list[str] | None = None,
    list_tool_name: str,
    invoke_tool_name: str,
    employee_id: str = "",
) -> str:
    normalized_skill_id = str(skill_id or "").strip() or str(name or "").strip() or "unknown-skill"
    normalized_name = str(name or "").strip() or normalized_skill_id
    normalized_description = str(description or "").strip() or "未提供描述"
    entry_examples = "、".join(f"`{item}`" for item in (sample_entries or []) if str(item or "").strip()) or "无"
    match_parts = []
    if employee_id:
        match_parts.append(f'`employee_id="{employee_id}"`')
    match_parts.append(f'`skill_id="{normalized_skill_id}"`')
    invoke_args = [f'"tool_name": "<从 {list_tool_name} 返回结果里选出的 tool_name>"']
    if employee_id:
        invoke_args.append(f'"employee_id": "{employee_id}"')
    invoke_args.append('"args": { "...": "..." }')
    invoke_example = ", ".join(invoke_args)
    return (
        f"#### {normalized_name} (`{normalized_skill_id}`)\n"
        f"- 描述：{normalized_description}\n"
        f"- 可执行入口数量：{entry_count}\n"
        f"- 可执行入口示例：{entry_examples}\n"
        f"- MCP 查看详情：先调用 `{list_tool_name}`，在返回结果中按 {' + '.join(match_parts)} 匹配该技能对应的 `tool_name`、`entry_name`、`description`\n"
        f"- MCP 调用示例：`{invoke_tool_name}({{{invoke_example}}})`\n"
        "- 手册写作要求：必须补出“何时使用这个技能”的触发条件，并基于上面的 MCP 查询/调用路径给出至少 1 个最小使用案例"
    )


def _format_manual_rule_index(
    rule_bindings: list[dict[str, str]],
    *,
    query_tool_name: str,
    employee_id: str = "",
) -> str:
    grouped: dict[str, list[dict[str, str]]] = {}
    for item in rule_bindings:
        domain = str(item.get("domain", "") or "").strip() or "未分类"
        grouped.setdefault(domain, []).append(item)
    if not grouped:
        return "无"

    sections: list[str] = []
    for domain in sorted(grouped):
        items = grouped[domain]
        lines = [
            f"- {str(rule.get('title', '') or '').strip() or str(rule.get('id', '') or '').strip() or '未命名规则'} (`{str(rule.get('id', '') or '').strip() or 'unknown-rule'}`)"
            for rule in items
        ]
        query_parts = ['keyword="<规则标题关键词>"']
        if employee_id:
            query_parts.append(f'employee_id="{employee_id}"')
        sections.append(
            "\n".join(
                [
                    f"#### {domain}",
                    *lines,
                    (
                        f"- MCP 获取详情：调用 `{query_tool_name}({', '.join(query_parts)})`，"
                        "再以返回结果中的 `id`、`title`、`content` 作为最终依据"
                    ),
                ]
            )
        )
    return "\n\n".join(sections)


def _format_rule_domain_summary(rule_bindings: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {}
    for item in rule_bindings:
        domain = str(item.get("domain", "") or "").strip() or "未分类"
        grouped.setdefault(domain, []).append(item)
    if not grouped:
        return "无"

    lines: list[str] = []
    for domain in sorted(grouped):
        items = grouped[domain]
        labels = [
            f"{str(rule.get('title', '') or '').strip() or str(rule.get('id', '') or '').strip() or '未命名规则'} (`{str(rule.get('id', '') or '').strip() or 'unknown-rule'}`)"
            for rule in items
        ]
        lines.append(f"- {domain}：{'；'.join(labels)}")
    return "\n".join(lines)


def _build_employee_draft_catalog_context() -> str:
    skills_text = []
    for skill in [item for item in skill_store.list_all() if _is_reusable_employee_skill(item)][:80]:
        skill_id = str(getattr(skill, "id", "") or "").strip()
        name = str(getattr(skill, "name", "") or skill_id).strip()
        description = str(getattr(skill, "description", "") or "").strip()
        line = f"- {name}"
        if description:
            line += f"：{description[:120]}"
        if skill_id and skill_id != name:
            line += f" (ID: {skill_id})"
        skills_text.append(line)

    rules_text = []
    for rule in rule_store.list_all()[:120]:
        rule_id = str(getattr(rule, "id", "") or "").strip()
        title = str(getattr(rule, "title", "") or rule_id).strip()
        domain = str(getattr(rule, "domain", "") or "").strip()
        line = f"- {title}"
        if domain:
            line += f" / 领域: {domain}"
        if rule_id and rule_id != title:
            line += f" (ID: {rule_id})"
        rules_text.append(line)

    return (
        "可复用技能目录（仅供参考，优先返回最匹配的技能名称或 ID）：\n"
        + ("\n".join(skills_text) if skills_text else "- 暂无技能")
        + "\n\n可复用规则目录（仅供参考，优先返回最匹配的 rule_domains 或规则标题）：\n"
        + ("\n".join(rules_text) if rules_text else "- 暂无规则")
    )


def _is_reusable_employee_skill(skill: Skill) -> bool:
    tags = {
        _normalize_match_key(tag)
        for tag in (getattr(skill, "tags", None) or ())
        if _normalize_match_key(tag)
    }
    return not bool(tags & {"employee-draft", "system-mcp", _SYSTEM_MCP_SKILL_TAG})


def _match_skill_ids_from_hints(skill_hints: list[str] | None) -> tuple[list[str], list[str]]:
    hints = _normalize_text_list(skill_hints, limit=20, item_limit=160)
    if not hints:
        return [], []
    catalog = [skill for skill in skill_store.list_all() if _is_reusable_employee_skill(skill)]
    matched_ids: list[str] = []
    unmatched_hints: list[str] = []
    seen_skill_ids: set[str] = set()
    for hint in hints:
        target = _normalize_match_key(hint)
        if not target:
            continue
        matched_skill = next(
            (
                skill for skill in catalog
                if _normalize_match_key(getattr(skill, "id", "")) == target
                or _normalize_match_key(getattr(skill, "name", "")) == target
            ),
            None,
        )
        if matched_skill is None:
            matched_skill = next(
                (
                    skill for skill in catalog
                    if any(
                        text and target in text
                        for text in (
                            _normalize_match_key(getattr(skill, "id", "")),
                            _normalize_match_key(getattr(skill, "name", "")),
                        )
                    )
                ),
                None,
            )
        skill_id = str(getattr(matched_skill, "id", "") or "").strip() if matched_skill else ""
        if not skill_id:
            unmatched_hints.append(hint)
            continue
        if skill_id in seen_skill_ids:
            continue
        seen_skill_ids.add(skill_id)
        matched_ids.append(skill_id)
    return matched_ids, unmatched_hints


def _match_rule_bindings_from_draft(
    *,
    rule_ids: list[str] | None,
    rule_titles: list[str] | None,
    rule_domains: list[str] | None,
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    catalog = rule_store.list_all()
    by_id = {
        str(getattr(rule, "id", "") or "").strip(): rule
        for rule in catalog
        if str(getattr(rule, "id", "") or "").strip()
    }
    bindings: list[dict[str, str]] = []
    unmatched_titles: list[str] = []
    unmatched_domains: list[str] = []
    seen_rule_ids: set[str] = set()

    def add_rule(rule_obj: Any) -> bool:
        rule_id = str(getattr(rule_obj, "id", "") or "").strip()
        if not rule_id or rule_id in seen_rule_ids:
            return False
        seen_rule_ids.add(rule_id)
        bindings.append(
            {
                "id": rule_id,
                "title": str(getattr(rule_obj, "title", "") or "").strip(),
                "domain": str(getattr(rule_obj, "domain", "") or "").strip(),
            }
        )
        return True

    for rule_id in _normalize_text_list(rule_ids, limit=30, item_limit=160):
        rule = by_id.get(rule_id)
        if rule is not None:
            add_rule(rule)

    for title in _normalize_text_list(rule_titles, limit=30, item_limit=160):
        target = _normalize_match_key(title)
        if not target:
            continue
        rule = next(
            (
                item for item in catalog
                if _normalize_match_key(getattr(item, "title", "")) == target
                or target in _normalize_match_key(getattr(item, "title", ""))
            ),
            None,
        )
        if rule is None:
            unmatched_titles.append(title)
            continue
        add_rule(rule)

    for domain in _normalize_text_list(rule_domains, limit=20, item_limit=120):
        target = _normalize_domain(domain)
        if not target:
            continue
        matched_any = False
        for rule in catalog:
            if _normalize_domain(getattr(rule, "domain", "")) != target:
                continue
            matched_any = True
            add_rule(rule)
        if not matched_any:
            unmatched_domains.append(domain)

    return bindings, unmatched_titles, unmatched_domains


def _allocate_generated_skill_id(name: str) -> str:
    base = _slugify_token(name)
    if not base:
        return skill_store.new_id()
    candidate = f"draft-skill-{base}"
    suffix = 2
    while skill_store.get(candidate) is not None:
        candidate = f"draft-skill-{base}-{suffix}"
        suffix += 1
    return candidate


def _allocate_generated_rule_title(employee_name: str, title_hint: str, domain_hint: str) -> str:
    title = _normalize_text_value(title_hint, limit=120)
    if title:
        return title
    domain = _normalize_text_value(domain_hint, limit=80)
    if domain:
        return f"{employee_name} · {domain} 执行规则"
    return f"{employee_name} · 通用执行规则"


def _write_generated_skill_package(
    *,
    skill_id: str,
    name: str,
    description: str,
    goal: str,
    style_hints: list[str],
) -> str:
    package_path = skill_store.package_path(skill_id)
    package_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "description": description,
        "version": "1.0.0",
        "tags": ["auto-generated", "employee-draft"],
        "mcp_service": "",
    }
    (package_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    skill_doc = [
        "---",
        f"name: {name}",
        f"description: {description or name}",
        "---",
        "",
        f"# {name}",
        "",
        "## Purpose",
        description or f"自动生成的员工草稿技能：{name}",
        "",
        "## Goal",
        goal or "承接员工草稿中的能力建议，后续可继续补充工具和资源。",
        "",
        "## Style Hints",
        *([f"- {item}" for item in style_hints] or ["- 暂无额外风格提示"]),
    ]
    (package_path / "SKILL.md").write_text("\n".join(skill_doc).strip() + "\n", encoding="utf-8")
    project_root = get_project_root()
    try:
        return str(package_path.relative_to(project_root))
    except ValueError:
        return str(package_path)


def _create_generated_skill(
    *,
    hint: str,
    employee_name: str,
    description: str,
    goal: str,
    style_hints: list[str],
    created_by: str,
) -> Skill:
    skill_name = _normalize_text_value(hint, limit=120) or f"{employee_name} 补充技能"
    skill_description = _normalize_text_value(
        description or f"为员工 {employee_name} 自动补充的技能：{skill_name}",
        limit=400,
    )
    skill_id = _allocate_generated_skill_id(skill_name)
    package_dir = _write_generated_skill_package(
        skill_id=skill_id,
        name=skill_name,
        description=skill_description,
        goal=goal,
        style_hints=style_hints,
    )
    skill = Skill(
        id=skill_id,
        name=skill_name,
        version="1.0.0",
        description=skill_description,
        mcp_service="",
        created_by=created_by,
        package_dir=package_dir,
        tools=(),
        resources=(),
        tags=("auto-generated", "employee-draft"),
        mcp_enabled=False,
    )
    skill_store.save(skill)
    return skill


def _allocate_system_mcp_skill_id(server_name: str) -> str:
    base = _slugify_token(server_name)
    if not base:
        return skill_store.new_id()
    candidate = f"system-mcp-{base}"
    suffix = 2
    while skill_store.get(candidate) is not None:
        candidate = f"system-mcp-{base}-{suffix}"
        suffix += 1
    return candidate


def _system_mcp_skill_description(server: dict[str, Any]) -> str:
    name = _normalize_text_value(server.get("name"), limit=120) or "system-mcp"
    tools = len(server.get("tools") or [])
    prompts = len(server.get("prompts") or [])
    resources = len(server.get("resources") or [])
    summary = _normalize_text_value(server.get("summary"), limit=180)
    base = f"导入自系统 MCP 服务 {name}，包含 tools {tools} / prompts {prompts} / resources {resources}。"
    return f"{base} {summary}".strip()[:400]


def _build_system_mcp_skill_artifacts(server: dict[str, Any]) -> tuple[tuple[ToolDef, ...], tuple[ResourceDef, ...]]:
    tools: list[ToolDef] = []
    resources: list[ResourceDef] = []
    seen_tool_names: set[str] = set()
    seen_resource_names: set[str] = set()

    for item in server.get("tools") or []:
        if not isinstance(item, dict):
            continue
        name = _normalize_text_value(item.get("name"), limit=160)
        if not name or name in seen_tool_names:
            continue
        seen_tool_names.add(name)
        tools.append(
            ToolDef(
                name=name,
                description=_normalize_text_value(item.get("description"), limit=240) or "Imported MCP tool",
            )
        )

    for item in server.get("prompts") or []:
        if not isinstance(item, dict):
            continue
        raw_name = _normalize_text_value(item.get("name"), limit=160)
        if not raw_name:
            continue
        name = f"prompt:{raw_name}"
        if name in seen_tool_names:
            continue
        seen_tool_names.add(name)
        tools.append(
            ToolDef(
                name=name,
                description=_normalize_text_value(item.get("description"), limit=240) or "Imported MCP prompt",
            )
        )

    for item in server.get("resources") or []:
        if not isinstance(item, dict):
            continue
        name = _normalize_text_value(item.get("name"), limit=160)
        if not name or name in seen_resource_names:
            continue
        seen_resource_names.add(name)
        resources.append(
            ResourceDef(
                name=name,
                description=_normalize_text_value(item.get("description"), limit=240) or "Imported MCP resource",
            )
        )
    return tuple(tools), tuple(resources)


def _write_system_mcp_skill_package(*, skill_id: str, server: dict[str, Any]) -> str:
    package_path = skill_store.package_path(skill_id)
    package_path.mkdir(parents=True, exist_ok=True)
    server_name = _normalize_text_value(server.get("name"), limit=120) or skill_id
    summary = _normalize_text_value(server.get("summary"), limit=240) or "系统 MCP 服务"
    description = _system_mcp_skill_description(server)
    manifest = {
        "name": f"系统MCP · {server_name}",
        "description": description,
        "version": "1.0.0",
        "tags": [_SYSTEM_MCP_SKILL_TAG, "employee-draft", "system-mcp"],
        "mcp_service": server_name,
    }
    (package_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    sections = [
        "---",
        f"name: 系统MCP · {server_name}",
        f"description: {description or server_name}",
        "---",
        "",
        f"# 系统MCP · {server_name}",
        "",
        "## Summary",
        summary,
        "",
        "## Source",
        f"- name: {server_name}",
        f"- url: {_normalize_text_value(server.get('url'), limit=400) or '-'}",
        f"- source: {_normalize_text_value(server.get('source'), limit=80) or '-'}",
    ]
    notice = _normalize_text_value(server.get("notice"), limit=400)
    if notice:
        sections.extend(["", "## Notice", notice])

    for heading, key in (("Tools", "tools"), ("Prompts", "prompts"), ("Resources", "resources")):
        entries = []
        for item in server.get(key) or []:
            if not isinstance(item, dict):
                continue
            name = _normalize_text_value(item.get("name"), limit=160)
            if not name:
                continue
            desc = _normalize_text_value(item.get("description"), limit=240)
            entries.append(f"- {name}" + (f": {desc}" if desc else ""))
        sections.extend(["", f"## {heading}", *(entries or ["- none"])])

    (package_path / "SKILL.md").write_text("\n".join(sections).strip() + "\n", encoding="utf-8")
    project_root = get_project_root()
    try:
        return str(package_path.relative_to(project_root))
    except ValueError:
        return str(package_path)


def _upsert_system_mcp_skill(*, server: dict[str, Any], created_by: str) -> Skill:
    server_name = _normalize_text_value(server.get("name"), limit=120)
    if not server_name:
        raise HTTPException(400, "system MCP server name is required")

    tools, resources = _build_system_mcp_skill_artifacts(server)
    description = _system_mcp_skill_description(server)
    existing = next(
        (
            item
            for item in skill_store.list_all()
            if item.mcp_service == server_name and _SYSTEM_MCP_SKILL_TAG in (item.tags or ())
        ),
        None,
    )

    skill_id = existing.id if existing else _allocate_system_mcp_skill_id(server_name)
    package_dir = _write_system_mcp_skill_package(skill_id=skill_id, server=server)
    skill_name = f"系统MCP · {server_name}"
    if existing is None:
        skill = Skill(
            id=skill_id,
            name=skill_name,
            version="1.0.0",
            description=description,
            mcp_service=server_name,
            created_by=created_by,
            package_dir=package_dir,
            tools=tools,
            resources=resources,
            tags=(_SYSTEM_MCP_SKILL_TAG, "employee-draft", "system-mcp"),
            mcp_enabled=True,
        )
    else:
        skill = Skill(
            id=existing.id,
            name=skill_name,
            version=existing.version or "1.0.0",
            description=description,
            mcp_service=server_name,
            created_by=existing.created_by or created_by,
            package_dir=package_dir,
            tools=tools,
            resources=resources,
            dependencies=existing.dependencies,
            tags=tuple(dict.fromkeys([*(existing.tags or ()), _SYSTEM_MCP_SKILL_TAG, "employee-draft", "system-mcp"])),
            mcp_enabled=True,
            created_at=existing.created_at,
            updated_at=skills_now_iso(),
        )
    skill_store.save(skill)
    return skill


def _import_selected_system_mcp_skills(server_names: list[str] | None, *, created_by: str) -> list[Skill]:
    requested_names = _normalize_text_list(server_names, limit=12, item_limit=160)
    if not requested_names:
        return []
    cfg = system_config_store.get_global()
    discovered = list_system_mcp_skills(getattr(cfg, "mcp_config", {}), timeout_sec=4)
    by_name = {
        _normalize_match_key(item.get("name")): item
        for item in discovered
        if _normalize_text_value(item.get("name"), limit=160)
    }
    imported: list[Skill] = []
    for server_name in requested_names:
        server = by_name.get(_normalize_match_key(server_name))
        if server is None:
            continue
        imported.append(_upsert_system_mcp_skill(server=server, created_by=created_by))
    return imported


def _build_employee_draft_mcp_tokens(
    *,
    name: str,
    description: str,
    goal: str,
    skills: list[str] | None,
    rule_titles: list[str] | None,
    rule_domains: list[str] | None,
    style_hints: list[str] | None,
    default_workflow: list[str] | None,
    tool_usage_policy: str,
) -> list[str]:
    raw_values = _normalize_text_list(
        [
            name,
            description,
            goal,
            *list(skills or []),
            *list(rule_titles or []),
            *list(rule_domains or []),
            *list(style_hints or []),
            *list(default_workflow or []),
            tool_usage_policy,
        ],
        limit=80,
        item_limit=240,
    )
    seen: set[str] = set()
    tokens: list[str] = []
    for value in raw_values:
        for piece in [value, *re.split(r"[\s,，。；;、/|]+", value)]:
            token = _normalize_match_key(piece)
            if not token or len(token) < 2 or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def _build_system_mcp_search_text(server: dict[str, Any]) -> str:
    values: list[str] = [
        _normalize_text_value(server.get("name"), limit=240),
        _normalize_text_value(server.get("summary"), limit=240),
        _normalize_text_value(server.get("notice"), limit=240),
    ]
    for item in server.get("skills") or []:
        if not isinstance(item, dict):
            continue
        values.extend(
            [
                _normalize_text_value(item.get("name"), limit=240),
                _normalize_text_value(item.get("description"), limit=240),
            ]
        )
    return " ".join(_normalize_text_list(values, limit=200, item_limit=240)).lower()


def _recommend_system_mcp_server_names(
    *,
    requested_names: list[str] | None,
    name: str,
    description: str,
    goal: str,
    skills: list[str] | None,
    rule_titles: list[str] | None,
    rule_domains: list[str] | None,
    style_hints: list[str] | None,
    default_workflow: list[str] | None,
    tool_usage_policy: str,
) -> list[str]:
    normalized_requested = _normalize_text_list(requested_names, limit=12, item_limit=160)
    if normalized_requested:
        return normalized_requested

    cfg = system_config_store.get_global()
    discovered = list_system_mcp_skills(getattr(cfg, "mcp_config", {}), timeout_sec=4)
    if not discovered:
        return []

    tokens = _build_employee_draft_mcp_tokens(
        name=name,
        description=description,
        goal=goal,
        skills=skills,
        rule_titles=rule_titles,
        rule_domains=rule_domains,
        style_hints=style_hints,
        default_workflow=default_workflow,
        tool_usage_policy=tool_usage_policy,
    )
    if not tokens:
        return []

    scored: list[tuple[int, int, str]] = []
    for server in discovered:
        if not isinstance(server, dict) or not bool(server.get("enabled", True)):
            continue
        server_name = _normalize_text_value(server.get("name"), limit=160)
        if not server_name:
            continue
        search_text = _build_system_mcp_search_text(server)
        if not search_text:
            continue
        score = 0
        normalized_name = _normalize_match_key(server_name)
        for token in tokens:
            if token not in search_text:
                continue
            score += 2 if len(token) >= 4 else 1
            if token == normalized_name:
                score += 2
        if score <= 0:
            continue
        skill_count = len(server.get("skills") or [])
        scored.append((score, skill_count, server_name))

    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [server_name for _, _, server_name in scored[:3]]

def _build_generated_rule_content(
    *,
    employee_name: str,
    rule_title: str,
    domain: str,
    description: str,
    goal: str,
    tone: str,
    verbosity: str,
) -> str:
    domain_text = domain or "通用"
    return (
        "规则目标:\n"
        f"- 约束员工 {employee_name} 在「{domain_text}」场景下稳定执行“{rule_title}”。\n"
        f"- 输出应围绕核心目标：{goal or description or employee_name}。\n\n"
        "执行要求:\n"
        f"- 回复语调保持 {tone or 'professional'}，信息密度保持 {verbosity or 'concise'}。\n"
        "- 先给结论，再给关键步骤或依据。\n"
        "- 如果现有技能或规则不足，应明确指出缺口，不要臆造不存在的工具能力。"
    )


def _create_generated_rule(
    *,
    employee_name: str,
    title_hint: str,
    domain_hint: str,
    description: str,
    goal: str,
    tone: str,
    verbosity: str,
    created_by: str,
) -> Rule:
    domain = _normalize_text_value(domain_hint, limit=80) or "通用"
    title = _allocate_generated_rule_title(employee_name, title_hint, domain)
    rule = Rule(
        id=rule_store.new_id(),
        domain=domain,
        title=title,
        content=_build_generated_rule_content(
            employee_name=employee_name,
            rule_title=title,
            domain=domain,
            description=description,
            goal=goal,
            tone=tone,
            verbosity=verbosity,
        ),
        severity=Severity.RECOMMENDED,
        risk_domain=RiskDomain.LOW,
        bound_employees=(),
        mcp_enabled=False,
        mcp_service="",
        created_by=created_by,
    )
    rule_store.save(rule)
    return rule


def _normalize_rule_draft_items(values: list[Any] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in values or []:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        title = _normalize_text_value(item.get("title"), limit=160)
        domain = _normalize_text_value(item.get("domain"), limit=80)
        content = _normalize_text_value(item.get("content"), limit=8000)
        source_label = _normalize_text_value(item.get("source_label"), limit=160)
        source_url = _normalize_text_value(item.get("source_url"), limit=400)
        if not title and not domain and not content:
            continue
        dedupe_key = _normalize_match_key(f"{title}|{domain}|{content[:240]}")
        if dedupe_key and dedupe_key in seen:
            continue
        if dedupe_key:
            seen.add(dedupe_key)
        normalized.append(
            {
                "title": title,
                "domain": domain,
                "content": content,
                "source_label": source_label,
                "source_url": source_url,
            }
        )
        if len(normalized) >= 20:
            break
    return normalized


def _build_system_auto_rule_drafts(
    *,
    employee_name: str,
    description: str,
    goal: str,
    skills: list[str] | None,
    rule_titles: list[str] | None,
    rule_domains: list[str] | None,
    style_hints: list[str] | None,
    default_workflow: list[str] | None,
    tool_usage_policy: str,
) -> list[dict[str, str]]:
    cfg = system_config_store.get_global()
    if not bool(getattr(cfg, "employee_auto_rule_generation_enabled", True)):
        return []

    configured_prompt = _normalize_text_value(
        getattr(cfg, "employee_auto_rule_generation_prompt", ""),
        limit=2000,
    )
    suggestions = build_external_rule_suggestions(
        name=employee_name,
        description=description,
        goal=goal,
        skills=skills,
        rule_titles=rule_titles,
        rule_domains=rule_domains,
        style_hints=[
            *_normalize_text_list(style_hints, limit=20, item_limit=240),
            *([configured_prompt] if configured_prompt else []),
        ],
        default_workflow=default_workflow,
        tool_usage_policy=tool_usage_policy,
        source_filters=getattr(
            cfg,
            "employee_auto_rule_generation_source_filters",
            ["prompts_chat_curated"],
        ),
        limit=int(getattr(cfg, "employee_auto_rule_generation_max_count", 3) or 3),
    )
    return _normalize_rule_draft_items(
        [
            {
                "title": item.get("title"),
                "domain": item.get("domain"),
                "content": item.get("content"),
                "source_label": item.get("source_label"),
                "source_url": item.get("source_url"),
            }
            for item in suggestions
        ]
    )


def _find_existing_rule_for_draft(rule_draft: dict[str, str]) -> Rule | None:
    target_title = _normalize_match_key(rule_draft.get("title"))
    target_domain = _normalize_domain(rule_draft.get("domain"))
    for item in rule_store.list_all():
        title = _normalize_match_key(getattr(item, "title", ""))
        domain = _normalize_domain(getattr(item, "domain", ""))
        if target_title and title == target_title:
            if not target_domain or not domain or domain == target_domain:
                return item
        if target_title and title and target_title in title:
            if target_domain and domain == target_domain:
                return item
    return None


def _looks_like_prompts_chat_source(rule_draft: dict[str, str]) -> bool:
    merged = " ".join(
        [
            _normalize_match_key(rule_draft.get("source_label")),
            _normalize_match_key(rule_draft.get("source_url")),
        ]
    )
    return "prompts.chat" in merged


def _create_rule_from_draft(
    *,
    employee_name: str,
    rule_draft: dict[str, str],
    description: str,
    goal: str,
    tone: str,
    verbosity: str,
    created_by: str,
) -> Rule:
    domain = _normalize_text_value(rule_draft.get("domain"), limit=80) or "通用"
    title = _allocate_generated_rule_title(
        employee_name,
        _normalize_text_value(rule_draft.get("title"), limit=160),
        domain,
    )
    content = _normalize_text_value(rule_draft.get("content"), limit=8000) or _build_generated_rule_content(
        employee_name=employee_name,
        rule_title=title,
        domain=domain,
        description=description,
        goal=goal,
        tone=tone,
        verbosity=verbosity,
    )
    rule = Rule(
        id=rule_store.new_id(),
        domain=domain,
        title=title,
        content=content,
        severity=Severity.RECOMMENDED,
        risk_domain=RiskDomain.LOW,
        bound_employees=(),
        mcp_enabled=_looks_like_prompts_chat_source(rule_draft),
        mcp_service="prompts.chat" if _looks_like_prompts_chat_source(rule_draft) else "",
        created_by=created_by,
    )
    rule_store.save(rule)
    return rule


def _create_employee_record(
    *,
    name: str,
    description: str,
    goal: str,
    skills: list[str],
    rule_bindings: list[dict[str, str]] | None,
    rule_ids: list[str] | None,
    rule_domains: list[str] | None,
    memory_scope: str,
    memory_retention_days: int,
    tone: str,
    verbosity: str,
    language: str,
    style_hints: list[str],
    default_workflow: list[str],
    tool_usage_policy: str,
    auto_evolve: bool,
    evolve_threshold: float,
    mcp_enabled: bool,
    feedback_upgrade_enabled: bool,
    auth_payload: dict | None,
) -> EmployeeConfig:
    rule_ids_resolved, rule_domains_resolved = _resolve_request_rule_payload(
        rule_bindings=rule_bindings,
        rule_ids=rule_ids,
        rule_domains=rule_domains,
    )
    normalized_name = _normalize_text_value(name, limit=120)
    if not normalized_name:
        raise HTTPException(400, "name is required")
    employee = EmployeeConfig(
        id=employee_store.new_id(),
        name=normalized_name,
        created_by=current_username(auth_payload),
        description=_normalize_text_value(description, limit=2000),
        goal=_normalize_text_value(goal, limit=2000),
        skills=_normalize_text_list(skills, limit=200, item_limit=160),
        rule_ids=rule_ids_resolved,
        rule_domains=rule_domains_resolved,
        memory_scope=memory_scope,
        memory_retention_days=memory_retention_days,
        tone=_normalize_text_value(tone, limit=40),
        verbosity=_normalize_text_value(verbosity, limit=40),
        language=_normalize_text_value(language, limit=40),
        style_hints=_normalize_text_list(style_hints, limit=20, item_limit=240),
        default_workflow=_normalize_text_list(default_workflow, limit=12, item_limit=240),
        tool_usage_policy=_normalize_text_value(tool_usage_policy, limit=2000),
        auto_evolve=auto_evolve,
        evolve_threshold=evolve_threshold,
        mcp_enabled=mcp_enabled,
        feedback_upgrade_enabled=feedback_upgrade_enabled,
    )
    employee_store.save(employee)
    return employee


@router.get("")
async def list_employees(auth_payload: dict = Depends(require_auth)):
    employees = employee_store.list_all()
    return {"employees": [_serialize_employee_payload(e, auth_payload) for e in employees]}


@router.post("")
async def create_employee(req: EmployeeCreateReq, auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.employees.create")
    rule_bindings_input = req.rule_bindings if "rule_bindings" in req.model_fields_set else None
    emp = _create_employee_record(
        name=req.name,
        description=req.description,
        goal=req.goal,
        skills=req.skills,
        rule_bindings=rule_bindings_input,
        rule_ids=req.rule_ids,
        rule_domains=req.rule_domains,
        memory_scope=req.memory_scope,
        memory_retention_days=req.memory_retention_days,
        tone=req.tone,
        verbosity=req.verbosity,
        language=req.language,
        style_hints=req.style_hints,
        default_workflow=req.default_workflow,
        tool_usage_policy=req.tool_usage_policy,
        auto_evolve=req.auto_evolve,
        evolve_threshold=req.evolve_threshold,
        mcp_enabled=req.mcp_enabled,
        feedback_upgrade_enabled=req.feedback_upgrade_enabled,
        auth_payload=auth_payload,
    )
    return {"status": "created", "employee": _serialize_employee_payload(emp, auth_payload)}


@router.post("/import-agent-templates")
async def preview_agent_templates(
    req: EmployeeAgentTemplateImportReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.employees.create")
    templates = import_agent_templates(
        source_type=req.source_type,
        source=req.source,
        subdirectory=req.subdirectory,
        branch=req.branch,
        limit=req.limit,
    )
    return {
        "templates": templates,
        "count": len(templates),
        "source_type": _normalize_text_value(req.source_type, limit=20) or "git",
        "source": _normalize_text_value(req.source, limit=1000),
        "subdirectory": _normalize_text_value(req.subdirectory, limit=400),
        "branch": _normalize_text_value(req.branch, limit=120),
    }


@router.post("/external-skill-suggestions")
async def suggest_external_skills(req: EmployeeExternalSkillSuggestReq):
    return {
        "suggestions": build_external_skill_suggestions(
            name=req.name,
            description=req.description,
            goal=req.goal,
            industry=req.industry,
            source_filters=req.source_filters,
            skills=req.skills,
            rule_titles=req.rule_titles,
            rule_domains=req.rule_domains,
            style_hints=req.style_hints,
            default_workflow=req.default_workflow,
            tool_usage_policy=req.tool_usage_policy,
        )
    }


@router.post("/external-rule-suggestions")
async def suggest_external_rules(req: EmployeeExternalRuleSuggestReq):
    return {
        "suggestions": build_external_rule_suggestions(
            name=req.name,
            description=req.description,
            goal=req.goal,
            industry=req.industry,
            source_filters=req.source_filters,
            skills=req.skills,
            rule_titles=req.rule_titles,
            rule_domains=req.rule_domains,
            style_hints=req.style_hints,
            default_workflow=req.default_workflow,
            tool_usage_policy=req.tool_usage_policy,
        )
    }


@router.post("/create-from-draft")
async def create_employee_from_draft(req: EmployeeDraftCreateReq, auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.employees.create")
    name = _normalize_text_value(req.name, limit=120)
    if not name:
        raise HTTPException(400, "name is required")

    matched_skill_ids, missing_skill_hints = _match_skill_ids_from_hints(req.skills)
    matched_rule_bindings, missing_rule_titles, missing_rule_domains = _match_rule_bindings_from_draft(
        rule_ids=req.rule_ids,
        rule_titles=req.rule_titles,
        rule_domains=req.rule_domains,
    )
    normalized_rule_drafts = _normalize_rule_draft_items(req.rule_drafts)
    created_by = current_username(auth_payload)
    created_skills: list[Skill] = []
    created_rules: list[Rule] = []
    selected_system_mcp_servers = _recommend_system_mcp_server_names(
        requested_names=req.selected_system_mcp_servers,
        name=name,
        description=req.description,
        goal=req.goal,
        skills=req.skills,
        rule_titles=req.rule_titles,
        rule_domains=req.rule_domains,
        style_hints=req.style_hints,
        default_workflow=req.default_workflow,
        tool_usage_policy=req.tool_usage_policy,
    )
    imported_system_mcp_skills = _import_selected_system_mcp_skills(
        selected_system_mcp_servers,
        created_by=created_by,
    )
    for skill in imported_system_mcp_skills:
        if skill.id not in matched_skill_ids:
            matched_skill_ids.append(skill.id)

    if req.auto_create_missing_skills:
        for hint in missing_skill_hints:
            skill = _create_generated_skill(
                hint=hint,
                employee_name=name,
                description=req.description,
                goal=req.goal,
                style_hints=req.style_hints,
                created_by=created_by,
            )
            created_skills.append(skill)
            matched_skill_ids.append(skill.id)

    if req.auto_create_missing_rules:
        normalized_rule_drafts = _normalize_rule_draft_items(
            [
                *normalized_rule_drafts,
                *_build_system_auto_rule_drafts(
                    employee_name=name,
                    description=req.description,
                    goal=req.goal,
                    skills=[
                        *_normalize_text_list(req.skills, limit=30, item_limit=160),
                        *[
                            str(getattr(skill, "name", "") or "").strip()
                            for skill in imported_system_mcp_skills
                        ],
                        *[
                            str(getattr(skill, "name", "") or "").strip()
                            for skill in created_skills
                        ],
                    ],
                    rule_titles=req.rule_titles,
                    rule_domains=req.rule_domains,
                    style_hints=req.style_hints,
                    default_workflow=req.default_workflow,
                    tool_usage_policy=req.tool_usage_policy,
                ),
            ]
        )

    if req.auto_create_missing_rules:
        for rule_draft in normalized_rule_drafts:
            existing_rule = _find_existing_rule_for_draft(rule_draft)
            if existing_rule is not None:
                matched_rule_bindings.append(
                    {
                        "id": str(getattr(existing_rule, "id", "") or "").strip(),
                        "title": str(getattr(existing_rule, "title", "") or "").strip(),
                        "domain": str(getattr(existing_rule, "domain", "") or "").strip(),
                    }
                )
                continue
            rule = _create_rule_from_draft(
                employee_name=name,
                rule_draft=rule_draft,
                description=req.description,
                goal=req.goal,
                tone=req.tone,
                verbosity=req.verbosity,
                created_by=created_by,
            )
            created_rules.append(rule)
            matched_rule_bindings.append(
                {"id": rule.id, "title": rule.title, "domain": rule.domain}
            )

        primary_domain = _normalize_text_value((req.rule_domains or [""])[0], limit=80)
        for title in missing_rule_titles:
            rule = _create_generated_rule(
                employee_name=name,
                title_hint=title,
                domain_hint=primary_domain,
                description=req.description,
                goal=req.goal,
                tone=req.tone,
                verbosity=req.verbosity,
                created_by=created_by,
            )
            created_rules.append(rule)
            matched_rule_bindings.append(
                {"id": rule.id, "title": rule.title, "domain": rule.domain}
            )
        titleless_domains = [domain for domain in missing_rule_domains if _normalize_domain(domain) != _normalize_domain(primary_domain)]
        if not missing_rule_titles and primary_domain and primary_domain not in titleless_domains:
            titleless_domains.insert(0, primary_domain)
        for domain in titleless_domains:
            rule = _create_generated_rule(
                employee_name=name,
                title_hint="",
                domain_hint=domain,
                description=req.description,
                goal=req.goal,
                tone=req.tone,
                verbosity=req.verbosity,
                created_by=created_by,
            )
            created_rules.append(rule)
            matched_rule_bindings.append(
                {"id": rule.id, "title": rule.title, "domain": rule.domain}
            )

    emp = _create_employee_record(
        name=name,
        description=req.description,
        goal=req.goal,
        skills=matched_skill_ids,
        rule_bindings=matched_rule_bindings,
        rule_ids=req.rule_ids,
        rule_domains=req.rule_domains,
        memory_scope=req.memory_scope,
        memory_retention_days=req.memory_retention_days,
        tone=req.tone,
        verbosity=req.verbosity,
        language=req.language,
        style_hints=req.style_hints,
        default_workflow=req.default_workflow,
        tool_usage_policy=req.tool_usage_policy,
        auto_evolve=req.auto_evolve,
        evolve_threshold=req.evolve_threshold,
        mcp_enabled=req.mcp_enabled,
        feedback_upgrade_enabled=req.feedback_upgrade_enabled,
        auth_payload=auth_payload,
    )
    return {
        "status": "created",
        "employee": _serialize_employee_payload(emp, auth_payload),
        "created_skills": [
            {"id": skill.id, "name": skill.name}
            for skill in created_skills
        ],
        "imported_system_mcp_skills": [
            {"id": skill.id, "name": skill.name, "mcp_service": skill.mcp_service}
            for skill in imported_system_mcp_skills
        ],
        "created_rules": [
            {"id": rule.id, "title": rule.title, "domain": rule.domain}
            for rule in created_rules
        ],
    }


@router.post("/generate-draft")
async def generate_employee_draft(
    req: EmployeeDraftGenerateReq,
    auth_payload: dict = Depends(require_auth),
):
    from services.llm_provider_service import get_llm_provider_service

    message = _normalize_text_value(req.message, limit=8000)
    if not message:
        raise HTTPException(400, "message is required")

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
        include_shared=True,
    )
    if not providers:
        raise HTTPException(400, "未配置 LLM 提供商")
    preferred_provider_id = str(req.provider_id or "").strip()
    default_provider = next((p for p in providers if p.get("is_default")), providers[0])
    provider = next(
        (item for item in providers if str(item.get("id") or "").strip() == preferred_provider_id),
        default_provider,
    )
    selected_model = str(req.model_name or "").strip() or str(provider.get("default_model") or "").strip()

    history_messages: list[dict[str, str]] = []
    for item in (req.history or [])[-6:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = _normalize_text_value(item.get("content"), limit=2000)
        if not content:
            continue
        history_messages.append({"role": role, "content": content})

    system_prompt = _normalize_text_value(
        req.system_prompt,
        limit=4000,
    ) or (
        "你是 AI 员工架构师。你的任务是根据用户描述生成一个可直接创建的 AI 员工草稿。"
        "你必须结合已有技能目录和规则目录做合理推荐。"
        "先给一句简短说明，然后必须输出一个严格 JSON 的 ```employee-draft``` 代码块。"
        "JSON 字段至少包含：name, description, goal, tone, verbosity, language, skills, "
        "rule_domains, style_hints, default_workflow, tool_usage_policy, memory_scope, memory_retention_days。"
        "如果能明确整理出可直接落地的规则，再额外输出 rule_drafts 数组，每项至少包含 title, domain, content，可选 source_label, source_url。"
        "skills 返回技能名称或技能 ID；rule_domains 返回最贴近的规则领域；不要输出额外解释性 JSON。"
    )

    user_prompt = (
        f"用户需求：\n{message}\n\n"
        f"{_build_employee_draft_catalog_context()}\n\n"
        "请优先推荐最适合当前需求的技能和规则领域。"
        "如果用户没有明确说明，也请补足合理的风格提示和默认工作流。"
        "如果你从外部提示词、技能模板或最佳实践中提炼出了明确规则，请输出到 rule_drafts。"
    )

    try:
        result = await llm_service.chat_completion(
            provider_id=provider["id"],
            model_name=selected_model or "gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                *history_messages,
                {"role": "user", "content": user_prompt},
            ],
            temperature=float(req.temperature if req.temperature is not None else 0.3),
            max_tokens=2400,
            timeout=60,
        )
        content = str(result.get("content") or "").strip()
    except Exception as exc:
        raise HTTPException(500, f"生成员工草稿失败: {str(exc)}")

    if not content:
        raise HTTPException(500, "模型未返回员工草稿内容")

    return {
        "status": "success",
        "content": content,
        "provider": provider["name"],
        "model": selected_model or "gpt-4",
    }


@router.get("/{employee_id}/config-test")
async def test_employee_config(employee_id: str):
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    skill_checks = []
    blocking_issues = []
    warning_issues = []
    skills_available = 0
    executable_skills = 0

    for skill_id in emp.skills or []:
        skill = skill_store.get(skill_id)
        if skill is None:
            skill_checks.append(
                {
                    "skill_id": skill_id,
                    "name": skill_id,
                    "status": "missing",
                    "entry_count": 0,
                    "sample_entries": [],
                    "message": "技能不存在或已删除",
                }
            )
            blocking_issues.append(f"技能缺失: {skill_id}")
            continue

        skills_available += 1
        entry_count, sample_entries = _scan_skill_entries(skill)
        if entry_count > 0:
            executable_skills += 1
            status = "ok"
            message = "技能脚本可执行"
        else:
            status = "warning"
            message = "未发现 tools/scripts 可执行脚本"
            warning_issues.append(f"技能无可执行脚本: {skill_id}")

        skill_checks.append(
            {
                "skill_id": skill.id,
                "name": skill.name,
                "status": status,
                "entry_count": entry_count,
                "sample_entries": sample_entries,
                "message": message,
            }
        )

    rule_ids, effective_domains, _bindings, rule_binding_mode = _resolve_employee_rule_bindings(emp)
    all_rules = rule_store.list_all()
    rule_by_id = {str(getattr(item, "id", "") or "").strip(): item for item in all_rules}
    rule_id_checks = []
    matched_rule_ids = 0
    for rule_id in rule_ids:
        rule = rule_by_id.get(rule_id)
        if rule is None:
            rule_id_checks.append(
                {
                    "rule_id": rule_id,
                    "status": "missing",
                    "title": "",
                    "domain": "",
                    "message": "规则不存在或已删除",
                }
            )
            blocking_issues.append(f"规则缺失: {rule_id}")
            continue
        matched_rule_ids += 1
        rule_id_checks.append(
            {
                "rule_id": rule_id,
                "status": "ok",
                "title": str(getattr(rule, "title", "") or ""),
                "domain": str(getattr(rule, "domain", "") or ""),
                "message": "规则可用",
            }
        )

    domain_checks = []
    matched_domains = 0
    total_matched_rules = 0

    for domain in effective_domains:
        key = _normalize_domain(domain)
        matched = [r for r in all_rules if _normalize_domain(r.domain) == key]
        total_matched_rules += len(matched)
        if matched:
            matched_domains += 1
            status = "ok"
            message = f"匹配 {len(matched)} 条规则"
        else:
            status = "missing"
            message = "该领域未匹配到规则"
            blocking_issues.append(f"规则领域无匹配: {domain}")

        domain_checks.append(
            {
                "domain": domain,
                "status": status,
                "matched_rule_count": len(matched),
                "sample_titles": [r.title for r in matched[:3]],
                "message": message,
            }
        )

    if not (emp.skills or []):
        warning_issues.append("员工未绑定任何技能")
    if not rule_ids and not effective_domains:
        warning_issues.append("员工未绑定任何规则（rule_ids 或 rule_domains）")

    is_healthy = len(blocking_issues) == 0
    overall_status = "healthy" if is_healthy else "failed"
    if is_healthy and warning_issues:
        overall_status = "warning"

    return {
        "employee_id": emp.id,
        "employee_name": emp.name,
        "summary": {
            "overall_status": overall_status,
            "is_healthy": is_healthy,
            "skills_total": len(emp.skills or []),
            "skills_available": skills_available,
            "skills_executable": executable_skills,
            "rule_binding_mode": rule_binding_mode,
            "rule_ids_total": len(rule_ids),
            "rule_ids_matched": matched_rule_ids,
            "rule_domains_total": len(effective_domains),
            "rule_domains_matched": matched_domains,
            "rules_total_matched": total_matched_rules,
        },
        "rule_ids": rule_id_checks,
        "skills": skill_checks,
        "rule_domains": domain_checks,
        "blocking_issues": blocking_issues,
        "warning_issues": warning_issues,
    }


@router.get("/{employee_id}")
async def get_employee(employee_id: str, auth_payload: dict = Depends(require_auth)):
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")
    return {"employee": _serialize_employee_payload(emp, auth_payload)}


def _apply_employee_update(employee_id: str, req: EmployeeUpdateReq, auth_payload: dict | None = None):
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")
    _assert_can_manage_employee_action(emp, auth_payload, "员工", "button.employees.update")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "employee": _serialize_employee_payload(emp, auth_payload)}

    rule_bindings_input = updates.pop("rule_bindings", None) if "rule_bindings" in updates else None
    rule_ids_input = updates.pop("rule_ids", None) if "rule_ids" in updates else None
    rule_domains_input = updates.pop("rule_domains", None) if "rule_domains" in updates else None
    if rule_bindings_input is not None:
        resolved_rule_ids, resolved_rule_domains = _resolve_request_rule_payload(
            rule_bindings=rule_bindings_input,
            rule_ids=None,
            rule_domains=None,
        )
        emp.rule_ids = resolved_rule_ids
        emp.rule_domains = resolved_rule_domains
    elif rule_ids_input is not None or rule_domains_input is not None:
        if rule_ids_input is None and rule_domains_input is not None:
            source_rule_ids = None
        else:
            source_rule_ids = rule_ids_input if rule_ids_input is not None else getattr(emp, "rule_ids", [])
        source_rule_domains = rule_domains_input if rule_domains_input is not None else emp.rule_domains
        resolved_rule_ids, resolved_rule_domains = _resolve_request_rule_payload(
            rule_bindings=None,
            rule_ids=source_rule_ids,
            rule_domains=source_rule_domains,
        )
        emp.rule_ids = resolved_rule_ids
        emp.rule_domains = resolved_rule_domains

    if "name" in updates:
        updates["name"] = _normalize_text_value(updates["name"], limit=120)
        if not updates["name"]:
            raise HTTPException(400, "name is required")
    if "description" in updates:
        updates["description"] = _normalize_text_value(updates["description"], limit=2000)
    if "goal" in updates:
        updates["goal"] = _normalize_text_value(updates["goal"], limit=2000)
    if "skills" in updates:
        updates["skills"] = _normalize_text_list(updates["skills"], limit=200, item_limit=160)
    if "tone" in updates:
        updates["tone"] = _normalize_text_value(updates["tone"], limit=40)
    if "verbosity" in updates:
        updates["verbosity"] = _normalize_text_value(updates["verbosity"], limit=40)
    if "language" in updates:
        updates["language"] = _normalize_text_value(updates["language"], limit=40)
    if "style_hints" in updates:
        updates["style_hints"] = _normalize_text_list(updates["style_hints"], limit=20, item_limit=240)
    if "default_workflow" in updates:
        updates["default_workflow"] = _normalize_text_list(updates["default_workflow"], limit=12, item_limit=240)
    if "tool_usage_policy" in updates:
        updates["tool_usage_policy"] = _normalize_text_value(updates["tool_usage_policy"], limit=2000)

    for field_name, val in updates.items():
        setattr(emp, field_name, val)
    emp.updated_at = _now_iso()
    employee_store.save(emp)
    return {"status": "updated", "employee": _serialize_employee_payload(emp, auth_payload)}


@router.put("/{employee_id}")
async def update_employee(employee_id: str, req: EmployeeUpdateReq, auth_payload: dict = Depends(require_auth)):
    return _apply_employee_update(employee_id, req, auth_payload)


@router.patch("/{employee_id}")
async def patch_employee(employee_id: str, req: EmployeeUpdateReq, auth_payload: dict = Depends(require_auth)):
    return _apply_employee_update(employee_id, req, auth_payload)


@router.post("/{employee_id}")
async def update_employee_compat(
    employee_id: str,
    req: EmployeeUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    """兼容部分工具默认使用 POST 调试更新接口。"""
    return _apply_employee_update(employee_id, req, auth_payload)


@router.delete("/{employee_id}")
async def delete_employee(employee_id: str, auth_payload: dict = Depends(require_auth)):
    employee = employee_store.get(employee_id)
    if employee is None:
        raise HTTPException(404, f"Employee {employee_id} not found")
    _assert_can_manage_employee_action(employee, auth_payload, "员工", "button.employees.delete")
    if not employee_store.delete(employee_id):
        raise HTTPException(404, f"Employee {employee_id} not found")
    removed_project_ids = _remove_employee_project_memberships(employee_id)
    cleaned_project_ids = _cleanup_employee_chat_settings(employee_id, removed_project_ids)
    return {
        "status": "deleted",
        "employee_id": employee_id,
        "removed_project_member_count": len(removed_project_ids),
        "removed_project_ids": removed_project_ids,
        "cleaned_project_chat_settings_count": len(cleaned_project_ids),
        "cleaned_project_chat_settings_ids": cleaned_project_ids,
    }


@router.post("/{employee_id}/mcp-test")
async def test_employee_mcp(employee_id: str):
    """测试员工 MCP 配置完整性"""
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    if not emp.mcp_enabled:
        return {
            "status": "disabled",
            "message": "员工 MCP 未开启",
            "mcp_enabled": False,
        }

    issues = []
    if not (emp.skills or []):
        issues.append("未绑定技能")
    rule_ids, rule_domains, _bindings, _mode = _resolve_employee_rule_bindings(emp)
    if not rule_ids and not rule_domains:
        issues.append("未绑定规则")

    skill_count = len(emp.skills or [])
    rule_count = len(rule_ids)
    rule_domain_count = len(rule_domains)

    if issues:
        return {
            "status": "warning",
            "message": f"MCP 已开启，但配置不完整: {', '.join(issues)}",
            "mcp_enabled": True,
            "skill_count": skill_count,
            "rule_count": rule_count,
            "rule_domain_count": rule_domain_count,
        }

    return {
        "status": "success",
        "message": f"MCP 配置完整：{skill_count} 个技能，{rule_count} 条规则，{rule_domain_count} 个规则领域",
        "mcp_enabled": True,
        "skill_count": skill_count,
        "rule_count": rule_count,
        "rule_domain_count": rule_domain_count,
    }



def _build_employee_manual_payload(employee_id: str) -> dict[str, Any]:
    """构建员工使用手册正文。"""
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    bound_skills = []
    for skill_id in emp.skills or []:
        skill = skill_store.get(skill_id)
        if skill:
            entry_count, sample_entries = _scan_skill_entries(skill)
            bound_skills.append(
                {
                    "id": skill_id,
                    "name": skill.name,
                    "description": skill.description or "",
                    "entry_count": entry_count,
                    "sample_entries": sample_entries,
                }
            )
            continue
        bound_skills.append(
            {
                "id": skill_id,
                "name": skill_id,
                "description": "",
                "entry_count": 0,
                "sample_entries": [],
            }
        )

    skills_text = (
        "\n\n".join(
            _format_manual_skill_item(
                str(item["id"]),
                str(item["name"]),
                str(item["description"]),
                entry_count=int(item.get("entry_count", 0) or 0),
                sample_entries=list(item.get("sample_entries") or []),
                list_tool_name="list_employee_proxy_tools",
                invoke_tool_name="invoke_employee_skill_tool",
            )
            for item in bound_skills
        )
        if bound_skills
        else "无"
    )
    _rule_ids, rule_domains, rule_bindings, _rule_mode = _resolve_employee_rule_bindings(emp)
    rules_text = _format_manual_rule_index(
        rule_bindings,
        query_tool_name="query_employee_rules",
    ) if rule_bindings else "无"
    domains_text = _format_rule_domain_summary(rule_bindings) if rule_bindings else "无"
    style_hints_text = "\n".join(f"- {h}" for h in (emp.style_hints or [])) if emp.style_hints else "无"
    workflow_text = "\n".join(f"- {item}" for item in (emp.default_workflow or [])) if (emp.default_workflow or []) else "无"

    manual = f"""# {emp.name} 使用手册

## 员工总览

- **员工 ID**：`{emp.id}`
- **员工名称**：{emp.name}
- **员工描述**：{emp.description or "AI 开发助手"}
- **核心目标**：{emp.goal or "未设置"}
- **语调**：{emp.tone}
- **风格**：{emp.verbosity}
- **语言**：{emp.language}

### 适用场景
- 适用于当前员工主责范围内的实现、排查、设计、评审、重构和技术选型任务。
- 适用于需要结合既有规则、项目记忆和员工技能做出工程化决策的场景。
- 不适用于明显超出当前员工能力边界的任务；遇到不匹配任务必须转交项目层处理。

### 强制执行流程
1. 收到用户提问后，先整理问题记录：问题原文、问题摘要、检索关键词。
2. 识别任务类型，并判断是否属于当前员工职责范围。
3. 若属于当前员工职责范围，先调用 `get_employee_runtime_context`、`recall_employee_memory`。
4. 每次有效对话都必须记录到员工记忆；当前宿主系统已接入自动记录链路，若当前入口未覆盖自动记录，则在本轮结束后立即调用 `save_employee_memory` 补记。
5. 再调用 `query_employee_rules` 和 `list_employee_proxy_tools`，先搜索匹配的规则与技能。
6. 锁定匹配项后，才调用 `invoke_employee_skill_tool`。
7. 如需沉淀结构化结论、排查经验或关键决策，在自动记录之外显式调用 `save_employee_memory` 追加一条可复用记忆。
8. 发现稳定性问题、规则缺口或实现缺陷时，再调用 `submit_feedback_bug`。

### 问题记录格式
```text
【问题记录】
- 问题原文：<用户原始提问>
- 问题摘要：<一句话归纳>
- 检索关键词：<3-5个关键词>
```

### 类型判断格式
```text
【类型判断】
- 任务类型：<类型名称>
- 处理归属：<当前员工处理 | 转交项目层>
- 判断依据：<命中的技能/规则领域或不匹配原因>
```

### 转交建议格式
```text
【转交建议】
- 建议动作：转项目层处理
- 原因：当前员工能力与任务类型不匹配
- 下一步：在项目层执行“任务类型识别 -> 自动分配员工 -> 写入并检索记忆”
```

## 核心工具说明

- **`get_employee_runtime_context`**：获取员工运行时上下文，先确认技能、规则、风格、记忆范围，再决定是否继续。
- **`recall_employee_memory`**：按问题摘要或关键词检索员工历史记忆；适用于延续上下文、避免重复踩坑。
- **`save_employee_memory`**：手动补记稳定结论、关键决策和排查经验；当当前入口未自动记录或需要追加结构化沉淀时必须调用。
- **`query_employee_rules`**：按关键词查询员工绑定规则；规则领域只用于索引，最终必须以 `id`、`title`、`content` 为准。
- **`list_employee_proxy_tools`**：列出当前员工可直接调用的技能工具；先搜索匹配项，再决定是否调用。
- **`invoke_employee_skill_tool`**：调用员工技能工具；只有锁定 `tool_name` 后才执行。
- **`submit_feedback_bug`**：提交结构化反馈工单；用于沉淀规则缺口、稳定性问题或工具异常。

## 员工能力清单

### 绑定技能
{skills_text}

### 规则索引（领域仅用于分组，引用时必须带标题和 ID）
{rules_text}

### 规则领域概览（仅用于快速筛选，不可替代具体规则）
{domains_text}

### 风格提示
{style_hints_text}

### 默认工作流
{workflow_text}

### 工具使用策略
{emp.tool_usage_policy or "无"}

### 记忆配置
- **作用域**：{emp.memory_scope}
- **保留期**：{emp.memory_retention_days}天

## 推荐工作流

```text
1. 问题登记（记录问题原文/摘要/关键词）
2. 类型识别与归属判断（当前员工处理 / 转交项目层）
3. 员工上下文检查 → get_employee_runtime_context
4. 记忆检索（仅当前员工处理时）→ recall_employee_memory
5. 每次对话记录 → 默认走自动记录；未覆盖入口则立刻 save_employee_memory 补记
6. 先搜索匹配的规则与技能 → query_employee_rules + list_employee_proxy_tools
7. 锁定匹配项后再调用技能 → invoke_employee_skill_tool
8. 结构化沉淀结论 → save_employee_memory
9. 反馈闭环 → submit_feedback_bug（如已启用）
```

### 记忆调用示例
```json
recall_employee_memory({{
  "query": "<问题摘要或关键词组合>"
}})
```

```json
save_employee_memory({{
  "content": "问题：<问题摘要>\\n结论：<最终方案>\\n关键决策：<需要沉淀的信息>",
  "project_name": "<当前项目名>"
}})
```

## 常见问题与故障排查

### Q1：记忆检索无结果
- 先检查问题摘要和关键词是否过泛。
- 优先使用业务实体、模块名、报错关键字重新检索。
- 如仍无结果，可继续按规则检索和技能检索流程处理，并在形成稳定结论后补记忆。

### Q2：规则查询返回多条结果
- 优先选与当前任务关键词最贴近的规则标题。
- 再比较 `domain`、`id`、`content`，不要只凭领域名判断。
- 多条都相关时，以约束更强、更新更明确的规则优先。

### Q3：技能调用参数错误
- 先用 `list_employee_proxy_tools` 确认 `tool_name` 是否真实存在。
- 再核对调用参数结构，避免臆造字段。
- 工具不存在时，不要强行调用，改为转交或仅给分析建议。

### Q4：反馈提交失败
- 检查必填字段是否齐全。
- 确认当前环境启用了反馈能力。
- 仅在问题可复现且具备可行动信息时提交反馈。

## 最佳实践

### 参数规范
- 调用记忆时，`query` 应来自问题摘要或检索关键词。
- 调用技能前，必须先通过 `list_employee_proxy_tools` 确认 `tool_name`。
- 查询规则时，先用标题关键词匹配，再读取具体 `content`。

### 记忆管理
- 每次有效对话都要留下员工记忆；自动记录未覆盖时，必须手动补记。
- 结构化结论、关键决策和可复用经验建议额外补一条高质量记忆。
- 若本轮内容明显无效、失败或噪音过高，可跳过追加结构化记忆，但不能误写错误结论。
- 保存内容要尽量结构化，方便后续检索与复用。

### 规则遵循
- 开发、排查、设计前先检索规则。
- 规则领域只是索引，最终必须回到具体规则正文。
- 如规则不适配当前问题，说明原因并考虑提交反馈。

### 技能使用
- 先搜索匹配技能，再决定是否调用。
- 有直接代理工具时优先走工具；没有代理工具时，将技能作为分析框架和输出约束使用。
- 涉及数据结构、接口数据、脏数据核验或联调排查时优先考虑 `db-query (db-query)`。

### 事实边界
- 当前宿主系统已接入对话记忆自动记录链路；若当前入口未覆盖自动记录，仍需显式调用 `save_employee_memory`。
- 不得臆造不存在的 `skill_id`、`tool_name`、`rule_id` 或规则正文。
- 手册面向接入方 AI 平台时，默认按显式工具调用描述。
"""

    return {
        "status": "success",
        "manual": manual,
        "template": manual,
        "employee_id": emp.id,
        "employee_name": emp.name,
    }


@router.get("/{employee_id}/manual-template")
async def get_manual_template(employee_id: str):
    """获取员工使用手册正文。"""
    return _build_employee_manual_payload(employee_id)
