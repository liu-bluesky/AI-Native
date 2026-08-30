use serde_json::Value;

use crate::liuagent_core::plugin_system::{PluginManifest, PluginRegistry, PluginRegistryError};
use crate::liuagent_core::ToolDefinition;

#[path = "builtin-media-image/runtime.rs"]
mod runtime;

pub use runtime::execute_builtin_media_image_tool;

const PLUGIN_MANIFEST: &str = include_str!("builtin-media-image/plugin.json");
const GENERATE_IMAGE_INPUT_SCHEMA: &str =
    include_str!("builtin-media-image/schemas/generate-image-input.json");
const EDIT_IMAGE_INPUT_SCHEMA: &str =
    include_str!("builtin-media-image/schemas/edit-image-input.json");

pub fn builtin_media_image_manifest() -> Result<PluginManifest, PluginRegistryError> {
    let manifest: PluginManifest = serde_json::from_str(PLUGIN_MANIFEST).map_err(|error| {
        PluginRegistryError::InvalidManifest(format!("builtin-media-image/plugin.json: {error}"))
    })?;
    Ok(manifest)
}

pub fn register_builtin_media_image(
    registry: &mut PluginRegistry,
) -> Result<(), PluginRegistryError> {
    registry.register(builtin_media_image_manifest()?)
}

pub fn builtin_media_image_tool_definitions() -> Vec<ToolDefinition> {
    vec![
        ToolDefinition {
            name: "generate_image",
            description: "调用图片插件的生成能力创建新图片；基于现有图片的修改必须使用 edit_image。供应商不支持该能力时必须如实返回失败。",
            action: "media.image.generate",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: schema(GENERATE_IMAGE_INPUT_SCHEMA),
        },
        ToolDefinition {
            name: "edit_image",
            description: "调用图片插件的编辑能力修改用户明确选择的图片；必须提供附件上下文中的 input_asset_ids，供应商不支持编辑时必须如实返回失败。",
            action: "media.image.edit",
            risk: "low",
            requires_approval: false,
            scope: "project",
            input_schema: schema(EDIT_IMAGE_INPUT_SCHEMA),
        },
    ]
}

fn schema(content: &str) -> Value {
    serde_json::from_str(content).expect("builtin image plugin schema must be valid JSON")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::liuagent_core::plugin_system::{
        CapabilityKind, CapabilityQuery, CapabilityResolver,
    };

    #[test]
    fn loads_image_plugin_manifest_from_plugin_package() {
        let manifest = builtin_media_image_manifest().unwrap();

        assert_eq!(manifest.id, "builtin-media-image");
        assert_eq!(manifest.capabilities.len(), 4);
        assert!(manifest.capabilities.iter().any(|capability| capability
            .metadata
            .as_ref()
            .is_some_and(|metadata| {
                metadata["skillFile"] == "skills/image-generation/SKILL.md"
            })));
    }

    #[test]
    fn resolves_image_tools_before_other_capabilities_by_query() {
        let mut registry = PluginRegistry::new();
        register_builtin_media_image(&mut registry).unwrap();
        let matches = CapabilityResolver::new().resolve(
            &registry,
            &CapabilityQuery {
                kind: Some(CapabilityKind::Tool),
                ..CapabilityQuery::default()
            },
        );

        assert_eq!(matches.len(), 2);
        assert_eq!(matches[0].capability.name, "edit_image");
        assert_eq!(matches[1].capability.name, "generate_image");
    }

    #[test]
    fn exposes_tool_definitions_from_the_image_plugin() {
        let definitions = builtin_media_image_tool_definitions();

        assert_eq!(definitions.len(), 2);
        assert_eq!(definitions[0].name, "generate_image");
        assert_eq!(definitions[1].name, "edit_image");
        assert_eq!(
            definitions[1].input_schema["required"][1],
            "input_asset_ids"
        );
    }
}
