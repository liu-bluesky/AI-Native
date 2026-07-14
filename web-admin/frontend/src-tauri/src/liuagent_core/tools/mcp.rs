//! 统一 MCP registry 调用。
//!
//! 桌面端从会话/项目设置传入的 MCP registry 读取 server 配置，并按 server transport
//! 通过 MCP JSON-RPC 调用 tools/list、resources/read 和 tools/call。

use reqwest::blocking::Client;
use reqwest::header::{HeaderMap, HeaderName, HeaderValue};
use reqwest::Url;
use serde_json::{json, Value};
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crate::liuagent_core::args::{required_string_arg, string_arg};
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};
use crate::liuagent_core::workspace::{resolve_workspace_child, resolve_workspace_root};

const MCP_TIMEOUT_MS: u64 = 10_000;
const MAX_MCP_OUTPUT_CHARS: usize = 120_000;

#[derive(Debug, Clone)]
pub struct DiscoveredMcpTool {
    /// Physical registry connection used by the desktop host.
    pub server: String,
    /// Logical capability server advertised by the runtime catalog.
    pub server_id: String,
    pub canonical_tool_id: String,
    pub domain: String,
    pub name: String,
    pub description: String,
    pub input_schema: Value,
    pub annotations: McpToolAnnotations,
}

impl DiscoveredMcpTool {
    fn from_wire_tool(physical_server: &str, tool: &Value) -> Result<Self, ToolError> {
        let name = tool
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim();
        if name.is_empty() {
            return Err(ToolError::new(
                "mcp.config_invalid",
                format!("MCP server {physical_server} returned a tool without name"),
            ));
        }
        let input_schema = tool
            .get("inputSchema")
            .or_else(|| tool.get("input_schema"))
            .cloned()
            .unwrap_or_else(|| json!({"type": "object", "properties": {}}));
        if !input_schema.is_object() {
            return Err(ToolError::new(
                "mcp.config_invalid",
                format!("MCP tool {physical_server}/{name} returned an invalid input schema"),
            ));
        }
        let metadata = tool.get("_meta").or_else(|| tool.get("meta"));
        let inferred_integration = name.starts_with("external__")
            || name.starts_with("system_mcp__")
            || metadata
                .and_then(|value| value.get("domain"))
                .and_then(Value::as_str)
                == Some("integrations");
        let domain = metadata
            .and_then(|value| value.get("domain"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| matches!(*value, "system" | "integrations"))
            .unwrap_or(if inferred_integration {
                "integrations"
            } else {
                "system"
            })
            .to_string();
        let inferred_server_id = integration_server_id_from_tool_name(name);
        let server_id = metadata
            .and_then(|value| value.get("server_id").or_else(|| value.get("serverId")))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or(if domain == "integrations" {
                inferred_server_id.as_deref().unwrap_or("integrations")
            } else {
                "system"
            })
            .to_string();
        let canonical_tool_id = metadata
            .and_then(|value| {
                value
                    .get("canonical_tool_id")
                    .or_else(|| value.get("canonicalToolId"))
            })
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| format!("{domain}.{server_id}.{name}"));
        Ok(Self {
            server: physical_server.to_string(),
            server_id,
            canonical_tool_id,
            domain,
            name: name.to_string(),
            description: tool
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string(),
            input_schema,
            annotations: McpToolAnnotations::from_value(tool.get("annotations")),
        })
    }
}

fn integration_server_id_from_tool_name(name: &str) -> Option<String> {
    let mut parts = name.split("__");
    let prefix = parts.next()?;
    if !matches!(prefix, "external" | "system_mcp") {
        return None;
    }
    parts
        .next()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct McpToolAnnotations {
    pub read_only: Option<bool>,
    pub destructive: Option<bool>,
    pub idempotent: Option<bool>,
    pub open_world: Option<bool>,
}

impl McpToolAnnotations {
    fn from_value(value: Option<&Value>) -> Self {
        let bool_value = |camel_case: &str, snake_case: &str| {
            value.and_then(|annotations| {
                annotations
                    .get(camel_case)
                    .or_else(|| annotations.get(snake_case))
                    .and_then(Value::as_bool)
            })
        };
        Self {
            read_only: bool_value("readOnlyHint", "read_only_hint"),
            destructive: bool_value("destructiveHint", "destructive_hint"),
            idempotent: bool_value("idempotentHint", "idempotent_hint"),
            open_world: bool_value("openWorldHint", "open_world_hint"),
        }
    }

    pub fn is_read_only(&self) -> bool {
        self.read_only == Some(true) && self.destructive != Some(true)
    }
}

pub fn discover_mcp_tools(
    workspace_path: &str,
    mcp_config: &Value,
    backend_api_base_url: &str,
    backend_token: &str,
) -> Result<Vec<DiscoveredMcpTool>, ToolError> {
    let arguments = json!({
        "_mcp_config": mcp_config,
        "_backend_api_base_url": backend_api_base_url,
        "_backend_token": backend_token,
    });
    let root = resolve_workspace_root(workspace_path)?;
    let config = read_registry_config(&root, &arguments)?;
    let mut discovered = Vec::new();
    for (server, _) in server_entries(&config)? {
        let response = invoke_mcp_method(
            workspace_path,
            &arguments,
            &server,
            "tools/list",
            json!({}),
            MCP_TIMEOUT_MS,
        )?;
        for tool in response
            .get("tools")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            discovered.push(DiscoveredMcpTool::from_wire_tool(&server, tool)?);
        }
    }
    Ok(discovered)
}

