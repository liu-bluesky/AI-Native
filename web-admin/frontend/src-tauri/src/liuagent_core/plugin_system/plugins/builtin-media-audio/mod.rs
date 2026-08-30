use serde_json::json;

use crate::liuagent_core::plugin_system::{PluginManifest, PluginRegistry, PluginRegistryError};
use crate::liuagent_core::ToolDefinition;

#[path = "runtime.rs"]
mod runtime;

pub use runtime::execute_builtin_media_audio_tool;

const PLUGIN_MANIFEST: &str = include_str!("plugin.json");

pub fn builtin_media_audio_manifest() -> Result<PluginManifest, PluginRegistryError> {
    serde_json::from_str(PLUGIN_MANIFEST).map_err(|error| {
        PluginRegistryError::InvalidManifest(format!("builtin-media-audio/plugin.json: {error}"))
    })
}

pub fn register_builtin_media_audio(
    registry: &mut PluginRegistry,
) -> Result<(), PluginRegistryError> {
    registry.register(builtin_media_audio_manifest()?)
}

pub fn builtin_media_audio_tool_definitions() -> Vec<ToolDefinition> {
    vec![ToolDefinition {
        name: "generate_audio",
        description: "调用统一的文本转语音工具协议，把文本生成音频。只有用户明确要求朗读、配音或文字转语音时调用。",
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
    }]
}
