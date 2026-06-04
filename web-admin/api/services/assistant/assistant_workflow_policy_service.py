"""Shared assistant workflow policy helpers."""

from __future__ import annotations

import re
from typing import Any

from services.assistant.assistant_workflow_state_service import (
    assistant_workflow_from_context,
    build_assistant_workflow_state,
)

_CONFIRMATION_TERMS = (
    "确认",
    "好的",
    "好",
    "行",
    "可以",
    "继续",
    "继续吧",
    "开始",
    "执行",
    "提交",
    "保存",
    "写入",
    "归档",
    "创建",
    "安排",
    "发送",
    "发吧",
    "没问题",
    "是的",
    "对",
    "ok",
    "okay",
    "yes",
    "goahead",
    "proceed",
)
_BLOCKER_TERMS = (
    "为什么",
    "怎么",
    "无法",
    "失败",
    "报错",
    "不行",
    "没有",
    "未",
    "先别",
    "等等",
    "取消",
)
_FOLLOW_UP_GENERAL_TYPES = {"general", ""}
_TOOL_SOURCE_LABELS = {
    "project_skill": "现有技能代理",
    "external_mcp": "外部 MCP",
    "system_mcp": "系统 MCP",
    "local_host": "本地 CLI/命令",
    "local_connector": "本地代码连接器",
    "project_tool": "项目工具",
    "builtin": "内建工具",
}


def _normalize_text(value: Any) -> str:
    return re.sub(r"[\s，。,.!！?？:：;；'\"`~]+", "", str(value or "").strip().lower())


