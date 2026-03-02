"""演化引擎路由"""

from __future__ import annotations

from dataclasses import asdict, replace as dc_replace

from fastapi import APIRouter, HTTPException, Depends

from deps import require_auth
from employee_store import _now_iso
from stores import (
    candidate_store, event_store, usage_log_store,
    serialize_candidate,
)
from models.requests import ReviewReq

router = APIRouter(prefix="/api/evolution", dependencies=[Depends(require_auth)])


# ── 固定路径优先，避免被 /{employee_id} 捕获 ──

@router.get("/pending")
async def global_pending_candidates(min_confidence: float = 0.0, limit: int = 50):
    candidates = candidate_store.list_pending(min_confidence, limit)
    return {"candidates": [serialize_candidate(c) for c in candidates]}


@router.post("/candidates/{candidate_id}/review")
async def review_candidate_api(candidate_id: str, req: ReviewReq):
    if req.action not in {"approve", "edit", "reject"}:
        raise HTTPException(400, f"Invalid action: {req.action}")
    c = candidate_store.get(candidate_id)
    if c is None:
        raise HTTPException(404, f"Candidate {candidate_id} not found")

    if req.action == "approve":
        updated = dc_replace(c, status="approved", reviewed_by=req.reviewed_by, updated_at=_now_iso())
        candidate_store.save(updated)
        return {"status": "approved", "candidate_id": candidate_id}

    if req.action == "reject":
        updated = dc_replace(c, status="rejected", reviewed_by=req.reviewed_by, updated_at=_now_iso())
        candidate_store.save(updated)
        return {"status": "rejected", "candidate_id": candidate_id}

    # action == "edit"
    if not req.edits:
        raise HTTPException(400, "edits is required when action='edit'")
    updated = dc_replace(c, description=req.edits, updated_at=_now_iso())
    candidate_store.save(updated)
    return {"status": "updated", "candidate_id": candidate_id}


# ── 参数路径路由 ──

@router.get("/{employee_id}/report")
async def evolution_report(employee_id: str):
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


@router.get("/{employee_id}/candidates")
async def evolution_candidates(employee_id: str):
    pending = candidate_store.list_by_employee(employee_id, status="pending")
    return {"candidates": [serialize_candidate(c) for c in pending]}


@router.get("/{employee_id}/usage")
async def evolution_usage_logs(employee_id: str, limit: int = 50):
    logs = usage_log_store.list_by_employee(employee_id, limit)
    return {"logs": [asdict(l) for l in logs]}


@router.get("/{employee_id}/patterns")
async def evolution_patterns(employee_id: str):
    logs = usage_log_store.list_by_employee(employee_id, 500)
    action_counts: dict[str, int] = {}
    rule_hits: dict[str, int] = {}
    correction_count = 0
    for l in logs:
        action_counts[l.action] = action_counts.get(l.action, 0) + 1
        if l.rule_id:
            rule_hits[l.rule_id] = rule_hits.get(l.rule_id, 0) + 1
        if l.corrected:
            correction_count += 1
    top_rules = sorted(rule_hits.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "total_logs": len(logs),
        "action_distribution": action_counts,
        "correction_rate": round(correction_count / max(len(logs), 1), 3),
        "top_rules": [{"rule_id": r, "count": c} for r, c in top_rules],
    }
