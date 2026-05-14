"""Shared assistant workflow routing and state helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.archive_workflow_state_service import (
    archive_workflow_status,
    reply_contains_structured_pending_archive,
)

_TASK_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "schedule": ("日程", "会议", "会议室", "预约", "calendar", "agenda"),
    "reminder": ("提醒", "催办", "提醒我", "待办"),
    "requirement": ("需求", "方案", "拆解", "总结", "梳理"),
    "bugfix": ("bug", "报错", "异常", "问题", "缺陷", "故障"),
    "coding": ("写代码", "改代码", "开发", "实现", "重构", "修复代码", "编码"),
    "automation": ("执行", "操作", "自动", "工作流", "mcp", "skill", "技能"),
    "docs": ("文档", "doc", "说明", "总结文档"),
    "query": ("查询", "看看", "查一下", "搜索", "检索"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def assistant_workflow_from_context(source_context: dict[str, Any] | None) -> dict[str, Any]:
    context = source_context if isinstance(source_context, dict) else {}
    workflow = context.get("assistant_workflow")
    return dict(workflow) if isinstance(workflow, dict) else {}


def with_assistant_workflow_state(
    source_context: dict[str, Any] | None,
    assistant_workflow_state: dict[str, Any] | None,
) -> dict[str, Any]:
    context = dict(source_context or {}) if isinstance(source_context, dict) else {}
    if isinstance(assistant_workflow_state, dict) and assistant_workflow_state:
        context["assistant_workflow"] = dict(assistant_workflow_state)
    else:
        context.pop("assistant_workflow", None)
    return context


def detect_assistant_task_types(user_message: str) -> list[str]:
    text = str(user_message or "").strip().lower()
    if not text:
        return ["general"]
    scored: list[tuple[int, str]] = []
    for task_type, keywords in _TASK_TYPE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in text)
        if score > 0:
            scored.append((score, task_type))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[1] for item in scored] or ["general"]


def _primary_task_type(task_types: list[str]) -> str:
    normalized = [str(item or "").strip() for item in (task_types or []) if str(item or "").strip()]
    return normalized[0] if normalized else "general"


def _requires_tooling(task_types: list[str], *, auto_use_tools: bool) -> bool:
    if auto_use_tools:
        return True
    return any(
        item in {"schedule", "reminder", "coding", "automation", "docs", "bugfix"}
        for item in task_types
    )


def _confirmation_policy(task_types: list[str]) -> str:
    if any(item in {"schedule", "reminder", "requirement", "bugfix"} for item in task_types):
        return "once_before_write"
    if any(item in {"coding", "automation"} for item in task_types):
        return "on_high_risk_only"
    return "none"


def _execution_mode(task_types: list[str], *, auto_use_tools: bool) -> str:
    if any(item in {"coding", "automation"} for item in task_types):
        return "agent_execution"
    if any(item in {"schedule", "reminder", "requirement", "bugfix"} for item in task_types):
        return "collect_then_confirm"
    if _requires_tooling(task_types, auto_use_tools=auto_use_tools):
        return "tool_augmented"
    return "direct_answer"


def build_assistant_workflow_state(
    *,
    user_message: str,
    source_context: dict[str, Any] | None = None,
    chat_surface: str = "main-chat",
    auto_use_tools: bool = True,
) -> dict[str, Any]:
    task_types = detect_assistant_task_types(user_message)
    confirmation_policy = _confirmation_policy(task_types)
    execution_mode = _execution_mode(task_types, auto_use_tools=auto_use_tools)
    status = "collecting" if confirmation_policy != "none" else "ready"
    platform = str((source_context or {}).get("platform") or "").strip().lower()
    return {
        "version": "v1",
        "task_types": task_types,
        "primary_task_type": _primary_task_type(task_types),
        "execution_mode": execution_mode,
        "confirmation_policy": confirmation_policy,
        "requires_tooling": _requires_tooling(task_types, auto_use_tools=auto_use_tools),
        "chat_surface": str(chat_surface or "main-chat").strip() or "main-chat",
        "platform": platform,
        "status": status,
        "updated_at": _now_iso(),
    }


def evolve_assistant_workflow_state(
    current_state: dict[str, Any] | None,
    *,
    reply_content: str = "",
    is_error: bool = False,
    archive_workflow_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = dict(current_state or {})
    if not state:
        return {}
    archive_status = archive_workflow_status(
        {"archive_workflow": dict(archive_workflow_state or {})}
        if isinstance(archive_workflow_state, dict) and archive_workflow_state
        else {}
    )
    if is_error:
        state["status"] = "failed"
    elif archive_status in {"pending_confirmation", "pending_write", "pending_retry", "pending_attachment"}:
        state["status"] = "pending_confirmation"
    elif archive_status in {"written", "saved", "completed"}:
        state["status"] = "done"
    elif archive_status in {"failed", "cancelled", "ignored"}:
        state["status"] = "failed"
    elif reply_contains_structured_pending_archive(reply_content):
        state["status"] = "pending_confirmation"
    elif state.get("confirmation_policy") == "none":
        state["status"] = "done"
    elif bool(state.get("confirmed_once")):
        state["status"] = "ready"
    elif any(marker in str(reply_content or "") for marker in ("请补充", "请提供", "还需要", "补充以下")):
        state["status"] = "collecting"
    else:
        state["status"] = "ready"
    state["updated_at"] = _now_iso()
    return state
