use serde_json::{json, Map, Value};

use crate::liuagent_core::args::{bool_arg, required_string_arg};
use crate::liuagent_core::paths::desktop_plugin_root;
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::plugin_system::{PluginInstallError, PluginInstaller};
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};

pub fn list_installed_plugins(_arguments: &Value) -> Result<(Value, String), ToolError> {
    let root = plugin_root()?;
    let records = PluginInstaller::list_installed(&root).map_err(install_error)?;
    let plugins = records
        .iter()
        .map(|record| {
            json!({
                "id": record.manifest.id,
                "version": record.manifest.version,
                "name": record.manifest.display_name,
                "description": record.manifest.description,
                "enabled": record.enabled,
                "configured": record.configured,
                "path": record.path
            })
        })
        .collect::<Vec<_>>();
    Ok((
        json!({"pluginRoot": root, "plugins": plugins}),
        format!("已发现 {} 个已安装插件版本", plugins.len()),
    ))
}

pub fn install_plugin_from_directory(
    tool_call_id: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let source_directory = required_string_arg(arguments, "source_directory")?;
    let source_path = std::path::PathBuf::from(&source_directory);
    require_approval(
        tool_call_id,
        "plugin.install",
        "high",
        "user",
        &format!("从本机目录安装插件：{source_directory}"),
        json!({"source_directory": source_directory}),
        permission_decision,
    )?;
    let root = plugin_root()?;
    let installed = PluginInstaller::install_directory(&source_path, &root, "local-directory")
        .map_err(install_error)?;
    Ok((
        json!({
            "installed": true,
            "pluginId": installed.manifest.id,
            "pluginVersion": installed.manifest.version,
            "path": installed.path,
            "nextStep": "插件 Skill 将在下一轮 Runtime 请求中自动发现"
        }),
        format!(
            "已安装插件 {}@{}",
            installed.manifest.id, installed.manifest.version
        ),
    ))
}

pub fn enable_plugin(
    tool_call_id: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    set_plugin_enabled(tool_call_id, arguments, permission_decision, true)
}

pub fn disable_plugin(
    tool_call_id: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    set_plugin_enabled(tool_call_id, arguments, permission_decision, false)
}

fn set_plugin_enabled(
    tool_call_id: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
    enabled: bool,
) -> Result<(Value, String), ToolError> {
    let plugin_id = required_string_arg(arguments, "plugin_id")?;
    let plugin_version = required_string_arg(arguments, "plugin_version")?;
    require_approval(
        tool_call_id,
        if enabled {
            "plugin.lifecycle.enable"
        } else {
            "plugin.lifecycle.disable"
        },
        "medium",
        "user",
        &format!(
            "{}插件 {}@{}",
            if enabled { "启用" } else { "禁用" },
            plugin_id,
            plugin_version
        ),
        json!({"plugin_id": plugin_id, "plugin_version": plugin_version, "enabled": enabled}),
        permission_decision,
    )?;
    let root = plugin_root()?;
    let record = PluginInstaller::set_enabled(&root, &plugin_id, &plugin_version, enabled)
        .map_err(install_error)?;
    Ok((
        json!({
            "pluginId": record.manifest.id,
            "pluginVersion": record.manifest.version,
            "enabled": record.enabled,
            "configured": record.configured
        }),
        format!(
            "{}插件 {}@{}",
            if enabled { "已启用" } else { "已禁用" },
            record.manifest.id,
            record.manifest.version
        ),
    ))
}

pub fn read_plugin_config(arguments: &Value) -> Result<(Value, String), ToolError> {
    let plugin_id = required_string_arg(arguments, "plugin_id")?;
    let plugin_version = required_string_arg(arguments, "plugin_version")?;
    let root = plugin_root()?;
    let config =
        PluginInstaller::read_config(&root, &plugin_id, &plugin_version).map_err(install_error)?;
    let configured = config.is_some();
    Ok((
        json!({
            "pluginId": plugin_id,
            "pluginVersion": plugin_version,
            "configured": configured,
            "config": config.map(redact_sensitive_values).unwrap_or(Value::Null)
        }),
        format!(
            "{}@{} 配置{}",
            plugin_id,
            plugin_version,
            if configured {
                "已存在（敏感值已脱敏）"
            } else {
                "不存在"
            }
        ),
    ))
}

