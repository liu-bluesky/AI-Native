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
    let tool_arguments = arguments
        .get("arguments")
        .filter(|value| value.is_object())
        .cloned()
        .unwrap_or_else(|| json!({}));
    require_approval(
        tool_call_id,
        "mcp.call",
        "medium",
        "project",
        &format!("调用 MCP 工具：{server}/{tool}"),
        json!({
            "server": server,
            "tool": tool,
            "arguments_summary": summarize_json_value(&tool_arguments)
        }),
        permission_decision,
    )?;
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
    Ok(ServerConfig {
        name,
        transport,
        command,
        args,
        cwd,
        framing,
        url,
        headers: parse_config_headers(&value)?,
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
}
