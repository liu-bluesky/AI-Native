use super::manifest::{CapabilityKind, CapabilityManifest, PluginType};
use super::registry::PluginRegistry;

#[derive(Debug, Clone, Default)]
pub struct CapabilityQuery {
    pub capability_id: Option<String>,
    pub kind: Option<CapabilityKind>,
    pub plugin_type: Option<PluginType>,
    pub include_disabled: bool,
}

#[derive(Debug, Clone)]
pub struct CapabilityMatch<'a> {
    pub plugin_id: &'a str,
    pub capability: &'a CapabilityManifest,
    pub priority: i32,
}

#[derive(Debug, Default)]
pub struct CapabilityResolver;

impl CapabilityResolver {
    pub fn new() -> Self {
        Self
    }

    pub fn resolve<'a>(
        &self,
        registry: &'a PluginRegistry,
        query: &CapabilityQuery,
    ) -> Vec<CapabilityMatch<'a>> {
        let mut matches = registry
            .list_capabilities()
            .filter_map(|(_, plugin_id, capability)| {
                if let Some(capability_id) = query.capability_id.as_deref() {
                    if capability.id != capability_id {
                        return None;
                    }
                }
                if let Some(kind) = query.kind {
                    if capability.kind != kind {
                        return None;
                    }
                }
                let plugin = registry.get(plugin_id)?;
                if !query.include_disabled && !plugin.manifest.enabled {
                    return None;
                }
                if let Some(plugin_type) = query.plugin_type {
                    if plugin.manifest.plugin_type != plugin_type {
                        return None;
                    }
                }
                let priority = capability
                    .selection
                    .as_ref()
                    .map(|selection| selection.priority)
                    .unwrap_or_default();
                Some(CapabilityMatch {
                    plugin_id,
                    capability,
                    priority,
                })
            })
            .collect::<Vec<_>>();
        matches.sort_by(|left, right| {
            right
                .priority
                .cmp(&left.priority)
                .then_with(|| left.plugin_id.cmp(right.plugin_id))
                .then_with(|| left.capability.id.cmp(&right.capability.id))
        });
        matches
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::liuagent_core::plugin_system::manifest::{
        CapabilitySelection, PluginManifest, PluginSource,
    };

    fn manifest(id: &str, capability_id: &str, priority: i32, enabled: bool) -> PluginManifest {
        PluginManifest {
            id: id.to_string(),
            plugin_type: PluginType::Tool,
            name: id.to_string(),
            display_name: id.to_string(),
            description: "test plugin".to_string(),
            version: "1.0.0".to_string(),
            source: PluginSource::Builtin,
            capabilities: vec![CapabilityManifest {
                id: capability_id.to_string(),
                kind: CapabilityKind::Tool,
                name: capability_id.to_string(),
                description: "test capability".to_string(),
                selection: Some(CapabilitySelection {
                    priority,
                    ..CapabilitySelection::default()
                }),
                input_schema: None,
                output_schema: None,
                metadata: None,
            }],
            dependencies: Vec::new(),
            config_schema: None,
            permissions: None,
            lifecycle: Default::default(),
            ui: None,
            enabled,
        }
    }

    #[test]
    fn resolves_enabled_capabilities_by_priority() {
        let mut registry = PluginRegistry::new();
        registry
            .register(manifest("builtin-low", "tool-low", 10, true))
            .unwrap();
        registry
            .register(manifest("builtin-high", "tool-high", 90, true))
            .unwrap();
        registry
            .register(manifest("builtin-off", "tool-off", 100, false))
            .unwrap();
        let matches = CapabilityResolver::new().resolve(
            &registry,
            &CapabilityQuery {
                kind: Some(CapabilityKind::Tool),
                ..CapabilityQuery::default()
            },
        );
        assert_eq!(matches.len(), 2);
        assert_eq!(matches[0].capability.id, "tool-high");
        assert_eq!(matches[1].capability.id, "tool-low");
    }
}
