"""人设管理 MCP 服务入口"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from store import (
    PersonaStore, SnapshotStore, CorpusStore,
    Persona, PersonaSnapshot, CorpusRef,
    DecisionPolicy, DelegationScope,
    _serialize_persona, _now_iso,
)

DATA_DIR = Path(__file__).parent / "knowledge"

mcp = FastMCP("persona-service")
persona_store = PersonaStore(DATA_DIR)
snapshot_store = SnapshotStore(DATA_DIR)
corpus_store = CorpusStore(DATA_DIR)

_VALID_TONES = {"professional", "friendly", "strict", "mentor"}
_VALID_VERBOSITY = {"verbose", "concise", "minimal"}


# ── Tools ──

@mcp.tool()
def get_persona(persona_id: str) -> dict:
    """获取人设详情"""
    p = persona_store.get(persona_id)
    if p is None:
        return {"error": f"Persona {persona_id} not found"}
    return _serialize_persona(p)


@mcp.tool()
def set_tone(persona_id: str, tone: str) -> dict:
    """设置人设语气风格"""
    if tone not in _VALID_TONES:
        return {"error": f"Invalid tone: {tone}. Valid: {sorted(_VALID_TONES)}"}
    p = persona_store.get(persona_id)
    if p is None:
        return {"error": f"Persona {persona_id} not found"}
    updated = replace(p, tone=tone, updated_at=_now_iso())
    persona_store.save(updated)
    return {"status": "updated", "persona_id": persona_id, "tone": tone}


@mcp.tool()
def set_style(persona_id: str, verbosity: str = "", behaviors: str = "", style_hints: str = "") -> dict:
    """设置人设输出风格（简洁度、行为列表、风格提示）"""
    p = persona_store.get(persona_id)
    if p is None:
        return {"error": f"Persona {persona_id} not found"}
    kwargs: dict = {"updated_at": _now_iso()}
    if verbosity:
        if verbosity not in _VALID_VERBOSITY:
            return {"error": f"Invalid verbosity: {verbosity}. Valid: {sorted(_VALID_VERBOSITY)}"}
        kwargs["verbosity"] = verbosity
    if behaviors:
        kwargs["behaviors"] = tuple(b.strip() for b in behaviors.split(",") if b.strip())
    if style_hints:
        kwargs["style_hints"] = tuple(h.strip() for h in style_hints.split(",") if h.strip())
    updated = replace(p, **kwargs)
    persona_store.save(updated)
    return {"status": "updated", "persona_id": persona_id}


@mcp.tool()
def train_persona_from_corpus(
    persona_id: str, user_id: str,
    corpus_refs: str, consent_token: str,
) -> dict:
    """从授权语料训练人设（数字分身核心）"""
    if not consent_token:
        return {"error": "consent_token is required for corpus training"}
    p = persona_store.get(persona_id)
    if p is None:
        return {"error": f"Persona {persona_id} not found"}
    refs = [r.strip() for r in corpus_refs.split(",") if r.strip()]
    if not refs:
        return {"error": "corpus_refs is required"}
    saved_ids = []
    for ref in refs:
        cr = CorpusRef(
            id=corpus_store.new_id(), user_id=user_id,
            persona_id=persona_id, content_summary=ref,
            consent_token=consent_token,
        )
        corpus_store.save(cr)
        saved_ids.append(cr.id)
    return {
        "status": "training_queued",
        "persona_id": persona_id,
        "corpus_count": len(saved_ids),
        "corpus_ids": saved_ids,
    }


@mcp.tool()
def set_decision_policy(
    persona_id: str, priority_order: str = "",
    risk_preference: str = "", uncertain_action: str = "",
    forbidden_goals: str = "",
) -> dict:
    """设置决策策略"""
    p = persona_store.get(persona_id)
    if p is None:
        return {"error": f"Persona {persona_id} not found"}
    dp = p.decision_policy
    new_dp = DecisionPolicy(
        priority_order=tuple(o.strip() for o in priority_order.split(",") if o.strip()) if priority_order else dp.priority_order,
        risk_preference=risk_preference or dp.risk_preference,
        uncertain_action=uncertain_action or dp.uncertain_action,
        forbidden_goals=tuple(g.strip() for g in forbidden_goals.split(",") if g.strip()) if forbidden_goals else dp.forbidden_goals,
    )
    updated = replace(p, decision_policy=new_dp, updated_at=_now_iso())
    persona_store.save(updated)
    return {"status": "updated", "persona_id": persona_id}


@mcp.tool()
def set_delegation_scope(
    persona_id: str, auto_approve: str = "",
    require_confirmation: str = "", forbidden: str = "",
    principle: str = "",
) -> dict:
    """设置委托权限范围"""
    p = persona_store.get(persona_id)
    if p is None:
        return {"error": f"Persona {persona_id} not found"}
    ds = p.delegation_scope
    new_ds = DelegationScope(
        auto_approve=tuple(a.strip() for a in auto_approve.split(",") if a.strip()) if auto_approve else ds.auto_approve,
        require_confirmation=tuple(r.strip() for r in require_confirmation.split(",") if r.strip()) if require_confirmation else ds.require_confirmation,
        forbidden=tuple(f_.strip() for f_ in forbidden.split(",") if f_.strip()) if forbidden else ds.forbidden,
        principle=principle or ds.principle,
    )
    updated = replace(p, delegation_scope=new_ds, updated_at=_now_iso())
    persona_store.save(updated)
    return {"status": "updated", "persona_id": persona_id, "scope": "delegation"}


@mcp.tool()
def get_persona_drift(persona_id: str) -> dict:
    """检测人设漂移"""
    p = persona_store.get(persona_id)
    if p is None:
        return {"error": f"Persona {persona_id} not found"}
    snapshots = snapshot_store.list_by_persona(persona_id)
    if not snapshots:
        return {"persona_id": persona_id, "drift_score": 0.0, "detail": "no snapshots to compare"}
    latest = snapshots[0].data
    current = _serialize_persona(p)
    changed_fields = [k for k in current if k not in ("updated_at",) and current.get(k) != latest.get(k)]
    drift_score = round(len(changed_fields) / max(len(current) - 1, 1), 2)
    dc = p.drift_control
    return {
        "persona_id": persona_id, "drift_score": drift_score,
        "changed_fields": changed_fields,
        "threshold": dc.max_drift_score,
        "alert": drift_score > dc.max_drift_score and dc.alert_on_drift,
    }


@mcp.tool()
def snapshot_persona(persona_id: str) -> dict:
    """创建人设快照"""
    p = persona_store.get(persona_id)
    if p is None:
        return {"error": f"Persona {persona_id} not found"}
    snap = PersonaSnapshot(
        id=snapshot_store.new_id(),
        persona_id=persona_id,
        data=_serialize_persona(p),
    )
    snapshot_store.save(snap)
    return {"status": "snapshot_created", "snapshot_id": snap.id, "persona_id": persona_id}


@mcp.tool()
def restore_persona(snapshot_id: str) -> dict:
    """从快照恢复人设"""
    snap = snapshot_store.get(snapshot_id)
    if snap is None:
        return {"error": f"Snapshot {snapshot_id} not found"}
    from store import _deserialize_persona
    restored = _deserialize_persona(snap.data)
    restored = replace(restored, updated_at=_now_iso())
    persona_store.save(restored)
    return {"status": "restored", "persona_id": restored.id, "from_snapshot": snapshot_id}


@mcp.tool()
def evaluate_persona_alignment(persona_id: str) -> dict:
    """评估人设一致性得分"""
    p = persona_store.get(persona_id)
    if p is None:
        return {"error": f"Persona {persona_id} not found"}
    score = 0.0
    checks = []
    if p.tone in _VALID_TONES:
        score += 0.2
        checks.append("tone_valid")
    if p.verbosity in _VALID_VERBOSITY:
        score += 0.2
        checks.append("verbosity_valid")
    if p.behaviors:
        score += 0.15
        checks.append("has_behaviors")
    if p.decision_policy.priority_order:
        score += 0.15
        checks.append("has_priority_order")
    if p.delegation_scope.principle:
        score += 0.15
        checks.append("has_delegation_principle")
    if p.expertise_primary:
        score += 0.15
        checks.append("has_expertise")
    score = round(score, 2)
    updated = replace(p, alignment_score=score, updated_at=_now_iso())
    persona_store.save(updated)
    return {"persona_id": persona_id, "alignment_score": score, "checks_passed": checks}


# ── Resources ──

@mcp.resource("persona://{persona_id}")
def persona_detail(persona_id: str) -> str:
    """人设详情"""
    p = persona_store.get(persona_id)
    if p is None:
        return f"Persona {persona_id} not found"
    return (
        f"[{p.id}] {p.name}\n"
        f"tone={p.tone} verbosity={p.verbosity} lang={p.language}\n"
        f"behaviors: {', '.join(p.behaviors) or 'none'}\n"
        f"alignment: {p.alignment_score}"
    )


@mcp.resource("persona://templates")
def persona_templates() -> str:
    """可用人设模板列表"""
    personas = persona_store.list_all()
    if not personas:
        return "暂无人设模板"
    lines = [f"[{p.id}] {p.name} (tone={p.tone}, verbosity={p.verbosity})" for p in personas]
    return "\n".join(lines)


@mcp.resource("persona://{persona_id}/drift-report")
def drift_report(persona_id: str) -> str:
    """人设漂移报告"""
    result = get_persona_drift(persona_id)
    if "error" in result:
        return result["error"]
    return (
        f"Persona: {persona_id}\n"
        f"Drift Score: {result['drift_score']} (threshold: {result['threshold']})\n"
        f"Changed: {', '.join(result['changed_fields']) or 'none'}\n"
        f"Alert: {result['alert']}"
    )


@mcp.resource("persona://{persona_id}/snapshots")
def persona_snapshots(persona_id: str) -> str:
    """人设快照列表"""
    snaps = snapshot_store.list_by_persona(persona_id)
    if not snaps:
        return f"Persona {persona_id} 暂无快照"
    lines = [f"[{s.id}] created={s.created_at}" for s in snaps]
    return "\n".join(lines)


@mcp.resource("persona://{persona_id}/alignment-score")
def alignment_score(persona_id: str) -> str:
    """人设一致性得分"""
    p = persona_store.get(persona_id)
    if p is None:
        return f"Persona {persona_id} not found"
    return f"Persona {persona_id} alignment_score={p.alignment_score}"


# ── Entry Point ──

if __name__ == "__main__":
    mcp.run()