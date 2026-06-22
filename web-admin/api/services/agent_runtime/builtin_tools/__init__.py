"""第一批内置工具：文件、命令、网络和 MCP 工具。

按 docs/liuAgent-cli/design/08-tool-contracts.md 定义实现。
每个工具声明 input_schema、action、risk、requires_approval、scope，
并接入 PermissionPolicy 做路径逃逸检查和命令风险分类。
"""

from services.agent_runtime.builtin_tools.definitions import (
    BUILTIN_TOOL_DEFINITIONS,
    BUILTIN_TOOL_NAMES,
    LOCAL_BUILTIN_TOOL_NAMES,
    MCP_DELEGATED_BUILTIN_TOOL_NAMES,
    get_builtin_tool_definition,
    is_local_builtin_tool,
    is_mcp_delegated_builtin_tool,
    is_builtin_tool,
    iter_builtin_runtime_tools,
)
from services.agent_runtime.builtin_tools.registry import execute_builtin_tool

__all__ = [
    "BUILTIN_TOOL_DEFINITIONS",
    "BUILTIN_TOOL_NAMES",
    "LOCAL_BUILTIN_TOOL_NAMES",
    "MCP_DELEGATED_BUILTIN_TOOL_NAMES",
    "execute_builtin_tool",
    "get_builtin_tool_definition",
    "is_builtin_tool",
    "is_local_builtin_tool",
    "is_mcp_delegated_builtin_tool",
    "iter_builtin_runtime_tools",
]
