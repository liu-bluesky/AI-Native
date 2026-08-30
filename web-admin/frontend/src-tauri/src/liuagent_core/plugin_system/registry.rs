use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use super::lifecycle::{LifecycleState, PluginLifecycle};
use super::manifest::{CapabilityManifest, PluginManifest};

#[derive(Debug, Clone)]
pub struct PluginRecord {
    pub manifest: PluginManifest,
    pub lifecycle: PluginLifecycle,
    pub registration_order: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginRegistrySnapshot {
    pub plugins: Vec<PluginManifest>,
    pub capabilities: Vec<RegisteredCapabilitySnapshot>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RegisteredCapabilitySnapshot {
    pub id: String,
    pub plugin_id: String,
    pub capability: CapabilityManifest,
}

#[derive(Debug, Clone)]
struct RegisteredCapability {
    plugin_id: String,
    capability: CapabilityManifest,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PluginRegistryError {
    InvalidManifest(String),
    DuplicatePlugin(String),
    PluginNotFound(String),
    DuplicateCapability(String),
    InvalidLifecycle(String),
}

impl std::fmt::Display for PluginRegistryError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidManifest(message) => {
                write!(formatter, "invalid plugin manifest: {message}")
            }
            Self::DuplicatePlugin(id) => write!(formatter, "plugin already registered: {id}"),
            Self::PluginNotFound(id) => write!(formatter, "plugin not found: {id}"),
            Self::DuplicateCapability(id) => {
                write!(formatter, "capability already registered: {id}")
            }
            Self::InvalidLifecycle(message) => {
                write!(formatter, "invalid plugin lifecycle: {message}")
            }
        }
    }
}

impl std::error::Error for PluginRegistryError {}

#[derive(Debug, Default)]
pub struct PluginRegistry {
    plugins: BTreeMap<String, PluginRecord>,
    capabilities: BTreeMap<String, RegisteredCapability>,
    next_registration_order: u64,
}

impl PluginRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&mut self, manifest: PluginManifest) -> Result<(), PluginRegistryError> {
        manifest
            .validate()
            .map_err(|error| PluginRegistryError::InvalidManifest(error.to_string()))?;
        if self.plugins.contains_key(&manifest.id) {
            return Err(PluginRegistryError::DuplicatePlugin(manifest.id));
        }
        for capability in &manifest.capabilities {
            if self.capabilities.contains_key(&capability.id) {
                return Err(PluginRegistryError::DuplicateCapability(
                    capability.id.clone(),
                ));
            }
        }
        let plugin_id = manifest.id.clone();
        let capabilities = manifest.capabilities.clone();
        let record = PluginRecord {
            manifest,
            lifecycle: PluginLifecycle::discovered(),
            registration_order: self.next_registration_order,
        };
        self.next_registration_order = self.next_registration_order.saturating_add(1);
        self.plugins.insert(plugin_id.clone(), record);
        for capability in capabilities {
            self.capabilities.insert(
                capability.id.clone(),
                RegisteredCapability {
                    plugin_id: plugin_id.clone(),
                    capability,
                },
            );
        }
        Ok(())
    }

    pub fn unregister(&mut self, plugin_id: &str) -> Result<PluginManifest, PluginRegistryError> {
        let record = self
            .plugins
            .remove(plugin_id)
            .ok_or_else(|| PluginRegistryError::PluginNotFound(plugin_id.to_string()))?;
        self.capabilities
            .retain(|_, capability| capability.plugin_id != plugin_id);
        Ok(record.manifest)
    }

    pub fn get(&self, plugin_id: &str) -> Option<&PluginRecord> {
        self.plugins.get(plugin_id)
    }

    pub fn get_capability(&self, capability_id: &str) -> Option<(&str, &CapabilityManifest)> {
        self.capabilities
            .get(capability_id)
            .map(|capability| (capability.plugin_id.as_str(), &capability.capability))
    }

    pub fn list_plugins(&self) -> impl Iterator<Item = &PluginRecord> {
        self.plugins.values()
    }

    pub fn list_capabilities(&self) -> impl Iterator<Item = (&str, &str, &CapabilityManifest)> {
        self.capabilities.values().map(|capability| {
            (
                capability.capability.id.as_str(),
                capability.plugin_id.as_str(),
                &capability.capability,
            )
        })
    }

    pub fn transition(
        &mut self,
        plugin_id: &str,
        next: LifecycleState,
    ) -> Result<(), PluginRegistryError> {
        let record = self
            .plugins
            .get_mut(plugin_id)
            .ok_or_else(|| PluginRegistryError::PluginNotFound(plugin_id.to_string()))?;
        record
            .lifecycle
            .transition(next)
            .map(|_| ())
            .map_err(PluginRegistryError::InvalidLifecycle)
    }

    pub fn snapshot(&self) -> PluginRegistrySnapshot {
        PluginRegistrySnapshot {
            plugins: self
                .plugins
                .values()
                .map(|record| record.manifest.clone())
                .collect(),
            capabilities: self
                .capabilities
                .values()
                .map(|capability| RegisteredCapabilitySnapshot {
                    id: capability.capability.id.clone(),
                    plugin_id: capability.plugin_id.clone(),
                    capability: capability.capability.clone(),
                })
                .collect(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::liuagent_core::plugin_system::manifest::{
        CapabilityKind, CapabilitySelection, PluginSource, PluginType,
    };

    fn manifest(id: &str, capability_id: &str, priority: i32) -> PluginManifest {
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
            enabled: true,
        }
    }

    #[test]
    fn registers_capabilities_and_rejects_duplicates() {
        let mut registry = PluginRegistry::new();
        registry
            .register(manifest("builtin-one", "tool-one", 10))
            .unwrap();
        assert!(registry.get("builtin-one").is_some());
        assert!(registry.get_capability("tool-one").is_some());
        assert!(matches!(
            registry.register(manifest("builtin-two", "tool-one", 20)),
            Err(PluginRegistryError::DuplicateCapability(_))
        ));
    }

    #[test]
    fn transition_updates_plugin_lifecycle() {
        let mut registry = PluginRegistry::new();
        registry
            .register(manifest("builtin-one", "tool-one", 10))
            .unwrap();
        registry
            .transition("builtin-one", LifecycleState::Loaded)
            .unwrap();
        assert_eq!(
            registry.get("builtin-one").unwrap().lifecycle.state(),
            LifecycleState::Loaded
        );
    }
}
