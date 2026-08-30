use serde_json::json;

use crate::liuagent_core::plugin_system::{PluginManifest, PluginRegistry, PluginRegistryError};
use crate::liuagent_core::ToolDefinition;

#[path = "runtime.rs"]
mod runtime;

pub use runtime::execute_builtin_media_transcription_tool;

const PLUGIN_MANIFEST: &str = include_str!("plugin.json");

pub fn builtin_media_transcription_manifest() -> Result<PluginManifest, PluginRegistryError> {
    serde_json::from_str(PLUGIN_MANIFEST).map_err(|error| {
        PluginRegistryError::InvalidManifest(format!(
            "builtin-media-transcription/plugin.json: {error}"
        ))
    })
}

pub fn register_builtin_media_transcription(
    registry: &mut PluginRegistry,
) -> Result<(), PluginRegistryError> {
    registry.register(builtin_media_transcription_manifest()?)
}

pub fn builtin_media_transcription_tool_definitions() -> Vec<ToolDefinition> {
    vec![ToolDefinition {
        name: "transcribe_audio",
        description:
            "调用统一的音频转写工具协议，把本轮上传的音频转成文字；音频内容由运行时自动注入。",
        action: "media.audio.transcribe",
        risk: "low",
        requires_approval: false,
        scope: "project",
        input_schema: json!({
            "type": "object",
            "properties": {"prompt": {"type": "string", "description": "可选的转写提示或语言说明"}}
        }),
    }]
}
