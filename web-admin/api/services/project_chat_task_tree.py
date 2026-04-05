"""项目聊天任务树服务。"""

from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any

from core.deps import project_chat_task_store, project_store, work_session_store
from services.dynamic_mcp_apps_query import _generate_execution_plan_payload
from stores.json.project_chat_task_store import (
    ProjectChatTaskNode,
    ProjectChatTaskSession,
)
from stores.json.work_session_store import WorkSessionEvent

_NODE_STATUS_VALUES = {"pending", "in_progress", "blocked", "verifying", "done"}
_TASK_TREE_TOOL_NAMES = {
    "get_current_task_tree",
    "update_task_node_status",
    "complete_task_node_with_verification",
}
_STATUS_PRIORITY = {
    "pending": 0,
    "in_progress": 1,
    "blocked": 1,
    "verifying": 2,
    "done": 3,
}
_COMPLETION_SIGNAL_TERMS = (
    "已完成",
    "已经完成",
    "完成了",
    "处理完成",
    "已处理",
    "已实现",
    "实现完成",
    "已修复",
    "修复完成",
    "已解决",
    "解决了",
    "done",
    "fixed",
)
_COMPLETION_NEGATION_TERMS = (
    "未完成",
    "没有完成",
    "尚未完成",
    "还没完成",
    "未实现",
    "没有实现",
    "未修复",
    "没有修复",
    "未解决",
    "没有解决",
)
_VERIFICATION_SIGNAL_TERMS = (
    "已验证",
    "验证通过",
    "测试通过",
    "构建通过",
    "回归通过",
    "联调通过",
    "人工验证",
    "人工确认",
    "截图确认",
    "日志确认",
    "验证完成",
)
_VERIFICATION_NEGATION_TERMS = (
    "未验证",
    "没有验证",
    "尚未验证",
    "还没验证",
    "待验证",
    "需要验证",
)
_CONTEXT_BOOTSTRAP_NODE_TERMS = (
    "项目上下文",
    "成员",
    "规则",
    "mcp 能力",
    "mcp能力",
    "检索项目上下文",
)
_LOOKUP_QUERY_GOAL_TERMS = (
    "都有谁",
    "有哪些",
    "都有什么",
    "有哪些能力",
    "多少",
    "做什么的",
    "干什么的",
    "用来做什么",
    "主要做什么",
    "列表",
    "清单",
    "明细",
    "是什么",
    "从哪里",
    "查看",
    "查询",
    "谁",
)
_NON_LOOKUP_QUERY_GOAL_TERMS = (
    "为什么",
    "怎么",
    "如何",
    "bug",
    "错误",
    "异常",
    "修复",
    "实现",
    "开发",
    "新增",
    "添加",
    "修改",
    "删除",
    "优化",
    "完善",
    "接入",
    "监听",
    "监控",
    "提示词",
    "任务树",
)
_LOOKUP_QUERY_NON_ANSWER_TOOL_NAMES = {
    "bind_project_context",
    "analyze_task",
    "generate_execution_plan",
    "classify_command_risk",
    "check_workspace_scope",
    "resolve_execution_mode",
    "check_operation_policy",
    "start_work_session",
    "save_work_facts",
    "append_session_event",
    "resume_work_session",
    "summarize_checkpoint",
    "build_delivery_report",
    "generate_release_note_entry",
}
_TASK_TREE_INTERNAL_PLAN_TOOL_NAMES = {
    "search_ids",
    "get_content",
    "get_manual_content",
    "resolve_relevant_context",
    "generate_execution_plan",
    "execute_project_collaboration",
    "search_project_context",
    "query_project_rules",
    "query_project_members",
    "get_project_detail",
    "get_project_employee_detail",
    "bind_project_context",
    "analyze_task",
    "classify_command_risk",
    "check_workspace_scope",
    "resolve_execution_mode",
    "check_operation_policy",
    "start_work_session",
    "save_work_facts",
    "append_session_event",
    "resume_work_session",
    "summarize_checkpoint",
    "save_project_memory",
    "build_delivery_report",
    "generate_release_note_entry",
}
_AUTO_INFERRED_PROXY_ENTRY_PREFIX = "auto inferred proxy entry from"
_ROUTE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._-]+)+")
_EMBEDDED_TOOL_CALL_RE = re.compile(r"<tool_call>([^<]+)(.*?)</tool_call>", re.S)
_EMBEDDED_TOOL_ARG_RE = re.compile(
    r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>",
    re.S,
)


def _normalize_text(value: Any, limit: int = 2000) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def _normalize_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _NODE_STATUS_VALUES else "pending"


def _task_tree_work_session_id(session: ProjectChatTaskSession) -> str:
    normalized = ProjectChatTaskSession(**asdict(session))
    source_session_id = _normalize_text(normalized.source_session_id, 80)
    if source_session_id:
        return source_session_id
    return _normalize_text(f"ws_{normalized.id}", 80)


def _resolve_project_name(project_id: str) -> str:
    normalized_project_id = _normalize_text(project_id, 80)
    if not normalized_project_id:
        return ""
    try:
        project = project_store.get(normalized_project_id)
    except Exception:  # pragma: no cover - defensive guard
        project = None
    return _normalize_text(getattr(project, "name", "") or normalized_project_id, 120)


