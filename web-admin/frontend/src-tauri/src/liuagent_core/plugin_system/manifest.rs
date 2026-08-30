use std::collections::HashSet;

use serde::{Deserialize, Serialize};
use serde_json::Value;

const IDENTIFIER_MAX_LENGTH: usize = 128;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PluginType {
    Tool,
    Mcp,
    Skill,
    Rule,
    Agent,
    Connector,
    Workflow,
    Provider,
    Ui,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PluginSource {
    Builtin,
    System,
    Project,
    User,
    Mcp,
    Marketplace,
    Runtime,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityKind {
    Tool,
    Skill,
    Rule,
    Agent,
    Provider,
    Connector,
    Workflow,
    Ui,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RiskLevel {
    Low,
    Medium,
    High,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginManifest {
    pub id: String,
    pub plugin_type: PluginType,
    pub name: String,
    pub display_name: String,
    pub description: String,
    pub version: String,
    pub source: PluginSource,
    #[serde(default)]
    pub capabilities: Vec<CapabilityManifest>,
    #[serde(default)]
    pub dependencies: Vec<PluginDependency>,
    #[serde(default)]
    pub config_schema: Option<Value>,
    #[serde(default)]
    pub permissions: Option<PluginPermissions>,
    #[serde(default)]
    pub lifecycle: PluginLifecycleManifest,
    #[serde(default)]
    pub ui: Option<PluginUiManifest>,
    #[serde(default = "default_enabled")]
    pub enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CapabilityManifest {
    pub id: String,
    pub kind: CapabilityKind,
    pub name: String,
    pub description: String,
    #[serde(default)]
    pub selection: Option<CapabilitySelection>,
    #[serde(default)]
    pub input_schema: Option<Value>,
    #[serde(default)]
    pub output_schema: Option<Value>,
    #[serde(default)]
    pub metadata: Option<Value>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CapabilitySelection {
    #[serde(default)]
    pub when_to_use: Vec<String>,
    #[serde(default)]
    pub avoid_when: Vec<String>,
    #[serde(default)]
    pub requires: Vec<String>,
    #[serde(default)]
    pub recommends: Vec<String>,
    #[serde(default)]
    pub conflicts: Vec<String>,
    #[serde(default)]
    pub fallbacks: Vec<String>,
    #[serde(default)]
    pub priority: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginDependency {
    pub plugin_id: String,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub optional: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginPermissions {
    pub risk: RiskLevel,
    #[serde(default)]
    pub requires_approval: bool,
    pub scope: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginLifecycleManifest {
    #[serde(default)]
    pub supports_reload: bool,
    #[serde(default)]
    pub owns_processes: bool,
    #[serde(default)]
    pub owns_event_listeners: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginUiManifest {
    #[serde(default)]
    pub icon: Option<String>,
    #[serde(default)]
    pub settings_route: Option<String>,
    #[serde(default)]
    pub panel_route: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ManifestValidationError {
    EmptyId,
    InvalidId,
    IdTooLong,
    EmptyName,
    EmptyDescription,
    EmptyVersion,
    EmptyCapabilityId,
    DuplicateCapabilityId,
    EmptyDependencyId,
    SelfDependency,
}

impl std::fmt::Display for ManifestValidationError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::EmptyId => "plugin id is required",
            Self::InvalidId => "plugin id must use lowercase kebab-case segments",
            Self::IdTooLong => "plugin id is too long",
            Self::EmptyName => "plugin name is required",
            Self::EmptyDescription => "plugin description is required",
            Self::EmptyVersion => "plugin version is required",
            Self::EmptyCapabilityId => "capability id is required",
            Self::DuplicateCapabilityId => "capability ids must be unique within a plugin",
            Self::EmptyDependencyId => "dependency plugin id is required",
            Self::SelfDependency => "plugin cannot depend on itself",
        })
    }
}

impl std::error::Error for ManifestValidationError {}

impl PluginManifest {
    pub fn validate(&self) -> Result<(), ManifestValidationError> {
        let normalized_id = self.id.trim();
        if normalized_id.is_empty() {
            return Err(ManifestValidationError::EmptyId);
        }
        if normalized_id.len() > IDENTIFIER_MAX_LENGTH {
            return Err(ManifestValidationError::IdTooLong);
        }
        if !is_kebab_identifier(normalized_id) {
            return Err(ManifestValidationError::InvalidId);
        }
        if self.name.trim().is_empty() {
            return Err(ManifestValidationError::EmptyName);
        }
        if self.description.trim().is_empty() {
            return Err(ManifestValidationError::EmptyDescription);
        }
        if self.version.trim().is_empty() {
            return Err(ManifestValidationError::EmptyVersion);
        }

        let mut capability_ids = HashSet::new();
        for capability in &self.capabilities {
            if capability.id.trim().is_empty() {
                return Err(ManifestValidationError::EmptyCapabilityId);
            }
            if !capability_ids.insert(capability.id.trim()) {
                return Err(ManifestValidationError::DuplicateCapabilityId);
            }
        }
        for dependency in &self.dependencies {
            if dependency.plugin_id.trim().is_empty() {
                return Err(ManifestValidationError::EmptyDependencyId);
            }
            if dependency.plugin_id.trim() == normalized_id {
                return Err(ManifestValidationError::SelfDependency);
            }
        }
        Ok(())
    }
}

fn default_enabled() -> bool {
    true
}

fn is_kebab_identifier(value: &str) -> bool {
    value.split('.').all(|segment| {
        !segment.is_empty()
            && segment.split('-').all(|part| {
                !part.is_empty()
                    && part.chars().all(|character| {
                        character.is_ascii_lowercase() || character.is_ascii_digit()
                    })
            })
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manifest(id: &str) -> PluginManifest {
        PluginManifest {
            id: id.to_string(),
            plugin_type: PluginType::Tool,
            name: "test-tool".to_string(),
            display_name: "Test Tool".to_string(),
            description: "A test plugin".to_string(),
            version: "1.0.0".to_string(),
            source: PluginSource::Builtin,
            capabilities: Vec::new(),
            dependencies: Vec::new(),
            config_schema: None,
            permissions: None,
            lifecycle: PluginLifecycleManifest::default(),
            ui: None,
            enabled: true,
        }
    }

    #[test]
    fn accepts_scoped_kebab_identifier() {
        assert!(manifest("builtin-file-tools").validate().is_ok());
        assert!(manifest("builtin.file-tools").validate().is_ok());
    }

    #[test]
    fn rejects_invalid_identifier() {
        assert_eq!(
            manifest("Builtin_File_Tools").validate(),
            Err(ManifestValidationError::InvalidId)
        );
    }
}
