"""Unified query MCP app builder."""

from __future__ import annotations

from dataclasses import asdict
import os

from mcp.server.fastmcp import FastMCP

from core.deps import employee_store, project_store
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
    rule_store,
    serialize_rule,
    serialize_skill,
    skill_store,
)

_FASTMCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")


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
            "- 目标: 在保留现有员工/项目/规则 MCP 的前提下，提供一个聚合查询入口，并补充最常用的项目执行代理。\n"
            "- 推荐工具: search_ids / get_content / get_manual_content\n"
            "- 典型用法: 先 search_ids 找到目标 ID，再用 get_content 或 get_manual_content 取正文。\n"
            "- 记忆留痕: 首次查询必须把用户原始问题放进可检索字段，优先使用 search_ids(keyword=\"<用户原始问题>\")；不要只传“当前项目”“这个规则”之类代称。\n"
            "- 执行代理: 本入口默认仍以查询与聚合优先；如宿主只接统一入口，项目协作型任务可优先调用 execute_project_collaboration(project_id, task, ...)。\n"
            "- 执行代理: execute_project_collaboration 是统一编排入口，但是否单人主责、是否需要多人协作以及如何拆分，仍由 AI 结合项目手册、员工手册、规则和工具自主判断，不预设固定行业分工模板。\n"
            "- 执行代理: 若需要手动编排项目执行，再继续调用 list_project_members / get_project_runtime_context / list_project_proxy_tools / invoke_project_skill_tool。\n"
            "- 注意: 本入口仍以查询与聚合优先；如宿主支持多 MCP，复杂执行场景仍优先直连对应 project MCP。\n"
            "- 记忆说明: 本入口不暴露 save_project_memory/save_employee_memory；如宿主系统已启用自动记忆，可在入口层自动记录问题快照。"
        )

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
