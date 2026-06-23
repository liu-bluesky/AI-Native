//! 内置工具定义注册表。
//!
//! 先声明内置工具契约；执行侧按工具实现进度逐步开放。

use serde_json::json;

use super::types::ToolDefinition;

pub fn builtin_tool_definitions() -> Vec<ToolDefinition> {
    vec![
        ToolDefinition {
            name: "list_files",
            description: "列出本地 workspace 内目录内容",
            action: "file.read",
            risk: "low",
            requires_approval: false,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "max_depth": {"type": "number", "default": 2},
                    "include_hidden": {"type": "boolean", "default": false}
                }
            }),
        },
        ToolDefinition {
            name: "read_file",
            description: "读取本地 workspace 内文件内容",
            action: "file.read",
            risk: "low",
            requires_approval: false,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "number", "default": 1},
                    "line_count": {"type": "number", "default": 200}
                },
                "required": ["path"]
            }),
        },
        ToolDefinition {
            name: "search_text",
            description: "在本地 workspace 内搜索文本",
            action: "file.read",
            risk: "low",
            requires_approval: false,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                    "glob": {"type": "string"},
                    "max_results": {"type": "number", "default": 50}
                },
                "required": ["query"]
            }),
        },
        ToolDefinition {
            name: "apply_patch",
            description: "在本地 workspace 内应用 unified diff patch",
            action: "file.write",
            risk: "medium",
            requires_approval: true,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "patch": {"type": "string"},
                    "summary": {"type": "string"}
                },
                "required": ["patch", "summary"]
            }),
        },
        ToolDefinition {
            name: "write_file",
            description: "写入或创建本地 workspace 内文件。必须同时提供 path 和 content，例如 {\"path\":\"register.html\",\"content\":\"完整文件内容\",\"overwrite\":false}。创建新文件时 overwrite=false；覆盖已有文件时 overwrite=true。",
            action: "file.write",
            risk: "medium",
            requires_approval: true,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对 workspace 的目标文件路径，例如 register.html 或 login/register.html。不得省略。"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入目标文件的完整文本内容。不得省略。"
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": false,
                        "description": "目标文件已存在且需要替换时设为 true；创建新文件时通常为 false。"
                    }
                },
                "required": ["path", "content"]
            }),
        },
        ToolDefinition {
            name: "delete_file",
            description: "删除本地 workspace 内文件，必须经过用户授权并验证删除结果",
            action: "file.delete",
            risk: "high",
            requires_approval: true,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }),
        },
        ToolDefinition {
            name: "check_command_risk",
            description: "检查本地命令风险，不执行命令",
            action: "command.check",
            risk: "low",
            requires_approval: false,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "cwd": {"type": "string", "default": "."}
                },
                "required": ["cmd"]
            }),
        },
        ToolDefinition {
            name: "run_command",
            description: "在本地 workspace 内执行命令",
            action: "command.run",
            risk: "medium",
            requires_approval: true,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "cwd": {"type": "string", "default": "."},
                    "timeout_ms": {"type": "number", "default": 30000},
                    "max_output_chars": {"type": "number", "default": 20000}
                },
                "required": ["cmd"]
            }),
        },
        ToolDefinition {
            name: "http_get",
            description: "发起 HTTP GET 请求",
            action: "network.read",
            risk: "medium",
            requires_approval: true,
            scope: "network",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "headers": {"type": "object"},
                    "timeout_ms": {"type": "number", "default": 30000}
                },
                "required": ["url"]
            }),
        },
        ToolDefinition {
            name: "http_post",
            description: "发起 HTTP POST 请求",
            action: "network.write",
            risk: "high",
            requires_approval: true,
            scope: "network",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "headers": {"type": "object"},
                    "body": {},
                    "timeout_ms": {"type": "number", "default": 30000}
                },
                "required": ["url", "body"]
            }),
        },
        ToolDefinition {
            name: "download_file",
            description: "下载文件到本地 workspace",
            action: "network.read",
            risk: "medium",
            requires_approval: true,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "dest_path": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": false},
                    "timeout_ms": {"type": "number", "default": 30000}
                },
                "required": ["url", "dest_path"]
            }),
        },
        ToolDefinition {
            name: "list_mcp_tools",
            description: "列出本地可用 MCP 工具",
            action: "mcp.list",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "server": {"type": "string"}
                }
            }),
        },
        ToolDefinition {
            name: "read_mcp_resource",
            description: "读取 MCP 资源",
            action: "mcp.read",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "server": {"type": "string"},
                    "uri": {"type": "string"}
                },
                "required": ["server", "uri"]
            }),
        },
        ToolDefinition {
            name: "call_mcp_tool",
            description: "调用 MCP 工具",
            action: "mcp.call",
            risk: "medium",
            requires_approval: true,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "server": {"type": "string"},
                    "tool": {"type": "string"},
                    "arguments": {"type": "object"}
                },
                "required": ["server", "tool"]
            }),
        },
    ]
}
