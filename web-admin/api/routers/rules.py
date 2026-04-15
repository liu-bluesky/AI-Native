"""规则管理路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from dataclasses import replace

from core.ownership import (
    assert_can_manage_record,
    can_view_record,
    current_username,
    normalize_share_scope,
    normalize_shared_usernames,
    ownership_payload,
)
from core.deps import employee_store, ensure_permission, project_store, require_auth
from stores.json.employee_store import _now_iso
from stores.mcp_bridge import rule_store, serialize_rule, Rule, Severity, RiskDomain, rules_now_iso
from models.requests import RuleUsageReq, RuleCreateReq, RuleUpdateReq

def _require_rules_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.rules")


router = APIRouter(
    prefix="/api/rules",
    dependencies=[Depends(require_auth), Depends(_require_rules_permission)],
)


def _normalize_tokens(values: list[str] | tuple[str, ...] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values or []:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _normalize_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _rule_domains_from_ids(rule_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    domains: list[str] = []
    for rid in _normalize_tokens(rule_ids):
        rule = rule_store.get(rid)
        if rule is None:
            continue
        domain = str(getattr(rule, "domain", "") or "").strip()
        key = _normalize_domain(domain)
        if not key or key in seen:
            continue
        seen.add(key)
        domains.append(domain)
    return domains


def _employees_having_rule(rule_id: str) -> list[str]:
    target = str(rule_id or "").strip()
    if not target:
        return []
    matched: list[str] = []
    for emp in employee_store.list_all():
        rule_ids = _normalize_tokens(getattr(emp, "rule_ids", []) or [])
        if target in rule_ids:
            matched.append(str(getattr(emp, "id", "") or ""))
    return [item for item in matched if item]


def _existing_employee_ids() -> set[str]:
    return {
        str(getattr(emp, "id", "") or "").strip()
        for emp in employee_store.list_all()
        if str(getattr(emp, "id", "") or "").strip()
    }


def _sanitize_bound_employees(values: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized = _normalize_tokens(values or [])
    valid_ids = _existing_employee_ids()
    return [eid for eid in normalized if eid in valid_ids]


def _visible_employee_map(auth_payload: dict | None) -> dict[str, str]:
    if not isinstance(auth_payload, dict):
        return {
            str(getattr(emp, "id", "") or "").strip(): str(getattr(emp, "name", "") or "").strip()
            for emp in employee_store.list_all()
            if str(getattr(emp, "id", "") or "").strip()
        }
    return {
        str(getattr(emp, "id", "") or "").strip(): str(getattr(emp, "name", "") or "").strip()
        for emp in employee_store.list_all()
        if str(getattr(emp, "id", "") or "").strip() and can_view_record(emp, auth_payload)
    }


def _rule_shared_via_employees(rule: Rule, auth_payload: dict | None) -> list[dict[str, str]]:
    visible_employees = _visible_employee_map(auth_payload)
    items: list[dict[str, str]] = []
    for employee_id in _employees_having_rule(rule.id):
        if employee_id not in visible_employees:
            continue
        items.append({"id": employee_id, "name": visible_employees.get(employee_id) or employee_id})
    return items


def _projects_having_rule(rule_id: str) -> list[dict[str, str]]:
    target = str(rule_id or "").strip()
    if not target:
        return []
    items: list[dict[str, str]] = []
    for project in project_store.list_all():
        project_rule_ids = _normalize_tokens(getattr(project, "experience_rule_ids", []) or [])
        if target not in project_rule_ids:
            continue
        project_id = str(getattr(project, "id", "") or "").strip()
        if not project_id:
            continue
        items.append(
            {
                "id": project_id,
                "name": str(getattr(project, "name", "") or "").strip() or project_id,
            }
        )
    return items


def _is_project_experience_rule(rule: Rule | None) -> bool:
    if rule is None:
        return False
    domain = str(getattr(rule, "domain", "") or "").strip()
    title = str(getattr(rule, "title", "") or "").strip()
    return domain == "项目经验" and title.startswith("经验卡片 · ")


def _rule_system_source(rule: Rule | None) -> str:
    if rule is None:
        return ""
    domain = str(getattr(rule, "domain", "") or "").strip()
    title = str(getattr(rule, "title", "") or "").strip()
    if domain == "项目经验" or title.startswith("经验卡片 · "):
        return "project_experience"
    if domain == "开发经验" or title.startswith("开发经验 · "):
        return "development_experience"
    return ""


def _is_managed_experience_rule(rule: Rule | None) -> bool:
    return _rule_system_source(rule) in {"project_experience", "development_experience"}


def _should_exclude_from_general_rule_list(rule: Rule | None) -> bool:
    return _is_managed_experience_rule(rule)


def _can_view_rule(rule: Rule, auth_payload: dict | None) -> bool:
    if not isinstance(auth_payload, dict):
        return True
    if can_view_record(rule, auth_payload):
        return True
    return bool(_rule_shared_via_employees(rule, auth_payload))


def _ensure_rule_view_access(rule: Rule | None, auth_payload: dict | None) -> Rule:
    if rule is None:
        raise HTTPException(404, "Rule not found")
    if not isinstance(auth_payload, dict):
        return rule
    if not _can_view_rule(rule, auth_payload):
        raise HTTPException(404, f"Rule {rule.id} not found")
    return rule


def _sync_rule_to_employee_bindings(rule_id: str, target_employee_ids: list[str]) -> None:
    target = str(rule_id or "").strip()
    if not target:
        return
    target_set = set(_normalize_tokens(target_employee_ids))
    for emp in employee_store.list_all():
        emp_id = str(getattr(emp, "id", "") or "").strip()
        if not emp_id:
            continue
        current_ids = _normalize_tokens(getattr(emp, "rule_ids", []) or [])
        current_set = set(current_ids)
        should_bind = emp_id in target_set
        changed = False
        if should_bind and target not in current_set:
            current_ids.append(target)
            changed = True
        if not should_bind and target in current_set:
            current_ids = [rid for rid in current_ids if rid != target]
            changed = True
        if not changed:
            continue
        emp.rule_ids = current_ids
        emp.rule_domains = _rule_domains_from_ids(current_ids)
        emp.updated_at = _now_iso()
        employee_store.save(emp)


def _remove_rule_from_all_employees(rule_id: str) -> None:
    target = str(rule_id or "").strip()
    if not target:
        return
    for emp in employee_store.list_all():
        current_ids = _normalize_tokens(getattr(emp, "rule_ids", []) or [])
        if target not in current_ids:
            continue
        next_ids = [rid for rid in current_ids if rid != target]
        emp.rule_ids = next_ids
        emp.rule_domains = _rule_domains_from_ids(next_ids)
        emp.updated_at = _now_iso()
        employee_store.save(emp)


def _refresh_employee_domains_for_rule(rule_id: str) -> None:
    target = str(rule_id or "").strip()
    if not target:
        return
    for emp in employee_store.list_all():
        current_ids = _normalize_tokens(getattr(emp, "rule_ids", []) or [])
        if target not in current_ids:
            continue
        next_domains = _rule_domains_from_ids(current_ids)
        if next_domains == list(getattr(emp, "rule_domains", []) or []):
            continue
        emp.rule_domains = next_domains
        emp.updated_at = _now_iso()
        employee_store.save(emp)


def _serialize_rule_payload(rule: Rule, auth_payload: dict | None = None) -> dict:
    payload = serialize_rule(rule)
    bound_ids = _employees_having_rule(rule.id)
    shared_via_employees = _rule_shared_via_employees(rule, auth_payload)
    source_project_bindings = _projects_having_rule(rule.id)
    system_source = _rule_system_source(rule)
    name_map = {
        str(getattr(emp, "id", "") or "").strip(): str(getattr(emp, "name", "") or "").strip()
        for emp in employee_store.list_all()
        if str(getattr(emp, "id", "") or "").strip()
    }
    payload["bound_employees"] = bound_ids
    payload["bound_employee_count"] = len(bound_ids)
    payload["bound_employee_names"] = [name_map.get(eid) or eid for eid in bound_ids]
    payload["shared_via_employees"] = shared_via_employees
    payload["source_project_bindings"] = source_project_bindings
    payload["system_managed"] = system_source == "project_experience"
    payload["system_source"] = system_source
    payload.update(ownership_payload(rule, auth_payload))
    return payload


@router.get("")
async def list_rules(auth_payload: dict = Depends(require_auth)):
    rules = [
        rule
        for rule in rule_store.list_all()
        if _can_view_rule(rule, auth_payload) and not _should_exclude_from_general_rule_list(rule)
    ]
    return {"rules": [_serialize_rule_payload(r, auth_payload) for r in rules]}


@router.get("/domains")
async def rule_domains(auth_payload: dict = Depends(require_auth)):
    domains = sorted(
        {
            str(getattr(rule, "domain", "") or "").strip()
            for rule in rule_store.list_all()
            if (
                _can_view_rule(rule, auth_payload)
                and not _should_exclude_from_general_rule_list(rule)
                and str(getattr(rule, "domain", "") or "").strip()
            )
        }
    )
    return {"domains": domains}


@router.get("/search")
async def search_rules(
    keyword: str = "",
    domain: str = None,
    auth_payload: dict = Depends(require_auth),
):
    results = [
        rule
        for rule in rule_store.query(keyword, domain)
        if _can_view_rule(rule, auth_payload) and not _should_exclude_from_general_rule_list(rule)
    ]
    return {"rules": [_serialize_rule_payload(r, auth_payload) for r in results]}


@router.get("/{rule_id}")
async def get_rule(rule_id: str, auth_payload: dict = Depends(require_auth)):
    r = _ensure_rule_view_access(rule_store.get(rule_id), auth_payload)
    return {"rule": _serialize_rule_payload(r, auth_payload)}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str, auth_payload: dict = Depends(require_auth)):
    rule = _ensure_rule_view_access(rule_store.get(rule_id), auth_payload)
    if _is_managed_experience_rule(rule):
        raise HTTPException(403, "经验规则请到项目详情中管理")
    assert_can_manage_record(rule, auth_payload, "规则")
    _remove_rule_from_all_employees(rule_id)
    if not rule_store.delete(rule_id):
        raise HTTPException(404, f"Rule {rule_id} not found")
    return {"status": "deleted", "rule_id": rule_id}


@router.post("/{rule_id}/usage")
async def record_rule_usage(rule_id: str, req: RuleUsageReq):
    rule_store.record_usage(rule_id, req.adopted)
    return {"status": "recorded"}


@router.post("")
async def create_rule(req: RuleCreateReq, auth_payload: dict = Depends(require_auth)):
    bound_employees = tuple(_sanitize_bound_employees(req.bound_employees))
    rule = Rule(
        id=rule_store.new_id(),
        domain=req.domain,
        title=req.title,
        content=req.content,
        share_scope=normalize_share_scope(req.share_scope),
        shared_with_usernames=tuple(
            normalize_shared_usernames(
                req.shared_with_usernames,
                owner_username=current_username(auth_payload),
            )
        ),
        severity=Severity(req.severity),
        risk_domain=RiskDomain(req.risk_domain),
        bound_employees=bound_employees,
        mcp_enabled=req.mcp_enabled,
        mcp_service=req.mcp_service,
        created_by=current_username(auth_payload),
    )
    rule_store.save(rule)
    _sync_rule_to_employee_bindings(rule.id, list(bound_employees))
    refreshed = rule_store.get(rule.id) or rule
    return {"status": "created", "rule": _serialize_rule_payload(refreshed, auth_payload)}


@router.put("/{rule_id}")
async def update_rule(rule_id: str, req: RuleUpdateReq, auth_payload: dict = Depends(require_auth)):
    r = _ensure_rule_view_access(rule_store.get(rule_id), auth_payload)
    if _is_managed_experience_rule(r):
        raise HTTPException(403, "经验规则请到项目详情中编辑")
    assert_can_manage_record(r, auth_payload, "规则")
    updates = req.model_dump(exclude_unset=True)
    if "share_scope" in updates:
        updates["share_scope"] = normalize_share_scope(updates["share_scope"])
    if "shared_with_usernames" in updates:
        updates["shared_with_usernames"] = tuple(
            normalize_shared_usernames(
                updates["shared_with_usernames"],
                owner_username=str(getattr(r, "created_by", "") or "").strip(),
            )
        )
    if "severity" in updates:
        updates["severity"] = Severity(updates["severity"])
    if "risk_domain" in updates:
        updates["risk_domain"] = RiskDomain(updates["risk_domain"])
    bound_employees_updated = "bound_employees" in updates and updates["bound_employees"] is not None
    if bound_employees_updated:
        updates["bound_employees"] = tuple(_sanitize_bound_employees(updates["bound_employees"]))
    domain_updated = "domain" in updates
    updates["updated_at"] = rules_now_iso()
    updated = replace(r, **updates)
    rule_store.save(updated)
    if bound_employees_updated:
        target_employees = _normalize_tokens(list(updated.bound_employees or []))
        _sync_rule_to_employee_bindings(rule_id, target_employees)
    if domain_updated:
        _refresh_employee_domains_for_rule(rule_id)
    refreshed = rule_store.get(rule_id) or updated
    return {"status": "updated", "rule": _serialize_rule_payload(refreshed, auth_payload)}
