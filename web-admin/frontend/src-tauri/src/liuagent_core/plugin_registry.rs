//! liuAgent 的内置插件目录。
//!
//! 核心工具始终可用；业务能力以插件分组，并通过请求里的
//! `mcpConfig.enabledPlugins` 按会话注入。未声明插件列表时保持兼容，
//! 默认启用所有已安装的内置插件。

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const PROJECT_MANAGEMENT_PLUGIN: &str = "project-management";
pub const DEPLOYMENT_PLUGIN: &str = "deployment";
pub const MEDIA_PLUGIN: &str = "media";
pub const PLUGIN_MANIFEST_FILE: &str = "plugin.json";
const BUILTIN_SKILLS: &[(&str, &str)] = &[
    (
        "plugin-manager",
        include_str!("../../builtin-skills/plugin-manager/SKILL.md"),
    ),
    (
        "plugin-configurator",
        include_str!("../../builtin-skills/plugin-configurator/SKILL.md"),
    ),
];

#[derive(Debug, Clone, Copy)]
pub struct BuiltinPluginDefinition {
    pub id: &'static str,
    pub label: &'static str,
    pub description: &'static str,
    pub tools: &'static [&'static str],
}

const BUILTIN_PLUGINS: &[BuiltinPluginDefinition] = &[
    BuiltinPluginDefinition {
        id: PROJECT_MANAGEMENT_PLUGIN,
        label: "项目管理",
        description: "列出项目、读取项目详情并切换项目工作区。",
        tools: &[
            "list_projects",
            "get_project",
            "list_bot_projects",
            "switch_project_workspace",
        ],
    },
    BuiltinPluginDefinition {
        id: DEPLOYMENT_PLUGIN,
        label: "部署发布",
        description: "读取部署目标并把工作区文件发布到配置的目标。",
        tools: &[
            "get_project_deploy_options",
            "deploy_workspace_files_to_target",
        ],
    },
    BuiltinPluginDefinition {
        id: MEDIA_PLUGIN,
        label: "媒体生成",
        description: "按用户需求生成或编辑图片、视频、音频并进行音频转写。",
        tools: &[
            "generate_image",
            "edit_image",
            "generate_video",
            "generate_audio",
            "transcribe_audio",
        ],
    },
];

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginComponentDescriptor {
    pub id: String,
    pub kind: String,
    pub name: String,
    pub entry: Option<String>,
    pub config: Option<Value>,
    pub enabled: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalPluginDescriptor {
    pub id: String,
    pub name: String,
    pub version: String,
    pub schema_version: u32,
    pub description: String,
    pub plugin_type: String,
    pub source: String,
    pub root_path: String,
    pub manifest_path: String,
    pub enabled: bool,
    pub components: Vec<PluginComponentDescriptor>,
    pub content: Option<Value>,
    pub interface: Option<Value>,
    pub runtime: Option<Value>,
    pub permissions: Option<Value>,
    pub tools: Vec<String>,
    pub error: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ExternalPluginManifest {
    id: String,
    #[serde(default, alias = "label")]
    name: String,
    #[serde(default)]
    version: String,
    #[serde(default = "default_schema_version", alias = "schema_version")]
    schema_version: u32,
    #[serde(default)]
    description: String,
    #[serde(default = "default_plugin_type", alias = "pluginType")]
    plugin_type: String,
    #[serde(default = "default_enabled")]
    enabled: bool,
    #[serde(default)]
    components: Vec<ExternalPluginComponent>,
    #[serde(default)]
    content: Option<Value>,
    #[serde(default)]
    interface: Option<Value>,
    #[serde(default)]
    runtime: Option<Value>,
    #[serde(default)]
    permissions: Option<Value>,
    #[serde(default)]
    tools: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ExternalPluginComponent {
    #[serde(default)]
    id: String,
    #[serde(default = "default_component_kind", alias = "type")]
    kind: String,
    #[serde(default)]
    name: String,
    #[serde(default)]
    entry: Option<String>,
    #[serde(default)]
    config: Option<Value>,
    #[serde(default = "default_enabled")]
    enabled: bool,
}

fn default_schema_version() -> u32 {
    1
}

fn default_component_kind() -> String {
    "mcp".to_string()
}

fn default_plugin_type() -> String {
    "mcp".to_string()
}

fn default_enabled() -> bool {
    true
}

pub fn discover_local_plugins(
    workspace_path: &str,
    user_home: Option<&Path>,
) -> Result<Vec<LocalPluginDescriptor>, String> {
    let mut roots = Vec::new();
    if let Some(home) = user_home {
        roots.push(("user", home.join(".ai-employee").join("plugins")));
    }
    let workspace = workspace_path.trim();
    if !workspace.is_empty() {
        roots.push((
            "project",
            PathBuf::from(workspace)
                .join(".ai-employee")
                .join("plugins"),
        ));
    }

    let mut plugins = HashMap::<String, LocalPluginDescriptor>::new();
    for (source, root) in roots {
        let Ok(entries) = fs::read_dir(&root) else {
            continue;
        };
        for entry in entries.flatten() {
            let plugin_root = entry.path();
            let Ok(metadata) = fs::symlink_metadata(&plugin_root) else {
                continue;
            };
            if !metadata.is_dir() || metadata.file_type().is_symlink() {
                continue;
            }
            let manifest_path = plugin_root.join(PLUGIN_MANIFEST_FILE);
            if !manifest_path.is_file() {
                continue;
            }
            let descriptor = read_plugin_manifest(source, &plugin_root, &manifest_path);
            let key = descriptor.id.to_ascii_lowercase();
            if !key.is_empty() {
                plugins.insert(key, descriptor);
            }
        }
    }
    let mut result: Vec<_> = plugins.into_values().collect();
    result.sort_by_key(|plugin| (plugin.source.clone(), plugin.name.to_ascii_lowercase()));
    Ok(result)
}

pub fn ensure_builtin_skills(workspace_path: &str) -> Result<Vec<String>, String> {
    let workspace = workspace_path.trim();
    if workspace.is_empty() {
        return Ok(Vec::new());
    }
    let skills_root = PathBuf::from(workspace).join(".ai-employee").join("skills");
    if skills_root.exists() {
        let metadata = fs::symlink_metadata(&skills_root).map_err(|error| error.to_string())?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(format!(
                "内置 Skill 目录不是安全的普通目录：{}",
                skills_root.display()
            ));
        }
    } else {
        fs::create_dir_all(&skills_root).map_err(|error| error.to_string())?;
    }
    let mut paths = Vec::new();
    for (skill_id, content) in BUILTIN_SKILLS {
        let skill_root = skills_root.join(skill_id);
        if skill_root.exists() {
            let metadata = fs::symlink_metadata(&skill_root).map_err(|error| error.to_string())?;
            if metadata.file_type().is_symlink() || !metadata.is_dir() {
                return Err(format!(
                    "Skill 目录不是安全的普通目录：{}",
                    skill_root.display()
                ));
            }
        } else {
            fs::create_dir_all(&skill_root).map_err(|error| error.to_string())?;
        }
        let target = skill_root.join("SKILL.md");
        if !target.exists() {
            fs::write(&target, content).map_err(|error| error.to_string())?;
        }
        paths.push(target.to_string_lossy().to_string());
    }
    Ok(paths)
}

fn read_plugin_manifest(source: &str, root: &Path, manifest_path: &Path) -> LocalPluginDescriptor {
    let base = LocalPluginDescriptor {
        id: String::new(),
        name: root
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("未命名插件")
            .to_string(),
        version: String::new(),
        schema_version: 1,
        description: String::new(),
        plugin_type: "mcp".to_string(),
        source: source.to_string(),
        root_path: root.to_string_lossy().to_string(),
        manifest_path: manifest_path.to_string_lossy().to_string(),
        enabled: false,
        components: Vec::new(),
        content: None,
        interface: None,
        runtime: None,
        permissions: None,
        tools: Vec::new(),
        error: String::new(),
    };
    let content = match fs::read_to_string(manifest_path) {
        Ok(content) => content,
        Err(error) => {
            return LocalPluginDescriptor {
                error: format!("读取清单失败：{error}"),
                ..base
            }
        }
    };
    let manifest: ExternalPluginManifest = match serde_json::from_str(&content) {
        Ok(manifest) => manifest,
        Err(error) => {
            return LocalPluginDescriptor {
                error: format!("清单 JSON 无效：{error}"),
                ..base
            }
        }
    };
    let id = manifest.id.trim().to_string();
    if id.is_empty() {
        return LocalPluginDescriptor {
            error: "插件 id 不能为空".to_string(),
            ..base
        };
    }
    let plugin_type = manifest.plugin_type.trim().to_ascii_lowercase();
    if !matches!(plugin_type.as_str(), "mcp" | "runtime" | "bundle") {
        return LocalPluginDescriptor {
            id,
            error: "插件 type 只能是 mcp、runtime 或 bundle".to_string(),
            ..base
        };
    }
    let components: Vec<PluginComponentDescriptor> = manifest
        .components
        .into_iter()
        .enumerate()
        .map(|(index, component)| PluginComponentDescriptor {
            id: if component.id.trim().is_empty() {
                format!("{id}.component-{}", index + 1)
            } else {
                component.id.trim().to_string()
            },
            kind: component.kind.trim().to_ascii_lowercase(),
            name: component.name.trim().to_string(),
            entry: component
                .entry
                .map(|entry| entry.trim().to_string())
                .filter(|entry| !entry.is_empty()),
            config: component.config.filter(Value::is_object),
            enabled: component.enabled,
        })
        .filter(|component| !component.kind.is_empty())
        .collect();
    let enabled = manifest.enabled && !components.is_empty();
    LocalPluginDescriptor {
        id,
        name: if manifest.name.trim().is_empty() {
            base.name
        } else {
            manifest.name.trim().to_string()
        },
        version: manifest.version.trim().to_string(),
        schema_version: manifest.schema_version,
        description: manifest.description.trim().to_string(),
        plugin_type,
        source: source.to_string(),
        root_path: root.to_string_lossy().to_string(),
        manifest_path: manifest_path.to_string_lossy().to_string(),
        enabled,
        components,
        content: manifest.content,
        interface: manifest.interface,
        runtime: manifest.runtime,
        permissions: manifest.permissions,
        tools: manifest
            .tools
            .into_iter()
            .map(|tool| tool.trim().to_string())
            .filter(|tool| !tool.is_empty())
            .collect(),
        error: String::new(),
    }
}

pub fn builtin_plugins() -> &'static [BuiltinPluginDefinition] {
    BUILTIN_PLUGINS
}

pub fn plugin_id_for_tool(tool_name: &str) -> Option<&'static str> {
    let normalized = tool_name.trim();
    BUILTIN_PLUGINS
        .iter()
        .find(|plugin| plugin.tools.contains(&normalized))
        .map(|plugin| plugin.id)
}