def looks_like_assistant_workflow_confirmation(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if any(term in normalized for term in _BLOCKER_TERMS):
        return False
    if normalized in {"1", "2", "3"}:
        return True
    return any(term in normalized for term in _CONFIRMATION_TERMS)


def latest_assistant_workflow_state_from_messages(messages: list[Any] | None) -> dict[str, Any]:
    for item in reversed(messages or []):
        source_context = (
            item.get("source_context")
            if isinstance(item, dict)
            else getattr(item, "source_context", None)
        )
        state = assistant_workflow_from_context(source_context)
        if state:
            return state
    return {}


def prepare_assistant_workflow_state(
    *,
    user_message: str,
    source_context: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    chat_surface: str = "main-chat",
    auto_use_tools: bool = True,
) -> dict[str, Any]:
    current_state = build_assistant_workflow_state(
        user_message=user_message,
        source_context=source_context,
        chat_surface=chat_surface,
        auto_use_tools=auto_use_tools,
    )
    previous = dict(previous_state or {})
    if not previous:
        return current_state

    previous_primary_type = str(previous.get("primary_task_type") or "").strip()
    current_primary_type = str(current_state.get("primary_task_type") or "").strip()
    previous_status = str(previous.get("status") or "").strip().lower()
    confirmation_policy = str(
        previous.get("confirmation_policy") or current_state.get("confirmation_policy") or ""
    ).strip()
    is_confirmation = looks_like_assistant_workflow_confirmation(user_message)

    if (
        current_primary_type in _FOLLOW_UP_GENERAL_TYPES
        and previous_primary_type not in _FOLLOW_UP_GENERAL_TYPES
    ):
        current_state["task_types"] = list(previous.get("task_types") or [previous_primary_type])
        current_state["primary_task_type"] = previous_primary_type
        current_state["execution_mode"] = str(
            previous.get("execution_mode") or current_state.get("execution_mode") or ""
        ).strip()
        current_state["confirmation_policy"] = confirmation_policy or str(
            current_state.get("confirmation_policy") or ""
        ).strip()
        current_state["requires_tooling"] = bool(
            previous.get("requires_tooling", current_state.get("requires_tooling"))
        )

    current_state["confirmed_once"] = bool(previous.get("confirmed_once"))
    current_state["confirmation_count"] = int(previous.get("confirmation_count") or 0)

    if (
        is_confirmation
        and confirmation_policy != "none"
        and previous_status in {"collecting", "pending_confirmation", "ready", "confirmed_once"}
    ):
        current_state["confirmed_once"] = True
        current_state["confirmation_count"] = max(
            1,
            int(previous.get("confirmation_count") or 0) + (0 if previous.get("confirmed_once") else 1),
        )
        current_state["status"] = "confirmed_once"
        current_state["last_user_action"] = "confirm"
        current_state["requires_tooling"] = bool(
            previous.get("requires_tooling", current_state.get("requires_tooling"))
        )
    elif bool(previous.get("confirmed_once")) and current_state.get("primary_task_type") == previous_primary_type:
        current_state["confirmed_once"] = True
        current_state["confirmation_count"] = max(1, int(previous.get("confirmation_count") or 1))

    return current_state


def build_assistant_workflow_prompt(assistant_workflow_state: dict[str, Any] | None) -> str:
    state = dict(assistant_workflow_state or {})
    if not state:
        return ""

    lines = [
        "当前共享 AI 工作流状态：",
        f"- primary_task_type: {state.get('primary_task_type') or 'general'}",
        f"- execution_mode: {state.get('execution_mode') or 'direct_answer'}",
        f"- confirmation_policy: {state.get('confirmation_policy') or 'none'}",
        f"- status: {state.get('status') or 'ready'}",
    ]
    if bool(state.get("requires_tooling")):
        lines.append("- 当前任务需要真实使用工具/技能/工作流时，应直接执行，不要只返回说明。")
    if state.get("confirmation_policy") == "once_before_write":
        lines.append("- 规则：同一轮只允许做一次有效确认；确认后除非出现新的缺失字段、附件、权限或环境阻塞，否则不要重复确认。")
    if bool(state.get("confirmed_once")):
        lines.append("- 当前状态：用户已完成本轮一次性确认。下一步应直接执行写入、创建、发送、安排、归档或后续动作，不要再次询问“是否确认”。")
    elif str(state.get("status") or "").strip().lower() in {"collecting", "pending_confirmation"}:
        lines.append("- 当前状态：只继续收集仍然缺失的关键输入；不要对已经确认过的内容重复确认。")
    return "\n".join(lines)


def build_capability_routing_prompt(tools: list[dict[str, Any]] | None) -> str:
    available_tools = [item for item in (tools or []) if isinstance(item, dict)]
    if not available_tools:
        return (
            "当前没有可直接调用的现成工具。只有在确实缺少能力时，才说明需要新增能力；"
            "不要把“新建技能”当成默认解法。"
        )

    grouped: dict[str, list[str]] = {}
    for item in available_tools:
        source = str(item.get("source") or item.get("module_type") or "").strip().lower() or "project_tool"
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            continue
        grouped.setdefault(source, [])
        if tool_name not in grouped[source]:
            grouped[source].append(tool_name)

    lines = [
        "当前任务的能力路由规则：",
        "- 优先复用当前已经可调用的 CLI、tool、skill、MCP；不要因为来了一个新需求，就默认建议“新增技能”。",
        "- 如果现有能力已经能覆盖读、写、编辑、创建、发送、查询、归档、执行等动作，就直接组合这些能力完成任务。",
        "- 只有在现有能力明确缺失，或者同一类多步流程长期高频且临时编排不稳定时，才考虑新增 workflow 或 skill 封装。",
    ]
    for source, tool_names in grouped.items():
        label = _TOOL_SOURCE_LABELS.get(source, source or "工具")
        preview = "、".join(tool_names[:8])
        suffix = " 等" if len(tool_names) > 8 else ""
        lines.append(f"- 当前可复用{label}：{preview}{suffix}")
    if grouped.get("local_host"):
        lines.append("- 发现本地 CLI/命令能力时，应优先把它当成能力底座，由 AI 负责理解需求并组合调用。")
    if grouped.get("project_skill") or grouped.get("external_mcp") or grouped.get("system_mcp"):
        lines.append("- 发现技能代理或 MCP 时，优先调用现有入口；不要把“已有能力的编排”误判成“需要新建技能”。")
    return "\n".join(lines)
