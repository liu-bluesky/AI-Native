"""Project collaboration planning and execution helpers."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from core.deps import project_store
from services.dynamic_mcp_context import (
    get_project_detail_runtime,
    get_project_employee_detail_runtime,
    search_project_context_runtime,
)
from services.project_chat_task_tree import (
    complete_task_tree_node_tool_payload,
    ensure_task_tree,
    get_task_tree_tool_payload,
    serialize_task_tree,
    update_task_tree_node_tool_payload,
)
from services.dynamic_mcp_external_tools import list_project_external_tools_runtime
from services.dynamic_mcp_profiles import (
    list_project_member_profiles_runtime,
    query_project_members_runtime,
    query_project_rules_runtime,
)
from services.dynamic_mcp_skill_proxies import list_project_proxy_tools_runtime

COLLABORATION_TOOL_NAME = "execute_project_collaboration"
_TEXT_ARG_CANDIDATES = (
    "task",
    "message",
    "prompt",
    "query",
    "keyword",
    "requirement",
    "request",
    "content",
    "question",
    "text",
    "description",
    "input",
)
_PROJECT_NAME_ARG_CANDIDATES = ("project_name", "repo_name", "repository_name")
_EMPLOYEE_IDS_ARG_CANDIDATES = ("employee_ids", "member_ids", "selected_employee_ids")
_MEMBER_CONTEXT_ARG_CANDIDATES = ("selected_members", "members", "member_context")
_PROJECT_CONTEXT_ARG_CANDIDATES = ("project_context", "execution_context", "context_payload")
_IMPLEMENTATION_TASK_HINTS = (
    "代码",
    "开发",
    "实现",
    "修改",
    "修复",
    "新增",
    "增加",
    "调整",
    "改",
    "页面",
    "前端",
    "后端",
    "接口",
    "重构",
    "测试",
    "构建",
    "code",
    "implement",
    "fix",
    "edit",
    "patch",
    "refactor",
    "frontend",
    "backend",
    "api",
    "test",
    "build",
)
_EXTERNAL_EXECUTOR_HINTS = (
    "agent",
    "execute",
    "executor",
    "task",
    "workflow",
    "orchestr",
    "run",
    "code",
    "edit",
    "patch",
    "apply",
    "workspace",
    "repo",
    "执行",
    "任务",
    "编排",
    "代码",
    "修改",
    "文件",
    "工作区",
)
_EXTERNAL_TERMINAL_EXECUTOR_HINTS = (
    "agent",
    "execute",
    "executor",
    "workflow",
    "orchestr",
    "code",
    "edit",
    "patch",
    "apply",
    "workspace",
    "repo",
    "执行",
    "编排",
    "代码",
    "修改",
    "工作区",
)
_TASK_TERM_RE = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")
_TASK_TREE_BUILTIN_TOOL_NAMES = {
    "get_current_task_tree",
    "update_task_node_status",
    "complete_task_node_with_verification",
}


def collaboration_tool_descriptor(employee_id: str = "") -> dict[str, Any]:
    employee_id_value = str(employee_id or "").strip()
    return {
        "tool_name": COLLABORATION_TOOL_NAME,
        "employee_id": employee_id_value,
        "base_tool_name": COLLABORATION_TOOL_NAME,
        "scoped_tool_name": COLLABORATION_TOOL_NAME,
        "skill_id": "__builtin__",
        "entry_name": COLLABORATION_TOOL_NAME,
        "script_type": "builtin",
        "description": (
            "项目协作编排工具。输入用户任务后，结合项目成员、规则和工具生成协作步骤，"
            "并在可安全映射参数时自动执行。"
        ),
        "builtin": True,
        "parameters_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "必填，用户原始任务描述。",
                },
                "employee_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选，限制协作员工范围。",
                },
                "max_employees": {
                    "type": "integer",
                    "description": "可选，最多纳入协作范围的员工数量，默认 3。",
                },
                "max_tool_calls": {
                    "type": "integer",
                    "description": "可选，最多自动执行的工具调用次数，默认 6。",
                },
                "auto_execute": {
                    "type": "boolean",
                    "description": "是否自动执行可安全映射参数的工具，默认 true。",
                },
                "include_external_tools": {
                    "type": "boolean",
                    "description": "是否把项目外部 MCP 工具纳入候选范围，默认 true。",
                },
            },
            "required": ["task"],
        },
    }


def parse_object_args(
    args: dict[str, Any] | None = None,
    args_json: str = "{}",
) -> tuple[dict[str, Any] | None, str]:
    if args is not None:
        if not isinstance(args, dict):
            return None, "args must be an object"
        return args, ""
    try:
        payload = json.loads(args_json or "{}")
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"Invalid args_json: {exc}"
    if not isinstance(payload, dict):
        return None, "args_json must be a JSON object"
    return payload, ""


def _looks_like_implementation_task(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in _IMPLEMENTATION_TASK_HINTS)


def _looks_like_execution_tool(tool_name: str) -> bool:
    lowered = str(tool_name or "").strip().lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in _EXTERNAL_EXECUTOR_HINTS)


def extract_execution_task_text(
    tool_name: str,
    *,
    args: dict[str, Any] | None = None,
    args_json: str = "{}",
) -> str:
    normalized_tool_name = str(tool_name or "").strip()
    if not normalized_tool_name or normalized_tool_name in _TASK_TREE_BUILTIN_TOOL_NAMES:
        return ""
    payload, _ = parse_object_args(args=args, args_json=args_json)
    if payload is None:
        return ""
    task_text = ""
    for key in _TEXT_ARG_CANDIDATES:
        value = payload.get(key)
        if isinstance(value, str) and str(value).strip():
            task_text = str(value).strip()
            break
    if not task_text:
        return ""
    if normalized_tool_name == COLLABORATION_TOOL_NAME:
        return task_text
    if _looks_like_implementation_task(task_text) or _looks_like_execution_tool(normalized_tool_name):
        return task_text
    return ""


def ensure_project_execution_task_tree(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    root_goal: str,
) -> dict[str, Any] | None:
    normalized_project_id = str(project_id or "").strip()
    normalized_username = str(username or "").strip()
    normalized_chat_session_id = str(chat_session_id or "").strip()
    normalized_goal = str(root_goal or "").strip()
    if not (
        normalized_project_id
        and normalized_username
        and normalized_chat_session_id
        and normalized_goal
    ):
        return None
    session = ensure_task_tree(
        project_id=normalized_project_id,
        username=normalized_username,
        chat_session_id=normalized_chat_session_id,
        root_goal=normalized_goal,
    )
    return serialize_task_tree(session)


def attach_task_tree_context(
    result: Any,
    *,
    task_tree_payload: dict[str, Any] | None,
    username: str,
    chat_session_id: str,
) -> Any:
    if not isinstance(result, dict) or not isinstance(task_tree_payload, dict):
        return result
    enriched = dict(result)
    enriched.setdefault("username", str(username or "").strip())
    enriched.setdefault("chat_session_id", str(chat_session_id or "").strip())
    if not isinstance(enriched.get("task_tree"), dict):
        enriched["task_tree"] = task_tree_payload
    return enriched


def _clean_text(value: Any, limit: int = 1000) -> str:
    return str(value or "").strip()[:limit]


def _task_tree_step_nodes(task_tree_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(task_tree_payload, dict):
        return []
    nodes = [
        item
        for item in list(task_tree_payload.get("nodes") or [])
        if isinstance(item, dict) and int(item.get("level") or 0) > 0
    ]
    return sorted(
        nodes,
        key=lambda item: (
            int(item.get("level") or 0),
            int(item.get("sort_order") or 0),
            _clean_text(item.get("id"), 80),
        ),
    )


def _task_tree_root_node_id(task_tree_payload: dict[str, Any] | None) -> str:
    if not isinstance(task_tree_payload, dict):
        return ""
    root = next(
        (
            item
            for item in list(task_tree_payload.get("nodes") or [])
            if isinstance(item, dict) and int(item.get("level") or 0) == 0
        ),
        None,
    )
    return _clean_text((root or {}).get("id"), 80)


def _resolve_task_tree_step_node_id(
    task_tree_payload: dict[str, Any] | None,
    step: dict[str, Any],
    step_index: int,
) -> str:
    ordered_nodes = _task_tree_step_nodes(task_tree_payload)
    if 0 <= step_index < len(ordered_nodes):
        return _clean_text(ordered_nodes[step_index].get("id"), 80)
    candidate_titles = [
        _clean_text(step.get("step"), 160),
        _clean_text(step.get("title"), 160),
        _clean_text(step.get("reason"), 160),
        _clean_text(step.get("tool_name"), 160),
    ]
    for node in ordered_nodes:
        node_title = _clean_text(node.get("title"), 160)
        if node_title and node_title in candidate_titles:
            return _clean_text(node.get("id"), 80)
    current_node = task_tree_payload.get("current_node") if isinstance(task_tree_payload, dict) else None
    return _clean_text((current_node or {}).get("id"), 80)


def _extract_task_tree_payloads(sync_payload: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(sync_payload, dict):
        return None, None
    history_payload = (
        sync_payload.get("history_task_tree")
        if isinstance(sync_payload.get("history_task_tree"), dict)
        else None
    )
    current_payload = (
        sync_payload.get("task_tree")
        if isinstance(sync_payload.get("task_tree"), dict)
        else None
    )
    if current_payload is None and (
        isinstance(sync_payload.get("nodes"), list)
        or "progress_percent" in sync_payload
        or "current_node_id" in sync_payload
    ):
        current_payload = sync_payload
    return current_payload, history_payload


def _sync_task_tree_payloads(
    sync_payload: Any,
    current_task_tree: dict[str, Any] | None,
    history_task_tree: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current_payload, history_payload = _extract_task_tree_payloads(sync_payload)
    if history_payload is not None:
        return None, history_payload
    if current_payload is not None:
        return current_payload, history_task_tree
    return current_task_tree, history_task_tree


def _summarize_tool_result(result: Any) -> str:
    if isinstance(result, dict):
        preview_parts: list[str] = []
        for key in ("message", "status", "summary", "detail", "reason", "tool_name"):
            value = _clean_text(result.get(key), 200)
            if value:
                preview_parts.append(f"{key}={value}")
        if preview_parts:
            return "；".join(preview_parts)[:300]
        filtered = {
            key: value
            for key, value in result.items()
            if key
            not in {
                "task_tree",
                "history_task_tree",
                "executed_calls",
                "skipped_calls",
                "candidate_tools",
                "plan_steps",
            }
        }
        return _clean_text(json.dumps(filtered, ensure_ascii=False), 300)
    return _clean_text(result, 300)


def _build_step_verification_result(step: dict[str, Any], result: Any, *, note: str = "") -> str:
    step_label = _clean_text(
        step.get("step") or step.get("title") or step.get("reason") or step.get("tool_name"),
        160,
    ) or "当前步骤"
    tool_name = _clean_text(step.get("tool_name"), 120)
    result_preview = _summarize_tool_result(result)
    parts = [f"系统自动验证：已按规划执行步骤“{step_label}”。"]
    if tool_name:
        parts.append(f"工具：{tool_name}。")
    if note:
        parts.append(_clean_text(note, 240))
    if result_preview:
        parts.append(f"结果摘要：{result_preview}")
    return " ".join(parts)[:1800]


def _build_root_verification_result(
    task: str,
    executed_calls: list[dict[str, Any]],
    *,
    halt_reason: str = "",
) -> str:
    tool_names = [
        _clean_text(item.get("tool_name"), 120)
        for item in executed_calls
        if _clean_text(item.get("tool_name"), 120)
    ]
    parts = [f"系统自动验证：协作任务“{_clean_text(task, 200)}”已按当前规划收口。"]
    if tool_names:
        parts.append(f"执行工具：{', '.join(tool_names[:6])}。")
    if halt_reason:
        parts.append(f"结束原因：{_clean_text(halt_reason, 120)}。")
    return " ".join(parts)[:1800]


def _mark_task_tree_step_started(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    task_tree_payload: dict[str, Any] | None,
    history_task_tree: dict[str, Any] | None,
    step: dict[str, Any],
    step_index: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    node_id = _resolve_task_tree_step_node_id(task_tree_payload, step, step_index)
    if not node_id:
        return task_tree_payload, history_task_tree
    sync_payload = update_task_tree_node_tool_payload(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        node_id=node_id,
        status="in_progress",
        summary_for_model=_clean_text(
            step.get("reason") or step.get("step") or step.get("tool_name"),
            240,
        ),
        is_current=True,
    )
    return _sync_task_tree_payloads(sync_payload, task_tree_payload, history_task_tree)


def _mark_task_tree_step_blocked(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    task_tree_payload: dict[str, Any] | None,
    history_task_tree: dict[str, Any] | None,
    step: dict[str, Any],
    step_index: int,
    result: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    node_id = _resolve_task_tree_step_node_id(task_tree_payload, step, step_index)
    if not node_id:
        return task_tree_payload, history_task_tree
    sync_payload = update_task_tree_node_tool_payload(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        node_id=node_id,
        status="blocked",
        summary_for_model=_build_step_verification_result(
            step,
            result,
            note="本步骤执行失败，任务树已保留阻塞状态。",
        ),
        is_current=True,
    )
    return _sync_task_tree_payloads(sync_payload, task_tree_payload, history_task_tree)


def _mark_task_tree_step_completed(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    task_tree_payload: dict[str, Any] | None,
    history_task_tree: dict[str, Any] | None,
    step: dict[str, Any],
    step_index: int,
    result: Any,
    note: str = "",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    node_id = _resolve_task_tree_step_node_id(task_tree_payload, step, step_index)
    if not node_id:
        return task_tree_payload, history_task_tree
    sync_payload = complete_task_tree_node_tool_payload(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        node_id=node_id,
        verification_result=_build_step_verification_result(step, result, note=note),
        summary_for_model=_clean_text(
            step.get("reason") or step.get("step") or step.get("tool_name"),
            240,
        ),
        is_current=True,
    )
    return _sync_task_tree_payloads(sync_payload, task_tree_payload, history_task_tree)


def _mark_task_tree_root_completed_if_ready(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    task: str,
    task_tree_payload: dict[str, Any] | None,
    history_task_tree: dict[str, Any] | None,
    executed_calls: list[dict[str, Any]],
    halt_reason: str = "",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(task_tree_payload, dict):
        return task_tree_payload, history_task_tree
    step_nodes = _task_tree_step_nodes(task_tree_payload)
    if not step_nodes or any(_clean_text(item.get("status"), 40) != "done" for item in step_nodes):
        return task_tree_payload, history_task_tree
    root_node_id = _task_tree_root_node_id(task_tree_payload)
    if not root_node_id:
        return task_tree_payload, history_task_tree
    sync_payload = complete_task_tree_node_tool_payload(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        node_id=root_node_id,
        verification_result=_build_root_verification_result(
            task,
            executed_calls,
            halt_reason=halt_reason,
        ),
        summary_for_model=_clean_text(task, 240),
        is_current=False,
    )
    return _sync_task_tree_payloads(sync_payload, task_tree_payload, history_task_tree)


def _auto_complete_remaining_task_tree_steps(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    task_tree_payload: dict[str, Any] | None,
    history_task_tree: dict[str, Any] | None,
    plan_steps: list[dict[str, Any]],
    start_index: int,
    result: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    working_task_tree = task_tree_payload
    working_history = history_task_tree
    for step_index in range(max(0, start_index), len(plan_steps)):
        step = plan_steps[step_index]
        working_task_tree, working_history = _mark_task_tree_step_completed(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            task_tree_payload=working_task_tree,
            history_task_tree=working_history,
            step=step,
            step_index=step_index,
            result=result,
            note="当前整体任务已由上一步主执行器完成，本候选步骤自动收口，不再单独执行。",
        )
        if working_history is not None:
            break
    return working_task_tree, working_history


def invoke_project_builtin_tool(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
    *,
    username: str = "",
    chat_session_id: str = "",
    args: dict[str, Any] | None = None,
    args_json: str = "{}",
) -> dict[str, Any] | None:
    normalized_tool_name = str(tool_name or "").strip()
    employee_id_value = str(employee_id or "").strip()

    if normalized_tool_name == "query_project_rules":
        payload, err = parse_object_args(args=args, args_json=args_json)
        if payload is None:
            return {"error": err}
        keyword = str(payload.get("keyword") or "").strip()
        target_employee_id = str(payload.get("employee_id") or employee_id_value).strip()
        result = query_project_rules_runtime(
            project_id=project_id,
            keyword=keyword,
            employee_id=target_employee_id,
        )
        return {
            "tool_name": "query_project_rules",
            "employee_id": target_employee_id,
            "result": result,
            "total": len(result),
        }

    if normalized_tool_name == "query_project_members":
        result = query_project_members_runtime(project_id)
        if isinstance(result, dict):
            return {
                "tool_name": "query_project_members",
                "employee_id": employee_id_value,
                **result,
            }
        return {
            "tool_name": "query_project_members",
            "employee_id": employee_id_value,
            "result": result,
        }

    if normalized_tool_name == "search_project_context":
        payload, err = parse_object_args(args=args, args_json=args_json)
        if payload is None:
            return {"error": err}
        scope_value = str(payload.get("scope") or "all").strip()
        keyword_value = str(payload.get("keyword") or "").strip()
        target_employee_id = str(payload.get("employee_id") or employee_id_value).strip()
        limit_value = payload.get("limit", 20)
        result = search_project_context_runtime(
            project_id=project_id,
            scope=scope_value,
            keyword=keyword_value,
            employee_id=target_employee_id,
            limit=limit_value,
        )
        return {
            "tool_name": "search_project_context",
            "employee_id": target_employee_id,
            **result,
        }

    if normalized_tool_name == "get_project_detail":
        result = get_project_detail_runtime(project_id)
        return {
            "tool_name": "get_project_detail",
            "employee_id": employee_id_value,
            **result,
        }

    if normalized_tool_name == "get_project_employee_detail":
        payload, err = parse_object_args(args=args, args_json=args_json)
        if payload is None:
            return {"error": err}
        target_employee_id = str(payload.get("employee_id") or employee_id_value).strip()
        result = get_project_employee_detail_runtime(project_id, target_employee_id)
        return {
            "tool_name": "get_project_employee_detail",
            "employee_id": target_employee_id,
            **result,
        }

    if normalized_tool_name == "get_current_task_tree":
        payload, err = parse_object_args(args=args, args_json=args_json)
        if payload is None:
            return {"error": err}
        target_chat_session_id = str(payload.get("chat_session_id") or chat_session_id).strip()
        target_username = str(payload.get("username") or username).strip()
        if not target_chat_session_id:
            return {"error": "chat_session_id is required"}
        if not target_username:
            return {"error": "username is required"}
        result = get_task_tree_tool_payload(
            project_id=project_id,
            username=target_username,
            chat_session_id=target_chat_session_id,
        )
        return {
            "tool_name": "get_current_task_tree",
            "employee_id": employee_id_value,
            **result,
        }

    if normalized_tool_name == "update_task_node_status":
        payload, err = parse_object_args(args=args, args_json=args_json)
        if payload is None:
            return {"error": err}
        target_chat_session_id = str(payload.get("chat_session_id") or chat_session_id).strip()
        target_username = str(payload.get("username") or username).strip()
        node_id = str(payload.get("node_id") or "").strip()
        status_value = str(payload.get("status") or "").strip()
        if not target_chat_session_id:
            return {"error": "chat_session_id is required"}
        if not target_username:
            return {"error": "username is required"}
        if not node_id:
            return {"error": "node_id is required"}
        if not status_value:
            return {"error": "status is required"}
        try:
            result = update_task_tree_node_tool_payload(
                project_id=project_id,
                username=target_username,
                chat_session_id=target_chat_session_id,
                node_id=node_id,
                status=status_value,
                verification_result=str(payload.get("verification_result") or ""),
                summary_for_model=str(payload.get("summary_for_model") or ""),
                is_current=payload.get("is_current"),
            )
        except ValueError as exc:
            return {"error": str(exc)}
        return {
            "tool_name": "update_task_node_status",
            "employee_id": employee_id_value,
            **result,
        }

    if normalized_tool_name == "complete_task_node_with_verification":
        payload, err = parse_object_args(args=args, args_json=args_json)
        if payload is None:
            return {"error": err}
        target_chat_session_id = str(payload.get("chat_session_id") or chat_session_id).strip()
        target_username = str(payload.get("username") or username).strip()
        node_id = str(payload.get("node_id") or "").strip()
        verification_result = str(payload.get("verification_result") or "").strip()
        if not target_chat_session_id:
            return {"error": "chat_session_id is required"}
        if not target_username:
            return {"error": "username is required"}
        if not node_id:
            return {"error": "node_id is required"}
        if not verification_result:
            return {"error": "verification_result is required"}
        try:
            result = complete_task_tree_node_tool_payload(
                project_id=project_id,
                username=target_username,
                chat_session_id=target_chat_session_id,
                node_id=node_id,
                verification_result=verification_result,
                summary_for_model=str(payload.get("summary_for_model") or ""),
                is_current=payload.get("is_current"),
            )
        except ValueError as exc:
            return {"error": str(exc)}
        return {
            "tool_name": "complete_task_node_with_verification",
            "employee_id": employee_id_value,
            **result,
        }

    return None


def _task_terms(task: str) -> list[str]:
    lowered = str(task or "").strip().lower()
    if not lowered:
        return []
    seen: set[str] = set()
    terms: list[str] = []
    for match in _TASK_TERM_RE.findall(lowered):
        term = str(match or "").strip()
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _score_against_task(task: str, values: list[Any] | tuple[Any, ...]) -> int:
    lowered_task = str(task or "").strip().lower()
    if not lowered_task:
        return 0
    terms = _task_terms(lowered_task)
    score = 0
    for raw in values:
        text = str(raw or "").strip().lower()
        if not text:
            continue
        if lowered_task in text:
            score += 12
        elif text in lowered_task and len(text) >= 2:
            score += 6
        for term in terms:
            if term in text:
                score += 4 if len(term) >= 4 else 2
    return score


def _normalize_employee_ids(employee_ids: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in employee_ids or []:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _looks_like_implementation_task(task: str) -> bool:
    lowered = str(task or "").strip().lower()
    if not lowered:
        return False
    return any(term in lowered for term in _IMPLEMENTATION_TASK_HINTS)


def _tool_joined_text(tool: dict[str, Any]) -> str:
    return " ".join(str(part or "").strip().lower() for part in _tool_text(tool) if str(part or "").strip())


def _external_executor_bonus(task: str, tool: dict[str, Any]) -> int:
    if str(tool.get("tool_source") or "").strip() != "external_mcp":
        return 0
    joined = _tool_joined_text(tool)
    if not joined:
        return 0
    bonus = 0
    if any(hint in joined for hint in _EXTERNAL_EXECUTOR_HINTS):
        bonus += 20
    if _looks_like_implementation_task(task) and any(
        hint in joined for hint in ("code", "edit", "patch", "workspace", "repo", "代码", "修改", "文件", "工作区")
    ):
        bonus += 24
    return bonus


def _tool_execution_priority(task: str, tool: dict[str, Any]) -> int:
    source = str(tool.get("tool_source") or "").strip()
    score = int(tool.get("match_score") or 0)
    if source == "external_mcp":
        return 200 + score + _external_executor_bonus(task, tool)
    return 100 + score


def _should_stop_after_success(tool: dict[str, Any], result: dict[str, Any] | Any) -> bool:
    if str(tool.get("tool_source") or "").strip() != "external_mcp":
        return False
    if isinstance(result, dict) and result.get("error"):
        return False
    joined = _tool_joined_text(tool)
    if not joined:
        return False
    return any(hint in joined for hint in _EXTERNAL_TERMINAL_EXECUTOR_HINTS)


def _pick_members(
    task: str,
    members: list[dict[str, Any]],
    tool_index: dict[str, list[dict[str, Any]]],
    *,
    employee_ids: list[str] | None = None,
    max_employees: int = 3,
) -> list[dict[str, Any]]:
    requested_ids = set(_normalize_employee_ids(employee_ids))
    candidates = [
        item
        for item in members
        if str(item.get("employee_id") or item.get("id") or "").strip()
        and (not requested_ids or str(item.get("employee_id") or item.get("id") or "").strip() in requested_ids)
    ]
    if not candidates:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in candidates:
        employee_id = str(item.get("employee_id") or item.get("id") or "").strip()
        rules = list(item.get("rule_bindings") or [])
        tools = tool_index.get(employee_id, [])
        score = _score_against_task(
            task,
            [
                item.get("name"),
                item.get("employee_name"),
                item.get("description"),
                item.get("goal"),
                *(item.get("skill_names") or []),
                *[rule.get("title") or rule.get("domain") or rule.get("id") for rule in rules],
                *[tool.get("tool_name") for tool in tools],
                *[tool.get("description") for tool in tools],
            ],
        )
        scored.append((score, item))
    scored.sort(
        key=lambda pair: (
            -pair[0],
            str(pair[1].get("name") or pair[1].get("employee_name") or pair[1].get("employee_id") or ""),
        )
    )
    selected = [item for score, item in scored if score > 0][: max(1, min(int(max_employees or 3), 10))]
    if selected:
        return selected
    fallback_limit = max(1, min(int(max_employees or 3), len(candidates)))
    return candidates[:fallback_limit]


def _tool_text(tool: dict[str, Any]) -> list[Any]:
    return [
        tool.get("tool_name"),
        tool.get("base_tool_name"),
        tool.get("skill_name"),
        tool.get("skill_id"),
        tool.get("entry_name"),
        tool.get("module_name"),
        tool.get("remote_tool_name"),
        tool.get("description"),
    ]


def _choose_candidate_tools(
    task: str,
    member_ids: list[str],
    project_tools: list[dict[str, Any]],
    external_tools: list[dict[str, Any]],
    *,
    max_tools_per_employee: int = 2,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for employee_id in member_ids:
        scoped_tools = [
            item
            for item in project_tools
            if str(item.get("employee_id") or "").strip() == employee_id
            and str(item.get("tool_name") or "").strip() != COLLABORATION_TOOL_NAME
        ]
        scored = [
            (_score_against_task(task, _tool_text(item)), item)
            for item in scoped_tools
        ]
        scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("tool_name") or "")))
        for score, item in scored[: max(0, min(int(max_tools_per_employee or 2), 5))]:
            payload = dict(item)
            payload["match_score"] = score
            payload["tool_source"] = "project_tool"
            selected.append(payload)
    shared_external = []
    for item in external_tools:
        scored = _score_against_task(task, _tool_text(item))
        payload = dict(item)
        payload["match_score"] = scored
        payload["tool_source"] = "external_mcp"
        shared_external.append(payload)
    shared_external.sort(
        key=lambda item: (
            -_tool_execution_priority(task, item),
            -int(item.get("match_score") or 0),
            str(item.get("tool_name") or ""),
        )
    )
    selected.extend(shared_external[:4])
    selected.sort(
        key=lambda item: (
            -_tool_execution_priority(task, item),
            -int(item.get("match_score") or 0),
            str(item.get("tool_name") or ""),
        )
    )
    return selected


def _map_tool_args(
    tool: dict[str, Any],
    *,
    project_id: str,
    project_name: str,
    employee_id: str,
    selected_employee_ids: list[str],
    selected_members: list[dict[str, Any]],
    task: str,
) -> tuple[dict[str, Any] | None, str]:
    tool_name = str(tool.get("tool_name") or "").strip()
    if tool_name == "search_project_context":
        return {
            "scope": "all",
            "keyword": task,
            "employee_id": employee_id,
            "limit": 8,
        }, ""
    if tool_name == "query_project_rules":
        return {
            "keyword": task,
            "employee_id": employee_id,
        }, ""
    if tool_name == "query_project_members":
        return {}, ""
    if tool_name == "get_project_detail":
        return {}, ""
    if tool_name == "get_project_employee_detail":
        if not employee_id:
            return None, "employee_id is required"
        return {"employee_id": employee_id}, ""

    schema = tool.get("parameters_schema")
    if not isinstance(schema, dict):
        return None, "missing parameters_schema"
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    required = [
        str(item or "").strip()
        for item in (schema.get("required") or [])
        if str(item or "").strip()
    ]
    mapped: dict[str, Any] = {}
    for name in properties:
        lower_name = str(name or "").strip().lower()
        prop_schema = properties.get(name)
        prop_type = (
            str(prop_schema.get("type") or "").strip().lower()
            if isinstance(prop_schema, dict)
            else ""
        )
        if lower_name in _TEXT_ARG_CANDIDATES:
            mapped[name] = task
        elif lower_name == "employee_id" and employee_id:
            mapped[name] = employee_id
        elif lower_name == "project_id":
            mapped[name] = project_id
        elif lower_name in _PROJECT_NAME_ARG_CANDIDATES and project_name:
            mapped[name] = project_name
        elif lower_name in _EMPLOYEE_IDS_ARG_CANDIDATES and selected_employee_ids:
            mapped[name] = list(selected_employee_ids)
        elif lower_name in _MEMBER_CONTEXT_ARG_CANDIDATES and selected_members:
            mapped[name] = list(selected_members)
        elif lower_name in _PROJECT_CONTEXT_ARG_CANDIDATES and prop_type in {"", "object"}:
            mapped[name] = {
                "project_id": project_id,
                "project_name": project_name,
                "task": task,
                "selected_employee_ids": list(selected_employee_ids),
                "selected_members": list(selected_members),
            }
        elif lower_name == "scope":
            mapped[name] = "all"
        elif lower_name == "limit":
            mapped[name] = 8
    missing = [name for name in required if name not in mapped]
    if missing:
        return None, f"required parameters not auto-mappable: {missing}"
    return mapped, ""


def execute_project_collaboration_runtime(
    project_id: str,
    task: str,
    *,
    username: str = "",
    chat_session_id: str = "",
    employee_ids: list[str] | tuple[str, ...] | None = None,
    max_employees: int = 3,
    max_tool_calls: int = 6,
    auto_execute: bool = True,
    include_external_tools: bool = True,
    timeout_sec: int = 30,
    invoke_tool: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    project = project_store.get(project_id)
    if project is None:
        return {"error": f"Project {project_id} not found"}
    task_value = str(task or "").strip()
    if not task_value:
        return {"error": "task is required"}
    normalized_username = str(username or "").strip()
    normalized_chat_session_id = str(chat_session_id or "").strip()
    task_tree_payload = ensure_project_execution_task_tree(
        project_id=project_id,
        username=normalized_username,
        chat_session_id=normalized_chat_session_id,
        root_goal=task_value,
    )

    members = list_project_member_profiles_runtime(
        project_id,
        include_disabled=False,
        include_missing=False,
        rule_limit=30,
    )
    if not members:
        return {"error": f"Project {project_id} has no active members"}

    project_tools = [
        item
        for item in list_project_proxy_tools_runtime(project_id, "")
        if str(item.get("tool_name") or "").strip() != COLLABORATION_TOOL_NAME
    ]
    external_tools = list_project_external_tools_runtime(project_id) if include_external_tools else []
    tools_by_employee: dict[str, list[dict[str, Any]]] = {}
    for item in project_tools:
        employee_id = str(item.get("employee_id") or "").strip()
        if not employee_id:
            continue
        tools_by_employee.setdefault(employee_id, []).append(item)

    selected_members = _pick_members(
        task_value,
        members,
        tools_by_employee,
        employee_ids=_normalize_employee_ids(employee_ids),
        max_employees=max_employees,
    )
    selected_employee_ids = [
        str(item.get("employee_id") or item.get("id") or "").strip()
        for item in selected_members
        if str(item.get("employee_id") or item.get("id") or "").strip()
    ]

    candidate_tools = _choose_candidate_tools(
        task_value,
        selected_employee_ids,
        project_tools,
        external_tools,
    )
    plan_steps: list[dict[str, Any]] = [
        {
            "phase": "context",
            "tool_name": "search_project_context",
            "employee_id": "",
            "reason": "先统一检索项目上下文、成员、规则和 MCP 能力。",
        }
    ]
    for employee in selected_members:
        employee_id = str(employee.get("employee_id") or employee.get("id") or "").strip()
        employee_name = str(employee.get("name") or employee.get("employee_name") or employee_id).strip()
        plan_steps.append(
            {
                "phase": "rule",
                "tool_name": "query_project_rules",
                "employee_id": employee_id,
                "reason": f"先检索 {employee_name} 相关规则，避免协作执行偏离约束。",
            }
        )
    for item in candidate_tools:
        plan_steps.append(
            {
                "phase": "execution",
                "tool_name": str(item.get("tool_name") or "").strip(),
                "employee_id": str(item.get("employee_id") or "").strip(),
                "tool_source": str(item.get("tool_source") or "project_tool"),
                "match_score": int(item.get("match_score") or 0),
                "reason": str(item.get("description") or item.get("entry_name") or "候选工具").strip(),
            }
        )

    executed_calls: list[dict[str, Any]] = []
    skipped_calls: list[dict[str, Any]] = []
    execution_halt_reason = ""
    history_task_tree: dict[str, Any] | None = None
    tool_budget = max(0, min(int(max_tool_calls or 6), 20))
    if auto_execute and tool_budget > 0 and invoke_tool is not None:
        for step_index, step in enumerate(plan_steps):
            if len(executed_calls) >= tool_budget:
                break
            tool_name = str(step.get("tool_name") or "").strip()
            employee_id = str(step.get("employee_id") or "").strip()
            args, reason = _map_tool_args(
                {
                    **step,
                    "parameters_schema": next(
                        (
                            item.get("parameters_schema")
                            for item in project_tools + external_tools
                            if str(item.get("tool_name") or "").strip() == tool_name
                            and str(item.get("employee_id") or "").strip() == employee_id
                        ),
                        None,
                    ),
                },
                project_id=project_id,
                project_name=str(getattr(project, "name", "") or ""),
                employee_id=employee_id,
                selected_employee_ids=selected_employee_ids,
                selected_members=[
                    {
                        "employee_id": str(item.get("employee_id") or item.get("id") or "").strip(),
                        "name": str(item.get("name") or item.get("employee_name") or "").strip(),
                        "goal": str(item.get("goal") or "").strip(),
                        "skill_names": list(item.get("skill_names") or []),
                    }
                    for item in selected_members
                ],
                task=task_value,
            )
            if args is None:
                skipped_calls.append(
                    {
                        "tool_name": tool_name,
                        "employee_id": employee_id,
                        "reason": reason,
                    }
                )
                continue
            task_tree_payload, history_task_tree = _mark_task_tree_step_started(
                project_id=project_id,
                username=normalized_username,
                chat_session_id=normalized_chat_session_id,
                task_tree_payload=task_tree_payload,
                history_task_tree=history_task_tree,
                step=step,
                step_index=step_index,
            )
            result = invoke_tool(
                project_id=project_id,
                tool_name=tool_name,
                employee_id=employee_id,
                username=normalized_username,
                chat_session_id=normalized_chat_session_id,
                args=args,
                args_json=json.dumps(args, ensure_ascii=False),
                timeout_sec=timeout_sec,
            )
            executed_calls.append(
                {
                    "tool_name": tool_name,
                    "employee_id": employee_id,
                    "tool_source": str(step.get("tool_source") or ""),
                    "args": args,
                    "result": result,
                }
            )
            if isinstance(result, dict) and result.get("error"):
                task_tree_payload, history_task_tree = _mark_task_tree_step_blocked(
                    project_id=project_id,
                    username=normalized_username,
                    chat_session_id=normalized_chat_session_id,
                    task_tree_payload=task_tree_payload,
                    history_task_tree=history_task_tree,
                    step=step,
                    step_index=step_index,
                    result=result,
                )
                continue
            task_tree_payload, history_task_tree = _mark_task_tree_step_completed(
                project_id=project_id,
                username=normalized_username,
                chat_session_id=normalized_chat_session_id,
                task_tree_payload=task_tree_payload,
                history_task_tree=history_task_tree,
                step=step,
                step_index=step_index,
                result=result,
            )
            if _should_stop_after_success({**step, "task": task_value}, result):
                execution_halt_reason = "external_executor_completed"
                task_tree_payload, history_task_tree = _auto_complete_remaining_task_tree_steps(
                    project_id=project_id,
                    username=normalized_username,
                    chat_session_id=normalized_chat_session_id,
                    task_tree_payload=task_tree_payload,
                    history_task_tree=history_task_tree,
                    plan_steps=plan_steps,
                    start_index=step_index + 1,
                    result=result,
                )
                task_tree_payload, history_task_tree = _mark_task_tree_root_completed_if_ready(
                    project_id=project_id,
                    username=normalized_username,
                    chat_session_id=normalized_chat_session_id,
                    task=task_value,
                    task_tree_payload=task_tree_payload,
                    history_task_tree=history_task_tree,
                    executed_calls=executed_calls,
                    halt_reason=execution_halt_reason,
                )
                break
        if not execution_halt_reason:
            task_tree_payload, history_task_tree = _mark_task_tree_root_completed_if_ready(
                project_id=project_id,
                username=normalized_username,
                chat_session_id=normalized_chat_session_id,
                task=task_value,
                task_tree_payload=task_tree_payload,
                history_task_tree=history_task_tree,
                executed_calls=executed_calls,
            )

    return {
        "tool_name": COLLABORATION_TOOL_NAME,
        "project_id": project_id,
        "project_name": str(getattr(project, "name", "") or ""),
        "username": normalized_username,
        "chat_session_id": normalized_chat_session_id,
        "task": task_value,
        "selected_employee_ids": selected_employee_ids,
        "selected_members": [
            {
                "employee_id": str(item.get("employee_id") or item.get("id") or "").strip(),
                "name": str(item.get("name") or item.get("employee_name") or "").strip(),
                "goal": str(item.get("goal") or "").strip(),
                "skill_names": list(item.get("skill_names") or []),
            }
            for item in selected_members
        ],
        "candidate_tools": [
            {
                "tool_name": str(item.get("tool_name") or "").strip(),
                "employee_id": str(item.get("employee_id") or "").strip(),
                "tool_source": str(item.get("tool_source") or "project_tool"),
                "match_score": int(item.get("match_score") or 0),
                "description": str(item.get("description") or "").strip(),
            }
            for item in candidate_tools
        ],
        "plan_steps": plan_steps,
        "executed_calls": executed_calls,
        "skipped_calls": skipped_calls,
        "execution_halt_reason": execution_halt_reason,
        "auto_execute": bool(auto_execute),
        "max_tool_calls": tool_budget,
        "task_tree": task_tree_payload,
        "history_task_tree": history_task_tree,
    }
