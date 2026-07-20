"""系统统一用户反馈业务服务。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from core.deps import user_feedback_store, user_store
from stores.json.user_feedback_store import UserFeedbackTicket


ALLOWED_CATEGORIES = {
    "product_bug",
    "ui_experience",
    "performance_stability",
    "ai_answer",
    "ai_execution",
    "feature_request",
    "security_privacy",
    "other",
}
ALLOWED_STATUSES = {
    "submitted",
    "triaged",
    "processing",
    "waiting_user",
    "resolved",
    "closed",
    "withdrawn",
}
ALLOWED_PRIORITIES = {"low", "normal", "high", "urgent"}
ALLOWED_TRANSITIONS = {
    "submitted": {"triaged", "processing", "withdrawn"},
    "triaged": {"processing", "waiting_user", "resolved", "closed", "withdrawn"},
    "processing": {"waiting_user", "resolved", "closed", "withdrawn"},
    "waiting_user": {"processing", "resolved", "closed", "withdrawn"},
    "resolved": {"processing", "closed"},
    "closed": {"processing"},
    "withdrawn": {"processing"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserFeedbackService:
    @staticmethod
    def _event(event_type: str, actor: str, **details: Any) -> dict[str, Any]:
        return {"type": event_type, "actor": actor, "created_at": _now_iso(), **details}

    @staticmethod
    def _reporter_name(username: str) -> str:
        try:
            user = user_store.get(username)
        except (ValueError, OSError):
            user = None
        return str(getattr(user, "display_name", "") or username).strip()

    def create(
        self,
        payload: dict[str, Any],
        *,
        reporter_id: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        existing = user_feedback_store.find_idempotent(reporter_id, idempotency_key)
        if existing is not None:
            return asdict(existing)
        category = str(payload.get("category") or "").strip().lower()
        if category not in ALLOWED_CATEGORIES:
            raise ValueError("不支持的反馈类型")
        title = str(payload.get("title") or "").strip()
        description = str(payload.get("description") or "").strip()
        if not title:
            raise ValueError("请填写反馈标题")
        if not description:
            raise ValueError("请填写详细描述")
        ai_evidence = payload.get("ai_evidence") if isinstance(payload.get("ai_evidence"), dict) else {}
        if category not in {"ai_answer", "ai_execution"}:
            ai_evidence = {}
        ticket = UserFeedbackTicket(
            id=user_feedback_store.new_id(),
            reporter_id=reporter_id,
            reporter_name_snapshot=self._reporter_name(reporter_id),
            category=category,
            subcategory=payload.get("subcategory", ""),
            title=title,
            description=description,
            expected_result=payload.get("expected_result", ""),
            impact_level=payload.get("impact_level", "general"),
            frequency=payload.get("frequency", "unknown"),
            source_entry=payload.get("source_entry", "global_menu"),
            project_id=payload.get("project_id", ""),
            security_restricted=category == "security_privacy",
            context=payload.get("context") if isinstance(payload.get("context"), dict) else {},
            ai_evidence=ai_evidence,
            diagnostic_consent=(
                payload.get("diagnostic_consent")
                if isinstance(payload.get("diagnostic_consent"), dict)
                else {}
            ),
            idempotency_key=idempotency_key,
        )
        ticket.events.append(self._event("created", reporter_id, status="submitted"))
        user_feedback_store.save(ticket)
        return asdict(user_feedback_store.get(ticket.id) or ticket)

    @staticmethod
    def _compact_supervision_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        raw = snapshot if isinstance(snapshot, dict) else {}
        compact_steps: list[dict[str, Any]] = []
        for step in raw.get("steps") if isinstance(raw.get("steps"), list) else []:
            if not isinstance(step, dict):
                continue
            meta = step.get("meta") if isinstance(step.get("meta"), dict) else {}
            permission_decision = (
                meta.get("permission_decision")
                if isinstance(meta.get("permission_decision"), dict)
                else {}
            )
            compact_steps.append(
                {
                    "id": str(step.get("id") or "")[:120],
                    "type": str(step.get("type") or step.get("kind") or "")[:80],
                    "status": str(step.get("status") or step.get("phase") or "")[:40],
                    "title": str(step.get("title") or "")[:240],
                    "summary": str(step.get("summary") or step.get("detail") or "")[:1000],
                    "tool_name": str(step.get("tool_name") or meta.get("tool_name") or "")[:160],
                    "duration_ms": step.get("duration_ms") or step.get("durationMs") or 0,
                    "risk_level": str(meta.get("risk_level") or "")[:40],
                    "permission_behavior": str(
                        meta.get("permission_behavior")
                        or permission_decision.get("behavior")
                    )[:40],
                }
            )
            if len(compact_steps) >= 120:
                break
        return {
            "answer_id": str(raw.get("answer_id") or "")[:160],
            "status": str(raw.get("status") or "")[:40],
            "provider_id": str(raw.get("provider_id") or "")[:120],
            "model_name": str(raw.get("model_name") or "")[:160],
            "duration_ms": raw.get("duration_ms") or raw.get("durationMs") or 0,
            "steps": compact_steps,
            "capture_status": "available" if compact_steps else "partial",
        }

    def create_from_answer(
        self,
        payload: dict[str, Any],
        *,
        reporter_id: str,
        project_id: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        answer_id = str(payload.get("answer_id") or "").strip()
        assistant_message_id = str(payload.get("assistant_message_id") or "").strip()
        chat_session_id = str(payload.get("chat_session_id") or "").strip()
        answer_content = str(payload.get("answer_snapshot") or "").strip()
        supervision_snapshot = self._compact_supervision_snapshot(
            payload.get("supervision_snapshot") if isinstance(payload.get("supervision_snapshot"), dict) else {}
        )
        ticket = self.create(
            {
                "category": "ai_answer",
                "subcategory": "",
                "title": f"AI 回复 Bug：{answer_content[:80] or answer_id}",
                "description": str(payload.get("description") or "该回复存在问题，请结合回答和执行监管证据进行人工分析。"),
                "expected_result": str(payload.get("expected_result") or "由处理人员核对问题并给出处理结果。"),
                "impact_level": "general",
                "frequency": "unknown",
                "source_entry": "project_chat_answer",
                "project_id": str(project_id or "").strip(),
                "context": payload.get("context") if isinstance(payload.get("context"), dict) else {},
                "diagnostic_consent": {"basic_context": True, "ai_context": True},
                "ai_evidence": {
                    "answer_id": answer_id,
                    "assistant_message_id": assistant_message_id,
                    "chat_session_id": chat_session_id,
                    "answer_origin": "desktop_local",
                    "answer_snapshot": answer_content[:12000],
                    "supervision_snapshot": supervision_snapshot,
                    "capture_status": supervision_snapshot.get("capture_status", "partial"),
                },
            },
            reporter_id=reporter_id,
            idempotency_key=idempotency_key,
        )
        return {"item": ticket}

    def get(self, feedback_id: str) -> dict[str, Any]:
        ticket = user_feedback_store.get(feedback_id)
        if ticket is None:
            raise LookupError("反馈工单不存在")
        return asdict(ticket)

    def list(self, *, reporter_id: str = "", filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
        normalized = filters or {}
        items = user_feedback_store.list_all()
        result: list[dict[str, Any]] = []
        keyword = str(normalized.get("keyword") or "").strip().lower()
        for item in items:
            if reporter_id and item.reporter_id != reporter_id:
                continue
            if normalized.get("status") and item.status != normalized["status"]:
                continue
            if normalized.get("category") and item.category != normalized["category"]:
                continue
            if normalized.get("priority") and item.priority != normalized["priority"]:
                continue
            if normalized.get("assignee_id") and item.assignee_id != normalized["assignee_id"]:
                continue
            if normalized.get("project_id") and item.project_id != normalized["project_id"]:
                continue
            if keyword and keyword not in f"{item.id} {item.title} {item.description} {item.reporter_id}".lower():
                continue
            result.append(asdict(item))
        return result

    def add_comment(self, feedback_id: str, *, actor: str, content: str, internal: bool = False) -> dict[str, Any]:
        ticket = user_feedback_store.get(feedback_id)
        if ticket is None:
            raise LookupError("反馈工单不存在")
        normalized_content = str(content or "").strip()
        if not normalized_content:
            raise ValueError("评论内容不能为空")
        ticket.comments.append(
            {
                "id": f"ufc_{len(ticket.comments) + 1}",
                "actor": actor,
                "content": normalized_content[:8000],
                "internal": bool(internal),
                "created_at": _now_iso(),
            }
        )
        ticket.events.append(self._event("commented", actor, internal=bool(internal)))
        user_feedback_store.save(ticket)
        return asdict(user_feedback_store.get(feedback_id) or ticket)

    def assign(self, feedback_id: str, *, actor: str, assignee_id: str) -> dict[str, Any]:
        ticket = user_feedback_store.get(feedback_id)
        if ticket is None:
            raise LookupError("反馈工单不存在")
        ticket.assignee_id = str(assignee_id or "").strip()
        ticket.events.append(self._event("assigned", actor, assignee_id=ticket.assignee_id))
        user_feedback_store.save(ticket)
        return asdict(user_feedback_store.get(feedback_id) or ticket)

    def transition(
        self,
        feedback_id: str,
        *,
        actor: str,
        status: str,
        priority: str = "",
    ) -> dict[str, Any]:
        ticket = user_feedback_store.get(feedback_id)
        if ticket is None:
            raise LookupError("反馈工单不存在")
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in ALLOWED_STATUSES:
            raise ValueError("不支持的工单状态")
        if normalized_status != ticket.status and normalized_status not in ALLOWED_TRANSITIONS.get(ticket.status, set()):
            raise ValueError(f"不允许从 {ticket.status} 流转到 {normalized_status}")
        normalized_priority = str(priority or "").strip().lower()
        if normalized_priority and normalized_priority not in ALLOWED_PRIORITIES:
            raise ValueError("不支持的优先级")
        previous_status = ticket.status
        ticket.status = normalized_status
        if normalized_priority:
            ticket.priority = normalized_priority
        if normalized_status == "resolved":
            ticket.resolved_at = _now_iso()
        if normalized_status == "closed":
            ticket.closed_at = _now_iso()
        if normalized_status == "processing":
            ticket.closed_at = ""
        ticket.events.append(
            self._event("transitioned", actor, from_status=previous_status, to_status=normalized_status)
        )
        user_feedback_store.save(ticket)
        return asdict(user_feedback_store.get(feedback_id) or ticket)

    def reply(self, feedback_id: str, *, actor: str, content: str) -> dict[str, Any]:
        ticket = user_feedback_store.get(feedback_id)
        if ticket is None:
            raise LookupError("反馈工单不存在")
        normalized_content = str(content or "").strip()
        if not normalized_content:
            raise ValueError("回复内容不能为空")
        ticket.public_reply = normalized_content[:8000]
        ticket.comments.append(
            {
                "id": f"ufc_{len(ticket.comments) + 1}",
                "actor": actor,
                "content": ticket.public_reply,
                "internal": False,
                "created_at": _now_iso(),
            }
        )
        ticket.events.append(self._event("replied", actor))
        user_feedback_store.save(ticket)
        return asdict(user_feedback_store.get(feedback_id) or ticket)

    def summary(self) -> dict[str, Any]:
        items = user_feedback_store.list_all()
        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for item in items:
            by_status[item.status] = by_status.get(item.status, 0) + 1
            by_category[item.category] = by_category.get(item.category, 0) + 1
        return {"total": len(items), "by_status": by_status, "by_category": by_category}


_service = UserFeedbackService()


def get_user_feedback_service() -> UserFeedbackService:
    return _service