pub fn select_mcp_tools_for_goal(
    discovered: Vec<DiscoveredMcpTool>,
    user_goal: &str,
    max_tools: usize,
) -> Vec<DiscoveredMcpTool> {
    let max_tools = max_tools.clamp(1, 24);
    let goal = user_goal.trim().to_lowercase();
    let goal_terms = search_terms(&goal);
    let mut scored = discovered
        .into_iter()
        .map(|tool| {
            let haystack = format!(
                "{} {} {} {} {}",
                tool.name, tool.description, tool.server_id, tool.domain, tool.canonical_tool_id
            )
            .to_lowercase();
            let mut score = goal_terms
                .iter()
                .filter(|term| haystack.contains(term.as_str()))
                .count() as i32
                * 10;
            for (intent_terms, tool_terms) in intent_tool_aliases() {
                if intent_terms.iter().any(|term| goal.contains(term))
                    && tool_terms.iter().any(|term| haystack.contains(term))
                {
                    score += 30;
                }
            }
            if tool.annotations.is_read_only() {
                score += 1;
            }
            (score, tool)
        })
        .collect::<Vec<_>>();
    scored.sort_by(|(left_score, left), (right_score, right)| {
        right_score
            .cmp(left_score)
            .then_with(|| left.canonical_tool_id.cmp(&right.canonical_tool_id))
    });
    let top_score = scored.first().map(|(score, _)| *score).unwrap_or(0);
    let has_positive = top_score > 1;
    let mut selected = Vec::new();
    for (score, tool) in scored {
        if selected.len() >= max_tools {
            break;
        }
        if has_positive && score < top_score {
            continue;
        }
        selected.push(tool);
    }
    selected
}

fn search_terms(value: &str) -> Vec<String> {
    value
        .split(|character: char| {
            character.is_whitespace()
                || matches!(
                    character,
                    ',' | '.'
                        | ':'
                        | ';'
                        | '/'
                        | '\\'
                        | '('
                        | ')'
                        | '['
                        | ']'
                        | '{'
                        | '}'
                        | '，'
                        | '。'
                        | '：'
                        | '；'
                        | '、'
                        | '（'
                        | '）'
                )
        })
        .map(str::trim)
        .filter(|term| term.chars().count() >= 2)
        .map(str::to_string)
        .collect()
}

fn intent_tool_aliases() -> Vec<(&'static [&'static str], &'static [&'static str])> {
    vec![
        (
            &["mcp", "服务", "server", "可用工具", "工具目录"],
            &["list_runtime_mcp_servers"],
        ),
        (
            &["智能体", "员工", "成员", "agent", "employee", "member"],
            &["member", "employee"],
        ),
        (&["项目", "project"], &["project"]),
        (&["规则", "rule"], &["rule"]),
        (&["技能", "skill"], &["skill"]),
        (&["任务树", "计划", "task", "plan"], &["task_tree", "plan"]),
        (&["记忆", "memory"], &["memory"]),
        (
            &["飞书", "github", "jira", "数据库", "database"],
            &["external__", "system_mcp__"],
        ),
    ]
}

#[cfg(test)]
fn unique_mcp_tool_route(
    discovered: Vec<DiscoveredMcpTool>,
    tool_name: &str,
) -> Result<Option<DiscoveredMcpTool>, ToolError> {
    let matches = discovered
        .into_iter()
        .filter(|tool| tool.name == tool_name.trim())
        .collect::<Vec<_>>();
    match matches.len() {
        0 => Ok(None),
        1 => Ok(matches.into_iter().next()),
        _ => Err(ToolError::new(
            "mcp.config_invalid",
            format!(
                "MCP tool name conflict: {} is exposed by multiple servers",
                tool_name.trim()
            ),
        )),
    }
}

pub fn list_mcp_tools(
    workspace_path: &str,
    arguments: &Value,
) -> Result<(Value, String), ToolError> {
    let server = string_arg(arguments, "server", "");
    if server.trim().is_empty() {
        let root = resolve_workspace_root(workspace_path)?;
        let config = read_registry_config(&root, arguments)?;
        let servers = server_entries(&config)?;
        let mut results = Vec::new();
        let mut total = 0usize;
        for (name, _) in servers {
            let response = invoke_mcp_method(
                workspace_path,
                arguments,
                &name,
                "tools/list",
                json!({}),
                MCP_TIMEOUT_MS,
            )?;
            let tools = response.get("tools").cloned().unwrap_or_else(|| json!([]));
            total += tools.as_array().map(|items| items.len()).unwrap_or(0);
            results.push(json!({
                "server": name,
                "tools": tools,
                "raw_result": response
            }));
        }
        return Ok((
            json!({
                "servers": results,
                "tools": flatten_tools_by_server(&json!(results)),
            }),
            format!("发现 {total} 个 MCP 工具"),
        ));
    }

    let response = invoke_mcp_method(
        workspace_path,
        arguments,
        &server,
        "tools/list",
        json!({}),
        MCP_TIMEOUT_MS,
    )?;
    let tools = response.get("tools").cloned().unwrap_or_else(|| json!([]));
    let count = tools.as_array().map(|items| items.len()).unwrap_or(0);
    Ok((
        json!({
            "server": server.trim(),
            "tools": tools,
            "raw_result": response
        }),
        format!("发现 {count} 个 MCP 工具"),
    ))
}

pub fn read_mcp_resource(
    workspace_path: &str,
    arguments: &Value,
) -> Result<(Value, String), ToolError> {
    let server = required_string_arg(arguments, "server")?;
    let uri = required_string_arg(arguments, "uri")?;
    let response = invoke_mcp_method(
        workspace_path,
        arguments,
        &server,
        "resources/read",
        json!({"uri": uri}),
        MCP_TIMEOUT_MS,
    )?;
    let contents = response
        .get("contents")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let first = contents.first().cloned().unwrap_or_else(|| json!({}));
    let content = first
        .get("text")
        .or_else(|| first.get("content"))
        .or_else(|| first.get("blob"))
        .cloned()
        .unwrap_or_else(|| json!(""));
    let content_text = if let Some(text) = content.as_str() {
        text.to_string()
    } else {
        serde_json::to_string(&content).unwrap_or_default()
    };
    let (content, truncated) = truncate_chars(&content_text, 40_000);
    let mime_type = first
        .get("mimeType")
        .or_else(|| first.get("mime_type"))
        .and_then(Value::as_str)
        .unwrap_or("text/plain");
    Ok((
        json!({
            "server": server,
            "uri": first.get("uri").and_then(Value::as_str).unwrap_or(uri.as_str()),
            "mime_type": mime_type,
            "content": content,
            "truncated": truncated,
            "raw_result": response
        }),
        format!("读取 MCP 资源 {}", uri),
    ))
}

