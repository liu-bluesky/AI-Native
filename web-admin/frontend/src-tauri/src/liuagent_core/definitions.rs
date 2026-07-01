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
                    "timeout_ms": {
                        "type": "number",
                        "default": 30000,
                        "description": "命令超时时间。普通命令默认 30 秒；构建、测试、打包、部署类命令可设置到小时级，最大 21600000ms。"
                    },
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
            name: "get_project_deploy_options",
            description: "读取当前项目后端部署配置摘要（脱敏），包含可选 profile、component、target、remote_path、artifact_kind、是否存在 deploy_command、notify_enabled。部署/发布/上线类任务必须先调用该工具，再让用户选择环境和目标；该工具只读，不上传、不部署、不返回服务器凭据。",
            action: "deploy.options.read",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "timeout_ms": {"type": "number", "default": 30000}
                },
                "required": ["project_id"]
            }),
        },
        ToolDefinition {
            name: "upload_deploy_artifact",
            description: "仅当用户明确要求“上传到部署产物模块/只上传部署产物”时使用：把本地 workspace 内已生成的部署产物直连上传到后端项目部署产物模块。上传规则是“原文件是什么就上传什么”：artifact_path 指向单个文件时原样上传该文件；artifact_path 指向目录或 artifact_paths 传多个文件时，用 multipart 逐个上传原文件并保存为目录型产物，不会压缩成 zip/tar。静态页面/多 HTML/CSS/JS/图片文件必须上传目录或 artifact_paths，禁止为了搬运多文件自行创建压缩包。该工具不代表远端已部署成功；桌面智能体部署主流程应优先使用 deploy_workspace_files_to_target。",
            action: "deploy.artifact.upload",
            risk: "high",
            requires_approval: true,
            scope: "network",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "artifact_path": {"type": "string", "description": "workspace 内部署产物路径；可指向单个文件或目录。目录会按目录型产物上传并保留相对路径。"},
                    "artifact_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "workspace 内多个部署文件路径清单。适合直接上传若干 HTML/CSS/JS/图片等静态文件；后端会保存为目录型产物。传该字段时优先于 artifact_path。"
                    },
                    "artifact_root": {
                        "type": "string",
                        "description": "artifact_paths 的相对路径根目录；例如传 . 时保留 login/index.html，传 dist 时保留 dist 内部路径。"
                    },
                    "profile": {"type": "string", "default": "prod"},
                    "component": {"type": "string", "default": ""},
                    "target_ids": {"type": "array", "items": {"type": "string"}},
                    "artifact_name": {"type": "string"},
                    "artifact_kind": {"type": "string", "default": "source-bundle"},
                    "version": {"type": "string"},
                    "manifest": {"type": "object"},
                    "auto_deploy": {"type": "boolean", "default": true},
                    "ai_deploy": {"type": "boolean", "default": true},
                    "chat_session_id": {"type": "string"},
                    "task_tree_node_id": {"type": "string"},
                    "requirement": {"type": "string"},
                    "plan": {"type": "string"},
                    "timeout_ms": {"type": "number", "default": 120000}
                },
                "required": ["project_id"],
                "anyOf": [
                    {"required": ["artifact_path"]},
                    {"required": ["artifact_paths"]}
                ]
            }),
        },
        ToolDefinition {
            name: "deploy_workspace_files_to_target",
            description: "桌面智能体直连部署主工具。由桌面 AI 先调用 get_project_deploy_options 读取配置并让用户选择 profile/component/target 后，再把 workspace 内的原文件、目录或文件清单直接上传到项目部署配置里的目标服务器；后端只使用已保存的部署配置和凭据执行 FTP 上传、已配置 deploy_command 和配置通知，不创建部署产物记录，不调用部署产物 AI，不接受自定义服务器凭据或自定义远端命令。上传规则是“原文件是什么就部署什么”：目录和 artifact_paths 会逐个 multipart 上传原文件并保留相对路径，禁止为了多文件部署自行创建 zip/tar；只有用户指定的原始产物本身就是 zip/tar 时，才按单个原文件部署。只有本工具返回 deployment_confirmed_success=true/status=success 时，才允许回复部署成功。",
            action: "deploy.direct.upload",
            risk: "high",
            requires_approval: true,
            scope: "network",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "artifact_path": {"type": "string", "description": "workspace 内要部署的源路径；可指向单个文件或目录。目录会递归上传原文件并保留相对路径。"},
                    "artifact_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "workspace 内多个部署文件路径清单。适合直接部署若干 HTML/CSS/JS/图片等静态文件。"
                    },
                    "artifact_root": {
                        "type": "string",
                        "description": "artifact_paths 的相对路径根目录；例如传 . 时保留 login/index.html，传 dist 时保留 dist 内部路径。"
                    },
                    "profile": {"type": "string", "default": "prod"},
                    "component": {"type": "string", "default": ""},
                    "target_ids": {"type": "array", "items": {"type": "string"}},
                    "artifact_name": {"type": "string"},
                    "artifact_kind": {"type": "string", "default": "source-bundle"},
                    "version": {"type": "string"},
                    "manifest": {"type": "object"},
                    "run_deploy_command": {"type": "boolean", "default": true, "description": "是否触发目标中已配置的 deploy_command；不能传自定义命令。"},
                    "chat_session_id": {"type": "string"},
                    "task_tree_node_id": {"type": "string"},
                    "requirement": {"type": "string"},
                    "plan": {"type": "string"},
                    "timeout_ms": {"type": "number", "default": 600000}
                },
                "required": ["project_id"],
                "anyOf": [
                    {"required": ["artifact_path"]},
                    {"required": ["artifact_paths"]}
                ]
            }),
        },
        ToolDefinition {
            name: "list_mcp_tools",
            description: "列出本机外部 MCP adapter 工具。仅当用户已显式配置本地 stdio MCP adapter 时使用；这不是桌面端系统 MCP 或项目上下文入口。",
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
            description: "读取本机外部 MCP adapter 资源。仅当用户已显式配置本地 stdio MCP adapter 时使用；不要用它读取桌面端系统 MCP、项目配置、提示词或任务树。",
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
            description: "调用本机外部 MCP adapter 工具。仅当用户已显式配置本地 stdio MCP adapter 时使用；不要用它调用桌面端系统 MCP 或项目内置工具。",
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
