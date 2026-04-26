"""Unified query MCP app builder."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import uuid

from mcp.server.fastmcp import FastMCP

from core.deps import employee_store, project_store, system_config_store, work_session_store
from services.query_mcp_project_state import (
    append_query_mcp_progress_outbox,
    bootstrap_query_mcp_local_workspace,
    delete_query_mcp_progress_outbox_entries,
    load_query_mcp_progress_outbox,
    load_query_mcp_requirement_record,
    mark_query_mcp_outbox_work_session_event,
    persist_query_mcp_local_state,
    upsert_query_mcp_requirement_record,
)
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
_LOCAL_PROGRESS_TERMINAL_STATUSES = {"done", "completed", "archived", "closed"}

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
    "start_project_workflow",
    "bind_project_context",
    "get_current_task_tree",
    "update_task_node_status",
    "complete_task_node_with_verification",
    "search_ids",
    "get_content",
    "get_manual_content",
    "analyze_task",
    "resolve_relevant_context",
    "generate_execution_plan",
    "save_project_memory",
    "list_project_members",
    "get_project_runtime_context",
    "resolve_project_experience_rules",
    "list_project_proxy_tools",
    "invoke_project_skill_tool",
    "execute_project_collaboration",
    "classify_command_risk",
    "check_workspace_scope",
    "resolve_execution_mode",
    "check_operation_policy",
    "start_work_session",
    "save_work_facts",
    "append_session_event",
    "resume_work_session",
    "summarize_checkpoint",
    "list_recent_project_requirements",
    "get_requirement_history",
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


def _normalize_text(value: object, limit: int | None = None) -> str:
    text = str(value or "").strip()
    if limit is None:
        return text
    try:
        safe_limit = int(limit)
    except (TypeError, ValueError):
        return text
    if safe_limit <= 0:
        return ""
    return text[:safe_limit]


def _normalize_text_lower(value: object) -> str:
    return _normalize_text(value).lower()


def _parse_history_datetime(value: object, *, end_of_day: bool = False) -> datetime | None:
    text = _normalize_text(value, 80)
    if not text:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            parsed = datetime.fromisoformat(text)
            parsed = parsed.replace(
                hour=23 if end_of_day else 0,
                minute=59 if end_of_day else 0,
                second=59 if end_of_day else 0,
                microsecond=999999 if end_of_day else 0,
            )
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _history_datetime_or_min(value: object) -> datetime:
    parsed = _parse_history_datetime(value)
    if parsed is not None:
        return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def _project_memory_candidate_items(employee_id: str, *, limit: int = 200) -> list[object]:
    recent = getattr(memory_store, "recent", None)
    list_by_employee = getattr(memory_store, "list_by_employee", None)
    if callable(recent):
        try:
            return list(recent(employee_id, limit) or [])
        except Exception:
            return []
    if callable(list_by_employee):
        try:
            return list(list_by_employee(employee_id) or [])[:limit]
        except Exception:
            return []
    return []


def _project_memory_fingerprint_tag(*parts: object) -> str:
    normalized_parts = [
        re.sub(r"\s+", " ", _normalize_text(part, 4000))
        for part in parts
        if _normalize_text(part, 4000)
    ]
    if not normalized_parts:
        return ""
    digest = hashlib.sha1("|".join(normalized_parts).encode("utf-8")).hexdigest()[:20]
    return f"fp:{digest}"


def _append_memory_project_binding(content: str, project_id: str, project_name: str = "") -> str:
    content_value = _normalize_text(content, 4000)
    project_id_value = _normalize_text(project_id, 120)
    project_name_value = _normalize_text(project_name, 160)
    if not content_value:
        return content_value
    lines = [content_value]
    if project_id_value and not re.search(r"(?:^|\n)\[项目ID\]\s*[^\n]+", content_value):
        lines.append(f"[项目ID] {project_id_value}")
    if project_name_value and not re.search(r"(?:^|\n)\[项目名称\]\s*[^\n]+", content_value):
        lines.append(f"[项目名称] {project_name_value}")
    return _normalize_text("\n".join(lines), 4000)


def _strip_memory_project_binding(content: str) -> str:
    content_value = _normalize_text(content, 4000)
    if not content_value:
        return ""
    cleaned_lines = [
        line
        for line in content_value.splitlines()
        if not re.match(r"^\[(?:项目ID|项目名称)\]\s*", line.strip())
    ]
    return _normalize_text("\n".join(cleaned_lines), 4000)


def _memory_matches_project_scope(
    memory: object,
    *,
    project_id: str,
    project_name: str,
) -> bool:
    project_id_value = _normalize_text(project_id, 120)
    project_name_value = _normalize_text(project_name, 160)
    purpose_tags = {
        _normalize_text(item, 120)
        for item in (getattr(memory, "purpose_tags", ()) or [])
        if _normalize_text(item, 120)
    }
    tagged_project_id = next(
        (
            tag.split("project-id:", 1)[1]
            for tag in purpose_tags
            if tag.startswith("project-id:")
        ),
        "",
    )
    content_value = _normalize_text(getattr(memory, "content", ""), 4000)
    bound_project_id = ""
    matched = re.search(r"(?:^|\n)\[项目ID\]\s*([^\n]+)", content_value)
    if matched:
        bound_project_id = _normalize_text(matched.group(1), 120)
    if bound_project_id or tagged_project_id:
        return (bound_project_id or tagged_project_id) == project_id_value
    return _normalize_text(getattr(memory, "project_name", ""), 160) == project_name_value


def _project_memory_duplicate_exists(
    *,
    project_id: str,
    employee_id: str,
    project_name: str,
    content: str,
    purpose_tags: tuple[str, ...],
    fingerprint_tag: str,
) -> bool:
    normalized_project_id = _normalize_text(project_id, 120)
    normalized_project_name = _normalize_text(project_name, 160)
    content_value = _normalize_text(content, 4000)
    required_tags = {
        _normalize_text(tag, 120)
        for tag in purpose_tags
        if _normalize_text(tag, 120)
        and not _normalize_text(tag, 120).startswith(("chat-session:", "task-tree-session:", "fp:"))
    }
    for memory in _project_memory_candidate_items(employee_id):
        if not _memory_matches_project_scope(
            memory,
            project_id=normalized_project_id,
            project_name=normalized_project_name,
        ):
            continue
        tags = {
            _normalize_text(item, 120)
            for item in (getattr(memory, "purpose_tags", ()) or [])
            if _normalize_text(item, 120)
        }
        if fingerprint_tag and fingerprint_tag in tags:
            return True
        current_content = _normalize_text(getattr(memory, "content", ""), 4000)
        if content_value != current_content and _strip_memory_project_binding(content_value) != _strip_memory_project_binding(current_content):
            continue
        if required_tags and not required_tags.issubset(tags):
            continue
        return True
    return False


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


def _resolve_project_experience_context_payload(
    project_id: str,
    task: str,
    *,
    limit: int,
) -> dict:
    project_id_value = _normalize_text(project_id)
    task_value = _normalize_text(task)
    default_payload = {
        "experience_rule_count": 0,
        "matched_experience_rule_count": 0,
        "matched_experience_rules": [],
        "experience_prompt_blocks": [],
        "experience_context": "",
    }
    if not project_id_value or not task_value:
        return default_payload
    project = project_store.get(project_id_value)
    if project is None:
        return default_payload
    from routers.projects import _resolve_project_experience_rules_payload

    experience_payload = _resolve_project_experience_rules_payload(
        project,
        task_value,
        limit=limit,
    )
    items = experience_payload.get("items") or []
    prompt_blocks = experience_payload.get("prompt_blocks") or []
    return {
        "experience_rule_count": int(experience_payload.get("experience_rule_count") or 0),
        "matched_experience_rule_count": len(items),
        "matched_experience_rules": items,
        "experience_prompt_blocks": prompt_blocks,
        "experience_context": _normalize_text(experience_payload.get("assembled_context"), 12000),
    }


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
        payload.update(
            _resolve_project_experience_context_payload(
                project_id_value,
                task_value,
                limit=limit_value,
            )
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
            payload = {
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
            payload.update(
                _resolve_project_experience_context_payload(
                    project_id_value,
                    task_value,
                    limit=min(step_limit, 5),
                )
            )
            return payload
    generic_steps = _generic_execution_steps(task_value, project_id=project_id_value)
    payload = {
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
    if project_id_value:
        payload.update(
            _resolve_project_experience_context_payload(
                project_id_value,
                task_value,
                limit=min(step_limit, 5),
            )
        )
    return payload


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


def _query_mcp_clarity_confirm_threshold() -> int:
    try:
        return max(
            1,
            min(
                5,
                int(
                    getattr(
                        system_config_store.get_global(),
                        "query_mcp_clarity_confirm_threshold",
                        3,
                    )
                    or 3
                ),
            ),
        )
    except Exception:
        return 3


def _query_mcp_clarity_instruction_lines() -> tuple[str, str, str, str]:
    threshold = _query_mcp_clarity_confirm_threshold()
    threshold_text = f"当前全局清晰度确认阈值为 {threshold}/5"
    return (
        f"{threshold_text}；处理前先按 1-5 分估计用户需求清晰度。",
        f"若目标、对象、范围和预期结果足够清晰，且清晰度分数 >= {threshold}，直接处理，不主动要求确认计划。",
        f"若清晰度分数 < {threshold}、需求表述模糊、对象或范围不明确，或存在两种及以上合理理解，先输出你的理解、计划摘要和可能误解点，再请求用户确认后再执行。",
        "同一轮中用户已确认当前理解和计划后，后续不要重复确认，除非用户目标、范围或约束发生变化；查询型、客服型问题不要默认升级成计划审批流程。",
    )


def _render_query_prompt_template(template: str, variables: dict[str, str]) -> str:
    rendered = str(template or "").strip()
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value or ""))
    return rendered.strip()


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
    if employee_id_value:
        target_employee_ids = [employee_id_value]
        memory_scope = MemoryScope.EMPLOYEE_PRIVATE
    else:
        # Project-level memory should be saved once as a shared entry instead of fan-out
        # duplicates under every active member.
        target_employee_ids = [active_employee_ids[0]]
        memory_scope = MemoryScope.TEAM_SHARED
    content_value = _append_memory_project_binding(
        content_value,
        project_id_value,
        normalized_project_name,
    )
    memory_ids: list[str] = []
    skipped_employee_ids: list[str] = []
    importance_value = max(0.0, min(float(importance), 1.0))
    fingerprint_tag = _project_memory_fingerprint_tag(
        normalized_project_name,
        memory_type.value,
        "|".join(purpose_tags),
        content_value,
    )
    purpose_tags_value = tuple(
        dict.fromkeys(
            [
                *purpose_tags,
                f"project-id:{project_id_value}",
                *([fingerprint_tag] if fingerprint_tag else []),
            ]
        )
    )
    for target_employee_id in target_employee_ids:
        if _project_memory_duplicate_exists(
            project_id=project_id_value,
            employee_id=target_employee_id,
            project_name=normalized_project_name,
            content=content_value,
            purpose_tags=purpose_tags_value,
            fingerprint_tag=fingerprint_tag,
        ):
            skipped_employee_ids.append(target_employee_id)
            continue
        memory = Memory(
            id=memory_store.new_id(),
            employee_id=target_employee_id,
            type=memory_type,
            content=content_value,
            project_name=normalized_project_name,
            importance=importance_value,
            scope=memory_scope,
            classification=Classification.INTERNAL,
            purpose_tags=purpose_tags_value,
        )
        memory_store.save(memory)
        memory_ids.append(memory.id)
    return {
        "status": "saved" if memory_ids else "skipped",
        "project_id": project_id_value,
        "project_name": normalized_project_name,
        "employee_ids": target_employee_ids,
        "memory_ids": memory_ids,
        "saved_count": len(memory_ids),
        "skipped_employee_ids": skipped_employee_ids,
        "duplicate_skipped": bool(skipped_employee_ids) and not bool(memory_ids),
        "type": memory_type.value,
        "scope": memory_scope.value,
        "importance": importance_value,
        "project_mcp_path": f"/mcp/projects/{project_id_value}",
    }


def _iter_text_values(values: list[str] | str | None = None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    if isinstance(values, (list, tuple, set)):
        return [str(item or "") for item in values]
    return [str(values or "")]


def _parse_fact_lines(content: str = "", facts: list[str] | str | None = None) -> list[str]:
    items: list[str] = []
    for item in _iter_text_values(facts):
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
    task_tree_session_id: str = "",
    task_tree_chat_session_id: str = "",
    task_node_id: str = "",
    task_node_title: str = "",
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
        "task_tree_session_id": _normalize_text(task_tree_session_id),
        "task_tree_chat_session_id": _normalize_text(task_tree_chat_session_id),
        "task_node_id": _normalize_text(task_node_id),
        "task_node_title": _normalize_text(task_node_title),
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


def _generate_work_session_id(*, project_id: str, employee_id: str = "") -> str:
    project_token = re.sub(r"[^a-zA-Z0-9_-]+", "-", _normalize_text(project_id)).strip("-")[:40] or "project"
    owner_source = _normalize_text(employee_id) or "team"
    owner_token = re.sub(r"[^a-zA-Z0-9_-]+", "-", owner_source).strip("-")[:40] or "team"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:4]
    return f"ws_{project_token}_{owner_token}_{timestamp}_{suffix}"


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
            task_tree_session_id=_normalize_text(trajectory.get("task_tree_session_id")),
            task_tree_chat_session_id=_normalize_text(trajectory.get("task_tree_chat_session_id")),
            task_node_id=_normalize_text(trajectory.get("task_node_id")),
            task_node_title=_normalize_text(trajectory.get("task_node_title")),
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


def _local_progress_entry_to_item(entry: dict[str, object]) -> dict[str, object]:
    trajectory = (
        entry.get("trajectory")
        if isinstance(entry.get("trajectory"), dict)
        else {}
    )
    memory_type = _normalize_text(entry.get("memory_type"))
    return {
        "id": _normalize_text(entry.get("event_id")),
        "employee_id": _normalize_text(entry.get("employee_id")),
        "project_id": _normalize_text(entry.get("project_id")),
        "project_name": _normalize_text(entry.get("project_name")),
        "type": memory_type or MemoryType.KEY_EVENT.value,
        "task_tree_session_id": _normalize_text(trajectory.get("task_tree_session_id")),
        "task_tree_chat_session_id": _normalize_text(trajectory.get("task_tree_chat_session_id")),
        "task_node_id": _normalize_text(trajectory.get("task_node_id")),
        "task_node_title": _normalize_text(trajectory.get("task_node_title")),
        "content": _normalize_text(entry.get("content"), 8000),
        "created_at": _normalize_text(entry.get("created_at")),
        "updated_at": _normalize_text(entry.get("updated_at")),
        "trajectory": _structured_trajectory_payload(
            kind=_normalize_text(trajectory.get("kind")),
            session_id=_normalize_text(trajectory.get("session_id")),
            task_tree_session_id=_normalize_text(trajectory.get("task_tree_session_id")),
            task_tree_chat_session_id=_normalize_text(trajectory.get("task_tree_chat_session_id")),
            task_node_id=_normalize_text(trajectory.get("task_node_id")),
            task_node_title=_normalize_text(trajectory.get("task_node_title")),
            event_type=_normalize_text(trajectory.get("event_type")),
            phase=_normalize_text(trajectory.get("phase")),
            step=_normalize_text(trajectory.get("step")),
            status=_normalize_text(trajectory.get("status")),
            goal=_normalize_text(trajectory.get("goal")),
            changed_files=_coerce_list_text(trajectory.get("changed_files")),
            verification=_coerce_list_text(trajectory.get("verification")),
            risks=_coerce_list_text(trajectory.get("risks")),
            next_steps=_coerce_list_text(trajectory.get("next_steps")),
            facts=_coerce_list_text(trajectory.get("facts")),
            content=_normalize_text(trajectory.get("content")),
        ),
    }


def _collect_local_progress_records(
    *,
    project_id: str,
    employee_id: str = "",
    session_id: str = "",
    chat_session_id: str = "",
    limit: int = 200,
) -> list[dict]:
    try:
        entries = load_query_mcp_progress_outbox(
            _normalize_text(project_id),
            chat_session_id=_normalize_text(chat_session_id),
            session_id=_normalize_text(session_id),
            limit=max(1, min(int(limit or 200), 500)),
        )
    except Exception:  # pragma: no cover - defensive fallback
        return []
    employee_id_value = _normalize_text(employee_id)
    items: list[dict] = []
    for entry in entries:
        if employee_id_value and _normalize_text(entry.get("employee_id")) not in {"", employee_id_value}:
            continue
        items.append(_local_progress_entry_to_item(entry))
    return items


def _merge_progress_records(*record_groups: list[dict], limit: int = 200) -> list[dict]:
    merged: list[dict] = []
    seen_ids: set[str] = set()
    for group in record_groups:
        for item in group or []:
            item_id = _normalize_text(item.get("id"), 120)
            if item_id and item_id in seen_ids:
                continue
            if item_id:
                seen_ids.add(item_id)
            merged.append(item)
    merged.sort(
        key=lambda item: (
            _item_modified_at(item),
            _normalize_text(item.get("id"), 120),
        ),
        reverse=True,
    )
    try:
        limit_value = max(1, min(int(limit or 200), 500))
    except (TypeError, ValueError):
        limit_value = 200
    return merged[:limit_value]


def _should_flush_local_progress(status: str) -> bool:
    return _normalize_text(status, 80).lower() in _LOCAL_PROGRESS_TERMINAL_STATUSES


def _sync_local_progress_entry(entry: dict[str, object]) -> dict[str, object]:
    project_id_value = _normalize_text(entry.get("project_id"))
    if not project_id_value:
        return {"error": "project_id is required"}
    content_value = _normalize_text(entry.get("content"), 8000)
    trajectory = entry.get("trajectory") if isinstance(entry.get("trajectory"), dict) else {}
    memory_type_value = _normalize_text(entry.get("memory_type"))
    memory_type = (
        MemoryType.LEARNED_PATTERN
        if memory_type_value == MemoryType.LEARNED_PATTERN.value
        else MemoryType.KEY_EVENT
    )
    purpose_tags = tuple(_coerce_list_text(entry.get("purpose_tags")))
    memory_result = _save_project_memory_entries(
        project_id=project_id_value,
        employee_id=_normalize_text(entry.get("employee_id")),
        content=content_value,
        memory_type=memory_type,
        importance=float(entry.get("importance") or 0.6),
        project_name=_normalize_text(entry.get("project_name")),
        purpose_tags=purpose_tags or ("query-mcp", "local-outbox"),
    )
    if memory_result.get("error"):
        return {"error": memory_result.get("error"), "memory_result": memory_result}
    work_session_event_id = _normalize_text(entry.get("work_session_event_id"))
    if work_session_event_id:
        work_session_event = {"status": "saved", "event_id": work_session_event_id}
    else:
        work_session_event = _save_work_session_event_record(
            project_id=project_id_value,
            project_name=_normalize_text(entry.get("project_name")),
            employee_id=_normalize_text(entry.get("employee_id")),
            trajectory=trajectory,
        )
        if work_session_event.get("status") == "error":
            return {"error": work_session_event.get("detail") or "sync_work_session_event_failed", "memory_result": memory_result}
    return {
        "memory_result": memory_result,
        "work_session_event": work_session_event,
        "task_tree": None,
    }


def _flush_local_progress_outbox(
    *,
    project_id: str,
    chat_session_id: str,
) -> dict[str, object]:
    entries = load_query_mcp_progress_outbox(
        _normalize_text(project_id),
        chat_session_id=_normalize_text(chat_session_id),
        limit=500,
        oldest_first=True,
    )
    if not entries:
        return {
            "status": "empty",
            "synced_count": 0,
            "memory_ids": [],
            "saved_count": 0,
            "work_session_event": {"status": "skipped", "reason": "outbox_empty"},
            "task_tree": None,
        }
    synced_event_ids: list[str] = []
    memory_ids: list[str] = []
    skipped_employee_ids: list[str] = []
    last_work_session_event: dict[str, object] = {"status": "skipped", "reason": "not_synced"}
    task_tree_payload = None
    sync_error = ""
    for entry in entries:
        synced = _sync_local_progress_entry(entry)
        if synced.get("error"):
            sync_error = _normalize_text(synced.get("error"), 400)
            break
        memory_result = synced.get("memory_result") if isinstance(synced.get("memory_result"), dict) else {}
        memory_ids.extend(_coerce_list_text(memory_result.get("memory_ids")))
        skipped_employee_ids.extend(_coerce_list_text(memory_result.get("skipped_employee_ids")))
        last_work_session_event = synced.get("work_session_event") if isinstance(synced.get("work_session_event"), dict) else last_work_session_event
        if synced.get("task_tree") is not None:
            task_tree_payload = synced.get("task_tree")
        event_id = _normalize_text(entry.get("event_id"), 80)
        if event_id:
            synced_event_ids.append(event_id)
    if synced_event_ids:
        delete_query_mcp_progress_outbox_entries(
            _normalize_text(project_id),
            chat_session_id=_normalize_text(chat_session_id),
            event_ids=synced_event_ids,
        )
    status_value = "synced" if not sync_error else "partial"
    if not synced_event_ids and sync_error:
        status_value = "error"
    return {
        "status": status_value,
        "synced_count": len(synced_event_ids),
        "memory_ids": memory_ids,
        "saved_count": len(memory_ids),
        "skipped_employee_ids": skipped_employee_ids,
        "work_session_event": last_work_session_event,
        "task_tree": task_tree_payload,
        "error": sync_error,
    }


def _work_session_event_to_item(event: WorkSessionEvent) -> dict:
    memory_type = (
        MemoryType.LEARNED_PATTERN.value
        if _normalize_text(event.source_kind) == "work-facts"
        else MemoryType.KEY_EVENT.value
    )
    trajectory = {
        "kind": _normalize_text(event.source_kind),
        "session_id": _normalize_text(event.session_id),
        "task_tree_session_id": _normalize_text(event.task_tree_session_id),
        "task_tree_chat_session_id": _normalize_text(event.task_tree_chat_session_id),
        "task_node_id": _normalize_text(event.task_node_id),
        "task_node_title": _normalize_text(event.task_node_title),
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
        "project_id": _normalize_text(event.project_id),
        "project_name": _normalize_text(event.project_name),
        "type": memory_type,
        "task_tree_session_id": _normalize_text(event.task_tree_session_id),
        "task_tree_chat_session_id": _normalize_text(event.task_tree_chat_session_id),
        "task_node_id": _normalize_text(event.task_node_id),
        "task_node_title": _normalize_text(event.task_node_title),
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
            if not _memory_matches_project_scope(
                mem,
                project_id=project_id_value,
                project_name=normalized_project_name,
            ):
                continue
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


def _item_modified_at(item: dict) -> str:
    updated_at = _normalize_text(item.get("updated_at"))
    if updated_at:
        return updated_at
    return _normalize_text(item.get("created_at"))


def _item_history_summary(item: dict) -> str:
    trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else {}
    summary = _normalize_text(trajectory.get("content"))
    if not summary:
        facts = _coerce_list_text(trajectory.get("facts"))
        if facts:
            summary = "；".join(facts[:3])
    if not summary:
        summary = _normalize_text(item.get("content")).replace("\n", " | ")
    return summary[:240]


def _extract_requirement_title_from_content(content: object) -> str:
    content_value = _normalize_text(content, 4000)
    if not content_value:
        return ""
    for raw_line in content_value.splitlines():
        line = re.sub(r"^[\-\*\d\.\)\s]+", "", raw_line.strip())
        if not line:
            continue
        heading_match = re.match(r"^#{1,6}\s*(.+)$", line)
        if heading_match:
            return _normalize_text(heading_match.group(1), 200)
        label_match = re.match(
            r"^(?:问题原文|问题摘要|问题|需求|标题|目标|goal|root_goal)\s*[:：]\s*(.+)$",
            line,
            re.IGNORECASE,
        )
        if label_match:
            return _normalize_text(label_match.group(1), 200)
    for raw_line in content_value.splitlines():
        line = re.sub(r"^[\-\*\d\.\)\s]+", "", raw_line.strip())
        if not line or line.startswith("[") or line.startswith("```"):
            continue
        if len(line) < 4:
            continue
        return _normalize_text(line, 200)
    return _normalize_text(content_value.replace("\n", " | "), 200)


def _session_requirement_title_lookup(items: list[dict]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in items:
        trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else {}
        session_id = _normalize_text(trajectory.get("session_id"))
        goal = _normalize_text(trajectory.get("goal"), 200)
        if session_id and goal and session_id not in lookup:
            lookup[session_id] = goal
    return lookup


def _derive_requirement_title(item: dict, *, session_title_lookup: dict[str, str] | None = None) -> str:
    trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else {}
    goal = _normalize_text(trajectory.get("goal"), 200)
    if goal:
        return goal
    session_id = _normalize_text(trajectory.get("session_id"))
    if session_id and isinstance(session_title_lookup, dict):
        session_title = _normalize_text(session_title_lookup.get(session_id), 200)
        if session_title:
            return session_title
    return _extract_requirement_title_from_content(item.get("content"))


def _normalize_requirement_key(title: str, *, item: dict) -> str:
    normalized_title = re.sub(
        r"[\s`\"'“”‘’·•，,。！？!?:：;；()\[\]{}<>《》]+",
        " ",
        _normalize_text_lower(title),
    ).strip()
    if normalized_title:
        return normalized_title
    trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else {}
    session_id = _normalize_text(trajectory.get("session_id"))
    if session_id:
        return f"session:{session_id}"
    memory_id = _normalize_text(item.get("id"))
    if memory_id:
        return f"memory:{memory_id}"
    return f"requirement:{uuid.uuid4().hex[:12]}"


def _filter_requirement_history_items(
    items: list[dict],
    *,
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
) -> tuple[list[dict], str]:
    keyword_value = _normalize_text(keyword)
    date_from_value = _normalize_text(date_from)
    date_to_value = _normalize_text(date_to)
    start_at = _parse_history_datetime(date_from_value, end_of_day=False) if date_from_value else None
    end_at = _parse_history_datetime(date_to_value, end_of_day=True) if date_to_value else None
    if date_from_value and start_at is None:
        return [], "date_from must be an ISO date or datetime"
    if date_to_value and end_at is None:
        return [], "date_to must be an ISO date or datetime"
    if start_at is not None and end_at is not None and start_at > end_at:
        return [], "date_from must be earlier than or equal to date_to"

    session_title_lookup = _session_requirement_title_lookup(items)
    filtered: list[dict] = []
    for item in items:
        modified_at = _parse_history_datetime(_item_modified_at(item))
        if start_at is not None and (modified_at is None or modified_at < start_at):
            continue
        if end_at is not None and (modified_at is None or modified_at > end_at):
            continue
        if keyword_value:
            trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else {}
            title = _derive_requirement_title(item, session_title_lookup=session_title_lookup)
            if not _keyword_match(
                keyword_value,
                title,
                item.get("content"),
                trajectory.get("goal"),
                trajectory.get("content"),
                trajectory.get("facts"),
                trajectory.get("changed_files"),
                trajectory.get("verification"),
            ):
                continue
        filtered.append(item)
    filtered.sort(
        key=lambda current: (
            _history_datetime_or_min(_item_modified_at(current)),
            _normalize_text(current.get("id")),
        ),
        reverse=True,
    )
    return filtered, ""


def _build_requirement_history_entry(
    item: dict,
    *,
    title: str,
) -> dict:
    trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else {}
    return {
        "id": _normalize_text(item.get("id")),
        "requirement_title": _normalize_text(title, 200),
        "modified_at": _item_modified_at(item),
        "created_at": _normalize_text(item.get("created_at")),
        "updated_at": _normalize_text(item.get("updated_at")),
        "summary": _item_history_summary(item),
        "source_kind": _normalize_text(trajectory.get("kind")) or "project-memory",
        "event_type": _normalize_text(trajectory.get("event_type")),
        "status": _normalize_text(trajectory.get("status")),
        "phase": _normalize_text(trajectory.get("phase")),
        "step": _normalize_text(trajectory.get("step")),
        "session_id": _normalize_text(trajectory.get("session_id")),
        "task_tree_session_id": _normalize_text(trajectory.get("task_tree_session_id")),
        "task_tree_chat_session_id": _normalize_text(trajectory.get("task_tree_chat_session_id")),
        "task_node_id": _normalize_text(trajectory.get("task_node_id")),
        "task_node_title": _normalize_text(trajectory.get("task_node_title")) or _normalize_text(item.get("task_node_title")),
        "changed_files": _coerce_list_text(trajectory.get("changed_files")),
        "verification": _coerce_list_text(trajectory.get("verification")),
        "risks": _coerce_list_text(trajectory.get("risks")),
        "next_steps": _coerce_list_text(trajectory.get("next_steps")),
    }


def _group_requirement_history(
    items: list[dict],
    *,
    limit: int,
    history_limit: int = 20,
) -> list[dict]:
    session_title_lookup = _session_requirement_title_lookup(items)
    grouped: dict[str, dict] = {}
    for item in items:
        title = _derive_requirement_title(item, session_title_lookup=session_title_lookup)
        key = _normalize_requirement_key(title, item=item)
        history_item = _build_requirement_history_entry(item, title=title)
        modified_at = _history_datetime_or_min(history_item.get("modified_at"))
        created_at = _history_datetime_or_min(history_item.get("created_at"))
        requirement = grouped.get(key)
        if requirement is None:
            requirement = {
                "requirement_key": key,
                "requirement_title": _normalize_text(title, 200),
                "first_seen_at": history_item.get("created_at") or history_item.get("modified_at") or "",
                "latest_modified_at": history_item.get("modified_at") or history_item.get("created_at") or "",
                "latest_status": _normalize_text(history_item.get("status")),
                "latest_summary": _normalize_text(history_item.get("summary"), 240),
                "session_ids": [],
                "task_tree_session_ids": [],
                "task_tree_chat_session_ids": [],
                "employee_ids": [],
                "phases": [],
                "steps": [],
                "changed_files": [],
                "verification": [],
                "risks": [],
                "next_steps": [],
                "source_kinds": [],
                "event_types": [],
                "history_count": 0,
                "history": [],
                "_latest_dt": modified_at,
                "_first_seen_dt": created_at,
            }
            grouped[key] = requirement
        requirement["history_count"] += 1
        if modified_at > requirement["_latest_dt"]:
            requirement["_latest_dt"] = modified_at
            requirement["latest_modified_at"] = history_item.get("modified_at") or history_item.get("created_at") or ""
            requirement["latest_status"] = _normalize_text(history_item.get("status"))
            requirement["latest_summary"] = _normalize_text(history_item.get("summary"), 240)
        if created_at < requirement["_first_seen_dt"]:
            requirement["_first_seen_dt"] = created_at
            requirement["first_seen_at"] = history_item.get("created_at") or history_item.get("modified_at") or ""
        for field in ("session_ids", "task_tree_session_ids", "task_tree_chat_session_ids"):
            value = _normalize_text(history_item.get(field) or "")
            if value and value not in requirement[field]:
                requirement[field].append(value)
        employee_id = _normalize_text(item.get("employee_id"))
        if employee_id and employee_id not in requirement["employee_ids"]:
            requirement["employee_ids"].append(employee_id)
        for field, source in (
            ("phases", _normalize_text(history_item.get("phase"))),
            ("steps", _normalize_text(history_item.get("step"))),
            ("source_kinds", _normalize_text(history_item.get("source_kind"))),
            ("event_types", _normalize_text(history_item.get("event_type"))),
        ):
            if source and source not in requirement[field]:
                requirement[field].append(source)
        for field in ("changed_files", "verification", "risks", "next_steps"):
            for value in history_item.get(field) or []:
                normalized_value = _normalize_text(value)
                if normalized_value and normalized_value not in requirement[field]:
                    requirement[field].append(normalized_value)
        if len(requirement["history"]) < max(1, min(int(history_limit or 20), 50)):
            requirement["history"].append(history_item)

    requirements = list(grouped.values())
    requirements.sort(key=lambda item: item["_latest_dt"], reverse=True)
    normalized_limit = max(1, min(int(limit or 10), 50))
    sliced = requirements[:normalized_limit]
    for item in sliced:
        item.pop("_latest_dt", None)
        item.pop("_first_seen_dt", None)
    return sliced


def _collect_requirement_history_items(
    *,
    project_id: str,
    employee_id: str = "",
    project_name: str = "",
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 10,
) -> tuple[list[dict], str, str]:
    try:
        fetch_limit = max(50, min(int(limit or 10) * 25, 500))
    except (TypeError, ValueError):
        fetch_limit = 250
    work_items = _structured_session_items(
        _collect_work_session_records(
            project_id=project_id,
            employee_id=employee_id,
            query=keyword,
            limit=fetch_limit,
        )
    )
    filtered_work_items, error = _filter_requirement_history_items(
        work_items,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )
    if error:
        return [], "", error
    if filtered_work_items:
        return filtered_work_items, "work-session", ""

    memory_items = _structured_session_items(
        _collect_project_memories(
            project_id=project_id,
            employee_id=employee_id,
            project_name=project_name,
            query=keyword,
            limit=min(fetch_limit, 50),
        )
    )
    filtered_memory_items, error = _filter_requirement_history_items(
        memory_items,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )
    if error:
        return [], "", error
    if filtered_memory_items or not work_items:
        return filtered_memory_items, "project-memory", ""
    return [], "work-session", ""


def _legacy_fact_or_event_counts(memories: list[dict]) -> tuple[int, int]:
    facts = [item for item in memories if _normalize_text(item.get("type")) == MemoryType.LEARNED_PATTERN.value]
    events = [item for item in memories if _normalize_text(item.get("type")) == MemoryType.KEY_EVENT.value]
    return len(facts), len(events)


def build_query_client_profile_text(client_name: str) -> str:
    config = system_config_store.get_global()
    template = str(
        getattr(config, "query_mcp_client_profile_template", "") or ""
    ).strip()
    normalized = _normalize_text_lower(client_name)
    title = client_name
    (
        clarity_threshold_line,
        clarity_direct_line,
        clarity_confirm_line,
        clarity_repeat_line,
    ) = _query_mcp_clarity_instruction_lines()
    if normalized == "claude-code":
        title = "Claude Code"
        focus = [
            "- 定位: 适合需要较强代码修改、命令执行和长任务续跑的开发型 CLI。",
            "- 推荐链路: query://usage-guide -> analyze_task -> search_ids/get_manual_content -> resolve_relevant_context -> generate_execution_plan -> check_operation_policy -> start_work_session。",
            "- 接入约束: `description` 只用于说明，不参与项目绑定；要续接任务树，优先让 URL 带上 `project_id` 和 `chat_session_id`，缺失时首轮调用 `bind_project_context(...)`。",
            "- 接入约束: 若 direct CLI fallback 先生成了临时 `query-cli.*` 会话，后续再用显式 `cli.*` 会话执行 `bind_project_context(...)` 时，系统会自动把影子任务树迁到正式会话；但仍建议首轮就传稳定 `chat_session_id`，避免产生影子链路。",
            "- 接入约束: 每个 CLI 会话都应自行生成唯一 `chat_session_id`；如能解析项目工作区，优先持久化到项目目录 `.ai-employee/query-mcp/`，否则再退回 CLI 自己的本地存储。同一轮任务内固定复用，只有新开的并行 CLI 或新任务才重新生成。",
            "- 接入约束: `query-mcp` 本地状态必须只写三类 canonical 文件：`.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每进程独立，避免多进程冲突）、`.ai-employee/query-mcp/active/<project_id>.json`、`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`；`current-session.json`、`chat_session_id.txt`、`session_id.txt`、`current-work-session.json` 等 legacy 文件只允许兼容读取，不允许新写。",
            "- 记忆约束: 仅在新需求开始、续跑恢复、修复旧问题或当前问题明显依赖历史经验时才检索记忆；同一任务轮若已生成任务树并进入执行，不要重复 recall。",
            f"- 交互约束: {clarity_threshold_line}",
            f"- 交互约束: {clarity_direct_line}",
            f"- 交互约束: {clarity_confirm_line}",
            f"- 交互约束: {clarity_repeat_line}",
            "- 项目约束: 优先使用项目绑定员工、规则和技能；只有项目能力不足时才自行补足。",
            "- 项目约束: 进入分析、实现或排查前，重新获取与当前任务直接相关的规则正文，不要只依赖规则标题。",
            "- 任务树约束: 任务树节点必须描述面向用户目标的真实工作步骤；不要把 search_project_context、query_project_rules、search_ids、get_manual_content、resolve_relevant_context、generate_execution_plan 或候选代理工具名直接写成节点。",
            "- 工作流约束: 用户提需求后先规划，再执行；执行中只更新任务树、工作事实和会话事件，不要提前输出最终结论。",
            "- 工作流约束: 必须做到“完成一个节点、补一次验证、再进入下一步”；只有整棵任务树完成并写入验证结果后，当前需求才算结束。",
            "- 长任务建议: 新会话优先调用 start_work_session 获取服务端 session_id，并与 `chat_session_id` 一起通过统一状态服务持久化到 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每进程独立）、`.ai-employee/query-mcp/active/<project_id>.json`、`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`；若当前拿不到项目工作区，再退回 CLI 自己的本地存储。每完成一个子阶段调用 save_work_facts 或 append_session_event。",
            "- 长任务建议: 中断恢复顺序应固定为“恢复本地 `chat_session_id/session_id` -> bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...) -> 按当前任务树继续执行”；如果项目工作区不可解析，则恢复来源应是 CLI 自己的本地存储，而不是共享仓库根目录。",
            "- 宿主扩展: 如宿主需要展示任务树演化摘要，可按需读取 `/api/projects/{project_id}/chat/task-tree/evolution-summary?chat_session_id=...`。",
            "- 适合自动化的能力: 任务分析、相关上下文聚合、执行步骤骨架、风险分类、工作轨迹恢复。",
            "- 需要谨慎的能力: 高风险命令、工作区外路径、破坏性命令，优先先调用 check_operation_policy。",
        ]
    elif normalized == "codex":
        title = "Codex"
        focus = [
            "- 定位: 适合以代码任务拆解、补丁实现和结构化交付为主的开发型 CLI。",
            "- 推荐链路: query://usage-guide -> query://client-profile/codex -> start_project_workflow -> check_operation_policy -> save_work_facts/append_session_event -> build_delivery_report。",
            "- 固定入口: 优先调用 `start_project_workflow`，不要手动拼接 search_ids / get_manual_content / analyze_task / resolve_relevant_context / generate_execution_plan 这一整串前置步骤。",
            "- 接入约束: `description`、项目说明和“当前项目”文字不会自动绑定任务树；URL 或首轮工具参数里必须显式出现 `project_id`，需要续接时再补 `chat_session_id` 或 `bind_project_context(...)`。",
            "- 接入约束: 如果当前 CLI 没有活跃 MCP session，只要显式传了 `project_id + chat_session_id`，`bind_project_context(...)` 也会走 detached 绑定并先建任务树；后续所有工具继续显式复用同一个 `chat_session_id`。",
            "- 接入约束: 若 direct CLI fallback 先生成了临时 `query-cli.*` 会话，后续再用显式 `cli.*` 会话执行 `bind_project_context(...)` 时，系统会自动把影子任务树迁到正式会话；但仍建议首轮就传稳定 `chat_session_id`。",
            "- 接入约束: 统一查询工作流默认先检查项目本地 `.ai-employee/skills/query-mcp-workflow/`；缺失时从系统技能库同步或创建到本地，已存在则直接复用，并优先读取本地副本。",
            "- 接入约束: 通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。",
            "- 接入约束: 每个 Codex CLI 会话都应先持久化自己生成的 `chat_session_id`；如能解析项目工作区，优先写到项目目录 `.ai-employee/query-mcp/`，否则再写 Codex 自己的本地存储。同一进程整轮任务固定复用，只有新开的并行任务或全新需求才重新生成。",
            "- 接入约束: `query-mcp` 本地状态必须只写三类 canonical 文件：`.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每进程独立，避免多进程冲突）、`.ai-employee/query-mcp/active/<project_id>.json`、`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`；`current-session.json`、`chat_session_id.txt`、`session_id.txt`、`current-query-session.json`、`current-work-session.json`、`session.env` 等 legacy 文件只允许兼容读取，不允许新写。",
            "- 接入约束: 除 query-mcp canonical 状态外，每个需求还要维护 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`；requirement 对象至少保留 `workflow_skill`、`record_path`、`storage_scope`、`task_tree`、`current_task_node`、`task_branches`、`history`。",
            "- 查询约束: 仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或需要跨项目检索时，再调用 `search_ids(keyword=\"<用户原始问题>\")`；当前项目和对象已明确时，可直接读取 `get_manual_content(project_id=...)` 或进入 `start_project_workflow(...)`。",
            f"- 交互约束: {clarity_threshold_line}",
            f"- 交互约束: {clarity_direct_line}",
            f"- 交互约束: {clarity_confirm_line}",
            f"- 交互约束: {clarity_repeat_line}",
            "- 记忆约束: 仅在新需求开始、续跑恢复、修复旧问题或当前问题明显依赖历史经验时才检索记忆；同一任务轮若已生成任务树并进入执行，不要重复 recall_project_memory / recall_employee_memory。",
            "- 项目约束: 优先使用项目绑定员工、规则和技能；只有项目能力不足时才自行补足。",
            "- 项目约束: 进入分析、实现或排查前，重新获取与当前任务直接相关的规则正文，不要只依赖规则标题。",
            "- 工作流约束: 本地优先推进分析、改动、验证和 requirement 记录，再通过 MCP 回写任务树、工作事实与交付结论。",
            "- 任务树约束: 查询型问题保持单检索节点；实现型任务节点才写成分析、实现、验证这类面向目标的步骤。不要把内部检索工具、规则查询工具、候选代理工具或 `Auto inferred proxy entry from scripts/...` 这类描述直接当成节点。",
            "- 任务树约束: `bind_project_context(...)` 后如果宿主支持任务树，立刻调用 `get_current_task_tree` 核对 `root_goal/title/current_node` 是否属于当前用户原始问题；若明显挂到了旧任务树，停止复用当前 `chat_session_id`，改为新建并持久化新的 `chat_session_id` 后重新绑定。",
            "- 工作流约束: 用户提需求后先生成计划并挂到任务树，再按计划逐项推进；执行中不要把阶段性结果写成最终结论。",
            "- 工作流约束: 每完成一个计划项就立刻补验证结果，再处理下一个；只有所有计划项完成后，才能生成最终总结或补稳定结论记忆。",
            "- 工作流约束: 开始执行某个任务节点前，先调用 `update_task_node_status(status=in_progress|verifying)`；完成节点时必须调用 `complete_task_node_with_verification`，不要只在自然语言里声称“已完成”。",
            "- 工作流约束: 如果当前宿主拿不到 `get_current_task_tree`、`update_task_node_status` 或 `complete_task_node_with_verification`，只能给出“未完成闭环”的结论，不能把任务树执行闭环描述成已经完成。",
            "- 收尾要求: 若宿主未启用自动记忆，或本轮需要额外沉淀稳定结论/关键决策，再调用一次 save_project_memory(project_id, content, ...)；不要在同一需求的每个中间步骤重复补记。",
            "- 长任务建议: 新会话优先调用 start_work_session 获取服务端 session_id，并与 `chat_session_id` 一起通过统一状态服务持久化到 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每进程独立）、`.ai-employee/query-mcp/active/<project_id>.json`、`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`；若当前拿不到项目工作区，再退回 Codex 自己的本地存储。关键决策写入 save_work_facts，关键执行节点写入 append_session_event，并始终复用同一个 `chat_session_id` / `session_id`。",
            "- 长任务建议: 中断后恢复时，先从本地恢复 `chat_session_id + session_id`，再按 `bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)` 的顺序拉起上下文，随后紧接着继续当前任务；如果项目工作区不可解析，则恢复来源应是 Codex 自己的本地存储，而不是共享仓库根目录。",
            "- 宿主扩展: 如宿主需要展示任务树演化摘要，可按需读取 `/api/projects/{project_id}/chat/task-tree/evolution-summary?chat_session_id=...`。",
            "- 适合自动化的能力: 结构化任务分析、项目规则聚合、交付报告、更新日志条目生成。",
            "- 需要谨慎的能力: 任何真实执行前先补 classify_command_risk / check_operation_policy。",
        ]
    else:
        title = "Generic CLI"
        focus = [
            "- 定位: 适合通用 MCP 宿主或尚未针对当前系统定制的 CLI 客户端。",
            "- 推荐链路: query://usage-guide -> search_ids -> get_manual_content -> analyze_task -> resolve_relevant_context -> start_work_session。",
            "- 接入约束: `type=sse` 的客户端有些会直接使用 `POST /mcp/query/sse` 作为 JSON-RPC bridge；这时如果 URL 没有 `project_id` / `chat_session_id`，首轮必须调用 `bind_project_context(...)` 或在工具参数里显式传 `project_id`。",
            "- 接入约束: 统一入口 CLI 建议同时持久化自生成的 `chat_session_id` 和服务端返回的 `session_id`；如能解析项目工作区，优先写到项目目录 `.ai-employee/query-mcp/`，否则再写 CLI 自己的本地存储，这样中断后才能稳定续跑。",
            "- 记忆约束: 不要把 recall 当成每轮固定前置步骤；只有新需求、续跑恢复、修复旧问题或明显需要历史经验时才查记忆。",
            f"- 交互约束: {clarity_threshold_line}",
            f"- 交互约束: {clarity_direct_line}",
            f"- 交互约束: {clarity_confirm_line}",
            f"- 交互约束: {clarity_repeat_line}",
            "- 项目约束: 优先使用项目绑定员工、规则和技能；只有项目能力不足时才自行补足。",
            "- 项目约束: 进入分析、实现或排查前，重新获取与当前任务直接相关的规则正文，不要只依赖规则标题。",
            "- 任务树约束: 若宿主会展示任务树，节点必须直接对应用户目标，不要把内部检索工具、规划工具或候选代理工具直接展示成节点。",
            "- 工作流约束: 先计划、再执行、逐项验证；未完成前只保留需求记录和过程状态，不要提前输出最终结论。",
            "- 最小可用目标: 先跑通查询、分析、规划，再逐步接入策略判断和恢复能力。",
            "- 建议优先工具: analyze_task、resolve_relevant_context、generate_execution_plan、check_operation_policy。",
            "- 长任务建议: 新会话优先调用 start_work_session；恢复时按 `bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)` 顺序拉起上下文，再继续执行。",
        ]
    if template:
        return _render_query_prompt_template(
            template,
            {
                "client_title": title,
                "focus_lines": "\n".join(focus),
            },
        )
    return "\n".join([f"# {title} Client Profile", "", *focus])


def build_query_usage_guide_text() -> str:
    config = system_config_store.get_global()
    template = str(
        getattr(config, "query_mcp_usage_guide_template", "") or ""
    ).strip()
    (
        clarity_threshold_line,
        clarity_direct_line,
        clarity_confirm_line,
        clarity_repeat_line,
    ) = _query_mcp_clarity_instruction_lines()
    if template:
        return _render_query_prompt_template(
            template,
            {
                "clarity_threshold_line": clarity_threshold_line,
                "clarity_direct_line": clarity_direct_line,
                "clarity_confirm_line": clarity_confirm_line,
                "clarity_repeat_line": clarity_repeat_line,
            },
        )
    return (
        "# Unified Query MCP\n\n"
        "- 统一入口路径: /mcp/query\n"
        "- 目标: 提供项目/员工/规则查询、任务分析、上下文聚合、执行规划、任务树推进、工作轨迹、需求历史查询和交付报告能力。\n"
        "- 推荐工具: start_project_workflow / bind_project_context / search_ids / get_content / get_manual_content / analyze_task / resolve_relevant_context / generate_execution_plan / get_current_task_tree / update_task_node_status / complete_task_node_with_verification / classify_command_risk / check_workspace_scope / resolve_execution_mode / check_operation_policy / start_work_session / save_work_facts / append_session_event / resume_work_session / summarize_checkpoint / list_recent_project_requirements / get_requirement_history / build_delivery_report / generate_release_note_entry / save_project_memory\n"
        "\n"
        "## 最少执行规则\n"
        "1. 先读取 query://usage-guide；当前是 Codex / Claude 这类代码 CLI 时，再补读 query://client-profile/codex 或 query://client-profile/claude-code。\n"
        "1.1 实现型需求优先调用 start_project_workflow(...) 作为固定入口，不要手动拼接十几个前置查询步骤。\n"
        "1.2 统一查询工作流默认先检查项目本地 `.ai-employee/skills/query-mcp-workflow/`；若不存在，再从系统技能库同步或创建到本地；已存在则直接复用，禁止重复创建。\n"
        "1.3 通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；优先读取本地副本中的 `SKILL.md` 与 `manifest.json`。只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。\n"
        "2. MCP 配置里的 description、项目说明、\"当前项目\" 这类文字都不参与真正绑定；真正生效的是 URL 里的 project_id / chat_session_id 默认上下文，以及 bind_project_context(...) 写入的 MCP 会话绑定。\n"
        "3. 若接入地址缺少 project_id，或需要续接任务树但缺少 chat_session_id，首轮立即调用 bind_project_context(project_id, chat_session_id?, root_goal?)；不要只依赖 description 里的项目说明。\n"
        "4. 如果当前 CLI 没有活跃 MCP session，只要显式传了 project_id + chat_session_id，bind_project_context(...) 也会走 detached 绑定并先建任务树；后续所有工具继续显式复用同一个 chat_session_id。\n"
        "4.0 如果 direct CLI fallback 已先生成临时 `query-cli.*` 会话，后续再用显式 `cli.*` 会话调用 bind_project_context(...) 时，系统会自动把影子任务树迁到正式会话；但最佳实践仍然是首轮就传稳定 chat_session_id。\n"
        "4.1 每个 CLI 会话都应持久化自己生成的 chat_session_id；如能解析项目工作区，优先写到项目目录 .ai-employee/query-mcp/，否则再退回 CLI 自己的本地存储。同一轮任务固定复用，只有新开的并行 CLI 或全新任务才重新生成。\n"
        "4.2 query-mcp 本地持久化必须使用唯一文件规范：每进程会话文件为 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每个 CLI 进程写自己的独立文件，避免多进程冲突）；项目级权威状态文件为 `.ai-employee/query-mcp/active/<project_id>.json` 与 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。除兼容历史数据时只读外，禁止新写 `current-session.json`、`chat_session_id.txt`、`session_id.txt`、`chat_session_id`、`session_id`、`session.env`、`current-query-session.json`、`current-work-session.json` 这类分叉文件。\n"
        "4.3 每个需求还必须单独维护 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`；一条需求一个对象，不要把多个需求混写到同一聚合文件。\n"
        "4.4 requirement 对象应至少记录 `workflow_skill`、`record_path`、`storage_scope`、`task_tree`、`current_task_node`、`task_branches`、`history`，保证本地推进和服务端任务树都能追溯到同一条需求。\n"
        "5. type=sse 的客户端可能直接使用 POST /mcp/query/sse 作为 JSON-RPC bridge，而不是先 GET /sse 再 /messages；这类接法若要自动创建项目任务树，首轮也必须显式提供 project_id，建议同时提供 chat_session_id 并调用 bind_project_context。\n"
        "6. 仅在缺少明确的 project_id / employee_id / rule_id，或需要跨项目检索时，再调用 search_ids(keyword=\"<用户原始问题>\")；已明确当前项目且在项目内执行时，可直接 get_manual_content、start_project_workflow 或进入本地实现。\n"
        "7. 需要规则或项目上下文时，先 get_manual_content，再按需调用 get_content；不要跳过 ID 定位直接臆造项目、员工、规则 ID。\n"
        "7.0 项目型问题优先使用项目绑定员工、规则和技能；先判断项目内现成能力能否闭环，只有项目能力不足时才自行补足。\n"
        "7.0.1 每次新请求进入分析、实现或排查前，重新获取与当前任务直接相关的规则正文；不要只看规则标题，也不要把无关规则机械带入当前问题。\n"
        "7.0.2 实现型任务先在项目本地推进：先完成本地分析、改动、验证和 requirement 记录，再通过 MCP 回写任务树、工作事实、交付结论与记忆。\n"
        f"7.0.3 {clarity_threshold_line}\n"
        f"7.0.4 {clarity_direct_line}\n"
        f"7.0.5 {clarity_confirm_line}\n"
        f"7.0.6 {clarity_repeat_line}\n"
        "7.1 记忆检索不是每轮固定步骤；仅在新需求开始、续跑恢复、修复旧问题或当前问题明显依赖历史经验时，再调用 recall_project_memory 或 recall_employee_memory。\n"
        "7.2 同一任务轮若已生成任务树并进入执行，后续默认依赖当前会话、任务树和工作轨迹，不要重复检索同一批项目记忆。\n"
        "8. 实现型需求必须遵守任务树闭环：先 analyze_task -> resolve_relevant_context -> generate_execution_plan，再 get_current_task_tree 确认节点；执行中用 update_task_node_status 回写状态，完成时必须 complete_task_node_with_verification 填写验证结果。\n"
        "9. 只有所有计划节点完成且验证结果齐全后，当前需求才算结束；执行中不得提前写“最终结论”。\n"
        "10. 查询型问题（谁 / 哪些 / 多少 / 从哪里）保持单检索节点，不要误拆成实现步骤；检索完成后应让任务树归档。\n"
        "11. 如用户在“已完成”后发现问题，必须重新起一轮修复计划，并继续回写轨迹与验证；不得直接覆盖上一轮结论。\n"
        "\n"
        "## 任务树与绑定约束\n"
        "- 任务树与记忆必须使用同一条聊天会话线索；记录项目记忆、工作事实或会话事件时，应复用当前 chat_session_id / session_id，不得把任务树和记忆拆成两条无关轨迹。\n"
        "- 同一条用户提问在统一查询 MCP 下只允许沉淀 1 条项目级问题记忆，并绑定 1 棵任务树；start_work_session / save_work_facts / append_session_event 等续跑工具不得再生成新的“用户问题”记忆或新的任务树。\n"
        "- 需要沉淀对话结论时，除最终答案外，还应保证后续可从记忆详情回看该轮规划、执行节点和验证结果。\n"
        "- 任务树节点必须直接描述面向用户目标的工作步骤；不要把 search_project_context、query_project_rules、search_ids、get_manual_content、resolve_relevant_context、generate_execution_plan 等内部检索/规划工具直接当成节点标题。\n"
        "- 候选代理工具、脚本路径和类似“Auto inferred proxy entry from scripts/... ”的描述，只能作为内部工具信息，不得直接展示为任务树节点。\n"
        "- `bind_project_context(...)` 后如已返回任务树，或宿主支持 `get_current_task_tree`，必须立刻校验 `root_goal/title/current_node` 是否属于当前用户原始问题；若明显属于旧问题，说明当前 `chat_session_id` 挂错了任务树，应立即改用新的 `chat_session_id` 重新绑定。\n"
        "- 不允许跳过节点状态回写直接口头宣布完成；开始节点用 `update_task_node_status`，完成节点用 `complete_task_node_with_verification`，父节点完成前必须补齐自己的整体验证结果。\n"
        "- 若当前宿主未暴露任务树读取/推进工具，只能说明“无法完成任务树执行闭环”，不得把缺失能力包装成已闭环。\n"
        "\n"
        "## 高层能力\n"
        "- analyze_task: 对用户原始任务做结构化理解。\n"
        "- resolve_relevant_context: 聚合相关项目成员、规则、工具和上下文。\n"
        "- generate_execution_plan: 输出执行步骤骨架，用于生成真正的任务计划。\n"
        "- get_current_task_tree / update_task_node_status / complete_task_node_with_verification: 用于读取、推进和验证任务树节点。\n"
        "\n"
        "## 策略与执行能力\n"
        "- classify_command_risk: 判断命令风险等级。\n"
        "- check_workspace_scope: 校验路径是否位于工作区内。\n"
        "- resolve_execution_mode: 判断该走 local connector、项目工具还是仅保留查询。\n"
        "- check_operation_policy: 输出允许 / 拦截 / 需确认结论。\n"
        "- resolve_project_experience_rules: 按任务文本从项目经验规则中按需加载相关经验卡片，避免无关经验占用上下文。\n"
        "- execute_project_collaboration: 统一编排入口（项目协作），但是否单人主责、是否需要多人协作以及如何拆分，仍由 AI 结合项目手册、员工手册、规则和工具自主判断，不预设固定行业分工模板。\n"
        "- 若需要手动编排项目执行，再继续调用 list_project_members / get_project_runtime_context / resolve_project_experience_rules / list_project_proxy_tools / invoke_project_skill_tool。\n"
        "\n"
        "## 工作轨迹与恢复\n"
        "- 多轮任务先 start_work_session；后续复用同一个 chat_session_id / session_id，并用 save_work_facts、append_session_event、resume_work_session、summarize_checkpoint 维护轨迹。\n"
        "- start_work_session 可返回服务端生成的 session_id；save_work_facts 和 append_session_event 支持附带 session_id、phase、step、changed_files、verification、risks、next_steps 等结构化轨迹字段；resume_work_session / summarize_checkpoint 会聚合这些字段，直接输出阶段、步骤、文件、验证、风险和下一步。\n"
        "- 每个新聊天窗口的首轮有效对话，如用户未显式提供 session_id，应优先调用 start_work_session 获取服务端 session_id，再在本窗口后续所有 save_work_facts / append_session_event / resume_work_session / summarize_checkpoint 中复用同一个值；如果未先调用，save_work_facts 也会自动补生成一个。\n"
        "- 建议把客户端自生成的 chat_session_id 和 start_work_session 返回的 session_id 一起持久化；如能解析项目工作区，优先通过统一状态服务写入 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每进程独立）、`.ai-employee/query-mcp/active/<project_id>.json`、`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`，并同步维护 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`，否则再退回 CLI 自己的本地存储。这样 CLI 中断后可以直接恢复同一条任务树和工作轨迹。\n"
        "- start_work_session 会立即写入一条 started 事件建立正式工作轨迹；首次拿到 session_id 后，仍建议尽快调用一次 save_work_facts 补充任务摘要、阶段和文件信息。若既不调用 start_work_session，也不写 save_work_facts / append_session_event，而只写 save_project_memory，会出现“有项目记忆但无正式工作轨迹”的情况。\n"
        "- 缺少活跃 MCP session 的 CLI / bridge 场景下，也必须显式传入并持续复用同一个 chat_session_id；否则容易出现“轨迹已写入，但当前主视图没有挂到任务树”的错觉。\n"
        "- 推荐的中断恢复顺序是：先从本地恢复 chat_session_id 和 session_id，再调用 bind_project_context(...)，然后依次调用 resume_work_session(...)、summarize_checkpoint(...)，最后按当前任务树继续执行；如果项目工作区不可解析，则恢复来源应是 CLI 自己的本地存储，而不是共享仓库根目录。\n"
        "- 如需回答“最近做了哪些需求”“某个需求什么时候改过”“按日期查需求变更”，可调用 list_recent_project_requirements / get_requirement_history；它们会优先读取 work_session_store，命中不足时回退项目记忆。\n"
        "- 如宿主需要展示任务树演化摘要，可按需读取 /api/projects/{project_id}/chat/task-tree/evolution-summary?chat_session_id=...。\n"
        "\n"
        "## 记忆与交付\n"
        "- recall_project_memory / recall_employee_memory 只在新需求开始、续跑恢复、修复旧问题或明显需要历史经验时使用；不要把记忆检索当成每个计划节点的固定前置动作。\n"
        "- 同一任务轮若已生成任务树并进入执行，后续优先依赖当前会话、任务树和工作轨迹；除非用户明确要求沿用历史方案或当前上下文明显不足，否则不要重复 recall。\n"
        "- save_project_memory 只在补充稳定结论或关键决策时使用；不要在同一需求的每个中间步骤重复补记。如宿主已启用自动记忆快照，仅在入口未覆盖自动记忆或需要补一条稳定结论时再额外保存。\n"
        "- build_delivery_report 用于结构化汇总本轮交付；generate_release_note_entry 用于生成更新日志条目。\n"
        "- 可读取 query://client-profile/claude-code 或 query://client-profile/codex 作为客户端接入画像。\n"
        "\n"
        "## 说明\n"
        "- 本入口仍以查询与聚合优先；如宿主支持多 MCP，复杂执行场景仍优先直连对应 project MCP。\n"
        "- 本入口已暴露 save_project_memory，可通过 project_id 直接写入项目对话内容；save_employee_memory 仍不暴露。如宿主系统已启用自动记忆，入口层仍会自动记录问题快照。"
    )


def _coerce_list_text(values: list[str] | str | None = None, fallback: str = "") -> list[str]:
    items: list[str] = []
    for item in _iter_text_values(values):
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
    completed_items: list[str] | str | None = None,
    changed_files: list[str] | str | None = None,
    verification: list[str] | str | None = None,
    risks: list[str] | str | None = None,
    next_steps: list[str] | str | None = None,
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


def create_query_mcp(
    *,
    current_key_owner_username_ctx=None,
    current_mcp_session_id_ctx=None,
    session_contexts: dict[str, dict[str, str]] | None = None,
):
    mcp = _new_mcp("query-center")

    def _current_query_session_context() -> dict[str, str]:
        session_binding_key = ""
        if current_mcp_session_id_ctx is not None:
            session_binding_key = str(current_mcp_session_id_ctx.get("") or "").strip()
        if not (session_contexts is not None and session_binding_key):
            return {}
        return dict(session_contexts.get(session_binding_key) or {})

    def _extract_memory_section(content: str, label: str) -> str:
        text = str(content or "")
        label_value = str(label or "").strip()
        if not label_value:
            return ""
        bracket_label = re.escape(label_value)
        bracket_match = re.search(
            rf"(?:^|\n)\[{bracket_label}\]\s*([\s\S]*?)(?=\n\[[^\n]+\]|$)",
            text,
        )
        if bracket_match:
            return _normalize_text(bracket_match.group(1), 1200)
        plain_match = re.search(
            rf"(?:^|\n){bracket_label}[:：]\s*([\s\S]*?)(?=\n(?:\[[^\n]+\]|[^\n\[\]:：]{{1,24}}[:：])|$)",
            text,
        )
        return _normalize_text(plain_match.group(1), 1200) if plain_match else ""

    def _derive_memory_root_goal(content: str) -> str:
        text = _normalize_text(content, 4000)
        if not text:
            return ""
        for label in ("用户问题", "问题原文", "问题摘要", "问题", "需求", "目标"):
            section_value = _extract_memory_section(text, label)
            if section_value:
                return _normalize_text(section_value, 1000)
        first_line = next(
            (line.strip() for line in text.splitlines() if str(line or "").strip()),
            "",
        )
        return _normalize_text(first_line, 1000)

    def _append_memory_project_binding(content: str, project_id: str, project_name: str = "") -> str:
        content_value = _normalize_text(content, 4000)
        project_id_value = _normalize_text(project_id, 120)
        project_name_value = _normalize_text(project_name, 160)
        if not content_value:
            return content_value
        lines = [content_value]
        if project_id_value and not _extract_memory_section(content_value, "项目ID"):
            lines.append(f"[项目ID] {project_id_value}")
        if project_name_value and not _extract_memory_section(content_value, "项目名称"):
            lines.append(f"[项目名称] {project_name_value}")
        return _normalize_text("\n".join(lines), 4000)

    def _append_memory_chat_session(content: str, chat_session_id: str) -> str:
        content_value = _normalize_text(content, 4000)
        chat_session_id_value = _normalize_text(chat_session_id, 120)
        if not content_value or not chat_session_id_value:
            return content_value
        if _extract_memory_section(content_value, "关联会话"):
            return content_value
        return f"{content_value}\n[关联会话] {chat_session_id_value}"

    def _append_memory_task_tree_binding(content: str, task_tree_payload: dict | None, chat_session_id: str = "") -> str:
        content_value = _normalize_text(content, 4000)
        if not content_value or not isinstance(task_tree_payload, dict):
            return content_value
        if any(str(line or "").strip().startswith("[执行轨迹JSON]") for line in content_value.splitlines()):
            return content_value
        current_node = (
            task_tree_payload.get("current_node")
            if isinstance(task_tree_payload.get("current_node"), dict)
            else {}
        )
        binding = {
            "chat_session_id": _normalize_text(chat_session_id, 120),
            "task_tree_session_id": _normalize_text(task_tree_payload.get("id"), 80),
            "task_tree_chat_session_id": _normalize_text(
                task_tree_payload.get("source_chat_session_id") or task_tree_payload.get("chat_session_id"),
                80,
            ),
            "task_node_id": _normalize_text(current_node.get("id"), 80),
            "task_node_title": _normalize_text(current_node.get("title"), 200),
            "root_goal": _normalize_text(task_tree_payload.get("root_goal") or task_tree_payload.get("title"), 400),
        }
        binding = {key: value for key, value in binding.items() if value}
        if not binding:
            return content_value
        return f"{content_value}\n[执行轨迹JSON] {json.dumps(binding, ensure_ascii=False, sort_keys=True)}"

    def _ensure_query_task_tree(
        *,
        root_goal: str,
        project_id: str = "",
        chat_session_id: str = "",
        max_steps: int | None = None,
        force: bool = False,
    ) -> dict | None:
        root_goal_value = _normalize_text(root_goal, 1000)
        if not root_goal_value:
            return None
        session_binding_key = ""
        if current_mcp_session_id_ctx is not None:
            session_binding_key = str(current_mcp_session_id_ctx.get("") or "").strip()
        bound_context = _current_query_session_context()
        project_id_value = _normalize_text(project_id, 120) or _normalize_text(
            bound_context.get("project_id"),
            120,
        )
        if not project_id_value:
            return None
        username, fallback_chat_session_id = _resolve_task_tree_context()
        chat_session_id_value = _normalize_text(chat_session_id, 120) or _normalize_text(
            bound_context.get("chat_session_id"),
            120,
        )
        if not chat_session_id_value:
            chat_session_id_value = _normalize_text(fallback_chat_session_id, 120)
        if not chat_session_id_value:
            return None
        if not username:
            username = "mcp-user"
        from services.project_chat_task_tree import ensure_task_tree, serialize_task_tree

        ensure_kwargs = {
            "project_id": project_id_value,
            "username": username,
            "chat_session_id": chat_session_id_value,
            "root_goal": root_goal_value,
        }
        if max_steps is not None:
            ensure_kwargs["max_steps"] = max(1, min(int(max_steps or 6), 10))
        if force:
            ensure_kwargs["force"] = True
        session = ensure_task_tree(**ensure_kwargs)
        if session_contexts is not None and session_binding_key:
            project_name_value = _resolve_project_name(
                project_id_value,
                str(bound_context.get("project_name") or "").strip(),
            )
            session_contexts[session_binding_key] = {
                "project_id": project_id_value,
                "project_name": project_name_value,
                "employee_id": str(bound_context.get("employee_id") or "").strip(),
                "chat_session_id": chat_session_id_value,
            }
        return serialize_task_tree(session)

    def _ensure_or_reuse_query_task_tree(
        *,
        project_id: str,
        chat_session_id: str = "",
        root_goal: str = "",
    ) -> dict | None:
        root_goal_value = _normalize_text(root_goal, 1000)
        if root_goal_value:
            return _ensure_query_task_tree(
                root_goal=root_goal_value,
                project_id=project_id,
                chat_session_id=chat_session_id,
            )
        return _get_existing_query_task_tree(
            project_id=project_id,
            chat_session_id=chat_session_id,
        )

    def _load_query_task_tree_for_progress(
        *,
        project_id: str,
        chat_session_id: str = "",
        root_goal: str = "",
    ) -> dict | None:
        existing_task_tree_payload = _get_existing_query_task_tree(
            project_id=project_id,
            chat_session_id=chat_session_id,
        )
        if isinstance(existing_task_tree_payload, dict):
            return existing_task_tree_payload

        project_id_value = _normalize_text(project_id, 120)
        chat_session_id_value = _normalize_text(chat_session_id, 120)
        if not (project_id_value and chat_session_id_value):
            return None

        existing_requirement = load_query_mcp_requirement_record(
            project_id_value,
            chat_session_id=chat_session_id_value,
        )
        requirement_task_tree = (
            existing_requirement.get("task_tree")
            if isinstance(existing_requirement.get("task_tree"), dict)
            else None
        )
        if requirement_task_tree:
            return requirement_task_tree

        root_goal_value = _normalize_text(root_goal, 1000)
        if not root_goal_value:
            return None
        return _ensure_or_reuse_query_task_tree(
            project_id=project_id_value,
            chat_session_id=chat_session_id_value,
            root_goal=root_goal_value,
        )

    def _resolve_task_tree_context() -> tuple[str, str]:
        username = ""
        if current_key_owner_username_ctx is not None:
            username = current_key_owner_username_ctx.get("").strip()
        if not username:
            username = "mcp-user"
        chat_session_id = ""
        if current_mcp_session_id_ctx is not None:
            chat_session_id = current_mcp_session_id_ctx.get("").strip()
        return username, chat_session_id

    def _resolve_query_chat_session_id(explicit_chat_session_id: str = "") -> str:
        bound_context = _current_query_session_context()
        _, fallback_chat_session_id = _resolve_task_tree_context()
        return _normalize_text(explicit_chat_session_id, 120) or _normalize_text(
            bound_context.get("chat_session_id"),
            120,
        ) or _normalize_text(fallback_chat_session_id, 120)

    def _resolve_query_project_id(explicit_project_id: str = "") -> str:
        bound_context = _current_query_session_context()
        return _normalize_text(explicit_project_id, 120) or _normalize_text(
            bound_context.get("project_id"),
            120,
        )

    def _select_query_task_tree_node(
        payload: dict[str, Any] | None,
        *,
        phase: str = "",
        step: str = "",
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        current_node = payload.get("current_node") if isinstance(payload.get("current_node"), dict) else {}
        nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
        candidate_nodes = [
            item for item in nodes
            if isinstance(item, dict) and _normalize_text(item.get("id"), 80) and _normalize_text(item.get("parent_id"), 80)
        ]
        if not candidate_nodes:
            return current_node if current_node else {}

        normalized_phase = _normalize_text(phase, 80).lower()
        normalized_step = _normalize_text(step, 200).lower()
        current_node_id = _normalize_text(current_node.get("id"), 80)
        if not normalized_phase and not normalized_step:
            return current_node if current_node else candidate_nodes[0]

        def step_match_score(node: dict[str, Any]) -> int:
            if not normalized_step:
                return 0
            texts = [
                _normalize_text(node.get("title"), 200).lower(),
                _normalize_text(node.get("objective"), 400).lower(),
                _normalize_text(node.get("description"), 500).lower(),
                _normalize_text(node.get("summary_for_model"), 500).lower(),
            ]
            if any(text == normalized_step for text in texts if text):
                return 3
            if any(normalized_step in text for text in texts if text):
                return 2
            if any(text and text in normalized_step for text in texts):
                return 1
            return 0

        def phase_match_score(node: dict[str, Any]) -> int:
            if not normalized_phase:
                return 0
            stage_key = _normalize_text(node.get("stage_key"), 80).lower()
            if stage_key == normalized_phase:
                return 3
            texts = [
                _normalize_text(node.get("title"), 200).lower(),
                _normalize_text(node.get("description"), 500).lower(),
            ]
            if any(normalized_phase in text for text in texts if text):
                return 1
            return 0

        if normalized_phase:
            phase_matched_nodes = [
                node for node in candidate_nodes
                if phase_match_score(node) > 0
            ]
            unfinished_phase_nodes = [
                node for node in phase_matched_nodes
                if _normalize_status(node.get("status")) != "done"
            ]
            if unfinished_phase_nodes:
                candidate_nodes = unfinished_phase_nodes
            elif phase_matched_nodes:
                candidate_nodes = phase_matched_nodes

        ranked = sorted(
            candidate_nodes,
            key=lambda node: (
                phase_match_score(node),
                step_match_score(node),
                1 if _normalize_status(node.get("status")) != "done" else 0,
                1 if _normalize_text(node.get("id"), 80) == current_node_id else 0,
                -int(node.get("level") or 0),
                -int(node.get("sort_order") or 0),
            ),
            reverse=True,
        )
        best = ranked[0] if ranked else {}
        if (step_match_score(best) > 0) or (phase_match_score(best) > 0):
            return best
        return current_node if current_node else best

    def _resolve_query_task_tree_binding(
        *,
        project_id: str,
        chat_session_id: str = "",
        phase: str = "",
        step: str = "",
    ) -> dict[str, str]:
        project_id_value = _normalize_text(project_id, 120)
        username, fallback_chat_session_id = _resolve_task_tree_context()
        chat_session_id_value = _resolve_query_chat_session_id(chat_session_id) or _normalize_text(
            fallback_chat_session_id,
            120,
        )
        if not (project_id_value and username and chat_session_id_value):
            return {}
        try:
            from services.project_chat_task_tree import get_task_tree_for_chat_session, serialize_task_tree

            session = get_task_tree_for_chat_session(
                project_id_value,
                username,
                chat_session_id_value,
            )
            payload = serialize_task_tree(session) if session is not None else None
        except Exception:  # pragma: no cover - defensive fallback
            payload = None
        if not isinstance(payload, dict):
            return {}
        selected_node = _select_query_task_tree_node(
            payload,
            phase=phase,
            step=step,
        )
        return {
            "task_tree_session_id": _normalize_text(payload.get("id"), 80),
            "task_tree_chat_session_id": _normalize_text(
                payload.get("source_chat_session_id") or payload.get("chat_session_id"),
                80,
            ),
            "task_node_id": _normalize_text(selected_node.get("id"), 80),
            "task_node_title": _normalize_text(selected_node.get("title"), 200),
        }

    def _fallback_query_task_tree_binding(
        *,
        task_tree_payload: dict | None,
        chat_session_id: str = "",
    ) -> dict[str, str]:
        if not isinstance(task_tree_payload, dict):
            return {}
        current_node = (
            task_tree_payload.get("current_node")
            if isinstance(task_tree_payload.get("current_node"), dict)
            else {}
        )
        return {
            "task_tree_session_id": _normalize_text(task_tree_payload.get("id"), 80),
            "task_tree_chat_session_id": _normalize_text(
                task_tree_payload.get("source_chat_session_id")
                or task_tree_payload.get("chat_session_id")
                or chat_session_id,
                120,
            ),
            "task_node_id": _normalize_text(current_node.get("id"), 80),
            "task_node_title": _normalize_text(current_node.get("title"), 200),
        }

    def _synthesize_task_tree_summary(content: str, step: str = "", goal: str = "") -> str:
        first_line = next(
            (line.strip() for line in str(content or "").splitlines() if str(line or "").strip()),
            "",
        )
        for candidate in (
            _normalize_text(first_line, 200),
            _normalize_text(step, 200),
            _normalize_text(goal, 200),
        ):
            if candidate:
                return _normalize_text(candidate, 1000)
        return ""

    def _coerce_task_tree_sync_status(status: str) -> str:
        normalized = _normalize_text(status, 40).lower()
        if normalized in {"done", "completed", "complete", "finished", "resolved", "fixed"}:
            return "done"
        if normalized in {"verifying", "verified", "checking", "validation"}:
            return "verifying"
        if normalized in {"in_progress", "in-progress", "started", "working", "processing", "running"}:
            return "in_progress"
        if normalized in {"blocked", "failed", "error"}:
            return "blocked"
        return ""

    def _normalize_status(status: object) -> str:
        normalized = _normalize_text(status, 40).lower()
        if normalized in {"pending", "in_progress", "verifying", "blocked", "done"}:
            return normalized
        return _coerce_task_tree_sync_status(normalized) or "pending"

    def _synthesize_transition_verification(
        current_node: dict[str, Any],
        *,
        next_node: dict[str, Any] | None = None,
        next_step: str = "",
        next_phase: str = "",
    ) -> str:
        current_title = _normalize_text(current_node.get("title"), 200)
        current_summary = _normalize_text(
            current_node.get("verification_result")
            or current_node.get("summary_for_model")
            or current_node.get("latest_outcome")
            or current_node.get("objective")
            or current_node.get("description"),
            1000,
        )
        if current_summary:
            return _normalize_text(current_summary, 2000)
        next_title = _normalize_text((next_node or {}).get("title"), 200) or _normalize_text(next_step, 200)
        next_phase_value = _normalize_text(next_phase, 80)
        if current_title and next_title:
            return _normalize_text(
                f"系统收口：已进入“{next_title}”，视为“{current_title}”已完成。",
                2000,
            )
        if current_title and next_phase_value:
            return _normalize_text(
                f"系统收口：已进入 {next_phase_value} 阶段，视为“{current_title}”已完成。",
                2000,
            )
        if current_title:
            return _normalize_text(f"系统收口：{current_title} 已完成。", 2000)
        return _normalize_text("系统收口：当前步骤已完成。", 2000)

    def _sync_query_task_tree_from_structured_progress(
        *,
        project_id: str,
        status: str = "",
        content: str = "",
        phase: str = "",
        step: str = "",
        goal: str = "",
        verification: list[str] | None = None,
        chat_session_id: str = "",
    ) -> dict | None:
        normalized_project_id = _normalize_text(project_id, 120)
        normalized_status = _coerce_task_tree_sync_status(status)
        username, _fallback_chat_session_id = _resolve_task_tree_context()
        normalized_chat_session_id = _resolve_query_chat_session_id(chat_session_id)
        if not (normalized_project_id and normalized_status and username and normalized_chat_session_id):
            return None
        from services.project_chat_task_tree import get_task_tree_for_chat_session, update_task_node, serialize_task_tree

        def _finalize_serialized_payload(payload: dict | None) -> dict | None:
            if not isinstance(payload, dict):
                return payload
            progress_percent = int(payload.get("progress_percent") or 0)
            if _normalize_status(payload.get("status")) == "pending" and progress_percent > 0:
                payload = dict(payload)
                payload["status"] = "in_progress"
            return payload

        session = get_task_tree_for_chat_session(
            normalized_project_id,
            username,
            normalized_chat_session_id,
        )
        if session is None:
            return None
        serialized = serialize_task_tree(session) or {}
        current_node = serialized.get("current_node") if isinstance(serialized.get("current_node"), dict) else {}
        target_node = _select_query_task_tree_node(
            serialized,
            phase=phase,
            step=step,
        )
        node_id = _normalize_text(target_node.get("id"), 80)
        if not node_id:
            return serialized or None

        verification_items = _coerce_list_text(verification)
        verification_result = "；".join(verification_items)[:2000]
        summary_for_model = _synthesize_task_tree_summary(content, step=step, goal=goal)

        def finalize_root_if_ready(updated_session):
            serialized_session = serialize_task_tree(updated_session) or {}
            nodes = serialized_session.get("nodes") if isinstance(serialized_session.get("nodes"), list) else []
            if not nodes:
                return updated_session
            parent_ids = {
                _normalize_text(node.get("parent_id"), 80)
                for node in nodes
                if _normalize_text(node.get("parent_id"), 80)
            }
            leaf_nodes = [
                node for node in nodes
                if _normalize_text(node.get("id"), 80)
                and _normalize_text(node.get("parent_id"), 80)
                and _normalize_text(node.get("id"), 80) not in parent_ids
            ]
            if not leaf_nodes or any(_normalize_status(node.get("status")) != "done" for node in leaf_nodes):
                return updated_session
            root_node = next(
                (node for node in nodes if not _normalize_text(node.get("parent_id"), 80)),
                None,
            )
            if root_node is None or _normalize_status(root_node.get("status")) == "done":
                return updated_session
            if (
                _normalize_status(root_node.get("status")) == "pending"
                and any(_normalize_status(node.get("status")) != "pending" for node in leaf_nodes)
            ):
                updated_session = update_task_node(
                    project_id=normalized_project_id,
                    username=username,
                    chat_session_id=normalized_chat_session_id,
                    node_id=_normalize_text(root_node.get("id"), 80),
                    status="in_progress",
                    summary_for_model=_normalize_text(
                        serialized_session.get("root_goal") or serialized_session.get("title"),
                        1000,
                    ),
                )
                serialized_session = serialize_task_tree(updated_session) or {}
                nodes = serialized_session.get("nodes") if isinstance(serialized_session.get("nodes"), list) else []
                root_node = next(
                    (node for node in nodes if not _normalize_text(node.get("parent_id"), 80)),
                    None,
                )
                if root_node is None or _normalize_status(root_node.get("status")) == "done":
                    return updated_session
            root_summary = _normalize_text(
                summary_for_model,
                1000,
            ) or f"整体验证完成：{_normalize_text(serialized_session.get('root_goal') or serialized_session.get('title'), 200)}"
            root_verification = _normalize_text(
                verification_result,
                2000,
            ) or root_summary
            return update_task_node(
                project_id=normalized_project_id,
                username=username,
                chat_session_id=normalized_chat_session_id,
                node_id=_normalize_text(root_node.get("id"), 80),
                status="done",
                verification_result=root_verification,
                summary_for_model=root_summary,
                allow_direct_completion=True,
            )

        try:
            current_node_id = _normalize_text(current_node.get("id"), 80)
            target_is_new_phase = current_node_id and current_node_id != node_id
            current_verification_result = _normalize_text(current_node.get("verification_result"), 2000)
            if target_is_new_phase and _normalize_status(current_node.get("status")) != "done":
                transition_verification = current_verification_result or _synthesize_transition_verification(
                    current_node,
                    next_node=target_node,
                    next_step=step,
                    next_phase=phase,
                )
                transition_summary = _normalize_text(
                    current_node.get("summary_for_model"),
                    1000,
                ) or _normalize_text(transition_verification, 1000)
                session = update_task_node(
                    project_id=normalized_project_id,
                    username=username,
                    chat_session_id=normalized_chat_session_id,
                    node_id=current_node_id,
                    status="done",
                    verification_result=transition_verification,
                    summary_for_model=transition_summary,
                    is_current=False,
                    allow_direct_completion=True,
                )
            if normalized_status == "done":
                if not verification_result:
                    normalized_status = "verifying"
                else:
                    session = update_task_node(
                        project_id=normalized_project_id,
                        username=username,
                        chat_session_id=normalized_chat_session_id,
                        node_id=node_id,
                        status="done",
                        verification_result=verification_result,
                        summary_for_model=summary_for_model,
                        is_current=True,
                        allow_direct_completion=True,
                    )
                    session = finalize_root_if_ready(session)
                    return _finalize_serialized_payload(serialize_task_tree(session))
            session = update_task_node(
                project_id=normalized_project_id,
                username=username,
                chat_session_id=normalized_chat_session_id,
                node_id=node_id,
                status=normalized_status,
                verification_result=verification_result,
                summary_for_model=summary_for_model,
                is_current=True,
                allow_direct_completion=True,
            )
            return _finalize_serialized_payload(serialize_task_tree(session))
        except ValueError:
            fallback_session = get_task_tree_for_chat_session(
                normalized_project_id,
                username,
                normalized_chat_session_id,
            )
            return (
                _finalize_serialized_payload(serialize_task_tree(fallback_session))
                if fallback_session is not None
                else None
            )

    def _audit_query_task_tree(
        *,
        project_id: str,
        assistant_content: str,
        successful_tool_names: list[str] | None = None,
        chat_session_id: str = "",
    ) -> dict | None:
        project_id_value = _normalize_text(project_id, 120)
        assistant_content_value = _normalize_text(assistant_content, 4000)
        if not (project_id_value and assistant_content_value):
            return None
        username, _fallback_chat_session_id = _resolve_task_tree_context()
        chat_session_id_value = _resolve_query_chat_session_id(chat_session_id)
        if not (username and chat_session_id_value):
            return None
        from services.project_chat_task_tree import audit_task_tree_round

        return audit_task_tree_round(
            project_id=project_id_value,
            username=username,
            chat_session_id=chat_session_id_value,
            assistant_content=assistant_content_value,
            successful_tool_names=successful_tool_names or ["save_project_memory"],
        )

    def _get_existing_query_task_tree(
        *,
        project_id: str,
        chat_session_id: str = "",
    ) -> dict | None:
        project_id_value = _normalize_text(project_id, 120)
        if not project_id_value:
            return None
        bound_context = _current_query_session_context()
        username, fallback_chat_session_id = _resolve_task_tree_context()
        chat_session_id_value = _normalize_text(chat_session_id, 120) or _normalize_text(
            bound_context.get("chat_session_id"),
            120,
        )
        if not chat_session_id_value:
            chat_session_id_value = _normalize_text(fallback_chat_session_id, 120)
        if not (username and chat_session_id_value):
            return None
        from services.project_chat_task_tree import get_task_tree_for_chat_session, serialize_task_tree

        session = get_task_tree_for_chat_session(
            project_id_value,
            username,
            chat_session_id_value,
        )
        if session is None:
            return None
        return serialize_task_tree(session)

    def _attach_query_task_tree(
        payload: dict,
        *,
        root_goal: str,
        project_id: str = "",
        chat_session_id: str = "",
        max_steps: int | None = None,
        force: bool = False,
    ) -> dict:
        task_tree_payload = _ensure_query_task_tree(
            root_goal=root_goal,
            project_id=project_id,
            chat_session_id=chat_session_id,
            max_steps=max_steps,
            force=force,
        )
        if task_tree_payload is not None:
            payload["task_tree"] = task_tree_payload
        return payload

    def _find_latest_work_session_id_for_chat_session(
        *,
        project_id: str,
        chat_session_id: str,
    ) -> str:
        project_id_value = _normalize_text(project_id, 120)
        chat_session_id_value = _normalize_text(chat_session_id, 120)
        if not (project_id_value and chat_session_id_value):
            return ""
        try:
            events = work_session_store.list_events(
                project_id=project_id_value,
                session_id="",
                query="",
                limit=50,
            )
        except Exception:
            return ""
        for item in events or []:
            if _normalize_text(getattr(item, "task_tree_chat_session_id", ""), 120) != chat_session_id_value:
                continue
            session_id_value = _normalize_text(getattr(item, "session_id", ""), 160)
            if session_id_value:
                return session_id_value
        return ""

    def _build_query_workflow_guard(
        *,
        raw_request: str,
        project_id: str,
        chat_session_id: str,
        clarity_score: int,
        clarity_threshold: int,
        manual_loaded: bool,
        analysis_generated: bool,
        context_resolved: bool,
        plan_generated: bool,
        work_session_started: bool,
        task_tree_ready: bool,
        task_tree_matches_request: bool,
    ) -> dict:
        missing_steps: list[str] = []
        required_before_execution: list[str] = []
        backend_enforced_checks: list[str] = []

        raw_request_value = _normalize_text(raw_request, 2000)
        project_id_value = _normalize_text(project_id, 120)
        chat_session_id_value = _normalize_text(chat_session_id, 120)

        if raw_request_value:
            backend_enforced_checks.extend(["raw_request_present", "raw_request_search"])
        else:
            missing_steps.extend(["raw_request", "raw_request_search"])
            required_before_execution.extend(
                ["provide_raw_request", "call_search_ids_with_raw_request"]
            )

        if project_id_value:
            backend_enforced_checks.append("project_bound")
        else:
            missing_steps.append("project_id")
            required_before_execution.append("provide_project_id")

        if chat_session_id_value:
            backend_enforced_checks.append("chat_session_bound")
        else:
            missing_steps.append("chat_session_id")
            required_before_execution.append("provide_chat_session_id")

        if manual_loaded:
            backend_enforced_checks.append("manual_loaded")
        elif project_id_value:
            missing_steps.append("project_manual")
            required_before_execution.append("load_project_manual")

        if analysis_generated:
            backend_enforced_checks.append("analysis_generated")
        elif raw_request_value and project_id_value:
            missing_steps.append("analysis")
            required_before_execution.append("generate_analysis")

        if context_resolved:
            backend_enforced_checks.append("context_resolved")
        elif raw_request_value and project_id_value:
            missing_steps.append("relevant_context")
            required_before_execution.append("resolve_relevant_context")

        if plan_generated:
            backend_enforced_checks.append("plan_generated")
        elif raw_request_value and project_id_value:
            missing_steps.append("execution_plan")
            required_before_execution.append("generate_execution_plan")

        if work_session_started:
            backend_enforced_checks.append("work_session_started")

        if task_tree_ready:
            backend_enforced_checks.append("task_tree_bound")
        elif project_id_value and chat_session_id_value:
            missing_steps.append("task_tree_binding")
            required_before_execution.append("bind_project_context")

        if task_tree_matches_request:
            backend_enforced_checks.append("task_tree_matches_request")
        elif task_tree_ready:
            missing_steps.append("fresh_chat_session_id")
            required_before_execution.append("create_new_chat_session_id_and_rebind")

        missing_steps = list(dict.fromkeys(missing_steps))
        required_before_execution = list(dict.fromkeys(required_before_execution))
        backend_enforced_checks = list(dict.fromkeys(backend_enforced_checks))

        if missing_steps:
            return {
                "status": "blocked",
                "missing_steps": missing_steps,
                "blocked_reason": "缺少项目绑定、原始问题登记或关键前置步骤，不能进入实现。",
                "required_before_execution": required_before_execution,
                "clarity_score": clarity_score,
                "clarity_threshold": clarity_threshold,
            }, backend_enforced_checks

        if clarity_score < clarity_threshold:
            return {
                "status": "needs_confirmation",
                "missing_steps": [],
                "blocked_reason": (
                    f"当前需求清晰度为 {clarity_score}/{clarity_threshold}，"
                    "需要先补齐目标、对象、范围或预期结果。"
                ),
                "required_before_execution": [
                    "clarify_goal_scope_expected_result",
                    "reinvoke_start_project_workflow",
                ],
                "clarity_score": clarity_score,
                "clarity_threshold": clarity_threshold,
            }, backend_enforced_checks

        return {
            "status": "ready",
            "missing_steps": [],
            "blocked_reason": "",
            "required_before_execution": [],
            "clarity_score": clarity_score,
            "clarity_threshold": clarity_threshold,
        }, backend_enforced_checks

    def _start_project_workflow_payload(
        *,
        raw_request: str,
        project_id: str = "",
        chat_session_id: str = "",
        workspace_path: str = "",
        client_profile: str = "codex",
        employee_id: str = "",
        clarity_score: int = 3,
        start_session: bool = True,
        session_id: str = "",
        max_steps: int = 6,
    ) -> dict:
        raw_request_value = _normalize_text(raw_request, 2000)
        project_id_value = _normalize_text(project_id, 120)
        chat_session_id_value = _normalize_text(chat_session_id, 120)
        workspace_path_value = _normalize_text(workspace_path, 1000)
        employee_id_value = _normalize_text(employee_id, 120)
        client_profile_value = _normalize_text(client_profile, 80) or "codex"
        threshold = _query_mcp_clarity_confirm_threshold()
        try:
            clarity_value = max(1, min(int(clarity_score), 5))
        except (TypeError, ValueError):
            clarity_value = threshold
        try:
            max_steps_value = max(1, min(int(max_steps or 6), 10))
        except (TypeError, ValueError):
            max_steps_value = 6

        lookup_payload = {
            "keyword": raw_request_value,
            "project_id": project_id_value,
            "employee_id": employee_id_value,
            "projects": [],
            "employees": [],
            "rules": [],
        }
        if raw_request_value:
            lookup_payload = search_ids(
                keyword=raw_request_value,
                project_id=project_id_value,
                employee_id=employee_id_value,
                limit=10,
            )

        manual_payload: dict = {}
        manual_loaded = False
        if project_id_value:
            manual_payload = get_manual_content(project_id=project_id_value)
            manual_loaded = not bool(manual_payload.get("error")) and bool(
                _normalize_text(manual_payload.get("manual"), 200)
            )

        binding_payload: dict = {}
        task_tree_payload: dict | None = None
        task_tree_matches_request = False
        if project_id_value and chat_session_id_value:
            binding_payload = bind_project_context(
                project_id=project_id_value,
                chat_session_id=chat_session_id_value,
                root_goal=raw_request_value,
                workspace_path=workspace_path_value,
            )
            if isinstance(binding_payload.get("task_tree"), dict):
                task_tree_payload = binding_payload.get("task_tree")
        elif project_id_value:
            task_tree_payload = _get_existing_query_task_tree(
                project_id=project_id_value,
                chat_session_id=chat_session_id_value,
            )

        if task_tree_payload is None and project_id_value and chat_session_id_value and raw_request_value:
            task_tree_payload = _ensure_or_reuse_query_task_tree(
                project_id=project_id_value,
                chat_session_id=chat_session_id_value,
                root_goal=raw_request_value,
            )

        current_node = (
            task_tree_payload.get("current_node")
            if isinstance((task_tree_payload or {}).get("current_node"), dict)
            else {}
        )
        task_tree_goal = _normalize_text(
            (task_tree_payload or {}).get("root_goal") or (task_tree_payload or {}).get("title"),
            1000,
        )
        task_tree_matches_request = bool(
            task_tree_goal and raw_request_value and task_tree_goal == raw_request_value
        )

        analysis_payload = (
            _analyze_task_payload(
                raw_request_value,
                project_id=project_id_value,
                employee_id=employee_id_value,
            )
            if raw_request_value
            else {}
        )
        relevant_context_payload = (
            _resolve_relevant_context_payload(
                raw_request_value,
                project_id=project_id_value,
                employee_id=employee_id_value,
                limit=min(max_steps_value, 10),
            )
            if raw_request_value
            else {}
        )
        execution_plan_payload = (
            _generate_execution_plan_payload(
                raw_request_value,
                project_id=project_id_value,
                employee_id=employee_id_value,
                max_steps=max_steps_value,
            )
            if raw_request_value
            else {}
        )

        resolved_session_id = _normalize_text(session_id, 160)
        session_result: dict = {}
        latest_session_id = ""
        if project_id_value and chat_session_id_value:
            latest_session_id = _find_latest_work_session_id_for_chat_session(
                project_id=project_id_value,
                chat_session_id=chat_session_id_value,
            )
        if not resolved_session_id:
            resolved_session_id = latest_session_id
        if (
            start_session
            and not resolved_session_id
            and raw_request_value
            and project_id_value
            and chat_session_id_value
            and clarity_value >= threshold
        ):
            session_result = start_work_session(
                project_id=project_id_value,
                employee_id=employee_id_value,
                goal=raw_request_value,
                title=raw_request_value[:120],
                chat_session_id=chat_session_id_value,
                workspace_path=workspace_path_value,
                phase="analysis",
                step="start_project_workflow",
                status="started",
            )
            if not session_result.get("error"):
                resolved_session_id = _normalize_text(session_result.get("session_id"), 160)

        task_tree_available = isinstance(task_tree_payload, dict)
        guard, backend_checks = _build_query_workflow_guard(
            raw_request=raw_request_value,
            project_id=project_id_value,
            chat_session_id=chat_session_id_value,
            clarity_score=clarity_value,
            clarity_threshold=threshold,
            manual_loaded=manual_loaded,
            analysis_generated=bool(analysis_payload),
            context_resolved=bool(relevant_context_payload),
            plan_generated=bool(execution_plan_payload),
            work_session_started=bool(resolved_session_id),
            task_tree_ready=task_tree_available,
            task_tree_matches_request=task_tree_matches_request,
        )

        status = _normalize_text(guard.get("status"), 40) or "blocked"
        if status == "blocked":
            next_required_actions = [
                "补齐 project_id 和 chat_session_id 后重新调用 start_project_workflow"
            ]
            if "raw_request" in (guard.get("missing_steps") or []):
                next_required_actions.insert(0, "保留用户原始问题原文并重新调用 start_project_workflow")
        elif status == "needs_confirmation":
            next_required_actions = [
                "先确认目标、对象、范围和预期结果",
                "确认后使用同一 raw_request/project_id/chat_session_id 重新调用 start_project_workflow",
            ]
        else:
            next_required_actions = [
                "mark_current_task_node_in_progress",
                "perform_file_edits",
                "run_targeted_verification",
            ]
            if not {"get_current_task_tree", "update_task_node_status", "complete_task_node_with_verification"}.issubset(_QUERY_TOOL_NAMES):
                next_required_actions.append("任务树闭环未完成：当前宿主未暴露任务树推进工具")
            else:
                next_required_actions.append("complete_task_node_with_verification")

        task_tree_summary = {
            "available": task_tree_available,
            "task_tree_closure_supported": {
                "get_current_task_tree",
                "update_task_node_status",
                "complete_task_node_with_verification",
            }.issubset(_QUERY_TOOL_NAMES),
            "matches_current_request": task_tree_matches_request,
            "id": _normalize_text((task_tree_payload or {}).get("id"), 80),
            "current_node_id": _normalize_text(current_node.get("id"), 80),
            "current_node_title": _normalize_text(current_node.get("title"), 200),
            "current_node_status": _normalize_text(current_node.get("status"), 40),
            "chat_session_id": _normalize_text(
                (task_tree_payload or {}).get("chat_session_id"),
                120,
            ),
            "root_goal": task_tree_goal,
        }

        return {
            "status": status,
            "project_id": project_id_value,
            "chat_session_id": chat_session_id_value,
            "session_id": resolved_session_id,
            "workflow_version": "query-mcp-workflow/v1",
            "client_profile": client_profile_value,
            "clarity_score": clarity_value,
            "clarity_threshold": threshold,
            "id_lookup": lookup_payload,
            "manual": manual_payload,
            "analysis": analysis_payload,
            "relevant_context": relevant_context_payload,
            "execution_plan": execution_plan_payload,
            "task_tree": task_tree_summary,
            "task_tree_binding": binding_payload,
            "work_session": session_result,
            "guard": guard,
            "next_required_actions": next_required_actions,
            "backend_enforced_checks": backend_checks,
        }

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
        return build_query_usage_guide_text()

    @mcp.resource("query://client-profile/claude-code")
    def query_client_profile_claude_code() -> str:
        return build_query_client_profile_text("claude-code")

    @mcp.resource("query://client-profile/codex")
    def query_client_profile_codex() -> str:
        return build_query_client_profile_text("codex")

    @mcp.resource("query://client-profile/generic-cli")
    def query_client_profile_generic_cli() -> str:
        return build_query_client_profile_text("generic-cli")

    @mcp.tool()
    def bind_project_context(
        project_id: str,
        project_name: str = "",
        chat_session_id: str = "",
        root_goal: str = "",
        workspace_path: str = "",
    ) -> dict:
        """绑定当前统一查询 MCP 会话到指定项目/聊天，并可选立即创建任务树。"""

        project_id_value = _normalize_text(project_id, 120)
        if not project_id_value:
            return {"error": "project_id is required"}
        project = project_store.get(project_id_value)
        if project is None:
            return {"error": f"Project {project_id_value} not found"}

        normalized_project_name = _normalize_text(project_name, 160) or str(
            getattr(project, "name", "") or ""
        ).strip()
        session_binding_key = ""
        if current_mcp_session_id_ctx is not None:
            session_binding_key = str(current_mcp_session_id_ctx.get("") or "").strip()
        normalized_chat_session_id = _normalize_text(chat_session_id, 120) or session_binding_key
        root_goal_value = _normalize_text(root_goal, 1000)
        workspace_path_value = _normalize_text(workspace_path, 1000)
        local_bootstrap_payload = {}
        local_state_payload = {}
        task_tree_payload = None
        if normalized_chat_session_id and root_goal_value:
            from services.project_chat_task_tree import ensure_task_tree, serialize_task_tree

            username, _ = _resolve_task_tree_context()
            session = ensure_task_tree(
                project_id=project_id_value,
                username=username,
                chat_session_id=normalized_chat_session_id,
                root_goal=root_goal_value,
            )
            task_tree_payload = serialize_task_tree(session)
        if normalized_chat_session_id:
            local_bootstrap_payload = bootstrap_query_mcp_local_workspace(
                project_id=project_id_value,
                chat_session_id=normalized_chat_session_id,
                workspace_path=workspace_path_value,
                project_name=normalized_project_name,
                root_goal=root_goal_value,
                latest_status="bound",
                phase="binding",
                step="bind_project_context",
                source="bind_project_context",
                sync_status="idle",
                task_tree_payload=task_tree_payload,
            )
            local_state_payload = persist_query_mcp_local_state(
                project_id=project_id_value,
                chat_session_id=normalized_chat_session_id,
                workspace_path=workspace_path_value,
                project_name=normalized_project_name,
                root_goal=root_goal_value,
                latest_status="bound",
                phase="binding",
                step="bind_project_context",
                source="bind_project_context",
                task_tree_payload=task_tree_payload,
            )

        if not session_binding_key or session_contexts is None:
            if not normalized_chat_session_id:
                return {
                    "error": "Current MCP session is missing; provide chat_session_id explicitly for detached binding",
                }
            payload = {
                "status": "bound_detached",
                "project_id": project_id_value,
                "project_name": normalized_project_name,
                "session_id": session_binding_key,
                "chat_session_id": normalized_chat_session_id,
                "binding_mode": "detached",
                "warning": "Active MCP session is unavailable; continue by explicitly reusing project_id and chat_session_id in subsequent calls.",
            }
            if task_tree_payload is not None:
                payload["task_tree"] = task_tree_payload
            if local_bootstrap_payload:
                payload["local_bootstrap"] = local_bootstrap_payload
            if local_state_payload:
                payload["local_state"] = local_state_payload
            return payload

        session_contexts[session_binding_key] = {
            "project_id": project_id_value,
            "project_name": normalized_project_name,
            "employee_id": str((session_contexts.get(session_binding_key) or {}).get("employee_id") or "").strip(),
            "chat_session_id": normalized_chat_session_id,
        }

        payload = {
            "status": "bound",
            "project_id": project_id_value,
            "project_name": normalized_project_name,
            "session_id": session_binding_key,
            "chat_session_id": normalized_chat_session_id,
        }

        if session_binding_key and normalized_chat_session_id and session_binding_key != normalized_chat_session_id:
            from services.project_chat_task_tree import rebind_task_tree_chat_session

            username, _ = _resolve_task_tree_context()
            migrated_session = rebind_task_tree_chat_session(
                project_id=project_id_value,
                username=username,
                from_chat_session_id=session_binding_key,
                to_chat_session_id=normalized_chat_session_id,
                root_goal=root_goal_value,
            )
            if migrated_session is not None:
                payload["shadow_task_tree_rebound"] = True

        if task_tree_payload is not None:
            payload["task_tree"] = task_tree_payload
        if local_bootstrap_payload:
            payload["local_bootstrap"] = local_bootstrap_payload
        if local_state_payload:
            payload["local_state"] = local_state_payload
        return payload

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
    def get_current_task_tree(project_id: str = "", chat_session_id: str = "") -> dict:
        """读取当前项目 / 会话绑定的任务树。"""

        project_id_value = _resolve_query_project_id(project_id)
        chat_session_id_value = _resolve_query_chat_session_id(chat_session_id)
        if not project_id_value:
            return {"error": "project_id is required"}
        if not chat_session_id_value:
            return {"error": "chat_session_id is required"}

        from services.project_chat_task_tree import get_task_tree_tool_payload

        username, _ = _resolve_task_tree_context()
        payload = get_task_tree_tool_payload(
            project_id=project_id_value,
            username=username,
            chat_session_id=chat_session_id_value,
        )
        if payload.get("error"):
            return {
                **payload,
                "project_id": project_id_value,
                "chat_session_id": chat_session_id_value,
            }
        payload["project_id"] = project_id_value
        payload["chat_session_id"] = _normalize_text(
            payload.get("chat_session_id"),
            120,
        ) or chat_session_id_value
        return payload

    @mcp.tool()
    def update_task_node_status(
        project_id: str = "",
        node_id: str = "",
        status: str = "",
        chat_session_id: str = "",
        summary_for_model: str = "",
        verification_result: str = "",
        is_current: bool | None = None,
    ) -> dict:
        """推进任务树节点状态。"""

        project_id_value = _resolve_query_project_id(project_id)
        chat_session_id_value = _resolve_query_chat_session_id(chat_session_id)
        node_id_value = _normalize_text(node_id, 80)
        status_value = _normalize_text(status, 40)
        if not project_id_value:
            return {"error": "project_id is required"}
        if not chat_session_id_value:
            return {"error": "chat_session_id is required"}
        if not node_id_value:
            return {"error": "node_id is required"}
        if not status_value:
            return {"error": "status is required"}

        from services.project_chat_task_tree import update_task_tree_node_tool_payload

        username, _ = _resolve_task_tree_context()
        try:
            payload = update_task_tree_node_tool_payload(
                project_id=project_id_value,
                username=username,
                chat_session_id=chat_session_id_value,
                node_id=node_id_value,
                status=status_value,
                verification_result=_normalize_text(verification_result, 2000),
                summary_for_model=_normalize_text(summary_for_model, 1000),
                is_current=is_current,
            )
        except ValueError as exc:
            return {
                "error": str(exc),
                "project_id": project_id_value,
                "chat_session_id": chat_session_id_value,
                "node_id": node_id_value,
                "status": status_value,
            }
        if isinstance(payload, dict):
            payload["project_id"] = project_id_value
            payload["chat_session_id"] = _normalize_text(
                payload.get("chat_session_id"),
                120,
            ) or chat_session_id_value
        return payload

    @mcp.tool()
    def complete_task_node_with_verification(
        project_id: str = "",
        node_id: str = "",
        verification_result: str = "",
        chat_session_id: str = "",
        summary_for_model: str = "",
        is_current: bool | None = None,
    ) -> dict:
        """完成任务树节点并写入验证结果。"""

        project_id_value = _resolve_query_project_id(project_id)
        chat_session_id_value = _resolve_query_chat_session_id(chat_session_id)
        node_id_value = _normalize_text(node_id, 80)
        verification_result_value = _normalize_text(verification_result, 2000)
        if not project_id_value:
            return {"error": "project_id is required"}
        if not chat_session_id_value:
            return {"error": "chat_session_id is required"}
        if not node_id_value:
            return {"error": "node_id is required"}
        if not verification_result_value:
            return {"error": "verification_result is required"}

        from services.project_chat_task_tree import archive_task_tree, serialize_task_tree, update_task_node

        username, _ = _resolve_task_tree_context()
        try:
            session = update_task_node(
                project_id=project_id_value,
                username=username,
                chat_session_id=chat_session_id_value,
                node_id=node_id_value,
                status="done",
                verification_result=verification_result_value,
                summary_for_model=_normalize_text(summary_for_model, 1000),
                is_current=is_current,
                allow_direct_completion=True,
            )
        except ValueError as exc:
            return {
                "error": str(exc),
                "project_id": project_id_value,
                "chat_session_id": chat_session_id_value,
                "node_id": node_id_value,
            }

        if _normalize_status(getattr(session, "status", "")) == "done":
            archived_session = archive_task_tree(
                session,
                reason="completed_task_closed",
                delete_current=True,
            )
            archived_payload = serialize_task_tree(archived_session) or {}
            return {
                "status": "completed",
                "project_id": project_id_value,
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
        payload["project_id"] = project_id_value
        payload["node_id"] = node_id_value
        payload["chat_session_id"] = _normalize_text(
            payload.get("chat_session_id"),
            120,
        ) or chat_session_id_value
        return payload

    @mcp.tool()
    def start_project_workflow(
        raw_request: str = "",
        project_id: str = "",
        chat_session_id: str = "",
        workspace_path: str = "",
        client_profile: str = "codex",
        employee_id: str = "",
        clarity_score: int = 3,
        start_session: bool = True,
        session_id: str = "",
        max_steps: int = 6,
    ) -> dict:
        """固定入口：统一完成项目绑定、分析、上下文聚合、执行计划与 guard 校验。"""

        return _start_project_workflow_payload(
            raw_request=raw_request,
            project_id=project_id,
            chat_session_id=chat_session_id,
            workspace_path=workspace_path,
            client_profile=client_profile,
            employee_id=employee_id,
            clarity_score=clarity_score,
            start_session=start_session,
            session_id=session_id,
            max_steps=max_steps,
        )

    @mcp.tool()
    def analyze_task(raw_request: str, project_id: str = "", employee_id: str = "") -> dict:
        """对用户原始任务做结构化分析，输出类型、范围、约束和建议下一步。"""

        raw_request_value = _normalize_text(raw_request)
        if not raw_request_value:
            return {"error": "raw_request is required"}
        return _attach_query_task_tree(
            _analyze_task_payload(
                raw_request_value,
                project_id=project_id,
                employee_id=employee_id,
            ),
            root_goal=raw_request_value,
            project_id=project_id,
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
        result = {
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
        return result

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
        return _attach_query_task_tree(
            _resolve_relevant_context_payload(
                task_value,
                project_id=project_id,
                employee_id=employee_id,
                limit=limit,
            ),
            root_goal=task_value,
            project_id=project_id,
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
        return _attach_query_task_tree(
            _generate_execution_plan_payload(
                task_value,
                project_id=project_id,
                employee_id=employee_id,
                max_steps=max_steps,
            ),
            root_goal=task_value,
            project_id=project_id,
            max_steps=max_steps,
            force=True,
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
    def start_work_session(
        project_id: str,
        employee_id: str = "",
        project_name: str = "",
        title: str = "",
        goal: str = "",
        chat_session_id: str = "",
        workspace_path: str = "",
        phase: str = "",
        step: str = "",
        status: str = "started",
    ) -> dict:
        """启动一条新的工作会话，并返回服务端生成的 session_id。"""

        project_id_value = _normalize_text(project_id)
        if not project_id_value:
            return {"error": "project_id is required"}
        active_employee_ids = _active_project_employee_ids(project_id_value)
        if not active_employee_ids:
            return {"error": f"Project {project_id_value} has no active members"}
        employee_id_value = _normalize_text(employee_id)
        if employee_id_value and employee_id_value not in active_employee_ids:
            return {"error": f"Employee {employee_id_value} is not an active project member"}
        session_id_value = _generate_work_session_id(
            project_id=project_id_value,
            employee_id=employee_id_value,
        )
        project_name_value = _resolve_project_name(project_id_value, project_name)
        chat_session_id_value = _resolve_query_chat_session_id(chat_session_id) or session_id_value
        workspace_path_value = _normalize_text(workspace_path, 1000)
        task_tree_payload = _ensure_query_task_tree(
            root_goal=_normalize_text(goal) or _normalize_text(title) or _normalize_text(step),
            project_id=project_id_value,
            chat_session_id=chat_session_id_value,
        )
        local_bootstrap_payload = bootstrap_query_mcp_local_workspace(
            project_id=project_id_value,
            chat_session_id=chat_session_id_value,
            workspace_path=workspace_path_value,
            project_name=project_name_value,
            session_id=session_id_value,
            root_goal=_normalize_text(goal),
            latest_status=_normalize_text(status) or "started",
            phase=phase,
            step=step,
            source="start_work_session",
            sync_status="idle",
            task_tree_payload=task_tree_payload,
        )
        local_state_payload = persist_query_mcp_local_state(
            project_id=project_id_value,
            chat_session_id=chat_session_id_value,
            workspace_path=workspace_path_value,
            project_name=project_name_value,
            employee_id=employee_id_value,
            session_id=session_id_value,
            root_goal=_normalize_text(goal),
            latest_status=_normalize_text(status) or "started",
            phase=phase,
            step=step,
            source="start_work_session",
            task_tree_payload=task_tree_payload,
        )
        task_tree_binding = _resolve_query_task_tree_binding(
            project_id=project_id_value,
            chat_session_id=chat_session_id_value,
            phase=phase,
            step=step,
        )
        if not task_tree_binding:
            task_tree_binding = _fallback_query_task_tree_binding(
                task_tree_payload=task_tree_payload,
                chat_session_id=chat_session_id_value,
            )
        trajectory = _structured_trajectory_payload(
            kind="session-start",
            session_id=session_id_value,
            task_tree_session_id=task_tree_binding.get("task_tree_session_id", ""),
            task_tree_chat_session_id=task_tree_binding.get("task_tree_chat_session_id", ""),
            task_node_id=task_tree_binding.get("task_node_id", ""),
            task_node_title=task_tree_binding.get("task_node_title", ""),
            event_type="start",
            phase=phase,
            step=step,
            status=status or "started",
            goal=goal,
            content=_normalize_text(title) or "Work session started",
        )
        work_session_event = _save_work_session_event_record(
            project_id=project_id_value,
            project_name=project_name_value,
            employee_id=employee_id_value,
            trajectory=trajectory,
        )
        result = {
            "status": "started",
            "project_id": project_id_value,
            "project_name": project_name_value,
            "employee_id": employee_id_value,
            "session_id": session_id_value,
            "chat_session_id": chat_session_id_value,
            "title": _normalize_text(title),
            "goal": _normalize_text(goal),
            "phase": _normalize_text(phase),
            "step": _normalize_text(step),
            "initial_status": _normalize_text(status) or "started",
            "trajectory": trajectory,
            "work_session_event": work_session_event,
            "recommended_next_tool": "save_work_facts",
            "message": "Use this session_id for subsequent save_work_facts, append_session_event, resume_work_session and summarize_checkpoint calls.",
        }
        if local_bootstrap_payload:
            result["local_bootstrap"] = local_bootstrap_payload
        if local_state_payload:
            result["local_state"] = local_state_payload
        if task_tree_payload is not None:
            result["task_tree"] = task_tree_payload
        return result

    @mcp.tool()
    def save_work_facts(
        project_id: str,
        facts: list[str] | str | None = None,
        content: str = "",
        employee_id: str = "",
        importance: float = 0.7,
        project_name: str = "",
        session_id: str = "",
        chat_session_id: str = "",
        phase: str = "",
        step: str = "",
        status: str = "",
        goal: str = "",
        changed_files: list[str] | str | None = None,
        verification: list[str] | str | None = None,
        risks: list[str] | str | None = None,
        next_steps: list[str] | str | None = None,
    ) -> dict:
        """保存工作事实，供后续恢复、检查点摘要和长期任务续跑使用。"""

        fact_items = _parse_fact_lines(content=content, facts=facts)
        if not fact_items:
            return {"error": "Provide at least one fact in facts or content"}
        session_id_value = _normalize_text(session_id) or _generate_work_session_id(
            project_id=project_id,
            employee_id=employee_id,
        )
        chat_session_id_value = _resolve_query_chat_session_id(chat_session_id) or session_id_value
        existing_task_tree_payload = _load_query_task_tree_for_progress(
            project_id=project_id,
            chat_session_id=chat_session_id_value,
            root_goal=goal,
        )
        task_tree_binding = _resolve_query_task_tree_binding(
            project_id=project_id,
            chat_session_id=chat_session_id_value,
            phase=phase,
            step=step,
        )
        if not task_tree_binding:
            task_tree_binding = _fallback_query_task_tree_binding(
                task_tree_payload=existing_task_tree_payload,
                chat_session_id=chat_session_id_value,
            )
        trajectory = _structured_trajectory_payload(
            kind="work-facts",
            session_id=session_id_value,
            task_tree_session_id=task_tree_binding.get("task_tree_session_id", ""),
            task_tree_chat_session_id=task_tree_binding.get("task_tree_chat_session_id", ""),
            task_node_id=task_tree_binding.get("task_node_id", ""),
            task_node_title=task_tree_binding.get("task_node_title", ""),
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
        rendered_with_session = _append_memory_chat_session(rendered, chat_session_id_value)
        purpose_tags = _trajectory_purpose_tags(
            base_tags=("query-mcp", "work-facts", "phase3"),
            session_id=session_id_value,
            phase=phase,
            step=step,
        )
        local_entry = append_query_mcp_progress_outbox(
            project_id=project_id,
            project_name=project_name,
            employee_id=employee_id,
            chat_session_id=chat_session_id_value,
            session_id=session_id_value,
            root_goal=goal,
            latest_status=status,
            phase=phase,
            step=step,
            source_kind="work-facts",
            memory_type=MemoryType.LEARNED_PATTERN.value,
            content=rendered_with_session,
            importance=importance,
            purpose_tags=purpose_tags,
            trajectory=trajectory,
            task_tree_payload=existing_task_tree_payload,
        )
        if local_entry:
            saved_work_session_event = _save_work_session_event_record(
                project_id=project_id,
                project_name=project_name,
                employee_id=employee_id,
                trajectory=trajectory,
            )
            mark_query_mcp_outbox_work_session_event(
                project_id=project_id,
                chat_session_id=chat_session_id_value,
                event_id=_normalize_text(local_entry.get("event_id")),
                work_session_event_id=_normalize_text(saved_work_session_event.get("event_id")),
            )
            result = {
                "status": "saved",
                "project_id": _normalize_text(project_id),
                "project_name": _resolve_project_name(project_id, project_name),
                "employee_ids": [_normalize_text(employee_id)] if _normalize_text(employee_id) else [],
                "memory_ids": [],
                "saved_count": 1,
                "skipped_employee_ids": [],
                "duplicate_skipped": False,
                "type": MemoryType.LEARNED_PATTERN.value,
                "scope": "local-outbox",
                "importance": max(0.0, min(float(importance), 1.0)),
                "project_mcp_path": f"/mcp/projects/{_normalize_text(project_id)}",
                "session_id": session_id_value,
                "chat_session_id": chat_session_id_value,
                "trajectory": trajectory,
                "work_session_event": saved_work_session_event,
                "sync_status": "pending",
                "storage": "local-outbox",
                "local_event_id": _normalize_text(local_entry.get("event_id")),
            }
            if _should_flush_local_progress(status):
                flush_result = _flush_local_progress_outbox(
                    project_id=project_id,
                    chat_session_id=chat_session_id_value,
                )
                result["sync_status"] = _normalize_text(flush_result.get("status"), 40) or "pending"
                result["memory_ids"] = _coerce_list_text(flush_result.get("memory_ids"))
                result["saved_count"] = max(result["saved_count"], int(flush_result.get("saved_count") or 0))
                result["skipped_employee_ids"] = _coerce_list_text(flush_result.get("skipped_employee_ids"))
                result["work_session_event"] = (
                    flush_result.get("work_session_event")
                    if isinstance(flush_result.get("work_session_event"), dict)
                    else result["work_session_event"]
                )
                if flush_result.get("task_tree") is not None:
                    result["task_tree"] = flush_result.get("task_tree")
                elif _should_flush_local_progress(status):
                    task_tree_payload = _sync_query_task_tree_from_structured_progress(
                        project_id=project_id,
                        status=status,
                        content=rendered_with_session,
                        phase=phase,
                        step=step,
                        goal=goal,
                        verification=verification,
                        chat_session_id=chat_session_id_value,
                    )
                    if task_tree_payload is None:
                        task_tree_payload = _get_existing_query_task_tree(
                            project_id=project_id,
                            chat_session_id=chat_session_id_value,
                        )
                    if task_tree_payload is not None:
                        result["task_tree"] = task_tree_payload
                if flush_result.get("error"):
                    result["sync_error"] = _normalize_text(flush_result.get("error"), 400)
            else:
                task_tree_payload = _sync_query_task_tree_from_structured_progress(
                    project_id=project_id,
                    status=status,
                    content=rendered_with_session,
                    phase=phase,
                    step=step,
                    goal=goal,
                    verification=verification,
                    chat_session_id=chat_session_id_value,
                )
                if task_tree_payload is None:
                    task_tree_payload = _get_existing_query_task_tree(
                        project_id=project_id,
                        chat_session_id=chat_session_id_value,
                    )
                if task_tree_payload is not None:
                    result["task_tree"] = task_tree_payload
            if result.get("task_tree") is not None:
                upsert_query_mcp_requirement_record(
                    project_id=_normalize_text(project_id),
                    project_name=_resolve_project_name(project_id, project_name),
                    chat_session_id=chat_session_id_value,
                    session_id=session_id_value,
                    root_goal=goal,
                    latest_status=status,
                    phase=phase,
                    step=step,
                    source="save_work_facts",
                    sync_status=_normalize_text(result.get("sync_status"), 40),
                    task_tree_payload=result.get("task_tree"),
                )
            return result
        result = _save_project_memory_entries(
            project_id=project_id,
            employee_id=employee_id,
            content=rendered_with_session,
            memory_type=MemoryType.LEARNED_PATTERN,
            importance=importance,
            project_name=project_name,
            purpose_tags=purpose_tags,
        )
        if not result.get("error"):
            result["session_id"] = session_id_value
            result["chat_session_id"] = chat_session_id_value
            result["trajectory"] = trajectory
            result["work_session_event"] = _save_work_session_event_record(
                project_id=project_id,
                project_name=project_name,
                employee_id=employee_id,
                trajectory=trajectory,
            )
            task_tree_payload = _sync_query_task_tree_from_structured_progress(
                project_id=project_id,
                status=status,
                content=rendered_with_session,
                phase=phase,
                step=step,
                goal=goal,
                verification=verification,
                chat_session_id=chat_session_id_value,
            )
            if task_tree_payload is None:
                task_tree_payload = _get_existing_query_task_tree(
                    project_id=project_id,
                    chat_session_id=chat_session_id_value,
                )
            if task_tree_payload is not None:
                result["task_tree"] = task_tree_payload
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
        chat_session_id: str = "",
        phase: str = "",
        step: str = "",
        status: str = "",
        goal: str = "",
        changed_files: list[str] | str | None = None,
        verification: list[str] | str | None = None,
        risks: list[str] | str | None = None,
        next_steps: list[str] | str | None = None,
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
        chat_session_id_value = _resolve_query_chat_session_id(chat_session_id) or session_id_value
        existing_task_tree_payload = _load_query_task_tree_for_progress(
            project_id=project_id,
            chat_session_id=chat_session_id_value,
            root_goal=goal,
        )
        task_tree_binding = _resolve_query_task_tree_binding(
            project_id=project_id,
            chat_session_id=chat_session_id_value,
            phase=phase,
            step=step,
        )
        if not task_tree_binding:
            task_tree_binding = _fallback_query_task_tree_binding(
                task_tree_payload=existing_task_tree_payload,
                chat_session_id=chat_session_id_value,
            )
        trajectory = _structured_trajectory_payload(
            kind="session-event",
            session_id=session_id_value,
            task_tree_session_id=task_tree_binding.get("task_tree_session_id", ""),
            task_tree_chat_session_id=task_tree_binding.get("task_tree_chat_session_id", ""),
            task_node_id=task_tree_binding.get("task_node_id", ""),
            task_node_title=task_tree_binding.get("task_node_title", ""),
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
        rendered_with_session = _append_memory_chat_session(rendered, chat_session_id_value)
        purpose_tags = _trajectory_purpose_tags(
            base_tags=("query-mcp", "session-event", event_type_value, "phase3"),
            session_id=session_id_value,
            phase=phase,
            step=step,
        )
        local_entry = append_query_mcp_progress_outbox(
            project_id=project_id,
            project_name=project_name,
            employee_id=employee_id,
            chat_session_id=chat_session_id_value,
            session_id=session_id_value,
            root_goal=goal,
            latest_status=status,
            phase=phase,
            step=step,
            source_kind="session-event",
            memory_type=MemoryType.KEY_EVENT.value,
            content=rendered_with_session,
            importance=importance,
            purpose_tags=purpose_tags,
            trajectory=trajectory,
            task_tree_payload=existing_task_tree_payload,
        )
        if local_entry:
            saved_work_session_event = _save_work_session_event_record(
                project_id=project_id,
                project_name=project_name,
                employee_id=employee_id,
                trajectory=trajectory,
            )
            mark_query_mcp_outbox_work_session_event(
                project_id=project_id,
                chat_session_id=chat_session_id_value,
                event_id=_normalize_text(local_entry.get("event_id")),
                work_session_event_id=_normalize_text(saved_work_session_event.get("event_id")),
            )
            result = {
                "status": "saved",
                "project_id": _normalize_text(project_id),
                "project_name": _resolve_project_name(project_id, project_name),
                "employee_ids": [_normalize_text(employee_id)] if _normalize_text(employee_id) else [],
                "memory_ids": [],
                "saved_count": 1,
                "skipped_employee_ids": [],
                "duplicate_skipped": False,
                "type": MemoryType.KEY_EVENT.value,
                "scope": "local-outbox",
                "importance": max(0.0, min(float(importance), 1.0)),
                "project_mcp_path": f"/mcp/projects/{_normalize_text(project_id)}",
                "chat_session_id": chat_session_id_value,
                "trajectory": trajectory,
                "work_session_event": saved_work_session_event,
                "sync_status": "pending",
                "storage": "local-outbox",
                "local_event_id": _normalize_text(local_entry.get("event_id")),
            }
            if _should_flush_local_progress(status):
                flush_result = _flush_local_progress_outbox(
                    project_id=project_id,
                    chat_session_id=chat_session_id_value,
                )
                result["sync_status"] = _normalize_text(flush_result.get("status"), 40) or "pending"
                result["memory_ids"] = _coerce_list_text(flush_result.get("memory_ids"))
                result["saved_count"] = max(result["saved_count"], int(flush_result.get("saved_count") or 0))
                result["skipped_employee_ids"] = _coerce_list_text(flush_result.get("skipped_employee_ids"))
                result["work_session_event"] = (
                    flush_result.get("work_session_event")
                    if isinstance(flush_result.get("work_session_event"), dict)
                    else result["work_session_event"]
                )
                if flush_result.get("task_tree") is not None:
                    result["task_tree"] = flush_result.get("task_tree")
                elif _should_flush_local_progress(status):
                    task_tree_payload = _sync_query_task_tree_from_structured_progress(
                        project_id=project_id,
                        status=status,
                        content=rendered_with_session,
                        phase=phase,
                        step=step,
                        goal=goal,
                        verification=verification,
                        chat_session_id=chat_session_id_value,
                    )
                    if task_tree_payload is None:
                        task_tree_payload = _get_existing_query_task_tree(
                            project_id=project_id,
                            chat_session_id=chat_session_id_value,
                        )
                    if task_tree_payload is not None:
                        result["task_tree"] = task_tree_payload
                if flush_result.get("error"):
                    result["sync_error"] = _normalize_text(flush_result.get("error"), 400)
            else:
                task_tree_payload = _sync_query_task_tree_from_structured_progress(
                    project_id=project_id,
                    status=status,
                    content=rendered_with_session,
                    phase=phase,
                    step=step,
                    goal=goal,
                    verification=verification,
                    chat_session_id=chat_session_id_value,
                )
                if task_tree_payload is None:
                    task_tree_payload = _get_existing_query_task_tree(
                        project_id=project_id,
                        chat_session_id=chat_session_id_value,
                    )
                if task_tree_payload is not None:
                    result["task_tree"] = task_tree_payload
            if result.get("task_tree") is not None:
                upsert_query_mcp_requirement_record(
                    project_id=_normalize_text(project_id),
                    project_name=_resolve_project_name(project_id, project_name),
                    chat_session_id=chat_session_id_value,
                    session_id=session_id_value,
                    root_goal=goal,
                    latest_status=status,
                    phase=phase,
                    step=step,
                    source="append_session_event",
                    sync_status=_normalize_text(result.get("sync_status"), 40),
                    task_tree_payload=result.get("task_tree"),
                )
            return result
        result = _save_project_memory_entries(
            project_id=project_id,
            employee_id=employee_id,
            content=rendered_with_session,
            memory_type=MemoryType.KEY_EVENT,
            importance=importance,
            project_name=project_name,
            purpose_tags=purpose_tags,
        )
        if not result.get("error"):
            result["chat_session_id"] = chat_session_id_value
            result["trajectory"] = trajectory
            result["work_session_event"] = _save_work_session_event_record(
                project_id=project_id,
                project_name=project_name,
                employee_id=employee_id,
                trajectory=trajectory,
            )
            task_tree_payload = _sync_query_task_tree_from_structured_progress(
                project_id=project_id,
                status=status,
                content=rendered_with_session,
                phase=phase,
                step=step,
                goal=goal,
                verification=verification,
                chat_session_id=chat_session_id_value,
            )
            if task_tree_payload is None:
                task_tree_payload = _get_existing_query_task_tree(
                    project_id=project_id,
                    chat_session_id=chat_session_id_value,
                )
            if task_tree_payload is not None:
                result["task_tree"] = task_tree_payload
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
        local_structured_memories = _collect_local_progress_records(
            project_id=project_id_value,
            employee_id=employee_id,
            session_id=session_id,
            limit=limit,
        )
        structured_memories = _merge_progress_records(
            local_structured_memories,
            structured_memories,
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
            structured_memories = _merge_progress_records(
                local_structured_memories,
                _structured_session_items(memories),
                limit=limit,
            )
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
        local_structured_memories = _collect_local_progress_records(
            project_id=project_id_value,
            employee_id=employee_id,
            session_id=session_id,
            limit=limit,
        )
        structured_memories = _merge_progress_records(
            local_structured_memories,
            structured_memories,
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
            structured_memories = _merge_progress_records(
                local_structured_memories,
                _structured_session_items(memories),
                limit=limit,
            )
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
    def list_recent_project_requirements(
        project_id: str,
        employee_id: str = "",
        keyword: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 10,
        project_name: str = "",
    ) -> dict:
        """列出项目近期需求，支持按关键词和日期范围过滤。"""

        project_id_value = _normalize_text(project_id)
        if not project_id_value:
            return {"error": "project_id is required"}
        selected, source, error = _collect_requirement_history_items(
            project_id=project_id_value,
            employee_id=employee_id,
            project_name=project_name,
            keyword=keyword,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        if error:
            return {"error": error}
        requirements = _group_requirement_history(selected, limit=limit)
        project_name_value = _resolve_project_name(project_id_value, project_name)
        return {
            "project_id": project_id_value,
            "project_name": project_name_value,
            "employee_id": _normalize_text(employee_id),
            "keyword": _normalize_text(keyword),
            "date_from": _normalize_text(date_from),
            "date_to": _normalize_text(date_to),
            "source": source,
            "requirements": requirements,
            "total": len(requirements),
        }

    @mcp.tool()
    def get_requirement_history(
        project_id: str,
        keyword: str,
        employee_id: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 10,
        project_name: str = "",
    ) -> dict:
        """按关键词查询需求历史，并返回需求的最近修改时间与变更轨迹。"""

        project_id_value = _normalize_text(project_id)
        keyword_value = _normalize_text(keyword)
        if not project_id_value:
            return {"error": "project_id is required"}
        if not keyword_value:
            return {"error": "keyword is required"}
        selected, source, error = _collect_requirement_history_items(
            project_id=project_id_value,
            employee_id=employee_id,
            project_name=project_name,
            keyword=keyword_value,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        if error:
            return {"error": error}
        requirements = _group_requirement_history(selected, limit=limit)
        primary = requirements[0] if requirements else {}
        project_name_value = _resolve_project_name(project_id_value, project_name)
        return {
            "project_id": project_id_value,
            "project_name": project_name_value,
            "employee_id": _normalize_text(employee_id),
            "keyword": keyword_value,
            "date_from": _normalize_text(date_from),
            "date_to": _normalize_text(date_to),
            "source": source,
            "requirements": requirements,
            "total": len(requirements),
            "matched_requirement": primary,
            "latest_modified_at": _normalize_text(primary.get("latest_modified_at")),
            "first_seen_at": _normalize_text(primary.get("first_seen_at")),
        }

    @mcp.tool()
    def build_delivery_report(
        title: str = "",
        project_id: str = "",
        summary: str = "",
        completed_items: list[str] | str | None = None,
        changed_files: list[str] | str | None = None,
        verification: list[str] | str | None = None,
        risks: list[str] | str | None = None,
        next_steps: list[str] | str | None = None,
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
        chat_session_id_value = _resolve_query_chat_session_id()
        content_with_session = _append_memory_chat_session(
            content_value,
            chat_session_id_value,
        )
        task_tree_payload = _get_existing_query_task_tree(
            project_id=project_id_value,
            chat_session_id=chat_session_id_value,
        )
        content_with_binding = _append_memory_task_tree_binding(
            content_with_session,
            task_tree_payload,
            chat_session_id=chat_session_id_value,
        )
        purpose_tags = ["query-mcp", "manual-write", "project-id"]
        if chat_session_id_value:
            purpose_tags.append(f"chat-session:{chat_session_id_value}")
        if isinstance(task_tree_payload, dict) and str(task_tree_payload.get("id") or "").strip():
            purpose_tags.append(f"task-tree-session:{str(task_tree_payload.get('id') or '').strip()}")
        result = _save_project_memory_entries(
            project_id=project_id_value,
            content=content_with_binding,
            employee_id=employee_id_value,
            memory_type=memory_type,
            importance=importance_value,
            project_name=project_name,
            purpose_tags=tuple(purpose_tags),
        )
        if task_tree_payload is not None and isinstance(result, dict):
            result["task_tree"] = task_tree_payload
        task_tree_audit = _audit_query_task_tree(
            project_id=project_id_value,
            assistant_content=content_with_binding,
            successful_tool_names=["save_project_memory"],
            chat_session_id=chat_session_id_value,
        )
        if task_tree_audit is not None and isinstance(result, dict):
            result["task_tree_audit"] = task_tree_audit
        return result

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
        result = {
            "project_id": project_id_value,
            "project_name": str(getattr(project, "name", "") or ""),
            "items": items,
            "total": len(items),
            "project_mcp_path": f"/mcp/projects/{project_id_value}",
        }
        member_names = [
            _normalize_text(item.get("name"), 80)
            for item in items
            if _normalize_text(item.get("name"), 80)
        ]
        if member_names:
            task_tree_audit = _audit_query_task_tree(
                project_id=project_id_value,
                assistant_content=(
                    f"已获取项目成员列表，共 {len(items)} 名。 成员包括：{ '、'.join(member_names) }。"
                ),
                successful_tool_names=["list_project_members"],
            )
            if task_tree_audit is not None:
                result["task_tree_audit"] = task_tree_audit
        return result

    @mcp.tool()
    def get_project_runtime_context(project_id: str) -> dict:
        """通过统一入口返回项目运行时上下文摘要。"""

        project_id_value = str(project_id or "").strip()
        if not project_id_value:
            return {"error": "project_id is required"}
        project = project_store.get(project_id_value)
        if project is None:
            return {"error": f"Project {project_id_value} not found"}
        from routers.projects import _resolve_project_experience_rule_bindings

        pairs = list_project_member_profiles_runtime(
            project_id_value,
            include_disabled=False,
            include_missing=False,
            rule_limit=30,
        )
        rules = query_project_rules_runtime(project_id_value)
        ui_rules = project_ui_rule_summary(project_id_value, limit=30)
        experience_rules = _resolve_project_experience_rule_bindings(project)
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
            "rule_count": len(rules) + len(experience_rules),
            "ui_rule_count": len(ui_rules),
            "ui_rules": ui_rules,
            "experience_rule_count": len(experience_rules),
            "experience_rules": experience_rules,
            "project_mcp_path": f"/mcp/projects/{project_id_value}",
        }

    @mcp.tool()
    def resolve_project_experience_rules(project_id: str, task_text: str, limit: int = 3) -> dict:
        """通过统一入口按任务文本解析项目经验规则，只返回高相关经验卡片。"""

        project_id_value = str(project_id or "").strip()
        if not project_id_value:
            return {"error": "project_id is required"}
        project = project_store.get(project_id_value)
        if project is None:
            return {"error": f"Project {project_id_value} not found"}
        from routers.projects import _resolve_project_experience_rules_payload

        payload = _resolve_project_experience_rules_payload(project, task_text, limit=limit)
        payload["project_mcp_path"] = f"/mcp/projects/{project_id_value}"
        return payload

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
        resolved_username, resolved_chat_session_id = _resolve_task_tree_context()

        result = invoke_project_skill_tool_runtime(
            project_id=project_id_value,
            tool_name=tool_name_value,
            employee_id=employee_id_value,
            username=resolved_username,
            chat_session_id=resolved_chat_session_id,
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
        resolved_username, resolved_chat_session_id = _resolve_task_tree_context()

        result = execute_project_collaboration_runtime(
            project_id=project_id_value,
            task=task_value,
            username=resolved_username,
            chat_session_id=resolved_chat_session_id,
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
