"""Proxy ASGI apps for dynamic MCP project/employee endpoints."""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import parse_qs

from fastapi.responses import JSONResponse, Response

from services.dynamic_mcp_audit import (
    create_tracking_receive,
    create_tracking_send,
    get_client_ip,
)


def _is_well_known_probe(path: str) -> bool:
    return (
        "/.well-known/oauth-authorization-server" in path
        or "/.well-known/openid-configuration" in path
        or "/.well-known/oauth-protected-resource" in path
    )


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
        session_keys: dict[str, tuple[str, str]],
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
        self._session_keys = session_keys
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
        method = auth_state["method"]
        is_sse = auth_state["is_sse"]

        client_ip = get_client_ip(scope)
        self._current_api_key_ctx.set(api_key)
        self._current_developer_name_ctx.set(developer_name)

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
        method = auth_state["method"]
        query = auth_state["query"]
        is_sse = auth_state["is_sse"]
        project_name_from_query = (
            (query.get("project_name") or query.get("project_id") or query.get("project") or [""])[0]
        ).strip()

        client_ip = get_client_ip(scope)
        self._current_api_key_ctx.set(api_key)
        self._current_developer_name_ctx.set(developer_name)

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

        def _handle_questions(method_name: str, tool_name: str, questions: list[str], project_name: str) -> None:
            source = f"mcp:{method_name or 'unknown'}:{tool_name or '-'}"
            self._save_auto_user_question_memory(
                employee_id,
                questions,
                source,
                project_name or project_name_from_query or "default",
            )

        tracking_receive = create_tracking_receive(
            receive,
            usage_scope_id=employee_id,
            api_key=api_key,
            developer_name=developer_name,
            client_ip=client_ip,
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