pub fn call_mcp_tool(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let server = required_string_arg(arguments, "server")?;
    let tool = required_string_arg(arguments, "tool")?;
    let route = resolve_mcp_tool_on_server(workspace_path, arguments, &server, &tool)?;
    call_routed_mcp_tool(
        tool_call_id,
        workspace_path,
        arguments,
        &route,
        permission_decision,
    )
}

pub fn call_routed_mcp_tool(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    route: &DiscoveredMcpTool,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let server = route.server.trim();
    let tool = route.name.trim();
    let tool_arguments = arguments
        .get("arguments")
        .filter(|value| value.is_object())
        .cloned()
        .unwrap_or_else(|| json!({}));
    validate_mcp_tool_arguments(route, &tool_arguments)?;
    require_mcp_tool_approval(tool_call_id, route, &tool_arguments, permission_decision)?;
    let response = invoke_mcp_method(
        workspace_path,
        arguments,
        &server,
        "tools/call",
        json!({
            "name": tool,
            "arguments": tool_arguments
        }),
        MCP_TIMEOUT_MS,
    )?;
    let is_error = response
        .get("isError")
        .or_else(|| response.get("is_error"))
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if is_error {
        return Err(ToolError::new(
            "mcp.failed",
            format!(
                "MCP tool returned error: {}",
                summarize_json_value(&response)
            ),
        ));
    }
    Ok((
        json!({
            "server": server,
            "tool": tool,
            "result": response
        }),
        format!("MCP 工具调用完成：{tool}"),
    ))
}

fn validate_mcp_tool_arguments(
    route: &DiscoveredMcpTool,
    arguments: &Value,
) -> Result<(), ToolError> {
    let required = route
        .input_schema
        .get("required")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    for field in required.iter().filter_map(Value::as_str) {
        if arguments.get(field).is_none() {
            return Err(ToolError::new(
                "tool.schema_invalid",
                format!(
                    "MCP tool {} is missing required argument: {field}",
                    route.canonical_tool_id
                ),
            ));
        }
    }
    let properties = route
        .input_schema
        .get("properties")
        .and_then(Value::as_object);
    if let (Some(properties), Some(arguments)) = (properties, arguments.as_object()) {
        for (field, value) in arguments {
            let Some(schema) = properties.get(field) else {
                continue;
            };
            let expected_type = schema.get("type").and_then(Value::as_str).unwrap_or("");
            let valid = match expected_type {
                "string" => value.is_string(),
                "object" => value.is_object(),
                "array" => value.is_array(),
                "boolean" => value.is_boolean(),
                "integer" => value.as_i64().is_some() || value.as_u64().is_some(),
                "number" => value.is_number(),
                _ => true,
            };
            if !valid {
                return Err(ToolError::new(
                    "tool.schema_invalid",
                    format!(
                        "MCP tool {} argument {field} must be {expected_type}",
                        route.canonical_tool_id
                    ),
                ));
            }
        }
    }
    Ok(())
}

fn resolve_mcp_tool_on_server(
    workspace_path: &str,
    arguments: &Value,
    server: &str,
    tool_name: &str,
) -> Result<DiscoveredMcpTool, ToolError> {
    let response = invoke_mcp_method(
        workspace_path,
        arguments,
        server,
        "tools/list",
        json!({}),
        MCP_TIMEOUT_MS,
    )?;
    let tool = response
        .get("tools")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .find(|tool| tool.get("name").and_then(Value::as_str) == Some(tool_name.trim()))
        .ok_or_else(|| {
            ToolError::new(
                "mcp.tool_not_found",
                format!(
                    "MCP tool not exposed by server {server}: {}",
                    tool_name.trim()
                ),
            )
        })?;
    DiscoveredMcpTool::from_wire_tool(server.trim(), tool)
}

