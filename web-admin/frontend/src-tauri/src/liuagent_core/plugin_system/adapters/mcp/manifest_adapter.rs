use serde_json::{json, Value};

use crate::liuagent_core::tools::mcp::{DiscoveredMcpTool, McpToolAnnotations};

use super::super::super::{
    CapabilityKind, CapabilityManifest, CapabilitySelection, PluginManifest, PluginPermissions,
    PluginRegistry, PluginRegistryError, PluginSource, PluginType, RiskLevel,
};

pub fn mcp_plugin_manifest(
    server_id: &str,
    server_config: &Value,
    tools: &[DiscoveredMcpTool],
) -> Result<PluginManifest, PluginRegistryError> {
    let normalized_server_id = normalize_server_id(server_id)?;
    let plugin_id = format!("mcp.{normalized_server_id}");
    let capabilities = tools.iter().map(mcp_tool_capability).collect();
    let risk = if tools
        .iter()
        .any(|tool| tool.annotations.destructive == Some(true))
    {
        RiskLevel::High
    } else {
        RiskLevel::Medium
    };

    let manifest = PluginManifest {
        id: plugin_id,
        plugin_type: PluginType::Mcp,
        name: normalized_server_id.clone(),
        display_name: format!("MCP: {normalized_server_id}"),
        description: format!("由 MCP Server {normalized_server_id} 提供的动态工具和资源能力。"),
        version: server_config
            .get("version")
            .and_then(Value::as_str)
            .filter(|version| !version.trim().is_empty())
            .unwrap_or("0.0.0")
            .to_string(),
        source: PluginSource::Mcp,
        capabilities,
        dependencies: Vec::new(),
        config_schema: Some(json!({
            "type": "object",
            "properties": {
                "serverId": {"type": "string"},
                "transport": {"type": "string", "enum": ["stdio", "http", "sse"]}
            }
        })),
        permissions: Some(PluginPermissions {
            risk,
            requires_approval: true,
            scope: "mcp-server".to_string(),
        }),
        lifecycle: Default::default(),
        ui: None,
        enabled: server_config
            .get("enabled")
            .and_then(Value::as_bool)
            .unwrap_or(true),
    };
    manifest
        .validate()
        .map_err(|error| PluginRegistryError::InvalidManifest(error.to_string()))?;
    Ok(manifest)
}

pub fn register_mcp_plugin(
    registry: &mut PluginRegistry,
    server_id: &str,
    server_config: &Value,
    tools: &[DiscoveredMcpTool],
) -> Result<(), PluginRegistryError> {
    registry.register(mcp_plugin_manifest(server_id, server_config, tools)?)
}

fn mcp_tool_capability(tool: &DiscoveredMcpTool) -> CapabilityManifest {
    let capability_id = tool.canonical_tool_id.trim();
    let when_to_use = if tool.description.trim().is_empty() {
        vec![format!(
            "用户请求使用 MCP Server {} 的工具 {}",
            tool.server_id, tool.name
        )]
    } else {
        vec![tool.description.clone()]
    };
    CapabilityManifest {
        id: capability_id.to_string(),
        kind: CapabilityKind::Tool,
        name: tool.name.clone(),
        description: if tool.description.trim().is_empty() {
            format!("调用 MCP Server {} 的 {} 工具。", tool.server_id, tool.name)
        } else {
            tool.description.clone()
        },
        selection: Some(CapabilitySelection {
            when_to_use,
            avoid_when: vec!["MCP Server 未启用或连接不可用".to_string()],
            priority: mcp_tool_priority(&tool.annotations),
            ..CapabilitySelection::default()
        }),
        input_schema: Some(tool.input_schema.clone()),
        output_schema: None,
        metadata: Some(json!({
            "hostExecutor": "tools.mcp.call_mcp_tool",
            "mcpServer": tool.server,
            "mcpServerId": tool.server_id,
            "mcpTool": tool.name,
            "canonicalToolId": tool.canonical_tool_id,
            "domain": tool.domain,
            "annotations": {
                "readOnly": tool.annotations.read_only,
                "destructive": tool.annotations.destructive,
                "idempotent": tool.annotations.idempotent,
                "openWorld": tool.annotations.open_world
            }
        })),
    }
}

fn mcp_tool_priority(annotations: &McpToolAnnotations) -> i32 {
    if annotations.destructive == Some(true) {
        20
    } else if annotations.read_only == Some(true) {
        60
    } else {
        40
    }
}

fn normalize_server_id(server_id: &str) -> Result<String, PluginRegistryError> {
    let normalized = server_id.trim().to_ascii_lowercase().replace('_', "-");
    if normalized.is_empty()
        || !normalized.chars().all(|character| {
            character.is_ascii_lowercase() || character.is_ascii_digit() || character == '-'
        })
        || normalized.starts_with('-')
        || normalized.ends_with('-')
    {
        return Err(PluginRegistryError::InvalidManifest(format!(
            "invalid MCP server id: {server_id}"
        )));
    }
    Ok(normalized)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn discovered_tool(name: &str, destructive: Option<bool>) -> DiscoveredMcpTool {
        DiscoveredMcpTool {
            server: "github".to_string(),
            server_id: "github".to_string(),
            canonical_tool_id: format!("integrations.github.{name}"),
            domain: "integrations".to_string(),
            name: name.to_string(),
            description: format!("Use {name}"),
            input_schema: json!({"type": "object", "properties": {}}),
            annotations: McpToolAnnotations {
                read_only: Some(destructive != Some(true)),
                destructive,
                ..McpToolAnnotations::default()
            },
        }
    }

    #[test]
    fn maps_discovered_mcp_tools_to_a_server_plugin() {
        let tools = vec![discovered_tool("search", Some(false))];
        let manifest = mcp_plugin_manifest(
            "GitHub",
            &json!({"type": "http", "url": "https://example.test/mcp"}),
            &tools,
        )
        .unwrap();

        assert_eq!(manifest.id, "mcp.github");
        assert_eq!(manifest.plugin_type, PluginType::Mcp);
        assert_eq!(manifest.capabilities.len(), 1);
        assert_eq!(manifest.capabilities[0].id, "integrations.github.search");
        assert_eq!(
            manifest.capabilities[0].metadata.as_ref().unwrap()["hostExecutor"],
            "tools.mcp.call_mcp_tool"
        );
    }

    #[test]
    fn marks_plugins_with_destructive_tools_as_high_risk() {
        let tools = vec![discovered_tool("create_issue", Some(true))];
        let manifest = mcp_plugin_manifest("github", &json!({}), &tools).unwrap();

        assert_eq!(manifest.permissions.unwrap().risk, RiskLevel::High);
    }

    #[test]
    fn registers_dynamic_mcp_plugin_in_registry() {
        let mut registry = PluginRegistry::new();
        register_mcp_plugin(
            &mut registry,
            "github",
            &json!({"enabled": true}),
            &[discovered_tool("search", Some(false))],
        )
        .unwrap();

        assert!(registry.get("mcp.github").is_some());
        assert!(registry
            .get_capability("integrations.github.search")
            .is_some());
    }
}
