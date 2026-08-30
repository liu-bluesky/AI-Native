use serde_json::json;

use crate::liuagent_core::plugin_system::{PluginManifest, PluginRegistry, PluginRegistryError};
use crate::liuagent_core::ToolDefinition;

#[path = "runtime.rs"]
mod runtime;

pub use runtime::execute_builtin_media_video_tool;

const PLUGIN_MANIFEST: &str = include_str!("plugin.json");

pub fn builtin_media_video_manifest() -> Result<PluginManifest, PluginRegistryError> {
    serde_json::from_str(PLUGIN_MANIFEST).map_err(|error| {
        PluginRegistryError::InvalidManifest(format!("builtin-media-video/plugin.json: {error}"))
    })
}

pub fn register_builtin_media_video(
    registry: &mut PluginRegistry,
) -> Result<(), PluginRegistryError> {
    registry.register(builtin_media_video_manifest()?)
}

pub fn builtin_media_video_tool_definitions() -> Vec<ToolDefinition> {
    vec![ToolDefinition {
        name: "generate_video",
        description: "调用统一的视频生成工具协议，由当前配置的供应商适配器连接视频模型创建视频。只有用户明确要求生成视频或动画时调用。",
        action: "media.video.generate",
        risk: "low",
        requires_approval: false,
        scope: "project",
        input_schema: json!({
            "type": "object",
            "properties": {"prompt": {"type": "string", "description": "完整的视频生成提示词"}},
            "required": ["prompt"]
        }),
    }]
}
