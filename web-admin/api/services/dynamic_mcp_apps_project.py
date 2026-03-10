"""Project MCP app builder for dynamic MCP runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core.deps import employee_store, project_store
from services.dynamic_mcp_external_tools import (
    invoke_external_mcp_tool_runtime,
    list_project_external_tools_runtime,
)
from services.dynamic_mcp_profiles import (
    employee_rule_summary as _employee_rule_summary,
    list_project_member_profiles_runtime,
    query_project_members_runtime,
    query_project_rules_runtime,
    query_rules_by_employee as _query_rules_by_employee,
)
from services.dynamic_mcp_skill_executor import execute_skill_proxy as _execute_skill_proxy
from services.dynamic_mcp_skill_proxies import (
    _tool_token,
    active_project_member_employees as _active_project_member_employees,
    build_project_proxy_specs as _build_project_proxy_specs,
    list_project_proxy_tools_runtime,
)
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
    skill_store,
)

_FASTMCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")


def _new_mcp(service_name: str) -> FastMCP:
    return FastMCP(service_name, host=_FASTMCP_HOST, stateless_http=True)


def create_project_mcp(
    project_id: str,
    *,
    current_api_key_ctx,
    current_developer_name_ctx,
    project_root: Path,
    recall_limit: int,
):
    mcp = _new_mcp(f"project-{project_id}")
    scoped_proxy_specs, employee_proxy_specs = _build_project_proxy_specs(project_id)
    external_tool_specs = list_project_external_tools_runtime(project_id)

    def _get_project():
        return project_store.get(project_id)

    def _list_member_pairs() -> list[tuple[object, object]]:
        return _active_project_member_employees(project_id)

    def _feedback_actor() -> str:
        actor = current_developer_name_ctx.get("").strip()
        return actor or "unknown"

    def _member_employee_ids() -> set[str]:
        return {employee.id for _member, employee in _list_member_pairs()}

    @mcp.resource(f"project://{project_id}/profile")
    def project_profile() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        return (
            f"[{project.id}] {project.name}\n"
            f"description: {project.description or '-'}\n"
            f"mcp_enabled={project.mcp_enabled} "
            f"feedback_upgrade_enabled={project.feedback_upgrade_enabled}"
        )

    @mcp.resource(f"project://{project_id}/members")
    def project_members() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        pairs = _list_member_pairs()
        if not pairs:
            return "No active project members."
        lines = []
        for member, employee in pairs:
            lines.append(
                f"- {employee.id}: {employee.name} | role={member.role} enabled={member.enabled}"
            )
        return "\n".join(lines)

    @mcp.resource(f"project://{project_id}/proxy-tools")
    def project_proxy_tools() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        if not scoped_proxy_specs:
            return "No executable skill tools discovered from project members."
        lines = []
        for tool_name, spec in sorted(scoped_proxy_specs.items()):
            lines.append(
                f"- {tool_name}: {spec['employee_id']} / {spec['skill_id']} / "
                f"{spec['entry_name']} ({spec['script_type']})"
            )
        return "\n".join(lines)

    @mcp.resource(f"project://{project_id}/external-mcp-tools")
    def project_external_tools() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        if not external_tool_specs:
            return "No external MCP tools available."
        lines = []
        for item in external_tool_specs:
            lines.append(
                f"- {item['tool_name']}: {item.get('module_name', '-')} / {item.get('remote_tool_name', '-')}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def get_project_profile() -> dict:
        """获取项目画像配置"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        return asdict(project)

    @mcp.tool()
    def list_project_members() -> list[dict]:
        """列出项目成员详情"""
        project = _get_project()
        if not project:
            return []
        return list_project_member_profiles_runtime(
            project.id,
            include_disabled=False,
            include_missing=False,
            rule_limit=30,
        )

    @mcp.tool()
    def get_project_runtime_context() -> dict:
        """返回项目运行时上下文摘要（成员、技能、规则、记忆统计）"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        pairs = _list_member_pairs()
        rule_ids: set[str] = set()
        for _member, employee in pairs:
            for rule in _query_rules_by_employee(employee):
                rule_ids.add(rule.id)
        return {
            "project_id": project.id,
            "project_name": project.name,
            "member_count": len(pairs),
            "members": [employee.id for _member, employee in pairs],
            "scoped_proxy_tool_count": len(scoped_proxy_specs),
            "rule_count": len(rule_ids),
        }

    @mcp.tool()
    def recall_project_memory(
        query: str = "",
        employee_id: str = "",
        project_name: str = "",
        limit: int = 100,
    ) -> list[dict]:
        """检索项目记忆（支持项目隔离）"""
        project = _get_project()
        if not project:
            return []
        query = str(query or "").strip()
        employee_id = str(employee_id or "").strip()
        normalized_project_name = str(project_name or "").strip() or str(project.name or "").strip() or "default"
        max_limit = max(1, min(int(limit), 200))

        member_ids = _member_employee_ids()
        if employee_id and employee_id not in member_ids:
            return []
        targets = [employee_id] if employee_id else sorted(member_ids)
        memories = []
        for eid in targets:
            if query:
                employee_mems = memory_store.recall(eid, query, recall_limit)
            else:
                employee_mems = memory_store.recent(eid, recall_limit)
            for memory in employee_mems:
                if str(getattr(memory, "project_name", "")) != normalized_project_name:
                    continue
                memories.append(memory)
        memories = sorted(memories, key=lambda item: str(getattr(item, "created_at", "")), reverse=True)
        return [serialize_memory(item) for item in memories[:max_limit]]

    @mcp.tool()
    def save_project_memory(
        employee_id: str,
        content: str,
        type: str = "project-context",
        importance: float = 0.6,
        project_name: str = "",
    ) -> dict:
        """向项目下指定员工写入记忆"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        employee_id_value = str(employee_id or "").strip()
        if employee_id_value not in _member_employee_ids():
            return {"error": f"Employee {employee_id_value} is not an active project member"}
        content_value = str(content or "").strip()
        if not content_value:
            return {"error": "content is required"}
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
        normalized_project_name = str(project_name or "").strip() or str(project.name or "").strip() or "default"
        memory = Memory(
            id=memory_store.new_id(),
            employee_id=employee_id_value,
            type=memory_type,
            content=content_value,
            project_name=normalized_project_name,
            importance=importance_value,
            scope=MemoryScope.EMPLOYEE_PRIVATE,
            classification=Classification.INTERNAL,
            purpose_tags=("project-mcp", "manual-write"),
        )
        memory_store.save(memory)
        return {
            "status": "saved",
            "memory_id": memory.id,
            "employee_id": employee_id_value,
            "project_name": normalized_project_name,
            "type": memory_type.value,
            "importance": importance_value,
        }

    @mcp.tool()
    def submit_project_feedback_bug(
        employee_id: str,
        title: str,
        symptom: str,
        expected: str,
        category: str = "general",
        severity: str = "medium",
        session_id: str = "",
        rule_id: str = "",
        source_context: dict | None = None,
    ) -> dict:
        """提交项目下员工反馈工单"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        employee_id_value = str(employee_id or "").strip()
        if employee_id_value not in _member_employee_ids():
            return {"error": f"Employee {employee_id_value} is not an active project member"}
        try:
            bug = get_feedback_service().create_bug(
                project_id=project.id,
                payload={
                    "employee_id": employee_id_value,
                    "title": title,
                    "symptom": symptom,
                    "expected": expected,
                    "category": category,
                    "severity": severity,
                    "session_id": session_id,
                    "rule_id": rule_id,
                    "source_context": source_context or {},
                },
                actor=_feedback_actor(),
            )
            return {"status": "created", "bug": bug}
        except (ValueError, RuntimeError, LookupError) as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def query_project_rules(keyword: str = "", employee_id: str = "") -> list[dict]:
        """检索项目成员规则（支持按 employee_id 过滤）"""
        project = _get_project()
        if not project:
            return []
        employee_id_value = str(employee_id or "").strip()
        results = []
        seen: set[str] = set()
        for _member, employee in _list_member_pairs():
            if employee_id_value and employee.id != employee_id_value:
                continue
            for rule in _query_rules_by_employee(employee, keyword):
                if rule.id in seen:
                    continue
                seen.add(rule.id)
                results.append(serialize_rule(rule))
        return results

    @mcp.tool()
    def list_project_proxy_tools() -> list[dict]:
        """列出项目成员可执行技能脚本代理工具"""
        tools = []
        for tool_name, spec in sorted(scoped_proxy_specs.items()):
            tools.append(
                {
                    "tool_name": tool_name,
                    "employee_id": spec["employee_id"],
                    "base_tool_name": spec["base_tool_name"],
                    "skill_id": spec["skill_id"],
                    "entry_name": spec["entry_name"],
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                }
            )
        return tools

    @mcp.tool()
    def list_external_mcp_tools() -> list[dict]:
        """列出当前项目可用的外部 MCP 工具"""
        return list_project_external_tools_runtime(project_id)

    @mcp.tool()
    def invoke_external_mcp_tool(
        tool_name: str,
        arguments: dict | None = None,
        timeout_sec: int = 30,
    ) -> dict:
        """调用当前项目配置的外部 MCP 工具"""
        return invoke_external_mcp_tool_runtime(
            project_id=project_id,
            tool_name=tool_name,
            args=arguments,
            args_json=json.dumps(arguments or {}, ensure_ascii=False),
            timeout_sec=timeout_sec,
        )

    def _resolve_project_tool_spec(tool_name: str, employee_id: str = "") -> tuple[dict | None, str]:
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

        matched = []
        for specs in employee_proxy_specs.values():
            if normalized_tool_name in specs:
                matched.append(specs[normalized_tool_name])
        if not matched:
            return None, f"Tool not found: {normalized_tool_name}"
        if len(matched) > 1:
            employee_ids = sorted({item["employee_id"] for item in matched})
            return None, (
                "Ambiguous tool_name, provide employee_id. "
                f"Candidates: {employee_ids}"
            )
        return matched[0], ""

    @mcp.tool()
    def invoke_project_skill_tool(
        tool_name: str,
        employee_id: str = "",
        args: dict | None = None,
        args_json: str = "{}",
        timeout_sec: int = 30,
    ) -> dict:
        """按工具名直接调用项目成员技能脚本（支持 employee_id 消歧）"""
        spec, err = _resolve_project_tool_spec(tool_name, employee_id)
        if spec is None:
            return {"error": err}
        return _execute_skill_proxy(
            spec,
            project_root=project_root,
            current_api_key=current_api_key_ctx.get(""),
            args=args,
            args_json=args_json,
            timeout_sec=timeout_sec,
            employee_id=spec["employee_id"],
        )

    for tool_name, spec in sorted(scoped_proxy_specs.items()):
        def _make_proxy_tool(spec_item: dict):
            def _proxy_tool(args: dict | None = None, args_json: str = "{}", timeout_sec: int = 30) -> dict:
                return _execute_skill_proxy(
                    spec_item,
                    args=args,
                    args_json=args_json,
                    timeout_sec=timeout_sec,
                    employee_id=spec_item["employee_id"],
                )
            _proxy_tool.__name__ = f"project_proxy_{tool_name}"
            return _proxy_tool

        mcp.tool(
            name=tool_name,
            description=(
                f"Proxy of {spec['employee_id']}:{spec['skill_id']}:{spec['entry_name']}. "
                "Pass CLI args via args(object) or args_json(string), e.g. args={\"sql\":\"SHOW TABLES\"}."
            ),
        )(_make_proxy_tool(spec))

    for external_spec in external_tool_specs:
        scoped_tool_name = str(external_spec.get("tool_name") or "").strip()
        remote_tool_name = str(external_spec.get("remote_tool_name") or "").strip()
        if not scoped_tool_name or not remote_tool_name:
            continue

        def _make_external_proxy(tool_name_value: str):
            def _proxy_tool(arguments: dict | None = None, timeout_sec: int = 30) -> dict:
                return invoke_external_mcp_tool_runtime(
                    project_id=project_id,
                    tool_name=tool_name_value,
                    args=arguments,
                    args_json=json.dumps(arguments or {}, ensure_ascii=False),
                    timeout_sec=timeout_sec,
                )

            _proxy_tool.__name__ = f"project_external_{tool_name_value}"
            return _proxy_tool

        mcp.tool(
            name=scoped_tool_name,
            description=(
                f"Proxy of external MCP {external_spec.get('module_name', '-')}:{remote_tool_name}. "
                "Pass remote tool arguments via arguments(object)."
            ),
        )(_make_external_proxy(scoped_tool_name))

    return _DualTransportMcpApp(
        _apply_mcp_arguments_compat(mcp.sse_app()),
        mcp.streamable_http_app(),
    )
