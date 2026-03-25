"""Employee MCP app builder for dynamic MCP runtime."""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core.deps import employee_store
from services.dynamic_mcp_profiles import (
    employee_rule_summary as _employee_rule_summary,
    query_rules_by_employee as _query_rules_by_employee,
)
from services.dynamic_mcp_skill_executor import execute_skill_proxy as _execute_skill_proxy
from services.dynamic_mcp_skill_proxies import build_employee_proxy_specs as _build_employee_proxy_specs
from services.dynamic_mcp_transports import (
    DualTransportMcpApp as _DualTransportMcpApp,
    apply_mcp_arguments_compat as _apply_mcp_arguments_compat,
)
from services.feedback_service import get_feedback_service
from stores.mcp_bridge import (
    Classification,
    Memory,
    MemoryScope,
    MemoryType,
    memory_store,
    serialize_memory,
    serialize_rule,
    serialize_skill,
)

_FASTMCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")


def _new_mcp(service_name: str) -> FastMCP:
    return FastMCP(service_name, host=_FASTMCP_HOST, stateless_http=True)


def create_employee_mcp(
    employee_id: str,
    *,
    current_api_key_ctx,
    current_developer_name_ctx,
    system_policy_text: str,
    load_project_config_fn,
    project_root: Path,
    recall_limit: int,
):
    mcp = _new_mcp(f"employee-{employee_id}")
    proxy_specs_by_name: dict[str, dict] = {}
    employee = employee_store.get(employee_id)
    if employee:
        proxy_specs_by_name = _build_employee_proxy_specs(employee_id)

    def _get_employee():
        return employee_store.get(employee_id)

    def _get_feedback_actor() -> str:
        actor = current_developer_name_ctx.get("").strip()
        return actor or "unknown"

    feedback_enabled = bool(getattr(employee, "feedback_upgrade_enabled", False)) if employee else False

    @mcp.resource(f"employee://{employee_id}/system-policy")
    def system_policy() -> str:
        """底层安全策略（不可修改，重启生效）"""
        return system_policy_text or "No system policy configured."

    @mcp.resource(f"employee://{employee_id}/profile")
    def employee_profile() -> str:
        employee = _get_employee()
        if not employee:
            return "Employee deleted or unavailable."
        style = " / ".join(employee.style_hints or []) or "none"
        workflow = " / ".join(employee.default_workflow or []) or "none"
        return (
            f"[{employee.id}] {employee.name}\n"
            f"description: {employee.description or '-'}\n"
            f"goal={employee.goal or '-'}\n"
            f"tone={employee.tone} verbosity={employee.verbosity} language={employee.language}\n"
            f"memory_scope={employee.memory_scope} retention_days={employee.memory_retention_days}\n"
            f"auto_evolve={employee.auto_evolve} evolve_threshold={employee.evolve_threshold}\n"
            f"style_hints: {style}\n"
            f"default_workflow: {workflow}\n"
            f"tool_usage_policy: {employee.tool_usage_policy or '-'}"
        )

    @mcp.resource(f"employee://{employee_id}/skills")
    def employee_skills() -> str:
        employee = _get_employee()
        if not employee:
            return "Employee deleted or unavailable."
        if not employee.skills:
            return "No bound skills."
        lines = []
        for skill_id in employee.skills:
            skill = skill_store.get(skill_id)
            if skill is None:
                lines.append(f"- {skill_id}: missing")
                continue
            lines.append(f"- {skill.id}: {skill.name} ({len(skill.tools)} tools)")
        return "\n".join(lines)

    @mcp.resource(f"employee://{employee_id}/rules")
    def employee_rules() -> str:
        employee = _get_employee()
        if not employee:
            return "Employee deleted or unavailable."
        rules = _query_rules_by_employee(employee)
        if not rules:
            return "No matched rules for current employee domains."
        lines = [
            f"- [{rule.id}] ({rule.domain}) {rule.title} "
            f"| severity={rule.severity.value} risk={rule.risk_domain.value}"
            for rule in rules
        ]
        return "\n".join(lines)

    @mcp.resource(f"employee://{employee_id}/proxy-tools")
    def employee_proxy_tools() -> str:
        employee = _get_employee()
        if not employee:
            return "Employee deleted or unavailable."
        if not proxy_specs_by_name:
            return "No executable skill tools discovered."
        lines = []
        for tool_name, spec in sorted(proxy_specs_by_name.items()):
            lines.append(
                f"- {tool_name}: {spec['skill_id']} / {spec['entry_name']} ({spec['script_type']})"
            )
        return "\n".join(lines)

    @mcp.tool()
    def get_employee_profile() -> dict:
        """获取员工画像与行为配置"""
        employee = _get_employee()
        if not employee:
            return {"error": "Employee not found"}
        payload = asdict(employee)
        payload.pop("rule_ids", None)
        payload.pop("rule_domains", None)
        payload["rule_bindings"] = _employee_rule_summary(employee, limit=200)
        return payload

    @mcp.tool()
    def list_employee_skills() -> list[dict]:
        """列出员工绑定技能详情"""
        employee = _get_employee()
        if not employee:
            return []
        results = []
        for skill_id in employee.skills:
            skill = skill_store.get(skill_id)
            if skill is None:
                results.append({"id": skill_id, "error": "Skill not found"})
                continue
            results.append(serialize_skill(skill))
        return results

    @mcp.tool()
    def query_employee_rules(keyword: str = "") -> list[dict]:
        """按员工绑定领域检索规则，可选关键词过滤"""
        employee = _get_employee()
        if not employee:
            return []
        rules = _query_rules_by_employee(employee, keyword)
        return [serialize_rule(rule) for rule in rules]

    @mcp.tool()
    def recall_employee_memory(query: str = "", project_name: str = "") -> list[dict]:
        """检索员工记忆（支持项目隔离）

        Args:
            query: 检索关键词（为空则返回最近记忆）
            project_name: 项目名称（为空则自动读取 .mcp-project.json）
        """
        employee = _get_employee()
        if not employee:
            return []
        query = str(query or "").strip()

        # 自动读取项目配置
        if not project_name:
            project_config = load_project_config_fn()
            project_name = project_config.get("project_name") or "default"
        project_name = str(project_name).strip()

        if query:
            memories = memory_store.recall(employee.id, query, recall_limit)
        else:
            memories = memory_store.recent(employee.id, recall_limit)

        # 按 project_name 过滤记忆
        filtered = [m for m in memories if getattr(m, "project_name", "") == project_name]
        return [serialize_memory(mem) for mem in filtered]

    @mcp.tool()
    def save_employee_memory(
        content: str,
        type: str = "project-context",
        importance: float = 0.6,
        project_name: str = "",
    ) -> dict:
        """向当前员工写入记忆（支持项目隔离）

        Args:
            project_name: 项目名称（为空则自动读取 .mcp-project.json）
        """
        employee = _get_employee()
        if not employee:
            return {"error": "Employee not found"}

        content_value = str(content or "").strip()
        if not content_value:
            return {"error": "content is required"}

        if not project_name:
            project_config = load_project_config_fn()
            project_name = project_config.get("project_name") or "default"
        project_name = str(project_name).strip()

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

        memory = Memory(
            id=memory_store.new_id(),
            employee_id=employee.id,
            type=memory_type,
            content=content_value,
            project_name=project_name,
            importance=importance_value,
            scope=MemoryScope.EMPLOYEE_PRIVATE,
            classification=Classification.INTERNAL,
            purpose_tags=("employee-mcp", "manual-write"),
        )
        memory_store.save(memory)
        return {
            "status": "saved",
            "memory_id": memory.id,
            "employee_id": employee.id,
            "project_name": project_name,
            "type": memory_type.value,
            "importance": importance_value,
        }

    @mcp.tool()
    def get_employee_runtime_context() -> dict:
        """返回员工运行时上下文摘要（技能、规则、记忆统计）"""
        employee = _get_employee()
        if not employee:
            return {"error": "Employee not found"}
        rule_bindings = _employee_rule_summary(employee, limit=200)
        return {
            "employee_id": employee.id,
            "name": employee.name,
            "goal": employee.goal,
            "tone": employee.tone,
            "verbosity": employee.verbosity,
            "language": employee.language,
            "style_hints": list(employee.style_hints or []),
            "default_workflow": list(employee.default_workflow or []),
            "tool_usage_policy": employee.tool_usage_policy,
            "skills": list(employee.skills or []),
            "proxy_tools": sorted(proxy_specs_by_name.keys()),
            "rule_bindings": rule_bindings,
            "rule_count": len(rule_bindings),
            "memory_count": memory_store.count(employee.id),
            "auto_evolve": employee.auto_evolve,
            "evolve_threshold": employee.evolve_threshold,
        }

    @mcp.tool()
    def list_employee_proxy_tools() -> list[dict]:
        """列出该员工可直接调用的技能代理工具"""
        tools = []
        for tool_name, spec in sorted(proxy_specs_by_name.items()):
            tools.append(
                {
                    "tool_name": tool_name,
                    "skill_id": spec["skill_id"],
                    "entry_name": spec["entry_name"],
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                }
            )
        return tools

    if feedback_enabled:
        @mcp.tool()
        def submit_feedback_bug(
            title: str,
            symptom: str,
            expected: str,
            project_name: str = "",
            category: str = "general",
            severity: str = "medium",
            session_id: str = "",
            rule_id: str = "",
            source_context: dict | None = None,
        ) -> dict:
            """提交当前员工的结构化反馈工单（支持项目隔离）

            Args:
                project_name: 项目名称（为空则自动读取 .mcp-project.json）
            """
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}

            # 自动读取项目配置
            if not project_name:
                project_config = load_project_config_fn()
                project_name = project_config.get("project_name") or "default"

            try:
                bug = get_feedback_service().create_bug(
                    project_id=project_name,
                    payload={
                        "employee_id": employee_id,
                        "title": title,
                        "symptom": symptom,
                        "expected": expected,
                        "category": category,
                        "severity": severity,
                        "session_id": session_id,
                        "rule_id": rule_id,
                        "source_context": source_context or {},
                    },
                    actor=_get_feedback_actor(),
                )
                return {"status": "created", "bug": bug}
            except (ValueError, RuntimeError) as exc:
                return {"error": str(exc)}

        @mcp.tool()
        def list_feedback_bugs(
            project_id: str = "default",
            status: str = "",
            severity: str = "",
            limit: int = 20,
        ) -> list[dict]:
            """查询当前员工在项目内的反馈工单列表"""
            employee = _get_employee()
            if not employee:
                return []
            try:
                return get_feedback_service().list_bugs(
                    project_id=project_id,
                    employee_id=employee_id,
                    status=status,
                    severity=severity,
                    limit=limit,
                )
            except (ValueError, RuntimeError):
                return []

        @mcp.tool()
        def get_feedback_bug_detail(feedback_id: str, project_id: str = "default") -> dict:
            """查看单条反馈的详情（含反思、候选、审核日志）"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            try:
                detail = get_feedback_service().get_bug_detail(
                    project_id,
                    feedback_id,
                    employee_id=employee_id,
                )
            except LookupError as exc:
                return {"error": str(exc)}
            except RuntimeError as exc:
                return {"error": str(exc)}
            bug = detail.get("bug") or {}
            if bug.get("employee_id") != employee_id:
                return {"error": f"Feedback {feedback_id} does not belong to employee {employee_id}"}
            return detail

        @mcp.tool()
        def analyze_feedback_bug(feedback_id: str, project_id: str = "default") -> dict:
            """触发反馈反思并生成规则升级候选"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            detail = get_feedback_bug_detail(feedback_id=feedback_id, project_id=project_id)
            if detail.get("error"):
                return detail
            try:
                result = get_feedback_service().analyze_bug(
                    project_id,
                    feedback_id,
                    employee_id=employee_id,
                )
                return {"status": "analyzed", **result}
            except ValueError as exc:
                return {"error": str(exc)}
            except LookupError as exc:
                return {"error": str(exc)}
            except RuntimeError as exc:
                return {"error": str(exc)}

        @mcp.tool()
        def list_feedback_candidates(
            project_id: str = "default",
            status: str = "pending",
            limit: int = 20,
        ) -> list[dict]:
            """查询当前员工在项目内的反馈候选规则"""
            employee = _get_employee()
            if not employee:
                return []
            try:
                return get_feedback_service().list_candidates(
                    project_id=project_id,
                    status=status,
                    employee_id=employee_id,
                    limit=limit,
                )
            except (ValueError, RuntimeError):
                return []

        def _find_candidate_in_employee_scope(project_id: str, candidate_id: str) -> dict:
            candidates = get_feedback_service().list_candidates(
                project_id=project_id,
                status="",
                employee_id=employee_id,
                limit=200,
            )
            for candidate in candidates:
                if candidate.get("id") == candidate_id:
                    return candidate
            return {}

        @mcp.tool()
        def review_feedback_candidate(
            candidate_id: str,
            action: str,
            project_id: str = "default",
            comment: str = "",
            edited_content: str = "",
            edited_executable_content: str = "",
        ) -> dict:
            """审核反馈候选（approve/edit/reject）"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            candidate = _find_candidate_in_employee_scope(project_id, candidate_id)
            if not candidate:
                return {"error": f"Candidate {candidate_id} not found for employee {employee_id}"}
            try:
                updated = get_feedback_service().review_candidate(
                    project_id=project_id,
                    candidate_id=candidate_id,
                    reviewed_by=_get_feedback_actor(),
                    action=action,
                    comment=comment,
                    edited_content=edited_content,
                    edited_executable_content=edited_executable_content,
                    employee_id=employee_id,
                )
                return {"status": updated.get("status", ""), "candidate": updated}
            except (ValueError, LookupError, RuntimeError) as exc:
                return {"error": str(exc)}

        @mcp.tool()
        def publish_feedback_candidate(
            candidate_id: str,
            project_id: str = "default",
            comment: str = "",
        ) -> dict:
            """发布已审核通过的反馈候选到规则库"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            candidate = _find_candidate_in_employee_scope(project_id, candidate_id)
            if not candidate:
                return {"error": f"Candidate {candidate_id} not found for employee {employee_id}"}
            try:
                updated = get_feedback_service().publish_candidate(
                    project_id=project_id,
                    candidate_id=candidate_id,
                    published_by=_get_feedback_actor(),
                    comment=comment,
                    employee_id=employee_id,
                )
                return {"status": "published", "candidate": updated}
            except (ValueError, LookupError, RuntimeError) as exc:
                return {"error": str(exc)}

        @mcp.tool()
        def rollback_feedback_candidate(
            candidate_id: str,
            project_id: str = "default",
            comment: str = "",
        ) -> dict:
            """回滚已发布的反馈候选规则版本"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            candidate = _find_candidate_in_employee_scope(project_id, candidate_id)
            if not candidate:
                return {"error": f"Candidate {candidate_id} not found for employee {employee_id}"}
            try:
                updated = get_feedback_service().rollback_candidate(
                    project_id=project_id,
                    candidate_id=candidate_id,
                    rolled_back_by=_get_feedback_actor(),
                    comment=comment,
                    employee_id=employee_id,
                )
                return {"status": "rolled_back", "candidate": updated}
            except (ValueError, LookupError, RuntimeError) as exc:
                return {"error": str(exc)}

    @mcp.tool()
    def invoke_employee_skill_tool(
        tool_name: str,
        args: dict | None = None,
        args_json: str = "{}",
        timeout_sec: int = 30,
    ) -> dict:
        """按工具名调用员工绑定技能脚本（参数使用 JSON 对象）"""
        spec = proxy_specs_by_name.get(str(tool_name or "").strip())
        if spec is None:
            return {"error": f"Tool not found: {tool_name}"}
        return _execute_skill_proxy(spec, project_root=project_root, current_api_key=current_api_key_ctx.get(""), args=args, args_json=args_json, timeout_sec=timeout_sec, employee_id=employee_id)
    for tool_name, spec in sorted(proxy_specs_by_name.items()):
        def _make_proxy_tool(spec_item: dict, tool_name_value: str):
            def _proxy_tool(args: dict | None = None, args_json: str = "{}", timeout_sec: int = 30) -> dict:
                return _execute_skill_proxy(spec_item, project_root=project_root, current_api_key=current_api_key_ctx.get(""), args=args, args_json=args_json, timeout_sec=timeout_sec, employee_id=employee_id)
            _proxy_tool.__name__ = f"proxy_{tool_name_value}"
            return _proxy_tool
        mcp.tool(
            name=tool_name,
            description=(
                f"Proxy of {spec['skill_id']}:{spec['entry_name']}. "
                "Pass CLI args via args(object) or args_json(string), e.g. args={\"sql\":\"SHOW TABLES\"}."
            ),
        )(_make_proxy_tool(spec, tool_name))

    return _DualTransportMcpApp(
        _apply_mcp_arguments_compat(mcp.sse_app()),
        mcp.streamable_http_app(),
    )
