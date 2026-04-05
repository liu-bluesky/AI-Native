"""Audit and auto-capture helpers for dynamic MCP runtime."""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable

from core.deps import employee_store, project_store, usage_store
from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType, memory_store

_QUESTION_FIELD_KEYS = {
    "question",
    "query",
    "keyword",
    "prompt",
    "content",
    "message",
    "text",
    "input",
    "user_input",
    "symptom",
    "expected",
    "title",
}

_PROJECT_FIELD_KEYS = {
    "project",
    "project_id",
    "project_name",
    "workspace",
    "workspace_id",
    "repo",
    "repository",
}

_EMPLOYEE_FIELD_KEYS = {
    "employee_id",
    "employee",
    "member_id",
    "member",
}

_CHAT_SESSION_FIELD_KEYS = {
    "chat_session_id",
    "chat_session",
    "chatsessionid",
}

_AUTO_CAPTURE_SKIP_TOOL_NAMES = {
    "bind_project_context",
    "start_work_session",
    "save_work_facts",
    "append_session_event",
    "resume_work_session",
    "summarize_checkpoint",
    "build_delivery_report",
    "generate_release_note_entry",
    "save_project_memory",
}


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_project_name(value: str) -> str:
    return normalize_text(value)


def _looks_like_project_id(value: str) -> bool:
    return normalize_text(value).lower().startswith("proj-")


def _looks_like_employee_id(value: str) -> bool:
    return normalize_text(value).lower().startswith("emp-")


def extract_text_nodes(node: object) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        out: list[str] = []
        for item in node:
            out.extend(extract_text_nodes(item))
        return out
    if isinstance(node, dict):
        out: list[str] = []
        if isinstance(node.get("text"), str):
            out.append(node["text"])
        if isinstance(node.get("content"), (str, list, dict)):
            out.extend(extract_text_nodes(node["content"]))
        return out
    return []


def join_text_nodes(node: object) -> str:
    parts = extract_text_nodes(node)
    if not parts:
        return ""
    return "".join(parts)


def collect_question_values(node: object, key_hint: str = "") -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, val in node.items():
            key_name = str(key or "").strip().lower()
            if isinstance(val, str) and key_name in _QUESTION_FIELD_KEYS:
                values.append((key_name, val))
            else:
                values.extend(collect_question_values(val, key_name))
    elif isinstance(node, list):
        for item in node:
            values.extend(collect_question_values(item, key_hint))
    elif isinstance(node, str) and key_hint in _QUESTION_FIELD_KEYS:
        values.append((key_hint, node))
    return values


def collect_field_values(
    node: object,
    allowed_keys: set[str],
    key_hint: str = "",
) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, val in node.items():
            key_name = str(key or "").strip().lower()
            if isinstance(val, str) and key_name in allowed_keys:
                values.append((key_name, val))
            else:
                values.extend(collect_field_values(val, allowed_keys, key_name))
    elif isinstance(node, list):
        for item in node:
            values.extend(collect_field_values(item, allowed_keys, key_hint))
    elif isinstance(node, str) and key_hint in allowed_keys:
        values.append((key_hint, node))
    return values


def collect_project_values(node: object, key_hint: str = "") -> list[tuple[str, str]]:
    return collect_field_values(node, _PROJECT_FIELD_KEYS, key_hint)


def collect_employee_values(node: object, key_hint: str = "") -> list[tuple[str, str]]:
    return collect_field_values(node, _EMPLOYEE_FIELD_KEYS, key_hint)


def collect_chat_session_values(node: object, key_hint: str = "") -> list[tuple[str, str]]:
    return collect_field_values(node, _CHAT_SESSION_FIELD_KEYS, key_hint)


def _build_query_fallback_question(tool_name: str, context: dict[str, str]) -> str:
    # Lookup-only query tools are often called as mandatory bootstrap steps
    # without any original user utterance in the RPC payload. Synthesizing
    # pseudo questions here pollutes memory with entries like
    # "[用户提问] 查询项目手册 proj-xxx", which are not the user's actual issue.
    if tool_name in {"get_manual_content", "get_content"}:
        return ""
    return ""


