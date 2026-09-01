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
        description: "调用统一的视频工具协议。默认使用文字生成视频；用户要求基于已有视频修改、重混或延长时，必须设置 operation 并通过 input_asset_ids 选择一个视频资产。只有当前供应商明确支持对应操作时才能调用。",
        action: "media.video.generate",
        risk: "low",
        requires_approval: false,
        scope: "project",
        input_schema: json!({
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 1, "description": "完整的视频生成或编辑提示词"},
                "operation": {
                    "type": "string",
                    "enum": ["text_to_video", "image_to_video", "video_remix", "video_modify", "video_extend"],
                    "description": "视频操作类型，默认是 text_to_video"
                },
                "input_asset_ids": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "maxItems": 1,
                    "description": "视频二次生成时使用的视频资产 ID"
                }
            },
            "required": ["prompt"]
        }),
    }]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exposes_video_generation_without_activation_state() {
        let definitions = builtin_media_video_tool_definitions();
        assert_eq!(definitions.len(), 1);
        assert_eq!(definitions[0].name, "generate_video");
        assert_eq!(definitions[0].input_schema["required"], json!(["prompt"]));
        assert_eq!(
            definitions[0].input_schema["properties"]["operation"]["enum"],
            json!(["text_to_video", "image_to_video", "video_remix", "video_modify", "video_extend"])
        );
    }

    #[test]
    fn video_runtime_returns_structured_validation_errors() {
        let error = execute_builtin_media_video_tool(
            "generate_video",
            &json!({"_media_validation_error": "缺少视频输入"}),
        )
        .expect_err("validation errors must stop before provider execution");
        assert_eq!(error.code, "tool.schema_invalid");
    }
}