fn require_mcp_tool_approval(
    tool_call_id: &str,
    route: &DiscoveredMcpTool,
    tool_arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(), ToolError> {
    if route.annotations.is_read_only() {
        return Ok(());
    }
    let risk = if route.annotations.destructive == Some(true) {
        "high"
    } else {
        "medium"
    };
    require_approval(
        tool_call_id,
        "mcp.call",
        risk,
        "project",
        &format!("调用 MCP 工具：{}/{}", route.server, route.name),
        json!({
            "server": route.server,
            "tool": route.name,
            "annotations": {
                "readOnlyHint": route.annotations.read_only,
                "destructiveHint": route.annotations.destructive,
                "idempotentHint": route.annotations.idempotent,
                "openWorldHint": route.annotations.open_world,
            },
            "arguments_summary": summarize_json_value(tool_arguments)
        }),
        permission_decision,
    )
}

fn invoke_mcp_method(
    workspace_path: &str,
    arguments: &Value,
    server: &str,
    method: &str,
    params: Value,
    timeout_ms: u64,
) -> Result<Value, ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let config = read_registry_config(&root, arguments)?;
    let server_config = resolve_server_config(&config, server, arguments)?;
    match server_config.transport {
        McpTransport::Stdio => {
            let output = run_stdio_command(&root, &server_config, method, params, timeout_ms)?;
            parse_json_rpc_result(&output, 2)
        }
        McpTransport::Http | McpTransport::Sse => {
            run_http_json_rpc(&server_config, method, params, timeout_ms)
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum McpTransport {
    Stdio,
    Http,
    Sse,
}

#[derive(Debug, Clone)]
struct ServerConfig {
    name: String,
    transport: McpTransport,
    command: String,
    args: Vec<String>,
    cwd: String,
    framing: String,
    url: String,
    headers: Vec<(String, String)>,
}

fn read_registry_config(root: &Path, arguments: &Value) -> Result<Value, ToolError> {
    if let Some(config) = arguments
        .get("_mcp_config")
        .filter(|value| value.is_object())
    {
        return Ok(config.clone());
    }

    let _ = root;
    Err(ToolError::new(
        "mcp.config_missing",
        "MCP registry config is missing from the current desktop session",
    ))
}

fn server_entries(config: &Value) -> Result<Vec<(String, Value)>, ToolError> {
    let servers = config
        .get("mcpServers")
        .or_else(|| config.get("servers"))
        .ok_or_else(|| ToolError::new("mcp.config_invalid", "missing mcpServers map"))?;
    let object = servers
        .as_object()
        .ok_or_else(|| ToolError::new("mcp.config_invalid", "mcpServers must be an object"))?;
    let mut entries = Vec::new();
    for (name, value) in object {
        if value
            .get("enabled")
            .and_then(Value::as_bool)
            .map(|enabled| !enabled)
            .unwrap_or(false)
        {
            continue;
        }
        entries.push((name.to_string(), value.clone()));
    }
    if entries.is_empty() {
        return Err(ToolError::new(
            "mcp.config_invalid",
            "mcpServers map is empty",
        ));
    }
    Ok(entries)
}

fn resolve_server_config(
    config: &Value,
    server: &str,
    arguments: &Value,
) -> Result<ServerConfig, ToolError> {
    let entries = server_entries(config)?;
    let (name, value) = if server.trim().is_empty() {
        entries
            .into_iter()
            .next()
            .ok_or_else(|| ToolError::new("mcp.config_invalid", "mcpServers map is empty"))?
    } else {
        let server_name = server.trim();
        entries
            .into_iter()
            .find(|(name, _)| name == server_name)
            .ok_or_else(|| {
                ToolError::new(
                    "mcp.server_not_found",
                    format!("MCP server not configured: {server_name}"),
                )
            })?
    };

    let raw_transport = value
        .get("transport")
        .or_else(|| value.get("type"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_ascii_lowercase();
    let url = resolve_server_url(&value, arguments)?;
    let command = value
        .get("command")
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or("")
        .to_string();
    let transport = if !command.is_empty()
        && !matches!(raw_transport.as_str(), "http" | "streamable-http" | "sse")
    {
        McpTransport::Stdio
    } else if raw_transport == "sse" {
        McpTransport::Sse
    } else if !url.is_empty() {
        McpTransport::Http
    } else {
        return Err(ToolError::new(
            "mcp.config_invalid",
            "server must configure url or command",
        ));
    };

    let args = value
        .get("args")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let cwd = value
        .get("cwd")
        .and_then(Value::as_str)
        .unwrap_or(".")
        .trim()
        .to_string();
    let framing = value
        .get("framing")
        .or_else(|| value.get("protocol"))
        .and_then(Value::as_str)
        .unwrap_or("line-json")
        .trim()
        .to_ascii_lowercase();
    let mut headers = parse_config_headers(&value)?;
    let desktop_auth = value
        .get("desktopAuth")
        .or_else(|| value.get("desktop_auth"))
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if desktop_auth {
        let token = arguments
            .get("_backend_token")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or("");
        if token.is_empty() {
            return Err(ToolError::new(
                "mcp.config_invalid",
                format!("desktop-auth MCP server {name} requires backend login context"),
            ));
        }
        headers.retain(|(key, _)| !key.eq_ignore_ascii_case("authorization"));
        headers.push(("Authorization".to_string(), format!("Bearer {token}")));
    }
    Ok(ServerConfig {
        name,
        transport,
        command,
        args,
        cwd,
        framing,
        url,
        headers,
    })
}

fn resolve_server_url(value: &Value, arguments: &Value) -> Result<String, ToolError> {
    let raw = value
        .get("url")
        .or_else(|| value.get("endpoint"))
        .or_else(|| value.get("endpoint_http"))
        .or_else(|| value.get("endpoint_sse"))
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or("");
    if raw.is_empty() {
        return Ok(String::new());
    }
    if raw.starts_with("http://") || raw.starts_with("https://") {
        return Ok(raw.to_string());
    }
    let base = arguments
        .get("_backend_api_base_url")
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or("");
    if base.is_empty() {
        return Err(ToolError::new(
            "mcp.config_invalid",
            "relative MCP url requires backend api base url",
        ));
    }
    let mut parsed_base = Url::parse(base).map_err(|err| {
        ToolError::new(
            "mcp.config_invalid",
            format!("invalid backend api base url: {err}"),
        )
    })?;
    parsed_base.set_path("");
    parsed_base.set_query(None);
    parsed_base
        .join(raw.trim_start_matches('/'))
        .map(|url| url.to_string())
        .map_err(|err| ToolError::new("mcp.config_invalid", format!("invalid MCP url: {err}")))
}

fn parse_config_headers(value: &Value) -> Result<Vec<(String, String)>, ToolError> {
    let Some(headers) = value.get("headers").and_then(Value::as_object) else {
        return Ok(Vec::new());
    };
    let mut output = Vec::new();
    for (key, value) in headers {
        let Some(raw_value) = value.as_str() else {
            return Err(ToolError::new(
                "mcp.config_invalid",
                format!("MCP header value must be string: {key}"),
            ));
        };
        output.push((key.to_string(), raw_value.to_string()));
    }
    Ok(output)
}

fn run_http_json_rpc(
    server: &ServerConfig,
    method: &str,
    params: Value,
    timeout_ms: u64,
) -> Result<Value, ToolError> {
    let client = Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-mcp/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "mcp.failed",
                format!("create MCP HTTP client failed: {err}"),
            )
        })?;
    let mut session_headers = HeaderMap::new();
    let init = http_rpc_request(
        &client,
        server,
        "initialize",
        json!({
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "liuagent-core",
                "version": "0.1.0"
            }
        }),
        1,
        &session_headers,
    )?;
    if let Some(session_id) = init
        .get("_meta")
        .and_then(|meta| meta.get("mcp_session_id"))
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
    {
        session_headers.insert(
            HeaderName::from_static("mcp-session-id"),
            HeaderValue::from_str(session_id).map_err(|err| {
                ToolError::new(
                    "mcp.failed",
                    format!("invalid MCP session id header: {err}"),
                )
            })?,
        );
    }
    let _ = http_rpc_notify(
        &client,
        server,
        "notifications/initialized",
        json!({}),
        &session_headers,
    );
    http_rpc_request(&client, server, method, params, 2, &session_headers)
}

fn http_rpc_request(
    client: &Client,
    server: &ServerConfig,
    method: &str,
    params: Value,
    id: i64,
    session_headers: &HeaderMap,
) -> Result<Value, ToolError> {
    let url = parse_http_url(&server.url)?;
    let response = client
        .post(url)
        .headers(build_http_headers(server, session_headers)?)
        .json(&json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params
        }))
        .send()
        .map_err(|err| ToolError::new("mcp.failed", format!("MCP HTTP request failed: {err}")))?;
    let status = response.status().as_u16();
    let content_type = response
        .headers()
        .get("content-type")
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
        .to_string();
    let session_id = response
        .headers()
        .get("mcp-session-id")
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
        .to_string();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "mcp.failed",
            format!("read MCP HTTP response failed: {err}"),
        )
    })?;
    if status >= 400 {
        return Err(ToolError::new(
            "mcp.failed",
            format!("MCP HTTP {status}: {}", truncate_chars(&text, 600).0),
        ));
    }
    let mut payload = parse_http_rpc_body(&text, &content_type)?;
    if let Some(error) = payload.get("error") {
        return Err(ToolError::new(
            "mcp.failed",
            format!("MCP returned error: {}", summarize_json_value(error)),
        ));
    }
    let mut result = payload.get("result").cloned().unwrap_or_else(|| json!({}));
    if let Some(object) = result.as_object_mut() {
        object.insert(
            "_meta".to_string(),
            json!({
                "status": status,
                "content_type": content_type,
                "mcp_session_id": session_id
            }),
        );
    } else {
        payload["_meta"] = json!({
            "status": status,
            "content_type": content_type,
            "mcp_session_id": session_id
        });
        result = payload;
    }
    Ok(result)
}

