"""动态 Micro-MCP 服务生成器"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import asdict
from datetime import timedelta
import json
import os
from pathlib import Path
from urllib.parse import parse_qs

from services.dynamic_mcp_skill_executor import execute_skill_proxy as _execute_skill_proxy

from fastapi.responses import JSONResponse, Response
from mcp.server.fastmcp import FastMCP

from services.dynamic_mcp_apps_basic import (
    create_rule_mcp as _create_rule_mcp,
    create_skill_mcp as _create_skill_mcp,
)
from services.dynamic_mcp_apps_employee import create_employee_mcp as _create_employee_mcp_impl
from services.dynamic_mcp_apps_project import create_project_mcp as _create_project_mcp_impl
from services.dynamic_mcp_apps_query import create_query_mcp as _create_query_mcp_impl
from starlette.types import ASGIApp, Receive, Scope, Send

from services.dynamic_mcp_context import (
    get_project_detail_runtime,
    get_project_employee_detail_runtime,
    query_project_mcp_modules_runtime,
    search_project_context_runtime,
)
from services.dynamic_mcp_collaboration import (
    COLLABORATION_TOOL_NAME,
    attach_task_tree_context,
    collaboration_tool_descriptor,
    ensure_project_execution_task_tree,
    execute_project_collaboration_runtime,
    extract_execution_task_text,
    invoke_project_builtin_tool,
    parse_object_args,
)
from services.dynamic_mcp_external_tools import (
    _list_visible_external_mcp_modules,
    invoke_external_mcp_tool_runtime,
    list_project_external_tools_runtime,
    resolve_external_tool_spec as _resolve_external_tool_spec,
)
from services.dynamic_mcp_profiles import (
    employee_rule_summary as _employee_rule_summary,
    list_project_member_profiles_runtime,
    query_project_members_runtime,
    query_project_rules_runtime,
    query_rules_by_employee as _query_rules_by_employee,
)
from services.dynamic_mcp_skill_proxies import (
    build_project_proxy_specs as _shared_build_project_proxy_specs,
    resolve_project_proxy_tool_spec as _shared_resolve_project_proxy_tool_spec,
)
from services.dynamic_mcp_transports import (
    DualTransportMcpApp as _DualTransportMcpApp,
    apply_mcp_arguments_compat as _apply_mcp_arguments_compat,
    replace_path_suffix as _replace_path_suffix,
)

from core.config import get_project_root
from core.deps import employee_store, external_mcp_store, project_store, usage_store
from services.feedback_service import get_feedback_service
from services.dynamic_mcp_audit import (
    create_tracking_receive,
    create_tracking_send,
    get_client_ip,
    save_auto_query_memory as _save_auto_query_memory,
    save_auto_user_question_memory as _save_auto_user_question_memory,
)
from services.dynamic_mcp_proxy_apps import EmployeeMcpProxyApp, ProjectMcpProxyApp
from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp, _resolve_key_owner_username, _resolve_project_context
from services.project_mcp_presence import touch_project_mcp_presence as _touch_project_mcp_presence
from stores.mcp_bridge import (
    rule_store,
    skill_store,
)


def _load_project_config() -> dict:
    """从项目根目录读取 .mcp-project.json 配置，不存在则创建"""
    try:
        config_path = Path.cwd() / ".mcp-project.json"
        if config_path.exists():
            return json.loads(config_path.read_text(encoding="utf-8"))
        else:
            # 首次使用，创建示例配置
            default_config = {
                "project_id": "default",
                "project_name": "Default Project",
                "description": "请修改此文件，设置你的项目名称"
            }
            config_path.write_text(json.dumps(default_config, ensure_ascii=False, indent=2), encoding="utf-8")
            return default_config
    except Exception:
        pass
    return {}


# 缓存动态生成的 ASGI App
_rule_apps = {}
_skill_apps = {}
_employee_apps = {}
_project_apps = {}
_employee_app_signatures = {}
_project_app_signatures = {}
_session_keys: dict[str, tuple[str, str]] = {}  # session_id -> (api_key, developer_name)
_session_contexts: dict[str, dict[str, str]] = {}  # session_id -> runtime context
_current_api_key: ContextVar[str] = ContextVar("_current_api_key", default="")
_current_developer_name: ContextVar[str] = ContextVar("_current_developer_name", default="")
_current_key_owner_username: ContextVar[str] = ContextVar("_current_key_owner_username", default="")
_current_mcp_session_id: ContextVar[str] = ContextVar("_current_mcp_session_id", default="")
_EMPLOYEE_MCP_APP_REV = "2026-03-04-sse-post-bridge"
_PROJECT_MCP_APP_REV = "2026-03-05-project-mcp-v1"
_PROJECT_ROOT = get_project_root()
_FASTMCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")

# 启动时加载底层安全策略（不可运行时修改，需重启生效）
_SYSTEM_POLICY_PATH = Path(__file__).resolve().parents[1] / "system-policy.md"
_SYSTEM_POLICY = _SYSTEM_POLICY_PATH.read_text(encoding="utf-8") if _SYSTEM_POLICY_PATH.exists() else ""


_RECALL_EMPLOYEE_MEMORY_LIMIT = 100


def _resolve_runtime_task_tree_context(
    username: str = "",
    chat_session_id: str = "",
) -> tuple[str, str]:
    resolved_username = str(username or "").strip()
    if not resolved_username:
        resolved_username = _current_key_owner_username.get("").strip()
    if not resolved_username:
        resolved_username = _current_developer_name.get("").strip()
    resolved_chat_session_id = str(chat_session_id or "").strip() or _current_mcp_session_id.get("").strip()
    return resolved_username, resolved_chat_session_id


def invoke_project_tool_runtime(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
    username: str = "",
    chat_session_id: str = "",
    args: dict | None = None,
    args_json: str = "{}",
    timeout_sec: int = 30,
) -> dict:
    resolved_username, resolved_chat_session_id = _resolve_runtime_task_tree_context(
        username=username,
        chat_session_id=chat_session_id,
    )
    spec, _ = _resolve_external_tool_spec(project_id, tool_name)
    if spec is not None:
        task_tree_payload = ensure_project_execution_task_tree(
            project_id=project_id,
            username=resolved_username,
            chat_session_id=resolved_chat_session_id,
            root_goal=extract_execution_task_text(
                tool_name,
                args=args,
                args_json=args_json,
            ),
        )
        result = invoke_external_mcp_tool_runtime(
            project_id=project_id,
            tool_name=tool_name,
            args=args,
            args_json=args_json,
            timeout_sec=timeout_sec,
        )
        return attach_task_tree_context(
            result,
            task_tree_payload=task_tree_payload,
            username=resolved_username,
            chat_session_id=resolved_chat_session_id,
        )
    return invoke_project_skill_tool_runtime(
        project_id=project_id,
        tool_name=tool_name,
        employee_id=employee_id,
        username=resolved_username,
        chat_session_id=resolved_chat_session_id,
        args=args,
        args_json=args_json,
        timeout_sec=timeout_sec,
    )


def _build_project_proxy_specs(project_id: str) -> tuple[dict[str, dict], dict[str, dict[str, dict]]]:
    return _shared_build_project_proxy_specs(project_id)


def _resolve_project_proxy_tool_spec(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
) -> tuple[dict | None, str]:
    return _shared_resolve_project_proxy_tool_spec(project_id, tool_name, employee_id)


def list_project_proxy_tools_runtime(project_id: str, employee_id: str = "") -> list[dict]:
    """列出项目技能代理工具，供非 MCP 路径（如聊天路由）复用。"""
    employee_id_value = str(employee_id or "").strip()
    scoped_proxy_specs, employee_proxy_specs = _build_project_proxy_specs(project_id)
    tools: list[dict] = []
    if employee_id_value:
        specs = employee_proxy_specs.get(employee_id_value, {})
        for base_tool_name, spec in sorted(specs.items()):
            tools.append(
                {
                    "tool_name": base_tool_name,
                    "employee_id": spec["employee_id"],
                    "base_tool_name": spec["base_tool_name"],
                    "scoped_tool_name": spec["scoped_tool_name"],
                    "skill_id": spec["skill_id"],
                    "skill_name": spec["skill_name"],
                    "entry_name": spec["entry_name"],
                    "runtime": spec.get("runtime", spec["script_type"]),
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                    "parameters_schema": spec.get("parameters_schema", {}),
                }
            )
    else:
        for scoped_tool_name, spec in sorted(scoped_proxy_specs.items()):
            tools.append(
                {
                    "tool_name": scoped_tool_name,
                    "employee_id": spec["employee_id"],
                    "base_tool_name": spec["base_tool_name"],
                    "scoped_tool_name": spec["scoped_tool_name"],
                    "skill_id": spec["skill_id"],
                    "skill_name": spec["skill_name"],
                    "entry_name": spec["entry_name"],
                    "runtime": spec.get("runtime", spec["script_type"]),
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                    "parameters_schema": spec.get("parameters_schema", {}),
                }
            )

    existing_names = {str(item.get("tool_name") or "") for item in tools}
    if "query_project_rules" not in existing_names:
        tools.append(
            {
                "tool_name": "query_project_rules",
                "employee_id": employee_id_value,
                "base_tool_name": "query_project_rules",
                "scoped_tool_name": "query_project_rules",
                "skill_id": "__builtin__",
                "entry_name": "query_project_rules",
                "script_type": "builtin",
                "description": "检索项目规则内容，可按 keyword 与 employee_id 过滤。",
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "用于检索规则的关键词，如“UI设计”或“数据库设计”。",
                        },
                        "employee_id": {
                            "type": "string",
                            "description": "可选，指定项目成员 employee_id 进行过滤。",
                        },
                    },
                    "required": [],
                },
            }
        )
    if "query_project_members" not in existing_names:
        tools.append(
            {
                "tool_name": "query_project_members",
                "employee_id": employee_id_value,
                "base_tool_name": "query_project_members",
                "scoped_tool_name": "query_project_members",
                "skill_id": "__builtin__",
                "entry_name": "query_project_members",
                "script_type": "builtin",
                "description": "查询项目的成员列表，返回成员的姓名、ID、角色等信息。",
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }
        )
    if "search_project_context" not in existing_names:
        tools.append(
            {
                "tool_name": "search_project_context",
                "employee_id": employee_id_value,
                "base_tool_name": "search_project_context",
                "scoped_tool_name": "search_project_context",
                "skill_id": "__builtin__",
                "entry_name": "search_project_context",
                "script_type": "builtin",
                "description": (
                    "统一检索项目上下文，支持按 scope/keyword/employee_id 查询"
                    "项目信息、成员详情、规则内容、MCP 模块。"
                ),
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "string",
                            "description": "检索范围：all/project/members/rules/mcp，默认 all。",
                        },
                        "keyword": {
                            "type": "string",
                            "description": "可选，关键词过滤。",
                        },
                        "employee_id": {
                            "type": "string",
                            "description": "可选，按员工 ID 过滤成员与规则。",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "每类结果最大返回条数，默认 20，范围 1-100。",
                        },
                    },
                    "required": [],
                },
            }
        )
    if "get_project_detail" not in existing_names:
        tools.append(
            {
                "tool_name": "get_project_detail",
                "employee_id": employee_id_value,
                "base_tool_name": "get_project_detail",
                "scoped_tool_name": "get_project_detail",
                "skill_id": "__builtin__",
                "entry_name": "get_project_detail",
                "script_type": "builtin",
                "description": "获取当前项目完整详情，包含基础配置、聊天配置、成员清单和用户成员清单。",
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }
        )
    if "get_project_employee_detail" not in existing_names:
        tools.append(
            {
                "tool_name": "get_project_employee_detail",
                "employee_id": employee_id_value,
                "base_tool_name": "get_project_employee_detail",
                "scoped_tool_name": "get_project_employee_detail",
                "skill_id": "__builtin__",
                "entry_name": "get_project_employee_detail",
                "script_type": "builtin",
                "description": "获取单个项目成员的完整员工详情，包含成员关系和员工完整配置。",
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "必填，项目成员 employee_id。",
                        },
                    },
                    "required": ["employee_id"],
                },
            }
        )
    if "get_current_task_tree" not in existing_names:
        tools.append(
            {
                "tool_name": "get_current_task_tree",
                "employee_id": employee_id_value,
                "base_tool_name": "get_current_task_tree",
                "scoped_tool_name": "get_current_task_tree",
                "skill_id": "__builtin__",
                "entry_name": "get_current_task_tree",
                "script_type": "builtin",
                "description": "读取当前聊天会话的任务树、当前节点和验证要求。",
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "chat_session_id": {
                            "type": "string",
                            "description": "可选，当前项目聊天会话 ID；在项目聊天里默认自动注入。",
                        },
                    },
                    "required": [],
                },
            }
        )
    if "update_task_node_status" not in existing_names:
        tools.append(
            {
                "tool_name": "update_task_node_status",
                "employee_id": employee_id_value,
                "base_tool_name": "update_task_node_status",
                "scoped_tool_name": "update_task_node_status",
                "skill_id": "__builtin__",
                "entry_name": "update_task_node_status",
                "script_type": "builtin",
                "description": "更新任务树节点状态，可写入当前状态、验证结果、模型摘要和当前焦点。",
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "chat_session_id": {
                            "type": "string",
                            "description": "可选，当前项目聊天会话 ID；在项目聊天里默认自动注入。",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "必填，任务节点 ID。",
                        },
                        "status": {
                            "type": "string",
                            "description": "必填，pending/in_progress/blocked/verifying/done 之一。",
                        },
                        "verification_result": {
                            "type": "string",
                            "description": "可选，节点验证结果。",
                        },
                        "summary_for_model": {
                            "type": "string",
                            "description": "可选，给后续模型轮次看的当前节点摘要。",
                        },
                        "is_current": {
                            "type": "boolean",
                            "description": "可选，是否把该节点设为当前执行焦点。",
                        },
                    },
                    "required": ["node_id", "status"],
                },
            }
        )
    if "complete_task_node_with_verification" not in existing_names:
        tools.append(
            {
                "tool_name": "complete_task_node_with_verification",
                "employee_id": employee_id_value,
                "base_tool_name": "complete_task_node_with_verification",
                "scoped_tool_name": "complete_task_node_with_verification",
                "skill_id": "__builtin__",
                "entry_name": "complete_task_node_with_verification",
                "script_type": "builtin",
                "description": "在写入验证结果后完成任务节点；父节点要求全部子节点已完成。",
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "chat_session_id": {
                            "type": "string",
                            "description": "可选，当前项目聊天会话 ID；在项目聊天里默认自动注入。",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "必填，任务节点 ID。",
                        },
                        "verification_result": {
                            "type": "string",
                            "description": "必填，完成该节点的验证结果。",
                        },
                        "summary_for_model": {
                            "type": "string",
                            "description": "可选，给后续模型轮次看的当前节点摘要。",
                        },
                        "is_current": {
                            "type": "boolean",
                            "description": "可选，是否把该节点设为当前执行焦点。",
                        },
                    },
                    "required": ["node_id", "verification_result"],
                },
            }
        )
    if COLLABORATION_TOOL_NAME not in existing_names:
        tools.append(collaboration_tool_descriptor(employee_id_value))
    return tools


def invoke_project_skill_tool_runtime(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
    username: str = "",
    chat_session_id: str = "",
    args: dict | None = None,
    args_json: str = "{}",
    timeout_sec: int = 30,
) -> dict:
    """执行项目成员技能脚本，供非 MCP 路径（如聊天路由）复用。"""
    normalized_tool_name = str(tool_name or "").strip()
    employee_id_value = str(employee_id or "").strip()
    resolved_username, resolved_chat_session_id = _resolve_runtime_task_tree_context(
        username=username,
        chat_session_id=chat_session_id,
    )
    try:
        builtin_result = invoke_project_builtin_tool(
            project_id,
            normalized_tool_name,
            employee_id_value,
            username=resolved_username,
            chat_session_id=resolved_chat_session_id,
            args=args,
            args_json=args_json,
        )
    except TypeError as exc:
        # Preserve compatibility with narrow test doubles that still expose the
        # legacy helper signature without username/chat_session_id keywords.
        if "unexpected keyword argument" not in str(exc):
            raise
        builtin_result = invoke_project_builtin_tool(
            project_id,
            normalized_tool_name,
            employee_id_value,
            args=args,
            args_json=args_json,
        )
    if builtin_result is not None:
        return builtin_result

    if normalized_tool_name == COLLABORATION_TOOL_NAME:
        payload, err = parse_object_args(args=args, args_json=args_json)
        if payload is None:
            return {"error": err}
        return execute_project_collaboration_runtime(
            project_id=project_id,
            task=str(payload.get("task") or "").strip(),
            username=resolved_username,
            chat_session_id=resolved_chat_session_id,
            employee_ids=payload.get("employee_ids") or [],
            max_employees=payload.get("max_employees", 3),
            max_tool_calls=payload.get("max_tool_calls", 6),
            auto_execute=bool(payload.get("auto_execute", True)),
            include_external_tools=bool(payload.get("include_external_tools", True)),
            timeout_sec=timeout_sec,
            invoke_tool=invoke_project_tool_runtime,
        )

    spec, err = _resolve_project_proxy_tool_spec(project_id, tool_name, employee_id)
    if spec is None:
        return {"error": err}
    task_tree_payload = ensure_project_execution_task_tree(
        project_id=project_id,
        username=resolved_username,
        chat_session_id=resolved_chat_session_id,
        root_goal=extract_execution_task_text(
            normalized_tool_name,
            args=args,
            args_json=args_json,
        ),
    )
    result = _execute_skill_proxy(
        spec,
        project_root=_PROJECT_ROOT,
        current_api_key=_current_api_key.get(""),
        args=args,
        args_json=args_json,
        timeout_sec=timeout_sec,
        employee_id=spec["employee_id"],
    )
    if isinstance(result, dict):
        return attach_task_tree_context(
            {
            "tool_name": str(spec.get("base_tool_name") or tool_name),
            "employee_id": str(spec.get("employee_id") or employee_id),
            **result,
            },
            task_tree_payload=task_tree_payload,
            username=resolved_username,
            chat_session_id=resolved_chat_session_id,
        )
    return attach_task_tree_context(
        {"result": result},
        task_tree_payload=task_tree_payload,
        username=resolved_username,
        chat_session_id=resolved_chat_session_id,
    )




def _create_employee_mcp(employee_id: str):
    return _create_employee_mcp_impl(
        employee_id,
        current_api_key_ctx=_current_api_key,
        current_developer_name_ctx=_current_developer_name,
        system_policy_text=_SYSTEM_POLICY,
        load_project_config_fn=_load_project_config,
        project_root=_PROJECT_ROOT,
        recall_limit=_RECALL_EMPLOYEE_MEMORY_LIMIT,
    )



def _create_project_mcp(project_id: str):
    return _create_project_mcp_impl(
        project_id,
        current_api_key_ctx=_current_api_key,
        current_developer_name_ctx=_current_developer_name,
        current_key_owner_username_ctx=_current_key_owner_username,
        current_mcp_session_id_ctx=_current_mcp_session_id,
        project_root=_PROJECT_ROOT,
        recall_limit=_RECALL_EMPLOYEE_MEMORY_LIMIT,
    )


def _create_query_mcp():
    mcp = _create_query_mcp_impl(
        current_key_owner_username_ctx=_current_key_owner_username,
        current_mcp_session_id_ctx=_current_mcp_session_id,
        session_contexts=_session_contexts,
    )
    return _DualTransportMcpApp(
        _apply_mcp_arguments_compat(mcp.sse_app()),
        mcp.streamable_http_app(),
    )


class _RuleMcpProxyApp:
    async def __call__(self, scope, receive, send):
        rule_id = scope.get("path_params", {}).get("rule_id")
        if not rule_id:
            response = JSONResponse({"detail": "Missing rule_id"}, status_code=400)
            await response(scope, receive, send)
            return

        rule = rule_store.get(rule_id)
        if not rule or not getattr(rule, "mcp_enabled", False):
            response = JSONResponse(
                {"detail": "Rule MCP service is disabled or rule not found."},
                status_code=404,
            )
            await response(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        qs = parse_qs(scope.get("query_string", b"").decode())
        api_key = ((qs.get("key") or [""])[0]).strip()
        session_id = ((qs.get("session_id") or [""])[0]).strip()
        project_id, project_name = _resolve_project_context(qs, session_id, _session_contexts)
        developer_name = ""
        key_owner_username = _resolve_key_owner_username(usage_store, api_key)
        if api_key:
            developer_name = str(usage_store.validate_key(api_key) or "").strip()
        if not developer_name and session_id and session_id in _session_keys:
            _, developer_name = _session_keys[session_id]
        method = str(scope.get("method", "")).upper()
        normalized_path = path.rstrip("/") or "/"
        is_sse = normalized_path.endswith("/sse")
        is_streamable = normalized_path.endswith("/mcp")
        is_messages = normalized_path.endswith("/messages") or "/messages/" in normalized_path
        client_ip = get_client_ip(scope)
        try:
            await _touch_project_mcp_presence(
                endpoint_type="rule",
                entity_id=str(rule_id),
                entity_name=str(getattr(rule, "title", "") or rule_id),
                project_id=project_id,
                project_name=project_name,
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

        tracking_send = create_tracking_send(
            send,
            is_sse=is_sse,
            method=method,
            api_key=api_key,
            developer_name=developer_name,
            session_keys=_session_keys,
        )

        async def _handle_context(
            method_name: str,
            tool_name: str,
            context: dict[str, str],
        ) -> None:
            _ = method_name, tool_name, context
            resolved_project_id, resolved_project_name = _resolve_project_context(qs, session_id, _session_contexts)
            if not resolved_project_id and not resolved_project_name:
                return
            try:
                await _touch_project_mcp_presence(
                    endpoint_type="rule",
                    entity_id=str(rule_id),
                    entity_name=str(getattr(rule, "title", "") or rule_id),
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

        tracking_receive = create_tracking_receive(
            receive,
            usage_scope_id=f"rule:{rule_id}",
            api_key=api_key,
            developer_name=developer_name,
            client_ip=client_ip,
            session_id=session_id,
            session_contexts=_session_contexts,
            on_context=_handle_context,
        )

        if rule_id not in _rule_apps:
            _rule_apps[rule_id] = _create_rule_mcp(rule_id)
        await _rule_apps[rule_id](scope, tracking_receive, tracking_send)


class _SkillMcpProxyApp:
    async def __call__(self, scope, receive, send):
        skill_id = scope.get("path_params", {}).get("skill_id")
        if not skill_id:
            response = JSONResponse({"detail": "Missing skill_id"}, status_code=400)
            await response(scope, receive, send)
            return

        skill = skill_store.get(skill_id)
        if not skill or not getattr(skill, "mcp_enabled", False):
            response = JSONResponse(
                {"detail": "Skill MCP service is disabled or skill not found."},
                status_code=404,
            )
            await response(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        qs = parse_qs(scope.get("query_string", b"").decode())
        api_key = ((qs.get("key") or [""])[0]).strip()
        session_id = ((qs.get("session_id") or [""])[0]).strip()
        project_id, project_name = _resolve_project_context(qs, session_id, _session_contexts)
        developer_name = ""
        key_owner_username = _resolve_key_owner_username(usage_store, api_key)
        if api_key:
            developer_name = str(usage_store.validate_key(api_key) or "").strip()
        if not developer_name and session_id and session_id in _session_keys:
            _, developer_name = _session_keys[session_id]
        method = str(scope.get("method", "")).upper()
        normalized_path = path.rstrip("/") or "/"
        is_sse = normalized_path.endswith("/sse")
        is_streamable = normalized_path.endswith("/mcp")
        is_messages = normalized_path.endswith("/messages") or "/messages/" in normalized_path
        client_ip = get_client_ip(scope)
        try:
            await _touch_project_mcp_presence(
                endpoint_type="skill",
                entity_id=str(skill_id),
                entity_name=str(getattr(skill, "name", "") or skill_id),
                project_id=project_id,
                project_name=project_name,
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

        tracking_send = create_tracking_send(
            send,
            is_sse=is_sse,
            method=method,
            api_key=api_key,
            developer_name=developer_name,
            session_keys=_session_keys,
        )

        async def _handle_context(
            method_name: str,
            tool_name: str,
            context: dict[str, str],
        ) -> None:
            _ = method_name, tool_name, context
            resolved_project_id, resolved_project_name = _resolve_project_context(qs, session_id, _session_contexts)
            if not resolved_project_id and not resolved_project_name:
                return
            try:
                await _touch_project_mcp_presence(
                    endpoint_type="skill",
                    entity_id=str(skill_id),
                    entity_name=str(getattr(skill, "name", "") or skill_id),
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

        tracking_receive = create_tracking_receive(
            receive,
            usage_scope_id=f"skill:{skill_id}",
            api_key=api_key,
            developer_name=developer_name,
            client_ip=client_ip,
            session_id=session_id,
            session_contexts=_session_contexts,
            on_context=_handle_context,
        )

        if skill_id not in _skill_apps:
            _skill_apps[skill_id] = _create_skill_mcp(skill_id)
        await _skill_apps[skill_id](scope, tracking_receive, tracking_send)


project_mcp_proxy_app = ProjectMcpProxyApp(
    project_store=project_store,
    employee_store=employee_store,
    usage_store=usage_store,
    current_api_key_ctx=_current_api_key,
    current_developer_name_ctx=_current_developer_name,
    current_key_owner_username_ctx=_current_key_owner_username,
    current_mcp_session_id_ctx=_current_mcp_session_id,
    session_keys=_session_keys,
    session_contexts=_session_contexts,
    project_apps=_project_apps,
    project_app_signatures=_project_app_signatures,
    create_project_mcp=_create_project_mcp,
    list_visible_external_mcp_modules=_list_visible_external_mcp_modules,
    replace_path_suffix=_replace_path_suffix,
    dual_transport_app_type=_DualTransportMcpApp,
    project_mcp_app_rev=_PROJECT_MCP_APP_REV,
)

employee_mcp_proxy_app = EmployeeMcpProxyApp(
    employee_store=employee_store,
    usage_store=usage_store,
    current_api_key_ctx=_current_api_key,
    current_developer_name_ctx=_current_developer_name,
    session_keys=_session_keys,
    session_contexts=_session_contexts,
    employee_apps=_employee_apps,
    employee_app_signatures=_employee_app_signatures,
    create_employee_mcp=_create_employee_mcp,
    save_auto_user_question_memory=_save_auto_user_question_memory,
    replace_path_suffix=_replace_path_suffix,
    dual_transport_app_type=_DualTransportMcpApp,
    employee_mcp_app_rev=_EMPLOYEE_MCP_APP_REV,
)

query_mcp_proxy_app = QueryMcpProxyApp(
    usage_store=usage_store,
    current_api_key_ctx=_current_api_key,
    current_developer_name_ctx=_current_developer_name,
    current_key_owner_username_ctx=_current_key_owner_username,
    current_mcp_session_id_ctx=_current_mcp_session_id,
    session_keys=_session_keys,
    session_contexts=_session_contexts,
    query_app=_create_query_mcp(),
    save_auto_query_memory=_save_auto_query_memory,
    replace_path_suffix=_replace_path_suffix,
)

rule_mcp_proxy_app = _RuleMcpProxyApp()
skill_mcp_proxy_app = _SkillMcpProxyApp()
