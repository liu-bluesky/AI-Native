use serde_json::Value;

use crate::liuagent_core::plugin_system::adapters::media::execute_media_tool;
use crate::liuagent_core::types::ToolError;

pub fn execute_builtin_media_video_tool(
    tool_name: &str,
    arguments: &Value,
) -> Result<(Value, String), ToolError> {
    execute_media_tool(tool_name, arguments)
}
