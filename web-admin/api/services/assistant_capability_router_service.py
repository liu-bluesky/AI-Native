"""Shared capability routing helpers for assistant workflows."""

from __future__ import annotations

from typing import Any

from services.runtime.tool_registry import infer_tool_source

_DEFAULT_SOURCE_ORDER = (
    "project_tool",
    "project_skill",
    "external_mcp",
    "system_mcp",
    "local_host",
    "local_connector",
    "builtin",
)
_SOURCE_PRIORITY_BY_TASK_TYPE: dict[str, tuple[str, ...]] = {
    "coding": (
        "local_connector",
        "local_host",
        "project_tool",
        "project_skill",
        "external_mcp",
        "system_mcp",
        "builtin",
    ),
    "automation": (
        "local_host",
        "local_connector",
        "project_skill",
        "project_tool",
        "external_mcp",
        "system_mcp",
        "builtin",
    ),
    "schedule": (
        "project_skill",
        "project_tool",
        "external_mcp",
        "system_mcp",
        "local_host",
        "local_connector",
        "builtin",
    ),
    "reminder": (
        "project_skill",
        "project_tool",
        "external_mcp",
        "system_mcp",
        "local_host",
        "local_connector",
        "builtin",
    ),
    "docs": (
        "project_skill",
        "project_tool",
        "external_mcp",
        "system_mcp",
        "local_host",
        "local_connector",
        "builtin",
    ),
    "requirement": (
        "project_skill",
        "project_tool",
        "local_host",
        "external_mcp",
        "system_mcp",
        "local_connector",
        "builtin",
    ),
    "bugfix": (
        "project_skill",
        "project_tool",
        "local_host",
        "external_mcp",
        "system_mcp",
        "local_connector",
        "builtin",
    ),
    "query": (
        "project_tool",
        "project_skill",
        "builtin",
        "external_mcp",
        "system_mcp",
        "local_host",
        "local_connector",
    ),
}
_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "docs": ("doc", "docs", "document", "wiki", "sheet", "slides", "文档", "云文档"),
    "schedule": ("calendar", "schedule", "agenda", "meeting", "会议", "日程", "会议室"),
    "reminder": ("remind", "reminder", "todo", "task", "提醒", "催办", "待办"),
    "archive": ("archive", "record", "base", "bitable", "归档", "记录", "写入", "保存", "需求", "bug"),
    "query": ("query", "search", "list", "get", "read", "lookup", "查询", "搜索", "查看", "读取"),
    "write": ("write", "update", "edit", "append", "insert", "create", "save", "send", "run", "execute", "写入", "编辑", "更新", "创建", "保存", "发送", "执行"),
    "coding": ("code", "connector", "workspace", "shell", "command", "file", "patch", "git", "npm", "python", "代码", "命令", "工作区"),
    "cli": ("cli", "shell", "command", "terminal", "命令", "终端"),
}
_TAG_PRIORITY_BY_TASK_TYPE: dict[str, tuple[str, ...]] = {
    "coding": ("coding", "cli", "write", "query"),
    "automation": ("cli", "write", "query", "coding"),
    "schedule": ("schedule", "reminder", "write", "query"),
    "reminder": ("reminder", "schedule", "write", "query"),
    "docs": ("docs", "write", "query"),
    "requirement": ("archive", "write", "docs", "query"),
    "bugfix": ("archive", "write", "docs", "query"),
    "query": ("query", "docs", "schedule", "archive", "write"),
}
_WRITE_FIRST_TASK_TYPES = {"schedule", "reminder", "requirement", "bugfix", "docs"}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def infer_tool_tags(item: dict[str, Any]) -> list[str]:
    source = infer_tool_source(item)
    tool_name = _normalize_text(item.get("tool_name"))
    description = _normalize_text(item.get("description"))
    text = f"{tool_name} {description}".strip()
    tags: set[str] = set()
    for tag, keywords in _TAG_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    if source == "local_host":
        tags.update({"cli", "coding", "write"})
    if source == "local_connector":
        tags.update({"coding", "query"})
    if source in {"external_mcp", "system_mcp"}:
        tags.add("query")
    if not tags:
        tags.add("query")
    return sorted(tags)


