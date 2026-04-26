"""Minimal tool registry helpers for chat runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class EffectiveToolDescriptor:
    tool_name: str
    source: str
    description: str = ""


def resolve_chat_workspace_path(
    project_workspace_path: str,
    settings: dict[str, Any] | None,
) -> str:
    source = settings if isinstance(settings, dict) else {}
    connector_workspace_path = str(source.get("connector_workspace_path") or "").strip()
    if connector_workspace_path:
        return connector_workspace_path
    return str(project_workspace_path or "").strip()


def normalize_connector_sandbox_mode(
    value: Any,
    *,
    default: str = "workspace-write",
) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"read-only", "workspace-write"} else default


def filter_tools_by_names(
    tools: list[dict[str, Any]],
    enabled_tool_names: list[str] | None,
) -> list[dict[str, Any]]:
    normalized = [
        str(item or "").strip()
        for item in (enabled_tool_names or [])
        if str(item or "").strip()
    ]
    allowed = set(normalized)
    if not allowed:
        return list(tools)
    return [
        item
        for item in tools
        if str(item.get("tool_name") or "").strip() in allowed
    ]


def filter_tools_by_employee_ids(
    tools: list[dict[str, Any]],
    employee_ids: list[str] | None,
) -> list[dict[str, Any]]:
    normalized = [
        str(item or "").strip()
        for item in (employee_ids or [])
        if str(item or "").strip()
    ]
    allowed = set(normalized)
    if not allowed:
        return list(tools)
    filtered: list[dict[str, Any]] = []
    for item in tools:
        employee_id = str(item.get("employee_id") or "").strip()
        if not employee_id or employee_id in allowed:
            filtered.append(item)
    return filtered


def sort_tools_by_priority(
    tools: list[dict[str, Any]],
    tool_priority: list[str] | None,
) -> list[dict[str, Any]]:
    normalized = [
        str(item or "").strip()
        for item in (tool_priority or [])
        if str(item or "").strip()
    ]
    if not normalized:
        return list(tools)
    priority_map = {name: idx for idx, name in enumerate(normalized)}
    return sorted(
        tools,
        key=lambda item: (
            priority_map.get(str(item.get("tool_name") or "").strip(), 10**9),
            str(item.get("tool_name") or "").strip(),
        ),
    )


def infer_tool_source(item: dict[str, Any]) -> str:
    tool_name = str(item.get("tool_name") or "").strip()
    module_type = str(item.get("module_type") or "").strip().lower()
    if tool_name == "project_host_run_command":
        return "local_host"
    if tool_name.startswith("local_connector_"):
        return "local_connector"
    if module_type == "external_mcp_tool":
        return "external_mcp"
    if module_type == "system_mcp_tool":
        return "system_mcp"
    if bool(item.get("builtin")) or str(item.get("skill_id") or "").strip() == "__builtin__":
        return "builtin"
    if str(item.get("employee_id") or "").strip():
        return "project_skill"
    return "project_tool"


def summarize_effective_tools(
    tools: list[dict[str, Any]] | None,
    *,
    max_items: int = 24,
) -> tuple[list[dict[str, str]], int]:
    source_tools = tools if isinstance(tools, list) else []
    summarized: list[dict[str, str]] = []
    for item in source_tools[:max_items]:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            continue
        descriptor = EffectiveToolDescriptor(
            tool_name=tool_name,
            source=infer_tool_source(item),
            description=str(item.get("description") or "").strip(),
        )
        summarized.append(
            {
                "tool_name": descriptor.tool_name,
                "source": descriptor.source,
                "description": descriptor.description,
            }
        )
    return summarized, len(source_tools)


def resolve_local_connector_runtime_tools(
    settings: dict[str, Any] | None,
    workspace_path: str,
    *,
    resolve_local_connector: Callable[[str], Any | None],
    build_connector_tools: Callable[[], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], Any | None, str]:
    source = settings if isinstance(settings, dict) else {}
    connector_id = str(source.get("local_connector_id") or "").strip()
    sandbox_mode = normalize_connector_sandbox_mode(
        source.get("connector_sandbox_mode"),
    )
    effective_workspace_path = resolve_chat_workspace_path(workspace_path, source)
    if not connector_id:
        return [], None, sandbox_mode
    connector = resolve_local_connector(connector_id)
    if connector is None or not effective_workspace_path:
        return [], connector, sandbox_mode

    normalized_tools: list[dict[str, Any]] = []
    for item in build_connector_tools() or []:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            continue
        tool_payload = dict(item)
        tool_payload.setdefault("workspace_path", effective_workspace_path)
        tool_payload.setdefault("sandbox_mode", sandbox_mode)
        normalized_tools.append(tool_payload)
    return normalized_tools, connector, sandbox_mode


def collect_project_runtime_tools(
    project_id: str,
    *,
    selected_employee_ids: list[str] | None,
    enabled_tool_names: list[str] | None,
    tool_priority: list[str] | None,
    list_internal_tools: Callable[[str], list[dict[str, Any]]],
    list_external_tools: Callable[[str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    internal_tools = filter_tools_by_employee_ids(
        list_internal_tools(project_id),
        selected_employee_ids,
    )
    internal_tools = filter_tools_by_names(
        internal_tools,
        enabled_tool_names,
    )
    external_tools = list_external_tools(project_id)
    return sort_tools_by_priority(
        internal_tools + external_tools,
        list(tool_priority or []),
    )
