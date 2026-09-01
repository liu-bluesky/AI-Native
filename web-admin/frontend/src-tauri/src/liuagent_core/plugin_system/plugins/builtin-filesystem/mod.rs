use serde_json::json;

use crate::liuagent_core::plugin_system::{PluginManifest, PluginRegistry, PluginRegistryError};
use crate::liuagent_core::ToolDefinition;

#[path = "runtime.rs"]
mod runtime;

pub use runtime::{
    apply_patch, delete_file, list_files, list_local_resources, read_file, read_local_resource,
    search_text, write_file,
};

const PLUGIN_MANIFEST: &str = include_str!("plugin.json");

pub fn builtin_filesystem_manifest() -> Result<PluginManifest, PluginRegistryError> {
    serde_json::from_str(PLUGIN_MANIFEST).map_err(|error| {
        PluginRegistryError::InvalidManifest(format!("builtin-filesystem/plugin.json: {error}"))
    })
}

pub fn register_builtin_filesystem(
    registry: &mut PluginRegistry,
) -> Result<(), PluginRegistryError> {
    registry.register(builtin_filesystem_manifest()?)
}

pub fn builtin_filesystem_tool_definitions() -> Vec<ToolDefinition> {
    vec![
        ToolDefinition {
            name: "list_files",
            description: "列出本地 workspace 内目录内容",
            action: "file.read",
            risk: "low",
            requires_approval: false,
            scope: "workspace",
            input_schema: json!({"type":"object","properties":{"path":{"type":"string","default":"."},"max_depth":{"type":"number","default":2},"include_hidden":{"type":"boolean","default":false}}}),
        },
        ToolDefinition {
            name: "read_file",
            description: "读取本地 workspace 内文件内容",
            action: "file.read",
            risk: "low",
            requires_approval: false,
            scope: "workspace",
            input_schema: json!({"type":"object","properties":{"path":{"type":"string"},"start_line":{"type":"number","default":1},"line_count":{"type":"number","default":200}},"required":["path"]}),
        },
        ToolDefinition {
            name: "search_text",
            description: "在本地 workspace 内搜索文本",
            action: "file.read",
            risk: "low",
            requires_approval: false,
            scope: "workspace",
            input_schema: json!({"type":"object","properties":{"query":{"type":"string"},"path":{"type":"string","default":"."},"glob":{"type":"string"},"max_results":{"type":"number","default":50}},"required":["query"]}),
        },
        ToolDefinition {
            name: "apply_patch",
            description: "在本地 workspace 内应用 unified diff patch",
            action: "file.write",
            risk: "medium",
            requires_approval: true,
            scope: "workspace",
            input_schema: json!({"type":"object","properties":{"patch":{"type":"string"},"summary":{"type":"string"}},"required":["patch","summary"]}),
        },
        ToolDefinition {
            name: "write_file",
            description: "写入或创建本地 workspace 内文本文件，必须同时提供 path 和 content；二进制或媒体内容使用 download_file。",
            action: "file.write",
            risk: "medium",
            requires_approval: true,
            scope: "workspace",
            input_schema: json!({"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"},"overwrite":{"type":"boolean","default":false}},"required":["path","content"]}),
        },
        ToolDefinition {
            name: "delete_file",
            description: "删除本地 workspace 内文件，必须经过用户授权并验证删除结果",
            action: "file.delete",
            risk: "high",
            requires_approval: true,
            scope: "workspace",
            input_schema: json!({"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
        },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    #[test]
    fn exposes_all_workspace_file_tools_with_expected_permissions() {
        let definitions = builtin_filesystem_tool_definitions();
        let names = definitions
            .iter()
            .map(|definition| definition.name)
            .collect::<HashSet<_>>();
        assert_eq!(names.len(), 6);
        for name in [
            "list_files",
            "read_file",
            "search_text",
            "apply_patch",
            "write_file",
            "delete_file",
        ] {
            assert!(names.contains(name));
        }
        assert!(definitions
            .iter()
            .find(|definition| definition.name == "write_file")
            .is_some_and(|definition| definition.requires_approval));
        assert!(definitions
            .iter()
            .find(|definition| definition.name == "delete_file")
            .is_some_and(|definition| definition.requires_approval));
    }
}