def _save_task_tree_progress_event(
    *,
    session: ProjectChatTaskSession,
    node: ProjectChatTaskNode | None = None,
    event_type: str,
    content: str,
    verification: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> None:
    normalized_session = _recompute_session(ProjectChatTaskSession(**asdict(session)))
    active_node = node
    if active_node is None:
        active_node = next(
            (item for item in normalized_session.nodes if item.id == normalized_session.current_node_id),
            None,
        )
    next_step_items = [
        _normalize_text(item, 300)
        for item in (next_steps or [])
        if _normalize_text(item, 300)
    ]
    verification_items = [
        _normalize_text(item, 400)
        for item in (verification or [])
        if _normalize_text(item, 400)
    ]
    try:
        work_session_store.save(
            WorkSessionEvent(
                id=work_session_store.new_id(),
                project_id=normalized_session.project_id,
                project_name=_resolve_project_name(normalized_session.project_id),
                employee_id=_normalize_text(normalized_session.username, 80),
                session_id=_task_tree_work_session_id(normalized_session),
                task_tree_session_id=_normalize_text(normalized_session.id, 80),
                task_tree_chat_session_id=(
                    _normalize_text(normalized_session.source_chat_session_id, 80)
                    or _normalize_text(normalized_session.chat_session_id, 80)
                ),
                task_node_id=_normalize_text(getattr(active_node, "id", ""), 80),
                task_node_title=_normalize_text(getattr(active_node, "title", ""), 200),
                source_kind="task-tree",
                event_type=_normalize_text(event_type, 40),
                phase=_normalize_text(getattr(active_node, "stage_key", ""), 80),
                step=_normalize_text(getattr(active_node, "title", ""), 80),
                status=_normalize_text(
                    getattr(active_node, "status", "") or normalized_session.status,
                    40,
                ),
                goal=_normalize_text(normalized_session.root_goal or normalized_session.title, 400),
                content=_normalize_text(content, 4000),
                verification=verification_items,
                next_steps=next_step_items,
            )
        )
    except Exception:  # pragma: no cover - defensive guard
        return


def _should_rebuild_task_tree_for_new_goal(
    existing: ProjectChatTaskSession | None,
    root_goal: str,
) -> bool:
    if existing is None:
        return False
    next_goal = _normalize_text(root_goal, 1000)
    current_goal = _normalize_text(getattr(existing, "root_goal", ""), 1000)
    if not next_goal or next_goal == current_goal:
        return False
    current_status = _normalize_status(getattr(existing, "status", "pending"))
    if current_status == "done":
        return True
    try:
        progress_percent = int(getattr(existing, "progress_percent", 0) or 0)
    except (TypeError, ValueError):
        progress_percent = 0
    if current_status == "pending" and progress_percent <= 0:
        return True
    return False


def _can_refine_task_tree_in_place(
    existing: ProjectChatTaskSession | None,
    root_goal: str,
    *,
    force: bool = False,
) -> bool:
    if existing is None:
        return False
    next_goal = _normalize_text(root_goal, 1000)
    current_goal = _normalize_text(getattr(existing, "root_goal", ""), 1000)
    if not force and (not next_goal or next_goal == current_goal):
        return False
    current_status = _normalize_status(getattr(existing, "status", "pending"))
    if current_status != "pending":
        return False
    try:
        progress_percent = int(getattr(existing, "progress_percent", 0) or 0)
    except (TypeError, ValueError):
        progress_percent = 0
    if progress_percent > 0:
        return False
    return all(_normalize_status(getattr(node, "status", "")) == "pending" for node in (existing.nodes or []))


def _refine_task_tree_in_place(
    existing: ProjectChatTaskSession,
    *,
    root_goal: str,
    max_steps: int = 6,
) -> ProjectChatTaskSession:
    rebuilt = build_task_tree_session(
        project_id=existing.project_id,
        username=existing.username,
        chat_session_id=existing.chat_session_id,
        root_goal=root_goal,
        max_steps=max_steps,
    )
    rebuilt.id = existing.id
    rebuilt.created_at = existing.created_at
    rebuilt.source_chat_session_id = existing.source_chat_session_id
    rebuilt.updated_at = existing.updated_at
    return project_chat_task_store.save(_recompute_session(rebuilt))


def _contains_any_term(text: str, terms: tuple[str, ...]) -> bool:
    normalized = str(text or "").strip().lower()
    return bool(normalized) and any(term in normalized for term in terms)


def _has_completion_signal(text: str) -> bool:
    return _contains_any_term(text, _COMPLETION_SIGNAL_TERMS) and not _contains_any_term(
        text,
        _COMPLETION_NEGATION_TERMS,
    )


def _has_verification_signal(text: str) -> bool:
    return _contains_any_term(text, _VERIFICATION_SIGNAL_TERMS) and not _contains_any_term(
        text,
        _VERIFICATION_NEGATION_TERMS,
    )


def _should_promote_status(current_status: str, next_status: str) -> bool:
    return _STATUS_PRIORITY.get(_normalize_status(next_status), 0) > _STATUS_PRIORITY.get(
        _normalize_status(current_status),
        0,
    )


def _merge_summary_for_model(existing: str, note: str) -> str:
    normalized_existing = _normalize_text(existing, 1000)
    normalized_note = _normalize_text(note, 300)
    if not normalized_note:
        return normalized_existing
    if not normalized_existing:
        return normalized_note
    if normalized_note in normalized_existing:
        return normalized_existing[:1000]
    return f"{normalized_note}\n{normalized_existing}"[:1000]


def _is_context_bootstrap_node(node: dict[str, Any]) -> bool:
    haystack = "\n".join(
        [
            _normalize_text(node.get("title"), 300),
            _normalize_text(node.get("description"), 500),
            _normalize_text(node.get("summary_for_model"), 500),
        ]
    ).lower()
    if not haystack:
        return False
    if (
        int(node.get("level") or 0) == 1
        and int(node.get("sort_order") or 0) == 1
        and ("上下文" in haystack or "context" in haystack)
    ):
        return True
    return all(term in haystack for term in _CONTEXT_BOOTSTRAP_NODE_TERMS[:3]) and any(
        term in haystack for term in _CONTEXT_BOOTSTRAP_NODE_TERMS[3:]
    )


def _is_lookup_query_goal(text: str) -> bool:
    normalized = _normalize_text(text, 400).lower()
    if not normalized:
        return False
    if any(term in normalized for term in _NON_LOOKUP_QUERY_GOAL_TERMS):
        return False
    if normalized.endswith(("?", "？")):
        return True
    return any(term in normalized for term in _LOOKUP_QUERY_GOAL_TERMS)


def _build_lookup_query_plan_step(task_text: str) -> dict[str, str]:
    normalized_task = _normalize_text(task_text, 300) or "当前问题"
    return {
        "phase": "query",
        "tool_name": "search_project_context",
        "step": "检索问题所需信息并直接回答用户",
        "purpose": (
            f"围绕“{normalized_task}”完成信息检索、整理结论并给出依据。"
            "若信息不足，明确缺失项。"
        ),
        "reason": "该问题属于查询型需求，不需要拆成实现或协作开发步骤。",
    }


def _extract_route_path(text: str) -> str:
    match = _ROUTE_PATH_RE.search(_normalize_text(text, 400))
    return _normalize_text(match.group(0), 200) if match else ""


def _compact_plan_step_text(item: dict[str, Any]) -> str:
    parts = [
        _normalize_text(item.get("step"), 200),
        _normalize_text(item.get("title"), 200),
        _normalize_text(item.get("reason"), 300),
        _normalize_text(item.get("purpose"), 300),
    ]
    return " ".join(part for part in parts if part).strip()


def _is_internal_plan_step(item: dict[str, Any]) -> bool:
    tool_name = _normalize_text(
        item.get("tool_name") or item.get("recommended_tool") or item.get("tool"),
        120,
    ).lower()
    compact_text = _compact_plan_step_text(item).lower()
    if compact_text.startswith(_AUTO_INFERRED_PROXY_ENTRY_PREFIX):
        return True
    if _AUTO_INFERRED_PROXY_ENTRY_PREFIX in compact_text:
        return True
    if tool_name and tool_name in _TASK_TREE_INTERNAL_PLAN_TOOL_NAMES:
        return True
    return False


def _normalize_task_tree_plan_step(item: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(item, dict) or _is_internal_plan_step(item):
        return None
    step = (
        _normalize_text(item.get("step"), 160)
        or _normalize_text(item.get("title"), 160)
        or _normalize_text(item.get("reason"), 160)
    )
    if not step:
        return None
    purpose = (
        _normalize_text(item.get("purpose"), 280)
        or _normalize_text(item.get("reason"), 280)
    )
    phase = _normalize_text(item.get("phase"), 60)
    return {
        "step": step,
        "purpose": purpose,
        "phase": phase,
    }


def _has_verification_flavored_step(steps: list[dict[str, str]]) -> bool:
    verification_terms = ("验证", "验收", "测试", "回归", "确认", "收尾", "发布")
    for item in steps:
        compact = _compact_plan_step_text(item)
        if any(term in compact for term in verification_terms):
            return True
    return False


def _build_goal_oriented_plan_steps(task_text: str, *, max_steps: int = 6) -> list[dict[str, str]]:
    normalized_task = _normalize_text(task_text, 300)
    route_path = _extract_route_path(normalized_task)
    target = route_path or "当前需求"
    lower_task = normalized_task.lower()

    if "tab" in lower_task or any(term in normalized_task for term in ("tabs", "切换", "设置页", "页面")):
        steps = [
            {
                "step": f"梳理 {target} 当前结构与切换路径",
                "purpose": "先确认现有页面结构、入口和状态流，避免改造后出现重复跳转或状态分叉。",
                "phase": "analysis",
            },
            {
                "step": "改造成页内 Tabs 切换并保持状态同步",
                "purpose": "围绕用户目标完成最小增量改动，让常用设置不必来回切换页面。",
                "phase": "implementation",
            },
            {
                "step": "验证 Tabs 切换、路由与边界状态",
                "purpose": "确认切换体验、默认激活项和返回路径都正确，再收口本轮任务。",
                "phase": "verification",
            },
        ]
    elif any(term in normalized_task for term in ("修复", "bug", "错误", "异常", "不对")):
        steps = [
            {
                "step": f"定位 {target} 的当前问题与影响范围",
                "purpose": "先确认触发条件、关联模块和最小修改面。",
                "phase": "analysis",
            },
            {
                "step": f"修复 {target} 的核心问题",
                "purpose": "完成最小增量改动，并处理必要的联动逻辑。",
                "phase": "implementation",
            },
            {
                "step": "验证修复结果并补充收尾说明",
                "purpose": "确认关键路径可用，记录验证结果与剩余风险。",
                "phase": "verification",
            },
        ]
    elif any(term in normalized_task for term in ("优化", "完善", "重构")):
        steps = [
            {
                "step": f"梳理 {target} 的现状与改动边界",
                "purpose": "先确认当前实现、约束和影响面。",
                "phase": "analysis",
            },
            {
                "step": f"完成 {target} 的优化改造",
                "purpose": "按最小改动原则推进核心调整，并兼顾关联路径。",
                "phase": "implementation",
            },
            {
                "step": "验证优化结果并整理交付结论",
                "purpose": "确认体验或行为达到预期，并补齐验证说明。",
                "phase": "verification",
            },
        ]
    else:
        steps = [
            {
                "step": f"梳理 {target} 的现状与改动范围",
                "purpose": "先明确当前实现、影响面和最小可行改动。",
                "phase": "analysis",
            },
            {
                "step": f"完成“{normalized_task or '当前需求'}”的核心改动",
                "purpose": "围绕用户目标实现主路径，避免把内部工具步骤误当成任务节点。",
                "phase": "implementation",
            },
            {
                "step": "验证结果并完成本轮收尾",
                "purpose": "确认关键路径和边界状态可用，再沉淀最终结论。",
                "phase": "verification",
            },
        ]
    return steps[: max(1, min(int(max_steps or 6), 10))]


def _build_task_tree_plan_steps(
    task_text: str,
    *,
    project_id: str,
    max_steps: int = 6,
) -> list[dict[str, str]]:
    plan = _generate_execution_plan_payload(task_text, project_id=project_id, max_steps=max_steps)
    normalized_steps = [
        item
        for item in (
            _normalize_task_tree_plan_step(raw_item)
            for raw_item in list(plan.get("plan_steps") or [])
        )
        if item
    ]
    step_limit = max(1, min(int(max_steps or 6), 10))
    if len(normalized_steps) >= 2:
        normalized_steps = normalized_steps[:step_limit]
        if not _has_verification_flavored_step(normalized_steps) and len(normalized_steps) < step_limit:
            normalized_steps.append(
                {
                    "step": "验证结果并完成本轮收尾",
                    "purpose": "确认关键路径与边界状态正确，再结束当前任务。",
                    "phase": "verification",
                }
            )
        return normalized_steps[:step_limit]
    return _build_goal_oriented_plan_steps(task_text, max_steps=step_limit)


def _strip_embedded_task_tree_markup(text: str) -> str:
    normalized = _normalize_text(text, 4000)
    if not normalized:
        return ""
    embedded_call = _extract_embedded_task_tree_tool_call(normalized)
    if isinstance(embedded_call, dict):
        embedded_args = embedded_call.get("args") or {}
        extracted_values = [
            _normalize_text(embedded_args.get("verification_result"), 1200),
            _normalize_text(embedded_args.get("summary_for_model"), 600),
        ]
        extracted_text = " ".join([item for item in extracted_values if item])
        if extracted_text:
            return extracted_text
    without_tags = re.sub(r"</?arg_(?:key|value)>", "", normalized, flags=re.I)
    without_tags = re.sub(r"</?tool_call>", "", without_tags, flags=re.I)
    return _normalize_text(without_tags, 4000)


def _extract_embedded_task_tree_tool_call(text: str) -> dict[str, Any] | None:
    normalized = _normalize_text(text, 4000)
    if not normalized:
        return None
    match = _EMBEDDED_TOOL_CALL_RE.search(normalized)
    if match is None:
        return None
    tool_name = _normalize_text(match.group(1), 120)
    if tool_name not in _TASK_TREE_TOOL_NAMES:
        return None
    args: dict[str, str] = {}
    for key, value in _EMBEDDED_TOOL_ARG_RE.findall(match.group(2) or ""):
        normalized_key = _normalize_text(key, 80)
        if not normalized_key:
            continue
        args[normalized_key] = _normalize_text(value, 2000)
    return {"tool_name": tool_name, "args": args}


def _has_substantive_answer(text: str) -> bool:
    normalized = _strip_embedded_task_tree_markup(text)
    if not normalized:
        return False
    lines = [
        line.strip()
        for line in normalized.splitlines()
        if line.strip() and not line.strip().startswith(">")
    ]
    compact = "".join(lines)
    if len(compact) < 8:
        return False
    if compact in _TASK_TREE_TOOL_NAMES:
        return False
    return True


def _build_auto_verification_result(
    *,
    root_goal: str,
    assistant_content: str,
    successful_tool_names: list[str],
) -> str:
    answer_excerpt = _strip_embedded_task_tree_markup(assistant_content)
    evidence_parts: list[str] = ["系统自动验证：已完成查询型问题的检索与回答。"]
    if successful_tool_names:
        evidence_parts.append(
            f"执行证据：{', '.join(successful_tool_names[:6])}"
        )
    if answer_excerpt:
        evidence_parts.append(f"回答摘要：{_normalize_text(answer_excerpt, 300)}")
    if root_goal:
        evidence_parts.append(f"问题目标：{_normalize_text(root_goal, 200)}")
    return " ".join(evidence_parts)[:1800]


def _auto_complete_lookup_query_session(
    *,
    session: ProjectChatTaskSession,
    project_id: str,
    username: str,
    chat_session_id: str,
    assistant_content: str,
    successful_tool_names: list[str],
) -> tuple[ProjectChatTaskSession | None, dict[str, Any] | None]:
    working_session = get_task_tree(project_id, username, chat_session_id) or session
    if not _is_lookup_query_goal(working_session.root_goal or working_session.title):
        return working_session, None
    children_by_parent = _children_map(working_session.nodes)
    leaf_nodes = [
        node for node in working_session.nodes if not children_by_parent.get(node.id)
    ]
    verification_result = _build_auto_verification_result(
        root_goal=working_session.root_goal or working_session.title,
        assistant_content=assistant_content,
        successful_tool_names=successful_tool_names,
    )
    for leaf in leaf_nodes:
        if _normalize_status(leaf.status) == "done":
            continue
        working_session = update_task_node(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            node_id=leaf.id,
            status="done",
            verification_result=verification_result,
            summary_for_model=(
                f"查询型问题已完成：{_normalize_text(working_session.root_goal or working_session.title, 200)}"
            ),
            allow_direct_completion=True,
        )
    root_nodes = [node for node in working_session.nodes if not str(node.parent_id or "").strip()]
    for root in root_nodes:
        if _normalize_status(root.status) == "done":
            continue
        working_session = update_task_node(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            node_id=root.id,
            status="done",
            verification_result=verification_result,
            summary_for_model=(
                f"查询型任务已整体完成：{_normalize_text(working_session.root_goal or working_session.title, 200)}"
            ),
            allow_direct_completion=True,
        )
    if _normalize_status(getattr(working_session, "status", "")) == "done":
        archived_session = archive_task_tree(
            working_session,
            reason="completed_task_closed",
            delete_current=True,
        )
        return None, serialize_task_tree(archived_session)
    return working_session, None


def _node_sort_key(node: ProjectChatTaskNode) -> tuple[int, int, str]:
    return int(node.level or 0), int(node.sort_order or 0), str(node.id or "")


def _children_map(nodes: list[ProjectChatTaskNode]) -> dict[str, list[ProjectChatTaskNode]]:
    mapping: dict[str, list[ProjectChatTaskNode]] = {}
    for node in sorted(nodes, key=_node_sort_key):
        mapping.setdefault(str(node.parent_id or ""), []).append(node)
    return mapping


def _node_title_from_plan_step(item: dict[str, Any], index: int) -> str:
    title = (
        _normalize_text(item.get("step"), 160)
        or _normalize_text(item.get("title"), 160)
        or _normalize_text(item.get("reason"), 160)
        or _normalize_text(item.get("tool_name"), 160)
        or _normalize_text(item.get("recommended_tool"), 160)
    )
    return title or f"步骤 {index}"


def _node_description_from_plan_step(item: dict[str, Any]) -> str:
    parts = [
        _normalize_text(item.get("purpose"), 280),
        _normalize_text(item.get("reason"), 280),
    ]
    tool_name = _normalize_text(item.get("tool_name") or item.get("recommended_tool"), 120)
    if tool_name:
        parts.append(f"建议工具：{tool_name}")
    phase = _normalize_text(item.get("phase"), 60)
    if phase:
        parts.append(f"阶段：{phase}")
    return "\n".join([part for part in parts if part])


def _build_default_verification_items(is_root: bool = False) -> list[str]:
    if is_root:
        return [
            "确认全部子任务已完成",
            "填写整体验证结论，说明最终结果与验证方式",
        ]
    return [
        "填写本步骤验证结果",
        "说明完成证据，例如测试、截图、日志或人工核对结论",
    ]


def _preorder_candidates(root_nodes: list[ProjectChatTaskNode], children_by_parent: dict[str, list[ProjectChatTaskNode]]) -> list[ProjectChatTaskNode]:
    ordered: list[ProjectChatTaskNode] = []

    def visit(node: ProjectChatTaskNode) -> None:
        ordered.append(node)
        for child in children_by_parent.get(node.id, []):
            visit(child)

    for root in root_nodes:
        visit(root)
    return ordered


def _normalize_match_text(value: Any, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", _normalize_text(value, limit)).strip().lower()


def _coerce_event_status(value: Any) -> str:
    normalized = _normalize_match_text(value, 60)
    if normalized in {"done", "completed", "complete", "finished", "resolved", "fixed"}:
        return "done"
    if normalized in {"verifying", "verified", "checking", "validation"}:
        return "verifying"
    if normalized in {"in_progress", "in-progress", "started", "working", "processing", "running"}:
        return "in_progress"
    if normalized in {"blocked", "failed", "error"}:
        return "blocked"
    return _normalize_status(normalized)


def _extract_event_verification_text(event: WorkSessionEvent) -> str:
    verification_items = [
        _normalize_text(item, 500)
        for item in list(getattr(event, "verification", []) or [])
        if _normalize_text(item, 500)
    ]
    if verification_items:
        return _normalize_text("；".join(verification_items), 2000)
    if _coerce_event_status(getattr(event, "status", "")) != "done":
        return ""
    facts = [
        _normalize_text(item, 500)
        for item in list(getattr(event, "facts", []) or [])
        if _normalize_text(item, 500)
    ]
    if facts:
        return _normalize_text("；".join(facts[:3]), 2000)
    content = _normalize_text(getattr(event, "content", ""), 2000)
    if content:
        return content
    return ""


def _task_node_event_match_score(node: ProjectChatTaskNode, event: WorkSessionEvent) -> int:
    score = 0
    node_id = _normalize_text(getattr(node, "id", ""), 80)
    event_node_id = _normalize_text(getattr(event, "task_node_id", ""), 80)
    if node_id and event_node_id and node_id == event_node_id:
        score += 100
    stage_key = _normalize_match_text(getattr(node, "stage_key", ""), 80)
    phase = _normalize_match_text(getattr(event, "phase", ""), 80)
    if stage_key and phase and stage_key == phase:
        score += 36
    title = _normalize_match_text(getattr(node, "title", ""), 200)
    event_title = _normalize_match_text(getattr(event, "task_node_title", ""), 200)
    step = _normalize_match_text(getattr(event, "step", ""), 200)
    for candidate in (event_title, step):
        if not candidate:
            continue
        if title and title == candidate:
            score += 28
        elif title and (title in candidate or candidate in title):
            score += 16
    return score


def _matched_events_for_node(node: ProjectChatTaskNode, events: list[WorkSessionEvent]) -> list[WorkSessionEvent]:
    matched: list[tuple[int, WorkSessionEvent]] = []
    for event in events:
        score = _task_node_event_match_score(node, event)
        if score <= 0:
            continue
        matched.append((score, event))
    matched.sort(key=lambda item: (item[1].created_at, item[1].id, item[0]))
    return [item[1] for item in matched]


def _build_root_reconcile_verification(
    root_node: ProjectChatTaskNode,
    leaf_nodes: list[ProjectChatTaskNode],
    events: list[WorkSessionEvent],
) -> str:
    for event in sorted(events, key=lambda item: (item.created_at, item.id), reverse=True):
        if _coerce_event_status(getattr(event, "status", "")) != "done":
            continue
        verification_text = _extract_event_verification_text(event)
        if verification_text:
            return verification_text
    leaf_results = [
        _normalize_text(getattr(node, "verification_result", ""), 500)
        for node in leaf_nodes
        if _normalize_text(getattr(node, "verification_result", ""), 500)
    ]
    if leaf_results:
        return _normalize_text("；".join(leaf_results[:3]), 2000)
    return _normalize_text(f"整体验证完成：{root_node.title}", 2000)


def _build_synthetic_leaf_reconcile_verification(
    node: ProjectChatTaskNode,
    matched_events: list[WorkSessionEvent],
    later_done_nodes: list[ProjectChatTaskNode],
) -> str:
    event_labels: list[str] = []
    for event in reversed(matched_events):
        phase = _normalize_text(getattr(event, "phase", ""), 80)
        step = _normalize_text(getattr(event, "step", ""), 120)
        candidate = step or phase
        if candidate and candidate not in event_labels:
            event_labels.append(candidate)
        if len(event_labels) >= 2:
            break
    later_titles = [
        _normalize_text(getattr(item, "title", ""), 120)
        for item in later_done_nodes
        if _normalize_text(getattr(item, "title", ""), 120)
    ][:2]
    prefix = _normalize_text(getattr(node, "title", ""), 160) or "当前节点"
    if event_labels and later_titles:
        return _normalize_text(
            f"系统收口：{prefix} 已存在过程轨迹，且后续节点“{' / '.join(later_titles)}”已完成，视为前序步骤已完成。",
            2000,
        )
    if event_labels:
        return _normalize_text(
            f"系统收口：{prefix} 已存在过程轨迹（{' / '.join(event_labels)}），后续执行链路已完成，视为本步骤已完成。",
            2000,
        )
    if later_titles:
        return _normalize_text(
            f"系统收口：后续节点“{' / '.join(later_titles)}”已完成，{prefix} 视为已完成。",
            2000,
        )
    return _normalize_text(f"系统收口：{prefix} 视为已完成。", 2000)


def _reconcile_task_tree_from_work_session_events(session: ProjectChatTaskSession) -> ProjectChatTaskSession:
    normalized = _recompute_session(ProjectChatTaskSession(**asdict(session)))
    events = work_session_store.list_events(
        project_id=normalized.project_id,
        task_tree_session_id=_normalize_text(normalized.id, 80),
        task_tree_chat_session_id=_normalize_text(
            normalized.source_chat_session_id or normalized.chat_session_id,
            80,
        ),
        limit=400,
    )
    if not events:
        return normalized

    working = ProjectChatTaskSession(**asdict(normalized))
    changed = False
    nodes_by_id = {node.id: node for node in working.nodes if node.id}
    matched_events_by_node_id: dict[str, list[WorkSessionEvent]] = {}

    for node in working.nodes:
        if not _normalize_text(getattr(node, "parent_id", ""), 80):
            continue
        matched_events = _matched_events_for_node(node, events)
        matched_events_by_node_id[node.id] = matched_events
        if not matched_events:
            continue
        current_status = _normalize_status(node.status)
        next_status = current_status
        verification_text = _normalize_text(node.verification_result, 2000)
        for event in matched_events:
            event_status = _coerce_event_status(getattr(event, "status", ""))
            if _STATUS_PRIORITY.get(event_status, 0) > _STATUS_PRIORITY.get(next_status, 0):
                next_status = event_status
            event_verification = _extract_event_verification_text(event)
            if event_verification and (
                not verification_text
                or _coerce_event_status(getattr(event, "status", "")) == "done"
            ):
                verification_text = event_verification
        if next_status == "done" and not verification_text:
            next_status = "verifying"
        if next_status != current_status:
            node.status = next_status
            changed = True
        if verification_text and verification_text != _normalize_text(node.verification_result, 2000):
            node.verification_result = verification_text
            node.summary_for_model = _normalize_text(verification_text, 1000)
            node.latest_outcome = _normalize_text(verification_text, 1000)
            changed = True

    children_by_parent = _children_map(list(nodes_by_id.values()))
    for parent_id, siblings in children_by_parent.items():
        if not _normalize_text(parent_id, 80):
            continue
        ordered_siblings = sorted(siblings, key=_node_sort_key)
        later_done_nodes: list[ProjectChatTaskNode] = []
        for node in reversed(ordered_siblings):
            if _normalize_status(node.status) == "done":
                later_done_nodes.append(node)
                continue
            if not later_done_nodes:
                continue
            if _normalize_status(node.status) not in {"in_progress", "verifying", "pending"}:
                continue
            verification_text = _normalize_text(node.verification_result, 2000)
            if not verification_text:
                matched_events = matched_events_by_node_id.get(node.id) or []
                if not matched_events:
                    continue
                verification_text = _build_synthetic_leaf_reconcile_verification(
                    node,
                    matched_events,
                    later_done_nodes,
                )
                node.verification_result = verification_text
                changed = True
            node.status = "done"
            node.summary_for_model = _normalize_text(
                node.summary_for_model or verification_text,
                1000,
            )
            node.latest_outcome = _normalize_text(
                node.latest_outcome or verification_text,
                1000,
            )
            changed = True

    working = _recompute_session(working)
    children_by_parent = _children_map(list(working.nodes))
    leaf_nodes = [node for node in working.nodes if not children_by_parent.get(node.id)]
    if leaf_nodes and all(_normalize_status(node.status) == "done" for node in leaf_nodes):
        root_nodes = [node for node in working.nodes if not _normalize_text(node.parent_id, 80)]
        for root_node in root_nodes:
            if not _normalize_text(root_node.verification_result, 2000):
                root_verification = _build_root_reconcile_verification(root_node, leaf_nodes, events)
                root_node.verification_result = root_verification
                root_node.summary_for_model = _normalize_text(root_verification, 1000)
                root_node.latest_outcome = _normalize_text(root_verification, 1000)
                changed = True
            if _normalize_status(root_node.status) != "done":
                root_node.status = "done"
                changed = True
        working = _recompute_session(working)

    return working if changed else normalized


def _load_reconciled_task_tree_session(session: ProjectChatTaskSession | None) -> ProjectChatTaskSession | None:
    if session is None:
        return None
    normalized = _recompute_session(ProjectChatTaskSession(**asdict(session)))
    reconciled = _reconcile_task_tree_from_work_session_events(normalized)
    if asdict(reconciled) != asdict(session):
        project_chat_task_store.save(reconciled)
    return reconciled


def _recompute_session(session: ProjectChatTaskSession) -> ProjectChatTaskSession:
    normalized = ProjectChatTaskSession(**asdict(session))
    if not normalized.source_session_id:
        normalized.source_session_id = _task_tree_work_session_id(normalized)
    if not normalized.nodes:
        normalized.progress_percent = 0
        normalized.status = "pending"
        normalized.current_node_id = ""
        return normalized

    nodes_by_id = {node.id: node for node in normalized.nodes if node.id}
    children_by_parent = _children_map(list(nodes_by_id.values()))
    root_nodes = children_by_parent.get("", []) or [
        node for node in sorted(nodes_by_id.values(), key=_node_sort_key) if not str(node.parent_id or "").strip()
    ]
    if not root_nodes:
        normalized.progress_percent = 0
        normalized.status = "pending"
        normalized.current_node_id = ""
        return normalized

    def resolve_node(node: ProjectChatTaskNode) -> str:
        children = children_by_parent.get(node.id, [])
        if not children:
            node.status = _normalize_status(node.status)
            if node.status == "done" and not node.verification_result:
                node.status = "verifying"
            return node.status

        child_statuses = [resolve_node(child) for child in children]
        all_children_done = all(status == "done" for status in child_statuses)
        any_blocked = any(status == "blocked" for status in child_statuses)
        any_active = any(status in {"in_progress", "verifying"} for status in child_statuses)
        if all_children_done and node.verification_result:
            node.status = "done"
        elif all_children_done:
            node.status = "verifying"
        elif any_active:
            node.status = "in_progress"
        elif any_blocked:
            node.status = "blocked"
        else:
            node.status = "pending"
        return node.status

    for root in root_nodes:
        resolve_node(root)

    leaf_nodes = [
        node
        for node in nodes_by_id.values()
        if not children_by_parent.get(node.id)
    ]
    done_leaf_nodes = [node for node in leaf_nodes if node.status == "done"]
    normalized.progress_percent = int(round((len(done_leaf_nodes) / max(len(leaf_nodes), 1)) * 100))
    root_statuses = [root.status for root in root_nodes]
    if root_statuses and all(status == "done" for status in root_statuses):
        normalized.status = "done"
    elif any(status in {"in_progress", "verifying"} for status in root_statuses):
        normalized.status = "in_progress"
    elif any(status == "blocked" for status in root_statuses):
        normalized.status = "blocked"
    else:
        normalized.status = "pending"

    ordered_nodes = _preorder_candidates(root_nodes, children_by_parent)
    current_candidates = [
        node
        for node in ordered_nodes
        if node.level > 0 and node.status in {"in_progress", "verifying", "pending", "blocked"}
    ]
    current_node = nodes_by_id.get(normalized.current_node_id)
    if current_node is None or current_node.status == "done":
        normalized.current_node_id = current_candidates[0].id if current_candidates else ordered_nodes[0].id
    normalized.nodes = ordered_nodes
    return normalized


def build_task_tree_session(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    root_goal: str,
    max_steps: int = 6,
) -> ProjectChatTaskSession:
    task_text = _normalize_text(root_goal, 1000)
    if _is_lookup_query_goal(task_text):
        plan_steps = [_build_lookup_query_plan_step(task_text)]
    else:
        plan_steps = _build_task_tree_plan_steps(
            task_text,
            project_id=project_id,
            max_steps=max_steps,
        )
    session = ProjectChatTaskSession(
        id=project_chat_task_store.new_session_id(),
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        source_chat_session_id="",
        record_kind="requirement",
        source_session_id="",
        round_index=1,
        title=_normalize_text(task_text, 120) or "当前任务",
        root_goal=task_text,
        status="pending",
        lifecycle_status="active",
        archived_reason="",
        archived_at="",
        progress_percent=0,
        nodes=[],
    )
    root_node = ProjectChatTaskNode(
        id=project_chat_task_store.new_node_id(),
        session_id=session.id,
        parent_id="",
        node_kind="goal",
        stage_key="goal",
        title=_normalize_text(task_text, 160) or "当前任务",
        description="根任务。父级完成必须包含全部子任务和整体验证。",
        objective="汇总当前需求下的全部计划节点，并在全部完成后产出整体验证结论。",
        level=0,
        sort_order=0,
        status="pending",
        done_definition="全部子任务完成后，填写整体验证结论，才能标记为完成。",
        completion_criteria="全部子任务完成后，填写整体验证结论，才能标记为完成。",
        verification_items=_build_default_verification_items(is_root=True),
        verification_method=_build_default_verification_items(is_root=True),
        summary_for_model=f"当前总目标：{task_text}",
        latest_outcome=f"当前总目标：{task_text}",
    )
    nodes = [root_node]
    for index, item in enumerate(plan_steps, start=1):
        title = _node_title_from_plan_step(item, index)
        description = _node_description_from_plan_step(item)
        nodes.append(
            ProjectChatTaskNode(
                id=project_chat_task_store.new_node_id(),
                session_id=session.id,
                parent_id=root_node.id,
                node_kind="plan_step",
                stage_key=_normalize_text(item.get("phase"), 80),
                title=title,
                description=description,
                objective=description or title,
                level=1,
                sort_order=index,
                status="pending",
                done_definition="完成该步骤后，必须填写验证结果，再标记完成。",
                completion_criteria="完成该步骤后，必须填写验证结果，再标记完成。",
                verification_items=_build_default_verification_items(is_root=False),
                verification_method=_build_default_verification_items(is_root=False),
                summary_for_model="\n".join(
                    [part for part in [title, description] if part]
                )[:1000],
                latest_outcome="\n".join(
                    [part for part in [title, description] if part]
                )[:1000],
            )
        )
    session.nodes = nodes
    session.current_node_id = nodes[1].id if len(nodes) > 1 else root_node.id
    session.source_session_id = _task_tree_work_session_id(session)
    return _recompute_session(session)


def get_task_tree(project_id: str, username: str, chat_session_id: str) -> ProjectChatTaskSession | None:
    session = project_chat_task_store.get(project_id, username, chat_session_id)
    return _load_reconciled_task_tree_session(session)


def get_task_tree_for_chat_session(
    project_id: str,
    username: str,
    chat_session_id: str,
) -> ProjectChatTaskSession | None:
    normalized_project_id = _normalize_text(project_id, 80)
    normalized_username = _normalize_text(username, 80)
    normalized_chat_session_id = _normalize_text(chat_session_id, 80)
    if not (
        normalized_project_id
        and normalized_username
        and normalized_chat_session_id
    ):
        return None

    active_session = get_task_tree(
        normalized_project_id,
        normalized_username,
        normalized_chat_session_id,
    )
    if active_session is not None:
        return active_session

    raw_sessions = project_chat_task_store.list_by_project(
        normalized_project_id,
        limit=500,
    )
    matched_sessions: list[ProjectChatTaskSession] = []
    for session in raw_sessions:
        if _normalize_text(getattr(session, "username", ""), 80) != normalized_username:
            continue
        candidate_chat_session_id = _normalize_text(
            getattr(session, "chat_session_id", ""),
            80,
        )
        candidate_source_chat_session_id = _normalize_text(
            getattr(session, "source_chat_session_id", ""),
            80,
        )
        if normalized_chat_session_id not in {
            candidate_chat_session_id,
            candidate_source_chat_session_id,
        }:
            continue
        reconciled = _load_reconciled_task_tree_session(session)
        if reconciled is not None:
            matched_sessions.append(reconciled)

    if not matched_sessions:
        return None

    matched_sessions.sort(
        key=lambda item: (
            _normalize_text(getattr(item, "updated_at", ""), 40),
            _normalize_text(getattr(item, "created_at", ""), 40),
            _normalize_text(getattr(item, "id", ""), 80),
        ),
        reverse=True,
    )
    return matched_sessions[0]


def get_task_tree_by_session_id(
    project_id: str,
    username: str,
    session_id: str,
) -> ProjectChatTaskSession | None:
    normalized_project_id = _normalize_text(project_id, 80)
    normalized_username = _normalize_text(username, 80)
    normalized_session_id = _normalize_text(session_id, 80)
    if not (normalized_project_id and normalized_username and normalized_session_id):
        return None

    raw_sessions = project_chat_task_store.list_by_project(
        normalized_project_id,
        limit=500,
    )
    for session in raw_sessions:
        if _normalize_text(getattr(session, "username", ""), 80) != normalized_username:
            continue
        if _normalize_text(getattr(session, "id", ""), 80) != normalized_session_id:
            continue
        return _load_reconciled_task_tree_session(session)
    return None


def get_latest_task_tree_for_user(
    project_id: str,
    username: str,
) -> ProjectChatTaskSession | None:
    normalized_project_id = _normalize_text(project_id, 80)
    normalized_username = _normalize_text(username, 80)
    if not (normalized_project_id and normalized_username):
        return None

    raw_sessions = project_chat_task_store.list_by_project(
        normalized_project_id,
        limit=500,
    )
    matched_sessions = []
    for session in raw_sessions:
        if _normalize_text(getattr(session, "username", ""), 80) != normalized_username:
            continue
        reconciled = _load_reconciled_task_tree_session(session)
        if reconciled is not None:
            matched_sessions.append(reconciled)
    if not matched_sessions:
        return None
    matched_sessions.sort(
        key=lambda item: (
            _normalize_text(getattr(item, "updated_at", ""), 40),
            _normalize_text(getattr(item, "created_at", ""), 40),
            _normalize_text(getattr(item, "id", ""), 80),
        ),
        reverse=True,
    )
    return matched_sessions[0]


def archive_task_tree(
    session: ProjectChatTaskSession,
    *,
    reason: str,
    delete_current: bool = True,
) -> ProjectChatTaskSession:
    normalized = _recompute_session(ProjectChatTaskSession(**asdict(session)))
    archive_source_chat_session_id = (
        _normalize_text(normalized.source_chat_session_id, 80)
        or _normalize_text(normalized.chat_session_id, 80)
    )
    archive_session = ProjectChatTaskSession(
        **{
            **asdict(normalized),
            "id": project_chat_task_store.new_session_id(),
            "chat_session_id": project_chat_task_store.new_archive_chat_session_id(
                archive_source_chat_session_id
            ),
            "source_chat_session_id": archive_source_chat_session_id,
            "lifecycle_status": "archived",
            "archived_reason": _normalize_text(reason, 200),
            "archived_at": _normalize_text(_normalize_text(normalized.updated_at, 40) or "", 40)
            or _normalize_text(_normalize_text(normalized.created_at, 40) or "", 40)
            or "",
        }
    )
    if not archive_session.archived_at:
        archive_session.archived_at = archive_session.updated_at
    saved_archive = project_chat_task_store.save(archive_session)
    if delete_current:
        delete_exact = getattr(project_chat_task_store, "delete_exact", None)
        if callable(delete_exact):
            delete_exact(
                normalized.project_id,
                normalized.username,
                normalized.chat_session_id,
            )
        else:
            project_chat_task_store.delete(
                normalized.project_id,
                normalized.username,
                normalized.chat_session_id,
            )
    return saved_archive


def ensure_task_tree(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    root_goal: str,
    force: bool = False,
    max_steps: int = 6,
) -> ProjectChatTaskSession:
    existing = get_task_tree(project_id, username, chat_session_id)
    if existing is not None:
        if _can_refine_task_tree_in_place(existing, root_goal, force=force):
            refined = _refine_task_tree_in_place(
                existing,
                root_goal=root_goal,
                max_steps=max_steps,
            )
            current_node = next(
                (item for item in refined.nodes if item.id == refined.current_node_id),
                None,
            )
            next_steps = [f"当前节点：{current_node.title}"] if current_node and current_node.title else []
            _save_task_tree_progress_event(
                session=refined,
                node=current_node,
                event_type="task_tree_replanned",
                content=(
                    f"已根据最新需求重建任务计划，共 {max(len(refined.nodes) - 1, 0)} 个计划节点。"
                ),
                next_steps=next_steps,
            )
            return refined
        if not force and not _should_rebuild_task_tree_for_new_goal(existing, root_goal):
            return existing
        archive_reason = "new_goal_rebuild"
        if _normalize_status(getattr(existing, "status", "")) == "done":
            archive_reason = "completed_task_closed"
        archive_task_tree(existing, reason=archive_reason, delete_current=True)
    session = build_task_tree_session(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        root_goal=root_goal,
        max_steps=max_steps,
    )
    saved_session = project_chat_task_store.save(session)
    current_node = next(
        (item for item in saved_session.nodes if item.id == saved_session.current_node_id),
        None,
    )
    next_steps = [f"当前节点：{current_node.title}"] if current_node and current_node.title else []
    _save_task_tree_progress_event(
        session=saved_session,
        node=current_node,
        event_type="task_tree_started",
        content=f"已创建需求任务树，共 {max(len(saved_session.nodes) - 1, 0)} 个计划节点。",
        next_steps=next_steps,
    )
    return saved_session


def update_task_node(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    node_id: str,
    status: str | None = None,
    verification_result: str | None = None,
    summary_for_model: str | None = None,
    is_current: bool | None = None,
    allow_direct_completion: bool = False,
) -> ProjectChatTaskSession:
    session = get_task_tree(project_id, username, chat_session_id)
    if session is None:
        raise ValueError("task tree not found")
    nodes_by_id = {node.id: node for node in session.nodes}
    target = nodes_by_id.get(str(node_id or "").strip())
    if target is None:
        raise ValueError("task node not found")
    target_before = ProjectChatTaskNode(**asdict(target))
    previous_current_node_id = _normalize_text(session.current_node_id, 80)

    children = [node for node in session.nodes if node.parent_id == target.id]
    if verification_result is not None:
        target.verification_result = _normalize_text(verification_result, 2000)
    if summary_for_model is not None:
        target.summary_for_model = _normalize_text(summary_for_model, 1000)
    if status is not None:
        normalized_status = _normalize_status(status)
        if normalized_status == "done":
            if target.status == "pending" and not allow_direct_completion:
                raise ValueError(
                    "task must be started before completion; mark it in_progress or verifying first"
                )
            if children:
                if any(child.status != "done" for child in children):
                    raise ValueError("all child tasks must be done before parent can be completed")
                if not target.verification_result:
                    raise ValueError("parent task requires verification_result before completion")
            elif not target.verification_result:
                raise ValueError("leaf task requires verification_result before completion")
        target.status = normalized_status
    if is_current is True:
        session.current_node_id = target.id
    elif is_current is False and session.current_node_id == target.id:
        session.current_node_id = ""
    normalized_session = _recompute_session(session)
    saved_session = project_chat_task_store.save(normalized_session)
    saved_target = next((item for item in saved_session.nodes if item.id == target.id), None)
    current_node = next(
        (item for item in saved_session.nodes if item.id == saved_session.current_node_id),
        None,
    )
    verification_items = []
    if saved_target and saved_target.verification_result:
        verification_items.append(saved_target.verification_result)
    next_step_items: list[str] = []
    if current_node and saved_session.status != "done":
        if saved_target is None or current_node.id != saved_target.id:
            next_step_items.append(f"下一节点：{current_node.title}")
    event_type = "task_node_updated"
    content = (
        f"任务节点“{saved_target.title if saved_target else target_before.title}”"
        f"已更新为 {saved_target.status if saved_target else target_before.status}。"
    )
    if status is not None and _normalize_status(status) == "done":
        event_type = "task_node_completed"
        content = (
            f"任务节点“{saved_target.title if saved_target else target_before.title}”已完成并写入验证结果。"
        )
    elif status is not None and _normalize_status(status) != _normalize_status(target_before.status):
        event_type = "task_node_progressed"
    elif is_current is not None and previous_current_node_id != _normalize_text(saved_session.current_node_id, 80):
        event_type = "task_node_focused"
        content = f"当前执行节点已切换到“{saved_target.title if saved_target else target_before.title}”。"
    _save_task_tree_progress_event(
        session=saved_session,
        node=saved_target or current_node or target_before,
        event_type=event_type,
        content=content,
        verification=verification_items,
        next_steps=next_step_items,
    )
    return saved_session


def serialize_task_tree(session: ProjectChatTaskSession | None) -> dict[str, Any] | None:
    if session is None:
        return None
    normalized = _recompute_session(session)
    children_by_parent = _children_map(normalized.nodes)

    def dump_node(node: ProjectChatTaskNode) -> dict[str, Any]:
        payload = asdict(node)
        payload["node_kind"] = _normalize_text(payload.get("node_kind"), 40) or ("goal" if node.level == 0 else "plan_step")
        payload["stage_key"] = _normalize_text(payload.get("stage_key"), 80)
        payload["objective"] = _normalize_text(payload.get("objective") or payload.get("description"), 2000)
        payload["completion_criteria"] = _normalize_text(
            payload.get("completion_criteria") or payload.get("done_definition"),
            500,
        )
        payload["verification_method"] = [
            _normalize_text(item, 300)
            for item in (
                payload.get("verification_method")
                or payload.get("verification_items")
                or []
            )
            if _normalize_text(item, 300)
        ]
        payload["latest_outcome"] = _normalize_text(
            payload.get("latest_outcome")
            or payload.get("summary_for_model")
            or payload.get("verification_result"),
            1000,
        )
        payload["is_root"] = bool(node.level == 0)
        payload["children"] = [dump_node(child) for child in children_by_parent.get(node.id, [])]
        return payload

    tree = [dump_node(node) for node in children_by_parent.get("", [])]
    current_node = next(
        (dump_node(node) for node in normalized.nodes if node.id == normalized.current_node_id),
        None,
    )
    leaf_nodes = [node for node in normalized.nodes if not children_by_parent.get(node.id)]
    done_leaf_total = len([node for node in leaf_nodes if node.status == "done"])
    return {
        "id": normalized.id,
        "project_id": normalized.project_id,
        "username": normalized.username,
        "chat_session_id": normalized.chat_session_id,
        "source_chat_session_id": normalized.source_chat_session_id,
        "record_kind": normalized.record_kind,
        "source_session_id": normalized.source_session_id,
        "round_index": normalized.round_index,
        "title": normalized.title,
        "root_goal": normalized.root_goal,
        "status": normalized.status,
        "lifecycle_status": normalized.lifecycle_status,
        "is_archived": normalized.lifecycle_status == "archived",
        "archived_reason": normalized.archived_reason,
        "archived_at": normalized.archived_at,
        "current_node_id": normalized.current_node_id,
        "progress_percent": normalized.progress_percent,
        "nodes": [asdict(node) for node in normalized.nodes],
        "tree": tree,
        "current_node": current_node,
        "stats": {
            "node_total": len(normalized.nodes),
            "leaf_total": len(leaf_nodes),
            "done_leaf_total": done_leaf_total,
        },
        "model_context_summary": build_task_tree_prompt(normalized),
        "created_at": normalized.created_at,
        "updated_at": normalized.updated_at,
    }


def build_task_tree_prompt(session: ProjectChatTaskSession | None) -> str:
    if session is None:
        return ""
    normalized = _recompute_session(session)
    if not normalized.nodes:
        return ""
    lines = [
        "当前对话存在结构化任务树，请严格以该状态推进执行，不要重复回到已经完成的节点。",
        f"总目标：{normalized.root_goal or normalized.title or '-'}",
        f"整体状态：{normalized.status}，进度：{normalized.progress_percent}%",
        "任务树节点必须直接描述面向用户目标的工作步骤，例如分析现状、实现改动、验证结果。",
        "不要把 search_project_context、query_project_rules、search_ids、get_manual_content、resolve_relevant_context、generate_execution_plan 这类内部检索或规划工具直接写成任务节点。",
        "不要把候选代理工具、脚本路径或类似“Auto inferred proxy entry from scripts/... ”的描述当成任务节点。",
        "如果当前节点看起来像内部工具名、规则检索步骤或候选脚本，而不是面向需求的步骤，应按用户目标重述为真正的工作步骤后再继续执行。",
        "当你开始某个节点时，优先调用 update_task_node_status 标记为 in_progress 或 verifying。",
        "当你完成某个节点时，必须调用 complete_task_node_with_verification 写入验证结果后再完成节点。",
        "如需确认当前任务结构或节点 ID，先调用 get_current_task_tree。",
    ]
    if _is_lookup_query_goal(normalized.root_goal or normalized.title):
        lines.append("该目标属于查询型问题，应优先检索并直接回答；不要额外拆成实现、协作开发或无关规则节点。")
    current_node = next((node for node in normalized.nodes if node.id == normalized.current_node_id), None)
    if current_node is not None:
        lines.append(
            f"当前焦点节点：{current_node.title} [{current_node.status}]"
        )
        if current_node.description:
            lines.append(f"当前节点说明：{current_node.description}")
        if current_node.verification_items:
            lines.append(
                "当前节点完成前必须验证："
                + "；".join(current_node.verification_items[:4])
            )
        if current_node.verification_result:
            lines.append(f"当前节点已记录验证：{current_node.verification_result}")
    lines.append("任务树摘要：")
    for node in normalized.nodes:
        if node.level == 0:
            continue
        indent = "  " * max(node.level - 1, 0)
        summary = node.summary_for_model or node.description
        if summary:
            lines.append(f"- {indent}{node.title} [{node.status}] {summary}")
        else:
            lines.append(f"- {indent}{node.title} [{node.status}]")
    return "\n".join(lines)[:4000]


def get_task_tree_tool_payload(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
) -> dict[str, Any]:
    session = get_task_tree_for_chat_session(project_id, username, chat_session_id)
    payload = serialize_task_tree(session)
    if payload is None:
        return {"error": "task tree not found"}
    return payload


def update_task_tree_node_tool_payload(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    node_id: str,
    status: str,
    verification_result: str = "",
    summary_for_model: str = "",
    is_current: bool | None = None,
) -> dict[str, Any]:
    session = update_task_node(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        node_id=node_id,
        status=status,
        verification_result=verification_result,
        summary_for_model=summary_for_model,
        is_current=is_current,
    )
    node_id_value = str(node_id or "").strip()
    if _normalize_status(getattr(session, "status", "")) == "done":
        archived_session = archive_task_tree(
            session,
            reason="completed_task_closed",
            delete_current=True,
        )
        archived_payload = serialize_task_tree(archived_session) or {}
        return {
            "status": "updated",
            "node_id": node_id_value,
            "task_tree": None,
            "history_task_tree": archived_payload,
            "history_session_id": str(archived_payload.get("id") or "").strip(),
            "chat_session_id": _normalize_text(session.chat_session_id, 80),
            "source_chat_session_id": _normalize_text(
                archived_payload.get("source_chat_session_id") or session.chat_session_id,
                80,
            ),
        }
    payload = serialize_task_tree(session) or {}
    payload["status"] = "updated"
    payload["node_id"] = node_id_value
    return payload


def complete_task_tree_node_tool_payload(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    node_id: str,
    verification_result: str,
    summary_for_model: str = "",
    is_current: bool | None = None,
) -> dict[str, Any]:
    session = update_task_node(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        node_id=node_id,
        status="done",
        verification_result=verification_result,
        summary_for_model=summary_for_model,
        is_current=is_current,
    )
    node_id_value = str(node_id or "").strip()
    if _normalize_status(getattr(session, "status", "")) == "done":
        archived_session = archive_task_tree(
            session,
            reason="completed_task_closed",
            delete_current=True,
        )
        archived_payload = serialize_task_tree(archived_session) or {}
        return {
            "status": "completed",
            "node_id": node_id_value,
            "task_tree": None,
            "history_task_tree": archived_payload,
            "history_session_id": str(archived_payload.get("id") or "").strip(),
            "chat_session_id": _normalize_text(session.chat_session_id, 80),
            "source_chat_session_id": _normalize_text(
                archived_payload.get("source_chat_session_id") or session.chat_session_id,
                80,
            ),
        }
    payload = serialize_task_tree(session) or {}
    payload["status"] = "completed"
    payload["node_id"] = node_id_value
    return payload


def list_project_task_tree_summaries(project_id: str, limit: int = 200) -> list[dict[str, Any]]:
    normalized_project_id = _normalize_text(project_id, 80)
    safe_limit = max(1, min(int(limit or 200), 500))
    if not normalized_project_id:
        return []
    raw_sessions = project_chat_task_store.list_by_project(normalized_project_id, safe_limit)
    items: list[dict[str, Any]] = []
    for session in raw_sessions:
        payload = serialize_task_tree(_load_reconciled_task_tree_session(session))
        if not isinstance(payload, dict):
            continue
        current_node = payload.get("current_node") or {}
        stats = payload.get("stats") or {}
        items.append(
            {
                "id": str(payload.get("id") or "").strip(),
                "project_id": str(payload.get("project_id") or "").strip(),
                "username": str(payload.get("username") or "").strip(),
                "chat_session_id": str(payload.get("chat_session_id") or "").strip(),
                "source_chat_session_id": str(payload.get("source_chat_session_id") or "").strip(),
                "title": str(payload.get("title") or "").strip(),
                "root_goal": str(payload.get("root_goal") or "").strip(),
                "status": _normalize_status(payload.get("status")),
                "lifecycle_status": str(payload.get("lifecycle_status") or "active").strip(),
                "is_archived": bool(payload.get("is_archived")),
                "archived_reason": str(payload.get("archived_reason") or "").strip(),
                "archived_at": str(payload.get("archived_at") or "").strip(),
                "progress_percent": int(payload.get("progress_percent") or 0),
                "current_node_id": str(payload.get("current_node_id") or "").strip(),
                "current_node_title": str(current_node.get("title") or "").strip(),
                "current_node_status": _normalize_status(current_node.get("status")),
                "leaf_total": int(stats.get("leaf_total") or 0),
                "done_leaf_total": int(stats.get("done_leaf_total") or 0),
                "node_total": int(stats.get("node_total") or 0),
                "created_at": str(payload.get("created_at") or "").strip(),
                "updated_at": str(payload.get("updated_at") or "").strip(),
            }
        )
    return sorted(
        items,
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("created_at") or ""),
        ),
        reverse=True,
    )[:safe_limit]


def audit_task_tree_round(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    assistant_content: str,
    successful_tool_names: list[str] | None = None,
    task_tree_tool_used: bool = False,
) -> dict[str, Any] | None:
    normalized_project_id = _normalize_text(project_id, 80)
    normalized_username = _normalize_text(username, 80)
    normalized_chat_session_id = _normalize_text(chat_session_id, 80)
    if not (normalized_project_id and normalized_username and normalized_chat_session_id):
        return None

    session = get_task_tree(normalized_project_id, normalized_username, normalized_chat_session_id)
    if session is None:
        return None

    serialized_before = serialize_task_tree(session) or {}
    current_node_before = serialized_before.get("current_node") or {}
    current_node_id = _normalize_text(current_node_before.get("id"), 80)
    current_status = _normalize_status(current_node_before.get("status"))
    if not current_node_id or current_status == "done":
        return None

    normalized_content = _normalize_text(assistant_content, 4000).lower()
    completion_signal = _has_completion_signal(normalized_content)
    verification_signal = _has_verification_signal(normalized_content)
    has_substantive_answer = _has_substantive_answer(assistant_content)

    deduped_tool_names: list[str] = []
    for item in successful_tool_names or []:
        normalized_tool_name = _normalize_text(item, 120)
        if normalized_tool_name and normalized_tool_name not in deduped_tool_names:
            deduped_tool_names.append(normalized_tool_name)
    non_task_tree_tool_names = [
        item for item in deduped_tool_names if item not in _TASK_TREE_TOOL_NAMES
    ]
    normalized_task_tree_tool_used = bool(task_tree_tool_used) or any(
        item in _TASK_TREE_TOOL_NAMES for item in deduped_tool_names
    )
    embedded_task_tree_call = None
    recovered_embedded_task_call = False
    if not normalized_task_tree_tool_used:
        embedded_task_tree_call = _extract_embedded_task_tree_tool_call(assistant_content)
        if isinstance(embedded_task_tree_call, dict):
            embedded_tool_name = _normalize_text(embedded_task_tree_call.get("tool_name"), 120)
            embedded_args = embedded_task_tree_call.get("args") or {}
            embedded_node_id = _normalize_text(embedded_args.get("node_id"), 80)
            if embedded_tool_name == "complete_task_node_with_verification" and embedded_node_id:
                session = update_task_node(
                    project_id=normalized_project_id,
                    username=normalized_username,
                    chat_session_id=normalized_chat_session_id,
                    node_id=embedded_node_id,
                    status="done",
                    verification_result=_normalize_text(embedded_args.get("verification_result"), 2000),
                    summary_for_model=_normalize_text(embedded_args.get("summary_for_model"), 1000),
                    allow_direct_completion=True,
                )
                recovered_embedded_task_call = True
                normalized_task_tree_tool_used = True
            elif embedded_tool_name == "update_task_node_status" and embedded_node_id:
                session = update_task_node(
                    project_id=normalized_project_id,
                    username=normalized_username,
                    chat_session_id=normalized_chat_session_id,
                    node_id=embedded_node_id,
                    status=_normalize_text(embedded_args.get("status"), 40) or "in_progress",
                    verification_result=_normalize_text(embedded_args.get("verification_result"), 2000),
                    summary_for_model=_normalize_text(embedded_args.get("summary_for_model"), 1000),
                    allow_direct_completion=True,
                )
                recovered_embedded_task_call = True
                normalized_task_tree_tool_used = True

    if not (completion_signal or verification_signal or non_task_tree_tool_names):
        if not recovered_embedded_task_call:
            return None

    suggested_status = "verifying" if (completion_signal or verification_signal) else "in_progress"
    auto_updated = False
    auto_completed_bootstrap = False
    if not normalized_task_tree_tool_used:
        if (
            "search_project_context" in non_task_tree_tool_names
            and not (completion_signal or verification_signal)
            and current_status != "done"
            and _is_context_bootstrap_node(current_node_before)
        ):
            audit_summary = "系统审计：已成功执行 search_project_context，当前上下文预检节点自动完成并推进到下一节点。"
            session = update_task_node(
                project_id=normalized_project_id,
                username=normalized_username,
                chat_session_id=normalized_chat_session_id,
                node_id=current_node_id,
                status="done",
                verification_result="系统自动验证：已成功调用 search_project_context 完成项目上下文、成员、规则与 MCP 能力预检。",
                summary_for_model=_merge_summary_for_model(
                    current_node_before.get("summary_for_model") or "",
                    audit_summary,
                ),
                allow_direct_completion=True,
            )
            auto_updated = True
            auto_completed_bootstrap = True
        elif _should_promote_status(current_status, suggested_status):
            audit_summary = (
                "系统审计：检测到本轮已有执行进展，但未写入完成验证，暂不自动推荐完成。"
            )
            session = update_task_node(
                project_id=normalized_project_id,
                username=normalized_username,
                chat_session_id=normalized_chat_session_id,
                node_id=current_node_id,
                status=suggested_status,
                summary_for_model=_merge_summary_for_model(
                    current_node_before.get("summary_for_model") or "",
                    audit_summary,
                ),
            )
            auto_updated = True

    archived_payload = None
    lookup_answer_tool_used = any(
        item not in _LOOKUP_QUERY_NON_ANSWER_TOOL_NAMES for item in non_task_tree_tool_names
    )
    if (
        _is_lookup_query_goal(session.root_goal or session.title)
        and has_substantive_answer
        and (
            lookup_answer_tool_used
            or normalized_task_tree_tool_used
            or recovered_embedded_task_call
        )
    ):
        session, archived_payload = _auto_complete_lookup_query_session(
            session=session,
            project_id=normalized_project_id,
            username=normalized_username,
            chat_session_id=normalized_chat_session_id,
            assistant_content=assistant_content,
            successful_tool_names=deduped_tool_names,
        )
        auto_updated = True

    serialized_after = serialize_task_tree(session) or serialized_before
    current_node_after = serialized_after.get("current_node") or current_node_before
    current_status_after = _normalize_status(current_node_after.get("status"))

    code = ""
    message = ""
    if archived_payload is not None:
        code = "lookup_query_auto_completed"
        message = ""
    elif recovered_embedded_task_call:
        code = "embedded_task_call_recovered"
        message = ""
    elif auto_completed_bootstrap:
        code = "bootstrap_step_auto_completed"
        message = "检测到本轮已完成项目上下文预检，系统已自动完成当前上下文节点并推进到下一节点。"
    elif completion_signal and current_status_after != "done":
        code = "completion_unverified"
        message = "检测到本轮存在完成表述，但当前节点还没有完成验证，系统未自动推荐完成。"
    elif not normalized_task_tree_tool_used and (
        verification_signal or non_task_tree_tool_names or auto_updated
    ):
        code = "progress_not_written_back"
        message = "检测到本轮已有执行进展，但任务树没有完整回写，当前节点已保持在继续执行或验证中。"
    if not code:
        return None

    return {
        "status": "resolved" if not message else "attention",
        "code": code,
        "message": message,
        "auto_updated": auto_updated,
        "suggested_status": suggested_status,
        "completion_signal_detected": completion_signal,
        "verification_signal_detected": verification_signal,
        "executed_tool_names": non_task_tree_tool_names[:6],
        "current_node": current_node_after,
        "task_tree": serialized_after if archived_payload is None else None,
        "history_task_tree": archived_payload,
    }
