use crate::liuagent_core::plugin_system::{PluginManifest, PluginRegistry, PluginRegistryError};

const PLUGIN_MANIFEST: &str = include_str!("builtin-media-image/plugin.json");

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
}