def _resolve_source_order(primary_task_type: str) -> list[str]:
    return list(
        _SOURCE_PRIORITY_BY_TASK_TYPE.get(
            str(primary_task_type or "").strip(),
            _DEFAULT_SOURCE_ORDER,
        )
    )


def _resolve_tag_order(
    primary_task_type: str,
    *,
    confirmed_once: bool,
    confirmation_policy: str,
) -> list[str]:
    task_type = str(primary_task_type or "").strip()
    base = list(_TAG_PRIORITY_BY_TASK_TYPE.get(task_type, ("query", "write", "docs")))
    if confirmed_once and confirmation_policy == "once_before_write" and task_type in _WRITE_FIRST_TASK_TYPES:
        for tag in ("archive", "write", "schedule", "reminder", "docs"):
            if tag in base:
                base.remove(tag)
                base.insert(0, tag)
    return base


def build_capability_routing_decision(
    tools: list[dict[str, Any]] | None,
    *,
    assistant_workflow: dict[str, Any] | None = None,
    chat_surface: str = "",
) -> dict[str, Any]:
    workflow = dict(assistant_workflow or {})
    primary_task_type = str(workflow.get("primary_task_type") or "general").strip() or "general"
    execution_mode = str(workflow.get("execution_mode") or "direct_answer").strip() or "direct_answer"
    confirmation_policy = str(workflow.get("confirmation_policy") or "none").strip() or "none"
    confirmed_once = bool(workflow.get("confirmed_once"))
    source_order = _resolve_source_order(primary_task_type)
    tag_order = _resolve_tag_order(
        primary_task_type,
        confirmed_once=confirmed_once,
        confirmation_policy=confirmation_policy,
    )
    available_tools = [item for item in (tools or []) if isinstance(item, dict)]
    routed_preview: list[str] = []
    for item in available_tools[:8]:
        tool_name = str(item.get("tool_name") or "").strip()
        if tool_name:
            routed_preview.append(tool_name)
    return {
        "version": "v1",
        "chat_surface": str(chat_surface or workflow.get("chat_surface") or "").strip(),
        "primary_task_type": primary_task_type,
        "execution_mode": execution_mode,
        "confirmation_policy": confirmation_policy,
        "confirmed_once": confirmed_once,
        "preferred_sources": source_order,
        "preferred_tags": tag_order,
        "tool_count": len(available_tools),
        "initial_tool_preview": routed_preview,
    }


def _score_tool(
    item: dict[str, Any],
    *,
    index: int,
    preferred_sources: list[str],
    preferred_tags: list[str],
) -> tuple[int, int, int, int]:
    source = infer_tool_source(item)
    tags = infer_tool_tags(item)
    try:
        source_rank = preferred_sources.index(source)
    except ValueError:
        source_rank = len(preferred_sources) + 1
    tag_ranks = [preferred_tags.index(tag) for tag in tags if tag in preferred_tags]
    tag_rank = min(tag_ranks) if tag_ranks else len(preferred_tags) + 1
    named = 0 if str(item.get("tool_name") or "").strip() else 1
    return (source_rank, tag_rank, named, index)


def apply_capability_routing(
    tools: list[dict[str, Any]] | None,
    *,
    assistant_workflow: dict[str, Any] | None = None,
    chat_surface: str = "",
) -> list[dict[str, Any]]:
    available_tools = [dict(item) for item in (tools or []) if isinstance(item, dict)]
    if len(available_tools) <= 1:
        return available_tools
    decision = build_capability_routing_decision(
        available_tools,
        assistant_workflow=assistant_workflow,
        chat_surface=chat_surface,
    )
    preferred_sources = list(decision.get("preferred_sources") or [])
    preferred_tags = list(decision.get("preferred_tags") or [])
    ranked = sorted(
        enumerate(available_tools),
        key=lambda pair: _score_tool(
            pair[1],
            index=pair[0],
            preferred_sources=preferred_sources,
            preferred_tags=preferred_tags,
        ),
    )
    return [item for _, item in ranked]
