"""Audit and auto-capture helpers for dynamic MCP runtime."""

from __future__ import annotations

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
        return method_name, "", [], {"project_id": "", "project_name": "", "employee_id": ""}

    tool_name = ""
    user_values: list[str] = []
    context_values: list[str] = []
    query_values: list[str] = []
    project_values: list[tuple[str, str]] = []
    employee_values: list[tuple[str, str]] = []
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
        for key_name, text in collect_question_values(parsed_arguments):
            if key_name == "query":
                query_values.append(text)
            else:
                context_values.append(text)
        project_values.extend(collect_project_values(parsed_arguments))
        employee_values.extend(collect_employee_values(parsed_arguments))

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

    context = {
        "project_id": "",
        "project_name": "",
        "employee_id": "",
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

    content = f"[用户提问] {primary_question}"
    if auxiliary_queries:
        content = f"{content}\n[辅助query] {' | '.join(auxiliary_queries)}"
    content_key = f"{normalized_project_name}|{content}"
    if content_key in existing:
        return
    try:
        memory_store.save(
            Memory(
                id=memory_store.new_id(),
                employee_id=employee_id,
                type=MemoryType.PROJECT_CONTEXT,
                content=content,
                project_name=normalized_project_name,
                importance=0.55,
                scope=MemoryScope.EMPLOYEE_PRIVATE,
                classification=Classification.INTERNAL,
                purpose_tags=("auto-capture", "user-question", source),
            )
        )
    except Exception:
        return


def save_auto_query_memory(
    questions: list[str],
    source: str,
    *,
    project_id: str = "",
    employee_id: str = "",
    project_name: str = "",
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

    seen: set[str] = set()
    for member in project_store.list_members(normalized_project_id or resolved_project.id):
        if not bool(getattr(member, "enabled", True)):
            continue
        member_employee_id = normalize_text(getattr(member, "employee_id", ""))
        if not member_employee_id or member_employee_id in seen:
            continue
        if employee_store.get(member_employee_id) is None:
            continue
        seen.add(member_employee_id)
        save_auto_user_question_memory(
            member_employee_id,
            questions,
            source,
            resolved_project_name or "default",
        )


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
):
    async def tracking_send(message):
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
                            break
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
    on_questions: Callable[[str, str, list[str], dict[str, str]], None] | None = None,
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
                if method_name == "tools/call":
                    usage_store.record_event(
                        usage_scope_id,
                        api_key,
                        developer_name,
                        "tool_call",
                        tool_name=tool_name,
                        client_ip=client_ip,
                    )
                if questions and on_questions is not None:
                    on_questions(method_name, tool_name, questions, context)
        except Exception:
            pass
        return message

    return tracking_receive
