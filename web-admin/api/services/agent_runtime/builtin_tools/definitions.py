"""内置工具定义注册表。

按 docs/liuAgent-cli/design/08-tool-contracts.md 声明每个工具的
name、description、input_schema、action、risk、requires_approval、scope。
"""

from __future__ import annotations

from typing import Any


LOCAL_BUILTIN_TOOL_NAMES = frozenset(
    {
        "list_files",
        "read_file",
        "search_text",
        "apply_patch",
        "write_file",
        "check_command_risk",
        "run_command",
        "http_get",
        "http_post",
        "download_file",
    }
)

MCP_DELEGATED_BUILTIN_TOOL_NAMES = frozenset(
    {
        "list_mcp_tools",
        "read_mcp_resource",
        "call_mcp_tool",
    }
)


def _file_entry_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对 workspace 的路径", "default": "."},
            "max_depth": {"type": "number", "description": "最大递归深度", "default": 2},
            "include_hidden": {"type": "boolean", "description": "是否包含隐藏文件", "default": False},
        },
    }


def _read_file_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对 workspace 的文件路径"},
            "start_line": {"type": "number", "description": "起始行（从 1 开始）", "default": 1},
            "line_count": {"type": "number", "description": "读取行数", "default": 200},
        },
        "required": ["path"],
    }


def _search_text_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索文本"},
            "path": {"type": "string", "description": "搜索目录", "default": "."},
            "glob": {"type": "string", "description": "文件过滤 glob"},
            "max_results": {"type": "number", "description": "最大结果数", "default": 50},
        },
        "required": ["query"],
    }


def _apply_patch_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "patch": {"type": "string", "description": "unified diff patch"},
            "summary": {"type": "string", "description": "修改目的"},
        },
        "required": ["patch", "summary"],
    }


def _write_file_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对 workspace 的文件路径"},
            "content": {"type": "string", "description": "文件内容"},
            "overwrite": {"type": "boolean", "description": "是否覆盖已有文件", "default": False},
        },
        "required": ["path", "content"],
    }


def _check_command_risk_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "cmd": {"type": "string", "description": "要检查的命令"},
            "cwd": {"type": "string", "description": "工作目录", "default": "."},
        },
        "required": ["cmd"],
    }


def _run_command_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "cmd": {"type": "string", "description": "要执行的命令"},
            "cwd": {"type": "string", "description": "工作目录", "default": "."},
            "timeout_ms": {"type": "number", "description": "超时（毫秒）", "default": 30000},
            "max_output_chars": {"type": "number", "description": "最大输出字符数", "default": 20000},
        },
        "required": ["cmd"],
    }


def _http_get_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "请求 URL"},
            "headers": {"type": "object", "description": "请求头"},
            "timeout_ms": {"type": "number", "description": "超时（毫秒）", "default": 30000},
        },
        "required": ["url"],
    }


def _http_post_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "请求 URL"},
            "headers": {"type": "object", "description": "请求头"},
            "body": {"description": "请求体"},
            "timeout_ms": {"type": "number", "description": "超时（毫秒）", "default": 30000},
        },
        "required": ["url", "body"],
    }


def _download_file_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "下载 URL"},
            "dest_path": {"type": "string", "description": "保存路径（相对 workspace）"},
            "overwrite": {"type": "boolean", "description": "是否覆盖", "default": False},
            "timeout_ms": {"type": "number", "description": "超时（毫秒）", "default": 30000},
        },
        "required": ["url", "dest_path"],
    }


def _list_mcp_tools_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "指定 MCP server 名"},
        },
    }


def _read_mcp_resource_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "MCP server 名"},
            "uri": {"type": "string", "description": "资源 URI"},
        },
        "required": ["server", "uri"],
    }


def _call_mcp_tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "MCP server 名"},
            "tool": {"type": "string", "description": "MCP tool 名"},
            "arguments": {"type": "object", "description": "工具参数"},
        },
        "required": ["server", "tool"],
    }