pub fn configure_plugin(
    tool_call_id: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let plugin_id = required_string_arg(arguments, "plugin_id")?;
    let plugin_version = required_string_arg(arguments, "plugin_version")?;
    let patch = arguments
        .get("config")
        .filter(|value| value.is_object())
        .ok_or_else(|| ToolError::new("tool.schema_invalid", "config must be a JSON object"))?;
    let replace = bool_arg(arguments, "replace", false);
    let root = plugin_root()?;
    let current = PluginInstaller::read_config(&root, &plugin_id, &plugin_version)
        .map_err(install_error)?
        .unwrap_or_else(|| json!({}));
    let next = if replace {
        patch.clone()
    } else {
        merge_config(current, patch)
    };
    let keys = next
        .as_object()
        .map(|object| object.keys().cloned().collect::<Vec<_>>())
        .unwrap_or_default();
    require_approval(
        tool_call_id,
        "plugin.configuration.write",
        "high",
        "user",
        &format!("写入插件配置：{plugin_id}@{plugin_version}"),
        json!({"plugin_id": plugin_id, "plugin_version": plugin_version, "replace": replace, "keys": keys}),
        permission_decision,
    )?;
    PluginInstaller::write_config(&root, &plugin_id, &plugin_version, &next)
        .map_err(install_error)?;
    Ok((
        json!({
            "configured": true,
            "pluginId": plugin_id,
            "pluginVersion": plugin_version,
            "replace": replace,
            "keys": keys
        }),
        format!("已写入插件 {}@{} 配置", plugin_id, plugin_version),
    ))
}

fn plugin_root() -> Result<std::path::PathBuf, ToolError> {
    desktop_plugin_root()
        .map_err(|error| ToolError::new("plugin.root_unavailable", error.to_string()))
}

fn install_error(error: PluginInstallError) -> ToolError {
    ToolError::new("plugin.management_failed", error.to_string())
}

fn merge_config(current: Value, patch: &Value) -> Value {
    let mut current = current.as_object().cloned().unwrap_or_default();
    if let Some(patch) = patch.as_object() {
        merge_config_objects(&mut current, patch);
    }
    Value::Object(current)
}

fn merge_config_objects(target: &mut Map<String, Value>, patch: &Map<String, Value>) {
    for (key, value) in patch {
        match (target.get_mut(key), value) {
            (Some(Value::Object(target)), Value::Object(patch)) => {
                merge_config_objects(target, patch);
            }
            _ => {
                target.insert(key.clone(), value.clone());
            }
        }
    }
}

fn redact_sensitive_values(value: Value) -> Value {
    match value {
        Value::Object(object) => Value::Object(
            object
                .into_iter()
                .map(|(key, value)| {
                    if is_sensitive_key(&key) {
                        (key, Value::String("[redacted]".to_string()))
                    } else {
                        (key, redact_sensitive_values(value))
                    }
                })
                .collect(),
        ),
        Value::Array(values) => {
            Value::Array(values.into_iter().map(redact_sensitive_values).collect())
        }
        other => other,
    }
}

fn is_sensitive_key(key: &str) -> bool {
    let key = key.to_ascii_lowercase();
    [
        "api_key",
        "apikey",
        "token",
        "password",
        "secret",
        "private_key",
    ]
    .iter()
    .any(|marker| key.contains(marker))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn merges_nested_configuration_without_dropping_existing_fields() {
        let merged = merge_config(
            json!({"provider":{"url":"https://example.test","timeout":30},"enabled":true}),
            &json!({"provider":{"timeout":60}}),
        );
        assert_eq!(merged["provider"]["url"], "https://example.test");
        assert_eq!(merged["provider"]["timeout"], 60);
        assert_eq!(merged["enabled"], true);
    }

    #[test]
    fn redacts_sensitive_configuration_recursively() {
        let redacted = redact_sensitive_values(json!({
            "apiKey":"secret",
            "nested":{"access_token":"secret-2","region":"us"}
        }));
        assert_eq!(redacted["apiKey"], "[redacted]");
        assert_eq!(redacted["nested"]["access_token"], "[redacted]");
        assert_eq!(redacted["nested"]["region"], "us");
    }
}