pub fn enabled_plugin_ids(mcp_config: &Value) -> Option<HashSet<String>> {
    let value = mcp_config
        .get("enabledPlugins")
        .or_else(|| mcp_config.get("enabled_plugins"))?;
    let values = value.as_array()?;
    Some(
        values
            .iter()
            .filter_map(Value::as_str)
            .map(|item| item.trim().to_ascii_lowercase())
            .filter(|item| !item.is_empty())
            .collect(),
    )
}

pub fn is_plugin_enabled(plugin_id: &str, mcp_config: &Value) -> bool {
    enabled_plugin_ids(mcp_config)
        .map(|enabled| enabled.contains(&plugin_id.trim().to_ascii_lowercase()))
        .unwrap_or(true)
}

pub fn tool_enabled(tool_name: &str, mcp_config: &Value) -> bool {
    plugin_id_for_tool(tool_name)
        .map(|plugin_id| is_plugin_enabled(plugin_id, mcp_config))
        .unwrap_or(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn keeps_core_tools_outside_optional_plugins() {
        assert_eq!(plugin_id_for_tool("read_file"), None);
    }

    #[test]
    fn filters_disabled_plugin_tools() {
        let config = json!({"enabledPlugins": ["media"]});
        assert!(!tool_enabled("get_project", &config));
        assert!(tool_enabled("generate_image", &config));
        assert!(tool_enabled("read_file", &config));
    }

    #[test]
    fn preserves_legacy_requests_without_plugin_list() {
        assert!(tool_enabled("deploy_workspace_files_to_target", &json!({})));
    }

    #[test]
    fn discovers_composable_plugin_components() {
        let root = std::env::temp_dir().join(format!(
            "ai-employee-plugin-registry-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("system clock should be after unix epoch")
                .as_nanos()
        ));
        let plugin_root = root.join(".ai-employee/plugins/company-tools");
        fs::create_dir_all(&plugin_root).expect("plugin directory should be created");
        fs::write(
            plugin_root.join(PLUGIN_MANIFEST_FILE),
            r#"{
                "schemaVersion": 1,
                "id": "company-tools",
                "name": "公司工具",
                "type": "runtime",
                "components": [
                    {
                        "id": "search",
                        "kind": "mcp",
                        "config": {"type": "stdio", "command": "node"}
                    },
                    {
                        "id": "search-skill",
                        "kind": "skill",
                        "entry": "./skills/search.md"
                    }
                ]
            }"#,
        )
        .expect("manifest should be written");

        let plugins =
            discover_local_plugins(root.to_str().expect("temp path should be utf-8"), None)
                .expect("plugin discovery should succeed");
        assert_eq!(plugins.len(), 1);
        assert_eq!(plugins[0].components.len(), 2);
        assert_eq!(plugins[0].components[0].kind, "mcp");
        assert_eq!(plugins[0].components[1].kind, "skill");
        assert_eq!(
            plugins[0].components[0]
                .config
                .as_ref()
                .and_then(|config| config.get("command")),
            Some(&json!("node"))
        );

        fs::remove_dir_all(root).expect("temporary plugin directory should be removed");
    }
}