def extract_user_questions_from_rpc_payload(
    rpc_payload: dict,
) -> tuple[str, str, list[str], dict[str, str]]:
    method_name = str(rpc_payload.get("method") or "")
    params = rpc_payload.get("params")
    if not isinstance(params, dict):
        return method_name, "", [], {
            "project_id": "",
            "project_name": "",
            "employee_id": "",
            "chat_session_id": "",
        }

    tool_name = ""
    user_values: list[str] = []
    context_values: list[str] = []
    query_values: list[str] = []
    project_values: list[tuple[str, str]] = []
    employee_values: list[tuple[str, str]] = []
    chat_session_values: list[tuple[str, str]] = []
    if method_name == "tools/call":
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments")
        parsed_arguments = arguments
        if isinstance(arguments, str):
            text = arguments
            stripped = text.strip()
            parsed_arguments = None
            if stripped:
                try:
                    candidate = json.loads(stripped)
                    if isinstance(candidate, (dict, list)):
                        parsed_arguments = candidate
                    elif isinstance(candidate, str):
                        context_values.append(candidate)
                    else:
                        context_values.append(text)
                except Exception:
                    context_values.append(text)
            else:
                context_values.append(text)
        if parsed_arguments is None:
            parsed_arguments = {}
        capture_argument_questions = tool_name not in _AUTO_CAPTURE_SKIP_TOOL_NAMES
        if capture_argument_questions:
            for key_name, text in collect_question_values(parsed_arguments):
                if key_name == "query":
                    query_values.append(text)
                else:
                    context_values.append(text)
        project_values.extend(collect_project_values(parsed_arguments))
        employee_values.extend(collect_employee_values(parsed_arguments))
        chat_session_values.extend(collect_chat_session_values(parsed_arguments))

    messages = params.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "").strip().lower()
            if role == "user":
                merged = join_text_nodes(msg.get("content"))
                if merged:
                    user_values.append(merged)

    if "message" in params:
        merged = join_text_nodes(params.get("message"))
        if merged:
            user_values.append(merged)
    if "content" in params:
        merged = join_text_nodes(params.get("content"))
        if merged:
            user_values.append(merged)
    project_values.extend(collect_project_values(params))
    employee_values.extend(collect_employee_values(params))
    chat_session_values.extend(collect_chat_session_values(params))

    context = {
        "project_id": "",
        "project_name": "",
        "employee_id": "",
        "chat_session_id": "",
    }
    for key_name, raw in project_values:
        value = normalize_project_name(raw)
        if not value:
            continue
        if key_name == "project_id" or _looks_like_project_id(value):
            if not context["project_id"]:
                context["project_id"] = value
            continue
        if key_name == "project_name":
            if not context["project_name"]:
                context["project_name"] = value
            continue
        if not context["project_name"]:
            context["project_name"] = value
    for key_name, raw in employee_values:
        value = normalize_text(raw)
        if not value:
            continue
        if key_name == "employee_id" or _looks_like_employee_id(value):
            context["employee_id"] = value
            break
    for _, raw in chat_session_values:
        value = normalize_text(raw)
        if value:
            context["chat_session_id"] = value
            break

    captured: list[str] = []
    seen: set[str] = set()
    for raw in user_values + context_values + query_values:
        if not isinstance(raw, str):
            continue
        if raw == "" or raw in seen:
            continue
        seen.add(raw)
        captured.append(raw)
    if not captured and tool_name:
        fallback = _build_query_fallback_question(tool_name, context)
        if fallback:
            captured.append(fallback)
    return method_name, tool_name, captured, context


