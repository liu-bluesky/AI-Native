//! 本地网络工具。
//!
//! 网络请求由桌面端本机发起；禁止自动携带 Cookie、Authorization 等本地凭据。

use reqwest::blocking::{Client, Response};
use reqwest::header::{HeaderMap, HeaderName, HeaderValue};
use reqwest::Url;
use serde_json::{json, Value};
use std::fs;
use std::time::Duration;

use crate::liuagent_core::args::{bool_arg, number_arg, required_string_arg};
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};
use crate::liuagent_core::workspace::{
    resolve_workspace_root, resolve_workspace_write_target, workspace_relative_path,
};

const MAX_BODY_CHARS: usize = 80_000;
const MAX_DOWNLOAD_BYTES: usize = 20 * 1024 * 1024;

pub fn http_get(_workspace_path: &str, arguments: &Value) -> Result<(Value, String), ToolError> {
    let url = parse_http_url(&required_string_arg(arguments, "url")?)?;
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let headers = parse_headers(arguments.get("headers"))?;
    let response = request_client(timeout_ms)?
        .get(url.clone())
        .headers(headers)
        .send()
        .map_err(|err| {
            ToolError::new("tool.execution_failed", format!("http get failed: {err}"))
        })?;
    response_to_result("GET", url.as_str(), response)
}

pub fn http_post(
    tool_call_id: &str,
    _workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let url = parse_http_url(&required_string_arg(arguments, "url")?)?;
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let headers = parse_headers(arguments.get("headers"))?;
    let body = arguments
        .get("body")
        .ok_or_else(|| ToolError::new("tool.schema_invalid", "missing required argument: body"))?
        .clone();
    require_approval(
        tool_call_id,
        "network.write",
        "high",
        "network",
        &format!("发送 HTTP POST：{}", url.as_str()),
        json!({
            "url": url.as_str(),
            "body_summary": summarize_json_value(&body),
            "timeout_ms": timeout_ms
        }),
        permission_decision,
    )?;

    let response = request_client(timeout_ms)?
        .post(url.clone())
        .headers(headers)
        .json(&body)
        .send()
        .map_err(|err| {
            ToolError::new("tool.execution_failed", format!("http post failed: {err}"))
        })?;
    response_to_result("POST", url.as_str(), response)
}

pub fn download_file(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let url = parse_http_url(&required_string_arg(arguments, "url")?)?;
    let dest_path = required_string_arg(arguments, "dest_path")?;
    let overwrite = bool_arg(arguments, "overwrite", false);
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let target = resolve_workspace_write_target(&root, &dest_path)?;
    let exists = target.exists();
    if exists && !target.is_file() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "dest_path is not a file",
        ));
    }
    if exists && !overwrite {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "file already exists; set overwrite=true to replace it",
        ));
    }
    let relative_path = workspace_relative_path(&root, &target);
    require_approval(
        tool_call_id,
        "network.read",
        if exists { "high" } else { "medium" },
        "workspace",
        &format!("下载文件到 {relative_path}"),
        json!({
            "url": url.as_str(),
            "dest_path": relative_path,
            "overwrite": overwrite,
            "exists": exists,
            "timeout_ms": timeout_ms
        }),
        permission_decision,
    )?;

    let response = request_client(timeout_ms)?
        .get(url.clone())
        .send()
        .map_err(|err| {
            ToolError::new("tool.execution_failed", format!("download failed: {err}"))
        })?;
    let status = response.status().as_u16();
    let content_type = response
        .headers()
        .get("content-type")
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
        .to_string();
    if !response.status().is_success() {
        return Err(ToolError::new(
            "tool.execution_failed",
            format!("download failed with http status {status}"),
        ));
    }
    let bytes = response.bytes().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read download failed: {err}"),
        )
    })?;
    if bytes.len() > MAX_DOWNLOAD_BYTES {
        return Err(ToolError::new(
            "tool.output_too_large",
            format!("download is larger than {} bytes", MAX_DOWNLOAD_BYTES),
        ));
    }
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            ToolError::new("tool.execution_failed", format!("create dir failed: {err}"))
        })?;
    }
    fs::write(&target, &bytes).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("write download failed: {err}"),
        )
    })?;
    let summary = format!("下载 {} 字节到 {}", bytes.len(), relative_path);
    Ok((
        json!({
            "dest_path": relative_path,
            "bytes": bytes.len(),
            "content_type": content_type,
            "status": status
        }),
        summary,
    ))
}