fn http_rpc_notify(
    client: &Client,
    server: &ServerConfig,
    method: &str,
    params: Value,
    session_headers: &HeaderMap,
) -> Result<(), ToolError> {
    let url = parse_http_url(&server.url)?;
    client
        .post(url)
        .headers(build_http_headers(server, session_headers)?)
        .json(&json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }))
        .send()
        .map_err(|err| ToolError::new("mcp.failed", format!("MCP HTTP notify failed: {err}")))?;
    Ok(())
}

fn build_http_headers(
    server: &ServerConfig,
    session_headers: &HeaderMap,
) -> Result<HeaderMap, ToolError> {
    let mut headers = HeaderMap::new();
    headers.insert(
        "accept",
        HeaderValue::from_static("application/json, text/event-stream;q=0.9, */*;q=0.8"),
    );
    headers.insert("content-type", HeaderValue::from_static("application/json"));
    for (key, value) in &server.headers {
        let name = HeaderName::from_bytes(key.as_bytes()).map_err(|err| {
            ToolError::new(
                "mcp.config_invalid",
                format!("invalid MCP header name: {err}"),
            )
        })?;
        let header_value = HeaderValue::from_str(value).map_err(|err| {
            ToolError::new(
                "mcp.config_invalid",
                format!("invalid MCP header value: {err}"),
            )
        })?;
        headers.insert(name, header_value);
    }
    for (key, value) in session_headers {
        headers.insert(key, value.clone());
    }
    Ok(headers)
}

fn parse_http_url(raw: &str) -> Result<Url, ToolError> {
    let url = Url::parse(raw.trim())
        .map_err(|err| ToolError::new("mcp.config_invalid", format!("invalid MCP url: {err}")))?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "mcp.config_invalid",
            "MCP url must use http or https",
        ));
    }
    Ok(url)
}

fn parse_http_rpc_body(body: &str, content_type: &str) -> Result<Value, ToolError> {
    if content_type
        .to_ascii_lowercase()
        .contains("text/event-stream")
    {
        return parse_sse_json_payload(body);
    }
    serde_json::from_str::<Value>(body.trim()).map_err(|err| {
        ToolError::new(
            "mcp.failed",
            format!("parse MCP JSON response failed: {err}"),
        )
    })
}

fn parse_sse_json_payload(body: &str) -> Result<Value, ToolError> {
    for block in body
        .split("\n\n")
        .map(str::trim)
        .filter(|item| !item.is_empty())
    {
        let payload = block
            .lines()
            .map(str::trim)
            .filter_map(|line| line.strip_prefix("data:").map(str::trim))
            .filter(|line| !line.is_empty())
            .collect::<Vec<_>>()
            .join("\n");
        if payload.is_empty() {
            continue;
        }
        return serde_json::from_str::<Value>(&payload).map_err(|err| {
            ToolError::new("mcp.failed", format!("parse MCP SSE payload failed: {err}"))
        });
    }
    Err(ToolError::new(
        "mcp.failed",
        "MCP event-stream did not contain JSON data",
    ))
}