def save_auto_user_question_memory(
    employee_id: str,
    questions: list[str],
    source: str,
    project_name: str = "",
    chat_session_id: str = "",
    scope: MemoryScope = MemoryScope.EMPLOYEE_PRIVATE,
) -> None:
    if not questions:
        return
    normalized_project_name = normalize_project_name(project_name) or "default"
    existing: set[str] = set()
    try:
        for mem in memory_store.recent(employee_id, 10):
            existing.add(
                f"{normalize_project_name(str(getattr(mem, 'project_name', '')))}|"
                f"{str(getattr(mem, 'content', ''))}"
            )
    except Exception:
        existing = set()

    normalized_questions: list[str] = []
    for question in questions:
        if not isinstance(question, str) or question == "" or question in normalized_questions:
            continue
        normalized_questions.append(question)
    if not normalized_questions:
        return

    primary_question = normalized_questions[0]
    primary_norm = normalize_text(primary_question).lower()
    auxiliary_queries: list[str] = []
    for question in normalized_questions[1:]:
        question_norm = normalize_text(question).lower()
        if question_norm == "":
            continue
        if primary_norm and question_norm in primary_norm:
            continue
        if question in auxiliary_queries:
            continue
        auxiliary_queries.append(question)

    normalized_chat_session_id = normalize_text(chat_session_id)
    content = f"[用户提问] {primary_question}"
    if auxiliary_queries:
        content = f"{content}\n[辅助query] {' | '.join(auxiliary_queries)}"
    if normalized_chat_session_id:
        content = f"{content}\n[关联会话] {normalized_chat_session_id}"
    content_key = f"{normalized_project_name}|{content}"
    if content_key in existing:
        return
    purpose_tags = ["auto-capture", "user-question", source]
    if normalized_chat_session_id:
        purpose_tags.append(f"chat-session:{normalized_chat_session_id}")
    try:
        memory_store.save(
            Memory(
                id=memory_store.new_id(),
                employee_id=employee_id,
                type=MemoryType.PROJECT_CONTEXT,
                content=content,
                project_name=normalized_project_name,
                importance=0.55,
                scope=scope,
                classification=Classification.INTERNAL,
                purpose_tags=tuple(purpose_tags),
            )
        )
    except Exception:
        return


def _resolve_project_auto_query_memory_employee_id(project_id: str) -> str:
    seen: set[str] = set()
    for member in project_store.list_members(project_id):
        if not bool(getattr(member, "enabled", True)):
            continue
        member_employee_id = normalize_text(getattr(member, "employee_id", ""))
        if not member_employee_id or member_employee_id in seen:
            continue
        if employee_store.get(member_employee_id) is None:
            continue
        seen.add(member_employee_id)
        return member_employee_id
    return ""


def save_auto_query_memory(
    questions: list[str],
    source: str,
    *,
    project_id: str = "",
    employee_id: str = "",
    project_name: str = "",
    chat_session_id: str = "",
) -> None:
    target_employee_id = normalize_text(employee_id)
    if target_employee_id and employee_store.get(target_employee_id) is not None:
        resolved_project_name = normalize_project_name(project_name)
        if not resolved_project_name and project_id:
            project = project_store.get(str(project_id).strip())
            if project is not None:
                resolved_project_name = normalize_project_name(getattr(project, "name", ""))
        save_auto_user_question_memory(
            target_employee_id,
            questions,
            source,
            resolved_project_name or "default",
            chat_session_id,
            MemoryScope.EMPLOYEE_PRIVATE,
        )
        return

    resolved_project = None
    normalized_project_id = normalize_text(project_id)
    if normalized_project_id:
        resolved_project = project_store.get(normalized_project_id)

    resolved_project_name = normalize_project_name(project_name)
    if resolved_project is None and resolved_project_name:
        for candidate in project_store.list_all():
            candidate_name = normalize_project_name(getattr(candidate, "name", ""))
            if candidate_name and candidate_name == resolved_project_name:
                resolved_project = candidate
                normalized_project_id = str(getattr(candidate, "id", "") or "").strip()
                break

    if resolved_project is not None and not resolved_project_name:
        resolved_project_name = normalize_project_name(getattr(resolved_project, "name", ""))

    if resolved_project is None:
        return

    target_employee_id = _resolve_project_auto_query_memory_employee_id(
        normalized_project_id or str(getattr(resolved_project, "id", "") or "").strip()
    )
    if not target_employee_id:
        return
    save_auto_user_question_memory(
        target_employee_id,
        questions,
        source,
        resolved_project_name or "default",
        chat_session_id,
        MemoryScope.TEAM_SHARED,
    )


