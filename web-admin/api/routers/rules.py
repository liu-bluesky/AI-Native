"""规则管理路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from dataclasses import replace

from deps import require_auth
from stores import rule_store, serialize_rule, Rule, Severity, RiskDomain, rules_now_iso
from models.requests import RuleUsageReq, RuleCreateReq, RuleUpdateReq

router = APIRouter(prefix="/api/rules", dependencies=[Depends(require_auth)])


@router.get("")
async def list_rules():
    rules = rule_store.list_all()
    return {"rules": [serialize_rule(r) for r in rules]}


@router.get("/domains")
async def rule_domains():
    return {"domains": rule_store.domains()}


@router.get("/search")
async def search_rules(keyword: str = "", domain: str = None):
    results = rule_store.query(keyword, domain)
    return {"rules": [serialize_rule(r) for r in results]}


@router.get("/{rule_id}")
async def get_rule(rule_id: str):
    r = rule_store.get(rule_id)
    if r is None:
        raise HTTPException(404, f"Rule {rule_id} not found")
    return {"rule": serialize_rule(r)}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str):
    if not rule_store.delete(rule_id):
        raise HTTPException(404, f"Rule {rule_id} not found")
    return {"status": "deleted", "rule_id": rule_id}


@router.post("/{rule_id}/usage")
async def record_rule_usage(rule_id: str, req: RuleUsageReq):
    rule_store.record_usage(rule_id, req.adopted)
    return {"status": "recorded"}


@router.post("")
async def create_rule(req: RuleCreateReq):
    rule = Rule(
        id=rule_store.new_id(),
        domain=req.domain,
        title=req.title,
        content=req.content,
        severity=Severity(req.severity),
        risk_domain=RiskDomain(req.risk_domain),
        mcp_enabled=req.mcp_enabled,
        mcp_service=req.mcp_service,
    )
    rule_store.save(rule)
    return {"status": "created", "rule": serialize_rule(rule)}


@router.put("/{rule_id}")
async def update_rule(rule_id: str, req: RuleUpdateReq):
    r = rule_store.get(rule_id)
    if r is None:
        raise HTTPException(404, f"Rule {rule_id} not found")
    updates = req.model_dump(exclude_unset=True)
    if "severity" in updates:
        updates["severity"] = Severity(updates["severity"])
    if "risk_domain" in updates:
        updates["risk_domain"] = RiskDomain(updates["risk_domain"])
    updates["updated_at"] = rules_now_iso()
    updated = replace(r, **updates)
    rule_store.save(updated)
    return {"status": "updated", "rule": serialize_rule(updated)}

