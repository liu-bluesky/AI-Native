//! 内置工具定义注册表。
//!
//! 先声明内置工具契约；执行侧按工具实现进度逐步开放。

use serde_json::json;

use super::types::ToolDefinition;

pub fn builtin_tool_definitions() -> Vec<ToolDefinition> {
    vec![
        ToolDefinition {
            name: "update_execution_plan",
            description: "为当前复杂任务创建或更新执行计划。仅当任务确实需要多个步骤时调用；简单问答不要调用。steps 必须是按执行顺序排列的具体步骤，数量 2-8；同一时刻最多一个 in_progress，已完成步骤不得退回 pending 或 in_progress。",
            action: "plan.update",
            risk: "low",
            requires_approval: false,
            scope: "session",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "explanation": {
                        "type": "string",
                        "description": "本次创建或调整计划的简短原因"
                    },
                    "steps": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "面向用户目标的具体动作，不要写理解目标、推进目标等固定模板"
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed", "blocked"]
                                }
                            },
                            "required": ["title", "status"]
                        }
                    }
                },
                "required": ["steps"]
            }),
        },
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
            description: "在本地 workspace 内执行命令。预计会退出的命令使用前台模式；服务器、watcher、开发服务等长期运行命令必须设置 background=true，工具会立即返回 session_id，后续统一使用 process 工具查询日志、等待、输入或终止。",
            action: "command.run",
            risk: "medium",
            requires_approval: true,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "cwd": {"type": "string", "default": "."},
                    "background": {
                        "type": "boolean",
                        "default": false,
                        "description": "是否创建后台进程会话。服务器、watcher、npm run dev 等不会自行退出的命令应设为 true；成功后立即返回 session_id。"
                    },
                    "timeout_ms": {
                        "type": "number",
                        "default": 30000,
                        "description": "前台命令最长等待时间，默认 30 秒，最大 21600000ms；background=true 时后台进程立即返回 session_id，不使用该值等待退出。"
                    },
                    "max_output_chars": {"type": "number", "default": 20000}
                },
                "required": ["cmd"]
            }),
        },
        ToolDefinition {
            name: "process",
            description: "管理 run_command(background=true) 创建的后台进程。使用 action=list 列出进程；poll 查询状态和本次新增输出；log 分页读取日志；wait 在有限时间内等待退出；kill 终止整个进程组，并由 Runtime 权限门冻结本次准确调用等待用户确认，模型不得先用自然语言询问；write 写入原始 stdin；submit 写入并追加回车；close 关闭 stdin 并发送 EOF。",
            action: "command.process",
            risk: "low",
            requires_approval: false,
            scope: "workspace",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "poll", "log", "wait", "kill", "write", "submit", "close"]
                    },
                    "session_id": {
                        "type": "string",
                        "description": "run_command 后台模式返回的进程会话 ID；list 之外的 action 必填。"
                    },
                    "data": {
                        "type": "string",
                        "description": "write 或 submit 写入 stdin 的文本。"
                    },
                    "timeout_ms": {
                        "type": "number",
                        "default": 5000,
                        "description": "wait 最长等待毫秒数，最大 300000。"
                    },
                    "offset": {
                        "type": "number",
                        "default": 0,
                        "description": "log 的起始行；0 表示读取最后 limit 行。"
                    },
                    "limit": {
                        "type": "number",
                        "default": 200,
                        "description": "log 返回的最大行数，最大 2000。"
                    }
                },
                "required": ["action"]
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
            name: "web_search",
            description: "搜索网络信息，返回标题、URL、摘要和来源后端。搜索结果是候选信息；是否需要继续打开页面、读取正文或补充核查，由模型根据用户目标、结果质量和任务风险判断。",
            action: "network.search",
            risk: "medium",
            requires_approval: false,
            scope: "network",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "number", "default": 5},
                    "timeout_ms": {"type": "number", "default": 30000}
                },
                "required": ["query"]
            }),
        },
        ToolDefinition {
            name: "web_extract",
            description: "从指定网页 URL 抽取正文内容，返回 URL、标题、正文和截断状态。用于需要比搜索摘要更完整正文的场景；是否调用由模型根据任务目标和搜索结果质量判断。",
            action: "network.extract",
            risk: "medium",
            requires_approval: false,
            scope: "network",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 5
                    },
                    "format": {"type": "string", "default": "markdown"},
                    "timeout_ms": {"type": "number", "default": 30000}
                },
                "required": ["urls"]
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
            name: "list_projects",
            description: "列出当前桌面登录用户在后端有权限访问的真实项目列表。用户询问“项目列表 / 有哪些项目 / 列出项目”时优先使用本工具；不要用 desktop-bot-global 或本地 workspace 目录缓存冒充真实项目列表。",
            action: "project.list",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "page": {"type": "number", "default": 1},
                    "page_size": {"type": "number", "default": 20},
                    "name": {"type": "string", "description": "按项目名称关键词过滤，可选"},
                    "created_by": {"type": "string", "description": "按创建人过滤，可选"},
                    "timeout_ms": {"type": "number", "default": 30000}
                }
            }),
        },
        ToolDefinition {
            name: "get_project",
            description: "读取当前桌面登录用户有权限访问的真实项目详情及项目绑定智能体清单。回答项目绑定几个/哪些智能体时，必须使用 bound_agent_count / bound_agents；selected_employee_ids 为空仅表示自动分配。",
            action: "project.read",
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
            name: "deploy_workspace_files_to_target",
            description: "桌面智能体直连部署主工具。由桌面 AI 先调用 get_project_deploy_options 读取配置并让用户选择 profile/component/target 后，由桌面运行时直接把 workspace 内的原文件、目录或文件清单上传到目标 FTP 服务器，文件不经过业务后端中转；后端仅负责权限校验、提供本次部署连接配置、执行已配置 deploy_command、发送配置通知和接收结果。FTP 凭据不会进入模型上下文或工具结果。上传目录时按根层文件和文件夹生成任务，实际并发受 FTP 连接的最大上传线程数限制。只有本工具返回 deployment_confirmed_success=true/status=success 时，才允许回复部署成功。",
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
    ]
}