def save_auto_query_result_memory(
    question: str,
    solution: str,
    conclusion: str,
    source: str,
    *,
    project_id: str = "",
    employee_id: str = "",
    project_name: str = "",
    chat_session_id: str = "",
    task_tree_payload: dict[str, Any] | None = None,
) -> None:
    def _normalize_task_tree_status(payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        session_status = normalize_text(payload.get("status")).lower()
        current_node = payload.get("current_node") if isinstance(payload.get("current_node"), dict) else {}
        current_status = normalize_text(current_node.get("status")).lower()
        return current_status or session_status

    def _is_task_tree_completed(payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return True
        status = normalize_text(payload.get("status")).lower()
        if not status:
            return True
        if bool(payload.get("is_archived")) and status == "done":
            return True
        if status != "done":
            return False
        try:
            progress_percent = int(payload.get("progress_percent", 0) or 0)
        except (TypeError, ValueError):
            progress_percent = 0
        if progress_percent >= 100:
            return True
        stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
        leaf_total = int(payload.get("leaf_total") or stats.get("leaf_total") or 0)
        done_leaf_total = int(payload.get("done_leaf_total") or stats.get("done_leaf_total") or 0)
        return leaf_total > 0 and done_leaf_total >= leaf_total

    def _query_stage_label(payload: dict[str, Any] | None) -> str:
        status = _normalize_task_tree_status(payload)
        if status == "pending":
            return "计划中"
        if status in {"in_progress", "started"}:
            return "执行中"
        if status == "verifying":
            return "待验证"
        if status in {"blocked", "failed"}:
            return "已阻塞"
        if _is_task_tree_completed(payload):
            return "已完成"
        return "执行中"

    def _render_task_tree_plan_outline(payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
        lines: list[str] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            try:
                level = int(node.get("level", 0) or 0)
            except (TypeError, ValueError):
                level = 0
            if level <= 0:
                continue
            title = normalize_text(node.get("title"))
            if not title:
                continue
            status = normalize_text(node.get("status")) or "pending"
            verification_result = normalize_text(node.get("verification_result"))
            line = f"- [{status}] {title}"
            if verification_result:
                line = f"{line} | 验证: {verification_result}"
            lines.append(line)
        return "\n".join(lines[:12])

    def _render_task_tree_verification_summary(payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
        items: list[str] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            verification_result = normalize_text(node.get("verification_result"))
            if not verification_result:
                continue
            title = normalize_text(node.get("title")) or "任务节点"
            items.append(f"{title}: {verification_result}")
        return "\n".join(items[:12])

    def _extract_task_tree_binding(payload: dict[str, Any] | None) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        current_node = payload.get("current_node") if isinstance(payload.get("current_node"), dict) else {}
        binding = {
            "chat_session_id": normalized_chat_session_id,
            "task_tree_session_id": normalize_text(payload.get("id")),
            "task_tree_chat_session_id": normalize_text(
                payload.get("source_chat_session_id") or payload.get("chat_session_id")
            ),
            "task_node_id": normalize_text(current_node.get("id")),
            "task_node_title": normalize_text(current_node.get("title")),
            "root_goal": normalize_text(payload.get("root_goal") or payload.get("title")),
        }
        return {key: value for key, value in binding.items() if value}

    def _memory_record_exists(
        employee_id_value: str,
        *,
        normalized_project_name: str,
        workflow_tag: str,
    ) -> bool:
        recent = getattr(memory_store, "recent", None)
        list_by_employee = getattr(memory_store, "list_by_employee", None)
        if callable(recent):
            try:
                candidates = list(recent(employee_id_value, 200) or [])
            except Exception:
                candidates = []
        elif callable(list_by_employee):
            try:
                candidates = list(list_by_employee(employee_id_value) or [])
            except Exception:
                candidates = []
        else:
            candidates = []
        normalized_chat_tag = f"chat-session:{normalized_chat_session_id}" if normalized_chat_session_id else ""
        for mem in candidates:
            if normalize_project_name(getattr(mem, "project_name", "")) != normalized_project_name:
                continue
            tags = {
                normalize_text(item)
                for item in (getattr(mem, "purpose_tags", ()) or [])
                if normalize_text(item)
            }
            if workflow_tag not in tags:
                continue
            if normalized_chat_tag and normalized_chat_tag not in tags:
                continue
            return True
        return False

    normalized_question = normalize_text(question)
    normalized_solution = normalize_text(solution)
    normalized_conclusion = normalize_text(conclusion)
    normalized_chat_session_id = normalize_text(chat_session_id)
    if not normalized_question or not (normalized_solution or normalized_conclusion):
        return

    resolved_project = None
    normalized_project_id = normalize_text(project_id)
    if normalized_project_id:
        resolved_project = project_store.get(normalized_project_id)

    resolved_project_name = normalize_project_name(project_name)
    if resolved_project is None and resolved_project_name:
        for candidate in project_store.list_all():
            candidate_name = normalize_project_name(getattr(candidate, "name", ""))
            if candidate_name and candidate_name == resolved_project_name:
                resolved_project = candidate
                normalized_project_id = str(getattr(candidate, "id", "") or "").strip()
                break

    if resolved_project is not None and not resolved_project_name:
        resolved_project_name = normalize_project_name(getattr(resolved_project, "name", ""))

    if resolved_project is None:
        return

    target_employee_id = normalize_text(employee_id)
    if not target_employee_id or employee_store.get(target_employee_id) is None:
        target_employee_id = _resolve_project_auto_query_memory_employee_id(
            normalized_project_id or str(getattr(resolved_project, "id", "") or "").strip()
        )
    if not target_employee_id:
        return

    task_tree_completed = _is_task_tree_completed(task_tree_payload)
    workflow_tag = "workflow:final-summary" if task_tree_completed else "workflow:requirement-record"
    stage_label = _query_stage_label(task_tree_payload)
    plan_outline = _render_task_tree_plan_outline(task_tree_payload)
    verification_summary = _render_task_tree_verification_summary(task_tree_payload)
    if task_tree_completed:
        content_lines = [
            f"[用户问题] {normalized_question}",
            "[处理过程] 已根据关联查询结果完成本轮处理，可结合任务树回看执行节点与验证结果。",
            f"[解决方案] {normalized_solution or normalized_conclusion}",
            f"[最终结论] {normalized_conclusion or normalized_solution}",
            "[解决状态] 已给出方案",
        ]
        if verification_summary:
            content_lines.append(f"[验证结果] {verification_summary[:2400]}")
    else:
        content_lines = [
            f"[用户问题] {normalized_question}",
            (
                "[处理过程] 已生成执行计划，当前只记录需求与计划状态。"
                f" 当前阶段：{stage_label}；必须按任务树逐项执行、逐项验证，全部完成前不生成最终结论。"
            ),
            f"[解决状态] {stage_label}",
            "[完成条件] 只有所有计划项完成并写入验证结果后，当前需求才算结束。",
        ]
        if plan_outline:
            content_lines.append(f"[任务计划]\n{plan_outline}")
    if normalized_chat_session_id:
        content_lines.append(f"[关联会话] {normalized_chat_session_id}")
    task_tree_binding = _extract_task_tree_binding(task_tree_payload)
    if task_tree_binding:
        content_lines.append(
            "[执行轨迹JSON] " + json.dumps(task_tree_binding, ensure_ascii=False, sort_keys=True)
        )
    content = "\n".join(content_lines)
    normalized_project_name = resolved_project_name or "default"
    if _memory_record_exists(
        target_employee_id,
        normalized_project_name=normalized_project_name,
        workflow_tag=workflow_tag,
    ):
        return

    purpose_tags = ["auto-capture", "query-result", source, workflow_tag]
    if normalized_chat_session_id:
        purpose_tags.append(f"chat-session:{normalized_chat_session_id}")
    if task_tree_binding.get("task_tree_session_id"):
        purpose_tags.append(f"task-tree-session:{task_tree_binding['task_tree_session_id']}")
    try:
        memory_store.save(
            Memory(
                id=memory_store.new_id(),
                employee_id=target_employee_id,
                type=MemoryType.PROJECT_CONTEXT,
                content=content,
                project_name=normalized_project_name,
                importance=0.62,
                scope=MemoryScope.TEAM_SHARED,
                classification=Classification.INTERNAL,
                purpose_tags=tuple(purpose_tags),
            )
        )
    except Exception:
        return


def get_client_ip(scope: dict[str, Any]) -> str:
    for header_name, header_val in scope.get("headers", []):
        if header_name == b"x-forwarded-for":
            return header_val.decode().split(",")[0].strip()
    client_addr = scope.get("client")
    if client_addr:
        return client_addr[0]
    return ""


def create_tracking_send(
    send,
    *,
    is_sse: bool,
    method: str,
    api_key: str,
    developer_name: str,
    session_keys: dict[str, tuple[str, str]],
    session_contexts: dict[str, dict[str, str]] | None = None,
    session_context: dict[str, str] | None = None,
    request_state: dict[str, Any] | None = None,
    on_tool_result: Callable[[str, str, dict[str, Any], dict[str, str], dict[str, Any]], Any] | None = None,
):
    response_body_buffer = bytearray()
    response_body_captured = False

    def _parse_rpc_response_payloads(body: bytes) -> list[dict[str, Any]]:
        text = body.decode(errors="ignore")
        payloads: list[dict[str, Any]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("data:"):
                continue
            data_text = stripped[5:].strip()
            if not data_text:
                continue
            try:
                parsed = json.loads(data_text)
            except Exception:
                continue
            if isinstance(parsed, dict):
                payloads.append(parsed)
            elif isinstance(parsed, list):
                payloads.extend(item for item in parsed if isinstance(item, dict))
        if payloads:
            return payloads
        try:
            parsed = json.loads(text)
        except Exception:
            return []
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        return []

    def _extract_tool_result_payload(rpc_payload: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(rpc_payload, dict):
            return None
        result = rpc_payload.get("result")
        if not isinstance(result, dict):
            return None
        content_text = join_text_nodes(result.get("content"))
        structured_content = result.get("structuredContent")
        parsed_payload: Any = structured_content if isinstance(structured_content, (dict, list)) else None
        if parsed_payload is None and isinstance(content_text, str):
            stripped = content_text.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    candidate = json.loads(stripped)
                    if isinstance(candidate, (dict, list)):
                        parsed_payload = candidate
                except Exception:
                    parsed_payload = None
        return {
            "is_error": bool(result.get("isError")) or bool(rpc_payload.get("error")),
            "text": content_text,
            "result": result,
            "structured_content": structured_content,
            "parsed_payload": parsed_payload,
        }

    async def tracking_send(message):
        nonlocal response_body_captured
        if is_sse and method == "GET" and message.get("type") == "http.response.body":
            body = message.get("body", b"")
            if b"endpoint" in body and b"session_id=" in body:
                try:
                    text = body.decode()
                    for line in text.split("\n"):
                        if "session_id=" in line:
                            sid = line.split("session_id=")[-1].split("&")[0].split("\n")[0].split("\r")[0].strip()
                            if sid:
                                session_keys[sid] = (api_key, developer_name)
                                if session_contexts is not None and isinstance(session_context, dict):
                                    existing_context = session_contexts.get(sid) or {}
                                    merged_context = {
                                        "project_id": normalize_text(
                                            session_context.get("project_id", "")
                                            or existing_context.get("project_id", "")
                                        ),
                                        "project_name": normalize_text(
                                            session_context.get("project_name", "")
                                            or existing_context.get("project_name", "")
                                        ),
                                        "employee_id": normalize_text(
                                            session_context.get("employee_id", "")
                                            or existing_context.get("employee_id", "")
                                        ),
                                        "chat_session_id": normalize_text(
                                            session_context.get("chat_session_id", "")
                                            or existing_context.get("chat_session_id", "")
                                        ),
                                    }
                                    if any(merged_context.values()):
                                        session_contexts[sid] = merged_context
                            break
                except Exception:
                    pass
        elif (
            message.get("type") == "http.response.body"
            and not response_body_captured
            and on_tool_result is not None
        ):
            body = message.get("body", b"")
            if body:
                response_body_buffer.extend(body)
            if message.get("more_body", False):
                await send(message)
                return
            response_body_captured = True
            if response_body_buffer:
                try:
                    rpc_payloads = _parse_rpc_response_payloads(bytes(response_body_buffer))
                    request_calls = list((request_state or {}).get("rpc_calls") or [])
                    for index, rpc_payload in enumerate(rpc_payloads):
                        tool_payload = _extract_tool_result_payload(rpc_payload)
                        if tool_payload is None:
                            continue
                        metadata = None
                        response_id = rpc_payload.get("id")
                        if request_calls:
                            for pos, candidate in enumerate(request_calls):
                                if candidate.get("id") == response_id:
                                    metadata = request_calls.pop(pos)
                                    break
                            if metadata is None:
                                if len(request_calls) == 1:
                                    metadata = request_calls.pop(0)
                                elif index < len(request_calls):
                                    metadata = request_calls.pop(index)
                        if not isinstance(metadata, dict):
                            continue
                        maybe_awaitable = on_tool_result(
                            str(metadata.get("method_name") or ""),
                            str(metadata.get("tool_name") or ""),
                            tool_payload,
                            dict(metadata.get("context") or {}),
                            dict(metadata),
                        )
                        if inspect.isawaitable(maybe_awaitable):
                            await maybe_awaitable
                    if request_state is not None:
                        request_state["rpc_calls"] = request_calls
                except Exception:
                    pass
        await send(message)

    return tracking_send


def create_tracking_receive(
    receive,
    *,
    usage_scope_id: str,
    api_key: str,
    developer_name: str,
    client_ip: str,
    session_id: str = "",
    session_contexts: dict[str, dict[str, str]] | None = None,
    resolve_fallback_chat_session_id: Callable[[dict[str, str]], str] | None = None,
    on_context: Callable[[str, str, dict[str, str]], Any] | None = None,
    on_questions: Callable[[str, str, list[str], dict[str, str]], None] | None = None,
    request_state: dict[str, Any] | None = None,
):
    request_body_buffer = bytearray()
    request_body_captured = False

    async def tracking_receive():
        nonlocal request_body_captured
        message = await receive()
        if request_body_captured or message.get("type") != "http.request":
            return message
        body = message.get("body", b"")
        if body:
            request_body_buffer.extend(body)
        if message.get("more_body", False):
            return message
        if not request_body_buffer:
            return message
        request_body_captured = True
        try:
            payload = json.loads(bytes(request_body_buffer))
            rpc_payloads = payload if isinstance(payload, list) else [payload]
            for rpc_payload in rpc_payloads:
                if not isinstance(rpc_payload, dict):
                    continue
                method_name, tool_name, questions, context = extract_user_questions_from_rpc_payload(rpc_payload)
                merged_context = {
                    "project_id": str((context or {}).get("project_id") or "").strip(),
                    "project_name": str((context or {}).get("project_name") or "").strip(),
                    "employee_id": str((context or {}).get("employee_id") or "").strip(),
                    "chat_session_id": str((context or {}).get("chat_session_id") or "").strip(),
                }
                if session_id and session_contexts is not None:
                    stored_context = session_contexts.get(session_id) or {}
                    merged_context = {
                        "project_id": merged_context["project_id"] or str(stored_context.get("project_id") or "").strip(),
                        "project_name": merged_context["project_name"] or str(stored_context.get("project_name") or "").strip(),
                        "employee_id": merged_context["employee_id"] or str(stored_context.get("employee_id") or "").strip(),
                        "chat_session_id": merged_context["chat_session_id"] or str(stored_context.get("chat_session_id") or "").strip(),
                    }
                if (
                    not merged_context["chat_session_id"]
                    and resolve_fallback_chat_session_id is not None
                ):
                    fallback_chat_session_id = str(
                        resolve_fallback_chat_session_id(merged_context) or ""
                    ).strip()
                    if fallback_chat_session_id:
                        merged_context["chat_session_id"] = fallback_chat_session_id
                if session_id and session_contexts is not None:
                    if any(merged_context.values()):
                        session_contexts[session_id] = merged_context
                if request_state is not None:
                    request_calls = request_state.setdefault("rpc_calls", [])
                    if isinstance(request_calls, list):
                        request_calls.append(
                            {
                                "id": rpc_payload.get("id"),
                                "method_name": method_name,
                                "tool_name": tool_name,
                                "context": dict(merged_context),
                                "questions": list(questions or []),
                            }
                        )
                if method_name == "tools/call":
                    usage_store.record_event(
                        usage_scope_id,
                        api_key,
                        developer_name,
                        "tool_call",
                        tool_name=tool_name,
                        client_ip=client_ip,
                    )
                if any(merged_context.values()) and on_context is not None:
                    maybe_awaitable = on_context(method_name, tool_name, merged_context)
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
                if questions and on_questions is not None:
                    maybe_awaitable = on_questions(method_name, tool_name, questions, merged_context)
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
        except Exception:
            pass
        return message

    return tracking_receive
