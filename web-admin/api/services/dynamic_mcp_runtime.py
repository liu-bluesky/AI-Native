"""动态 Micro-MCP 服务生成器"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import asdict
from datetime import timedelta
import json
import os
from pathlib import Path

from services.dynamic_mcp_skill_executor import execute_skill_proxy as _execute_skill_proxy

from fastapi.responses import JSONResponse, Response
from mcp.server.fastmcp import FastMCP

from services.dynamic_mcp_apps_basic import (
    create_rule_mcp as _create_rule_mcp,
    create_skill_mcp as _create_skill_mcp,
)
from services.dynamic_mcp_apps_employee import create_employee_mcp as _create_employee_mcp_impl
from services.dynamic_mcp_apps_project import create_project_mcp as _create_project_mcp_impl
from starlette.types import ASGIApp, Receive, Scope, Send

from services.dynamic_mcp_context import (
    query_project_mcp_modules_runtime,
    search_project_context_runtime,
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
    active_project_member_employees as _active_project_member_employees,
    build_project_proxy_specs as _build_project_proxy_specs,
    discover_skill_proxy_specs as _discover_skill_proxy_specs,
    list_project_proxy_tools_runtime,
    resolve_project_proxy_tool_spec as _resolve_project_proxy_tool_spec,
)
from services.dynamic_mcp_transports import (
    DualTransportMcpApp as _DualTransportMcpApp,
    apply_mcp_arguments_compat as _apply_mcp_arguments_compat,
    replace_path_suffix as _replace_path_suffix,
)

from core.deps import employee_store, external_mcp_store, project_store, usage_store
from services.feedback_service import get_feedback_service
from services.dynamic_mcp_audit import (
    save_auto_user_question_memory as _save_auto_user_question_memory,
)
from services.dynamic_mcp_proxy_apps import EmployeeMcpProxyApp, ProjectMcpProxyApp
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
_current_api_key: ContextVar[str] = ContextVar("_current_api_key", default="")
_current_developer_name: ContextVar[str] = ContextVar("_current_developer_name", default="")
_EMPLOYEE_MCP_APP_REV = "2026-03-04-sse-post-bridge"
_PROJECT_MCP_APP_REV = "2026-03-05-project-mcp-v1"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_EXECUTABLE_SUFFIXES = {".py", ".js"}
_FASTMCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")

# 启动时加载底层安全策略（不可运行时修改，需重启生效）
_SYSTEM_POLICY_PATH = Path(__file__).resolve().parents[1] / "system-policy.md"
_SYSTEM_POLICY = _SYSTEM_POLICY_PATH.read_text(encoding="utf-8") if _SYSTEM_POLICY_PATH.exists() else ""


def _tool_token(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in str(value or "").strip().lower())
    text = "_".join(part for part in text.split("_") if part)
    if not text:
        return "tool"
    if text[0].isdigit():
        return f"t_{text}"
    return text


_RECALL_EMPLOYEE_MEMORY_LIMIT = 100


def invoke_project_tool_runtime(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
    args: dict | None = None,
    args_json: str = "{}",
    timeout_sec: int = 30,
) -> dict:
    spec, _ = _resolve_external_tool_spec(project_id, tool_name)
    if spec is not None:
        return invoke_external_mcp_tool_runtime(
            project_id=project_id,
            tool_name=tool_name,
            args=args,
            args_json=args_json,
            timeout_sec=timeout_sec,
        )
    return invoke_project_skill_tool_runtime(
        project_id=project_id,
        tool_name=tool_name,
        employee_id=employee_id,
        args=args,
        args_json=args_json,
        timeout_sec=timeout_sec,
    )


def _build_project_proxy_specs(project_id: str) -> tuple[dict[str, dict], dict[str, dict[str, dict]]]:
    by_scoped_name: dict[str, dict] = {}
    by_employee_base_name: dict[str, dict[str, dict]] = {}
    for _member, employee in _active_project_member_employees(project_id):
        name_counter: dict[str, int] = {}
        employee_map = by_employee_base_name.setdefault(employee.id, {})
        for skill_id in employee.skills or []:
            skill = skill_store.get(skill_id)
            if not skill:
                continue
            for spec in _discover_skill_proxy_specs(skill):
                base_name = f"{_tool_token(skill.id)}__{_tool_token(spec['entry_name'])}"
                idx = name_counter.get(base_name, 0) + 1
                name_counter[base_name] = idx
                base_key = base_name if idx == 1 else f"{base_name}_{idx}"
                scoped_name = f"{_tool_token(employee.id)}__{base_key}"
                wrapped = {
                    **spec,
                    "employee_id": employee.id,
                    "base_tool_name": base_key,
                    "scoped_tool_name": scoped_name,
                }
                by_scoped_name[scoped_name] = wrapped
                employee_map[base_key] = wrapped
    return by_scoped_name, by_employee_base_name


def _resolve_project_proxy_tool_spec(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
) -> tuple[dict | None, str]:
    scoped_proxy_specs, employee_proxy_specs = _build_project_proxy_specs(project_id)
    normalized_tool_name = str(tool_name or "").strip()
    employee_id_value = str(employee_id or "").strip()
    if not normalized_tool_name:
        return None, "tool_name is required"

    if employee_id_value:
        employee_specs = employee_proxy_specs.get(employee_id_value, {})
        if normalized_tool_name in employee_specs:
            return employee_specs[normalized_tool_name], ""
        scoped_name = f"{_tool_token(employee_id_value)}__{normalized_tool_name}"
        scoped_spec = scoped_proxy_specs.get(scoped_name)
        if scoped_spec:
            return scoped_spec, ""
        return None, f"Tool not found for employee {employee_id_value}: {normalized_tool_name}"

    if normalized_tool_name in scoped_proxy_specs:
        return scoped_proxy_specs[normalized_tool_name], ""

    matched: list[dict] = []
    for specs in employee_proxy_specs.values():
        if normalized_tool_name in specs:
            matched.append(specs[normalized_tool_name])
    if not matched:
        return None, f"Tool not found: {normalized_tool_name}"
    if len(matched) > 1:
        employee_ids = sorted({item["employee_id"] for item in matched})
        return None, f"Ambiguous tool_name, provide employee_id. Candidates: {employee_ids}"
    return matched[0], ""


def list_project_proxy_tools_runtime(project_id: str, employee_id: str = "") -> list[dict]:
    """列出项目技能代理工具，供非 MCP 路径（如聊天路由）复用。"""
    scoped_proxy_specs, employee_proxy_specs = _build_project_proxy_specs(project_id)
    employee_id_value = str(employee_id or "").strip()
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
                    "entry_name": spec["entry_name"],
                    "script_type": spec["script_type"],
                    "description": spec["description"],
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
                    "entry_name": spec["entry_name"],
                    "script_type": spec["script_type"],
                    "description": spec["description"],
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
    return tools


def invoke_project_skill_tool_runtime(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
    args: dict | None = None,
    args_json: str = "{}",
    timeout_sec: int = 30,
) -> dict:
    """执行项目成员技能脚本，供非 MCP 路径（如聊天路由）复用。"""
    normalized_tool_name = str(tool_name or "").strip()
    employee_id_value = str(employee_id or "").strip()

    if normalized_tool_name == "query_project_rules":
        payload: dict = {}
        if args is not None:
            if not isinstance(args, dict):
                return {"error": "args must be an object"}
            payload = args
        else:
            try:
                payload = json.loads(args_json or "{}")
            except Exception as exc:
                return {"error": f"Invalid args_json: {exc}"}
            if not isinstance(payload, dict):
                return {"error": "args_json must be a JSON object"}
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
        payload: dict = {}
        if args is not None:
            if not isinstance(args, dict):
                return {"error": "args must be an object"}
            payload = args
        else:
            try:
                payload = json.loads(args_json or "{}")
            except Exception as exc:
                return {"error": f"Invalid args_json: {exc}"}
            if not isinstance(payload, dict):
                return {"error": "args_json must be a JSON object"}
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

    spec, err = _resolve_project_proxy_tool_spec(project_id, tool_name, employee_id)
    if spec is None:
        return {"error": err}
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
        return {
            "tool_name": str(spec.get("base_tool_name") or tool_name),
            "employee_id": str(spec.get("employee_id") or employee_id),
            **result,
        }
    return {"result": result}




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
        project_root=_PROJECT_ROOT,
        recall_limit=_RECALL_EMPLOYEE_MEMORY_LIMIT,
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

        if rule_id not in _rule_apps:
            _rule_apps[rule_id] = _create_rule_mcp(rule_id)
        await _rule_apps[rule_id](scope, receive, send)


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

        if skill_id not in _skill_apps:
            _skill_apps[skill_id] = _create_skill_mcp(skill_id)
        await _skill_apps[skill_id](scope, receive, send)


project_mcp_proxy_app = ProjectMcpProxyApp(
    project_store=project_store,
    employee_store=employee_store,
    usage_store=usage_store,
    current_api_key_ctx=_current_api_key,
    current_developer_name_ctx=_current_developer_name,
    session_keys=_session_keys,
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
    employee_apps=_employee_apps,
    employee_app_signatures=_employee_app_signatures,
    create_employee_mcp=_create_employee_mcp,
    save_auto_user_question_memory=_save_auto_user_question_memory,
    replace_path_suffix=_replace_path_suffix,
    dual_transport_app_type=_DualTransportMcpApp,
    employee_mcp_app_rev=_EMPLOYEE_MCP_APP_REV,
)

rule_mcp_proxy_app = _RuleMcpProxyApp()
skill_mcp_proxy_app = _SkillMcpProxyApp()
