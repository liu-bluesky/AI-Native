"""Proxy ASGI apps for dynamic MCP project/employee endpoints."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Callable
from urllib.parse import parse_qs

from fastapi.responses import JSONResponse, Response

from services.dynamic_mcp_audit import (
    create_tracking_receive,
    create_tracking_send,
    get_client_ip,
    save_auto_query_result_memory,
)
from services.project_mcp_presence import touch_project_mcp_presence as _touch_project_mcp_presence
from services.project_chat_task_tree import audit_task_tree_round, ensure_task_tree
from services.query_mcp_project_state import (
    load_resumable_query_mcp_local_state,
    persist_query_mcp_local_state,
)


def _is_well_known_probe(path: str) -> bool:
    return (
        "/.well-known/oauth-authorization-server" in path
        or "/.well-known/openid-configuration" in path
        or "/.well-known/oauth-protected-resource" in path
    )


def _normalize_text(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


_QUERY_TASK_TREE_AUDIT_SKIP_TOOLS = {
    "bind_project_context",
    "save_project_memory",
}

_QUERY_QUESTION_TASK_TREE_SKIP_TOOLS: set[str] = set()

_QUERY_RESULT_MEMORY_SKIP_TOOLS = {
    "bind_project_context",
    "search_ids",
    "get_manual_content",
    "get_content",
    "analyze_task",
    "resolve_relevant_context",
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
    "save_project_memory",
}


def _summarize_named_items(items: object, *, limit: int = 5) -> str:
    names: list[str] = []
    if not isinstance(items, list):
        return ""
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = (
            _normalize_text(item.get("name"), 120)
            or _normalize_text(item.get("title"), 120)
            or _normalize_text(item.get("id"), 120)
            or _normalize_text(item.get("employee_id"), 120)
            or _normalize_text(item.get("project_id"), 120)
        )
        if candidate and candidate not in names:
            names.append(candidate)
        if len(names) >= limit:
            break
    return "、".join(names)


def _build_query_tool_result_summary(tool_name: str, tool_payload: dict[str, Any]) -> str:
    parsed_payload = tool_payload.get("parsed_payload")
    if isinstance(parsed_payload, dict):
        if tool_name == "search_ids":
            parts: list[str] = []
            for key, label in (
                ("projects", "项目"),
                ("employees", "员工"),
                ("rules", "规则"),
            ):
                items = parsed_payload.get(key)
                if not isinstance(items, list) or not items:
                    continue
                item_names = _summarize_named_items(items)
                summary = f"{label} {len(items)} 项"
                if item_names:
                    summary = f"{summary}：{item_names}"
                parts.append(summary)
            if parts:
                return f"已完成 ID 检索，命中 {'；'.join(parts)}。"
        if tool_name == "list_project_members":
            items = parsed_payload.get("items")
            if isinstance(items, list) and items:
                item_names = _summarize_named_items(items)
                return f"已获取项目成员列表，共 {len(items)} 名：{item_names}。"
            return "已获取项目成员列表，但当前没有可用成员。"
        if tool_name == "resolve_relevant_context":
            members = parsed_payload.get("members") or parsed_payload.get("employees") or []
            rules = parsed_payload.get("rules") or []
            tools = parsed_payload.get("tools") or []
            parts: list[str] = []
            if isinstance(members, list) and members:
                parts.append(f"成员 {len(members)} 项")
            if isinstance(rules, list) and rules:
                parts.append(f"规则 {len(rules)} 项")
            if isinstance(tools, list) and tools:
                parts.append(f"工具 {len(tools)} 项")
            if parts:
                return f"已聚合相关上下文：{'；'.join(parts)}。"
        if tool_name == "get_project_runtime_context":
            items = parsed_payload.get("members") or parsed_payload.get("member_profiles") or []
            if isinstance(items, list) and items:
                item_names = _summarize_named_items(items)
                return f"已读取项目运行时上下文，成员 {len(items)} 名：{item_names}。"
            return "已读取项目运行时上下文。"
        if tool_name == "get_manual_content":
            entity_type = _normalize_text(parsed_payload.get("entity_type"), 40) or "project"
            entity_id = _normalize_text(parsed_payload.get("entity_id"), 120)
            return f"已读取 {entity_type} 手册 {entity_id or ''}，用于整理答案与规则依据。".strip()
        if tool_name == "get_content":
            entity_type = _normalize_text(parsed_payload.get("entity_type"), 40)
            entity_id = _normalize_text(parsed_payload.get("entity_id"), 120)
            if entity_type or entity_id:
                return f"已读取 {entity_type or '目标对象'} {entity_id or ''} 的结构化上下文。".strip()
    text = _normalize_text(tool_payload.get("text"), 2000)
    if text:
        return text
    result = tool_payload.get("result")
    if isinstance(result, dict):
        return _normalize_text(json.dumps(result, ensure_ascii=False), 2000)
    return ""


def _build_query_tool_solution_summary(tool_name: str, tool_payload: dict[str, Any]) -> str:
    parsed_payload = tool_payload.get("parsed_payload")
    if tool_name == "search_ids":
        return "通过 ID 检索聚合项目、员工和规则命中结果，再整理后返回。"
    if tool_name == "list_project_members":
        return "通过项目成员列表查询当前项目的有效成员，并汇总人数与成员名称后返回。"
    if tool_name == "get_project_runtime_context":
        return "通过读取项目运行时上下文整理成员、规则和当前配置，再返回关键信息。"
    if tool_name == "resolve_relevant_context":
        if isinstance(parsed_payload, dict) and parsed_payload.get("matched_experience_rules"):
            return "通过聚合相关成员、规则、工具和命中的经验规则，筛出与当前问题最相关的信息后返回。"
        return "通过聚合相关成员、规则和工具上下文，筛出与当前问题最相关的信息后返回。"
    if tool_name == "get_manual_content":
        entity_type = ""
        if isinstance(parsed_payload, dict):
            entity_type = _normalize_text(parsed_payload.get("entity_type"), 40) or "目标对象"
        return f"通过读取{entity_type}手册提取与当前问题相关的说明后返回。"
    if tool_name == "get_content":
        return "通过读取目标对象的结构化内容，提取与当前问题直接相关的字段后返回。"
    normalized_tool_name = _normalize_text(tool_name, 120)
    if normalized_tool_name:
        return f"通过执行 {normalized_tool_name} 工具获取结果，并整理后返回。"
    return "通过执行关联查询工具获取结果，并整理后返回。"


def _resolve_project_context(
    query: dict[str, list[str]],
    session_id: str,
    session_contexts: dict[str, dict[str, str]],
) -> tuple[str, str]:
    project_id = _normalize_text(((query.get("project_id") or [""])[0]), 120)
    project_name = _normalize_text(((query.get("project_name") or query.get("project") or [""])[0]), 160)
    if session_id:
        stored = session_contexts.get(session_id) or {}
        project_id = project_id or _normalize_text(stored.get("project_id", ""), 120)
        project_name = project_name or _normalize_text(stored.get("project_name", ""), 160)
    if project_id and not project_name:
        project_name = project_id
    return project_id, project_name


def _resolve_chat_session_id(
    query: dict[str, list[str]],
    session_id: str,
    session_contexts: dict[str, dict[str, str]],
) -> str:
    chat_session_id = _normalize_text(
        ((query.get("chat_session_id") or query.get("chatSessionId") or [""])[0]),
        120,
    )
    if session_id:
        stored = session_contexts.get(session_id) or {}
        chat_session_id = chat_session_id or _normalize_text(
            stored.get("chat_session_id", ""),
            120,
        )
    return chat_session_id or _normalize_text(session_id, 120)


def _safe_session_token(value: object, *, default: str = "unknown", limit: int = 32) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip("._-")
    return (normalized[:limit] or default).strip("._-") or default


def _build_query_cli_chat_session_id(
    project_id: str,
    *,
    key_owner_username: str = "",
    developer_name: str = "",
    request_token: str = "",
) -> str:
    project_token = _safe_session_token(project_id, default="project", limit=36)
    user_token = _safe_session_token(
        key_owner_username or developer_name,
        default="user",
        limit=36,
    )
    request_suffix = _safe_session_token(
        request_token or uuid.uuid4().hex[:10],
        default="req",
        limit=24,
    )
    return f"query-cli.{project_token}.{user_token}.{request_suffix}"[:120]


def _build_direct_cli_context_key(
    project_id: str,
    *,
    key_owner_username: str = "",
    developer_name: str = "",
) -> str:
    project_token = _safe_session_token(project_id, default="project", limit=36)
    user_token = _safe_session_token(
        key_owner_username or developer_name,
        default="user",
        limit=36,
    )
    return f"direct-cli-context.{project_token}.{user_token}"[:120]


def _resolve_key_owner_username(usage_store, api_key: str) -> str:
    normalized_key = _normalize_text(api_key, 120)
    if not normalized_key:
        return ""
    get_key = getattr(usage_store, "get_key", None)
    if not callable(get_key):
        return ""
    try:
        record = get_key(normalized_key) or {}
    except Exception:
        return ""
    return _normalize_text(getattr(record, "get", lambda *_: "")("created_by", ""), 120)


def _resolve_request_auth(scope: dict[str, Any], usage_store, session_keys: dict[str, tuple[str, str]]):
    path = str(scope.get("path", ""))
    method = str(scope.get("method", "")).upper()
    qs = parse_qs(scope.get("query_string", b"").decode())
    api_key = (qs.get("key") or [""])[0]
    session_id = (qs.get("session_id") or [""])[0]
    is_sse = path.rstrip("/").endswith("/sse")
    is_streamable = path.rstrip("/").endswith("/mcp")
    is_messages = path.rstrip("/").endswith("/messages") or "/messages/" in path

    if is_sse or is_streamable:
        if not api_key:
            return None, JSONResponse(
                {"detail": "Missing API key. Add ?key=YOUR_API_KEY to the URL."},
                status_code=401,
            )
        developer_name = usage_store.validate_key(api_key)
        if not developer_name:
            return None, JSONResponse({"detail": "Invalid or deactivated API key."}, status_code=403)
    elif is_messages:
        if session_id and session_id in session_keys:
            api_key, developer_name = session_keys[session_id]
        else:
            return None, JSONResponse({"detail": "Unauthorized session."}, status_code=401)
    else:
        api_key = ""
        developer_name = ""

    return {
        "path": path,
        "method": method,
        "query": qs,
        "api_key": api_key,
        "developer_name": developer_name,
        "key_owner_username": _resolve_key_owner_username(usage_store, api_key),
        "is_sse": is_sse,
        "is_streamable": is_streamable,
        "is_messages": is_messages,
    }, None


def _rewrite_downstream_scope(scope: dict[str, Any], *, is_sse: bool, method: str, replace_path_suffix: Callable[[str, str, str], str]):
    if not is_sse or method == "GET":
        return scope
    rewritten_path = replace_path_suffix(str(scope.get("path", "")), "/sse", "/mcp")
    rewritten_scope = dict(scope)
    rewritten_scope["path"] = rewritten_path
    rewritten_scope["raw_path"] = rewritten_path.encode("utf-8")
    return rewritten_scope


class ProjectMcpProxyApp:
    def __init__(
        self,
        *,
        project_store,
        employee_store,
        usage_store,
        current_api_key_ctx,
        current_developer_name_ctx,
        current_key_owner_username_ctx=None,
        current_mcp_session_id_ctx=None,
        session_keys: dict[str, tuple[str, str]],
        session_contexts: dict[str, dict[str, str]],
        project_apps: dict[str, Any],
        project_app_signatures: dict[str, Any],
        create_project_mcp: Callable[[str], Any],
        list_visible_external_mcp_modules: Callable[[str], list[Any]],
        replace_path_suffix: Callable[[str, str, str], str],
        dual_transport_app_type: type,
        project_mcp_app_rev: str,
    ) -> None:
        self._project_store = project_store
        self._employee_store = employee_store
        self._usage_store = usage_store
        self._current_api_key_ctx = current_api_key_ctx
        self._current_developer_name_ctx = current_developer_name_ctx
        self._current_key_owner_username_ctx = current_key_owner_username_ctx
        self._current_mcp_session_id_ctx = current_mcp_session_id_ctx
        self._session_keys = session_keys
        self._session_contexts = session_contexts
        self._project_apps = project_apps
        self._project_app_signatures = project_app_signatures
        self._create_project_mcp = create_project_mcp
        self._list_visible_external_mcp_modules = list_visible_external_mcp_modules
        self._replace_path_suffix = replace_path_suffix
        self._dual_transport_app_type = dual_transport_app_type
        self._project_mcp_app_rev = project_mcp_app_rev

    async def __call__(self, scope, receive, send):
        project_id = scope.get("path_params", {}).get("project_id")
        if not project_id:
            response = JSONResponse({"detail": "Missing project_id"}, status_code=400)
            await response(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        if _is_well_known_probe(path):
            response = Response(status_code=204)
            await response(scope, receive, send)
            return

        project = self._project_store.get(project_id)
        if not project:
            response = JSONResponse({"detail": "Project not found."}, status_code=404)
            await response(scope, receive, send)
            return
        if not getattr(project, "mcp_enabled", True):
            response = JSONResponse({"detail": "Project MCP service is disabled."}, status_code=404)
            await response(scope, receive, send)
            return

        auth_state, auth_error = _resolve_request_auth(scope, self._usage_store, self._session_keys)
        if auth_error is not None:
            await auth_error(scope, receive, send)
            return
        assert auth_state is not None

        api_key = auth_state["api_key"]
        developer_name = auth_state["developer_name"]
        key_owner_username = auth_state["key_owner_username"]
        method = auth_state["method"]
        query = auth_state["query"]
        is_sse = auth_state["is_sse"]
        is_streamable = auth_state["is_streamable"]
        is_messages = auth_state["is_messages"]

        client_ip = get_client_ip(scope)
        self._current_api_key_ctx.set(api_key)
        self._current_developer_name_ctx.set(developer_name)
        if self._current_key_owner_username_ctx is not None:
            self._current_key_owner_username_ctx.set(key_owner_username)
        if self._current_mcp_session_id_ctx is not None:
            self._current_mcp_session_id_ctx.set(((query.get("session_id") or [""])[0]).strip())

        try:
            await _touch_project_mcp_presence(
                endpoint_type="project",
                entity_id=str(project_id),
                entity_name=str(getattr(project, "name", "") or ""),
                project_id=str(project_id),
                project_name=str(getattr(project, "name", "") or ""),
                developer_name=developer_name,
                key_owner_username=key_owner_username,
                api_key=api_key,
                client_ip=client_ip,
                transport="sse" if is_sse else "streamable-http" if is_streamable else "messages" if is_messages else "http",
                method=method,
                path=path,
                session_id=((query.get("session_id") or [""])[0]).strip(),
            )
        except Exception:
            pass

        usage_scope_id = f"project:{project_id}"
        if is_sse and method == "GET":
            self._usage_store.record_event(usage_scope_id, api_key, developer_name, "connection", client_ip=client_ip)

        tracking_send = create_tracking_send(
            send,
            is_sse=is_sse,
            method=method,
            api_key=api_key,
            developer_name=developer_name,
            session_keys=self._session_keys,
        )
        tracking_receive = create_tracking_receive(
            receive,
            usage_scope_id=usage_scope_id,
            api_key=api_key,
            developer_name=developer_name,
            client_ip=client_ip,
            session_id=((query.get("session_id") or [""])[0]).strip(),
            session_contexts=self._session_contexts,
        )

        members = self._project_store.list_members(project_id)
        active_members = [m for m in members if bool(getattr(m, "enabled", True))]
        member_signature = tuple(
            sorted(
                (
                    str(getattr(m, "employee_id", "")),
                    bool(getattr(m, "enabled", True)),
                    str(getattr(m, "role", "")),
                )
                for m in members
            )
        )
        employee_signature = tuple(
            sorted(
                (
                    employee.id,
                    employee.updated_at,
                    tuple(employee.skills or []),
                    tuple(employee.rule_ids or []),
                )
                for m in active_members
                for employee in [self._employee_store.get(m.employee_id)]
                if employee is not None
            )
        )
        external_signature = tuple(
            sorted(
                (
                    str(getattr(module, "id", "") or ""),
                    str(getattr(module, "updated_at", "") or ""),
                    str(getattr(module, "endpoint_http", "") or ""),
                    str(getattr(module, "endpoint_sse", "") or ""),
                    str(getattr(module, "project_id", "") or ""),
                    bool(getattr(module, "enabled", True)),
                )
                for module in self._list_visible_external_mcp_modules(project_id)
            )
        )
        signature = (
            self._project_mcp_app_rev,
            project.updated_at,
            bool(getattr(project, "mcp_enabled", True)),
            member_signature,
            employee_signature,
            external_signature,
        )
        cached_app = self._project_apps.get(project_id)
        if (
            cached_app is None
            or not isinstance(cached_app, self._dual_transport_app_type)
            or self._project_app_signatures.get(project_id) != signature
        ):
            self._project_apps[project_id] = self._create_project_mcp(project_id)
            self._project_app_signatures[project_id] = signature

        downstream_scope = _rewrite_downstream_scope(
            scope,
            is_sse=is_sse,
            method=method,
            replace_path_suffix=self._replace_path_suffix,
        )
        await self._project_apps[project_id](downstream_scope, tracking_receive, tracking_send)


class EmployeeMcpProxyApp:
    def __init__(
        self,
        *,
        employee_store,
        usage_store,
        current_api_key_ctx,
        current_developer_name_ctx,
        session_keys: dict[str, tuple[str, str]],
        session_contexts: dict[str, dict[str, str]],
        employee_apps: dict[str, Any],
        employee_app_signatures: dict[str, Any],
        create_employee_mcp: Callable[[str], Any],
        save_auto_user_question_memory: Callable[[str, list[str], str, str], None],
        replace_path_suffix: Callable[[str, str, str], str],
        dual_transport_app_type: type,
        employee_mcp_app_rev: str,
    ) -> None:
        self._employee_store = employee_store
        self._usage_store = usage_store
        self._current_api_key_ctx = current_api_key_ctx
        self._current_developer_name_ctx = current_developer_name_ctx
        self._session_keys = session_keys
        self._session_contexts = session_contexts
        self._employee_apps = employee_apps
        self._employee_app_signatures = employee_app_signatures
        self._create_employee_mcp = create_employee_mcp
        self._save_auto_user_question_memory = save_auto_user_question_memory
        self._replace_path_suffix = replace_path_suffix
        self._dual_transport_app_type = dual_transport_app_type
        self._employee_mcp_app_rev = employee_mcp_app_rev

    async def __call__(self, scope, receive, send):
        employee_id = scope.get("path_params", {}).get("employee_id")
        if not employee_id:
            response = JSONResponse({"detail": "Missing employee_id"}, status_code=400)
            await response(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        if _is_well_known_probe(path):
            response = Response(status_code=204)
            await response(scope, receive, send)
            return

        employee = self._employee_store.get(employee_id)
        if not employee:
            response = JSONResponse({"detail": "Employee not found."}, status_code=404)
            await response(scope, receive, send)
            return
        if not getattr(employee, "mcp_enabled", True):
            response = JSONResponse({"detail": "Employee MCP service is disabled."}, status_code=404)
            await response(scope, receive, send)
            return

        auth_state, auth_error = _resolve_request_auth(scope, self._usage_store, self._session_keys)
        if auth_error is not None:
            await auth_error(scope, receive, send)
            return
        assert auth_state is not None

        api_key = auth_state["api_key"]
        developer_name = auth_state["developer_name"]
        key_owner_username = auth_state["key_owner_username"]
        method = auth_state["method"]
        query = auth_state["query"]
        is_sse = auth_state["is_sse"]
        session_id = ((query.get("session_id") or [""])[0]).strip()
        project_id_from_query, project_name_from_query = _resolve_project_context(
            query,
            session_id,
            self._session_contexts,
        )
        is_streamable = auth_state["is_streamable"]
        is_messages = auth_state["is_messages"]

        client_ip = get_client_ip(scope)
        self._current_api_key_ctx.set(api_key)
        self._current_developer_name_ctx.set(developer_name)

        try:
            await _touch_project_mcp_presence(
                endpoint_type="employee",
                entity_id=str(employee_id),
                entity_name=str(getattr(employee, "name", "") or employee_id),
                project_id=project_id_from_query,
                project_name=project_name_from_query,
                developer_name=developer_name,
                key_owner_username=key_owner_username,
                api_key=api_key,
                client_ip=client_ip,
                transport="sse" if is_sse else "streamable-http" if is_streamable else "messages" if is_messages else "http",
                method=method,
                path=path,
                session_id=session_id,
            )
        except Exception:
            pass

        if is_sse and method == "GET":
            self._usage_store.record_event(employee_id, api_key, developer_name, "connection", client_ip=client_ip)

        tracking_send = create_tracking_send(
            send,
            is_sse=is_sse,
            method=method,
            api_key=api_key,
            developer_name=developer_name,
            session_keys=self._session_keys,
        )

        async def _handle_context(
            method_name: str,
            tool_name: str,
            context: dict[str, str],
        ) -> None:
            resolved_project_id, resolved_project_name = _resolve_project_context(
                query,
                session_id,
                self._session_contexts,
            )
            if not resolved_project_id and not resolved_project_name:
                return
            try:
                await _touch_project_mcp_presence(
                    endpoint_type="employee",
                    entity_id=str(employee_id),
                    entity_name=str(getattr(employee, "name", "") or employee_id),
                    project_id=resolved_project_id,
                    project_name=resolved_project_name,
                    developer_name=developer_name,
                    key_owner_username=key_owner_username,
                    api_key=api_key,
                    client_ip=client_ip,
                    transport="sse" if is_sse else "streamable-http" if is_streamable else "messages" if is_messages else "http",
                    method=method,
                    path=path,
                    session_id=session_id,
                )
            except Exception:
                pass

        def _handle_questions(
            method_name: str,
            tool_name: str,
            questions: list[str],
            context: dict[str, str],
        ) -> None:
            source = f"mcp:{method_name or 'unknown'}:{tool_name or '-'}"
            self._save_auto_user_question_memory(
                employee_id,
                questions,
                source,
                str((context or {}).get("project_name") or project_name_from_query or "default"),
            )

        tracking_receive = create_tracking_receive(
            receive,
            usage_scope_id=employee_id,
            api_key=api_key,
            developer_name=developer_name,
            client_ip=client_ip,
            session_id=session_id,
            session_contexts=self._session_contexts,
            on_context=_handle_context,
            on_questions=_handle_questions,
        )

        signature = (
            self._employee_mcp_app_rev,
            tuple(employee.skills or []),
            tuple(employee.rule_ids or []),
            bool(getattr(employee, "mcp_enabled", True)),
            employee.updated_at,
        )
        cached_app = self._employee_apps.get(employee_id)
        if (
            cached_app is None
            or not isinstance(cached_app, self._dual_transport_app_type)
            or self._employee_app_signatures.get(employee_id) != signature
        ):
            self._employee_apps[employee_id] = self._create_employee_mcp(employee_id)
            self._employee_app_signatures[employee_id] = signature

        downstream_scope = _rewrite_downstream_scope(
            scope,
            is_sse=is_sse,
            method=method,
            replace_path_suffix=self._replace_path_suffix,
        )
        await self._employee_apps[employee_id](downstream_scope, tracking_receive, tracking_send)


class QueryMcpProxyApp:
    def __init__(
        self,
        *,
        usage_store,
        current_api_key_ctx,
        current_developer_name_ctx,
        current_key_owner_username_ctx=None,
        current_mcp_session_id_ctx=None,
        session_keys: dict[str, tuple[str, str]],
        session_contexts: dict[str, dict[str, str]],
        query_app,
        save_auto_query_memory: Callable[..., None],
        replace_path_suffix: Callable[[str, str, str], str],
    ) -> None:
        self._usage_store = usage_store
        self._current_api_key_ctx = current_api_key_ctx
        self._current_developer_name_ctx = current_developer_name_ctx
        self._current_key_owner_username_ctx = current_key_owner_username_ctx
        self._current_mcp_session_id_ctx = current_mcp_session_id_ctx
        self._session_keys = session_keys
        self._session_contexts = session_contexts
        self._query_app = query_app
        self._save_auto_query_memory = save_auto_query_memory
        self._replace_path_suffix = replace_path_suffix

    async def __call__(self, scope, receive, send):
        path = str(scope.get("path", ""))
        if _is_well_known_probe(path):
            response = Response(status_code=204)
            await response(scope, receive, send)
            return

        auth_state, auth_error = _resolve_request_auth(scope, self._usage_store, self._session_keys)
        if auth_error is not None:
            await auth_error(scope, receive, send)
            return
        assert auth_state is not None

        api_key = auth_state["api_key"]
        developer_name = auth_state["developer_name"]
        key_owner_username = auth_state["key_owner_username"]
        method = auth_state["method"]
        query = auth_state["query"]
        is_sse = auth_state["is_sse"]
        is_streamable = auth_state["is_streamable"]
        is_messages = auth_state["is_messages"]
        accept_header = ""
        for name, value in scope.get("headers") or []:
            if bytes(name).lower() == b"accept":
                accept_header = value.decode("latin-1", errors="ignore").lower()
                break
        expects_event_stream_response = "text/event-stream" in accept_header
        session_id = ((query.get("session_id") or [""])[0]).strip()
        request_token = uuid.uuid4().hex[:10]
        chat_session_id = _resolve_chat_session_id(query, session_id, self._session_contexts)
        project_id_from_query, project_name_from_query = _resolve_project_context(
            query,
            session_id,
            self._session_contexts,
        )
        direct_cli_fallback_enabled = bool(
            not session_id and method != "GET" and (is_streamable or is_sse)
        )
        direct_cli_context_key = ""
        persisted_direct_state: dict[str, str] = {}
        if direct_cli_fallback_enabled and project_id_from_query:
            persisted_direct_state = load_resumable_query_mcp_local_state(project_id_from_query)
            direct_cli_context_key = _build_direct_cli_context_key(
                project_id_from_query,
                key_owner_username=key_owner_username,
                developer_name=developer_name,
            )
            stored_direct_context = self._session_contexts.get(direct_cli_context_key) or {}
            if not chat_session_id:
                chat_session_id = _normalize_text(
                    stored_direct_context.get("chat_session_id", ""),
                    120,
                )
            if not chat_session_id:
                chat_session_id = _normalize_text(
                    persisted_direct_state.get("chat_session_id", ""),
                    120,
                )
        direct_cli_chat_session_id = ""

        def _persist_project_local_state(**extra: str) -> dict[str, Any]:
            resolved_project_id = _normalize_text(
                extra.get("project_id") or project_id_from_query,
                120,
            )
            resolved_chat_session_id = _normalize_text(
                extra.get("chat_session_id") or chat_session_id or direct_cli_chat_session_id,
                200,
            )
            if not resolved_project_id or not resolved_chat_session_id:
                return {}
            return persist_query_mcp_local_state(
                project_id=resolved_project_id,
                project_name=_normalize_text(
                    extra.get("project_name") or project_name_from_query,
                    200,
                ),
                employee_id=_normalize_text(extra.get("employee_id"), 120),
                chat_session_id=resolved_chat_session_id,
                session_id=_normalize_text(extra.get("work_session_id"), 200),
                root_goal=_normalize_text(extra.get("root_goal"), 1000),
                latest_status=_normalize_text(extra.get("latest_status"), 80),
                phase=_normalize_text(extra.get("phase"), 80),
                step=_normalize_text(extra.get("step"), 200),
                developer_name=developer_name,
                key_owner_username=key_owner_username,
                source=_normalize_text(extra.get("source"), 120),
            )

        def _ensure_direct_cli_chat_session_id(project_id_hint: str = "") -> str:
            nonlocal chat_session_id, direct_cli_chat_session_id
            if chat_session_id:
                return chat_session_id
            normalized_project_id = _normalize_text(project_id_hint or project_id_from_query, 120)
            if not (direct_cli_fallback_enabled and normalized_project_id):
                return ""
            context_key = direct_cli_context_key or _build_direct_cli_context_key(
                normalized_project_id,
                key_owner_username=key_owner_username,
                developer_name=developer_name,
            )
            stored_direct_context = self._session_contexts.get(context_key) or {}
            stored_chat_session_id = _normalize_text(
                stored_direct_context.get("chat_session_id", ""),
                120,
            )
            if stored_chat_session_id:
                direct_cli_chat_session_id = stored_chat_session_id
            if not direct_cli_chat_session_id:
                direct_cli_chat_session_id = _normalize_text(
                    persisted_direct_state.get("chat_session_id", ""),
                    120,
                )
            if not direct_cli_chat_session_id:
                direct_cli_chat_session_id = _build_query_cli_chat_session_id(
                    normalized_project_id,
                    key_owner_username=key_owner_username,
                    developer_name=developer_name,
                    request_token=request_token,
                )
            chat_session_id = direct_cli_chat_session_id
            self._session_contexts[context_key] = {
                "project_id": normalized_project_id,
                "project_name": str(project_name_from_query or "").strip(),
                "employee_id": str((stored_direct_context or {}).get("employee_id") or "").strip(),
                "chat_session_id": chat_session_id,
            }
            if self._current_mcp_session_id_ctx is not None:
                self._current_mcp_session_id_ctx.set(chat_session_id or session_id)
            _persist_project_local_state(
                project_id=normalized_project_id,
                project_name=str(project_name_from_query or "").strip(),
                employee_id=str((stored_direct_context or {}).get("employee_id") or "").strip(),
                chat_session_id=chat_session_id,
                source="direct_cli_fallback",
            )
            return chat_session_id

        if not chat_session_id:
            _ensure_direct_cli_chat_session_id(project_id_from_query)
        employee_id_from_query = ((query.get("employee_id") or [""])[0]).strip()
        initial_session_context = {
            "project_id": str(project_id_from_query or "").strip(),
            "project_name": str(project_name_from_query or "").strip(),
            "employee_id": str(employee_id_from_query or "").strip(),
            "chat_session_id": str(chat_session_id or "").strip(),
        }
        if session_id and any(initial_session_context.values()):
            stored_context = self._session_contexts.get(session_id) or {}
            self._session_contexts[session_id] = {
                "project_id": initial_session_context["project_id"]
                or str(stored_context.get("project_id") or "").strip(),
                "project_name": initial_session_context["project_name"]
                or str(stored_context.get("project_name") or "").strip(),
                "employee_id": initial_session_context["employee_id"]
                or str(stored_context.get("employee_id") or "").strip(),
                "chat_session_id": initial_session_context["chat_session_id"]
                or str(stored_context.get("chat_session_id") or "").strip(),
            }
        elif direct_cli_context_key and any(initial_session_context.values()):
            stored_context = self._session_contexts.get(direct_cli_context_key) or {}
            self._session_contexts[direct_cli_context_key] = {
                "project_id": initial_session_context["project_id"]
                or str(stored_context.get("project_id") or "").strip(),
                "project_name": initial_session_context["project_name"]
                or str(stored_context.get("project_name") or "").strip(),
                "employee_id": initial_session_context["employee_id"]
                or str(stored_context.get("employee_id") or "").strip(),
                "chat_session_id": initial_session_context["chat_session_id"]
                or str(stored_context.get("chat_session_id") or "").strip(),
            }

        client_ip = get_client_ip(scope)
        self._current_api_key_ctx.set(api_key)
        self._current_developer_name_ctx.set(developer_name)
        if self._current_key_owner_username_ctx is not None:
            self._current_key_owner_username_ctx.set(key_owner_username)
        if self._current_mcp_session_id_ctx is not None:
            self._current_mcp_session_id_ctx.set(chat_session_id or session_id)

        try:
            await _touch_project_mcp_presence(
                endpoint_type="query",
                entity_id="query-center",
                entity_name="统一查询 MCP",
                project_id=project_id_from_query,
                project_name=project_name_from_query,
                developer_name=developer_name,
                key_owner_username=key_owner_username,
                api_key=api_key,
                client_ip=client_ip,
                transport="sse" if is_sse else "streamable-http" if is_streamable else "messages" if is_messages else "http",
                method=method,
                path=path,
                session_id=session_id,
            )
        except Exception:
            pass

        usage_scope_id = "mcp:query"
        if is_sse and method == "GET":
            self._usage_store.record_event(
                usage_scope_id,
                api_key,
                developer_name,
                "connection",
                client_ip=client_ip,
            )

        request_state: dict[str, Any] = {"rpc_calls": []}

        def _resolve_effective_chat_session_id(context: dict[str, str] | None = None) -> str:
            resolved = str((context or {}).get("chat_session_id") or chat_session_id).strip()
            if resolved:
                return resolved
            if not direct_cli_fallback_enabled:
                return ""
            return direct_cli_chat_session_id

        def _handle_tool_result(
            method_name: str,
            tool_name: str,
            tool_payload: dict[str, Any],
            context: dict[str, str],
            metadata: dict[str, Any],
        ) -> None:
            parsed_payload = tool_payload.get("parsed_payload")
            if isinstance(parsed_payload, dict):
                task_tree_payload = (
                    parsed_payload.get("task_tree")
                    if isinstance(parsed_payload.get("task_tree"), dict)
                    else {}
                )
                trajectory_payload = (
                    parsed_payload.get("trajectory")
                    if isinstance(parsed_payload.get("trajectory"), dict)
                    else {}
                )
                _persist_project_local_state(
                    project_id=str((context or {}).get("project_id") or parsed_payload.get("project_id") or ""),
                    project_name=str((context or {}).get("project_name") or parsed_payload.get("project_name") or ""),
                    employee_id=str((context or {}).get("employee_id") or parsed_payload.get("employee_id") or ""),
                    chat_session_id=str(
                        parsed_payload.get("chat_session_id")
                        or task_tree_payload.get("chat_session_id")
                        or trajectory_payload.get("task_tree_chat_session_id")
                        or (context or {}).get("chat_session_id")
                        or ""
                    ),
                    work_session_id=str(
                        parsed_payload.get("session_id")
                        or trajectory_payload.get("session_id")
                        or ""
                    ),
                    root_goal=str(
                        parsed_payload.get("goal")
                        or parsed_payload.get("root_goal")
                        or task_tree_payload.get("root_goal")
                        or ""
                    ),
                    latest_status=str(
                        parsed_payload.get("status")
                        or parsed_payload.get("initial_status")
                        or trajectory_payload.get("status")
                        or task_tree_payload.get("status")
                        or ""
                    ),
                    phase=str(parsed_payload.get("phase") or trajectory_payload.get("phase") or ""),
                    step=str(parsed_payload.get("step") or trajectory_payload.get("step") or ""),
                    source=f"tool_result:{_normalize_text(tool_name, 120)}",
                )
            if method_name != "tools/call":
                return
            normalized_tool_name = _normalize_text(tool_name, 120)
            if not normalized_tool_name or normalized_tool_name in _QUERY_TASK_TREE_AUDIT_SKIP_TOOLS:
                return
            if bool(tool_payload.get("is_error")):
                return
            resolved_project_id = str((context or {}).get("project_id") or project_id_from_query).strip()
            resolved_chat_session_id = _resolve_effective_chat_session_id(context)
            resolved_username = str(key_owner_username or developer_name).strip()
            if not (resolved_project_id and resolved_chat_session_id and resolved_username):
                return
            assistant_content = _build_query_tool_result_summary(normalized_tool_name, tool_payload)
            if not assistant_content:
                return
            task_tree_audit_payload = None
            try:
                task_tree_audit_payload = audit_task_tree_round(
                    project_id=resolved_project_id,
                    username=resolved_username,
                    chat_session_id=resolved_chat_session_id,
                    assistant_content=assistant_content,
                    successful_tool_names=[normalized_tool_name],
                )
            except Exception:
                pass
            if normalized_tool_name in _QUERY_RESULT_MEMORY_SKIP_TOOLS:
                return
            question_candidates = metadata.get("questions") if isinstance(metadata, dict) else []
            primary_question = ""
            if isinstance(question_candidates, list):
                for item in question_candidates:
                    candidate = _normalize_text(item, 1000)
                    if candidate:
                        primary_question = candidate
                        break
            if not primary_question:
                return
            try:
                save_auto_query_result_memory(
                    primary_question,
                    _build_query_tool_solution_summary(normalized_tool_name, tool_payload),
                    assistant_content,
                    f"mcp:{method_name or 'unknown'}:{normalized_tool_name}",
                    project_id=resolved_project_id,
                    employee_id=str((context or {}).get("employee_id") or employee_id_from_query),
                    project_name=str((context or {}).get("project_name") or project_name_from_query),
                    chat_session_id=resolved_chat_session_id,
                    task_tree_payload=(
                        (task_tree_audit_payload or {}).get("history_task_tree")
                        or (task_tree_audit_payload or {}).get("task_tree")
                    ) if isinstance(task_tree_audit_payload, dict) else None,
                )
            except Exception:
                pass

        tracking_send = create_tracking_send(
            send,
            is_sse=is_sse,
            method=method,
            api_key=api_key,
            developer_name=developer_name,
            session_keys=self._session_keys,
            session_contexts=self._session_contexts,
            session_context=initial_session_context,
            request_state=request_state,
            on_tool_result=_handle_tool_result,
        )

        async def _handle_context(
            method_name: str,
            tool_name: str,
            context: dict[str, str],
        ) -> None:
            resolved_project_id = str((context or {}).get("project_id") or project_id_from_query).strip()
            resolved_project_name = str((context or {}).get("project_name") or project_name_from_query).strip()
            resolved_chat_session_id = _resolve_effective_chat_session_id(context)
            if resolved_project_id and resolved_chat_session_id:
                _persist_project_local_state(
                    project_id=resolved_project_id,
                    project_name=resolved_project_name,
                    employee_id=str((context or {}).get("employee_id") or employee_id_from_query),
                    chat_session_id=resolved_chat_session_id,
                    source=f"context:{_normalize_text(tool_name or method_name, 120)}",
                )
            resolved_project_id, resolved_project_name = _resolve_project_context(
                query,
                session_id,
                self._session_contexts,
            )
            if not resolved_project_id and not resolved_project_name:
                return
            try:
                await _touch_project_mcp_presence(
                    endpoint_type="query",
                    entity_id="query-center",
                    entity_name="统一查询 MCP",
                    project_id=resolved_project_id,
                    project_name=resolved_project_name,
                    developer_name=developer_name,
                    key_owner_username=key_owner_username,
                    api_key=api_key,
                    client_ip=client_ip,
                    transport="sse" if is_sse else "streamable-http" if is_streamable else "messages" if is_messages else "http",
                    method=method,
                    path=path,
                    session_id=session_id,
                )
            except Exception:
                pass

        def _handle_questions(
            method_name: str,
            tool_name: str,
            questions: list[str],
            context: dict[str, str],
        ) -> None:
            resolved_project_id = str((context or {}).get("project_id") or project_id_from_query).strip()
            resolved_chat_session_id = _resolve_effective_chat_session_id(context)
            resolved_username = str(key_owner_username or developer_name).strip()
            normalized_tool_name = _normalize_text(tool_name, 120)
            should_skip_question_bootstrap = (
                normalized_tool_name == "search_ids"
                and expects_event_stream_response
                and not is_sse
            )
            if (
                resolved_project_id
                and resolved_chat_session_id
                and resolved_username
                and normalized_tool_name not in _QUERY_QUESTION_TASK_TREE_SKIP_TOOLS
                and not should_skip_question_bootstrap
            ):
                root_goal = ""
                for item in questions or []:
                    normalized_question = _normalize_text(item, 1000)
                    if normalized_question:
                        root_goal = normalized_question
                        break
                if root_goal:
                    try:
                        ensure_task_tree(
                            project_id=resolved_project_id,
                            username=resolved_username,
                            chat_session_id=resolved_chat_session_id,
                            root_goal=root_goal,
                        )
                    except Exception:
                        pass
            source = f"mcp:{method_name or 'unknown'}:{tool_name or '-'}"
            self._save_auto_query_memory(
                questions,
                source,
                project_id=resolved_project_id,
                employee_id=str((context or {}).get("employee_id") or employee_id_from_query),
                project_name=str((context or {}).get("project_name") or project_name_from_query),
                chat_session_id=resolved_chat_session_id,
            )

        tracking_receive = create_tracking_receive(
            receive,
            usage_scope_id=usage_scope_id,
            api_key=api_key,
            developer_name=developer_name,
            client_ip=client_ip,
            session_id=session_id,
            session_contexts=self._session_contexts,
            resolve_fallback_chat_session_id=lambda context: _ensure_direct_cli_chat_session_id(
                str((context or {}).get("project_id") or "").strip()
            ),
            on_context=_handle_context,
            on_questions=_handle_questions,
            request_state=request_state,
        )

        downstream_scope = _rewrite_downstream_scope(
            scope,
            is_sse=is_sse,
            method=method,
            replace_path_suffix=self._replace_path_suffix,
        )
        await self._query_app(downstream_scope, tracking_receive, tracking_send)
