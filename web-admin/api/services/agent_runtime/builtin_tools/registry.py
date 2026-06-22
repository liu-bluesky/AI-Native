"""内置工具执行分发注册表。

ToolExecutor 调用 execute_builtin_tool(tool_name, args, workspace_path=...) 
时，按工具名分发到对应实现。
"""

from __future__ import annotations

from typing import Any

from services.agent_runtime.builtin_tools.command_tools import (
    check_command_risk,
    classify_command_risk,
    run_command,
)
from services.agent_runtime.builtin_tools.definitions import (
    BUILTIN_TOOL_NAMES,
    get_builtin_tool_definition,
    is_builtin_tool,
    is_local_builtin_tool,
)
from services.agent_runtime.builtin_tools.file_tools import (
    apply_patch,
    list_files,
    read_file,
    search_text,
    write_file,
)
from services.agent_runtime.builtin_tools.network_tools import (
    download_file,
    http_get,
    http_post,
)

# MCP 工具委托到现有 MCP runtime，不在此重复实现
# list_mcp_tools / read_mcp_resource / call_mcp_tool 由 ToolExecutor 的 MCP 分发路径处理

_DISPATCH: dict[str, Any] = {
    # 文件工具
    "list_files": list_files,
    "read_file": read_file,
    "search_text": search_text,
    "apply_patch": apply_patch,
    "write_file": write_file,
    # 命令工具
    "check_command_risk": check_command_risk,
    "run_command": run_command,
    # 网络工具
    "http_get": http_get,
    "http_post": http_post,
    "download_file": download_file,
}


_TYPE_MAP = {
    "string": str,
    "boolean": bool,
    "object": dict,
    "array": list,
    "number": (int, float),
    "integer": int,
}


def _validate_input_schema(tool_name: str, args: dict[str, Any]) -> str:
    definition = get_builtin_tool_definition(tool_name) or {}
    schema = definition.get("input_schema") if isinstance(definition, dict) else {}
    if not isinstance(schema, dict):
        return ""
    if not isinstance(args, dict):
        return "arguments must be an object"
    required = schema.get("required") or []
    if isinstance(required, list):
        for key in required:
            normalized_key = str(key or "").strip()
            if normalized_key and normalized_key not in args:
                return f"missing required argument: {normalized_key}"
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return ""
    for key, value in args.items():
        if str(key).startswith("_agent_runtime_"):
            continue
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict):
            continue
        expected_type = str(property_schema.get("type") or "").strip()
        expected_python_type = _TYPE_MAP.get(expected_type)
        if expected_python_type is None or value is None:
            continue
        if expected_type == "number" and isinstance(value, bool):
            return f"argument {key} must be number"
        if expected_type == "integer" and isinstance(value, bool):
            return f"argument {key} must be integer"
        if not isinstance(value, expected_python_type):
            return f"argument {key} must be {expected_type}"
    return ""


async def execute_builtin_tool(
    tool_name: str,
    args: dict[str, Any],
    *,
    workspace_path: str = "",
) -> dict[str, Any]:
    """执行内置工具，返回 ToolResult 格式的 dict。"""
    normalized = str(tool_name or "").strip()
    handler = _DISPATCH.get(normalized)
    if handler is None:
        if normalized in BUILTIN_TOOL_NAMES:
            # MCP 工具不在此实现，交由 ToolExecutor 的 MCP 路径
            return {
                "ok": False,
                "error": f"MCP tool {normalized} should be routed through MCP runtime",
                "error_code": "tool.mcp_delegated",
            }
        return {
            "ok": False,
            "error": f"unknown builtin tool: {normalized}",
            "error_code": "tool.not_found",
        }

    if not is_local_builtin_tool(normalized):
        return {
            "ok": False,
            "error": f"builtin tool {normalized} is not executable locally",
            "error_code": "tool.mcp_delegated",
        }

    schema_error = _validate_input_schema(normalized, args)
    if schema_error:
        return {
            "ok": False,
            "error": schema_error,
            "error_code": "tool.schema_invalid",
        }

    if not workspace_path:
        return {
            "ok": False,
            "error": "workspace_path is required for builtin tools",
            "error_code": "tool.schema_invalid",
        }

    try:
        return await handler(workspace_path, args)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"builtin tool {normalized} failed: {exc}",
            "error_code": "tool.schema_invalid",
        }


def get_builtin_tool_risk_override(tool_name: str, args: dict[str, Any]) -> str:
    """根据工具参数动态计算风险等级。

    用于 PermissionPolicy 的 risk_level 计算：write_file 覆盖已有文件升为 high，
    run_command 按命令内容分类。
    """
    normalized = str(tool_name or "").strip()

    if normalized == "write_file":
        overwrite = bool(args.get("overwrite", False))
        return "high" if overwrite else "medium"

    if normalized == "run_command":
        cmd = str(args.get("cmd") or "").strip()
        if cmd:
            risk, _ = classify_command_risk(cmd)
            return risk
        return "medium"

    if normalized == "http_post":
        return "high"

    return ""


__all__ = [
    "execute_builtin_tool",
    "get_builtin_tool_risk_override",
    "is_builtin_tool",
]