fn run_stdio_command(
    root: &Path,
    server: &ServerConfig,
    method: &str,
    params: Value,
    timeout_ms: u64,
) -> Result<String, ToolError> {
    let cwd = resolve_workspace_child(root, &server.cwd, true)?;
    if !cwd.is_dir() {
        return Err(ToolError::new(
            "mcp.config_invalid",
            "server.cwd is not a directory",
        ));
    }
    let temp_base = adapter_temp_base();
    let stdout_path = temp_base.with_extension("stdout");
    let stderr_path = temp_base.with_extension("stderr");
    let stdout_file = File::create(&stdout_path).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("create MCP stdout failed: {err}"),
        )
    })?;
    let stderr_file = File::create(&stderr_path).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("create MCP stderr failed: {err}"),
        )
    })?;
    let mut child = Command::new(&server.command)
        .args(&server.args)
        .current_dir(&cwd)
        .stdin(Stdio::piped())
        .stdout(Stdio::from(stdout_file))
        .stderr(Stdio::from(stderr_file))
        .spawn()
        .map_err(|err| {
            ToolError::new(
                "mcp.failed",
                format!("spawn MCP server {} failed: {err}", server.name),
            )
        })?;
    if let Some(stdin) = child.stdin.as_mut() {
        let messages = vec![
            json!({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "liuagent-core",
                        "version": "0.1.0"
                    }
                }
            }),
            json!({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }),
            json!({
                "jsonrpc": "2.0",
                "id": 2,
                "method": method,
                "params": params
            }),
        ];
        for message in messages {
            write_mcp_request(stdin, &message, &server.framing)?;
        }
    }
    drop(child.stdin.take());

    let started = Instant::now();
    let timeout = Duration::from_millis(timeout_ms);
    let (exit_code, timed_out) = loop {
        match child.try_wait() {
            Ok(Some(status)) => break (status.code().unwrap_or(-1), false),
            Ok(None) if started.elapsed() >= timeout => {
                let _ = child.kill();
                let _ = child.wait();
                break (-1, true);
            }
            Ok(None) => thread::sleep(Duration::from_millis(20)),
            Err(err) => {
                cleanup_temp_outputs(&stdout_path, &stderr_path);
                return Err(ToolError::new(
                    "mcp.failed",
                    format!("wait MCP server failed: {err}"),
                ));
            }
        }
    };
    let stdout = read_output_file(&stdout_path, MAX_MCP_OUTPUT_CHARS);
    let stderr = read_output_file(&stderr_path, 20_000);
    cleanup_temp_outputs(&stdout_path, &stderr_path);
    if timed_out {
        return Err(ToolError::new(
            "mcp.failed",
            format!("MCP server timed out after {timeout_ms}ms"),
        ));
    }
    if exit_code != 0 && stdout.trim().is_empty() {
        return Err(ToolError::new(
            "mcp.failed",
            format!("MCP server exited with {exit_code}: {stderr}"),
        ));
    }
    Ok(stdout)
}

fn parse_json_rpc_result(output: &str, expected_id: i64) -> Result<Value, ToolError> {
    for value in parse_json_rpc_messages(output)? {
        if value.get("id").and_then(Value::as_i64) != Some(expected_id) {
            continue;
        }
        if let Some(error) = value.get("error") {
            return Err(ToolError::new(
                "mcp.failed",
                format!("MCP returned error: {}", summarize_json_value(error)),
            ));
        }
        return Ok(value.get("result").cloned().unwrap_or_else(|| json!({})));
    }
    Err(ToolError::new(
        "mcp.failed",
        "MCP server did not return a matching JSON-RPC response",
    ))
}

fn write_mcp_request(
    stdin: &mut impl Write,
    message: &Value,
    framing: &str,
) -> Result<(), ToolError> {
    let raw = serde_json::to_string(message).map_err(|err| {
        ToolError::new("mcp.failed", format!("serialize MCP request failed: {err}"))
    })?;
    if matches!(framing, "line-json" | "jsonl" | "newline") {
        writeln!(stdin, "{raw}")
    } else {
        write!(
            stdin,
            "Content-Length: {}\r\n\r\n{}",
            raw.as_bytes().len(),
            raw
        )
    }
    .map_err(|err| ToolError::new("mcp.failed", format!("write MCP stdin failed: {err}")))
}

fn parse_json_rpc_messages(output: &str) -> Result<Vec<Value>, ToolError> {
    if output.contains("Content-Length:") {
        let framed = parse_content_length_messages(output)?;
        if !framed.is_empty() {
            return Ok(framed);
        }
    }
    let mut values = Vec::new();
    for line in output.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || !trimmed.starts_with('{') {
            continue;
        }
        let value = serde_json::from_str::<Value>(trimmed).map_err(|err| {
            ToolError::new("mcp.failed", format!("parse MCP response failed: {err}"))
        })?;
        values.push(value);
    }
    Ok(values)
}

fn parse_content_length_messages(output: &str) -> Result<Vec<Value>, ToolError> {
    let mut cursor = std::io::Cursor::new(output.as_bytes());
    let mut values = Vec::new();
    loop {
        let mut header = Vec::new();
        let mut last_four = [0u8; 4];
        loop {
            let mut byte = [0u8; 1];
            let read = cursor.read(&mut byte).map_err(|err| {
                ToolError::new("mcp.failed", format!("read MCP frame failed: {err}"))
            })?;
            if read == 0 {
                return Ok(values);
            }
            header.push(byte[0]);
            last_four.rotate_left(1);
            last_four[3] = byte[0];
            if last_four == *b"\r\n\r\n" {
                break;
            }
            if header.len() > 65536 {
                return Err(ToolError::new("mcp.failed", "MCP frame header too large"));
            }
        }
        let header_text = String::from_utf8_lossy(&header).to_string();
        let content_length = header_text
            .lines()
            .find_map(|line| {
                let (key, value) = line.split_once(':')?;
                if key.trim().eq_ignore_ascii_case("content-length") {
                    value.trim().parse::<usize>().ok()
                } else {
                    None
                }
            })
            .ok_or_else(|| ToolError::new("mcp.failed", "MCP frame missing Content-Length"))?;
        let mut body = vec![0u8; content_length];
        cursor.read_exact(&mut body).map_err(|err| {
            ToolError::new("mcp.failed", format!("read MCP frame body failed: {err}"))
        })?;
        let value = serde_json::from_slice::<Value>(&body).map_err(|err| {
            ToolError::new("mcp.failed", format!("parse MCP frame body failed: {err}"))
        })?;
        values.push(value);
    }
}

