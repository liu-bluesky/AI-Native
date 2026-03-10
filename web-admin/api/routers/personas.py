"""人设管理路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from dataclasses import replace

from core.deps import require_auth
from stores.mcp_bridge import (
    persona_store, snapshot_store, serialize_persona,
    Persona, DecisionPolicy, DriftControl, persona_now_iso,
)
from models.requests import PersonaCreateReq, PersonaUpdateReq

router = APIRouter(prefix="/api/personas", dependencies=[Depends(require_auth)])


@router.get("")
async def list_personas():
    personas = persona_store.list_all()
    return {"personas": [serialize_persona(p) for p in personas]}


@router.get("/{persona_id}")
async def get_persona(persona_id: str):
    p = persona_store.get(persona_id)
    if p is None:
        raise HTTPException(404, f"Persona {persona_id} not found")
    return {"persona": serialize_persona(p)}


@router.get("/{persona_id}/snapshots")
async def persona_snapshots(persona_id: str):
    snaps = snapshot_store.list_by_persona(persona_id)
    return {"snapshots": [
        {"id": s.id, "persona_id": s.persona_id, "created_at": s.created_at}
        for s in snaps
    ]}


def _build_decision_policy(d: dict | None) -> DecisionPolicy:
    if not d:
        return DecisionPolicy()
    return DecisionPolicy(
        priority_order=tuple(d.get("priority_order", ())),
        risk_preference=d.get("risk_preference", "balanced"),
        uncertain_action=d.get("uncertain_action", "ask_for_confirmation"),
        forbidden_goals=tuple(d.get("forbidden_goals", ())),
    )


def _build_drift_control(d: dict | None) -> DriftControl:
    if not d:
        return DriftControl()
    return DriftControl(
        enabled=d.get("enabled", True),
        window_days=d.get("window_days", 30),
        max_drift_score=d.get("max_drift_score", 0.25),
        alert_on_drift=d.get("alert_on_drift", True),
    )


@router.post("")
async def create_persona(req: PersonaCreateReq):
    persona = Persona(
        id=persona_store.new_id(),
        name=req.name,
        tone=req.tone,
        verbosity=req.verbosity,
        language=req.language,
        behaviors=tuple(req.behaviors),
        style_hints=tuple(req.style_hints),
        decision_policy=_build_decision_policy(req.decision_policy),
        drift_control=_build_drift_control(req.drift_control),
    )
    persona_store.save(persona)
    return {"status": "created", "persona": serialize_persona(persona)}


@router.put("/{persona_id}")
async def update_persona(persona_id: str, req: PersonaUpdateReq):
    p = persona_store.get(persona_id)
    if p is None:
        raise HTTPException(404, f"Persona {persona_id} not found")
    updates = req.model_dump(exclude_unset=True)
    if "behaviors" in updates:
        updates["behaviors"] = tuple(updates["behaviors"])
    if "style_hints" in updates:
        updates["style_hints"] = tuple(updates["style_hints"])
    if "decision_policy" in updates:
        updates["decision_policy"] = _build_decision_policy(updates["decision_policy"])
    if "drift_control" in updates:
        updates["drift_control"] = _build_drift_control(updates["drift_control"])
    updates["updated_at"] = persona_now_iso()
    updated = replace(p, **updates)
    persona_store.save(updated)
    return {"status": "updated", "persona": serialize_persona(updated)}


@router.delete("/{persona_id}")
async def delete_persona(persona_id: str):
    if not persona_store.delete(persona_id):
        raise HTTPException(404, f"Persona {persona_id} not found")
    return {"status": "deleted", "persona_id": persona_id}
