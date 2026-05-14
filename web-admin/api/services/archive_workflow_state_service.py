"""Shared archive workflow state helpers."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def reply_claims_archive_success(content: str) -> bool:
    return bool(re.search(r"已(?:归档|保存|写入)|保存到|写入完成|记录已保存", str(content or "")))


def archive_workflow_state_from_context(source_context: dict[str, Any] | None) -> dict[str, Any]:
    context = source_context if isinstance(source_context, dict) else {}
    workflow = context.get("archive_workflow")
    return dict(workflow) if isinstance(workflow, dict) else {}


def archive_workflow_status(source_context: dict[str, Any] | None) -> str:
    return str(archive_workflow_state_from_context(source_context).get("status") or "").strip().lower()


def build_archive_workflow_state(
    *,
    status: str,
    workflow_id: str = "",
    reply_content: str = "",
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = result if isinstance(result, dict) else {}
    state = {
        "status": str(status or "").strip().lower(),
        "workflow_id": str(workflow_id or payload.get("archive_key") or uuid.uuid4().hex[:12]).strip(),
        "updated_at": now_iso(),
    }
    if reply_content:
        state["reply_content"] = str(reply_content or "")
    if payload:
        state["result_status"] = str(payload.get("status") or "").strip().lower()
        for key in (
            "archive_key",
            "document_title",
            "document_id",
            "doc_id",
            "doc_url",
            "table_id",
            "record_id",
            "writer_type",
            "writer_mode",
        ):
            value = str(payload.get(key) or "").strip()
            if value:
                state[key] = value
    return state


def build_pending_archive_workflow_state(
    *,
    reply_content: str,
    workflow_id: str = "",
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_archive_workflow_state(
        status="pending_confirmation",
        workflow_id=workflow_id,
        reply_content=reply_content,
        result=result,
    )


def archive_message_reply_content(message: Any) -> str:
    source_context = getattr(message, "source_context", None)
    workflow = archive_workflow_state_from_context(source_context if isinstance(source_context, dict) else {})
    reply_content = str(workflow.get("reply_content") or "").strip()
    if reply_content:
        return reply_content
    return str(getattr(message, "content", "") or "").strip()


def reply_contains_structured_pending_archive(content: str) -> bool:
    text = str(content or "")
    return all(
        item in text
        for item in ("【待归档类型】", "【待归档状态】", "【结构化内容】")
    ) and ("尚未写入" in text or "待归档" in text or "已整理" in text)


def message_has_pending_archive_state(message: Any) -> bool:
    source_context = getattr(message, "source_context", None)
    status = archive_workflow_status(source_context if isinstance(source_context, dict) else {})
    return status in {
        "pending_confirmation",
        "pending_write",
        "pending_attachment",
        "pending_retry",
        "unconfirmed",
    }


def message_has_closed_archive_state(message: Any) -> bool:
    source_context = getattr(message, "source_context", None)
    status = archive_workflow_status(source_context if isinstance(source_context, dict) else {})
    return status in {"written", "saved", "completed", "failed", "cancelled", "ignored"}


def with_archive_workflow_state(
    source_context: dict[str, Any] | None,
    archive_workflow_state: dict[str, Any] | None,
) -> dict[str, Any]:
    context = dict(source_context or {}) if isinstance(source_context, dict) else {}
    if isinstance(archive_workflow_state, dict) and archive_workflow_state:
        context["archive_workflow"] = dict(archive_workflow_state)
    else:
        context.pop("archive_workflow", None)
    return context
