from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.deps import (
    employee_store,
    project_store,
    resolve_role_ids_permissions,
    system_config_store,
    user_store,
)
from core.ownership import can_view_record
from core.role_permissions import MENU_PERMISSION_ITEMS, has_permission
from stores.json.system_config_store import default_global_assistant_guide_modules
from stores.mcp_bridge import Rule, Skill, binding_store, rule_store, skill_store

GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME = "global_assistant_system_guide"
GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME = "global_assistant_browser_requests"
GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME = "global_assistant_browser_actions"

def build_global_assistant_builtin_tools() -> list[dict[str, Any]]:
    return [
        {
            "tool_name": GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME,
            "description": (
                "读取当前系统的产品定位、核心模块、主要入口、配置位置和当前登录用户可见菜单。"
                "适用于回答“这个系统做什么、有哪些功能、怎么用、去哪里配置”这类问题。"
            ),
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "可选。用户当前最关心的主题，例如 项目管理、模型供应商、系统配置、素材库。",
                    },
                    "include_paths": {
                        "type": "boolean",
                        "description": "是否在结果里附带页面路径，默认 true。",
                    },
                },
            },
        },
        {
            "tool_name": GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME,
            "description": (
                "读取当前浏览器页面最近发出的接口请求，返回请求地址、状态码、耗时、成功失败状态、"
                "请求摘要和响应摘要。适用于排查接口报错、确认页面当前拿到的真实数据、检查接口是否超时。"
            ),
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "返回最近多少条请求，默认 10，最大 80。",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "可选。按 URL、状态或摘要内容过滤请求。",
                    },
                    "only_errors": {
                        "type": "boolean",
                        "description": "可选。只返回失败请求。",
                    },
                    "include_pending": {
                        "type": "boolean",
                        "description": "可选。是否包含仍在进行中的请求，默认 true。",
                    },
                },
            },
        },
        {
            "tool_name": GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME,
            "description": (
                "在当前浏览器页面执行操作，可查询 DOM、读取文本、点击、聚焦、填值、选择、滚动、按键、页面跳转，"
                "以及在页面上下文里执行受当前登录态约束的脚本。适用于代替用户检查页面、触发表单或模拟真实交互。"
            ),
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": (
                            "操作类型。支持 query_dom、get_text、click、focus、fill、select、scroll、press、navigate、run_script。"
                        ),
                    },
                    "selector": {
                        "type": "string",
                        "description": "需要操作的 CSS 选择器。query_dom 可返回多个匹配结果。",
                    },
                    "value": {
                        "type": "string",
                        "description": "fill 或 select 时写入的值。",
                    },
                    "key": {
                        "type": "string",
                        "description": "press 时发送的键值，例如 Enter、Escape、ArrowDown。",
                    },
                    "target": {
                        "type": "string",
                        "description": "navigate 时跳转目标。支持 /system/config、#/system/config、完整 URL，以及 back/forward/reload。",
                    },
                    "replace": {
                        "type": "boolean",
                        "description": "navigate 时是否替换当前历史记录。",
                    },
                    "wait_ms": {
                        "type": "integer",
                        "description": "navigate 后等待页面状态稳定的毫秒数，默认约 180。",
                    },
                    "top": {
                        "type": "number",
                        "description": "scroll 时窗口滚动到的 top 值。",
                    },
                    "left": {
                        "type": "number",
                        "description": "scroll 时窗口滚动到的 left 值。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "query_dom 时最多返回多少个匹配元素。",
                    },
                    "script": {
                        "type": "string",
                        "description": "run_script 时执行的脚本函数体。",
                    },
                    "args": {
                        "type": "array",
                        "description": "run_script 时的附加参数数组。",
                        "items": {
                            "type": "string",
                            "description": "传给页面脚本的单个字符串参数。",
                        },
                    },
                },
                "required": ["action"],
            },
        }
    ]


def is_global_assistant_builtin_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() in {
        GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME,
        GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME,
        GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME,
    }


