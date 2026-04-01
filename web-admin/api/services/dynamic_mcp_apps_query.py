"""Unified query MCP app builder."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
import re

from mcp.server.fastmcp import FastMCP

from core.deps import employee_store, project_store, work_session_store
from services.dynamic_mcp_context import (
    get_project_detail_runtime,
    get_project_employee_detail_runtime,
)
from services.dynamic_mcp_profiles import (
    employee_rule_summary,
    list_project_member_profiles_runtime,
    project_ui_rule_summary,
    query_project_rules_runtime,
    query_rules_by_employee,
)
from stores.mcp_bridge import (
    Classification,
    Memory,
    MemoryScope,
    MemoryType,
    memory_store,
    rule_store,
    serialize_memory,
    serialize_rule,
    serialize_skill,
    skill_store,
)
from stores.json.work_session_store import WorkSessionEvent

_FASTMCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")

_TASK_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "mcp-upgrade": ("mcp", "query", "sse", "tool", "resource", "agent capability"),
    "frontend": ("前端", "页面", "ui", "vue", "组件", "样式", "交互", "菜单", "导航"),
    "backend": ("后端", "接口", "api", "服务", "路由", "数据库", "表", "字段", "存储"),
    "docs": ("文档", "docs", "设计", "规划", "方案", "骨架", "步骤", "README"),
    "bugfix": ("bug", "报错", "异常", "不对", "有问题", "修复", "检查一下", "排查"),
    "release": ("更新日志", "release", "changelog", "版本", "发布说明"),
}

_SCOPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "frontend": ("前端", "页面", "ui", "菜单", "导航", "组件", "样式"),
    "backend": ("后端", "api", "接口", "服务", "数据库", "表", "字段", "路由"),
    "docs": ("文档", "方案", "规划", "README", "设计", "骨架"),
    "mcp": ("mcp", "query", "sse", "resource", "tool"),
    "workflow": ("流程", "步骤", "规划", "执行", "协作", "编排"),
}

_CONSTRAINT_PREFIXES = ("不要", "不能", "必须", "优先", "通过", "只", "单独", "确保", "根据")
_DESTRUCTIVE_COMMAND_PATTERNS = (
    "rm -rf",
    "rm -fr",
    "git reset --hard",
    "git clean -fd",
    "git clean -xdf",
    "mkfs",
    "dd if=",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "chown -r",
    "chmod -r 777",
)
_HIGH_RISK_COMMAND_PATTERNS = (
    "git push",
    "git rebase",
    "git cherry-pick",
    "docker rm",
    "docker stop",
    "docker compose down",
    "npm publish",
    "pip uninstall",
    "brew uninstall",
    "kill -9",
    "mv ",
)
_WRITE_COMMAND_HINTS = (
    " > ",
    " >> ",
    "tee ",
    "sed -i",
    "truncate ",
    "cp ",
    "mv ",
    "touch ",
    "mkdir ",
    "rm ",
    "git add",
    "git commit",
    "npm install",
    "pnpm install",
    "yarn add",
)
_LOW_RISK_COMMAND_HINTS = (
    "pwd",
    "ls",
    "cat ",
    "sed -n",
    "rg ",
    "find ",
    "git status",
    "git diff",
)
_SYSTEM_PATH_PREFIXES = (
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/opt",
    "/var",
    "/Library",
    "/System",
    "/Applications",
    "/private",
    "/root",
    "~/.ssh",
)
_QUERY_TOOL_NAMES = {
    "search_ids",
    "get_content",
    "get_manual_content",
    "analyze_task",
    "resolve_relevant_context",
    "generate_execution_plan",
    "save_project_memory",
    "list_project_members",
    "get_project_runtime_context",
    "list_project_proxy_tools",
    "invoke_project_skill_tool",
    "execute_project_collaboration",
    "classify_command_risk",
    "check_workspace_scope",
    "resolve_execution_mode",
    "check_operation_policy",
    "save_work_facts",
    "append_session_event",
    "resume_work_session",
    "summarize_checkpoint",
}


def _new_mcp(service_name: str) -> FastMCP:
    return FastMCP(service_name, host=_FASTMCP_HOST, stateless_http=True)


def _build_employee_lookup(employee_id: str, *, include_skills: bool, include_rules: bool) -> dict:
    employee = employee_store.get(employee_id)
    if employee is None:
        return {"error": f"Employee {employee_id} not found"}

    payload = asdict(employee)
    payload["resource_uri"] = f"employee://{employee_id}/profile"
    payload["mcp_path"] = f"/mcp/employees/{employee_id}"
    payload["manual_endpoint"] = f"/api/employees/{employee_id}/manual-template"
    payload["rule_bindings"] = employee_rule_summary(employee, limit=200)

    if include_skills:
        skills = []
        for skill_id in employee.skills or []:
            skill = skill_store.get(skill_id)
            if skill is None:
                skills.append({"id": skill_id, "error": "Skill not found"})
                continue
            skills.append(serialize_skill(skill))
        payload["skills_detail"] = skills

    if include_rules:
        payload["rules_detail"] = [
            serialize_rule(rule) for rule in query_rules_by_employee(employee)
        ]

    return payload


def _build_rule_lookup(rule_id: str) -> dict:
    rule = rule_store.get(rule_id)
    if rule is None:
        return {"error": f"Rule {rule_id} not found"}

    payload = serialize_rule(rule)
    payload["resource_uri"] = f"rule://{rule_id}"
    payload["mcp_path"] = f"/mcp/rules/{rule_id}"
    return payload


def _build_project_lookup(
    project_id: str,
    *,
    include_members: bool,
    include_rules: bool,
) -> dict:
    payload = get_project_detail_runtime(project_id)
    if payload.get("error"):
        return payload

    payload["resource_uri"] = f"project://{project_id}/profile"
    payload["mcp_path"] = f"/mcp/projects/{project_id}"
    payload["manual_endpoint"] = f"/api/projects/{project_id}/manual-template"

    if include_members:
        payload["members_detail"] = list_project_member_profiles_runtime(
            project_id,
            include_disabled=True,
            include_missing=True,
            rule_limit=50,
        )

    if include_rules:
        payload["rules_detail"] = query_project_rules_runtime(project_id)

    return payload


def _keyword_match(keyword: str, *values: object) -> bool:
    keyword_value = str(keyword or "").strip().lower()
    if not keyword_value:
        return True
    for value in values:
        text = str(value or "").strip().lower()
        if text and keyword_value in text:
            return True
    return False


def _search_projects(keyword: str, limit: int) -> list[dict]:
    matches: list[dict] = []
    for project in project_store.list_all():
        if not _keyword_match(
            keyword,
            getattr(project, "id", ""),
            getattr(project, "name", ""),
            getattr(project, "description", ""),
        ):
            continue
        matches.append(
            {
                "id": str(getattr(project, "id", "") or ""),
                "name": str(getattr(project, "name", "") or ""),
                "description": str(getattr(project, "description", "") or ""),
                "mcp_path": f"/mcp/projects/{project.id}",
                "manual_endpoint": f"/api/projects/{project.id}/manual-template",
            }
        )
        if len(matches) >= limit:
            break
    return matches


def _search_employees(keyword: str, project_id: str, limit: int) -> list[dict]:
    matches: list[dict] = []
    seen_ids: set[str] = set()
    if project_id:
        candidates = list_project_member_profiles_runtime(
            project_id,
            include_disabled=True,
            include_missing=True,
            rule_limit=20,
        )
        for item in candidates:
            employee_id = str(item.get("employee_id") or "").strip()
            if not employee_id or employee_id in seen_ids:
                continue
            if not _keyword_match(
                keyword,
                employee_id,
                item.get("name"),
                item.get("description"),
                item.get("goal"),
            ):
                continue
            seen_ids.add(employee_id)
            matches.append(
                {
                    "id": employee_id,
                    "name": str(item.get("name") or ""),
                    "description": str(item.get("description") or ""),
                    "project_id": project_id,
                    "mcp_path": f"/mcp/employees/{employee_id}",
                    "manual_endpoint": f"/api/employees/{employee_id}/manual-template",
                }
            )
            if len(matches) >= limit:
                break
        return matches

    for employee in employee_store.list_all():
        employee_id = str(getattr(employee, "id", "") or "").strip()
        if not employee_id or employee_id in seen_ids:
            continue
        if not _keyword_match(
            keyword,
            employee_id,
            getattr(employee, "name", ""),
            getattr(employee, "description", ""),
            getattr(employee, "goal", ""),
        ):
            continue
        seen_ids.add(employee_id)
        matches.append(
            {
                "id": employee_id,
                "name": str(getattr(employee, "name", "") or ""),
                "description": str(getattr(employee, "description", "") or ""),
                "mcp_path": f"/mcp/employees/{employee_id}",
                "manual_endpoint": f"/api/employees/{employee_id}/manual-template",
            }
        )
        if len(matches) >= limit:
            break
    return matches


def _search_rules(keyword: str, project_id: str, employee_id: str, limit: int) -> list[dict]:
    matches: list[dict] = []
    seen_ids: set[str] = set()
    if project_id:
        candidates = query_project_rules_runtime(project_id, keyword=keyword, employee_id=employee_id)
        for rule in candidates:
            rule_id = str(rule.get("id") or "").strip()
            if not rule_id or rule_id in seen_ids:
                continue
            seen_ids.add(rule_id)
            matches.append(
                {
                    "id": rule_id,
                    "title": str(rule.get("title") or ""),
                    "domain": str(rule.get("domain") or ""),
                    "mcp_path": f"/mcp/rules/{rule_id}",
                }
            )
            if len(matches) >= limit:
                break
        return matches

    for rule in rule_store.list_all():
        rule_id = str(getattr(rule, "id", "") or "").strip()
        if not rule_id or rule_id in seen_ids:
            continue
        if not _keyword_match(
            keyword,
            rule_id,
            getattr(rule, "title", ""),
            getattr(rule, "domain", ""),
            getattr(rule, "content", ""),
        ):
            continue
        seen_ids.add(rule_id)
        matches.append(
            {
                "id": rule_id,
                "title": str(getattr(rule, "title", "") or ""),
                "domain": str(getattr(rule, "domain", "") or ""),
                "mcp_path": f"/mcp/rules/{rule_id}",
            }
        )
        if len(matches) >= limit:
            break
    return matches


def _active_project_employee_ids(project_id: str) -> list[str]:
    employee_ids: list[str] = []
    seen_ids: set[str] = set()
    for member in project_store.list_members(project_id):
        if not bool(getattr(member, "enabled", True)):
            continue
        employee_id = str(getattr(member, "employee_id", "") or "").strip()
        if not employee_id or employee_id in seen_ids:
            continue
        if employee_store.get(employee_id) is None:
            continue
        seen_ids.add(employee_id)
        employee_ids.append(employee_id)
    return employee_ids


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_text_lower(value: object) -> str:
    return _normalize_text(value).lower()


def _tokenize_keywords(text: object) -> list[str]:
    raw = _normalize_text_lower(text)
    if not raw:
        return []
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9/_-]{1,}", raw):
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _score_text_match(query: str, *values: object) -> int:
    tokens = _tokenize_keywords(query)
    if not tokens:
        return 0
    haystack = " ".join(_normalize_text_lower(value) for value in values if _normalize_text(value))
    if not haystack:
        return 0
    score = 0
    for token in tokens:
        if token in haystack:
            score += max(1, len(token))
    return score


def _detect_task_types(raw_request: str) -> list[str]:
    text = _normalize_text_lower(raw_request)
    detected: list[tuple[int, str]] = []
    for task_type, keywords in _TASK_TYPE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score > 0:
            detected.append((score, task_type))
    detected.sort(key=lambda item: (-item[0], item[1]))
    return [item[1] for item in detected] or ["general"]


def _detect_scope(raw_request: str) -> list[str]:
    text = _normalize_text_lower(raw_request)
    scopes: list[str] = []
    for scope, keywords in _SCOPE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            scopes.append(scope)
    return scopes or ["general"]


def _extract_constraints(raw_request: str, *, limit: int = 6) -> list[str]:
    text = _normalize_text(raw_request)
    if not text:
        return []
    chunks = re.split(r"[。\n；;!?！？]+", text)
    constraints: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        normalized = chunk.strip(" -\t")
        if not normalized:
            continue
        if not any(prefix in normalized for prefix in _CONSTRAINT_PREFIXES):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        constraints.append(normalized)
        if len(constraints) >= limit:
            break
    return constraints


def _extract_paths_and_routes(raw_request: str, *, limit: int = 8) -> list[str]:
    text = _normalize_text(raw_request)
    if not text:
        return []
    seen: set[str] = set()
    matches: list[str] = []
    for match in re.findall(r"(?:/[A-Za-z0-9._\-]+)+", text):
        if match in seen:
            continue
        seen.add(match)
        matches.append(match)
        if len(matches) >= limit:
            break
    return matches


def _infer_deliverables(task_types: list[str], scopes: list[str]) -> list[str]:
    deliverables: list[str] = []
    if "docs" in task_types or "docs" in scopes:
        deliverables.append("骨架文档或实施步骤文档")
    if "frontend" in task_types or "frontend" in scopes:
        deliverables.append("前端页面或交互改动")
    if "backend" in task_types or "backend" in scopes:
        deliverables.append("后端接口、字段或服务实现")
    if "mcp-upgrade" in task_types or "mcp" in scopes:
        deliverables.append("统一查询 MCP 新工具或资源能力")
    if "bugfix" in task_types:
        deliverables.append("问题复现、修复与验证结果")
    if "release" in task_types:
        deliverables.append("更新日志配置或发布说明")
    return deliverables or ["结构化分析与执行建议"]


def _suggest_next_tools(project_id: str, task_types: list[str]) -> list[str]:
    suggestions = ["search_ids", "get_manual_content"]
    if project_id:
        suggestions = ["get_manual_content", "get_project_runtime_context", "resolve_relevant_context"]
    if any(task_type in {"mcp-upgrade", "docs", "backend", "frontend", "bugfix"} for task_type in task_types):
        suggestions.append("generate_execution_plan")
    if project_id:
        suggestions.append("execute_project_collaboration")
    seen: set[str] = set()
    ordered: list[str] = []
    for name in suggestions:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _analyze_task_payload(raw_request: str, project_id: str = "", employee_id: str = "") -> dict:
    raw_request_value = _normalize_text(raw_request)
    project_id_value = _normalize_text(project_id)
    employee_id_value = _normalize_text(employee_id)
    task_types = _detect_task_types(raw_request_value)
    scopes = _detect_scope(raw_request_value)
    objective = raw_request_value.splitlines()[0].strip() if raw_request_value else ""
    return {
        "raw_request": raw_request_value,
        "project_id": project_id_value,
        "employee_id": employee_id_value,
        "task_types": task_types,
        "scope": scopes,
        "objective": objective,
        "constraints": _extract_constraints(raw_request_value),
        "mentioned_paths": _extract_paths_and_routes(raw_request_value),
        "deliverables": _infer_deliverables(task_types, scopes),
        "suggested_next_tools": _suggest_next_tools(project_id_value, task_types),
        "analysis_mode": "heuristic",
    }


def _rank_project_members(project_id: str, task: str, limit: int) -> list[dict]:
    members = list_project_member_profiles_runtime(
        project_id,
        include_disabled=False,
        include_missing=False,
        rule_limit=30,
    )
    scored: list[tuple[int, dict]] = []
    for item in members:
        score = _score_text_match(
            task,
            item.get("name"),
            item.get("description"),
            item.get("goal"),
            " ".join(str(value or "") for value in item.get("skill_names") or []),
        )
        if score <= 0:
            continue
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("employee_id") or "")))
    results: list[dict] = []
    for score, item in scored[:limit]:
        results.append(
            {
                "employee_id": str(item.get("employee_id") or ""),
                "name": str(item.get("name") or ""),
                "description": str(item.get("description") or ""),
                "skill_names": item.get("skill_names") or [],
                "match_score": score,
            }
        )
    return results


def _rank_project_rules(project_id: str, task: str, employee_id: str, limit: int) -> list[dict]:
    rules = query_project_rules_runtime(project_id, keyword="", employee_id=employee_id)
    scored: list[tuple[int, dict]] = []
    for item in rules:
        score = _score_text_match(task, item.get("title"), item.get("domain"), item.get("content"))
        if score <= 0:
            continue
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("id") or "")))
    results: list[dict] = []
    for score, item in scored[:limit]:
        results.append(
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "domain": str(item.get("domain") or ""),
                "match_score": score,
            }
        )
    return results


def _rank_project_tools(project_id: str, task: str, employee_id: str, limit: int) -> list[dict]:
    from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime

    tools = list_project_proxy_tools_runtime(project_id, employee_id)
    scored: list[tuple[int, dict]] = []
    for item in tools:
        score = _score_text_match(
            task,
            item.get("tool_name"),
            item.get("description"),
            item.get("entry_name"),
            item.get("employee_id"),
            item.get("employee_name"),
        )
        if score <= 0:
            continue
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("tool_name") or "")))
    results: list[dict] = []
    for score, item in scored[:limit]:
        results.append(
            {
                "tool_name": str(item.get("tool_name") or ""),
                "employee_id": str(item.get("employee_id") or ""),
                "employee_name": str(item.get("employee_name") or ""),
                "description": str(item.get("description") or ""),
                "match_score": score,
            }
        )
    return results


def _resolve_relevant_context_payload(task: str, project_id: str = "", employee_id: str = "", limit: int = 5) -> dict:
    task_value = _normalize_text(task)
    project_id_value = _normalize_text(project_id)
    employee_id_value = _normalize_text(employee_id)
    try:
        limit_value = max(1, min(int(limit or 5), 10))
    except (TypeError, ValueError):
        limit_value = 5
    payload = {
        "task": task_value,
        "project_id": project_id_value,
        "employee_id": employee_id_value,
        "limit": limit_value,
        "matched_projects": _search_projects(task_value, limit_value) if not project_id_value else [],
        "matched_employees": _search_employees(task_value, project_id_value, limit_value),
        "matched_rules": _search_rules(task_value, project_id_value, employee_id_value, limit_value),
        "matched_members": [],
        "matched_tools": [],
    }
    if project_id_value:
        payload["project"] = {
            "id": project_id_value,
            "summary": get_project_detail_runtime(project_id_value),
        }
        payload["matched_members"] = _rank_project_members(project_id_value, task_value, limit_value)
        payload["matched_rules"] = _rank_project_rules(
            project_id_value,
            task_value,
            employee_id_value,
            limit_value,
        )
        payload["matched_tools"] = _rank_project_tools(
            project_id_value,
            task_value,
            employee_id_value,
            limit_value,
        )
    return payload


def _generic_execution_steps(task: str, project_id: str = "") -> list[dict]:
    analysis = _analyze_task_payload(task, project_id=project_id)
    task_types = analysis.get("task_types") or []
    steps = [
        {
            "step": "保留用户原始问题并读取 usage-guide",
            "recommended_tool": "search_ids" if not project_id else "get_manual_content",
            "purpose": "先固定问题原文和入口约定，避免后续上下文漂移",
        },
        {
            "step": "收集项目手册、规则和运行时上下文",
            "recommended_tool": "resolve_relevant_context" if project_id else "search_ids",
            "purpose": "确认相关项目、规则、成员和工具范围",
        },
    ]
    if any(item in {"frontend", "backend", "mcp-upgrade", "bugfix"} for item in task_types):
        steps.append(
            {
                "step": "做实现拆解并确定最小增量修改面",
                "recommended_tool": "generate_execution_plan",
                "purpose": "把任务拆成可执行步骤，再决定是否需要项目协作",
            }
        )
    steps.append(
        {
            "step": "执行实现或编排协作",
            "recommended_tool": "execute_project_collaboration" if project_id else "get_content",
            "purpose": "进入实际实现、联调或多人协作阶段",
        }
    )
    steps.append(
        {
            "step": "保存结论与验证结果",
            "recommended_tool": "save_project_memory" if project_id else "get_content",
            "purpose": "沉淀结构化结论，便于后续恢复与复用",
        }
    )
    return steps


def _generate_execution_plan_payload(
    task: str,
    project_id: str = "",
    employee_id: str = "",
    max_steps: int = 6,
) -> dict:
    task_value = _normalize_text(task)
    project_id_value = _normalize_text(project_id)
    employee_id_value = _normalize_text(employee_id)
    try:
        step_limit = max(1, min(int(max_steps or 6), 10))
    except (TypeError, ValueError):
        step_limit = 6
    if project_id_value:
        from services.dynamic_mcp_collaboration import execute_project_collaboration_runtime

        result = execute_project_collaboration_runtime(
            project_id=project_id_value,
            task=task_value,
            employee_ids=[employee_id_value] if employee_id_value else [],
            max_employees=1 if employee_id_value else 3,
            max_tool_calls=0,
            auto_execute=False,
            include_external_tools=False,
            timeout_sec=30,
            invoke_tool=None,
        )
        if isinstance(result, dict) and not result.get("error"):
            plan_steps = result.get("plan_steps") or []
            return {
                "task": task_value,
                "project_id": project_id_value,
                "employee_id": employee_id_value,
                "planning_mode": "project-collaboration-runtime",
                "selected_employee_ids": result.get("selected_employee_ids") or [],
                "selected_members": result.get("selected_members") or [],
                "candidate_tools": result.get("candidate_tools") or [],
                "plan_steps": plan_steps[:step_limit],
                "plan_step_count": min(len(plan_steps), step_limit),
            }
    generic_steps = _generic_execution_steps(task_value, project_id=project_id_value)
    return {
        "task": task_value,
        "project_id": project_id_value,
        "employee_id": employee_id_value,
        "planning_mode": "heuristic",
        "selected_employee_ids": [employee_id_value] if employee_id_value else [],
        "selected_members": [],
        "candidate_tools": [],
        "plan_steps": generic_steps[:step_limit],
        "plan_step_count": min(len(generic_steps), step_limit),
    }


def _infer_action(tool_name: str = "", command: str = "", path: str = "", action: str = "") -> str:
    normalized_action = _normalize_text_lower(action)
    if normalized_action:
        return normalized_action
    normalized_tool = _normalize_text_lower(tool_name)
    normalized_command = _normalize_text_lower(command)
    normalized_path = _normalize_text_lower(path)
    if normalized_tool in {"local_connector_write_file"}:
        return "write"
    if normalized_tool in {"local_connector_read_file"}:
        return "read"
    if normalized_tool in {"local_connector_run_command"}:
        if any(pattern in normalized_command for pattern in _DESTRUCTIVE_COMMAND_PATTERNS):
            return "destructive"
        if any(hint in normalized_command for hint in _WRITE_COMMAND_HINTS):
            return "write"
        return "execute"
    if any(pattern in normalized_command for pattern in _DESTRUCTIVE_COMMAND_PATTERNS):
        return "destructive"
    if any(hint in normalized_command for hint in _WRITE_COMMAND_HINTS):
        return "write"
    if any(hint in normalized_command for hint in _LOW_RISK_COMMAND_HINTS):
        return "read"
    if normalized_path:
        return "write" if any(
            normalized_path.endswith(suffix) for suffix in (".md", ".json", ".yml", ".yaml", ".ts", ".tsx", ".py", ".vue")
        ) else "read"
    if normalized_tool:
        return "execute"
    return "read"


def _normalize_workspace_path(project_id: str = "", workspace_path: str = "") -> str:
    direct = _normalize_text(workspace_path)
    if direct:
        return direct
    project_id_value = _normalize_text(project_id)
    if not project_id_value:
        return ""
    payload = get_project_detail_runtime(project_id_value)
    if payload.get("error"):
        return ""
    settings = payload.get("chat_settings") or {}
    connector_workspace = _normalize_text(settings.get("connector_workspace_path"))
    if connector_workspace:
        return connector_workspace
    return _normalize_text(payload.get("workspace_path"))


def _normalize_sandbox_mode(project_id: str = "", sandbox_mode: str = "") -> str:
    sandbox_value = _normalize_text(sandbox_mode)
    if sandbox_value in {"read-only", "workspace-write"}:
        return sandbox_value
    project_id_value = _normalize_text(project_id)
    if not project_id_value:
        return "workspace-write"
    payload = get_project_detail_runtime(project_id_value)
    if payload.get("error"):
        return "workspace-write"
    settings = payload.get("chat_settings") or {}
    candidate = _normalize_text(settings.get("connector_sandbox_mode"))
    return candidate if candidate in {"read-only", "workspace-write"} else "workspace-write"


def _project_high_risk_confirm(project_id: str) -> bool:
    project_id_value = _normalize_text(project_id)
    if not project_id_value:
        return True
    payload = get_project_detail_runtime(project_id_value)
    if payload.get("error"):
        return True
    settings = payload.get("chat_settings") or {}
    return bool(settings.get("high_risk_tool_confirm", True))


def _path_scope_payload(path: str, project_id: str = "", workspace_path: str = "", sandbox_mode: str = "") -> dict:
    path_value = _normalize_text(path)
    workspace_value = _normalize_workspace_path(project_id, workspace_path)
    sandbox_value = _normalize_sandbox_mode(project_id, sandbox_mode)
    if not path_value:
        return {
            "path": "",
            "workspace_path": workspace_value,
            "sandbox_mode": sandbox_value,
            "path_kind": "none",
            "within_workspace": None,
            "allowed": True,
            "reason": "path_not_provided",
        }
    is_absolute = path_value.startswith("/")
    normalized_path = os.path.normpath(path_value) if is_absolute else path_value
    normalized_workspace = os.path.normpath(workspace_value) if workspace_value else ""
    within_workspace: bool | None = None
    allowed = True
    reason = "relative_to_workspace" if not is_absolute else "workspace_not_configured"
    if is_absolute and normalized_workspace:
        try:
            within_workspace = os.path.commonpath([normalized_path, normalized_workspace]) == normalized_workspace
        except ValueError:
            within_workspace = False
        reason = "inside_workspace" if within_workspace else "outside_workspace"
    elif not is_absolute:
        within_workspace = True if normalized_workspace else None
    if normalized_path and any(
        normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
        for prefix in _SYSTEM_PATH_PREFIXES
        if prefix.startswith("/")
    ):
        allowed = False
        reason = "system_path"
    if within_workspace is False and sandbox_value == "workspace-write":
        allowed = False
    return {
        "path": path_value,
        "normalized_path": normalized_path,
        "workspace_path": workspace_value,
        "sandbox_mode": sandbox_value,
        "path_kind": "absolute" if is_absolute else "relative",
        "within_workspace": within_workspace,
        "allowed": allowed,
        "reason": reason,
    }


def _classify_risk_payload(
    command: str = "",
    tool_name: str = "",
    path: str = "",
    project_id: str = "",
    action: str = "",
) -> dict:
    command_value = _normalize_text_lower(command)
    tool_name_value = _normalize_text(tool_name)
    action_value = _infer_action(tool_name=tool_name, command=command, path=path, action=action)
    reasons: list[str] = []
    indicators: list[str] = []
    risk_level = "low"
    if any(pattern in command_value for pattern in _DESTRUCTIVE_COMMAND_PATTERNS):
        risk_level = "critical"
        reasons.append("命中破坏性命令模式")
        indicators.append("destructive_command")
    elif any(pattern in command_value for pattern in _HIGH_RISK_COMMAND_PATTERNS):
        risk_level = "high"
        reasons.append("命中高风险命令模式")
        indicators.append("high_risk_command")
    if tool_name_value == "local_connector_write_file":
        risk_level = "medium" if risk_level == "low" else risk_level
        reasons.append("涉及文件写入")
        indicators.append("file_write")
    if path:
        scope = _path_scope_payload(path, project_id=project_id)
        if scope.get("reason") == "system_path":
            risk_level = "high" if risk_level in {"low", "medium"} else risk_level
            reasons.append("目标路径属于系统敏感路径")
            indicators.append("system_path")
        elif scope.get("within_workspace") is False:
            risk_level = "high" if risk_level in {"low", "medium"} else risk_level
            reasons.append("目标路径在项目工作区之外")
            indicators.append("outside_workspace")
    if action_value == "destructive" and risk_level != "critical":
        risk_level = "high"
        reasons.append("动作类型为 destructive")
        indicators.append("destructive_action")
    elif action_value in {"write", "execute"} and risk_level == "low":
        risk_level = "medium"
        reasons.append("动作会修改文件或执行命令")
        indicators.append("write_or_execute")
    if not reasons:
        reasons.append("仅涉及只读查询或低风险命令")
        indicators.append("read_only")
    requires_confirmation = risk_level in {"high", "critical"}
    return {
        "project_id": _normalize_text(project_id),
        "tool_name": tool_name_value,
        "command": _normalize_text(command),
        "path": _normalize_text(path),
        "action": action_value,
        "risk_level": risk_level,
        "requires_confirmation": requires_confirmation,
        "reasons": reasons,
        "indicators": indicators,
    }


def _resolve_execution_mode_payload(
    project_id: str = "",
    tool_name: str = "",
    command: str = "",
    path: str = "",
    employee_id: str = "",
    prefer_connector: bool = True,
) -> dict:
    project_id_value = _normalize_text(project_id)
    tool_name_value = _normalize_text(tool_name)
    workspace_value = _normalize_workspace_path(project_id_value)
    sandbox_value = _normalize_sandbox_mode(project_id_value)
    mode = "query-only"
    reason = "no_execution_target"
    if tool_name_value.startswith("local_connector_"):
        mode = "local_connector"
        reason = "tool_name_requests_connector"
    elif tool_name_value:
        mode = "project_tool"
        reason = "tool_name_provided"
    elif prefer_connector and (command or path) and workspace_value:
        mode = "local_connector"
        reason = "workspace_command_or_path_detected"
    elif command or path:
        mode = "manual_external"
        reason = "execution_requested_without_project_tool"
    return {
        "project_id": project_id_value,
        "employee_id": _normalize_text(employee_id),
        "tool_name": tool_name_value,
        "mode": mode,
        "reason": reason,
        "workspace_path": workspace_value,
        "sandbox_mode": sandbox_value,
        "prefer_connector": bool(prefer_connector),
    }


def _is_known_project_tool(project_id: str, tool_name: str, employee_id: str = "") -> bool:
    project_id_value = _normalize_text(project_id)
    tool_name_value = _normalize_text(tool_name)
    if not project_id_value or not tool_name_value:
        return False
    if tool_name_value in _QUERY_TOOL_NAMES or tool_name_value.startswith("local_connector_"):
        return True
    from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime

    for item in list_project_proxy_tools_runtime(project_id_value, _normalize_text(employee_id)):
        if _normalize_text(item.get("tool_name")) == tool_name_value:
            return True
    return False


def _check_operation_policy_payload(
    project_id: str = "",
    tool_name: str = "",
    command: str = "",
    path: str = "",
    employee_id: str = "",
    action: str = "",
    workspace_path: str = "",
    sandbox_mode: str = "",
) -> dict:
    project_id_value = _normalize_text(project_id)
    tool_name_value = _normalize_text(tool_name)
    execution = _resolve_execution_mode_payload(
        project_id=project_id_value,
        tool_name=tool_name_value,
        command=command,
        path=path,
        employee_id=employee_id,
    )
    risk = _classify_risk_payload(
        command=command,
        tool_name=tool_name_value,
        path=path,
        project_id=project_id_value,
        action=action,
    )
    scope = _path_scope_payload(
        path,
        project_id=project_id_value,
        workspace_path=workspace_path or execution.get("workspace_path") or "",
        sandbox_mode=sandbox_mode or execution.get("sandbox_mode") or "",
    )
    policy_reasons: list[str] = []
    allowed = True
    requires_confirmation = bool(risk.get("requires_confirmation"))
    if project_id_value and tool_name_value and not _is_known_project_tool(project_id_value, tool_name_value, employee_id):
        allowed = False
        policy_reasons.append("tool_not_in_project_scope")
    if scope.get("reason") == "system_path":
        allowed = False
        policy_reasons.append("system_path_blocked")
    if scope.get("within_workspace") is False and execution.get("sandbox_mode") == "workspace-write":
        allowed = False
        policy_reasons.append("outside_workspace_blocked")
    if execution.get("sandbox_mode") == "read-only" and risk.get("action") in {"write", "destructive"}:
        allowed = False
        policy_reasons.append("read_only_mode_blocks_write")
    if risk.get("risk_level") in {"high", "critical"} and _project_high_risk_confirm(project_id_value):
        requires_confirmation = True
        policy_reasons.append("high_risk_requires_confirmation")
    if allowed and not policy_reasons:
        policy_reasons.append("policy_check_passed")
    return {
        "project_id": project_id_value,
        "employee_id": _normalize_text(employee_id),
        "tool_name": tool_name_value,
        "allowed": allowed,
        "requires_confirmation": requires_confirmation,
        "risk": risk,
        "workspace_scope": scope,
        "execution_mode": execution,
        "policy_reasons": policy_reasons,
    }


def _resolve_project_name(project_id: str = "", project_name: str = "") -> str:
    direct = _normalize_text(project_name)
    if direct:
        return direct
    project_id_value = _normalize_text(project_id)
    if not project_id_value:
        return "default"
    project = project_store.get(project_id_value)
    if project is None:
        return "default"
    return _normalize_text(getattr(project, "name", "")) or "default"


def _save_project_memory_entries(
    *,
    project_id: str,
    content: str,
    employee_id: str = "",
    memory_type: MemoryType = MemoryType.PROJECT_CONTEXT,
    importance: float = 0.6,
    project_name: str = "",
    purpose_tags: tuple[str, ...] = ("query-mcp",),
) -> dict:
    project_id_value = _normalize_text(project_id)
    employee_id_value = _normalize_text(employee_id)
    content_value = _normalize_text(content)
    if not project_id_value:
        return {"error": "project_id is required"}
    if not content_value:
        return {"error": "content is required"}
    project = project_store.get(project_id_value)
    if project is None:
        return {"error": f"Project {project_id_value} not found"}
    active_employee_ids = _active_project_employee_ids(project_id_value)
    if not active_employee_ids:
        return {"error": f"Project {project_id_value} has no active members"}
    if employee_id_value and employee_id_value not in active_employee_ids:
        return {"error": f"Employee {employee_id_value} is not an active project member"}
    normalized_project_name = _resolve_project_name(project_id_value, project_name)
    target_employee_ids = [employee_id_value] if employee_id_value else active_employee_ids
    memory_ids: list[str] = []
    importance_value = max(0.0, min(float(importance), 1.0))
    for target_employee_id in target_employee_ids:
        memory = Memory(
            id=memory_store.new_id(),
            employee_id=target_employee_id,
            type=memory_type,
            content=content_value,
            project_name=normalized_project_name,
            importance=importance_value,
            scope=MemoryScope.EMPLOYEE_PRIVATE,
            classification=Classification.INTERNAL,
            purpose_tags=purpose_tags,
        )
        memory_store.save(memory)
        memory_ids.append(memory.id)
    return {
        "status": "saved",
        "project_id": project_id_value,
        "project_name": normalized_project_name,
        "employee_ids": target_employee_ids,
        "memory_ids": memory_ids,
        "saved_count": len(memory_ids),
        "type": memory_type.value,
        "importance": importance_value,
        "project_mcp_path": f"/mcp/projects/{project_id_value}",
    }


def _parse_fact_lines(content: str = "", facts: list[str] | None = None) -> list[str]:
    items: list[str] = []
    for item in facts or []:
        normalized = _normalize_text(item)
        if normalized and normalized not in items:
            items.append(normalized)
    for line in _normalize_text(content).splitlines():
        normalized = line.strip(" -\t")
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _normalize_tag_token(value: object, prefix: str) -> str:
    normalized = _normalize_text_lower(value)
    if not normalized:
        return ""
    compact = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", normalized).strip("-")
    return f"{prefix}:{compact[:40]}" if compact else ""


def _structured_trajectory_payload(
    *,
    kind: str,
    session_id: str = "",
    event_type: str = "",
    phase: str = "",
    step: str = "",
    status: str = "",
    goal: str = "",
    changed_files: list[str] | None = None,
    verification: list[str] | None = None,
    risks: list[str] | None = None,
    next_steps: list[str] | None = None,
    facts: list[str] | None = None,
    content: str = "",
) -> dict:
    payload = {
        "kind": _normalize_text(kind),
        "session_id": _normalize_text(session_id),
        "event_type": _normalize_text(event_type),
        "phase": _normalize_text(phase),
        "step": _normalize_text(step),
        "status": _normalize_text(status),
        "goal": _normalize_text(goal),
        "changed_files": _coerce_list_text(changed_files),
        "verification": _coerce_list_text(verification),
        "risks": _coerce_list_text(risks),
        "next_steps": _coerce_list_text(next_steps),
        "facts": _coerce_list_text(facts),
        "content": _normalize_text(content),
    }
    return {key: value for key, value in payload.items() if value not in ("", [], None)}


def _save_work_session_event_record(
    *,
    project_id: str,
    project_name: str = "",
    employee_id: str = "",
    trajectory: dict,
) -> dict:
    project_id_value = _normalize_text(project_id)
    session_id_value = _normalize_text(trajectory.get("session_id"))
    if not project_id_value or not session_id_value:
        return {"status": "skipped", "reason": "project_id_or_session_id_missing"}
    try:
        event = WorkSessionEvent(
            id=work_session_store.new_id(),
            project_id=project_id_value,
            project_name=_resolve_project_name(project_id_value, project_name),
            employee_id=_normalize_text(employee_id),
            session_id=session_id_value,
            source_kind=_normalize_text(trajectory.get("kind")),
            event_type=_normalize_text(trajectory.get("event_type")),
            phase=_normalize_text(trajectory.get("phase")),
            step=_normalize_text(trajectory.get("step")),
            status=_normalize_text(trajectory.get("status")),
            goal=_normalize_text(trajectory.get("goal")),
            content=_normalize_text(trajectory.get("content")),
            facts=_coerce_list_text(trajectory.get("facts")),
            changed_files=_coerce_list_text(trajectory.get("changed_files")),
            verification=_coerce_list_text(trajectory.get("verification")),
            risks=_coerce_list_text(trajectory.get("risks")),
            next_steps=_coerce_list_text(trajectory.get("next_steps")),
        )
        work_session_store.save(event)
    except Exception as exc:  # pragma: no cover - defensive guard
        return {"status": "error", "detail": str(exc)}
    return {"status": "saved", "event_id": event.id}


def _work_session_event_to_item(event: WorkSessionEvent) -> dict:
    memory_type = (
        MemoryType.LEARNED_PATTERN.value
        if _normalize_text(event.source_kind) == "work-facts"
        else MemoryType.KEY_EVENT.value
    )
    trajectory = {
        "kind": _normalize_text(event.source_kind),
        "session_id": _normalize_text(event.session_id),
        "event_type": _normalize_text(event.event_type),
        "phase": _normalize_text(event.phase),
        "step": _normalize_text(event.step),
        "status": _normalize_text(event.status),
        "goal": _normalize_text(event.goal),
        "content": _normalize_text(event.content),
        "facts": _coerce_list_text(event.facts),
        "changed_files": _coerce_list_text(event.changed_files),
        "verification": _coerce_list_text(event.verification),
        "risks": _coerce_list_text(event.risks),
        "next_steps": _coerce_list_text(event.next_steps),
    }
    if _normalize_text(event.source_kind) == "work-facts":
        content = _render_structured_work_facts(
            fact_items=_coerce_list_text(event.facts),
            trajectory=trajectory,
        )
    else:
        content = _render_structured_session_event(
            session_id=_normalize_text(event.session_id),
            event_type=_normalize_text(event.event_type),
            content=_normalize_text(event.content),
            trajectory=trajectory,
        )
    return {
        "id": _normalize_text(event.id),
        "employee_id": _normalize_text(event.employee_id),
        "project_name": _normalize_text(event.project_name),
        "type": memory_type,
        "content": content,
        "created_at": _normalize_text(event.created_at),
        "updated_at": _normalize_text(event.updated_at),
        "trajectory": {key: value for key, value in trajectory.items() if value not in ("", [], None)},
    }


def _collect_work_session_records(
    *,
    project_id: str,
    employee_id: str = "",
    session_id: str = "",
    query: str = "",
    limit: int = 200,
) -> list[dict]:
    try:
        events = work_session_store.list_events(
            project_id=_normalize_text(project_id),
            employee_id=_normalize_text(employee_id),
            session_id=_normalize_text(session_id),
            query=_normalize_text(query),
            limit=max(1, min(int(limit or 200), 500)),
        )
    except Exception:  # pragma: no cover - defensive fallback
        return []
    return [_work_session_event_to_item(item) for item in events]


def _trajectory_purpose_tags(
    *,
    base_tags: tuple[str, ...],
    session_id: str = "",
    phase: str = "",
    step: str = "",
) -> tuple[str, ...]:
    tags = list(base_tags)
    for value, prefix in (
        (session_id, "session"),
        (phase, "phase"),
        (step, "step"),
    ):
        token = _normalize_tag_token(value, prefix)
        if token and token not in tags:
            tags.append(token)
    return tuple(tags)


def _render_structured_work_facts(
    *,
    fact_items: list[str],
    trajectory: dict,
) -> str:
    lines = ["[工作事实]"]
    lines.extend(f"- {item}" for item in fact_items)
    if trajectory:
        lines.append("")
        lines.append("[执行轨迹]")
        for key, label in (
            ("session_id", "session_id"),
            ("phase", "phase"),
            ("step", "step"),
            ("status", "status"),
            ("goal", "goal"),
        ):
            value = _normalize_text(trajectory.get(key))
            if value:
                lines.append(f"- {label}: {value}")
        for key in ("changed_files", "verification", "risks", "next_steps"):
            values = _coerce_list_text(trajectory.get(key))
            if values:
                lines.append(f"- {key}: {' | '.join(values)}")
        lines.append("[执行轨迹JSON] " + json.dumps(trajectory, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


def _render_structured_session_event(
    *,
    session_id: str,
    event_type: str,
    content: str,
    trajectory: dict,
) -> str:
    lines = [f"[会话事件] session_id={session_id} event_type={event_type}", content]
    if trajectory:
        lines.append("")
        lines.append("[执行轨迹]")
        for key, label in (
            ("phase", "phase"),
            ("step", "step"),
            ("status", "status"),
            ("goal", "goal"),
        ):
            value = _normalize_text(trajectory.get(key))
            if value:
                lines.append(f"- {label}: {value}")
        for key in ("changed_files", "verification", "risks", "next_steps"):
            values = _coerce_list_text(trajectory.get(key))
            if values:
                lines.append(f"- {key}: {' | '.join(values)}")
        lines.append("[执行轨迹JSON] " + json.dumps(trajectory, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


def _extract_structured_trajectory(content: str) -> dict:
    content_value = _normalize_text(content)
    if not content_value:
        return {}
    for line in content_value.splitlines():
        normalized = line.strip()
        if not normalized.startswith("[执行轨迹JSON]"):
            continue
        payload = normalized[len("[执行轨迹JSON]") :].strip()
        if not payload:
            continue
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded

    if content_value.startswith("[工作事实]"):
        facts = _parse_fact_lines(content=content_value)
        if facts:
            return {
                "kind": "work-facts",
                "facts": facts,
            }

    first_line, _, remainder = content_value.partition("\n")
    match = re.match(r"^\[会话事件\]\s+session_id=([^\s]+)\s+event_type=([^\s]+)$", first_line.strip())
    if match:
        payload = {
            "kind": "session-event",
            "session_id": match.group(1),
            "event_type": match.group(2),
        }
        body = _normalize_text(remainder)
        if body:
            payload["content"] = body
        return payload

    return {}


def _decorate_work_memory(item: dict) -> dict:
    decorated = dict(item)
    trajectory = _extract_structured_trajectory(decorated.get("content", ""))
    if trajectory:
        decorated["trajectory"] = trajectory
    return decorated


def _build_checkpoint_view(memories: list[dict]) -> dict:
    phases: list[str] = []
    steps: list[str] = []
    changed_files: list[str] = []
    verification: list[str] = []
    risks: list[str] = []
    next_steps: list[str] = []
    timeline: list[dict] = []
    latest_status = ""

    for item in memories:
        trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else {}
        phase_value = _normalize_text(trajectory.get("phase"))
        step_value = _normalize_text(trajectory.get("step"))
        status_value = _normalize_text(trajectory.get("status"))
        event_type_value = _normalize_text(trajectory.get("event_type"))

        if phase_value and phase_value not in phases:
            phases.append(phase_value)
        if step_value and step_value not in steps:
            steps.append(step_value)
        if status_value and not latest_status:
            latest_status = status_value

        for source, target in (
            (_coerce_list_text(trajectory.get("changed_files")), changed_files),
            (_coerce_list_text(trajectory.get("verification")), verification),
            (_coerce_list_text(trajectory.get("risks")), risks),
            (_coerce_list_text(trajectory.get("next_steps")), next_steps),
        ):
            for value in source:
                if value not in target:
                    target.append(value)

        summary = _normalize_text(trajectory.get("content"))
        if not summary:
            facts = _coerce_list_text(trajectory.get("facts"))
            if facts:
                summary = "；".join(facts[:3])
        if not summary:
            summary = _normalize_text(item.get("content")).replace("\n", " | ")[:180]

        timeline.append(
            {
                "memory_id": _normalize_text(item.get("id")),
                "created_at": _normalize_text(item.get("created_at")),
                "type": _normalize_text(item.get("type")),
                "session_id": _normalize_text(trajectory.get("session_id")),
                "event_type": event_type_value,
                "phase": phase_value,
                "step": step_value,
                "status": status_value,
                "summary": summary,
            }
        )

    return {
        "phases": phases,
        "steps": steps,
        "changed_files": changed_files,
        "verification": verification,
        "risks": risks,
        "next_steps": next_steps,
        "latest_status": latest_status,
        "timeline": timeline[:8],
    }


def _collect_project_memories(
    *,
    project_id: str,
    employee_id: str = "",
    project_name: str = "",
    query: str = "",
    limit: int = 10,
) -> list[dict]:
    project_id_value = _normalize_text(project_id)
    employee_id_value = _normalize_text(employee_id)
    normalized_project_name = _resolve_project_name(project_id_value, project_name)
    try:
        limit_value = max(1, min(int(limit or 10), 50))
    except (TypeError, ValueError):
        limit_value = 10
    target_employee_ids = [employee_id_value] if employee_id_value else _active_project_employee_ids(project_id_value)
    seen_ids: set[str] = set()
    collected: list[dict] = []
    for target_employee_id in target_employee_ids:
        if query:
            memories = memory_store.recall(
                target_employee_id,
                _normalize_text(query),
                limit_value,
                project_name=normalized_project_name,
            )
        else:
            memories = memory_store.recent(
                target_employee_id,
                limit_value,
                project_name=normalized_project_name,
            )
        for mem in memories:
            if getattr(mem, "id", "") in seen_ids:
                continue
            seen_ids.add(getattr(mem, "id", ""))
            collected.append(serialize_memory(mem))
    collected.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            str(item.get("importance") or ""),
        ),
        reverse=True,
    )
    return collected[:limit_value]


def _filter_session_memories(memories: list[dict], session_id: str = "", event_types: tuple[str, ...] = ()) -> list[dict]:
    session_id_value = _normalize_text(session_id)
    normalized_event_types = {_normalize_text(event_type) for event_type in event_types if _normalize_text(event_type)}
    filtered: list[dict] = []
    for item in memories:
        trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else {}
        trajectory_session_id = _normalize_text(trajectory.get("session_id"))
        content = _normalize_text(item.get("content"))
        if session_id_value and session_id_value not in {trajectory_session_id, ""}:
            if session_id_value not in content:
                continue
        if normalized_event_types:
            trajectory_event_type = _normalize_text(trajectory.get("event_type"))
            if trajectory_event_type:
                if trajectory_event_type not in normalized_event_types:
                    continue
            elif not any(f"event_type={event_type}" in content for event_type in normalized_event_types):
                continue
        filtered.append(item)
    return filtered


def _checkpoint_summary_text(project_id: str, project_name: str, session_id: str, memories: list[dict]) -> str:
    checkpoint = _build_checkpoint_view(memories)
    lines = [
        f"项目：{project_name or project_id}",
    ]
    if session_id:
        lines.append(f"会话：{session_id}")
    if checkpoint["phases"]:
        lines.append(f"阶段：{' -> '.join(checkpoint['phases'])}")
    if checkpoint["steps"]:
        lines.append(f"步骤：{' -> '.join(checkpoint['steps'][:4])}")
    if checkpoint["latest_status"]:
        lines.append(f"当前状态：{checkpoint['latest_status']}")
    if checkpoint["changed_files"]:
        lines.append("相关文件：")
        lines.extend(f"- {item}" for item in checkpoint["changed_files"][:6])
    if checkpoint["verification"]:
        lines.append("验证：")
        lines.extend(f"- {item}" for item in checkpoint["verification"][:6])
    if checkpoint["risks"]:
        lines.append("风险：")
        lines.extend(f"- {item}" for item in checkpoint["risks"][:4])
    if checkpoint["next_steps"]:
        lines.append("下一步：")
        lines.extend(f"- {item}" for item in checkpoint["next_steps"][:4])
    if not memories:
        lines.append("暂无可恢复的工作轨迹。")
        return "\n".join(lines)
    lines.append("最近轨迹：")
    for item in checkpoint["timeline"][:6]:
        summary = _normalize_text(item.get("summary"))
        phase_value = _normalize_text(item.get("phase"))
        step_value = _normalize_text(item.get("step"))
        event_type_value = _normalize_text(item.get("event_type"))
        label_parts = [part for part in (phase_value, step_value, event_type_value) if part]
        suffix = f" ({' / '.join(label_parts)})" if label_parts else ""
        lines.append(
            f"- [{_normalize_text(item.get('type'))}] {_normalize_text(item.get('created_at'))}{suffix} {summary[:180]}"
        )
    return "\n".join(lines)


def _structured_session_items(memories: list[dict]) -> list[dict]:
    return [_decorate_work_memory(item) for item in memories]


def _legacy_fact_or_event_counts(memories: list[dict]) -> tuple[int, int]:
    facts = [item for item in memories if _normalize_text(item.get("type")) == MemoryType.LEARNED_PATTERN.value]
    events = [item for item in memories if _normalize_text(item.get("type")) == MemoryType.KEY_EVENT.value]
    return len(facts), len(events)


def _client_profile_text(client_name: str) -> str:
    normalized = _normalize_text_lower(client_name)
    title = client_name
    if normalized == "claude-code":
        title = "Claude Code"
        focus = [
            "- 定位: 适合需要较强代码修改、命令执行和长任务续跑的开发型 CLI。",
            "- 推荐链路: query://usage-guide -> analyze_task -> search_ids/get_manual_content -> resolve_relevant_context -> generate_execution_plan -> check_operation_policy。",
            "- 长任务建议: 每完成一个子阶段调用 save_work_facts 或 append_session_event，恢复时调用 resume_work_session / summarize_checkpoint。",
            "- 适合自动化的能力: 任务分析、相关上下文聚合、执行步骤骨架、风险分类、工作轨迹恢复。",
            "- 需要谨慎的能力: 高风险命令、工作区外路径、破坏性命令，优先先调用 check_operation_policy。",
        ]
    elif normalized == "codex":
        title = "Codex"
        focus = [
            "- 定位: 适合以代码任务拆解、补丁实现和结构化交付为主的开发型 CLI。",
            "- 推荐链路: query://usage-guide -> analyze_task -> resolve_relevant_context -> generate_execution_plan -> build_delivery_report。",
            "- 长任务建议: 关键决策写入 save_work_facts，关键执行节点写入 append_session_event。",
            "- 适合自动化的能力: 结构化任务分析、项目规则聚合、交付报告、更新日志条目生成。",
            "- 需要谨慎的能力: 任何真实执行前先补 classify_command_risk / check_operation_policy。",
        ]
    else:
        title = "Generic CLI"
        focus = [
            "- 定位: 适合通用 MCP 宿主或尚未针对当前系统定制的 CLI 客户端。",
            "- 推荐链路: query://usage-guide -> search_ids -> get_manual_content -> analyze_task -> resolve_relevant_context。",
            "- 最小可用目标: 先跑通查询、分析、规划，再逐步接入策略判断和恢复能力。",
            "- 建议优先工具: analyze_task、resolve_relevant_context、generate_execution_plan、check_operation_policy。",
            "- 长任务建议: 使用 save_work_facts 和 summarize_checkpoint 做轻量恢复。",
        ]
    return "\n".join([f"# {title} Client Profile", "", *focus])


def _coerce_list_text(values: list[str] | None = None, fallback: str = "") -> list[str]:
    items: list[str] = []
    for item in values or []:
        normalized = _normalize_text(item)
        if normalized and normalized not in items:
            items.append(normalized)
    if fallback:
        for chunk in _normalize_text(fallback).splitlines():
            normalized = chunk.strip(" -\t")
            if normalized and normalized not in items:
                items.append(normalized)
    return items


def _build_delivery_report_payload(
    *,
    title: str = "",
    project_id: str = "",
    summary: str = "",
    completed_items: list[str] | None = None,
    changed_files: list[str] | None = None,
    verification: list[str] | None = None,
    risks: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> dict:
    project_id_value = _normalize_text(project_id)
    project_name_value = _resolve_project_name(project_id_value, "")
    completed = _coerce_list_text(completed_items, summary)
    files = _coerce_list_text(changed_files)
    verification_items = _coerce_list_text(verification)
    risk_items = _coerce_list_text(risks)
    next_step_items = _coerce_list_text(next_steps)
    title_value = _normalize_text(title) or "交付报告"
    report_lines = [f"# {title_value}", ""]
    if project_id_value:
        report_lines.append(f"- 项目: {project_name_value} ({project_id_value})")
    if completed:
        report_lines.append("- 已完成:")
        report_lines.extend(f"  - {item}" for item in completed)
    if files:
        report_lines.append("- 相关文件:")
        report_lines.extend(f"  - {item}" for item in files)
    if verification_items:
        report_lines.append("- 验证:")
        report_lines.extend(f"  - {item}" for item in verification_items)
    if risk_items:
        report_lines.append("- 风险:")
        report_lines.extend(f"  - {item}" for item in risk_items)
    if next_step_items:
        report_lines.append("- 下一步:")
        report_lines.extend(f"  - {item}" for item in next_step_items)
    return {
        "title": title_value,
        "project_id": project_id_value,
        "project_name": project_name_value if project_id_value else "",
        "completed_items": completed,
        "changed_files": files,
        "verification": verification_items,
        "risks": risk_items,
        "next_steps": next_step_items,
        "report_markdown": "\n".join(report_lines).strip(),
    }


def _generate_release_note_entry_payload(
    *,
    version: str = "",
    release_date: str = "",
    summary: str = "",
    key_changes: list[str] | None = None,
    project_id: str = "",
) -> dict:
    version_value = _normalize_text(version) or "Unversioned"
    date_value = _normalize_text(release_date) or _normalize_text(os.environ.get("CURRENT_DATE")) or ""
    changes = _coerce_list_text(key_changes, summary)
    project_name_value = _resolve_project_name(project_id, "")
    entry_lines = [f"## {version_value}"]
    if date_value:
        entry_lines.append(f"- 日期：{date_value}")
    if project_id:
        entry_lines.append(f"- 项目：{project_name_value} ({project_id})")
    if changes:
        entry_lines.append("- 关键变化：")
        entry_lines.extend(f"  - {item}" for item in changes[:8])
    else:
        entry_lines.append("- 关键变化：待补充")
    return {
        "version": version_value,
        "release_date": date_value,
        "project_id": _normalize_text(project_id),
        "project_name": project_name_value if project_id else "",
        "key_changes": changes,
        "entry_markdown": "\n".join(entry_lines),
    }


def create_query_mcp():
    mcp = _new_mcp("query-center")

    def _get_content_payload(
        project_id: str = "",
        employee_id: str = "",
        rule_id: str = "",
        include_project_members: bool = True,
        include_project_rules: bool = True,
        include_employee_skills: bool = True,
        include_employee_rules: bool = True,
    ) -> dict:
        project_id_value = str(project_id or "").strip()
        employee_id_value = str(employee_id or "").strip()
        rule_id_value = str(rule_id or "").strip()
        if not any([project_id_value, employee_id_value, rule_id_value]):
            return {
                "error": "At least one of project_id, employee_id, rule_id is required"
            }

        result = {
            "query": {
                "project_id": project_id_value,
                "employee_id": employee_id_value,
                "rule_id": rule_id_value,
            },
            "project": None,
            "employee": None,
            "rule": None,
            "relation": None,
            "links": {
                "query_mcp_path": "/mcp/query",
                "query_usage_guide_resource": "query://usage-guide",
            },
        }

        if project_id_value:
            result["project"] = _build_project_lookup(
                project_id_value,
                include_members=include_project_members,
                include_rules=include_project_rules,
            )
            result["links"]["project_mcp_path"] = f"/mcp/projects/{project_id_value}"

        if employee_id_value:
            result["employee"] = _build_employee_lookup(
                employee_id_value,
                include_skills=include_employee_skills,
                include_rules=include_employee_rules,
            )
            result["links"]["employee_mcp_path"] = f"/mcp/employees/{employee_id_value}"

        if rule_id_value:
            result["rule"] = _build_rule_lookup(rule_id_value)
            result["links"]["rule_mcp_path"] = f"/mcp/rules/{rule_id_value}"

        if project_id_value and employee_id_value:
            result["relation"] = get_project_employee_detail_runtime(
                project_id_value,
                employee_id_value,
            )

        return result

    @mcp.resource("query://usage-guide")
    def query_usage_guide() -> str:
        return (
            "# Unified Query MCP\n\n"
            "- 统一入口路径: /mcp/query\n"
            "- 目标: 在保留现有员工/项目/规则 MCP 的前提下，提供一个聚合查询入口，并补充最常用的项目执行代理与高层智能体分析能力。\n"
            "- 推荐工具: search_ids / get_content / get_manual_content / analyze_task / resolve_relevant_context / generate_execution_plan / classify_command_risk / check_workspace_scope / resolve_execution_mode / check_operation_policy / save_work_facts / append_session_event / resume_work_session / summarize_checkpoint / build_delivery_report / generate_release_note_entry / save_project_memory\n"
            "- 典型用法: 先 search_ids 找到目标 ID，再用 get_content 或 get_manual_content 取正文。\n"
            "- 高层能力: analyze_task 用于任务结构化理解；resolve_relevant_context 用于聚合相关项目成员/规则/工具；generate_execution_plan 用于输出执行步骤骨架。\n"
            "- 策略能力: classify_command_risk 用于风险等级判断；check_workspace_scope 用于校验路径是否在工作区内；resolve_execution_mode 用于判断该走 local connector 还是项目工具；check_operation_policy 用于输出允许/拦截/需确认结论。\n"
            "- 恢复能力: save_work_facts 和 append_session_event 支持附带 session_id、phase、step、changed_files、verification、risks、next_steps 等结构化轨迹字段；resume_work_session / summarize_checkpoint 会聚合这些字段，直接输出阶段、步骤、文件、验证、风险和下一步。\n"
            "- 交付能力: build_delivery_report 用于结构化汇总本轮交付；generate_release_note_entry 用于生成更新日志条目；可读取 query://client-profile/claude-code 或 query://client-profile/codex 作为客户端接入画像。\n"
            "- 记忆留痕: 首次查询必须把用户原始问题放进可检索字段，优先使用 search_ids(keyword=\"<用户原始问题>\")；不要只传“当前项目”“这个规则”之类代称。\n"
            "- 记忆留痕: 每次有效对话结束后，可调用 save_project_memory(project_id, content, ...) 按项目 ID 显式保存对话内容或结构化结论。\n"
            "- 执行代理: 本入口默认仍以查询与聚合优先；如宿主只接统一入口，项目协作型任务可优先调用 execute_project_collaboration(project_id, task, ...)。\n"
            "- 执行代理: execute_project_collaboration 是统一编排入口，但是否单人主责、是否需要多人协作以及如何拆分，仍由 AI 结合项目手册、员工手册、规则和工具自主判断，不预设固定行业分工模板。\n"
            "- 执行代理: 若需要手动编排项目执行，再继续调用 list_project_members / get_project_runtime_context / list_project_proxy_tools / invoke_project_skill_tool。\n"
            "- 注意: 本入口仍以查询与聚合优先；如宿主支持多 MCP，复杂执行场景仍优先直连对应 project MCP。\n"
            "- 记忆说明: 本入口已暴露 save_project_memory，可通过 project_id 直接写入项目对话内容；save_employee_memory 仍不暴露。如宿主系统已启用自动记忆，入口层仍会自动记录问题快照。"
        )

    @mcp.resource("query://client-profile/claude-code")
    def query_client_profile_claude_code() -> str:
        return _client_profile_text("claude-code")

    @mcp.resource("query://client-profile/codex")
    def query_client_profile_codex() -> str:
        return _client_profile_text("codex")

    @mcp.resource("query://client-profile/generic-cli")
    def query_client_profile_generic_cli() -> str:
        return _client_profile_text("generic-cli")

    @mcp.tool()
    def get_content(
        project_id: str = "",
        employee_id: str = "",
        rule_id: str = "",
    ) -> dict:
        """简化版统一内容查询。

        常用场景优先调用这个工具，不需要自己处理 include 参数。
        """

        return _get_content_payload(
            project_id=project_id,
            employee_id=employee_id,
            rule_id=rule_id,
            include_project_members=True,
            include_project_rules=True,
            include_employee_skills=True,
            include_employee_rules=True,
        )

    @mcp.tool()
    def analyze_task(raw_request: str, project_id: str = "", employee_id: str = "") -> dict:
        """对用户原始任务做结构化分析，输出类型、范围、约束和建议下一步。"""

        raw_request_value = _normalize_text(raw_request)
        if not raw_request_value:
            return {"error": "raw_request is required"}
        return _analyze_task_payload(
            raw_request_value,
            project_id=project_id,
            employee_id=employee_id,
        )

    @mcp.tool()
    def search_ids(
        keyword: str,
        project_id: str = "",
        employee_id: str = "",
        limit: int = 10,
    ) -> dict:
        """按关键词搜索项目、员工、规则 ID。

        适合先定位目标 ID，再继续调用 get_content / get_manual_content。
        当传 project_id 时，会优先在该项目范围内搜索员工和规则。
        """

        keyword_value = str(keyword or "").strip()
        project_id_value = str(project_id or "").strip()
        employee_id_value = str(employee_id or "").strip()
        try:
            limit_value = int(limit or 10)
        except (TypeError, ValueError):
            limit_value = 10
        limit_value = max(1, min(limit_value, 50))
        return {
            "keyword": keyword_value,
            "project_id": project_id_value,
            "employee_id": employee_id_value,
            "projects": _search_projects(keyword_value, limit_value),
            "employees": _search_employees(keyword_value, project_id_value, limit_value),
            "rules": _search_rules(
                keyword_value,
                project_id_value,
                employee_id_value,
                limit_value,
            ),
        }

    @mcp.tool()
    def resolve_relevant_context(
        task: str,
        project_id: str = "",
        employee_id: str = "",
        limit: int = 5,
    ) -> dict:
        """根据任务聚合最相关的项目成员、规则、工具和对象。"""

        task_value = _normalize_text(task)
        if not task_value:
            return {"error": "task is required"}
        return _resolve_relevant_context_payload(
            task_value,
            project_id=project_id,
            employee_id=employee_id,
            limit=limit,
        )

    @mcp.tool()
    def generate_execution_plan(
        task: str,
        project_id: str = "",
        employee_id: str = "",
        max_steps: int = 6,
    ) -> dict:
        """根据任务和项目上下文生成执行步骤骨架。"""

        task_value = _normalize_text(task)
        if not task_value:
            return {"error": "task is required"}
        return _generate_execution_plan_payload(
            task_value,
            project_id=project_id,
            employee_id=employee_id,
            max_steps=max_steps,
        )

    @mcp.tool()
    def classify_command_risk(
        command: str = "",
        tool_name: str = "",
        path: str = "",
        project_id: str = "",
        action: str = "",
    ) -> dict:
        """根据命令、工具名、路径和动作输出风险等级与原因。"""

        if not any([_normalize_text(command), _normalize_text(tool_name), _normalize_text(path), _normalize_text(action)]):
            return {"error": "Provide at least one of command, tool_name, path, action"}
        return _classify_risk_payload(
            command=command,
            tool_name=tool_name,
            path=path,
            project_id=project_id,
            action=action,
        )

    @mcp.tool()
    def check_workspace_scope(
        path: str,
        project_id: str = "",
        workspace_path: str = "",
        sandbox_mode: str = "",
    ) -> dict:
        """校验路径是否位于项目工作区内，并返回 sandbox 影响。"""

        path_value = _normalize_text(path)
        if not path_value:
            return {"error": "path is required"}
        return _path_scope_payload(
            path_value,
            project_id=project_id,
            workspace_path=workspace_path,
            sandbox_mode=sandbox_mode,
        )

    @mcp.tool()
    def resolve_execution_mode(
        project_id: str = "",
        tool_name: str = "",
        command: str = "",
        path: str = "",
        employee_id: str = "",
        prefer_connector: bool = True,
    ) -> dict:
        """判断当前执行更适合走 local connector、项目工具还是仅保留查询。"""

        if not any([_normalize_text(project_id), _normalize_text(tool_name), _normalize_text(command), _normalize_text(path)]):
            return {"error": "Provide at least one of project_id, tool_name, command, path"}
        return _resolve_execution_mode_payload(
            project_id=project_id,
            tool_name=tool_name,
            command=command,
            path=path,
            employee_id=employee_id,
            prefer_connector=prefer_connector,
        )

    @mcp.tool()
    def check_operation_policy(
        project_id: str = "",
        tool_name: str = "",
        command: str = "",
        path: str = "",
        employee_id: str = "",
        action: str = "",
        workspace_path: str = "",
        sandbox_mode: str = "",
    ) -> dict:
        """综合风险、工作区范围与项目设置，输出允许/需确认/拦截结论。"""

        if not any([_normalize_text(project_id), _normalize_text(tool_name), _normalize_text(command), _normalize_text(path)]):
            return {"error": "Provide at least one of project_id, tool_name, command, path"}
        return _check_operation_policy_payload(
            project_id=project_id,
            tool_name=tool_name,
            command=command,
            path=path,
            employee_id=employee_id,
            action=action,
            workspace_path=workspace_path,
            sandbox_mode=sandbox_mode,
        )

    @mcp.tool()
    def save_work_facts(
        project_id: str,
        facts: list[str] | None = None,
        content: str = "",
        employee_id: str = "",
        importance: float = 0.7,
        project_name: str = "",
        session_id: str = "",
        phase: str = "",
        step: str = "",
        status: str = "",
        goal: str = "",
        changed_files: list[str] | None = None,
        verification: list[str] | None = None,
        risks: list[str] | None = None,
        next_steps: list[str] | None = None,
    ) -> dict:
        """保存工作事实，供后续恢复、检查点摘要和长期任务续跑使用。"""

        fact_items = _parse_fact_lines(content=content, facts=facts)
        if not fact_items:
            return {"error": "Provide at least one fact in facts or content"}
        trajectory = _structured_trajectory_payload(
            kind="work-facts",
            session_id=session_id,
            phase=phase,
            step=step,
            status=status,
            goal=goal,
            changed_files=changed_files,
            verification=verification,
            risks=risks,
            next_steps=next_steps,
            facts=fact_items,
        )
        rendered = _render_structured_work_facts(
            fact_items=fact_items,
            trajectory=trajectory,
        )
        result = _save_project_memory_entries(
            project_id=project_id,
            employee_id=employee_id,
            content=rendered,
            memory_type=MemoryType.LEARNED_PATTERN,
            importance=importance,
            project_name=project_name,
            purpose_tags=_trajectory_purpose_tags(
                base_tags=("query-mcp", "work-facts", "phase3"),
                session_id=session_id,
                phase=phase,
                step=step,
            ),
        )
        if not result.get("error"):
            result["trajectory"] = trajectory
            result["work_session_event"] = _save_work_session_event_record(
                project_id=project_id,
                project_name=project_name,
                employee_id=employee_id,
                trajectory=trajectory,
            )
        return result

    @mcp.tool()
    def append_session_event(
        project_id: str,
        session_id: str,
        event_type: str,
        content: str,
        employee_id: str = "",
        importance: float = 0.55,
        project_name: str = "",
        phase: str = "",
        step: str = "",
        status: str = "",
        goal: str = "",
        changed_files: list[str] | None = None,
        verification: list[str] | None = None,
        risks: list[str] | None = None,
        next_steps: list[str] | None = None,
    ) -> dict:
        """向项目范围追加一条会话事件，用于恢复最近执行轨迹。"""

        session_id_value = _normalize_text(session_id)
        event_type_value = _normalize_text(event_type)
        content_value = _normalize_text(content)
        if not session_id_value:
            return {"error": "session_id is required"}
        if not event_type_value:
            return {"error": "event_type is required"}
        if not content_value:
            return {"error": "content is required"}
        trajectory = _structured_trajectory_payload(
            kind="session-event",
            session_id=session_id_value,
            event_type=event_type_value,
            phase=phase,
            step=step,
            status=status,
            goal=goal,
            changed_files=changed_files,
            verification=verification,
            risks=risks,
            next_steps=next_steps,
            content=content_value,
        )
        rendered = _render_structured_session_event(
            session_id=session_id_value,
            event_type=event_type_value,
            content=content_value,
            trajectory=trajectory,
        )
        result = _save_project_memory_entries(
            project_id=project_id,
            employee_id=employee_id,
            content=rendered,
            memory_type=MemoryType.KEY_EVENT,
            importance=importance,
            project_name=project_name,
            purpose_tags=_trajectory_purpose_tags(
                base_tags=("query-mcp", "session-event", event_type_value, "phase3"),
                session_id=session_id_value,
                phase=phase,
                step=step,
            ),
        )
        if not result.get("error"):
            result["trajectory"] = trajectory
            result["work_session_event"] = _save_work_session_event_record(
                project_id=project_id,
                project_name=project_name,
                employee_id=employee_id,
                trajectory=trajectory,
            )
        return result

    @mcp.tool()
    def resume_work_session(
        project_id: str,
        session_id: str = "",
        employee_id: str = "",
        query: str = "",
        limit: int = 10,
        project_name: str = "",
    ) -> dict:
        """恢复项目近期工作轨迹，支持按 session_id 或关键词缩小范围。"""

        project_id_value = _normalize_text(project_id)
        if not project_id_value:
            return {"error": "project_id is required"}
        structured_memories = _collect_work_session_records(
            project_id=project_id_value,
            employee_id=employee_id,
            session_id=session_id,
            query=query,
            limit=limit,
        )
        if not structured_memories:
            memories = _collect_project_memories(
                project_id=project_id_value,
                employee_id=employee_id,
                project_name=project_name,
                query=query,
                limit=limit,
            )
            structured_memories = _structured_session_items(memories)
        session_filtered = _filter_session_memories(structured_memories, session_id=session_id)
        selected = session_filtered if session_filtered else structured_memories
        selected = _structured_session_items(selected)
        project_name_value = _resolve_project_name(project_id_value, project_name)
        checkpoint = _build_checkpoint_view(selected)
        return {
            "project_id": project_id_value,
            "project_name": project_name_value,
            "session_id": _normalize_text(session_id),
            "query": _normalize_text(query),
            "items": selected,
            "total": len(selected),
            "phases": checkpoint["phases"],
            "steps": checkpoint["steps"],
            "changed_files": checkpoint["changed_files"],
            "verification": checkpoint["verification"],
            "risks": checkpoint["risks"],
            "next_steps": checkpoint["next_steps"],
            "latest_status": checkpoint["latest_status"],
            "timeline": checkpoint["timeline"],
            "checkpoint_summary": _checkpoint_summary_text(
                project_id_value,
                project_name_value,
                _normalize_text(session_id),
                selected,
            ),
        }

    @mcp.tool()
    def summarize_checkpoint(
        project_id: str,
        session_id: str = "",
        employee_id: str = "",
        limit: int = 12,
        project_name: str = "",
    ) -> dict:
        """根据已保存的工作事实和会话事件输出检查点摘要。"""

        project_id_value = _normalize_text(project_id)
        if not project_id_value:
            return {"error": "project_id is required"}
        structured_memories = _collect_work_session_records(
            project_id=project_id_value,
            employee_id=employee_id,
            session_id=session_id,
            query="",
            limit=limit,
        )
        if not structured_memories:
            memories = _collect_project_memories(
                project_id=project_id_value,
                employee_id=employee_id,
                project_name=project_name,
                query="",
                limit=limit,
            )
            structured_memories = _structured_session_items(memories)
        filtered = _filter_session_memories(structured_memories, session_id=session_id)
        selected = filtered if filtered else structured_memories
        selected = _structured_session_items(selected)
        fact_count, event_count = _legacy_fact_or_event_counts(selected)
        facts = [item for item in selected if _normalize_text(item.get("type")) == MemoryType.LEARNED_PATTERN.value]
        events = [item for item in selected if _normalize_text(item.get("type")) == MemoryType.KEY_EVENT.value]
        project_name_value = _resolve_project_name(project_id_value, project_name)
        checkpoint = _build_checkpoint_view(selected)
        return {
            "project_id": project_id_value,
            "project_name": project_name_value,
            "session_id": _normalize_text(session_id),
            "fact_count": fact_count,
            "event_count": event_count,
            "facts": facts[: max(1, min(len(facts), 6))],
            "events": events[: max(1, min(len(events), 6))],
            "phases": checkpoint["phases"],
            "steps": checkpoint["steps"],
            "changed_files": checkpoint["changed_files"],
            "verification": checkpoint["verification"],
            "risks": checkpoint["risks"],
            "next_steps": checkpoint["next_steps"],
            "latest_status": checkpoint["latest_status"],
            "timeline": checkpoint["timeline"],
            "summary": _checkpoint_summary_text(
                project_id_value,
                project_name_value,
                _normalize_text(session_id),
                selected,
            ),
        }

    @mcp.tool()
    def build_delivery_report(
        title: str = "",
        project_id: str = "",
        summary: str = "",
        completed_items: list[str] | None = None,
        changed_files: list[str] | None = None,
        verification: list[str] | None = None,
        risks: list[str] | None = None,
        next_steps: list[str] | None = None,
    ) -> dict:
        """生成结构化交付报告，供 CLI 直接输出或写入文档。"""

        return _build_delivery_report_payload(
            title=title,
            project_id=project_id,
            summary=summary,
            completed_items=completed_items,
            changed_files=changed_files,
            verification=verification,
            risks=risks,
            next_steps=next_steps,
        )

    @mcp.tool()
    def generate_release_note_entry(
        version: str = "",
        release_date: str = "",
        summary: str = "",
        key_changes: list[str] | None = None,
        project_id: str = "",
    ) -> dict:
        """生成一条可直接用于更新日志的版本条目。"""

        return _generate_release_note_entry_payload(
            version=version,
            release_date=release_date,
            summary=summary,
            key_changes=key_changes,
            project_id=project_id,
        )

    @mcp.tool()
    def get_manual_content(project_id: str = "", employee_id: str = "") -> dict:
        """直接获取项目或员工使用手册正文。"""

        project_id_value = str(project_id or "").strip()
        employee_id_value = str(employee_id or "").strip()
        if bool(project_id_value) == bool(employee_id_value):
            return {
                "error": "Provide exactly one of project_id or employee_id"
            }

        if employee_id_value:
            from routers.employees import _build_employee_manual_payload

            payload = _build_employee_manual_payload(employee_id_value)
            return {
                "entity_type": "employee",
                "entity_id": employee_id_value,
                "manual": payload.get("manual") or "",
                "manual_endpoint": f"/api/employees/{employee_id_value}/manual-template",
                "mcp_path": f"/mcp/employees/{employee_id_value}",
            }

        from routers.projects import _build_project_manual_template_payload

        payload = _build_project_manual_template_payload(project_id_value)
        return {
            "entity_type": "project",
            "entity_id": project_id_value,
            "manual": payload.get("manual") or "",
            "manual_endpoint": f"/api/projects/{project_id_value}/manual-template",
            "mcp_path": f"/mcp/projects/{project_id_value}",
        }

    @mcp.tool()
    def save_project_memory(
        project_id: str,
        content: str,
        employee_id: str = "",
        type: str = "project-context",
        importance: float = 0.6,
        project_name: str = "",
    ) -> dict:
        """通过统一入口按 project_id 写入项目对话或结论记忆。"""

        project_id_value = str(project_id or "").strip()
        employee_id_value = str(employee_id or "").strip()
        content_value = str(content or "").strip()
        if not project_id_value:
            return {"error": "project_id is required"}
        if not content_value:
            return {"error": "content is required"}

        project = project_store.get(project_id_value)
        if project is None:
            return {"error": f"Project {project_id_value} not found"}

        active_employee_ids = _active_project_employee_ids(project_id_value)
        if not active_employee_ids:
            return {"error": f"Project {project_id_value} has no active members"}
        if employee_id_value and employee_id_value not in active_employee_ids:
            return {"error": f"Employee {employee_id_value} is not an active project member"}

        memory_type_value = str(type or "").strip() or "project-context"
        try:
            memory_type = MemoryType(memory_type_value)
        except ValueError:
            return {"error": f"Invalid type: {memory_type_value}. Valid: {[item.value for item in MemoryType]}"}
        try:
            importance_value = float(importance)
        except (TypeError, ValueError):
            return {"error": "importance must be a number"}
        importance_value = max(0.0, min(1.0, importance_value))

        normalized_project_name = str(project_name or "").strip() or str(getattr(project, "name", "") or "").strip() or "default"
        target_employee_ids = [employee_id_value] if employee_id_value else active_employee_ids
        memory_ids: list[str] = []
        for target_employee_id in target_employee_ids:
            memory = Memory(
                id=memory_store.new_id(),
                employee_id=target_employee_id,
                type=memory_type,
                content=content_value,
                project_name=normalized_project_name,
                importance=importance_value,
                scope=MemoryScope.EMPLOYEE_PRIVATE,
                classification=Classification.INTERNAL,
                purpose_tags=("query-mcp", "manual-write", "project-id"),
            )
            memory_store.save(memory)
            memory_ids.append(memory.id)

        return {
            "status": "saved",
            "project_id": project_id_value,
            "project_name": normalized_project_name,
            "employee_ids": target_employee_ids,
            "memory_ids": memory_ids,
            "saved_count": len(memory_ids),
            "type": memory_type.value,
            "importance": importance_value,
            "project_mcp_path": f"/mcp/projects/{project_id_value}",
        }

    @mcp.tool()
    def list_project_members(project_id: str) -> dict:
        """通过统一入口列出项目成员详情。"""

        project_id_value = str(project_id or "").strip()
        if not project_id_value:
            return {"error": "project_id is required"}
        project = project_store.get(project_id_value)
        if project is None:
            return {"error": f"Project {project_id_value} not found"}
        items = list_project_member_profiles_runtime(
            project_id_value,
            include_disabled=False,
            include_missing=False,
            rule_limit=30,
        )
        return {
            "project_id": project_id_value,
            "project_name": str(getattr(project, "name", "") or ""),
            "items": items,
            "total": len(items),
            "project_mcp_path": f"/mcp/projects/{project_id_value}",
        }

    @mcp.tool()
    def get_project_runtime_context(project_id: str) -> dict:
        """通过统一入口返回项目运行时上下文摘要。"""

        project_id_value = str(project_id or "").strip()
        if not project_id_value:
            return {"error": "project_id is required"}
        project = project_store.get(project_id_value)
        if project is None:
            return {"error": f"Project {project_id_value} not found"}
        pairs = list_project_member_profiles_runtime(
            project_id_value,
            include_disabled=False,
            include_missing=False,
            rule_limit=30,
        )
        rules = query_project_rules_runtime(project_id_value)
        ui_rules = project_ui_rule_summary(project_id_value, limit=30)
        from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime

        proxy_tools = list_project_proxy_tools_runtime(project_id_value, "")
        return {
            "project_id": project_id_value,
            "project_name": str(getattr(project, "name", "") or ""),
            "member_count": len(pairs),
            "members": [
                str(item.get("employee_id") or "").strip()
                for item in pairs
                if str(item.get("employee_id") or "").strip()
            ],
            "scoped_proxy_tool_count": len(proxy_tools),
            "rule_count": len(rules),
            "ui_rule_count": len(ui_rules),
            "ui_rules": ui_rules,
            "project_mcp_path": f"/mcp/projects/{project_id_value}",
        }

    @mcp.tool()
    def list_project_proxy_tools(project_id: str, employee_id: str = "") -> dict:
        """通过统一入口列出项目成员技能代理工具。"""

        project_id_value = str(project_id or "").strip()
        employee_id_value = str(employee_id or "").strip()
        if not project_id_value:
            return {"error": "project_id is required"}
        project = project_store.get(project_id_value)
        if project is None:
            return {"error": f"Project {project_id_value} not found"}
        from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime

        items = list_project_proxy_tools_runtime(project_id_value, employee_id_value)
        return {
            "project_id": project_id_value,
            "employee_id": employee_id_value,
            "items": items,
            "total": len(items),
            "project_mcp_path": f"/mcp/projects/{project_id_value}",
        }

    @mcp.tool()
    def invoke_project_skill_tool(
        project_id: str,
        tool_name: str,
        employee_id: str = "",
        args: dict | None = None,
        args_json: str = "{}",
        timeout_sec: int = 30,
    ) -> dict:
        """通过统一入口代理调用项目成员技能工具。"""

        project_id_value = str(project_id or "").strip()
        tool_name_value = str(tool_name or "").strip()
        employee_id_value = str(employee_id or "").strip()
        if not project_id_value:
            return {"error": "project_id is required"}
        if not tool_name_value:
            return {"error": "tool_name is required"}
        project = project_store.get(project_id_value)
        if project is None:
            return {"error": f"Project {project_id_value} not found"}
        from services.dynamic_mcp_runtime import invoke_project_skill_tool_runtime

        result = invoke_project_skill_tool_runtime(
            project_id=project_id_value,
            tool_name=tool_name_value,
            employee_id=employee_id_value,
            args=args,
            args_json=args_json,
            timeout_sec=timeout_sec,
        )
        if isinstance(result, dict):
            return {
                "project_id": project_id_value,
                "project_name": str(getattr(project, "name", "") or ""),
                "project_mcp_path": f"/mcp/projects/{project_id_value}",
                **result,
            }
        return {
            "project_id": project_id_value,
            "project_name": str(getattr(project, "name", "") or ""),
            "project_mcp_path": f"/mcp/projects/{project_id_value}",
            "result": result,
        }

    @mcp.tool()
    def execute_project_collaboration(
        project_id: str,
        task: str,
        employee_ids: list[str] | None = None,
        max_employees: int = 3,
        max_tool_calls: int = 6,
        auto_execute: bool = True,
        include_external_tools: bool = True,
        timeout_sec: int = 30,
    ) -> dict:
        """通过统一入口代理调用项目多员工协作执行工具。"""

        project_id_value = str(project_id or "").strip()
        task_value = str(task or "").strip()
        if not project_id_value:
            return {"error": "project_id is required"}
        if not task_value:
            return {"error": "task is required"}
        project = project_store.get(project_id_value)
        if project is None:
            return {"error": f"Project {project_id_value} not found"}
        from services.dynamic_mcp_runtime import execute_project_collaboration_runtime

        result = execute_project_collaboration_runtime(
            project_id=project_id_value,
            task=task_value,
            employee_ids=employee_ids or [],
            max_employees=max_employees,
            max_tool_calls=max_tool_calls,
            auto_execute=auto_execute,
            include_external_tools=include_external_tools,
            timeout_sec=timeout_sec,
        )
        if isinstance(result, dict):
            return {
                "project_id": project_id_value,
                "project_name": str(getattr(project, "name", "") or ""),
                "project_mcp_path": f"/mcp/projects/{project_id_value}",
                **result,
            }
        return {
            "project_id": project_id_value,
            "project_name": str(getattr(project, "name", "") or ""),
            "project_mcp_path": f"/mcp/projects/{project_id_value}",
            "result": result,
        }

    return mcp
