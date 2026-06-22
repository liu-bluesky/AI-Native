//! 本地 MCP adapter 委托。
//!
//! 桌面端不直接连接服务端 MCP，也不把本机 workspace 暴露给 Docker。这里读取
//! workspace 内 `.ai-employee/mcp-adapter/servers.json` 中声明的本地 adapter 命令，
//! 通过简化的 line-delimited JSON-RPC stdio 协议调用 MCP 方法。

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

const MCP_ADAPTER_CONFIG: &str = ".ai-employee/mcp-adapter/servers.json";
const MCP_ADAPTER_TIMEOUT_MS: u64 = 10_000;
const MAX_MCP_OUTPUT_CHARS: usize = 120_000;

pub fn list_mcp_tools(
    workspace_path: &str,
    arguments: &Value,
) -> Result<(Value, String), ToolError> {
    let server = string_arg(arguments, "server", "");
    let response = invoke_mcp_method(
        workspace_path,
        &server,
        "tools/list",
        json!({}),
        MCP_ADAPTER_TIMEOUT_MS,
    )?;
    let tools = response.get("tools").cloned().unwrap_or_else(|| json!([]));
    let count = tools.as_array().map(|items| items.len()).unwrap_or(0);
    Ok((
        json!({
            "server": resolved_server_name(&server),
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
        &server,
        "resources/read",
        json!({"uri": uri}),
        MCP_ADAPTER_TIMEOUT_MS,
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
        &format!("调用本地 MCP 工具：{server}/{tool}"),
        json!({
            "server": server,
            "tool": tool,
            "arguments_summary": summarize_json_value(&tool_arguments)
        }),
        permission_decision,
    )?;
    let response = invoke_mcp_method(
        workspace_path,
        &server,
        "tools/call",
        json!({
            "name": tool,
            "arguments": tool_arguments
        }),
        MCP_ADAPTER_TIMEOUT_MS,
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
    server: &str,
    method: &str,
    params: Value,
    timeout_ms: u64,
) -> Result<Value, ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let config = read_adapter_config(&root)?;
    let server_config = resolve_server_config(&config, server)?;
    let output = run_adapter_command(&root, &server_config, method, params, timeout_ms)?;
    parse_json_rpc_result(&output, 2)
}

struct ServerConfig {
    name: String,
    command: String,
    args: Vec<String>,
    cwd: String,
    framing: String,
}

fn read_adapter_config(root: &Path) -> Result<Value, ToolError> {
    let path = root.join(MCP_ADAPTER_CONFIG);
    let raw = fs::read_to_string(&path).map_err(|err| {
        ToolError::new(
            "mcp.adapter_missing",
            format!("read MCP adapter config failed: {err}"),
        )
    })?;
    serde_json::from_str::<Value>(&raw).map_err(|err| {
        ToolError::new(
            "mcp.config_invalid",
            format!("parse MCP adapter config failed: {err}"),
        )
    })
}

fn resolve_server_config(config: &Value, server: &str) -> Result<ServerConfig, ToolError> {
    let servers = config
        .get("servers")
        .or_else(|| config.get("mcpServers"))
        .ok_or_else(|| ToolError::new("mcp.config_invalid", "missing servers map"))?;
    let (name, value) = if server.trim().is_empty() {
        let object = servers
            .as_object()
            .ok_or_else(|| ToolError::new("mcp.config_invalid", "servers must be an object"))?;
        object
            .iter()
            .next()
            .map(|(name, value)| (name.to_string(), value))
            .ok_or_else(|| ToolError::new("mcp.config_invalid", "servers map is empty"))?
    } else {
        (
            server.trim().to_string(),
            servers.get(server.trim()).ok_or_else(|| {
                ToolError::new(
                    "mcp.server_not_found",
                    format!("MCP server not configured: {}", server.trim()),
                )
            })?,
        )
    };
    let command = value
        .get("command")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .ok_or_else(|| ToolError::new("mcp.config_invalid", "server.command is required"))?
        .to_string();
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
        .or_else(|| value.get("transport"))
        .and_then(Value::as_str)
        .unwrap_or("line-json")
        .trim()
        .to_ascii_lowercase();
    Ok(ServerConfig {
        name,
        command,
        args,
        cwd,
        framing,
    })
}

fn run_adapter_command(
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
                "mcp.adapter_failed",
                format!("spawn MCP adapter {} failed: {err}", server.name),
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
                    "mcp.adapter_failed",
                    format!("wait MCP adapter failed: {err}"),
                ));
            }
        }
    };
    let stdout = read_output_file(&stdout_path, MAX_MCP_OUTPUT_CHARS);
    let stderr = read_output_file(&stderr_path, 20_000);
    cleanup_temp_outputs(&stdout_path, &stderr_path);
    if timed_out {
        return Err(ToolError::new(
            "mcp.adapter_timeout",
            format!("MCP adapter timed out after {timeout_ms}ms"),
        ));
    }
    if exit_code != 0 && stdout.trim().is_empty() {
        return Err(ToolError::new(
            "mcp.adapter_failed",
            format!("MCP adapter exited with {exit_code}: {stderr}"),
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
                format!(
                    "MCP adapter returned error: {}",
                    summarize_json_value(error)
                ),
            ));
        }
        return Ok(value.get("result").cloned().unwrap_or_else(|| json!({})));
    }
    Err(ToolError::new(
        "mcp.failed",
        "MCP adapter did not return a matching JSON-RPC response",
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
    if matches!(framing, "content-length" | "mcp" | "standard") {
        write!(
            stdin,
            "Content-Length: {}\r\n\r\n{}",
            raw.as_bytes().len(),
            raw
        )
    } else {
        writeln!(stdin, "{raw}")
    }
    .map_err(|err| {
        ToolError::new(
            "mcp.adapter_failed",
            format!("write MCP stdin failed: {err}"),
        )
    })
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
            if header.len() > 8192 {
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

fn resolved_server_name(server: &str) -> String {
    if server.trim().is_empty() {
        "default".to_string()
    } else {
        server.trim().to_string()
    }
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
    fn writes_content_length_json_rpc_request() {
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
}
