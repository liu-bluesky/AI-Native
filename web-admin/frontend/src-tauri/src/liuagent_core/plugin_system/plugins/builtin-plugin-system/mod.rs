use serde_json::json;

use crate::liuagent_core::plugin_system::{PluginManifest, PluginRegistry, PluginRegistryError};
use crate::liuagent_core::ToolDefinition;

#[path = "runtime.rs"]
mod runtime;

pub use runtime::{
    configure_plugin, disable_plugin, enable_plugin, install_plugin_from_directory,
    list_installed_plugins, read_plugin_config,
};

const PLUGIN_MANIFEST: &str = include_str!("plugin.json");

pub fn builtin_plugin_system_manifest() -> Result<PluginManifest, PluginRegistryError> {
    serde_json::from_str(PLUGIN_MANIFEST).map_err(|error| {
        PluginRegistryError::InvalidManifest(format!("builtin-plugin-system/plugin.json: {error}"))
    })
}

pub fn register_builtin_plugin_system(
    registry: &mut PluginRegistry,
) -> Result<(), PluginRegistryError> {
    registry.register(builtin_plugin_system_manifest()?)
}

pub fn builtin_plugin_system_tool_definitions() -> Vec<ToolDefinition> {
    vec![
        ToolDefinition {
            name: "list_installed_plugins",
            description: "列出本机已安装的插件、版本、启用状态和配置状态。用于插件管理前的事实检查。",
            action: "plugin.discovery.list",
            risk: "low",
            requires_approval: false,
            scope: "user",
            input_schema: json!({"type":"object","properties":{}}),
        },
        ToolDefinition {
            name: "install_plugin_from_directory",
            description: "从用户本机已有的插件目录安装一个版本化插件。只接受包含 plugin.json 的本地目录；安装前必须经过用户授权。",
            action: "plugin.install",
            risk: "high",
            requires_approval: true,
            scope: "user",
            input_schema: json!({
                "type":"object",
                "properties":{"source_directory":{"type":"string","description":"本机插件目录绝对路径或可访问路径"}},
                "required":["source_directory"]
            }),
        },
        ToolDefinition {
            name: "enable_plugin",
            description: "启用已安装插件的指定版本。启用状态写入 plugin-lock.json，并在后续 Runtime 请求中生效。",
            action: "plugin.lifecycle.enable",
            risk: "medium",
            requires_approval: true,
            scope: "user",
            input_schema: json!({
                "type":"object",
                "properties":{"plugin_id":{"type":"string"},"plugin_version":{"type":"string"}},
                "required":["plugin_id","plugin_version"]
            }),
        },
        ToolDefinition {
            name: "disable_plugin",
            description: "禁用已安装插件的指定版本。禁用状态写入 plugin-lock.json，并阻止后续 Skill 被 Runtime 发现。",
            action: "plugin.lifecycle.disable",
            risk: "medium",
            requires_approval: true,
            scope: "user",
            input_schema: json!({
                "type":"object",
                "properties":{"plugin_id":{"type":"string"},"plugin_version":{"type":"string"}},
                "required":["plugin_id","plugin_version"]
            }),
        },
        ToolDefinition {
            name: "read_plugin_config",
            description: "读取已安装插件的配置状态和脱敏配置，用于判断还缺少哪些配置；不会返回密钥原文。",
            action: "plugin.configuration.read",
            risk: "low",
            requires_approval: false,
            scope: "user",
            input_schema: json!({
                "type":"object",
                "properties":{"plugin_id":{"type":"string"},"plugin_version":{"type":"string"}},
                "required":["plugin_id","plugin_version"]
            }),
        },
        ToolDefinition {
            name: "configure_plugin",
            description: "写入已安装插件的 JSON 配置。默认按对象字段合并，不会覆盖未提供的字段；写入前必须经过用户授权。",
            action: "plugin.configuration.write",
            risk: "high",
            requires_approval: true,
            scope: "user",
            input_schema: json!({
                "type":"object",
                "properties":{
                    "plugin_id":{"type":"string"},
                    "plugin_version":{"type":"string"},
                    "config":{"type":"object"},
                    "replace":{"type":"boolean","default":false,"description":"为 true 时完整替换配置；否则按对象字段合并"}
                },
                "required":["plugin_id","plugin_version","config"]
            }),
        },
    ]
}