async def execute_global_assistant_builtin_tool(
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    username: str = "",
    role_ids: list[str] | None = None,
    browser_bridge_handler: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    normalized_tool_name = str(tool_name or "").strip()
    if normalized_tool_name == GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME:
        return build_global_assistant_system_guide(
            username=username,
            role_ids=role_ids,
            focus=str((args or {}).get("focus") or "").strip(),
            include_paths=bool((args or {}).get("include_paths", True)),
        )
    if normalized_tool_name in {
        GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME,
        GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME,
    }:
        if browser_bridge_handler is None:
            return {"error": "Browser bridge is unavailable in current assistant session"}
        return await browser_bridge_handler(normalized_tool_name, dict(args or {}))
    if normalized_tool_name != GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME:
        return {"error": f"Unsupported global assistant builtin tool: {normalized_tool_name}"}
    return {"error": f"Unsupported global assistant builtin tool: {normalized_tool_name}"}


def build_global_assistant_system_guide(
    *,
    username: str = "",
    role_ids: list[str] | None = None,
    focus: str = "",
    include_paths: bool = True,
) -> dict[str, Any]:
    visibility = build_global_assistant_visibility_context(
        username=username,
        role_ids=role_ids,
    )
    normalized_username = str(visibility["username"] or "").strip()
    effective_role_ids = list(visibility["role_ids"] or [])
    primary_role_id = str(visibility["primary_role_id"] or "").strip()
    permissions = list(visibility["permissions"] or [])
    configured_modules = _load_system_guide_modules()
    visible_modules = [
        _serialize_module(item, permissions=permissions, primary_role_id=primary_role_id, include_paths=include_paths)
        for item in configured_modules
        if _module_visible(item, permissions=permissions, primary_role_id=primary_role_id)
    ]
    visible_menu_items = [
        {
            "name": str(item.get("label") or item.get("key") or "").strip(),
            "permission": str(item.get("key") or "").strip(),
            "path": str(item.get("path") or "").strip(),
        }
        for item in MENU_PERMISSION_ITEMS
        if has_permission(permissions, str(item.get("key") or "").strip(), role_id=primary_role_id)
    ]
    guide_lines = [
        "这是一个把 AI 对话、项目协作、员工技能编排、规则治理、素材生产和短片制作放在一起的后台系统。",
        "核心目标是让团队围绕数字分身、AI 图片视频生成和系统协作，在同一套工作台里完成配置、生产和管理。",
        "如果用户想知道这个系统怎么用，优先从 AI 对话中心、项目管理、员工管理、规则管理、系统配置、模型供应商、素材工作区 这几条主路径解释。",
    ]
    if visible_modules:
        guide_lines.append("当前登录用户优先可用的入口：")
        for item in visible_modules:
            title = str(item.get("name") or "").strip()
            summary = str(item.get("summary") or "").strip()
            paths = list(item.get("paths") or [])
            if include_paths and paths:
                guide_lines.append(f"- {title}：{summary} 路径：{', '.join(paths)}")
            else:
                guide_lines.append(f"- {title}：{summary}")
    if focus:
        guide_lines.append(f"当前用户关注点：{focus}")
        guide_lines.append("回答时应优先展开与该主题最相关的模块、配置入口和典型操作路径。")

    usage_guide = _build_visible_usage_guide(visible_modules)
    return {
        "tool": GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME,
        "focus": str(focus or "").strip(),
        "product_summary": "AI 对话 + 项目协作 + 员工/技能/规则编排 + 素材与短片生产的一体化后台系统",
        "current_user": {
            "username": normalized_username,
            "role_ids": effective_role_ids,
            "visible_menu_count": len(visible_menu_items),
        },
        "system_counts": dict(visibility["system_counts"] or {}),
        "data_scope": "visible_only",
        "visible_menu_items": visible_menu_items,
        "visible_modules": visible_modules,
        "all_modules": visible_modules,
        "usage_guide": usage_guide,
        "guide_text": "\n".join(guide_lines),
    }


def build_global_assistant_visibility_context(
    *,
    username: str = "",
    role_ids: list[str] | None = None,
) -> dict[str, Any]:
    normalized_username = str(username or "").strip()
    effective_role_ids = _resolve_role_ids(normalized_username, role_ids)
    primary_role_id = effective_role_ids[0] if effective_role_ids else ""
    permissions = resolve_role_ids_permissions(effective_role_ids)
    auth_payload = {
        "sub": normalized_username,
        "role": primary_role_id,
        "roles": effective_role_ids,
    }
    visible_projects = _list_visible_projects(
        username=normalized_username,
        permissions=permissions,
        primary_role_id=primary_role_id,
    )
    visible_employees = _list_visible_employees(
        auth_payload=auth_payload,
        permissions=permissions,
        primary_role_id=primary_role_id,
    )
    visible_employee_ids = {
        str(getattr(item, "id", "") or "").strip()
        for item in visible_employees
        if str(getattr(item, "id", "") or "").strip()
    }
    system_counts: dict[str, int] = {}
    if has_permission(permissions, "menu.projects", role_id=primary_role_id):
        system_counts["project_count"] = len(visible_projects)
    if has_permission(permissions, "menu.employees", role_id=primary_role_id):
        system_counts["employee_count"] = len(visible_employees)
    if has_permission(permissions, "menu.skills", role_id=primary_role_id):
        system_counts["skill_count"] = _count_visible_skills(
            auth_payload=auth_payload,
            visible_employee_ids=visible_employee_ids,
        )
    if has_permission(permissions, "menu.rules", role_id=primary_role_id):
        system_counts["rule_count"] = _count_visible_rules(
            auth_payload=auth_payload,
            visible_employee_ids=visible_employee_ids,
        )
    if has_permission(permissions, "menu.users", role_id=primary_role_id):
        system_counts["user_count"] = len(user_store.list_all())
    return {
        "username": normalized_username,
        "role_ids": effective_role_ids,
        "primary_role_id": primary_role_id,
        "permissions": permissions,
        "visible_project_ids": [
            str(getattr(item, "id", "") or "").strip()
            for item in visible_projects
            if str(getattr(item, "id", "") or "").strip()
        ],
        "visible_project_count": len(visible_projects),
        "visible_employee_ids": sorted(visible_employee_ids),
        "visible_employee_count": len(visible_employees),
        "system_counts": system_counts,
    }


def _resolve_role_ids(username: str, explicit_role_ids: list[str] | None) -> list[str]:
    normalized = [
        str(item or "").strip().lower()
        for item in (explicit_role_ids or [])
        if str(item or "").strip()
    ]
    if normalized:
        return _dedupe_role_ids(normalized)
    if username:
        user = user_store.get(username)
        if user is not None:
            return _dedupe_role_ids(list(getattr(user, "role_ids", []) or []))
    return ["user"]


def _dedupe_role_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_item in values:
        role_id = str(raw_item or "").strip().lower()
        if not role_id or role_id in seen:
            continue
        seen.add(role_id)
        normalized.append(role_id)
    return normalized or ["user"]


def _module_visible(
    item: dict[str, Any],
    *,
    permissions: list[str],
    primary_role_id: str,
) -> bool:
    if not bool(item.get("enabled", True)):
        return False
    if bool(item.get("is_public", False)):
        return True
    permission_key = str(item.get("permission") or "").strip()
    if not permission_key:
        return True
    return has_permission(permissions, permission_key, role_id=primary_role_id)


def _serialize_module(
    item: dict[str, Any],
    *,
    permissions: list[str],
    primary_role_id: str,
    include_paths: bool,
) -> dict[str, Any]:
    permission_key = str(item.get("permission") or "").strip()
    payload = {
        "id": str(item.get("id") or "").strip(),
        "name": str(item.get("name") or "").strip(),
        "summary": str(item.get("summary") or "").strip(),
        "available": _module_visible(item, permissions=permissions, primary_role_id=primary_role_id),
        "is_public": bool(item.get("is_public", False)),
    }
    if include_paths:
        payload["paths"] = list(item.get("paths") or [])
    if permission_key:
        payload["permission"] = permission_key
    return payload


def _list_visible_projects(
    *,
    username: str,
    permissions: list[str],
    primary_role_id: str,
) -> list[Any]:
    if not has_permission(permissions, "menu.projects", role_id=primary_role_id):
        return []
    all_projects = project_store.list_all()
    if "*" in set(permissions):
        return all_projects
    if not username:
        return []
    visible_projects: list[Any] = []
    for item in all_projects:
        try:
            member = project_store.get_user_member(str(getattr(item, "id", "") or "").strip(), username)
        except Exception:
            member = None
        if member is not None and bool(getattr(member, "enabled", True)):
            visible_projects.append(item)
    return visible_projects


def _list_visible_employees(
    *,
    auth_payload: dict[str, Any],
    permissions: list[str],
    primary_role_id: str,
) -> list[Any]:
    if not has_permission(permissions, "menu.employees", role_id=primary_role_id):
        return []
    return [
        employee
        for employee in employee_store.list_all()
        if can_view_record(employee, auth_payload)
    ]


def _employee_has_skill(employee: Any, skill_id: str) -> bool:
    normalized_skill_id = str(skill_id or "").strip()
    if not normalized_skill_id:
        return False
    for item in getattr(employee, "skills", []) or []:
        if str(item or "").strip() == normalized_skill_id:
            return True
    employee_id = str(getattr(employee, "id", "") or "").strip()
    if not employee_id:
        return False
    for binding in binding_store.get_bindings(employee_id):
        if str(getattr(binding, "skill_id", "") or "").strip() == normalized_skill_id:
            return True
    return False


def _skill_shared_via_visible_employees(skill: Skill, visible_employee_ids: set[str]) -> bool:
    if not visible_employee_ids:
        return False
    for employee in employee_store.list_all():
        employee_id = str(getattr(employee, "id", "") or "").strip()
        if not employee_id or employee_id not in visible_employee_ids:
            continue
        if _employee_has_skill(employee, skill.id):
            return True
    return False


def _rule_shared_via_visible_employees(rule: Rule, visible_employee_ids: set[str]) -> bool:
    if not visible_employee_ids:
        return False
    target_rule_id = str(getattr(rule, "id", "") or "").strip()
    if not target_rule_id:
        return False
    for employee in employee_store.list_all():
        employee_id = str(getattr(employee, "id", "") or "").strip()
        if not employee_id or employee_id not in visible_employee_ids:
            continue
        for rule_id in getattr(employee, "rule_ids", []) or []:
            if str(rule_id or "").strip() == target_rule_id:
                return True
    return False


def _count_visible_skills(*, auth_payload: dict[str, Any], visible_employee_ids: set[str]) -> int:
    count = 0
    for skill in skill_store.list_all():
        if can_view_record(skill, auth_payload) or _skill_shared_via_visible_employees(skill, visible_employee_ids):
            count += 1
    return count


def _count_visible_rules(*, auth_payload: dict[str, Any], visible_employee_ids: set[str]) -> int:
    count = 0
    for rule in rule_store.list_all():
        if can_view_record(rule, auth_payload) or _rule_shared_via_visible_employees(rule, visible_employee_ids):
            count += 1
    return count


def _build_visible_usage_guide(visible_modules: list[dict[str, Any]]) -> list[str]:
    usage_by_id = {
        "ai-chat": "想直接提问、排查问题、查看系统状态：进入 /ai/chat 或使用全局 AI 助手。",
        "projects": "想配置项目、项目成员、项目对话：进入 /projects。",
        "system-config": "想配置系统级开关、语音、默认提示词：进入 /system/config。",
        "llm-providers": "想维护文本、语音、图像模型：进入 /llm/providers。",
        "employees": "想维护 AI 员工、职责与手册：进入 /employees。",
        "skills": "想维护技能与技能资源：进入 /skills 和 /skill-resources。",
        "rules": "想维护执行规则与约束：进入 /rules。",
        "materials": "想查看素材和声音资产：进入 /materials。",
        "studio": "想做短片生产与导出：进入 /materials/studio。",
        "users-roles": "想管理账号、角色和权限：进入 /users 和 /roles。",
        "intro": "想快速了解产品定位和整体工作流：进入 /intro。",
        "market": "想查看对外展示的能力介绍和市场化页面：进入 /market。",
        "updates": "想查看版本更新和迭代记录：进入 /updates。",
    }
    lines: list[str] = []
    seen: set[str] = set()
    for item in visible_modules:
        module_id = str(item.get("id") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        text = usage_by_id.get(module_id)
        if not text:
            paths = [str(path or "").strip() for path in (item.get("paths") or []) if str(path or "").strip()]
            summary = str(item.get("summary") or "").strip()
            if paths and summary:
                text = f"想了解或使用 {name}：进入 {', '.join(paths)}。{summary}"
            elif paths:
                text = f"想了解或使用 {name}：进入 {', '.join(paths)}。"
            elif summary:
                text = f"想了解或使用 {name}：{summary}"
        if not text or text in seen:
            continue
        seen.add(text)
        lines.append(text)
    if lines:
        return lines
    return ["当前账号仅开放了有限入口；如需更多模块，请联系管理员调整角色权限。"]


def _load_system_guide_modules() -> list[dict[str, Any]]:
    config = system_config_store.get_global()
    modules = getattr(config, "global_assistant_guide_modules", None)
    if isinstance(modules, list) and modules:
        return [dict(item) for item in modules if isinstance(item, dict)]
    return default_global_assistant_guide_modules()