# 工具定义注册表
# action 对应权限策略动作名；risk 是默认风险等级；requires_approval 控制是否默认需要确认
BUILTIN_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "list_files": {
        "name": "list_files",
        "description": "列出目录内容",
        "input_schema": _file_entry_schema(),
        "action": "file.read",
        "risk": "low",
        "requires_approval": False,
        "scope": "workspace",
    },
    "read_file": {
        "name": "read_file",
        "description": "读取文件内容",
        "input_schema": _read_file_schema(),
        "action": "file.read",
        "risk": "low",
        "requires_approval": False,
        "scope": "workspace",
    },
    "search_text": {
        "name": "search_text",
        "description": "在 workspace 内搜索文本",
        "input_schema": _search_text_schema(),
        "action": "file.read",
        "risk": "low",
        "requires_approval": False,
        "scope": "workspace",
    },
    "apply_patch": {
        "name": "apply_patch",
        "description": "应用 unified diff patch 修改文件",
        "input_schema": _apply_patch_schema(),
        "action": "file.write",
        "risk": "medium",
        "requires_approval": True,
        "scope": "workspace",
    },
    "write_file": {
        "name": "write_file",
        "description": "写入或创建文件",
        "input_schema": _write_file_schema(),
        "action": "file.write",
        "risk": "medium",
        "requires_approval": True,
        "scope": "workspace",
    },
    "check_command_risk": {
        "name": "check_command_risk",
        "description": "检查命令的风险等级（不执行命令）",
        "input_schema": _check_command_risk_schema(),
        "action": "command.check",
        "risk": "low",
        "requires_approval": False,
        "scope": "workspace",
    },
    "run_command": {
        "name": "run_command",
        "description": "在 workspace 内执行命令",
        "input_schema": _run_command_schema(),
        "action": "command.run",
        "risk": "medium",
        "requires_approval": True,
        "scope": "workspace",
    },
    "http_get": {
        "name": "http_get",
        "description": "发起 HTTP GET 请求",
        "input_schema": _http_get_schema(),
        "action": "network.read",
        "risk": "medium",
        "requires_approval": True,
        "scope": "network",
    },
    "http_post": {
        "name": "http_post",
        "description": "发起 HTTP POST 请求",
        "input_schema": _http_post_schema(),
        "action": "network.write",
        "risk": "high",
        "requires_approval": True,
        "scope": "network",
    },
    "download_file": {
        "name": "download_file",
        "description": "下载文件到 workspace",
        "input_schema": _download_file_schema(),
        "action": "network.read",
        "risk": "medium",
        "requires_approval": True,
        "scope": "workspace",
    },
    "list_mcp_tools": {
        "name": "list_mcp_tools",
        "description": "列出可用的 MCP 工具",
        "input_schema": _list_mcp_tools_schema(),
        "action": "mcp.list",
        "risk": "low",
        "requires_approval": False,
        "scope": "project",
    },
    "read_mcp_resource": {
        "name": "read_mcp_resource",
        "description": "读取 MCP 资源",
        "input_schema": _read_mcp_resource_schema(),
        "action": "mcp.read",
        "risk": "low",
        "requires_approval": False,
        "scope": "project",
    },
    "call_mcp_tool": {
        "name": "call_mcp_tool",
        "description": "调用 MCP 工具",
        "input_schema": _call_mcp_tool_schema(),
        "action": "mcp.call",
        "risk": "medium",
        "requires_approval": True,
        "scope": "project",
    },
}

BUILTIN_TOOL_NAMES = frozenset(BUILTIN_TOOL_DEFINITIONS.keys())


def is_builtin_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() in BUILTIN_TOOL_NAMES


def get_builtin_tool_definition(tool_name: str) -> dict[str, Any] | None:
    return BUILTIN_TOOL_DEFINITIONS.get(str(tool_name or "").strip())


def is_local_builtin_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() in LOCAL_BUILTIN_TOOL_NAMES


def is_mcp_delegated_builtin_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() in MCP_DELEGATED_BUILTIN_TOOL_NAMES


def _audit_policy_for_risk(risk: str) -> str:
    normalized = str(risk or "").strip().lower()
    if normalized in {"high", "critical"}:
        return "full"
    if normalized == "medium":
        return "standard"
    return "summary"


def iter_builtin_runtime_tools() -> list[dict[str, Any]]:
    """Return built-in definitions in the runtime tool catalog shape."""
    entries: list[dict[str, Any]] = []
    for name, definition in BUILTIN_TOOL_DEFINITIONS.items():
        risk = str(definition.get("risk") or "low").strip().lower() or "low"
        scope = str(definition.get("scope") or "workspace").strip() or "workspace"
        execution_backend = "builtin" if name in LOCAL_BUILTIN_TOOL_NAMES else "mcp"
        entries.append(
            {
                "tool_name": name,
                "name": name,
                "description": str(definition.get("description") or "").strip(),
                "parameters_schema": dict(definition.get("input_schema") or {}),
                "input_schema": dict(definition.get("input_schema") or {}),
                "action": str(definition.get("action") or "").strip(),
                "risk_level": risk,
                "risk": risk,
                "permission_scope": scope,
                "scope": scope,
                "source": "builtin",
                "builtin": True,
                "requires_approval": bool(definition.get("requires_approval")),
                "requires_trust": scope in {"workspace", "host", "local"},
                "execution_backend": execution_backend,
                "audit_policy": _audit_policy_for_risk(risk),
                "installed": True,
                "load_status": "available",
                "version": "builtin",
            }
        )
    return entries
