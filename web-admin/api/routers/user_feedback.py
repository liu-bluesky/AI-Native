"""系统统一用户反馈中心路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from core.deps import (
    ensure_permission,
    is_super_admin_payload,
    project_store,
    require_auth,
)
from models.requests import (
    ProjectAnswerBugFeedbackReq,
    UserFeedbackAssignReq,
    UserFeedbackCommentReq,
    UserFeedbackCreateReq,
    UserFeedbackReplyReq,
    UserFeedbackTransitionReq,
)
from services.user_feedback_service import get_user_feedback_service


router = APIRouter()


def _actor(auth_payload: dict) -> str:
    return str(auth_payload.get("sub") or "").strip()


def _service_call(callback):
    try:
        return callback()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


def _assert_owner_or_admin(item: dict, auth_payload: dict) -> None:
    actor = _actor(auth_payload)
    if str(item.get("reporter_id") or "") == actor:
        return
    try:
        ensure_permission(auth_payload, "menu.feedback.admin")
    except HTTPException as exc:
        raise HTTPException(403, "无权查看该反馈") from exc


def _assert_project_access(project_id: str, auth_payload: dict) -> None:
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, "项目不存在")
    if is_super_admin_payload(auth_payload):
        return
    member = project_store.get_user_member(project_id, _actor(auth_payload))
    if member is None or not bool(getattr(member, "enabled", True)):
        raise HTTPException(403, "无权访问该项目")


def _validate_local_answer_feedback(req: ProjectAnswerBugFeedbackReq) -> None:
    requested_message_id = str(req.assistant_message_id or "").strip()
    answer_id = str(req.answer_id or "").strip()
    answer_snapshot = str(req.answer_snapshot or "").strip()
    chat_session_id = str(req.chat_session_id or "").strip()
    is_valid_local_answer = (
        requested_message_id.startswith("chat-local-")
        and answer_id == f"ans_{requested_message_id}"
        and bool(chat_session_id)
        and bool(answer_snapshot)
    )
    if not is_valid_local_answer:
        raise HTTPException(400, "本地回答反馈数据不完整或回答 ID 不一致")


@router.post("/api/user-feedback")
async def create_user_feedback(
    req: UserFeedbackCreateReq,
    auth_payload: dict = Depends(require_auth),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    item = _service_call(
        lambda: get_user_feedback_service().create(
            req.model_dump(),
            reporter_id=_actor(auth_payload),
            idempotency_key=idempotency_key,
        )
    )
    return {"status": "created", "item": item}


@router.post("/api/projects/{project_id}/user-feedback/from-answer")
async def create_user_feedback_from_answer(
    project_id: str,
    req: ProjectAnswerBugFeedbackReq,
    auth_payload: dict = Depends(require_auth),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    _assert_project_access(project_id, auth_payload)
    _validate_local_answer_feedback(req)
    result = _service_call(
        lambda: get_user_feedback_service().create_from_answer(
            req.model_dump(),
            reporter_id=_actor(auth_payload),
            project_id=project_id,
            idempotency_key=idempotency_key,
        )
    )
    return {"status": "created", **result}


@router.get("/api/user-feedback/mine")
async def list_my_user_feedback(
    status: str = "",
    category: str = "",
    keyword: str = "",
    auth_payload: dict = Depends(require_auth),
):
    items = get_user_feedback_service().list(
        reporter_id=_actor(auth_payload),
        filters={"status": status, "category": category, "keyword": keyword},
    )
    return {"items": items, "total": len(items)}


@router.get("/api/user-feedback/{feedback_id}")
async def get_user_feedback(feedback_id: str, auth_payload: dict = Depends(require_auth)):
    item = _service_call(lambda: get_user_feedback_service().get(feedback_id))
    _assert_owner_or_admin(item, auth_payload)
    return {"item": item}


@router.post("/api/user-feedback/{feedback_id}/comments")
async def comment_user_feedback(
    feedback_id: str,
    req: UserFeedbackCommentReq,
    auth_payload: dict = Depends(require_auth),
):
    current = _service_call(lambda: get_user_feedback_service().get(feedback_id))
    _assert_owner_or_admin(current, auth_payload)
    item = _service_call(
        lambda: get_user_feedback_service().add_comment(
            feedback_id,
            actor=_actor(auth_payload),
            content=req.content,
        )
    )
    return {"item": item}


@router.post("/api/user-feedback/{feedback_id}/reopen")
async def reopen_user_feedback(feedback_id: str, auth_payload: dict = Depends(require_auth)):
    current = _service_call(lambda: get_user_feedback_service().get(feedback_id))
    _assert_owner_or_admin(current, auth_payload)
    item = _service_call(
        lambda: get_user_feedback_service().transition(
            feedback_id,
            actor=_actor(auth_payload),
            status="processing",
        )
    )
    return {"item": item}


@router.post("/api/user-feedback/{feedback_id}/withdraw")
async def withdraw_user_feedback(feedback_id: str, auth_payload: dict = Depends(require_auth)):
    current = _service_call(lambda: get_user_feedback_service().get(feedback_id))
    _assert_owner_or_admin(current, auth_payload)
    item = _service_call(
        lambda: get_user_feedback_service().transition(
            feedback_id,
            actor=_actor(auth_payload),
            status="withdrawn",
        )
    )
    return {"item": item}


@router.get("/api/admin/user-feedback/summary")
async def summarize_user_feedback(auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.feedback.admin")
    return {"summary": get_user_feedback_service().summary()}


@router.get("/api/admin/user-feedback")
async def list_admin_user_feedback(
    status: str = "",
    category: str = "",
    priority: str = "",
    assignee_id: str = "",
    project_id: str = "",
    keyword: str = "",
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.feedback.admin")
    items = get_user_feedback_service().list(
        filters={
            "status": status,
            "category": category,
            "priority": priority,
            "assignee_id": assignee_id,
            "project_id": project_id,
            "keyword": keyword,
        }
    )
    return {"items": items, "total": len(items)}


@router.get("/api/admin/user-feedback/{feedback_id}")
async def get_admin_user_feedback(feedback_id: str, auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.feedback.admin")
    return {"item": _service_call(lambda: get_user_feedback_service().get(feedback_id))}


@router.post("/api/admin/user-feedback/{feedback_id}/assign")
async def assign_admin_user_feedback(
    feedback_id: str,
    req: UserFeedbackAssignReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.feedback.admin")
    item = _service_call(
        lambda: get_user_feedback_service().assign(
            feedback_id,
            actor=_actor(auth_payload),
            assignee_id=req.assignee_id,
        )
    )
    return {"item": item}


@router.post("/api/admin/user-feedback/{feedback_id}/transition")
async def transition_admin_user_feedback(
    feedback_id: str,
    req: UserFeedbackTransitionReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.feedback.admin")
    item = _service_call(
        lambda: get_user_feedback_service().transition(
            feedback_id,
            actor=_actor(auth_payload),
            status=req.status,
            priority=req.priority,
        )
    )
    return {"item": item}


@router.post("/api/admin/user-feedback/{feedback_id}/reply")
async def reply_admin_user_feedback(
    feedback_id: str,
    req: UserFeedbackReplyReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.feedback.admin")
    item = _service_call(
        lambda: get_user_feedback_service().reply(
            feedback_id,
            actor=_actor(auth_payload),
            content=req.content,
        )
    )
    return {"item": item}