fn flatten_tools_by_server(servers: &Value) -> Value {
    let mut output = Vec::new();
    for server in servers.as_array().into_iter().flatten() {
        let server_name = server.get("server").and_then(Value::as_str).unwrap_or("");
        for tool in server
            .get("tools")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let mut item = tool.clone();
            if let Some(object) = item.as_object_mut() {
                object.insert("server".to_string(), json!(server_name));
            }
            output.push(item);
        }
    }
    json!(output)
}

fn adapter_temp_base() -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    std::env::temp_dir().join(format!("liuagent_mcp_{nonce}"))
}

fn read_output_file(path: &Path, max_chars: usize) -> String {
    let raw = fs::read(path).unwrap_or_default();
    let output = String::from_utf8_lossy(&raw).to_string();
    truncate_chars(&output, max_chars).0
}

fn cleanup_temp_outputs(stdout_path: &Path, stderr_path: &Path) {
    let _ = fs::remove_file(stdout_path);
    let _ = fs::remove_file(stderr_path);
}

fn truncate_chars(value: &str, max_chars: usize) -> (String, bool) {
    let mut chars = value.chars();
    let output = chars.by_ref().take(max_chars).collect::<String>();
    let truncated = chars.next().is_some();
    (output, truncated)
}

fn summarize_json_value(value: &Value) -> String {
    let raw = serde_json::to_string(value).unwrap_or_default();
    truncate_chars(&raw, 600).0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_content_length_json_rpc_frames() {
        let body = r#"{"jsonrpc":"2.0","id":2,"result":{"ok":true}}"#;
        let output = format!("Content-Length: {}\r\n\r\n{}", body.as_bytes().len(), body);
        let parsed = parse_json_rpc_result(&output, 2).expect("parse framed response");
        assert_eq!(parsed["ok"], true);
    }

    #[test]
    fn writes_content_length_json_rpc_request_by_default() {
        let mut output = Vec::new();
        write_mcp_request(
            &mut output,
            &json!({"jsonrpc":"2.0","id":1,"method":"tools/list"}),
            "content-length",
        )
        .expect("write frame");
        let raw = String::from_utf8(output).expect("utf8 frame");
        assert!(raw.starts_with("Content-Length: "));
        assert!(raw.contains("\r\n\r\n"));
        assert!(raw.ends_with(r#""method":"tools/list"}"#));
    }

    #[test]
    fn resolves_http_server_from_unified_config() {
        let config = json!({
            "mcpServers": {
                "query": {
                    "type": "sse",
                    "url": "http://127.0.0.1:8000/mcp/query/sse",
                    "enabled": true
                }
            }
        });
        let server =
            resolve_server_config(&config, "query", &json!({})).expect("resolve http server");
        assert_eq!(server.transport, McpTransport::Sse);
        assert_eq!(server.url, "http://127.0.0.1:8000/mcp/query/sse");
    }

    #[test]
    fn rejects_unknown_server_without_guessing() {
        let config = json!({
            "mcpServers": {
                "runtime": {
                    "type": "http",
                    "url": "http://127.0.0.1:8000/mcp/runtime/mcp",
                    "enabled": true
                }
            }
        });
        let error = resolve_server_config(&config, "default", &json!({})).unwrap_err();
        assert_eq!(error.code, "mcp.server_not_found");
        assert!(error.message.contains("default"));
    }

    #[test]
    fn desktop_auth_server_uses_backend_login_token() {
        let config = json!({
            "mcpServers": {
                "runtime": {
                    "type": "http",
                    "url": "/mcp/runtime/mcp?project_id=proj-657fe77f",
                    "desktopAuth": true,
                    "enabled": true
                }
            }
        });
        let server = resolve_server_config(
            &config,
            "runtime",
            &json!({
                "_backend_api_base_url": "http://127.0.0.1:8000/api",
                "_backend_token": "login-token"
            }),
        )
        .unwrap();
        assert_eq!(
            server.url,
            "http://127.0.0.1:8000/mcp/runtime/mcp?project_id=proj-657fe77f"
        );
        assert!(server.headers.iter().any(|(key, value)| {
            key.eq_ignore_ascii_case("authorization") && value == "Bearer login-token"
        }));
    }

    #[test]
    fn desktop_auth_server_requires_backend_login_token() {
        let config = json!({
            "mcpServers": {
                "runtime": {
                    "type": "http",
                    "url": "/mcp/runtime/mcp?project_id=proj-657fe77f",
                    "desktopAuth": true
                }
            }
        });
        let error = resolve_server_config(
            &config,
            "runtime",
            &json!({"_backend_api_base_url": "http://127.0.0.1:8000/api"}),
        )
        .unwrap_err();
        assert!(error.message.contains("requires backend login context"));
    }

    #[test]
    fn resolves_unique_dynamic_tool_route() {
        let route = unique_mcp_tool_route(
            vec![DiscoveredMcpTool {
                server: "runtime".to_string(),
                server_id: "system".to_string(),
                canonical_tool_id: "system.system.get_project_employee_detail".to_string(),
                domain: "system".to_string(),
                name: "get_project_employee_detail".to_string(),
                description: "detail".to_string(),
                input_schema: json!({"type": "object"}),
                annotations: McpToolAnnotations::default(),
            }],
            "get_project_employee_detail",
        )
        .unwrap()
        .unwrap();
        assert_eq!(route.server, "runtime");
    }

    #[test]
    fn rejects_dynamic_tool_name_conflict() {
        let tools = ["system-a", "system-b"]
            .into_iter()
            .map(|server_id| DiscoveredMcpTool {
                server: "runtime".to_string(),
                server_id: server_id.to_string(),
                canonical_tool_id: format!("system.{server_id}.query_project_members"),
                domain: "system".to_string(),
                name: "query_project_members".to_string(),
                description: String::new(),
                input_schema: json!({"type": "object"}),
                annotations: McpToolAnnotations::default(),
            })
            .collect();
        let error = unique_mcp_tool_route(tools, "query_project_members").unwrap_err();
        assert_eq!(error.code, "mcp.config_invalid");
        assert!(error.message.contains("multiple servers"));
    }

    #[test]
    fn parses_standard_mcp_tool_annotations() {
        let annotations = McpToolAnnotations::from_value(Some(&json!({
            "readOnlyHint": true,
            "destructiveHint": false,
            "idempotentHint": true,
            "openWorldHint": false
        })));
        assert!(annotations.is_read_only());
        assert_eq!(annotations.idempotent, Some(true));
        assert_eq!(annotations.open_world, Some(false));
    }

    #[test]
    fn read_only_dynamic_mcp_tool_does_not_require_approval() {
        let route = DiscoveredMcpTool {
            server: "runtime".to_string(),
            server_id: "system".to_string(),
            canonical_tool_id: "system.system.get_project_manual".to_string(),
            domain: "system".to_string(),
            name: "get_project_manual".to_string(),
            description: "manual".to_string(),
            input_schema: json!({"type": "object"}),
            annotations: McpToolAnnotations {
                read_only: Some(true),
                destructive: Some(false),
                idempotent: Some(true),
                open_world: Some(false),
            },
        };
        require_mcp_tool_approval("call-manual", &route, &json!({}), None).unwrap();
    }

    #[test]
    fn mutating_dynamic_mcp_tool_still_requires_approval() {
        let route = DiscoveredMcpTool {
            server: "runtime".to_string(),
            server_id: "system".to_string(),
            canonical_tool_id: "system.system.save_project_memory".to_string(),
            domain: "system".to_string(),
            name: "save_project_memory".to_string(),
            description: "save".to_string(),
            input_schema: json!({"type": "object"}),
            annotations: McpToolAnnotations {
                read_only: Some(false),
                destructive: Some(false),
                idempotent: Some(false),
                open_world: Some(false),
            },
        };
        let error = require_mcp_tool_approval("call-save", &route, &json!({}), None).unwrap_err();
        assert_eq!(error.code, "permission.required");
        assert!(error.message.contains("mcp.call"));
    }

    #[test]
    fn wire_tool_uses_runtime_catalog_identity() {
        let tool = DiscoveredMcpTool::from_wire_tool(
            "runtime",
            &json!({
                "name": "query_project_members",
                "description": "members",
                "inputSchema": {"type": "object"},
                "_meta": {
                    "domain": "system",
                    "server_id": "system",
                    "canonical_tool_id": "system.system.query_project_members"
                }
            }),
        )
        .unwrap();
        assert_eq!(tool.server, "runtime");
        assert_eq!(tool.server_id, "system");
        assert_eq!(
            tool.canonical_tool_id,
            "system.system.query_project_members"
        );
    }

    #[test]
    fn external_tool_keeps_independent_server_identity() {
        let tool = DiscoveredMcpTool::from_wire_tool(
            "runtime",
            &json!({
                "name": "external__feishu_prod__send_message",
                "description": "send",
                "inputSchema": {"type": "object"}
            }),
        )
        .unwrap();
        assert_eq!(tool.domain, "integrations");
        assert_eq!(tool.server_id, "feishu_prod");
        assert_eq!(
            tool.canonical_tool_id,
            "integrations.feishu_prod.external__feishu_prod__send_message"
        );
    }

    #[test]
    fn validates_required_mcp_arguments_before_call() {
        let route = DiscoveredMcpTool {
            server: "runtime".to_string(),
            server_id: "system".to_string(),
            canonical_tool_id: "system.system.get_project_employee_detail".to_string(),
            domain: "system".to_string(),
            name: "get_project_employee_detail".to_string(),
            description: "detail".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {"employee_id": {"type": "string"}},
                "required": ["employee_id"]
            }),
            annotations: McpToolAnnotations::default(),
        };
        let missing = validate_mcp_tool_arguments(&route, &json!({})).unwrap_err();
        assert_eq!(missing.code, "tool.schema_invalid");
        let wrong_type =
            validate_mcp_tool_arguments(&route, &json!({"employee_id": 123})).unwrap_err();
        assert_eq!(wrong_type.code, "tool.schema_invalid");
        validate_mcp_tool_arguments(&route, &json!({"employee_id": "emp-1"})).unwrap();
    }

    #[test]
    fn selects_only_goal_relevant_tools() {
        let tools = [
            ("query_project_members", "查询项目成员"),
            ("query_project_rules", "查询项目规则"),
            ("save_project_memory", "保存项目记忆"),
        ]
        .into_iter()
        .map(|(name, description)| DiscoveredMcpTool {
            server: "runtime".to_string(),
            server_id: "system".to_string(),
            canonical_tool_id: format!("system.system.{name}"),
            domain: "system".to_string(),
            name: name.to_string(),
            description: description.to_string(),
            input_schema: json!({"type": "object"}),
            annotations: McpToolAnnotations::default(),
        })
        .collect();
        let selected = select_mcp_tools_for_goal(tools, "当前项目绑定几个智能体", 8);
        assert_eq!(selected.len(), 1);
        assert_eq!(selected[0].name, "query_project_members");
    }

    #[test]
    fn selects_server_catalog_for_mcp_service_question() {
        let tools = ["list_runtime_mcp_servers", "query_project_members"]
            .into_iter()
            .map(|name| DiscoveredMcpTool {
                server: "runtime".to_string(),
                server_id: "system".to_string(),
                canonical_tool_id: format!("system.system.{name}"),
                domain: "system".to_string(),
                name: name.to_string(),
                description: name.to_string(),
                input_schema: json!({"type": "object"}),
                annotations: McpToolAnnotations::default(),
            })
            .collect();
        let selected = select_mcp_tools_for_goal(tools, "当前可用 MCP 服务有哪些", 8);
        assert_eq!(selected.len(), 1);
        assert_eq!(selected[0].name, "list_runtime_mcp_servers");
    }
}
