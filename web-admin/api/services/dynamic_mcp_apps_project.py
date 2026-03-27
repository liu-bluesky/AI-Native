"""Project MCP app builder for dynamic MCP runtime."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core.deps import employee_store, project_store
from services.dynamic_mcp_external_tools import (
    invoke_external_mcp_tool_runtime,
    list_project_external_tools_runtime,
)
from services.dynamic_mcp_context import (
    get_project_detail_runtime,
    get_project_employee_detail_runtime,
)
from services.dynamic_mcp_collaboration import (
    COLLABORATION_TOOL_NAME,
    collaboration_tool_descriptor,
    execute_project_collaboration_runtime,
    invoke_project_builtin_tool,
    parse_object_args,
)
from services.dynamic_mcp_profiles import (
    employee_rule_summary as _employee_rule_summary,
    list_project_member_profiles_runtime,
    project_ui_rule_summary,
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

    def _resolve_mcp_instruction(project) -> str:
        return (
            str(getattr(project, "mcp_instruction", "") or "").strip()
            or str(getattr(project, "description", "") or "").strip()
        )

    def _resolve_ai_entry_path(project) -> tuple[str, Path | None]:
        ai_entry_file = str(getattr(project, "ai_entry_file", "") or "").strip()
        if not ai_entry_file:
            return "", None
        workspace_path = str(getattr(project, "workspace_path", "") or "").strip()
        entry_path = Path(ai_entry_file).expanduser()
        if entry_path.is_absolute():
            return ai_entry_file, entry_path.resolve()
        if workspace_path:
            return ai_entry_file, (Path(workspace_path).expanduser() / entry_path).resolve()
        return ai_entry_file, (project_root / entry_path).resolve()

    def _read_ai_entry_excerpt(project, max_chars: int = 6000) -> tuple[str, str]:
        display_path, resolved_path = _resolve_ai_entry_path(project)
        if not display_path:
            return "", "未配置项目 AI 入口文件。"
        if resolved_path is None:
            return display_path, "AI 入口文件路径解析失败。"
        if not resolved_path.exists() or not resolved_path.is_file():
            return display_path, f"AI 入口文件不存在或不可读取：{resolved_path}"
        try:
            content = resolved_path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception as exc:
            return display_path, f"读取 AI 入口文件失败：{exc}"
        if not content:
            return display_path, "AI 入口文件为空。"
        if len(content) > max_chars:
            content = f"{content[:max_chars].rstrip()}\n\n[内容已截断，请按需继续读取原文件]"
        return display_path, content

    def _build_usage_guide(project) -> dict:
        manual_resource = f"project://{project.id}/manual"
        display_path, ai_entry_excerpt = _read_ai_entry_excerpt(project)
        mcp_instruction = _resolve_mcp_instruction(project)
        proxy_tool_count = len(scoped_proxy_specs)
        external_tool_count = len(external_tool_specs)
        ui_rule_bindings = project_ui_rule_summary(project.id, limit=20)
        ui_rule_titles = [str(item.get("title") or item.get("id") or "").strip() for item in ui_rule_bindings if str(item.get("title") or item.get("id") or "").strip()]
        guide_lines = [
            f"# {project.name} Project MCP Usage Guide",
            "",
            f"- 项目 ID: {project.id}",
            f"- 项目描述: {project.description or '-'}",
            f"- MCP 使用说明: {mcp_instruction or '-'}",
            f"- 适用场景: 读取项目画像、项目级 UI 规则、项目成员规则、项目成员技能代理工具，以及当前项目挂载的外部 MCP 工具。",
            f"- 项目使用手册 Resource: {manual_resource}",
            "",
            "## 推荐调用顺序",
            f"1. 先调用 get_project_usage_guide 或读取 project://{project.id}/usage-guide，了解项目范围与约定。",
            "2. 如需项目手册，直接读取 project://<project_id>/manual 或调用 get_project_manual。",
            "3. 调用 get_project_profile，确认项目基础配置、工作区与入口文件配置。",
            "4. 调用 get_project_runtime_context，快速了解成员数量、项目级 UI 规则、规则规模和代理工具规模。",
            f"5. 如需选人，先调用 list_project_members；如需选工具，先调用 list_project_proxy_tools 或读取 project://{project.id}/proxy-tools。",
            "6. 规则检索用 query_project_rules；其中项目级 UI 规则优先于员工个人规则。协作型任务可直接调用 execute_project_collaboration，由 AI 结合项目手册、员工手册、规则和工具自主判断单人主责或多人协作；成员技能脚本调用用 invoke_project_skill_tool；外部模块调用用 list_external_mcp_tools / invoke_external_mcp_tool。",
            "",
            "## 调用建议",
            "- 页面、交互、视觉相关任务先检查项目级 UI 规则，其优先级高于员工个人规则。",
            "- 当 tool_name 可能重名时，给 invoke_project_skill_tool 同时传 employee_id 做消歧。",
            "- 在直接调用技能脚本前，先读取项目规则和成员信息，避免工具选错。",
            "- execute_project_collaboration 是统一协作入口，但不内置固定行业分工模板；若单个成员足以闭环，可保持单人主责。",
            "- 外部 MCP 工具的参数以远端工具 schema 为准，先用 list_external_mcp_tools 查看。",
            "",
            "## 当前项目能力概览",
            f"- 项目级 UI 规则数: {len(ui_rule_bindings)}",
            f"- 项目级 UI 规则: {', '.join(ui_rule_titles) or '-'}",
            f"- 项目成员技能代理工具数: {proxy_tool_count}",
            f"- 外部 MCP 工具数: {external_tool_count}",
        ]
        if display_path:
            guide_lines.extend(
                [
                    "",
                    "## 项目 AI 入口文件",
                    f"- 配置值: {display_path}",
                    "- 建议在深入调用工具前，先阅读下面摘录的入口文件内容。",
                    "",
                    ai_entry_excerpt,
                ]
            )
        else:
            guide_lines.extend(
                [
                    "",
                    "## 项目 AI 入口文件",
                    ai_entry_excerpt,
                ]
            )
        return {
            "project_id": project.id,
            "project_name": project.name,
            "project_description": str(project.description or ""),
            "mcp_instruction": mcp_instruction,
            "workspace_path": str(getattr(project, "workspace_path", "") or ""),
            "ai_entry_file": display_path,
            "ui_rule_count": len(ui_rule_bindings),
            "ui_rules": ui_rule_bindings,
            "proxy_tool_count": proxy_tool_count,
            "external_tool_count": external_tool_count,
            "recommended_flow": [
                "get_project_usage_guide",
                "get_project_manual",
                "get_project_profile",
                "get_project_runtime_context",
                "list_project_members or list_project_proxy_tools",
                "query_project_rules / invoke_project_skill_tool / invoke_external_mcp_tool",
            ],
            "guide_markdown": "\n".join(guide_lines),
        }

    @mcp.resource(f"project://{project_id}/profile")
    def project_profile() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        mcp_instruction = _resolve_mcp_instruction(project)
        return (
            f"[{project.id}] {project.name}\n"
            f"description: {project.description or '-'}\n"
            f"mcp_instruction: {mcp_instruction or '-'}\n"
            f"usage_guide=project://{project.id}/usage-guide\n"
            f"manual=project://{project.id}/manual\n"
            f"recommended_first_tool=get_project_usage_guide\n"
            f"mcp_enabled={project.mcp_enabled} "
            f"feedback_upgrade_enabled={project.feedback_upgrade_enabled}"
        )

    @mcp.resource(f"project://{project_id}/usage-guide")
    def project_usage_guide() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        return str(_build_usage_guide(project).get("guide_markdown") or "")

    @mcp.resource(f"project://{project_id}/manual")
    def project_manual() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        from routers.projects import _build_project_manual_template_payload

        payload = _build_project_manual_template_payload(project.id)
        return str(payload.get("manual") or "")

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
            lines = []
        else:
            lines = []
            for tool_name, spec in sorted(scoped_proxy_specs.items()):
                lines.append(
                    f"- {tool_name}: {spec['employee_id']} / {spec['skill_name']} / {spec['skill_id']} / "
                    f"{spec['entry_name']} ({spec['script_type']})"
                )
        lines.append(
            f"- {COLLABORATION_TOOL_NAME}: builtin / 多员工协作执行工具"
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
    def get_project_usage_guide() -> dict:
        """获取当前项目 MCP 的使用说明、推荐调用顺序和项目入口文件摘录"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        return _build_usage_guide(project)

    @mcp.tool()
    def get_project_profile() -> dict:
        """获取项目画像配置"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        payload = asdict(project)
        payload["usage_guide_resource"] = f"project://{project.id}/usage-guide"
        payload["manual_resource"] = f"project://{project.id}/manual"
        payload["proxy_tools_resource"] = f"project://{project.id}/proxy-tools"
        payload["external_tools_resource"] = f"project://{project.id}/external-mcp-tools"
        payload["recommended_first_tool"] = "get_project_usage_guide"
        return payload

    @mcp.tool()
    def get_project_manual() -> dict:
        """获取当前项目使用手册正文"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        from routers.projects import _build_project_manual_template_payload

        payload = _build_project_manual_template_payload(project.id)
        return {
            "project_id": project.id,
            "project_name": project.name,
            "manual_resource": f"project://{project.id}/manual",
            "manual": str(payload.get("manual") or ""),
        }

    @mcp.tool()
    def get_project_detail() -> dict:
        """获取当前项目完整详情（含聊天配置、成员清单、用户成员清单）"""
        return get_project_detail_runtime(project_id)

    @mcp.tool()
    def get_project_employee_detail(employee_id: str) -> dict:
        """获取指定项目成员的完整员工详情（含成员关系和员工完整配置）"""
        return get_project_employee_detail_runtime(project_id, employee_id)

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
        ui_rules = project_ui_rule_summary(project.id, limit=30)
        rule_ids: set[str] = set()
        for _member, employee in pairs:
            for rule in _query_rules_by_employee(employee):
                rule_ids.add(rule.id)
        for item in ui_rules:
            rule_id = str(item.get("id") or "").strip()
            if rule_id:
                rule_ids.add(rule_id)
        return {
            "project_id": project.id,
            "project_name": project.name,
            "member_count": len(pairs),
            "members": [employee.id for _member, employee in pairs],
            "scoped_proxy_tool_count": len(scoped_proxy_specs),
            "rule_count": len(rule_ids),
            "ui_rule_count": len(ui_rules),
            "ui_rules": ui_rules,
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
        """检索项目规则，包含项目级 UI 规则与成员规则（支持按 employee_id 过滤成员规则）"""
        project = _get_project()
        if not project:
            return []
        employee_id_value = str(employee_id or "").strip()
        return query_project_rules_runtime(project.id, keyword=keyword, employee_id=employee_id_value)

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
                    "skill_name": spec["skill_name"],
                    "skill_id": spec["skill_id"],
                    "entry_name": spec["entry_name"],
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                }
            )
        tools.append(collaboration_tool_descriptor())
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

    def _invoke_project_tool_local(
        *,
        project_id: str,
        tool_name: str,
        employee_id: str = "",
        args: dict | None = None,
        args_json: str = "{}",
        timeout_sec: int = 30,
    ) -> dict:
        builtin_result = invoke_project_builtin_tool(
            project_id,
            tool_name,
            employee_id,
            args=args,
            args_json=args_json,
        )
        if builtin_result is not None:
            return builtin_result
        if any(str(item.get("tool_name") or "").strip() == str(tool_name or "").strip() for item in external_tool_specs):
            return invoke_external_mcp_tool_runtime(
                project_id=project_id,
                tool_name=tool_name,
                args=args,
                args_json=args_json,
                timeout_sec=timeout_sec,
            )
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

    @mcp.tool()
    def invoke_project_skill_tool(
        tool_name: str,
        employee_id: str = "",
        args: dict | None = None,
        args_json: str = "{}",
        timeout_sec: int = 30,
    ) -> dict:
        """按工具名直接调用项目成员技能脚本（支持 employee_id 消歧）"""
        if str(tool_name or "").strip() == COLLABORATION_TOOL_NAME:
            payload, err = parse_object_args(args=args, args_json=args_json)
            if payload is None:
                return {"error": err}
            return execute_project_collaboration_runtime(
                project_id=project_id,
                task=str(payload.get("task") or "").strip(),
                employee_ids=payload.get("employee_ids") or [],
                max_employees=payload.get("max_employees", 3),
                max_tool_calls=payload.get("max_tool_calls", 6),
                auto_execute=bool(payload.get("auto_execute", True)),
                include_external_tools=bool(payload.get("include_external_tools", True)),
                timeout_sec=timeout_sec,
                invoke_tool=_invoke_project_tool_local,
            )
        return _invoke_project_tool_local(
            project_id=project_id,
            tool_name=tool_name,
            employee_id=employee_id,
            args=args,
            args_json=args_json,
            timeout_sec=timeout_sec,
        )

    @mcp.tool()
    def execute_project_collaboration(
        task: str,
        employee_ids: list[str] | None = None,
        max_employees: int = 3,
        max_tool_calls: int = 6,
        auto_execute: bool = True,
        include_external_tools: bool = True,
        timeout_sec: int = 30,
    ) -> dict:
        """输入用户任务，自动选取项目成员并执行协作编排。"""
        return execute_project_collaboration_runtime(
            project_id=project_id,
            task=task,
            employee_ids=employee_ids or [],
            max_employees=max_employees,
            max_tool_calls=max_tool_calls,
            auto_execute=auto_execute,
            include_external_tools=include_external_tools,
            timeout_sec=timeout_sec,
            invoke_tool=_invoke_project_tool_local,
        )

    for tool_name, spec in sorted(scoped_proxy_specs.items()):
        def _make_proxy_tool(spec_item: dict, tool_name_value: str):
            def _proxy_tool(args: dict | None = None, args_json: str = "{}", timeout_sec: int = 30) -> dict:
                return _execute_skill_proxy(
                    spec_item,
                    project_root=project_root,
                    current_api_key=current_api_key_ctx.get(""),
                    args=args,
                    args_json=args_json,
                    timeout_sec=timeout_sec,
                    employee_id=spec_item["employee_id"],
                )
            _proxy_tool.__name__ = f"project_proxy_{tool_name_value}"
            return _proxy_tool

        mcp.tool(
            name=tool_name,
            description=(
                f"Proxy of {spec['employee_id']}:{spec['skill_name']}:{spec['entry_name']}. "
                "Pass CLI args via args(object) or args_json(string), e.g. args={\"sql\":\"SHOW TABLES\"}."
            ),
        )(_make_proxy_tool(spec, tool_name))

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
