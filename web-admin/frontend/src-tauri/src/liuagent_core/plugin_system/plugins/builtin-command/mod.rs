use serde_json::json;

use crate::liuagent_core::plugin_system::{PluginManifest, PluginRegistry, PluginRegistryError};
use crate::liuagent_core::ToolDefinition;

#[path = "process.rs"]
mod process;
#[path = "runtime.rs"]
mod runtime;

pub(crate) use process::configure_process_group;
pub use process::{process_tool, wait_for_background_process_notification};
pub use runtime::{
    check_command_risk, classify_command_risk, run_command, run_command_with_output_sink_and_cancel,
};

const PLUGIN_MANIFEST: &str = include_str!("plugin.json");

pub fn builtin_command_manifest() -> Result<PluginManifest, PluginRegistryError> {
    serde_json::from_str(PLUGIN_MANIFEST).map_err(|error| {
        PluginRegistryError::InvalidManifest(format!("builtin-command/plugin.json: {error}"))
    })
}

pub fn register_builtin_command(registry: &mut PluginRegistry) -> Result<(), PluginRegistryError> {
    registry.register(builtin_command_manifest()?)
}

pub fn builtin_command_tool_definitions() -> Vec<ToolDefinition> {
    vec![
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
    ]
}