fn request_client(timeout_ms: u64) -> Result<Client, ToolError> {
    Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create http client failed: {err}"),
            )
        })
}

fn parse_http_url(raw: &str) -> Result<Url, ToolError> {
    let url = Url::parse(raw.trim())
        .map_err(|err| ToolError::new("tool.schema_invalid", format!("invalid url: {err}")))?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "only http and https urls are allowed",
        ));
    }
    Ok(url)
}

fn parse_headers(value: Option<&Value>) -> Result<HeaderMap, ToolError> {
    let mut headers = HeaderMap::new();
    let Some(Value::Object(map)) = value else {
        return Ok(headers);
    };
    for (key, value) in map {
        if is_sensitive_header(key) {
            return Err(ToolError::new(
                "tool.schema_invalid",
                format!("sensitive header is not allowed: {key}"),
            ));
        }
        let Some(raw_value) = value.as_str() else {
            return Err(ToolError::new(
                "tool.schema_invalid",
                format!("header value must be string: {key}"),
            ));
        };
        let name = HeaderName::from_bytes(key.as_bytes()).map_err(|err| {
            ToolError::new("tool.schema_invalid", format!("invalid header name: {err}"))
        })?;
        let header_value = HeaderValue::from_str(raw_value).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid header value: {err}"),
            )
        })?;
        headers.insert(name, header_value);
    }
    Ok(headers)
}

fn response_to_result(
    method: &str,
    url: &str,
    response: Response,
) -> Result<(Value, String), ToolError> {
    let status = response.status().as_u16();
    let headers = safe_response_headers(response.headers());
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read response failed: {err}"),
        )
    })?;
    let (body, truncated) = truncate_chars(&text, MAX_BODY_CHARS);
    let summary = format!(
        "{method} {url} -> HTTP {status}{}",
        if truncated { "（已截断）" } else { "" }
    );
    Ok((
        json!({
            "status": status,
            "headers": headers,
            "body": body,
            "truncated": truncated
        }),
        summary,
    ))
}

fn safe_response_headers(headers: &HeaderMap) -> Value {
    let mut result = serde_json::Map::new();
    for key in [
        "content-type",
        "content-length",
        "etag",
        "last-modified",
        "cache-control",
    ] {
        if let Some(value) = headers.get(key).and_then(|item| item.to_str().ok()) {
            result.insert(key.to_string(), json!(value));
        }
    }
    Value::Object(result)
}

fn is_sensitive_header(key: &str) -> bool {
    matches!(
        key.to_ascii_lowercase().as_str(),
        "authorization"
            | "cookie"
            | "set-cookie"
            | "proxy-authorization"
            | "x-api-key"
            | "x-auth-token"
    )
}

fn summarize_json_value(value: &Value) -> Value {
    match value {
        Value::String(text) => json!({"type": "string", "chars": text.chars().count()}),
        Value::Array(items) => json!({"type": "array", "items": items.len()}),
        Value::Object(map) => {
            json!({"type": "object", "keys": map.keys().cloned().collect::<Vec<_>>() })
        }
        Value::Null => json!({"type": "null"}),
        Value::Bool(_) => json!({"type": "boolean"}),
        Value::Number(_) => json!({"type": "number"}),
    }
}

fn truncate_chars(value: &str, max_chars: usize) -> (String, bool) {
    if value.chars().count() <= max_chars {
        return (value.to_string(), false);
    }
    (value.chars().take(max_chars).collect(), true)
}
