//! 内置工具定义注册表。
//!
//! 先声明内置工具契约；执行侧按工具实现进度逐步开放。

use serde_json::json;

use super::types::ToolDefinition;

pub fn builtin_tool_definitions() -> Vec<ToolDefinition> {
    vec![
        ToolDefinition {
            name: "ask_user_question",
            description: "仅当用户已经提出明确任务，且缺少会改变执行结果、只能由用户决定、无法从上下文读取或安全采用默认值的关键信息时使用。调用后 Runtime 会暂停当前工具循环并展示问题；收到答案后会从同一个工具调用继续。不要把问候、闲聊、能力咨询、泛泛的“想做什么”澄清、内部错误、可自行读取/推断的信息或非关键偏好交给用户；非关键缺失应采用合理默认值并继续。一次最多提出 3 个具体问题。每个问题必须明确设置 multi_select：互斥答案只能选一个时设为 false；多个答案可以同时成立、用户可能需要组合选择时设为 true。",
            action: "interaction.ask_user",
            risk: "low",
            requires_approval: false,
            scope: "session",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "question": {"type": "string"},
                                "header": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "maxItems": 5,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "label": {"type": "string"},
                                            "description": {"type": "string"}
                                        },
                                        "required": ["label"]
                                    }
                                },
                                "multi_select": {
                                    "type": "boolean",
                                    "description": "是否允许同时选择多个选项。互斥方向、唯一名称、单一受众设为 false；技术栈、能力范围、交付物、需要同时包含的内容设为 true。"
                                }
                            },
                            "required": ["id", "question", "multi_select"]
                        }
                    }
                },
                "required": ["questions"]
            }),
        },
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
            description: "实际执行本机 workspace 内的 Shell/终端命令。用于运行 Git、npm、cargo、测试、构建、脚本和其他命令，例如 git status、git pull origin main、npm run build、cargo test。cmd 是要执行的完整命令，cwd 是运行目录，默认使用当前 workspace。普通的短命令使用 background=false；只有服务器、watcher、消费者等持续运行的进程才使用 background=true。此工具会真正执行命令；check_command_risk 只检查风险而不执行命令，process 只管理已创建的后台进程。",
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
                        "description": "是否创建后台进程会话。成功后立即返回 session_id。"
                    },
                    "notify_on_complete": {
                        "type": "boolean",
                        "default": true,
                        "description": "仅配合 background=true 使用。有限后台任务默认在进程退出时由 Runtime 主动通知模型。与 watch_patterns 同时提供时，以 notify_on_complete 为准。"
                    },
                    "watch_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 20,
                        "description": "仅配合 background=true 使用。适用于不会自行退出的常驻任务；输出首次包含任一目标字符串时 Runtime 主动通知模型，进程保持运行。例如 Worker ready、Watching for changes。不要用它匹配高频日志。"
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
            description: "管理 run_command(background=true) 创建的后台进程。正常完成和目标信号由 Runtime 主动反馈 AI；poll/wait 仅用于人工诊断或通知监听失败后的恢复。log 分页读取日志；kill 终止整个进程组；write 写入原始 stdin；submit 写入并追加回车；close 关闭 stdin 并发送 EOF。",
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
            name: "generate_image",
            description: "调用统一的图片生成工具协议，由当前配置的供应商适配器连接图片模型，从零创建新图片。只有用户要求生成、绘制不依赖现有图片的新图片时调用；只接受文字提示词。凡是基于现有图片生成或修改，都必须调用 edit_image，禁止改用 run_command、Python、Pillow 或 OpenCV。供应商不支持该能力时必须如实返回失败，不得伪造结果或静默切换成本地脚本。",
            action: "media.image.generate",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "完整的图片生成提示词"}
                },
                "required": ["prompt"]
            }),
        },
        ToolDefinition {
            name: "edit_image",
            description: "调用统一的图片编辑工具协议，由当前配置的供应商适配器连接图片模型，编辑一张或多张现有图片；该工具同时覆盖图改图和基于参考图生成。必须在 input_asset_ids 中明确选择附件上下文给出的图片资产 ID；只编辑被选择的图片。供应商不支持图片编辑时直接返回实际失败，禁止改用生成接口、run_command、Python、Pillow 或 OpenCV 静默替代。",
            action: "media.image.edit",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "针对所选图片的完整编辑要求"},
                    "input_asset_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "必填；要编辑的图片资产 ID，只能使用附件上下文中明确列出的资产 ID"
                    }
                },
                "required": ["prompt", "input_asset_ids"]
            }),
        },
        ToolDefinition {
            name: "generate_video",
            description: "调用统一的视频生成工具协议，由当前配置的供应商适配器连接视频模型创建视频。只有用户明确要求生成视频或动画时调用；用户上传的图片会自动作为参考素材传给该工具。视频编辑、重混或延长能力只有在对应工具和供应商适配器明确提供时才能调用，不得把视频编辑请求伪装成重新生成。",
            action: "media.video.generate",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "完整的视频生成提示词"}
                },
                "required": ["prompt"]
            }),
        },
        ToolDefinition {
            name: "generate_audio",
            description: "调用统一的文本转语音工具协议，由当前配置的供应商适配器连接语音模型把文本生成音频。只有用户明确要求朗读、配音或文字转语音时调用；该工具不代表所有音乐、音效或通用音频生成能力。",
            action: "media.audio.generate",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "要朗读或配音的完整文本"},
                    "voice": {"type": "string", "description": "可选音色 ID"},
                    "response_format": {"type": "string", "default": "wav"},
                    "speed": {"type": "number", "default": 1.0, "minimum": 0.25, "maximum": 4.0}
                },
                "required": ["prompt"]
            }),
        },
        ToolDefinition {
            name: "transcribe_audio",
            description: "调用统一的音频转写工具协议，由当前配置的供应商适配器连接转写模型把本轮上传的音频转成文字。音频内容由运行时自动注入，不要要求用户提供文件路径或 Base64；语言、说话人识别和翻译等扩展能力以供应商支持情况为准。",
            action: "media.audio.transcribe",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "可选的转写提示或语言说明"}
                }
            }),
        },
        ToolDefinition {
            name: "list_projects",
            description: "列出桌面本机全局项目目录中的项目，与项目页面同源，不依赖后端登录。用户询问“项目列表 / 有哪些项目 / 列出项目”时优先使用本工具；不要把 desktop-bot-global 当成真实项目。",
            action: "project.list",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "page": {"type": "number", "default": 1},
                    "page_size": {"type": "number", "default": 20},
                    "name": {"type": "string", "description": "按项目 ID、名称或说明关键词过滤，可选"}
                }
            }),
        },
        ToolDefinition {
            name: "get_project",
            description: "读取桌面本机全局项目目录中的项目详情，包含名称、描述和工作区状态。本机目录不保存项目绑定智能体；bound_agent_count 为 0 只表示目录没有这份数据。selected_employee_ids 为空仅表示自动分配。",
            action: "project.read",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"}
                },
                "required": ["project_id"]
            }),
        },
        ToolDefinition {
            name: "list_bot_projects",
            description: "仅飞书机器人会话可用。列出桌面本机全局项目目录中的项目和工作区，不读取桌面当前登录用户、后端 Token 或机器人连接器配置。返回项目 ID、名称、描述和工作区状态；选择项目后必须调用 switch_project_workspace，不能根据名称猜测或直接使用任意本机路径。",
            action: "bot.project.list",
            risk: "low",
            requires_approval: false,
            scope: "bot",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "page": {"type": "number", "default": 1},
                    "page_size": {"type": "number", "default": 50},
                    "name": {"type": "string", "description": "按项目 ID、名称或说明关键词过滤，可选"}
                }
            }),
        },
        ToolDefinition {
            name: "switch_project_workspace",
            description: "仅飞书机器人会话可用。按 project_id 从桌面本机全局项目目录中选择项目，并切换本轮及后续飞书会话使用的本机工作区。工具只接受项目 ID，不接受工作区路径；只有项目目录记录的绝对路径在本机可访问且是目录时才会成功。",
            action: "bot.workspace.switch",
            risk: "low",
            requires_approval: false,
            scope: "bot",
            input_schema: json!({
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"}
                },
                "required": ["project_id"]
            }),
        },
        ToolDefinition {
            name: "get_project_deploy_options",
            description: "读取当前项目本机部署配置摘要（脱敏），包含可选 profile、component、target、remote_path、artifact_kind、是否存在 deploy_command、notify_enabled。部署/发布/上线类任务必须先调用该工具，再让用户选择环境和目标；该工具只读，不上传、不部署、不返回服务器凭据。",
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
            description: "桌面智能体直连部署主工具。由桌面 AI 先调用 get_project_deploy_options 读取本机部署配置并让用户选择 profile/component/target 后，由桌面运行时直接把 workspace 内的原文件、目录或文件清单上传到目标 FTP 服务器。连接配置来自本机项目目录和全局 FTP 连接文件，不经过业务后端中转；本机运行时会跳过远端 deploy_command，而不是因为缺少后端执行器而阻塞。FTP 凭据不会进入模型上下文或工具结果。上传目录时按根层文件和文件夹生成任务，实际并发受 FTP 连接的最大上传线程数限制。只有本工具返回 deployment_confirmed_success=true/status=success 时，才允许回复部署成功。",
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
