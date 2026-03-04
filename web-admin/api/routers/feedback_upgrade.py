"""反馈驱动规则升级路由（项目级）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from deps import require_auth
from feedback_service import get_feedback_service
from llm_provider_service import get_llm_provider_service
from models.requests import (
    FeedbackAnalyzeReq,
    FeedbackBatchAnalyzeReq,
    FeedbackBugBatchDeleteReq,
    FeedbackBugCreateReq,
    FeedbackCandidatePublishReq,
    FeedbackCandidateRollbackReq,
    FeedbackCandidateReviewReq,
    FeedbackManualCandidateCreateReq,
    FeedbackProjectConfigUpdateReq,
    FeedbackReflectionConfigUpdateReq,
)

router = APIRouter(prefix="/api/projects/{project_id}/feedback")


def _assert_project_access(project_id: str, x_project_id: str | None) -> None:
    if x_project_id and x_project_id != project_id:
        raise HTTPException(403, "Project mismatch")


@router.post("/bugs")
async def create_feedback_bug(
    project_id: str,
    req: FeedbackBugCreateReq,
    auth_payload: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        bug = get_feedback_service().create_bug(
            project_id,
            req.model_dump(),
            actor=str(auth_payload.get("sub") or "unknown"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"status": "created", "bug": bug}


@router.get("/bugs")
async def list_feedback_bugs(
    project_id: str,
    employee_id: str = "",
    category: str = "",
    rule_id: str = "",
    status: str = "",
    severity: str = "",
    limit: int = 50,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    bugs = get_feedback_service().list_bugs(
        project_id=project_id,
        employee_id=employee_id,
        category=category,
        rule_id=rule_id,
        status=status,
        severity=severity,
        limit=limit,
    )
    return {"bugs": bugs}


@router.get("/bugs/summary")
async def summarize_feedback_bugs(
    project_id: str,
    employee_id: str = "",
    rule_id: str = "",
    status: str = "",
    severity: str = "",
    limit: int = 500,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    summary = get_feedback_service().summarize_bugs_by_category(
        project_id=project_id,
        employee_id=employee_id,
        rule_id=rule_id,
        status=status,
        severity=severity,
        limit=limit,
    )
    return {"summary": summary}


@router.post("/bugs/batch-delete")
async def batch_delete_feedback_bugs(
    project_id: str,
    req: FeedbackBugBatchDeleteReq,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        result = get_feedback_service().delete_bugs(
            project_id=project_id,
            feedback_ids=req.feedback_ids,
            employee_id=req.employee_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "ok", **result}


@router.get("/bugs/{feedback_id}")
async def get_feedback_bug_detail(
    project_id: str,
    feedback_id: str,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        return get_feedback_service().get_bug_detail(project_id, feedback_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/bugs/{feedback_id}")
async def delete_feedback_bug(
    project_id: str,
    feedback_id: str,
    employee_id: str = "",
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        result = get_feedback_service().delete_bug(
            project_id=project_id,
            feedback_id=feedback_id,
            employee_id=employee_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"status": "deleted", **result}


@router.post("/bugs/{feedback_id}/analyze")
async def analyze_feedback_bug(
    project_id: str,
    feedback_id: str,
    req: FeedbackAnalyzeReq | None = None,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        result = get_feedback_service().analyze_bug(
            project_id,
            feedback_id,
            analyze_options=req.model_dump() if req is not None else None,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"status": "analyzed", **result}


@router.post("/bugs/batch-analyze")
async def analyze_feedback_bugs_batch(
    project_id: str,
    req: FeedbackBatchAnalyzeReq,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        result = get_feedback_service().analyze_bugs_batch(
            project_id=project_id,
            feedback_ids=req.feedback_ids,
            analyze_options={
                "target_rule_id": req.target_rule_id,
                "provider_id": req.provider_id,
                "model_name": req.model_name,
                "temperature": req.temperature,
            },
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"status": "analyzed", **result}


@router.get("/candidates")
async def list_feedback_candidates(
    project_id: str,
    status: str = "pending",
    employee_id: str = "",
    limit: int = 50,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    candidates = get_feedback_service().list_candidates(
        project_id=project_id,
        status=status,
        employee_id=employee_id,
        limit=limit,
    )
    return {"candidates": candidates}


@router.post("/candidates/{candidate_id}/review")
async def review_feedback_candidate(
    project_id: str,
    candidate_id: str,
    req: FeedbackCandidateReviewReq,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        updated = get_feedback_service().review_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            reviewed_by=req.reviewed_by,
            action=req.action,
            comment=req.comment,
            edited_content=req.edited_content,
            edited_executable_content=req.edited_executable_content,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": updated["status"], "candidate": updated}


@router.post("/candidates/{candidate_id}/publish")
async def publish_feedback_candidate(
    project_id: str,
    candidate_id: str,
    req: FeedbackCandidatePublishReq,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        updated = get_feedback_service().publish_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            published_by=req.published_by,
            comment=req.comment,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "published", "candidate": updated}


@router.post("/candidates/{candidate_id}/rollback")
async def rollback_feedback_candidate(
    project_id: str,
    candidate_id: str,
    req: FeedbackCandidateRollbackReq,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        updated = get_feedback_service().rollback_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            rolled_back_by=req.rolled_back_by,
            comment=req.comment,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "rolled_back", "candidate": updated}


@router.post("/candidates/manual")
async def create_manual_feedback_candidate(
    project_id: str,
    req: FeedbackManualCandidateCreateReq,
    auth_payload: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        candidate = get_feedback_service().create_manual_candidate(
            project_id=project_id,
            payload=req.model_dump(),
            actor=str(auth_payload.get("sub") or "unknown"),
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "created", "candidate": candidate}


@router.get("/config")
async def get_feedback_project_config(
    project_id: str,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    return {"config": get_feedback_service().get_project_config(project_id)}


@router.get("/reflection/config")
async def get_feedback_reflection_config(
    project_id: str,
    employee_id: str,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    employee_id_value = str(employee_id or "").strip()
    if not employee_id_value:
        raise HTTPException(400, "employee_id is required")
    service = get_llm_provider_service()
    options = service.list_reflection_options()
    config = service.get_reflection_config(project_id, employee_id_value)
    return {"config": config, **options}


@router.put("/reflection/config")
async def update_feedback_reflection_config(
    project_id: str,
    req: FeedbackReflectionConfigUpdateReq,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        config = get_llm_provider_service().upsert_reflection_config(
            project_id=project_id,
            employee_id=str(req.employee_id or "").strip(),
            provider_id=str(req.provider_id or "").strip(),
            model_name=str(req.model_name or "").strip(),
            temperature=req.temperature,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "ok", "config": config}


@router.patch("/config")
async def update_feedback_project_config(
    project_id: str,
    req: FeedbackProjectConfigUpdateReq,
    _: dict = Depends(require_auth),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
):
    _assert_project_access(project_id, x_project_id)
    try:
        config = get_feedback_service().update_project_config(project_id, enabled=req.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "ok", "config": config}
