"""市场目录只读路由"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends

from core.deps import employee_store, require_auth
from stores.mcp_bridge import rule_store, skill_store

router = APIRouter(prefix="/api/market", dependencies=[Depends(require_auth)])


def _normalize_tokens(values: list[str] | tuple[str, ...] | None) -> list[str]:
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


def _normalize_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _sort_records(items: list[Any]) -> list[Any]:
    return sorted(
        items,
        key=lambda item: (
            str(getattr(item, "updated_at", "") or ""),
            str(getattr(item, "created_at", "") or ""),
            str(getattr(item, "id", "") or ""),
        ),
        reverse=True,
    )


def _build_rule_domain_map() -> dict[str, list[str]]:
    domain_map: dict[str, list[str]] = defaultdict(list)
    for rule in rule_store.list_all():
        rule_id = str(getattr(rule, "id", "") or "").strip()
        domain_key = _normalize_domain(getattr(rule, "domain", ""))
        if not rule_id or not domain_key:
            continue
        domain_map[domain_key].append(rule_id)
    return domain_map


def _resolve_employee_rule_ids(employee: Any, domain_map: dict[str, list[str]]) -> list[str]:
    explicit_rule_ids = _normalize_tokens(getattr(employee, "rule_ids", []) or [])
    if explicit_rule_ids:
        return explicit_rule_ids

    inferred_rule_ids: list[str] = []
    for domain in _normalize_tokens(getattr(employee, "rule_domains", []) or []):
        inferred_rule_ids.extend(domain_map.get(_normalize_domain(domain), []))
    return _normalize_tokens(inferred_rule_ids)


def _serialize_market_skill(skill: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(skill, "id", "") or ""),
        "name": str(getattr(skill, "name", "") or ""),
        "description": str(getattr(skill, "description", "") or ""),
        "version": str(getattr(skill, "version", "") or ""),
        "tags": _normalize_tokens(getattr(skill, "tags", []) or []),
        "tool_count": len(getattr(skill, "tools", []) or []),
        "mcp_enabled": bool(getattr(skill, "mcp_enabled", False)),
        "updated_at": str(getattr(skill, "updated_at", "") or ""),
        "created_at": str(getattr(skill, "created_at", "") or ""),
    }


def _serialize_market_employee(employee: Any) -> dict[str, Any]:
    skill_names: list[str] = []
    for skill_id in _normalize_tokens(getattr(employee, "skills", []) or []):
        skill = skill_store.get(skill_id)
        skill_name = str(getattr(skill, "name", "") or "").strip() if skill else ""
        skill_names.append(skill_name or skill_id)

    return {
        "id": str(getattr(employee, "id", "") or ""),
        "name": str(getattr(employee, "name", "") or ""),
        "description": str(getattr(employee, "description", "") or ""),
        "goal": str(getattr(employee, "goal", "") or ""),
        "tone": str(getattr(employee, "tone", "") or ""),
        "verbosity": str(getattr(employee, "verbosity", "") or ""),
        "skill_ids": _normalize_tokens(getattr(employee, "skills", []) or []),
        "skill_names": skill_names,
        "feedback_upgrade_enabled": bool(getattr(employee, "feedback_upgrade_enabled", False)),
        "updated_at": str(getattr(employee, "updated_at", "") or ""),
        "created_at": str(getattr(employee, "created_at", "") or ""),
    }


def _serialize_market_rule(rule: Any, bound_employee_names: list[str]) -> dict[str, Any]:
    severity = getattr(rule, "severity", "")
    risk_domain = getattr(rule, "risk_domain", "")
    return {
        "id": str(getattr(rule, "id", "") or ""),
        "title": str(getattr(rule, "title", "") or ""),
        "domain": str(getattr(rule, "domain", "") or ""),
        "severity": str(getattr(severity, "value", severity) or ""),
        "risk_domain": str(getattr(risk_domain, "value", risk_domain) or ""),
        "confidence": float(getattr(rule, "confidence", 0) or 0),
        "version": str(getattr(rule, "version", "") or ""),
        "bound_employee_count": len(bound_employee_names),
        "bound_employee_names": bound_employee_names,
        "updated_at": str(getattr(rule, "updated_at", "") or ""),
        "created_at": str(getattr(rule, "created_at", "") or ""),
    }


@router.get("/catalog")
async def get_market_catalog():
    rules = _sort_records(rule_store.list_all())
    employees = _sort_records(employee_store.list_all())
    skills = _sort_records(skill_store.list_all())

    rule_domain_map = _build_rule_domain_map()
    employees_by_rule: dict[str, list[str]] = defaultdict(list)
    for employee in employees:
        employee_name = str(getattr(employee, "name", "") or "").strip()
        if not employee_name:
            continue
        for rule_id in _resolve_employee_rule_ids(employee, rule_domain_map):
            employees_by_rule[rule_id].append(employee_name)

    return {
        "catalog": {
            "skills": [_serialize_market_skill(skill) for skill in skills],
            "employees": [_serialize_market_employee(employee) for employee in employees],
            "rules": [
                _serialize_market_rule(
                    rule,
                    _normalize_tokens(employees_by_rule.get(str(getattr(rule, "id", "") or "").strip(), [])),
                )
                for rule in rules
            ],
        },
        "meta": {
            "skill_count": len(skills),
            "employee_count": len(employees),
            "rule_count": len(rules),
        },
    }
