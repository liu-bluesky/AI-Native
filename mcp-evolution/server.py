"""进化引擎 MCP 服务入口"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from store import (
    CandidateStore, EventStore, UsageLogStore,
    EvolutionCandidate, EvolutionEvent, UsageLog,
    serialize_candidate, _now_iso,
)

DATA_DIR = Path(__file__).parent / "knowledge"

mcp = FastMCP("evolution-engine")
candidate_store = CandidateStore(DATA_DIR)
event_store = EventStore(DATA_DIR)
usage_log_store = UsageLogStore(DATA_DIR)

THRESHOLD_BY_RISK = {
    "low": 0.85,
    "medium": 0.90,
    "high": None,
}
MAX_PER_DAY = 5
_VALID_ACTIONS = {"approve", "edit", "reject"}
_VALID_RISK = {"low", "medium", "high"}


# ── Tools ──

@mcp.tool()
def analyze_usage_patterns(employee_id: str, limit: int = 200) -> dict:
    """分析 AI 员工的使用模式，发现进化机会"""
    logs = usage_log_store.list_by_employee(employee_id, limit=limit)
    if not logs:
        return {"employee_id": employee_id, "total_logs": 0, "patterns": {}}
    corrections = [l for l in logs if l.corrected]
    rejections = [l for l in logs if l.action == "rule_rejected"]
    rule_hits: dict[str, int] = {}
    for l in logs:
        if l.rule_id:
            rule_hits[l.rule_id] = rule_hits.get(l.rule_id, 0) + 1
    low_hit = [rid for rid, cnt in rule_hits.items() if cnt <= 1]
    return {
        "employee_id": employee_id,
        "total_logs": len(logs),
        "patterns": {
            "frequent_corrections": len(corrections),
            "rejection_count": len(rejections),
            "low_hit_rules": low_hit,
            "unique_rules_used": len(rule_hits),
        },
    }


@mcp.tool()
def propose_rule(
    employee_id: str, title: str, description: str,
    confidence: float = 0.5, risk_domain: str = "low",
    pattern_id: str = "",
) -> dict:
    """提出新规则候选"""
    if risk_domain not in _VALID_RISK:
        return {"error": f"Invalid risk_domain: {risk_domain}. Valid: {sorted(_VALID_RISK)}"}
    if not 0.0 <= confidence <= 1.0:
        return {"error": "confidence must be between 0.0 and 1.0"}
    cand = EvolutionCandidate(
        id=candidate_store.new_id(), employee_id=employee_id,
        title=title, description=description,
        pattern_id=pattern_id, confidence=confidence,
        risk_domain=risk_domain,
    )
    candidate_store.save(cand)
    event_store.save(EvolutionEvent(
        id=event_store.new_id(), employee_id=employee_id,
        event_type="candidate_created", target_id=cand.id,
    ))
    return {"status": "proposed", "candidate_id": cand.id, "confidence": confidence}


@mcp.tool()
def auto_evolve(
    employee_id: str, threshold: float = 0.8, dry_run: bool = False,
) -> dict:
    """自动进化：批量处理高置信度候选规则"""
    if not 0.0 <= threshold <= 1.0:
        return {"error": "threshold must be between 0.0 and 1.0"}
    candidates = candidate_store.list_by_employee(employee_id, status="pending")
    evolved, skipped = [], []
    budget = MAX_PER_DAY
    for c in candidates:
        if budget <= 0 and not dry_run:
            skipped.append({"candidate_id": c.id, "reason": "daily_rate_limited"})
            continue
        risk_threshold = THRESHOLD_BY_RISK.get(c.risk_domain, 0.90)
        if risk_threshold is None:
            skipped.append({"candidate_id": c.id, "reason": "high_risk_manual_only"})
            continue
        effective = max(threshold, risk_threshold)
        if c.confidence < effective:
            skipped.append({"candidate_id": c.id, "reason": "below_threshold"})
            continue
        if dry_run:
            evolved.append({"candidate_id": c.id, "title": c.title,
                            "confidence": c.confidence, "would_promote": True})
            continue
        promoted = replace(c, status="approved", updated_at=_now_iso())
        candidate_store.save(promoted)
        event_store.save(EvolutionEvent(
            id=event_store.new_id(), employee_id=employee_id,
            event_type="rule_promoted", target_id=c.id,
        ))
        budget -= 1
        evolved.append({"candidate_id": c.id, "title": c.title, "confidence": c.confidence})
    return {"evolved_count": len(evolved), "rules": evolved,
            "skipped": skipped, "dry_run": dry_run}


@mcp.tool()
def review_candidate(
    candidate_id: str, reviewed_by: str, action: str,
    edits: str = "",
) -> dict:
    """审核候选规则"""
    if action not in _VALID_ACTIONS:
        return {"error": f"Invalid action: {action}. Valid: {sorted(_VALID_ACTIONS)}"}
    c = candidate_store.get(candidate_id)
    if c is None:
        return {"error": f"Candidate {candidate_id} not found"}
    if action == "approve":
        updated = replace(c, status="approved", reviewed_by=reviewed_by, updated_at=_now_iso())
        candidate_store.save(updated)
        event_store.save(EvolutionEvent(
            id=event_store.new_id(), employee_id=c.employee_id,
            event_type="rule_promoted", target_id=c.id,
            detail={"reviewed_by": reviewed_by},
        ))
        return {"status": "approved", "candidate_id": candidate_id}
    if action == "reject":
        updated = replace(c, status="rejected", reviewed_by=reviewed_by, updated_at=_now_iso())
        candidate_store.save(updated)
        event_store.save(EvolutionEvent(
            id=event_store.new_id(), employee_id=c.employee_id,
            event_type="candidate_rejected", target_id=c.id,
        ))
        return {"status": "rejected", "candidate_id": candidate_id}
    # action == "edit"
    if not edits:
        return {"error": "edits is required when action='edit'"}
    updated = replace(c, description=edits, updated_at=_now_iso())
    candidate_store.save(updated)
    return {"status": "updated", "candidate_id": candidate_id}


@mcp.tool()
def get_evolution_report(employee_id: str) -> dict:
    """获取 AI 员工的进化报告"""
    pending = candidate_store.list_by_employee(employee_id, status="pending")
    approved = candidate_store.list_by_employee(employee_id, status="approved")
    rejected = candidate_store.list_by_employee(employee_id, status="rejected")
    events = event_store.list_by_employee(employee_id, limit=20)
    return {
        "employee_id": employee_id,
        "summary": {
            "pending_count": len(pending),
            "approved_count": len(approved),
            "rejected_count": len(rejected),
            "recent_events": len(events),
        },
        "pending_candidates": [serialize_candidate(c) for c in pending[:10]],
        "recent_events": [
            {"id": e.id, "type": e.event_type, "target": e.target_id,
             "created_at": e.created_at}
            for e in events
        ],
    }


# ── Resources ──

@mcp.resource("evolution://candidates/{employee_id}")
def evolution_candidates(employee_id: str) -> str:
    """AI 员工的进化候选队列"""
    candidates = candidate_store.list_by_employee(employee_id, status="pending")
    if not candidates:
        return f"员工 {employee_id} 暂无待审候选"
    lines = [f"[{c.id}] conf={c.confidence} risk={c.risk_domain} | {c.title}" for c in candidates]
    return "\n".join(lines)


@mcp.resource("evolution://updates/{employee_id}")
def recent_updates(employee_id: str) -> str:
    """AI 员工最近的进化更新"""
    events = event_store.list_by_employee(employee_id, limit=20)
    if not events:
        return f"员工 {employee_id} 暂无进化事件"
    lines = [f"[{e.created_at}] {e.event_type}: {e.target_id}" for e in events]
    return "\n".join(lines)


@mcp.resource("evolution://report/{employee_id}")
def evolution_report_resource(employee_id: str) -> str:
    """AI 员工的进化报告"""
    report = get_evolution_report(employee_id)
    s = report["summary"]
    return (
        f"# 进化报告: {employee_id}\n"
        f"待审: {s['pending_count']} | 已通过: {s['approved_count']} | 已拒绝: {s['rejected_count']}\n"
        f"近期事件: {s['recent_events']}"
    )


# ── Prompts ──

@mcp.prompt()
def review_evolution_suggestions(employee_id: str) -> str:
    """审核 AI 员工的进化建议"""
    return (
        f"请审核 AI 员工 {employee_id} 的进化建议。\n\n"
        "步骤：\n"
        "1. 调用 get_evolution_report 获取进化报告\n"
        "2. 分析待审核的候选规则\n"
        "3. 对每条候选规则给出审核建议（采纳/编辑/拒绝）\n"
        "4. 说明理由\n\n"
        "请开始审核。"
    )


# ── Entry Point ──

if __name__ == "__main__":
    mcp.run()