#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc, Mutex,
};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
#[cfg(debug_assertions)]
use tauri::menu::{Menu, MenuItem, Submenu};
use tauri::{Emitter, Manager};
use tauri_plugin_updater::UpdaterExt;
use url::Url;

mod bot;
mod liuagent_core;
mod project_chat_store;

#[derive(Debug, Serialize)]
struct PickPathResult {
    cancelled: bool,
    path: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ClipboardFileResult {
    copied: bool,
    path: String,
    name: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SavedResourceFileResult {
    saved: bool,
    cancelled: bool,
    path: String,
    name: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct PersistedProjectChatAssetResult {
    asset_id: String,
    kind: String,
    mime_type: String,
    bytes: u64,
    name: String,
    local_path: String,
    source_url: String,
    source_tool: String,
    message_id: String,
    created_at: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LocalFileReadResult {
    name: String,
    mime_type: String,
    size: u64,
    bytes: Vec<u8>,
}

#[derive(Debug, Serialize)]
struct ExecutorStatus {
    installed: bool,
    available: bool,
    path: String,
    version: String,
    reason: String,
}

#[derive(Debug, Serialize)]
struct WorkspaceStatus {
    configured: bool,
    exists: bool,
    is_directory: bool,
    path: String,
}

#[derive(Debug, Serialize)]
struct ExecutorDetectionResult {
    codex: ExecutorStatus,
    hermes: ExecutorStatus,
    #[serde(rename = "claudeCode")]
    claude_code: ExecutorStatus,
    workspace: WorkspaceStatus,
}

#[derive(Debug, Serialize)]
struct RuntimeInfo {
    platform: String,
    arch: String,
    desktop_bridge_version: String,
    install_dir: String,
    default_workspace_path: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkspaceFileItem {
    name: String,
    path: String,
    kind: String,
    size: u64,
    modified_at_epoch_ms: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkspaceFileListResult {
    root: String,
    path: String,
    items: Vec<WorkspaceFileItem>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkspaceFileReadResult {
    root: String,
    path: String,
    name: String,
    size: u64,
    modified_at_epoch_ms: u64,
    encoding: String,
    content: String,
    content_hash: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkspaceDiffPreviewResult {
    root: String,
    path: String,
    available: bool,
    summary: String,
    diff: String,
    status: String,
    exit_code: i32,
    truncated: bool,
    reason: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkspaceFileWritePreparation {
    root: String,
    path: String,
    exists: bool,
    current_size: u64,
    next_size: u64,
    current_line_count: usize,
    next_line_count: usize,
    changed: bool,
    risk_level: String,
    requires_approval: bool,
    summary: String,
    reason: String,
    current_hash: String,
    next_hash: String,
    modified_at_epoch_ms: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkspaceFileWriteResult {
    root: String,
    path: String,
    size: u64,
    modified_at_epoch_ms: u64,
    previous_hash: String,
    content_hash: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct McpConfigFileResult {
    scope: String,
    path: String,
    exists: bool,
    content: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct WebToolsConfigFileResult {
    scope: String,
    path: String,
    exists: bool,
    content: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RunnerCommandClassification {
    allowed: bool,
    risk_level: String,
    requires_approval: bool,
    command: String,
    args: Vec<String>,
    workspace_path: String,
    blocked_reason: String,
    summary: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RunnerCommandResult {
    allowed: bool,
    risk_level: String,
    requires_approval: bool,
    command: String,
    args: Vec<String>,
    workspace_path: String,
    stdout: String,
    stderr: String,
    exit_code: i32,
    duration_ms: u128,
    timed_out: bool,
    blocked_reason: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RunnerPermissionDecisionInput {
    decision_id: Option<String>,
    command: String,
    args: Option<Vec<String>>,
    workspace_path: Option<String>,
    decision: String,
    reason: Option<String>,
    scope: Option<String>,
    source: Option<String>,
    risk_level: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct RunnerPermissionDecisionRecord {
    decision_id: String,
    command: String,
    args: Vec<String>,
    workspace_path: String,
    decision: String,
    reason: String,
    scope: String,
    source: String,
    risk_level: String,
    created_at_epoch_ms: u64,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderModelDiscoveryRequest {
    provider_type: Option<String>,
    base_url: String,
    api_key: String,
    extra_headers: Option<std::collections::HashMap<String, String>>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProviderModelDiscoveryResult {
    models: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderModelTestRequest {
    provider_type: String,
    base_url: String,
    api_key: String,
    model_name: String,
    model_type: Option<String>,
    extra_headers: Option<std::collections::HashMap<String, String>>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProviderModelTestResult {
    reachable: bool,
    model_tested: String,
    request_url: String,
    http_status: Option<u16>,
    model_type: String,
    artifacts: Vec<Value>,
    message: String,
}

const DESKTOP_UPDATE_PUBLIC_KEY: &str = "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDQxMUQ3NjhBMEYzMjI3RTIKUldUaUp6SVBpbllkUVNNdzVwVmFuZ1dmV2xFdzc1amtiWE9LTEFOeUI4aVBDalBUZ1Y2b1VnSEYK";
const DESKTOP_UPDATE_PROGRESS_EVENT: &str = "desktop-update-progress";

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DesktopUpdateMetadata {
    version: String,
    current_version: String,
    notes: String,
    pub_date: Option<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct DesktopUpdateProgress {
    downloaded: u64,
    content_length: Option<u64>,
    finished: bool,
}

fn desktop_update_endpoint(value: &str) -> Result<Url, String> {
    let endpoint = value.trim();
    if endpoint.is_empty() {
        return Err("版本更新地址未配置".to_string());
    }
    let separator = if endpoint.contains('?') {
        if endpoint.ends_with('?') || endpoint.ends_with('&') {
            ""
        } else {
            "&"
        }
    } else {
        "?"
    };
    let endpoint = format!(
        "{endpoint}{separator}target={{{{target}}}}&arch={{{{arch}}}}&bundle_type={{{{bundle_type}}}}"
    );
    let parsed = Url::parse(&endpoint).map_err(|error| format!("版本更新地址无效：{error}"))?;
    if !matches!(parsed.scheme(), "http" | "https")
        || parsed.username() != ""
        || parsed.password().is_some()
        || parsed.fragment().is_some()
    {
        return Err("版本更新地址必须是 HTTP 或 HTTPS 地址，且不能包含账号密码和片段".to_string());
    }
    Ok(parsed)
}

fn desktop_update_metadata(update: &tauri_plugin_updater::Update) -> DesktopUpdateMetadata {
    DesktopUpdateMetadata {
        version: update.version.clone(),
        current_version: update.current_version.clone(),
        notes: update.body.clone().unwrap_or_default(),
        pub_date: update.date.as_ref().map(ToString::to_string),
    }
}

#[tauri::command]
fn get_desktop_version(app: tauri::AppHandle) -> String {
    app.package_info().version.to_string()
}

#[tauri::command]
async fn check_desktop_update(
    app: tauri::AppHandle,
    endpoint: String,
) -> Result<Option<DesktopUpdateMetadata>, String> {
    let endpoint = desktop_update_endpoint(&endpoint)?;
    let update = app
        .updater_builder()
        .endpoints(vec![endpoint])
        .map_err(|error| format!("构建版本更新请求失败：{error}"))?
        .build()
        .map_err(|error| format!("初始化版本更新失败：{error}"))?
        .check()
        .await
        .map_err(|error| format!("检查版本更新失败：{error}"))?;
    Ok(update.as_ref().map(desktop_update_metadata))
}

#[tauri::command]
async fn install_desktop_update(app: tauri::AppHandle, endpoint: String) -> Result<(), String> {
    let endpoint = desktop_update_endpoint(&endpoint)?;
    let update = app
        .updater_builder()
        .endpoints(vec![endpoint])
        .map_err(|error| format!("构建版本更新请求失败：{error}"))?
        .build()
        .map_err(|error| format!("初始化版本更新失败：{error}"))?
        .check()
        .await
        .map_err(|error| format!("确认版本更新失败：{error}"))?
        .ok_or_else(|| "版本更新已不存在或当前版本已经是最新版本".to_string())?;

    let progress_app = app.clone();
    let downloaded = Arc::new(AtomicU64::new(0));
    let progress_downloaded = Arc::clone(&downloaded);
    let finished_downloaded = Arc::clone(&downloaded);
    update
        .download_and_install(
            |chunk_length, content_length| {
                let downloaded = progress_downloaded
                    .fetch_add(chunk_length as u64, Ordering::Relaxed)
                    .saturating_add(chunk_length as u64);
                let _ = progress_app.emit(
                    DESKTOP_UPDATE_PROGRESS_EVENT,
                    DesktopUpdateProgress {
                        downloaded,
                        content_length,
                        finished: false,
                    },
                );
            },
            || {
                let _ = progress_app.emit(
                    DESKTOP_UPDATE_PROGRESS_EVENT,
                    DesktopUpdateProgress {
                        downloaded: finished_downloaded.load(Ordering::Relaxed),
                        content_length: None,
                        finished: true,
                    },
                );
            },
        )
        .await
        .map_err(|error| format!("下载或安装版本更新失败：{error}"))?;

    app.request_restart();
    Ok(())
}

#[tauri::command]
async fn discover_provider_models(
    request: ProviderModelDiscoveryRequest,
) -> Result<ProviderModelDiscoveryResult, String> {
    tauri::async_runtime::spawn_blocking(move || discover_provider_models_with_http(request))
        .await
        .map_err(|error| format!("模型发现任务执行失败：{error}"))?
}

fn discover_provider_models_with_http(
    request: ProviderModelDiscoveryRequest,
) -> Result<ProviderModelDiscoveryResult, String> {
    let base_url = request.base_url.trim().trim_end_matches('/');
    if base_url.is_empty() {
        return Err("请填写 Base URL".to_string());
    }
    let provider_type = request
        .provider_type
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();

    // 模型列表端点候选：不同供应商的 /models 可能位于根路径或 /v1 前缀下。
    // 按顺序尝试，遇到 4xx 时回退到下一个候选，直到成功或全部失败。
    let mut candidates: Vec<String> = vec![format!("{base_url}/models")];
    if provider_type != "custom" {
        candidates.push(format!("{base_url}/v1/models"));
    }
    candidates.sort();
    candidates.dedup();

    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|error| format!("创建模型发现客户端失败：{error}"))?;

    let extra_headers = request.extra_headers.unwrap_or_default();
    let mut last_error: Option<String> = None;

    for models_url in candidates {
        let parsed_url =
            reqwest::Url::parse(&models_url).map_err(|error| format!("Base URL 无效：{error}"))?;
        if !matches!(parsed_url.scheme(), "http" | "https") {
            return Err("Base URL 只支持 http 或 https".to_string());
        }

        let mut http_request = client.get(parsed_url);
        if !request.api_key.trim().is_empty() {
            http_request = http_request.bearer_auth(request.api_key.trim());
        }
        for (name, value) in &extra_headers {
            let header_name = reqwest::header::HeaderName::from_bytes(name.trim().as_bytes())
                .map_err(|_| format!("额外请求头名称无效：{}", name.trim()))?;
            let header_value = reqwest::header::HeaderValue::from_str(value.trim())
                .map_err(|_| format!("额外请求头值无效：{}", name.trim()))?;
            http_request = http_request.header(header_name, header_value);
        }

        let response = match http_request.send() {
            Ok(response) => response,
            Err(error) => {
                last_error = Some(format!("请求供应商模型列表失败（{models_url}）：{error}"));
                continue;
            }
        };
        let status = response.status();
        let body = match response.text() {
            Ok(body) => body,
            Err(error) => {
                last_error = Some(format!(
                    "读取供应商模型列表响应失败（{models_url}）：{error}"
                ));
                continue;
            }
        };
        if !status.is_success() {
            let detail = body.chars().take(500).collect::<String>();
            last_error = Some(format!(
                "供应商模型列表请求失败（{models_url}，HTTP {status}）：{detail}"
            ));
            // 仅对客户端/资源错误（4xx）回退到下一个端点候选；
            // 5xx 或鉴权失败通常不会因换路径而好转，直接停止。
            if !status.is_client_error() {
                break;
            }
            continue;
        }

        let payload: Value = match serde_json::from_str(&body) {
            Ok(payload) => payload,
            Err(error) => {
                last_error = Some(format!("供应商模型列表响应不是有效 JSON：{error}"));
                continue;
            }
        };
        let items = payload
            .get("data")
            .or_else(|| payload.get("models"))
            .and_then(Value::as_array);
        let Some(items) = items else {
            last_error = Some("供应商模型列表响应缺少 data 或 models 数组".to_string());
            continue;
        };
        let models = items
            .iter()
            .filter_map(|item| match item {
                Value::String(value) => Some(value.trim().to_string()),
                Value::Object(_) => item
                    .get("id")
                    .or_else(|| item.get("name"))
                    .or_else(|| item.get("model"))
                    .and_then(Value::as_str)
                    .map(|value| value.trim().to_string()),
                _ => None,
            })
            .filter(|value| !value.is_empty())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        return Ok(ProviderModelDiscoveryResult { models });
    }

    Err(last_error.unwrap_or_else(|| "供应商模型列表请求失败".to_string()))
}

#[tauri::command]
async fn test_provider_model(
    request: ProviderModelTestRequest,
) -> Result<ProviderModelTestResult, String> {
    tauri::async_runtime::spawn_blocking(move || test_provider_model_with_http(request))
        .await
        .map_err(|error| format!("模型测试任务执行失败：{error}"))?
}

fn test_provider_model_with_http(
    request: ProviderModelTestRequest,
) -> Result<ProviderModelTestResult, String> {
    let base_url = request.base_url.trim().trim_end_matches('/');
    let model_name = request.model_name.trim();
    if base_url.is_empty() || model_name.is_empty() {
        return Err("测试模型需要 Base URL 和模型名称".to_string());
    }
    let model_type = request
        .model_type
        .as_deref()
        .unwrap_or("text_generation")
        .trim()
        .to_ascii_lowercase();
    let is_responses = request
        .provider_type
        .trim()
        .eq_ignore_ascii_case("responses");
    let is_image_generation = model_type == "image_generation";
    let path = if is_image_generation {
        "/images/generations"
    } else if is_responses {
        "/responses"
    } else {
        "/chat/completions"
    };
    let request_url = format!("{base_url}{path}");
    let parsed_url =
        reqwest::Url::parse(&request_url).map_err(|error| format!("模型测试地址无效：{error}"))?;
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(45))
        .build()
        .map_err(|error| format!("创建模型测试客户端失败：{error}"))?;
    let body = if is_image_generation {
        json!({
            "model": model_name,
            "prompt": "请生成一张简单的测试图片",
            "size": "1024x1024",
            "n": 1,
        })
    } else if is_responses {
        json!({
            "model": model_name,
            "input": "请只回复：连接测试成功",
            "max_output_tokens": 32,
        })
    } else {
        json!({
            "model": model_name,
            "messages": [{"role": "user", "content": "请只回复：连接测试成功"}],
            "max_tokens": 32,
            "temperature": 0,
        })
    };
    let mut http_request = client.post(parsed_url).json(&body);
    if !request.api_key.trim().is_empty() {
        http_request = http_request.bearer_auth(request.api_key.trim());
    }
    for (name, value) in request.extra_headers.unwrap_or_default() {
        let header_name = reqwest::header::HeaderName::from_bytes(name.trim().as_bytes())
            .map_err(|_| format!("额外请求头名称无效：{}", name.trim()))?;
        let header_value = reqwest::header::HeaderValue::from_str(value.trim())
            .map_err(|_| format!("额外请求头值无效：{}", name.trim()))?;
        http_request = http_request.header(header_name, header_value);
    }
    let response = match http_request.send() {
        Ok(response) => response,
        Err(error) => {
            return Ok(ProviderModelTestResult {
                reachable: false,
                model_tested: model_name.to_string(),
                request_url,
                http_status: None,
                model_type: model_type.clone(),
                artifacts: Vec::new(),
                message: format!("请求模型测试接口失败：{error}"),
            });
        }
    };
    let status = response.status();
    let response_body = response.text().map_err(|error| {
        format!("读取模型测试响应失败（请求地址：{request_url}，HTTP {status}）：{error}")
    })?;
    if !status.is_success() {
        let detail = response_body.chars().take(500).collect::<String>();
        return Ok(ProviderModelTestResult {
            reachable: false,
            model_tested: model_name.to_string(),
            request_url,
            http_status: Some(status.as_u16()),
            model_type: model_type.clone(),
            artifacts: Vec::new(),
            message: format!("模型测试失败（HTTP {status}）：{detail}"),
        });
    }
    let payload: Value = serde_json::from_str(&response_body).map_err(|error| {
        format!("模型测试响应不是有效 JSON（请求地址：{request_url}，HTTP {status}）：{error}")
    })?;
    let has_output = if is_image_generation {
        payload
            .get("data")
            .and_then(Value::as_array)
            .map(|items| !items.is_empty())
            .unwrap_or(false)
            || payload
                .get("images")
                .and_then(Value::as_array)
                .map(|items| !items.is_empty())
                .unwrap_or(false)
            || payload
                .get("candidates")
                .and_then(Value::as_array)
                .map(|items| !items.is_empty())
                .unwrap_or(false)
    } else if is_responses {
        payload
            .get("output")
            .and_then(Value::as_array)
            .map(|items| !items.is_empty())
            .unwrap_or(false)
            || payload
                .get("output_text")
                .and_then(Value::as_str)
                .map(|text| !text.trim().is_empty())
                .unwrap_or(false)
    } else {
        payload
            .get("choices")
            .and_then(Value::as_array)
            .map(|items| !items.is_empty())
            .unwrap_or(false)
    };
    if !has_output {
        return Err("模型测试请求成功，但响应中没有可用输出".to_string());
    }
    let artifacts = if is_image_generation {
        extract_image_test_artifacts(&payload)
    } else {
        Vec::new()
    };
    Ok(ProviderModelTestResult {
        reachable: true,
        model_tested: model_name.to_string(),
        request_url,
        http_status: Some(status.as_u16()),
        model_type,
        artifacts,
        message: "模型真实调用成功".to_string(),
    })
}

fn extract_image_test_artifacts(payload: &Value) -> Vec<Value> {
    let mut artifacts = Vec::new();
    if let Some(items) = payload.get("data").and_then(Value::as_array) {
        for item in items {
            if let Some(url) = item
                .get("url")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
            {
                artifacts.push(json!({
                    "asset_type": "image",
                    "content_url": url,
                    "preview_url": url,
                    "title": "图片模型测试结果",
                }));
            } else if let Some(encoded) = item
                .get("b64_json")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
            {
                artifacts.push(json!({
                    "asset_type": "image",
                    "content_url": format!("data:image/png;base64,{encoded}"),
                    "preview_url": format!("data:image/png;base64,{encoded}"),
                    "title": "图片模型测试结果",
                }));
            }
        }
    }
    if let Some(candidates) = payload.get("candidates").and_then(Value::as_array) {
        for candidate in candidates {
            let parts = candidate
                .get("content")
                .and_then(|content| content.get("parts"))
                .and_then(Value::as_array);
            if let Some(parts) = parts {
                for part in parts {
                    let inline_data = part.get("inlineData").or_else(|| part.get("inline_data"));
                    let Some(inline_data) = inline_data else {
                        continue;
                    };
                    let Some(encoded) = inline_data
                        .get("data")
                        .and_then(Value::as_str)
                        .filter(|value| !value.trim().is_empty())
                    else {
                        continue;
                    };
                    let mime_type = inline_data
                        .get("mimeType")
                        .or_else(|| inline_data.get("mime_type"))
                        .and_then(Value::as_str)
                        .filter(|value| !value.trim().is_empty())
                        .unwrap_or("image/png");
                    artifacts.push(json!({
                        "asset_type": "image",
                        "content_url": format!("data:{mime_type};base64,{encoded}"),
                        "preview_url": format!("data:{mime_type};base64,{encoded}"),
                        "title": "图片模型测试结果",
                    }));
                }
            }
        }
    }
    artifacts
}

#[tauri::command]
fn liuagent_builtin_tool_definitions() -> Vec<liuagent_core::ToolDefinition> {
    liuagent_core::builtin_tool_definitions()
}

#[tauri::command]
fn liuagent_execute_tool(
    request: liuagent_core::ToolExecutionRequest,
) -> liuagent_core::ToolExecutionResult {
    liuagent_core::execute_tool(request)
}

#[tauri::command]
async fn liuagent_upload_provider_file(
    request: liuagent_core::ProviderFileUploadRequest,
) -> liuagent_core::ProviderFileUploadResult {
    let fallback_request = liuagent_core::ProviderFileUploadRequest {
        provider_id: request.provider_id.clone(),
        base_url: request.base_url.clone(),
        api_key: request.api_key.clone(),
        filename: request.filename.clone(),
        mime_type: request.mime_type.clone(),
        purpose: request.purpose.clone(),
        file_bytes: Vec::new(),
        timeout_ms: request.timeout_ms,
    };
    match tauri::async_runtime::spawn_blocking(move || liuagent_core::upload_provider_file(request))
        .await
    {
        Ok(result) => result,
        Err(error) => liuagent_core::ProviderFileUploadResult::failed(
            fallback_request,
            liuagent_core::ToolError::new(
                "runtime.join_failed",
                format!("provider file upload worker failed: {error}"),
            ),
        ),
    }
}

#[tauri::command]
async fn liuagent_start_local_chat(
    app: tauri::AppHandle,
    request: liuagent_core::LocalChatRequest,
) -> liuagent_core::LocalChatResult {
    let chat_session_id = request.chat_session_id.trim().to_string();
    if !liuagent_core::try_begin_local_chat_run(&chat_session_id) {
        return liuagent_core::LocalChatResult::failed(
            chat_session_id,
            liuagent_core::ToolError::new(
                "runtime.already_running",
                "该聊天会话仍有本地 Runtime 在运行或正在停止，请等待其完成后再继续。",
            ),
        );
    }
    liuagent_core::prepare_local_chat_run(&chat_session_id);
    let live_events = Arc::new(Mutex::new(Vec::new()));
    let live_events_for_worker = Arc::clone(&live_events);
    let result = match tauri::async_runtime::spawn_blocking(move || {
        liuagent_core::start_local_chat_with_event_sink(request, |event| {
            if let Ok(mut events) = live_events_for_worker.lock() {
                events.push(event.clone());
            }
            let _ = app.emit("liuagent-runtime-event", event.clone());
            let _ = app.emit("liuagent://runtime-event", event);
        })
    })
    .await
    {
        Ok(mut result) => {
            if let Ok(events) = live_events.lock() {
                for event in events.iter() {
                    let event_id = event
                        .get("event_id")
                        .and_then(serde_json::Value::as_str)
                        .unwrap_or("");
                    let already_present = !event_id.is_empty()
                        && result.runtime_events.iter().any(|existing| {
                            existing
                                .get("event_id")
                                .and_then(serde_json::Value::as_str)
                                .map(|value| value == event_id)
                                .unwrap_or(false)
                        });
                    if !already_present {
                        result.runtime_events.push(event.clone());
                    }
                }
            }
            result
        }
        Err(error) => liuagent_core::LocalChatResult::failed(
            chat_session_id.clone(),
            liuagent_core::ToolError::new(
                "runtime.join_failed",
                format!("local chat worker failed: {error}"),
            ),
        ),
    };
    liuagent_core::finish_local_chat_run(&chat_session_id);
    result
}

#[tauri::command]
fn liuagent_pause_local_chat(request: liuagent_core::LocalChatPauseRequest) -> bool {
    liuagent_core::request_local_chat_pause(request)
}

#[tauri::command]
async fn liuagent_classify_permission_reply(
    request: liuagent_core::LocalChatRequest,
) -> liuagent_core::LocalPermissionReplyResult {
    match tauri::async_runtime::spawn_blocking(move || {
        liuagent_core::classify_local_permission_reply(request)
    })
    .await
    {
        Ok(result) => result,
        Err(error) => {
            liuagent_core::LocalPermissionReplyResult::failed(liuagent_core::ToolError::new(
                "runtime.join_failed",
                format!("permission reply classifier worker failed: {error}"),
            ))
        }
    }
}

#[tauri::command]
fn bot_start_feishu_local_listener(
    app: tauri::AppHandle,
    request: bot::feishu::FeishuLocalListenerStartRequest,
) -> Result<bot::feishu::FeishuLocalListenerStatus, String> {
    bot::feishu::start_local_listener(app, request)
}

#[tauri::command]
fn bot_stop_feishu_local_listener(
    connector_id: String,
) -> Result<bot::feishu::FeishuLocalListenerStatus, String> {
    bot::feishu::stop_local_listener(connector_id)
}

#[tauri::command]
fn bot_list_feishu_local_listeners() -> Vec<bot::feishu::FeishuLocalListenerStatus> {
    bot::feishu::list_local_listeners()
}

#[tauri::command]
fn bot_scan_feishu_chats(
    request: bot::feishu::FeishuChatScanRequest,
) -> Result<bot::feishu::FeishuChatScanResult, String> {
    bot::feishu::scan_chats(request)
}

#[tauri::command]
fn liuagent_prepare_agent_invocation(
    request: liuagent_core::AgentInvocationRequest,
) -> liuagent_core::AgentInvocationResult {
    liuagent_core::prepare_agent_invocation(request)
}

#[tauri::command]
fn liuagent_recover_runtime_state(
    request: liuagent_core::LocalRuntimeRecoveryRequest,
) -> liuagent_core::LocalRuntimeRecoveryResult {
    liuagent_core::recover_local_runtime_state(request)
}

#[tauri::command]
fn liuagent_refresh_runtime_job(
    request: liuagent_core::LocalRuntimeJobRequest,
) -> liuagent_core::LocalRuntimeJobResult {
    liuagent_core::refresh_local_runtime_job(request)
}

#[tauri::command]
fn liuagent_cancel_runtime_job(
    request: liuagent_core::LocalRuntimeJobRequest,
) -> liuagent_core::LocalRuntimeJobResult {
    liuagent_core::cancel_local_runtime_job(request)
}

#[tauri::command]
fn liuagent_list_runtime_events(
    request: liuagent_core::LocalRuntimeEventsRequest,
) -> liuagent_core::LocalRuntimeEventsResult {
    liuagent_core::list_local_runtime_events(request)
}

#[tauri::command]
fn liuagent_list_runtime_outbox(
    request: liuagent_core::LocalRuntimeOutboxRequest,
) -> liuagent_core::LocalRuntimeOutboxResult {
    liuagent_core::list_local_runtime_outbox(request)
}

#[tauri::command]
fn liuagent_ack_runtime_outbox(
    request: liuagent_core::LocalRuntimeOutboxAckRequest,
) -> liuagent_core::LocalRuntimeOutboxResult {
    liuagent_core::ack_local_runtime_outbox(request)
}

#[tauri::command]
fn liuagent_save_offline_cache(
    request: liuagent_core::OfflineCacheSaveRequest,
) -> liuagent_core::OfflineCacheResult {
    liuagent_core::save_local_offline_cache(request)
}

#[tauri::command]
fn liuagent_load_offline_cache(
    request: liuagent_core::OfflineCacheLoadRequest,
) -> liuagent_core::OfflineCacheResult {
    liuagent_core::load_local_offline_cache(request)
}

#[tauri::command]
fn liuagent_cleanup_offline_cache(
    request: liuagent_core::OfflineCacheCleanupRequest,
) -> liuagent_core::OfflineCacheResult {
    liuagent_core::cleanup_local_offline_cache(request)
}

#[tauri::command]
fn pick_workspace_directory(title: Option<String>, initial_path: Option<String>) -> PickPathResult {
    let mut dialog = rfd::FileDialog::new();
    if let Some(title) = title.filter(|value| !value.trim().is_empty()) {
        dialog = dialog.set_title(title);
    }
    if let Some(initial_path) = initial_path.filter(|value| !value.trim().is_empty()) {
        dialog = dialog.set_directory(initial_path);
    }
    match dialog.pick_folder() {
        Some(path) => PickPathResult {
            cancelled: false,
            path: path.to_string_lossy().to_string(),
        },
        None => PickPathResult {
            cancelled: true,
            path: String::new(),
        },
    }
}

#[tauri::command]
fn detect_executors(workspace_path: Option<String>) -> ExecutorDetectionResult {
    let workspace_path = workspace_path.unwrap_or_default().trim().to_string();
    let workspace_meta = if workspace_path.is_empty() {
        None
    } else {
        fs::metadata(&workspace_path).ok()
    };

    ExecutorDetectionResult {
        codex: detect_executor("codex"),
        hermes: detect_executor("hermes"),
        claude_code: detect_executor("claude"),
        workspace: WorkspaceStatus {
            configured: !workspace_path.is_empty(),
            exists: workspace_meta.is_some(),
            is_directory: workspace_meta
                .as_ref()
                .map(|metadata| metadata.is_dir())
                .unwrap_or(false),
            path: workspace_path,
        },
    }
}

#[tauri::command]
fn get_runtime_info() -> RuntimeInfo {
    let install_dir = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|parent| parent.to_path_buf()))
        .map(|path| path.to_string_lossy().to_string())
        .unwrap_or_default();
    let default_workspace_path = default_runner_workspace_path();
    let _ = fs::create_dir_all(&default_workspace_path);
    RuntimeInfo {
        platform: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
        desktop_bridge_version: "0.1.0".to_string(),
        install_dir,
        default_workspace_path: default_workspace_path.to_string_lossy().to_string(),
    }
}

fn default_runner_workspace_path() -> PathBuf {
    let base = if cfg!(target_os = "macos") {
        std::env::var_os("HOME")
            .map(PathBuf::from)
            .map(|home| home.join("Library").join("Application Support"))
    } else if cfg!(target_os = "windows") {
        std::env::var_os("APPDATA").map(PathBuf::from)
    } else {
        std::env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .or_else(|| {
                std::env::var_os("HOME")
                    .map(PathBuf::from)
                    .map(|home| home.join(".local").join("share"))
            })
    };
    base.unwrap_or_else(std::env::temp_dir)
        .join("ai-employee")
        .join("runner-workspace")
}

#[tauri::command]
fn list_workspace_files(
    workspace_path: String,
    path: Option<String>,
) -> Result<WorkspaceFileListResult, String> {
    let root = resolve_existing_workspace_root(&workspace_path)?;
    let directory = resolve_workspace_child(&root, path.unwrap_or_default())?;
    if !directory.exists() {
        return Err("目录不存在".to_string());
    }
    if !directory.is_dir() {
        return Err("路径不是目录".to_string());
    }

    let mut items = Vec::new();
    let entries = fs::read_dir(&directory).map_err(|err| format!("无法读取目录：{err}"))?;
    for entry in entries.flatten() {
        if items.len() >= 500 {
            break;
        }
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if name.is_empty() {
            continue;
        }
        let metadata = match entry.metadata() {
            Ok(value) => value,
            Err(_) => continue,
        };
        let modified_at_epoch_ms = metadata
            .modified()
            .ok()
            .and_then(system_time_to_epoch_millis)
            .unwrap_or(0);
        items.push(WorkspaceFileItem {
            name,
            path: workspace_relative_path(&root, &path),
            kind: if metadata.is_dir() {
                "directory"
            } else {
                "file"
            }
            .to_string(),
            size: metadata.len(),
            modified_at_epoch_ms,
        });
    }
    items.sort_by(|a, b| {
        let a_hidden = hidden_file_weight(&a.name);
        let b_hidden = hidden_file_weight(&b.name);
        (a_hidden, a.kind != "directory", a.name.to_lowercase()).cmp(&(
            b_hidden,
            b.kind != "directory",
            b.name.to_lowercase(),
        ))
    });

    Ok(WorkspaceFileListResult {
        root: root.to_string_lossy().to_string(),
        path: workspace_relative_path(&root, &directory),
        items,
    })
}

#[tauri::command]
fn read_workspace_file(
    workspace_path: String,
    path: String,
) -> Result<WorkspaceFileReadResult, String> {
    let root = resolve_existing_workspace_root(&workspace_path)?;
    let target = resolve_workspace_write_target(&root, path)?;
    if !target.exists() {
        return Err("文件不存在".to_string());
    }
    if !target.is_file() {
        return Err("路径不是文件".to_string());
    }
    let metadata = target
        .metadata()
        .map_err(|err| format!("无法读取文件信息：{err}"))?;
    if metadata.len() > 1024 * 1024 {
        return Err("文件超过 1MB，暂不支持在侧栏直接打开".to_string());
    }
    let raw = fs::read(&target).map_err(|err| format!("无法读取文件：{err}"))?;
    let (content, encoding) = match String::from_utf8(raw) {
        Ok(value) => (value, "utf-8".to_string()),
        Err(err) => (
            String::from_utf8_lossy(err.as_bytes()).to_string(),
            "utf-8-replace".to_string(),
        ),
    };
    let modified_at_epoch_ms = metadata
        .modified()
        .ok()
        .and_then(system_time_to_epoch_millis)
        .unwrap_or(0);

    let content_hash = text_fingerprint(&content);
    Ok(WorkspaceFileReadResult {
        root: root.to_string_lossy().to_string(),
        path: workspace_relative_path(&root, &target),
        name: target
            .file_name()
            .map(|value| value.to_string_lossy().to_string())
            .unwrap_or_default(),
        size: metadata.len(),
        modified_at_epoch_ms,
        encoding,
        content,
        content_hash,
    })
}

#[tauri::command]
fn delete_workspace_file(workspace_path: String, path: String) -> Result<bool, String> {
    let root = resolve_existing_workspace_root(&workspace_path)?;
    let target = resolve_workspace_write_target(&root, path)?;
    if !target.exists() {
        return Ok(false);
    }
    if !target.is_file() {
        return Err("只能删除文件，不能删除目录".to_string());
    }
    fs::remove_file(target).map_err(|err| format!("删除文件失败：{err}"))?;
    Ok(true)
}

#[tauri::command]
fn delete_workspace_directory(workspace_path: String, path: String) -> Result<bool, String> {
    if path.trim().is_empty() {
        return Err("缺少目录路径".to_string());
    }
    let root = resolve_existing_workspace_root(&workspace_path)?;
    let target = resolve_workspace_write_target(&root, path)?;
    if target == root {
        return Err("不能删除项目工作区根目录".to_string());
    }
    if !target.exists() {
        return Ok(false);
    }
    if !target.is_dir() {
        return Err("只能删除目录，不能删除文件".to_string());
    }
    let mut last_error = None;
    for attempt in 0..3 {
        match fs::remove_dir_all(&target) {
            Ok(()) => return Ok(true),
            Err(error) => {
                last_error = Some(error);
                if attempt < 2 {
                    thread::sleep(Duration::from_millis(80 * (attempt + 1)));
                }
            }
        }
    }
    Err(format!(
        "删除目录失败：{}",
        last_error
            .map(|error| error.to_string())
            .unwrap_or_else(|| "未知错误".to_string())
    ))
}

#[tauri::command]
fn preview_workspace_diff(
    workspace_path: String,
    path: Option<String>,
) -> Result<WorkspaceDiffPreviewResult, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    let raw_path = path.unwrap_or_default();
    let relative_path = if raw_path.trim().is_empty() {
        String::new()
    } else {
        let target = resolve_workspace_write_target(&root, raw_path)?;
        workspace_relative_path(&root, &target)
    };
    let path_filter = if relative_path.is_empty() {
        Vec::new()
    } else {
        vec![relative_path.as_str()]
    };

    let status = run_git_readonly(
        &root,
        &build_git_path_args(&["status", "--short"], &path_filter),
    );
    if status.exit_code == -1 {
        return Ok(WorkspaceDiffPreviewResult {
            root: root.to_string_lossy().to_string(),
            path: relative_path,
            available: false,
            summary: String::new(),
            diff: String::new(),
            status: String::new(),
            exit_code: status.exit_code,
            truncated: false,
            reason: status.stderr,
        });
    }

    let summary = run_git_readonly(
        &root,
        &build_git_path_args(&["diff", "--stat"], &path_filter),
    );
    let diff = run_git_readonly(&root, &build_git_path_args(&["diff"], &path_filter));
    let review_diff = if !relative_path.is_empty() && diff.stdout.trim().is_empty() {
        liuagent_core::review_diff_inputs(&root, &relative_path)?
            .map(|(baseline, current)| render_review_diff(&root, &relative_path, baseline, current))
    } else {
        None
    };
    let reason = [status.stderr, summary.stderr.clone(), diff.stderr.clone()]
        .into_iter()
        .map(|value| value.trim().to_string())
        .find(|value| !value.is_empty())
        .unwrap_or_default();
    let (summary_text, summary_truncated) = truncate_text(summary.stdout, 8_000);
    let (diff_text, diff_truncated) = match review_diff {
        Some(result) => truncate_text(result.stdout, 30_000),
        None => truncate_text(diff.stdout, 30_000),
    };
    let (status_text, status_truncated) = truncate_text(status.stdout, 8_000);
    let exit_code = if diff.exit_code != 0 {
        diff.exit_code
    } else if summary.exit_code != 0 {
        summary.exit_code
    } else {
        status.exit_code
    };

    Ok(WorkspaceDiffPreviewResult {
        root: root.to_string_lossy().to_string(),
        path: relative_path,
        available: exit_code == 0,
        summary: summary_text,
        diff: diff_text,
        status: status_text,
        exit_code,
        truncated: summary_truncated || diff_truncated || status_truncated,
        reason,
    })
}

fn render_review_diff(
    root: &Path,
    relative_path: &str,
    baseline: Vec<u8>,
    current: Vec<u8>,
) -> GitReadResult {
    let review_dir = root.join(".ai-employee").join("file-change-review");
    if let Err(err) = fs::create_dir_all(&review_dir) {
        return GitReadResult {
            exit_code: -1,
            stdout: String::new(),
            stderr: format!("创建差异临时目录失败：{err}"),
        };
    }
    let token = format!(
        "{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|value| value.as_nanos())
            .unwrap_or_default()
    );
    let baseline_path = review_dir.join(format!(".diff-{token}-baseline"));
    let current_path = review_dir.join(format!(".diff-{token}-current"));
    let result = (|| {
        fs::write(&baseline_path, baseline).map_err(|err| format!("写入差异基线失败：{err}"))?;
        fs::write(&current_path, current).map_err(|err| format!("写入当前差异失败：{err}"))?;
        let args = vec![
            "diff".to_string(),
            "--no-index".to_string(),
            "--no-ext-diff".to_string(),
            "--unified=3".to_string(),
            "--".to_string(),
            baseline_path.to_string_lossy().to_string(),
            current_path.to_string_lossy().to_string(),
        ];
        let mut output = run_git_readonly(root, &args);
        if output.exit_code == 1 {
            output.exit_code = 0;
        }
        output.stdout = output
            .stdout
            .replace(
                &baseline_path.to_string_lossy().to_string(),
                &format!("a/{relative_path}"),
            )
            .replace(
                &current_path.to_string_lossy().to_string(),
                &format!("b/{relative_path}"),
            );
        Ok(output)
    })();
    let _ = fs::remove_file(&baseline_path);
    let _ = fs::remove_file(&current_path);
    result.unwrap_or_else(|err| GitReadResult {
        exit_code: -1,
        stdout: String::new(),
        stderr: err,
    })
}

#[tauri::command]
fn prepare_workspace_file_write(
    workspace_path: String,
    path: String,
    content: String,
) -> Result<WorkspaceFileWritePreparation, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    let target = resolve_workspace_write_target(&root, path)?;
    let relative_path = workspace_relative_path(&root, &target);
    let exists = target.exists();
    let metadata = if exists {
        Some(
            target
                .metadata()
                .map_err(|err| format!("无法读取文件信息：{err}"))?,
        )
    } else {
        None
    };
    if metadata
        .as_ref()
        .map(|value| !value.is_file())
        .unwrap_or(false)
    {
        return Err("目标路径不是文件".to_string());
    }
    let current_content = if exists {
        fs::read_to_string(&target).map_err(|err| format!("无法读取当前文件：{err}"))?
    } else {
        String::new()
    };
    let current_size = metadata.as_ref().map(|value| value.len()).unwrap_or(0);
    let next_size = content.as_bytes().len() as u64;
    let current_line_count = count_text_lines(&current_content);
    let next_line_count = count_text_lines(&content);
    let changed = current_content != content;
    let risk_level = classify_workspace_file_write_risk(exists, current_size, next_size);
    let size_delta = next_size as i128 - current_size as i128;
    let line_delta = next_line_count as i128 - current_line_count as i128;
    let summary = if changed {
        format!(
            "准备写入工作区文件：{}；大小变化 {:+} bytes，行数变化 {:+}",
            relative_path, size_delta, line_delta
        )
    } else {
        format!("文件内容未变化：{}", relative_path)
    };

    Ok(WorkspaceFileWritePreparation {
        root: root.to_string_lossy().to_string(),
        path: relative_path,
        exists,
        current_size,
        next_size,
        current_line_count,
        next_line_count,
        changed,
        risk_level,
        requires_approval: changed,
        summary,
        reason: if changed {
            "确认后将校验文件哈希并执行真实写入".to_string()
        } else {
            "没有检测到内容变化".to_string()
        },
        current_hash: text_fingerprint(&current_content),
        next_hash: text_fingerprint(&content),
        modified_at_epoch_ms: metadata
            .as_ref()
            .and_then(|value| value.modified().ok())
            .and_then(system_time_to_epoch_millis)
            .unwrap_or(0),
    })
}

#[tauri::command]
fn write_workspace_file(
    workspace_path: String,
    path: String,
    content: String,
    expected_current_hash: String,
) -> Result<WorkspaceFileWriteResult, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    let target = resolve_workspace_write_target(&root, path)?;
    if target.exists() && !target.is_file() {
        return Err("目标路径不是文件".to_string());
    }
    let current_content = if target.exists() {
        fs::read_to_string(&target).map_err(|err| format!("无法读取当前文件：{err}"))?
    } else {
        String::new()
    };
    let previous_hash = text_fingerprint(&current_content);
    if !expected_current_hash.is_empty() && previous_hash != expected_current_hash {
        return Err("文件已被其他程序修改，请刷新 Diff 后重新确认".to_string());
    }
    if content.as_bytes().len() > 1024 * 1024 {
        return Err("文件超过 1MB，暂不支持在侧栏直接保存".to_string());
    }
    if current_content != content {
        liuagent_core::capture_baseline(&root, &target).map_err(|err| err.message)?;
    }
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("无法创建目标目录：{err}"))?;
    }
    let temporary = target.with_extension(format!("{}.ai-employee-tmp", std::process::id()));
    fs::write(&temporary, content.as_bytes()).map_err(|err| format!("无法写入临时文件：{err}"))?;
    if let Err(rename_error) = fs::rename(&temporary, &target) {
        if cfg!(windows) && target.exists() {
            fs::remove_file(&target).map_err(|err| format!("无法替换已有文件：{err}"))?;
            fs::rename(&temporary, &target).map_err(|err| {
                let _ = fs::remove_file(&temporary);
                format!("无法替换目标文件：{err}")
            })?;
        } else {
            let _ = fs::remove_file(&temporary);
            return Err(format!("无法替换目标文件：{rename_error}"));
        }
    }
    let metadata = target
        .metadata()
        .map_err(|err| format!("无法读取保存结果：{err}"))?;
    Ok(WorkspaceFileWriteResult {
        root: root.to_string_lossy().to_string(),
        path: workspace_relative_path(&root, &target),
        size: metadata.len(),
        modified_at_epoch_ms: metadata
            .modified()
            .ok()
            .and_then(system_time_to_epoch_millis)
            .unwrap_or(0),
        previous_hash,
        content_hash: text_fingerprint(&content),
    })
}

#[tauri::command]
fn list_workspace_file_changes(
    workspace_path: String,
) -> Result<Vec<liuagent_core::FileChangeReviewItem>, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    liuagent_core::list_changes(&root)
}

#[tauri::command]
fn accept_workspace_file_change(
    workspace_path: String,
    path: String,
    expected_current_hash: String,
) -> Result<bool, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    liuagent_core::accept_change(&root, &path, &expected_current_hash)?;
    Ok(true)
}

#[tauri::command]
fn revert_workspace_file_change(
    workspace_path: String,
    path: String,
    expected_current_hash: String,
) -> Result<bool, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    liuagent_core::revert_change(&root, &path, &expected_current_hash)?;
    Ok(true)
}

#[tauri::command]
fn read_global_mcp_config_file(app: tauri::AppHandle) -> Result<McpConfigFileResult, String> {
    let target = global_mcp_config_path(&app)?;
    read_mcp_config_file("global", target, default_global_mcp_config())
}

#[tauri::command]
fn write_global_mcp_config_file(
    app: tauri::AppHandle,
    content: String,
) -> Result<McpConfigFileResult, String> {
    let target = global_mcp_config_path(&app)?;
    write_mcp_config_file("global", target, content)
}

#[tauri::command]
fn read_project_mcp_config_file(workspace_path: String) -> Result<McpConfigFileResult, String> {
    let target = project_mcp_config_path(&workspace_path)?;
    read_mcp_config_file("project", target, default_project_mcp_config())
}

#[tauri::command]
fn write_project_mcp_config_file(
    workspace_path: String,
    content: String,
) -> Result<McpConfigFileResult, String> {
    let target = project_mcp_config_path(&workspace_path)?;
    write_mcp_config_file("project", target, content)
}

#[tauri::command]
fn read_global_web_tools_config_file() -> Result<WebToolsConfigFileResult, String> {
    let target = global_web_tools_config_path()?;
    read_web_tools_config_file("global", target, default_web_tools_config())
}

#[tauri::command]
fn write_global_web_tools_config_file(content: String) -> Result<WebToolsConfigFileResult, String> {
    let target = global_web_tools_config_path()?;
    write_web_tools_config_file("global", target, content)
}

#[tauri::command]
fn read_project_web_tools_config_file(
    workspace_path: String,
) -> Result<WebToolsConfigFileResult, String> {
    let target = project_web_tools_config_path(&workspace_path)?;
    read_web_tools_config_file("project", target, default_web_tools_config())
}

#[tauri::command]
fn write_project_web_tools_config_file(
    workspace_path: String,
    content: String,
) -> Result<WebToolsConfigFileResult, String> {
    let target = project_web_tools_config_path(&workspace_path)?;
    write_web_tools_config_file("project", target, content)
}

#[tauri::command]
fn read_global_bot_connector_config_file() -> Result<WebToolsConfigFileResult, String> {
    let target = global_bot_connector_config_path()?;
    read_json_object_config_file(
        "global",
        target,
        default_bot_connector_config(),
        "机器人连接器",
    )
}

#[tauri::command]
fn write_global_bot_connector_config_file(
    content: String,
) -> Result<WebToolsConfigFileResult, String> {
    let target = global_bot_connector_config_path()?;
    write_json_object_config_file("global", target, content, "机器人连接器")
}

#[tauri::command]
fn read_global_project_catalog_file() -> Result<WebToolsConfigFileResult, String> {
    let target = liuagent_core::global_project_catalog_path()?;
    let catalog = liuagent_core::read_global_project_catalog()?;
    let content = serde_json::to_string_pretty(&catalog)
        .map_err(|err| format!("无法序列化全局项目目录：{err}"))?;
    Ok(WebToolsConfigFileResult {
        scope: "global".to_string(),
        path: target.to_string_lossy().to_string(),
        exists: target.exists(),
        content: format!("{content}\n"),
    })
}

#[tauri::command]
fn write_global_project_catalog_file(content: String) -> Result<WebToolsConfigFileResult, String> {
    let catalog = liuagent_core::parse_project_catalog_content(&content)?;
    let catalog = liuagent_core::write_global_project_catalog(catalog)?;
    let target = liuagent_core::global_project_catalog_path()?;
    let content = serde_json::to_string_pretty(&catalog)
        .map_err(|err| format!("无法序列化全局项目目录：{err}"))?;
    Ok(WebToolsConfigFileResult {
        scope: "global".to_string(),
        path: target.to_string_lossy().to_string(),
        exists: true,
        content: format!("{content}\n"),
    })
}

#[tauri::command]
fn read_global_ftp_credentials_file() -> Result<WebToolsConfigFileResult, String> {
    let target = liuagent_core::global_ftp_credentials_path()?;
    let credentials = liuagent_core::read_global_ftp_credentials()?;
    let content = serde_json::to_string_pretty(&credentials)
        .map_err(|err| format!("无法序列化全局 FTP 连接：{err}"))?;
    Ok(WebToolsConfigFileResult {
        scope: "global".to_string(),
        path: target.to_string_lossy().to_string(),
        exists: target.exists(),
        content: format!("{content}\n"),
    })
}

#[tauri::command]
fn write_global_ftp_credentials_file(content: String) -> Result<WebToolsConfigFileResult, String> {
    let credentials = liuagent_core::parse_ftp_credentials_content(&content)?;
    let credentials = liuagent_core::write_global_ftp_credentials(credentials)?;
    let target = liuagent_core::global_ftp_credentials_path()?;
    let content = serde_json::to_string_pretty(&credentials)
        .map_err(|err| format!("无法序列化全局 FTP 连接：{err}"))?;
    Ok(WebToolsConfigFileResult {
        scope: "global".to_string(),
        path: target.to_string_lossy().to_string(),
        exists: true,
        content: format!("{content}\n"),
    })
}

#[tauri::command]
fn open_external_url(url: String) -> Result<bool, String> {
    let normalized = url.trim();
    if normalized.is_empty() {
        return Err("缺少外部链接".to_string());
    }
    let parsed = reqwest::Url::parse(normalized).map_err(|err| format!("外部链接无效：{err}"))?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err("只允许打开 http/https 外部链接".to_string());
    }
    open_external_url_with_system(parsed.as_str())
}

#[tauri::command]
fn copy_resource_file_to_clipboard(
    url: String,
    file_name: Option<String>,
    mime_type: Option<String>,
    authorization_token: Option<String>,
) -> Result<ClipboardFileResult, String> {
    let normalized_url = url.trim();
    if normalized_url.is_empty() {
        return Err("缺少要复制的文件地址".to_string());
    }
    let requested_mime_type = mime_type.unwrap_or_default();
    let (bytes, resolved_mime_type) = load_clipboard_resource(
        normalized_url,
        authorization_token.as_deref().unwrap_or(""),
        &requested_mime_type,
    )?;
    if bytes.is_empty() {
        return Err("文件内容为空".to_string());
    }
    if bytes.len() > 100 * 1024 * 1024 {
        return Err("复制文件不能超过 100MB".to_string());
    }
    let output_name = resolve_clipboard_file_name(
        file_name.as_deref().unwrap_or(""),
        normalized_url,
        &resolved_mime_type,
    );
    let clipboard_entry_id = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let output_dir = std::env::temp_dir()
        .join("ai-employee-clipboard")
        .join(clipboard_entry_id.to_string());
    fs::create_dir_all(&output_dir).map_err(|err| format!("创建临时目录失败：{err}"))?;
    let output_path = output_dir.join(&output_name);
    fs::write(&output_path, bytes).map_err(|err| format!("保存临时文件失败：{err}"))?;
    copy_local_file_to_system_clipboard(&output_path)?;
    Ok(ClipboardFileResult {
        copied: true,
        path: output_path.to_string_lossy().to_string(),
        name: output_name,
    })
}

#[tauri::command]
fn save_resource_file(
    url: String,
    file_name: Option<String>,
    mime_type: Option<String>,
    authorization_token: Option<String>,
) -> Result<SavedResourceFileResult, String> {
    let normalized_url = url.trim();
    if normalized_url.is_empty() {
        return Err("缺少要保存的文件地址".to_string());
    }
    let requested_mime_type = mime_type.unwrap_or_default();
    let suggested_name = resolve_clipboard_file_name(
        file_name.as_deref().unwrap_or(""),
        normalized_url,
        &requested_mime_type,
    );
    let Some(output_path) = rfd::FileDialog::new()
        .set_title("保存资源")
        .set_file_name(&suggested_name)
        .save_file()
    else {
        return Ok(SavedResourceFileResult {
            saved: false,
            cancelled: true,
            path: String::new(),
            name: suggested_name,
        });
    };
    let (bytes, _) = load_clipboard_resource(
        normalized_url,
        authorization_token.as_deref().unwrap_or(""),
        &requested_mime_type,
    )?;
    if bytes.is_empty() {
        return Err("文件内容为空".to_string());
    }
    if bytes.len() > 100 * 1024 * 1024 {
        return Err("保存文件不能超过 100MB".to_string());
    }
    fs::write(&output_path, bytes).map_err(|err| format!("保存文件失败：{err}"))?;
    let saved_name = output_path
        .file_name()
        .map(|value| value.to_string_lossy().to_string())
        .unwrap_or(suggested_name);
    Ok(SavedResourceFileResult {
        saved: true,
        cancelled: false,
        path: output_path.to_string_lossy().to_string(),
        name: saved_name,
    })
}

#[tauri::command]
fn persist_project_chat_asset(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
    chat_session_id: String,
    message_id: String,
    url: String,
    file_name: Option<String>,
    mime_type: Option<String>,
    asset_type: Option<String>,
    authorization_token: Option<String>,
    source_tool: Option<String>,
) -> Result<PersistedProjectChatAssetResult, String> {
    let username = require_project_chat_asset_component(&username, "用户名")?;
    let project_id = require_project_chat_asset_component(&project_id, "项目 ID")?;
    let chat_session_id = require_project_chat_asset_component(&chat_session_id, "会话 ID")?;
    let message_id = require_project_chat_asset_component(&message_id, "消息 ID")?;
    let source_url = url.trim();
    if source_url.is_empty() {
        return Err("缺少要持久化的资源地址".to_string());
    }
    let requested_mime_type = mime_type.unwrap_or_default();
    let (bytes, downloaded_mime_type) = load_clipboard_resource(
        source_url,
        authorization_token.as_deref().unwrap_or(""),
        &requested_mime_type,
    )?;
    if bytes.is_empty() {
        return Err("资源内容为空".to_string());
    }
    if bytes.len() > 100 * 1024 * 1024 {
        return Err("持久化资源不能超过 100MB".to_string());
    }
    let resolved_mime_type = if !downloaded_mime_type.trim().is_empty() {
        downloaded_mime_type.trim().to_string()
    } else {
        requested_mime_type.trim().to_string()
    };
    let resolved_name = resolve_clipboard_file_name(
        file_name.as_deref().unwrap_or(""),
        source_url,
        &resolved_mime_type,
    );
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    let digest = format!("{:x}", hasher.finalize());
    let extension = Path::new(&resolved_name)
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| value.trim().to_lowercase())
        .filter(|value| !value.is_empty())
        .or_else(|| clipboard_extension_for_mime_type(&resolved_mime_type).map(str::to_string));
    let stored_name = extension
        .as_deref()
        .map(|value| format!("{digest}.{value}"))
        .unwrap_or_else(|| digest.clone());
    let app_data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    let asset_directory = app_data_dir
        .join("project-chat-data")
        .join(project_chat_asset_path_component(&username))
        .join(project_chat_asset_path_component(&project_id))
        .join("assets")
        .join(project_chat_asset_path_component(&chat_session_id))
        .join(project_chat_asset_path_component(&message_id));
    fs::create_dir_all(&asset_directory).map_err(|err| format!("创建会话资产目录失败：{err}"))?;
    let local_path = asset_directory.join(&stored_name);
    if !local_path.exists() {
        let temporary_path = asset_directory.join(format!(
            ".{stored_name}.{}.{}.tmp",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        fs::write(&temporary_path, &bytes).map_err(|err| format!("写入会话资产失败：{err}"))?;
        if let Err(error) = fs::rename(&temporary_path, &local_path) {
            if local_path.exists() {
                let _ = fs::remove_file(&temporary_path);
            } else {
                return Err(format!("保存会话资产失败：{error}"));
            }
        }
    }
    let kind =
        normalize_project_chat_asset_kind(asset_type.as_deref().unwrap_or(""), &resolved_mime_type);
    let result = PersistedProjectChatAssetResult {
        asset_id: format!("sha256:{digest}"),
        kind,
        mime_type: resolved_mime_type,
        bytes: bytes.len() as u64,
        name: resolved_name,
        local_path: local_path.to_string_lossy().to_string(),
        source_url: source_url.to_string(),
        source_tool: source_tool.unwrap_or_default().trim().to_string(),
        message_id,
        created_at: chrono::Utc::now().to_rfc3339(),
    };
    let metadata_path = asset_directory.join(format!("{digest}.json"));
    let metadata = serde_json::to_vec_pretty(&result)
        .map_err(|err| format!("序列化会话资产元数据失败：{err}"))?;
    fs::write(metadata_path, metadata).map_err(|err| format!("保存会话资产元数据失败：{err}"))?;
    Ok(result)
}

fn require_project_chat_asset_component(value: &str, label: &str) -> Result<String, String> {
    let normalized = value.trim();
    if normalized.is_empty() {
        return Err(format!("缺少{label}"));
    }
    Ok(normalized.to_string())
}

fn project_chat_asset_path_component(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>()
}

fn normalize_project_chat_asset_kind(requested: &str, mime_type: &str) -> String {
    let requested = requested.trim().to_lowercase();
    if matches!(requested.as_str(), "image" | "video" | "audio" | "file") {
        return requested;
    }
    let mime_type = mime_type.trim().to_lowercase();
    if mime_type.starts_with("image/") {
        "image".to_string()
    } else if mime_type.starts_with("video/") {
        "video".to_string()
    } else if mime_type.starts_with("audio/") {
        "audio".to_string()
    } else {
        "file".to_string()
    }
}

#[tauri::command]
fn read_local_file(path: String) -> Result<LocalFileReadResult, String> {
    let target = PathBuf::from(path.trim());
    if target.as_os_str().is_empty() {
        return Err("缺少本地文件路径".to_string());
    }
    if !target.exists() {
        return Err("拖入的文件不存在".to_string());
    }
    if !target.is_file() {
        return Err("拖入的路径不是文件".to_string());
    }
    let metadata = target
        .metadata()
        .map_err(|err| format!("无法读取文件信息：{err}"))?;
    if metadata.len() > 100 * 1024 * 1024 {
        return Err("文件超过 100MB，暂不支持上传".to_string());
    }
    let bytes = fs::read(&target).map_err(|err| format!("无法读取拖入文件：{err}"))?;
    let name = target
        .file_name()
        .map(|value| value.to_string_lossy().to_string())
        .unwrap_or_else(|| "dropped-file".to_string());
    Ok(LocalFileReadResult {
        mime_type: mime_type_for_path(&target).to_string(),
        name,
        size: metadata.len(),
        bytes,
    })
}

#[tauri::command]
fn open_desktop_devtools(window: tauri::WebviewWindow) -> Result<(), String> {
    #[cfg(debug_assertions)]
    {
        window.open_devtools();
        return Ok(());
    }

    #[cfg(not(debug_assertions))]
    {
        let _ = window;
        Err("开发者工具仅在桌面调试构建中可用".to_string())
    }
}

fn mime_type_for_path(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_lowercase()
        .as_str()
    {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "bmp" => "image/bmp",
        "webp" => "image/webp",
        "svg" => "image/svg+xml",
        "heic" => "image/heic",
        "heif" => "image/heif",
        "mp3" => "audio/mpeg",
        "wav" => "audio/wav",
        "m4a" => "audio/mp4",
        "aac" => "audio/aac",
        "ogg" => "audio/ogg",
        "flac" => "audio/flac",
        "mp4" => "video/mp4",
        "mov" => "video/quicktime",
        "webm" => "video/webm",
        "pdf" => "application/pdf",
        "txt" => "text/plain",
        "md" => "text/markdown",
        "csv" => "text/csv",
        "json" => "application/json",
        "doc" => "application/msword",
        "docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls" => "application/vnd.ms-excel",
        "xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ppt" => "application/vnd.ms-powerpoint",
        "pptx" => "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        _ => "application/octet-stream",
    }
}

fn load_clipboard_resource(
    resource_url: &str,
    authorization_token: &str,
    fallback_mime_type: &str,
) -> Result<(Vec<u8>, String), String> {
    if resource_url.starts_with("data:") {
        return decode_clipboard_data_url(resource_url, fallback_mime_type);
    }
    if let Ok(parsed) = reqwest::Url::parse(resource_url) {
        if parsed.scheme() == "file" {
            let path = parsed
                .to_file_path()
                .map_err(|_| "本地文件地址无效".to_string())?;
            let bytes = fs::read(&path).map_err(|err| format!("读取本地文件失败：{err}"))?;
            return Ok((bytes, fallback_mime_type.trim().to_string()));
        }
        if matches!(parsed.scheme(), "http" | "https") {
            let client = reqwest::blocking::Client::builder()
                .timeout(Duration::from_secs(60))
                .build()
                .map_err(|err| format!("创建下载客户端失败：{err}"))?;
            let mut request = client.get(parsed);
            if !authorization_token.trim().is_empty() {
                request = request.bearer_auth(authorization_token.trim());
            }
            let response = request
                .send()
                .map_err(|err| format!("下载文件失败：{err}"))?
                .error_for_status()
                .map_err(|err| format!("下载文件失败：{err}"))?;
            let content_type = response
                .headers()
                .get(reqwest::header::CONTENT_TYPE)
                .and_then(|value| value.to_str().ok())
                .map(|value| value.split(';').next().unwrap_or("").trim().to_string())
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| fallback_mime_type.trim().to_string());
            let bytes = response
                .bytes()
                .map_err(|err| format!("读取下载文件失败：{err}"))?;
            return Ok((bytes.to_vec(), content_type));
        }
    }
    let path = PathBuf::from(resource_url);
    let bytes = fs::read(&path).map_err(|err| format!("读取文件失败：{err}"))?;
    Ok((bytes, fallback_mime_type.trim().to_string()))
}

fn decode_clipboard_data_url(
    data_url: &str,
    fallback_mime_type: &str,
) -> Result<(Vec<u8>, String), String> {
    let (header, payload) = data_url
        .split_once(',')
        .ok_or_else(|| "Data URL 格式无效".to_string())?;
    if !header.ends_with(";base64") {
        return Err("仅支持 Base64 Data URL".to_string());
    }
    let mime_type = header
        .strip_prefix("data:")
        .and_then(|value| value.strip_suffix(";base64"))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| fallback_mime_type.trim())
        .to_string();
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(payload.trim())
        .map_err(|err| format!("Data URL 解码失败：{err}"))?;
    Ok((bytes, mime_type))
}

fn resolve_clipboard_file_name(requested: &str, resource_url: &str, mime_type: &str) -> String {
    let requested_name = sanitize_clipboard_file_name(requested);
    let url_name = reqwest::Url::parse(resource_url)
        .ok()
        .and_then(|url| {
            url.path_segments()
                .and_then(|mut segments| segments.next_back())
                .map(sanitize_clipboard_file_name)
        })
        .unwrap_or_default();
    let mut name = if !requested_name.is_empty() {
        requested_name
    } else if !url_name.is_empty() {
        url_name
    } else {
        "liuagent-file".to_string()
    };
    if Path::new(&name).extension().is_none() {
        if let Some(extension) = clipboard_extension_for_mime_type(mime_type) {
            name.push('.');
            name.push_str(extension);
        }
    }
    name
}

fn sanitize_clipboard_file_name(value: &str) -> String {
    value
        .trim()
        .chars()
        .map(|character| {
            if character.is_alphanumeric() || matches!(character, '.' | '-' | '_' | ' ') {
                character
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim_matches(['.', ' '])
        .chars()
        .take(120)
        .collect()
}

fn clipboard_extension_for_mime_type(mime_type: &str) -> Option<&'static str> {
    match mime_type.trim().to_lowercase().as_str() {
        "image/png" => Some("png"),
        "image/jpeg" => Some("jpg"),
        "image/gif" => Some("gif"),
        "image/webp" => Some("webp"),
        "video/mp4" => Some("mp4"),
        "video/webm" => Some("webm"),
        "audio/mpeg" => Some("mp3"),
        "audio/wav" | "audio/x-wav" => Some("wav"),
        "audio/mp4" => Some("m4a"),
        "application/pdf" => Some("pdf"),
        "text/plain" => Some("txt"),
        _ => None,
    }
}

#[cfg(target_os = "macos")]
fn copy_local_file_to_system_clipboard(path: &Path) -> Result<(), String> {
    let output = Command::new("osascript")
        .args([
            "-e",
            "on run argv",
            "-e",
            "set the clipboard to (POSIX file (item 1 of argv))",
            "-e",
            "end run",
            "--",
        ])
        .arg(path)
        .output()
        .map_err(|err| format!("调用系统剪贴板失败：{err}"))?;
    if output.status.success() {
        Ok(())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).trim().to_string())
    }
}

#[cfg(target_os = "windows")]
fn copy_local_file_to_system_clipboard(path: &Path) -> Result<(), String> {
    let output = Command::new("powershell")
        .args(["-NoProfile", "-Command", "Set-Clipboard -Path $args[0]"])
        .arg(path)
        .output()
        .map_err(|err| format!("调用系统剪贴板失败：{err}"))?;
    if output.status.success() {
        Ok(())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).trim().to_string())
    }
}

#[cfg(target_os = "linux")]
fn copy_local_file_to_system_clipboard(path: &Path) -> Result<(), String> {
    let uri = format!("file://{}\n", path.to_string_lossy());
    let mut child = Command::new("xclip")
        .args(["-selection", "clipboard", "-t", "text/uri-list"])
        .stdin(Stdio::piped())
        .spawn()
        .map_err(|err| format!("需要安装 xclip 才能复制文件：{err}"))?;
    child
        .stdin
        .as_mut()
        .ok_or_else(|| "无法写入系统剪贴板".to_string())?
        .write_all(uri.as_bytes())
        .map_err(|err| format!("写入系统剪贴板失败：{err}"))?;
    let status = child.wait().map_err(|err| err.to_string())?;
    if status.success() {
        Ok(())
    } else {
        Err("系统剪贴板拒绝复制文件".to_string())
    }
}

#[tauri::command]
fn classify_runner_command(
    command: String,
    args: Option<Vec<String>>,
    workspace_path: Option<String>,
) -> RunnerCommandClassification {
    classify_runner_command_inner(command, args.unwrap_or_default(), workspace_path)
}

#[tauri::command]
fn run_runner_command(
    command: String,
    args: Option<Vec<String>>,
    workspace_path: Option<String>,
    timeout_ms: Option<u64>,
    dry_run: Option<bool>,
) -> RunnerCommandResult {
    let args = args.unwrap_or_default();
    let classification =
        classify_runner_command_inner(command.clone(), args.clone(), workspace_path.clone());
    if !classification.allowed || dry_run.unwrap_or(false) {
        return RunnerCommandResult {
            allowed: classification.allowed,
            risk_level: classification.risk_level,
            requires_approval: classification.requires_approval,
            command: classification.command,
            args: classification.args,
            workspace_path: classification.workspace_path,
            stdout: String::new(),
            stderr: String::new(),
            exit_code: if classification.allowed { 0 } else { -1 },
            duration_ms: 0,
            timed_out: false,
            blocked_reason: classification.blocked_reason,
        };
    }

    let timeout = Duration::from_millis(timeout_ms.unwrap_or(5_000).clamp(1_000, 30_000));
    execute_allowed_runner_command(classification, timeout)
}

#[tauri::command]
fn record_runner_permission_decision(
    app: tauri::AppHandle,
    input: RunnerPermissionDecisionInput,
) -> Result<RunnerPermissionDecisionRecord, String> {
    let now = current_epoch_millis();
    let command = input.command.trim().to_string();
    let args = input
        .args
        .unwrap_or_default()
        .into_iter()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>();
    let decision = input.decision.trim().to_string();
    if command.is_empty() {
        return Err("缺少命令".to_string());
    }
    if !matches!(
        decision.as_str(),
        "approve_once" | "approve_session" | "reject"
    ) {
        return Err("未知的 Runner 权限决定".to_string());
    }

    let record = RunnerPermissionDecisionRecord {
        decision_id: input
            .decision_id
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| format!("runner-permission-{now}")),
        command,
        args,
        workspace_path: input.workspace_path.unwrap_or_default().trim().to_string(),
        decision,
        reason: input.reason.unwrap_or_default().trim().to_string(),
        scope: input
            .scope
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "current_request".to_string()),
        source: input
            .source
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "project_chat".to_string()),
        risk_level: input
            .risk_level
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "unknown".to_string()),
        created_at_epoch_ms: now,
    };

    let mut records = read_runner_permission_decisions(&app)?;
    records.push(record.clone());
    if records.len() > 100 {
        records = records.split_off(records.len() - 100);
    }
    write_runner_permission_decisions(&app, &records)?;
    Ok(record)
}

#[tauri::command]
fn list_runner_permission_decisions(
    app: tauri::AppHandle,
    limit: Option<usize>,
) -> Result<Vec<RunnerPermissionDecisionRecord>, String> {
    let records = read_runner_permission_decisions(&app)?;
    let max_records = limit.unwrap_or(20).clamp(1, 100);
    Ok(records
        .into_iter()
        .rev()
        .take(max_records)
        .collect::<Vec<_>>())
}

fn detect_executor(command: &str) -> ExecutorStatus {
    match Command::new(command).arg("--version").output() {
        Ok(output) if output.status.success() => {
            let stdout = String::from_utf8_lossy(&output.stdout);
            let stderr = String::from_utf8_lossy(&output.stderr);
            let version = stdout
                .lines()
                .chain(stderr.lines())
                .map(str::trim)
                .find(|line| !line.is_empty())
                .unwrap_or("")
                .to_string();
            ExecutorStatus {
                installed: true,
                available: true,
                path: command.to_string(),
                version,
                reason: String::new(),
            }
        }
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            ExecutorStatus {
                installed: false,
                available: false,
                path: String::new(),
                version: String::new(),
                reason: if stderr.is_empty() {
                    format!("{command} --version exited with {}", output.status)
                } else {
                    stderr
                },
            }
        }
        Err(err) => ExecutorStatus {
            installed: false,
            available: false,
            path: String::new(),
            version: String::new(),
            reason: err.to_string(),
        },
    }
}

fn classify_runner_command_inner(
    command: String,
    args: Vec<String>,
    workspace_path: Option<String>,
) -> RunnerCommandClassification {
    let normalized_command = command.trim().to_string();
    let normalized_args: Vec<String> = args
        .into_iter()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .collect();
    let normalized_workspace = workspace_path.unwrap_or_default().trim().to_string();

    let mut blocked_reason = String::new();
    if normalized_command.is_empty() {
        blocked_reason = "缺少命令".to_string();
    } else if !is_allowed_runner_command(&normalized_command, &normalized_args) {
        blocked_reason = format!(
            "当前桌面 Runner 只允许版本检查和 git status --short，自检命令不在白名单内：{} {}",
            normalized_command,
            normalized_args.join(" ")
        )
        .trim()
        .to_string();
    } else if !normalized_workspace.is_empty() {
        match fs::metadata(&normalized_workspace) {
            Ok(metadata) if metadata.is_dir() => {}
            Ok(_) => blocked_reason = "工作区路径不是目录".to_string(),
            Err(err) => blocked_reason = format!("工作区不可访问：{err}"),
        }
    } else if normalized_command == "git" {
        blocked_reason = "git status 需要先配置本机工作区".to_string();
    }

    let allowed = blocked_reason.is_empty();
    RunnerCommandClassification {
        allowed,
        risk_level: if allowed { "low" } else { "blocked" }.to_string(),
        requires_approval: false,
        command: normalized_command.clone(),
        args: normalized_args.clone(),
        workspace_path: normalized_workspace,
        blocked_reason,
        summary: if allowed {
            format!(
                "允许执行只读自检命令：{} {}",
                normalized_command,
                normalized_args.join(" ")
            )
            .trim()
            .to_string()
        } else {
            "命令已被桌面 Runner 权限边界拦截".to_string()
        },
    }
}

fn is_allowed_runner_command(command: &str, args: &[String]) -> bool {
    matches!(
        (command, args),
        ("node", [arg]) if is_version_arg(arg)
    ) || matches!(
        (command, args),
        ("npm", [arg]) if is_version_arg(arg)
    ) || matches!(
        (command, args),
        ("codex", [arg]) if is_version_arg(arg)
    ) || matches!(
        (command, args),
        ("hermes", [arg]) if is_version_arg(arg)
    ) || matches!(
        (command, args),
        ("claude", [arg]) if is_version_arg(arg)
    ) || matches!(
        (command, args),
        ("cargo", [arg]) if is_version_arg(arg)
    ) || matches!(
        (command, args),
        ("tauri", [arg]) if is_version_arg(arg)
    ) || matches!(
        (command, args),
        ("git", [arg]) if is_version_arg(arg)
    ) || matches!(
        (command, args),
        ("git", [status, short]) if status == "status" && short == "--short"
    )
}

fn is_version_arg(value: &str) -> bool {
    value == "--version" || value == "-v" || value == "version"
}

fn execute_allowed_runner_command(
    classification: RunnerCommandClassification,
    timeout: Duration,
) -> RunnerCommandResult {
    let started_at = Instant::now();
    let mut command = Command::new(&classification.command);
    command.args(&classification.args);
    if !classification.workspace_path.is_empty() {
        command.current_dir(Path::new(&classification.workspace_path));
    }
    command.stdout(Stdio::piped()).stderr(Stdio::piped());

    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(err) => {
            return RunnerCommandResult {
                allowed: true,
                risk_level: classification.risk_level,
                requires_approval: classification.requires_approval,
                command: classification.command,
                args: classification.args,
                workspace_path: classification.workspace_path,
                stdout: String::new(),
                stderr: err.to_string(),
                exit_code: -1,
                duration_ms: started_at.elapsed().as_millis(),
                timed_out: false,
                blocked_reason: String::new(),
            };
        }
    };

    let stdout_receiver = child.stdout.take().map(|mut stream| {
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            let mut text = String::new();
            let _ = stream.read_to_string(&mut text);
            let _ = sender.send(text);
        });
        receiver
    });
    let stderr_receiver = child.stderr.take().map(|mut stream| {
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            let mut text = String::new();
            let _ = stream.read_to_string(&mut text);
            let _ = sender.send(text);
        });
        receiver
    });
    let mut timed_out = false;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if started_at.elapsed() >= timeout => {
                timed_out = true;
                let _ = child.kill();
                break child.wait().ok();
            }
            Ok(None) => thread::sleep(Duration::from_millis(30)),
            Err(_) => break None,
        }
    };

    let stdout_text = receive_process_output(stdout_receiver, Duration::from_millis(300));
    let stderr_text = sanitize_runner_process_output(&receive_process_output(
        stderr_receiver,
        Duration::from_millis(300),
    ));

    RunnerCommandResult {
        allowed: true,
        risk_level: classification.risk_level,
        requires_approval: classification.requires_approval,
        command: classification.command,
        args: classification.args,
        workspace_path: classification.workspace_path,
        stdout: truncate_command_output(stdout_text),
        stderr: truncate_command_output(stderr_text),
        exit_code: status.and_then(|value| value.code()).unwrap_or(-1),
        duration_ms: started_at.elapsed().as_millis(),
        timed_out,
        blocked_reason: String::new(),
    }
}

fn truncate_command_output(value: String) -> String {
    const MAX_OUTPUT_CHARS: usize = 20_000;
    truncate_text(value, MAX_OUTPUT_CHARS).0
}

fn receive_process_output(receiver: Option<mpsc::Receiver<String>>, timeout: Duration) -> String {
    receiver
        .and_then(|receiver| receiver.recv_timeout(timeout).ok())
        .unwrap_or_default()
}

fn sanitize_runner_process_output(content: &str) -> String {
    content
        .lines()
        .filter(|line| !is_runner_diagnostic_line(line))
        .collect::<Vec<_>>()
        .join("\n")
}

fn is_runner_diagnostic_line(content: &str) -> bool {
    let line = content.trim();
    if line.is_empty() {
        return false;
    }
    line.contains("failed to record rollout items")
        || line.contains("failed to flush rollout recorder")
        || (line.len() > 22
            && line.as_bytes().get(4) == Some(&b'-')
            && line.as_bytes().get(7) == Some(&b'-')
            && (line.contains(" [INFO] ")
                || line.contains(" [DEBUG] ")
                || line.contains(" [WARNING] ")
                || line.contains(" [ERROR] ")))
}

fn truncate_text(value: String, max_chars: usize) -> (String, bool) {
    if value.chars().count() <= max_chars {
        return (value, false);
    }
    let mut truncated: String = value.chars().take(max_chars).collect();
    truncated.push_str("\n[output truncated]");
    (truncated, true)
}

fn current_epoch_millis() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis().min(u128::from(u64::MAX)) as u64)
        .unwrap_or(0)
}

fn system_time_to_epoch_millis(value: SystemTime) -> Option<u64> {
    value
        .duration_since(UNIX_EPOCH)
        .ok()
        .map(|duration| duration.as_millis().min(u128::from(u64::MAX)) as u64)
}

fn resolve_workspace_root(workspace_path: &str) -> Result<PathBuf, String> {
    let raw = workspace_path.trim();
    if raw.is_empty() {
        return Err("缺少工作区路径".to_string());
    }
    let raw_root = PathBuf::from(raw);
    if !raw_root.exists() {
        fs::create_dir_all(&raw_root).map_err(|err| format!("工作区无法创建：{err}"))?;
    }
    let root = raw_root
        .canonicalize()
        .map_err(|err| format!("工作区不可访问：{err}"))?;
    if !root.is_dir() {
        return Err("工作区路径不是目录".to_string());
    }
    Ok(root)
}

fn resolve_existing_workspace_root(workspace_path: &str) -> Result<PathBuf, String> {
    let raw = workspace_path.trim();
    if raw.is_empty() {
        return Err("缺少工作区路径".to_string());
    }
    let raw_root = PathBuf::from(raw);
    if !raw_root.exists() {
        return Err("目录不存在".to_string());
    }
    let root = raw_root
        .canonicalize()
        .map_err(|err| format!("工作区不可访问：{err}"))?;
    if !root.is_dir() {
        return Err("工作区路径不是目录".to_string());
    }
    Ok(root)
}

fn resolve_workspace_child(root: &Path, raw_path: String) -> Result<PathBuf, String> {
    let raw = raw_path.trim();
    let candidate = if raw.is_empty() {
        root.to_path_buf()
    } else {
        let path = PathBuf::from(raw);
        if path.is_absolute() {
            path
        } else {
            root.join(path)
        }
    };
    let resolved = candidate
        .canonicalize()
        .map_err(|err| format!("路径不可访问：{err}"))?;
    if !resolved.starts_with(root) {
        return Err("路径必须位于项目工作区内".to_string());
    }
    Ok(resolved)
}

fn resolve_workspace_write_target(root: &Path, raw_path: String) -> Result<PathBuf, String> {
    let raw = raw_path.trim();
    if raw.is_empty() {
        return Err("缺少文件路径".to_string());
    }
    let path = PathBuf::from(raw);
    let candidate = if path.is_absolute() {
        path
    } else {
        root.join(path)
    };
    let candidate = normalize_path_lexically(&candidate);
    if !candidate.starts_with(root) {
        return Err("路径必须位于项目工作区内".to_string());
    }
    let parent = candidate.parent().ok_or_else(|| "缺少父目录".to_string())?;
    let mut existing_ancestor = parent;
    let mut missing_segments = Vec::new();
    while !existing_ancestor.exists() {
        let segment = existing_ancestor
            .file_name()
            .ok_or_else(|| "父目录不可访问".to_string())?;
        missing_segments.push(segment.to_os_string());
        existing_ancestor = existing_ancestor
            .parent()
            .ok_or_else(|| "父目录不可访问".to_string())?;
    }
    let canonical_ancestor = existing_ancestor
        .canonicalize()
        .map_err(|err| format!("父目录不可访问：{err}"))?;
    if !canonical_ancestor.starts_with(root) {
        return Err("路径必须位于项目工作区内".to_string());
    }
    let mut resolved_parent = canonical_ancestor;
    for segment in missing_segments.iter().rev() {
        resolved_parent.push(segment);
    }
    let target = resolved_parent.join(
        candidate
            .file_name()
            .ok_or_else(|| "缺少文件名".to_string())?,
    );
    if target.symlink_metadata().is_ok() {
        let canonical_target = target
            .canonicalize()
            .map_err(|err| format!("目标路径不可访问：{err}"))?;
        if !canonical_target.starts_with(root) {
            return Err("路径必须位于项目工作区内".to_string());
        }
        return Ok(canonical_target);
    }
    Ok(target)
}

fn normalize_path_lexically(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                normalized.pop();
            }
            std::path::Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            std::path::Component::RootDir => normalized.push(component.as_os_str()),
            std::path::Component::Normal(segment) => normalized.push(segment),
        }
    }
    normalized
}

fn global_mcp_config_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    if let Some(home) = std::env::var_os("HOME") {
        return Ok(PathBuf::from(home).join(".ai-employee").join("mcp.json"));
    }
    let app_data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    Ok(app_data_dir.join("mcp.json"))
}

fn project_mcp_config_path(workspace_path: &str) -> Result<PathBuf, String> {
    let root = resolve_workspace_root(workspace_path)?;
    Ok(root.join(".ai-employee").join("mcp.json"))
}

fn global_web_tools_config_path() -> Result<PathBuf, String> {
    ensure_global_desktop_runtime_migrated()?;
    liuagent_core::global_web_tool_config_path()
        .ok_or_else(|| "缺少 HOME，无法定位全局 web-tools 配置文件".to_string())
}

fn project_web_tools_config_path(workspace_path: &str) -> Result<PathBuf, String> {
    let root = resolve_workspace_root(workspace_path)?;
    liuagent_core::ensure_desktop_runtime_migrated(&root)
        .map_err(|err| format!("迁移旧桌面 Runtime 项目配置失败：{err}"))?;
    Ok(liuagent_core::project_web_tool_config_path(&root))
}

fn global_bot_connector_config_path() -> Result<PathBuf, String> {
    let home = ensure_global_desktop_runtime_migrated()?;
    Ok(liuagent_core::desktop_runtime_root(&home)
        .join("bots")
        .join("connectors.json"))
}

fn ensure_global_desktop_runtime_migrated() -> Result<PathBuf, String> {
    let home = liuagent_core::global_user_home_dir()
        .ok_or_else(|| "缺少用户目录，无法定位全局桌面 Runtime".to_string())?;
    liuagent_core::ensure_desktop_runtime_migrated(&home)
        .map_err(|err| format!("迁移旧全局桌面 Runtime 数据失败：{err}"))?;
    Ok(home)
}

fn default_global_mcp_config() -> Value {
    json!({
        "mcpServers": {
            "prompts.chat": {
                "type": "http",
                "url": "https://prompts.chat/api/mcp",
                "enabled": true
            }
        }
    })
}

fn default_project_mcp_config() -> Value {
    json!({ "mcpServers": {} })
}

fn default_web_tools_config() -> Value {
    serde_json::from_str(liuagent_core::WEB_TOOL_CONFIG_TEMPLATE).unwrap_or_else(|_| json!({}))
}

fn default_bot_connector_config() -> Value {
    json!({
        "version": 1,
        "connectors": []
    })
}

fn validate_mcp_config_content(content: &str) -> Result<String, String> {
    let raw = content.trim();
    let parsed: Value = serde_json::from_str(if raw.is_empty() || raw == "undefined" {
        "{}"
    } else {
        raw
    })
    .map_err(|err| format!("MCP 配置 JSON 解析失败：{err}"))?;
    if !parsed.is_object() {
        return Err("MCP 配置必须是 JSON 对象".to_string());
    }
    serde_json::to_string_pretty(&parsed).map_err(|err| err.to_string())
}

fn read_mcp_config_file(
    scope: &str,
    target: PathBuf,
    fallback: Value,
) -> Result<McpConfigFileResult, String> {
    if !target.exists() {
        let content = serde_json::to_string_pretty(&fallback).map_err(|err| err.to_string())?;
        return Ok(McpConfigFileResult {
            scope: scope.to_string(),
            path: target.to_string_lossy().to_string(),
            exists: false,
            content,
        });
    }
    if !target.is_file() {
        return Err("MCP 配置路径不是文件".to_string());
    }
    let content = fs::read_to_string(&target).map_err(|err| format!("无法读取 MCP 配置：{err}"))?;
    Ok(McpConfigFileResult {
        scope: scope.to_string(),
        path: target.to_string_lossy().to_string(),
        exists: true,
        content,
    })
}

fn write_mcp_config_file(
    scope: &str,
    target: PathBuf,
    content: String,
) -> Result<McpConfigFileResult, String> {
    let normalized = validate_mcp_config_content(&content)?;
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("无法创建 MCP 配置目录：{err}"))?;
    }
    fs::write(&target, format!("{normalized}\n"))
        .map_err(|err| format!("无法写入 MCP 配置：{err}"))?;
    Ok(McpConfigFileResult {
        scope: scope.to_string(),
        path: target.to_string_lossy().to_string(),
        exists: true,
        content: format!("{normalized}\n"),
    })
}

fn validate_web_tools_config_content(content: &str) -> Result<String, String> {
    let raw = content.trim();
    let parsed: Value = serde_json::from_str(if raw.is_empty() || raw == "undefined" {
        "{}"
    } else {
        raw
    })
    .map_err(|err| format!("web-tools 配置 JSON 解析失败：{err}"))?;
    if !parsed.is_object() {
        return Err("web-tools 配置必须是 JSON 对象".to_string());
    }
    serde_json::to_string_pretty(&parsed).map_err(|err| err.to_string())
}

fn read_web_tools_config_file(
    scope: &str,
    target: PathBuf,
    fallback: Value,
) -> Result<WebToolsConfigFileResult, String> {
    if !target.exists() {
        let content = serde_json::to_string_pretty(&fallback).map_err(|err| err.to_string())?;
        return Ok(WebToolsConfigFileResult {
            scope: scope.to_string(),
            path: target.to_string_lossy().to_string(),
            exists: false,
            content,
        });
    }
    if !target.is_file() {
        return Err("web-tools 配置路径不是文件".to_string());
    }
    let content =
        fs::read_to_string(&target).map_err(|err| format!("无法读取 web-tools 配置：{err}"))?;
    Ok(WebToolsConfigFileResult {
        scope: scope.to_string(),
        path: target.to_string_lossy().to_string(),
        exists: true,
        content,
    })
}

fn write_web_tools_config_file(
    scope: &str,
    target: PathBuf,
    content: String,
) -> Result<WebToolsConfigFileResult, String> {
    let normalized = validate_web_tools_config_content(&content)?;
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("无法创建 web-tools 配置目录：{err}"))?;
    }
    fs::write(&target, format!("{normalized}\n"))
        .map_err(|err| format!("无法写入 web-tools 配置：{err}"))?;
    Ok(WebToolsConfigFileResult {
        scope: scope.to_string(),
        path: target.to_string_lossy().to_string(),
        exists: true,
        content: format!("{normalized}\n"),
    })
}

fn validate_json_object_config_content(content: &str, label: &str) -> Result<String, String> {
    let raw = content.trim();
    let parsed: Value = serde_json::from_str(if raw.is_empty() || raw == "undefined" {
        "{}"
    } else {
        raw
    })
    .map_err(|err| format!("{label}配置 JSON 解析失败：{err}"))?;
    if !parsed.is_object() {
        return Err(format!("{label}配置必须是 JSON 对象"));
    }
    serde_json::to_string_pretty(&parsed).map_err(|err| err.to_string())
}

fn read_json_object_config_file(
    scope: &str,
    target: PathBuf,
    fallback: Value,
    label: &str,
) -> Result<WebToolsConfigFileResult, String> {
    if !target.exists() {
        let content = serde_json::to_string_pretty(&fallback).map_err(|err| err.to_string())?;
        return Ok(WebToolsConfigFileResult {
            scope: scope.to_string(),
            path: target.to_string_lossy().to_string(),
            exists: false,
            content,
        });
    }
    if !target.is_file() {
        return Err(format!("{label}配置路径不是文件"));
    }
    let content =
        fs::read_to_string(&target).map_err(|err| format!("无法读取{label}配置：{err}"))?;
    Ok(WebToolsConfigFileResult {
        scope: scope.to_string(),
        path: target.to_string_lossy().to_string(),
        exists: true,
        content,
    })
}

fn write_json_object_config_file(
    scope: &str,
    target: PathBuf,
    content: String,
    label: &str,
) -> Result<WebToolsConfigFileResult, String> {
    let normalized = validate_json_object_config_content(&content, label)?;
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("无法创建{label}配置目录：{err}"))?;
    }
    fs::write(&target, format!("{normalized}\n"))
        .map_err(|err| format!("无法写入{label}配置：{err}"))?;
    Ok(WebToolsConfigFileResult {
        scope: scope.to_string(),
        path: target.to_string_lossy().to_string(),
        exists: true,
        content: format!("{normalized}\n"),
    })
}

fn open_external_url_with_system(url: &str) -> Result<bool, String> {
    #[cfg(target_os = "macos")]
    let status = Command::new("open")
        .arg(url)
        .status()
        .map_err(|err| format!("打开外部浏览器失败：{err}"))?;

    #[cfg(target_os = "windows")]
    let status = Command::new("rundll32")
        .args(["url.dll,FileProtocolHandler", url])
        .status()
        .map_err(|err| format!("打开外部浏览器失败：{err}"))?;

    #[cfg(all(unix, not(target_os = "macos")))]
    let status = Command::new("xdg-open")
        .arg(url)
        .status()
        .map_err(|err| format!("打开外部浏览器失败：{err}"))?;

    Ok(status.success())
}

fn workspace_relative_path(root: &Path, path: &Path) -> String {
    let value = path
        .strip_prefix(root)
        .map(|value| value.to_string_lossy().to_string())
        .unwrap_or_else(|_| {
            path.file_name()
                .map(|value| value.to_string_lossy().to_string())
                .unwrap_or_default()
        });
    value.replace('\\', "/")
}

fn count_text_lines(value: &str) -> usize {
    if value.is_empty() {
        0
    } else {
        value.lines().count()
    }
}

fn text_fingerprint(value: &str) -> String {
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in value.as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("fnv1a64:{hash:016x}")
}

fn classify_workspace_file_write_risk(exists: bool, current_size: u64, next_size: u64) -> String {
    if !exists {
        return "medium".to_string();
    }
    let max_size = current_size.max(next_size);
    let delta = current_size.abs_diff(next_size);
    if max_size > 1024 * 1024 || delta > 256 * 1024 {
        "high".to_string()
    } else {
        "medium".to_string()
    }
}

fn hidden_file_weight(name: &str) -> u8 {
    if matches!(name, ".git" | "node_modules" | ".venv" | "__pycache__") {
        1
    } else {
        0
    }
}

struct GitReadResult {
    exit_code: i32,
    stdout: String,
    stderr: String,
}

fn build_git_path_args(base_args: &[&str], path_filter: &[&str]) -> Vec<String> {
    let mut args = base_args
        .iter()
        .map(|value| value.to_string())
        .collect::<Vec<_>>();
    args.push("--".to_string());
    args.extend(path_filter.iter().map(|value| value.to_string()));
    args
}

fn run_git_readonly(root: &Path, args: &[String]) -> GitReadResult {
    match Command::new("git")
        .arg("--no-pager")
        .args(args)
        .current_dir(root)
        .env("GIT_PAGER", "cat")
        .env("PAGER", "cat")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
    {
        Ok(output) => GitReadResult {
            exit_code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        },
        Err(err) => GitReadResult {
            exit_code: -1,
            stdout: String::new(),
            stderr: err.to_string(),
        },
    }
}

fn runner_permission_decision_store_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    fs::create_dir_all(&app_data_dir).map_err(|err| err.to_string())?;
    Ok(app_data_dir.join("runner-permission-decisions.json"))
}

fn read_runner_permission_decisions(
    app: &tauri::AppHandle,
) -> Result<Vec<RunnerPermissionDecisionRecord>, String> {
    let path = runner_permission_decision_store_path(app)?;
    match fs::read_to_string(path) {
        Ok(content) if content.trim().is_empty() => Ok(Vec::new()),
        Ok(content) => serde_json::from_str(&content).map_err(|err| err.to_string()),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(Vec::new()),
        Err(err) => Err(err.to_string()),
    }
}

fn write_runner_permission_decisions(
    app: &tauri::AppHandle,
    records: &[RunnerPermissionDecisionRecord],
) -> Result<(), String> {
    let path = runner_permission_decision_store_path(app)?;
    let content = serde_json::to_string_pretty(records).map_err(|err| err.to_string())?;
    fs::write(path, content).map_err(|err| err.to_string())
}

fn desktop_file_drag_drop_payload(event: &tauri::DragDropEvent) -> Option<Value> {
    match event {
        tauri::DragDropEvent::Enter { paths, position } => Some(json!({
            "type": "enter",
            "paths": paths
                .iter()
                .map(|path| path.to_string_lossy().to_string())
                .collect::<Vec<_>>(),
            "position": { "x": position.x, "y": position.y },
        })),
        tauri::DragDropEvent::Over { position } => Some(json!({
            "type": "over",
            "paths": Vec::<String>::new(),
            "position": { "x": position.x, "y": position.y },
        })),
        tauri::DragDropEvent::Drop { paths, position } => Some(json!({
            "type": "drop",
            "paths": paths
                .iter()
                .map(|path| path.to_string_lossy().to_string())
                .collect::<Vec<_>>(),
            "position": { "x": position.x, "y": position.y },
        })),
        tauri::DragDropEvent::Leave => Some(json!({
            "type": "leave",
            "paths": Vec::<String>::new(),
        })),
        _ => None,
    }
}

fn desktop_file_drag_drop_log_path() -> PathBuf {
    std::env::temp_dir().join("ai-employee-desktop-file-drag-drop.log")
}

fn log_desktop_file_drag_drop(payload: &Value) {
    let line = format!(
        "{} {}\n",
        chrono::Local::now().format("%Y-%m-%d %H:%M:%S%.3f"),
        payload
    );
    eprintln!("[desktop-file-drag-drop] {}", payload);
    if let Ok(mut file) = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(desktop_file_drag_drop_log_path())
    {
        let _ = file.write_all(line.as_bytes());
    }
}

fn emit_desktop_file_drag_drop<R: tauri::Runtime, E: tauri::Emitter<R>>(
    emitter: &E,
    payload: &Value,
) {
    log_desktop_file_drag_drop(payload);
    if let Err(error) = emitter.emit("desktop-file-drag-drop", payload) {
        eprintln!("[desktop-file-drag-drop] event emit failed: {error}");
    }
}

fn dispatch_desktop_file_drag_drop_dom<R: tauri::Runtime>(
    webviews: impl IntoIterator<Item = tauri::Webview<R>>,
    payload: &Value,
) {
    let script = format!(
        r#"(function(){{
  try {{
    var payload = {payload};
    window.__AI_EMPLOYEE_NATIVE_DRAG__ = payload;
    window.dispatchEvent(new CustomEvent("ai-employee-native-file-drag-drop", {{ detail: payload }}));
  }} catch (error) {{
    console.warn("[desktop-file-drag-drop] DOM dispatch failed", error);
  }}
}})();"#
    );
    for webview in webviews {
        if let Err(error) = webview.eval(&script) {
            eprintln!("[desktop-file-drag-drop] eval failed: {error}");
        }
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_updater::Builder::new()
                .pubkey(DESKTOP_UPDATE_PUBLIC_KEY)
                .build(),
        )
        .on_window_event(|window, event| {
            let tauri::WindowEvent::DragDrop(drag_event) = event else {
                return;
            };
            if let Some(payload) = desktop_file_drag_drop_payload(drag_event) {
                emit_desktop_file_drag_drop(window, &payload);
                emit_desktop_file_drag_drop(window.app_handle(), &payload);
                dispatch_desktop_file_drag_drop_dom(window.webviews(), &payload);
            }
        })
        .on_webview_event(|webview, event| {
            let tauri::WebviewEvent::DragDrop(drag_event) = event else {
                return;
            };
            if let Some(payload) = desktop_file_drag_drop_payload(drag_event) {
                emit_desktop_file_drag_drop(webview, &payload);
                emit_desktop_file_drag_drop(webview.app_handle(), &payload);
                dispatch_desktop_file_drag_drop_dom(std::iter::once(webview.clone()), &payload);
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_desktop_version,
            check_desktop_update,
            install_desktop_update,
            pick_workspace_directory,
            detect_executors,
            get_runtime_info,
            list_workspace_files,
            read_workspace_file,
            delete_workspace_file,
            delete_workspace_directory,
            preview_workspace_diff,
            prepare_workspace_file_write,
            write_workspace_file,
            list_workspace_file_changes,
            accept_workspace_file_change,
            revert_workspace_file_change,
            read_global_mcp_config_file,
            write_global_mcp_config_file,
            read_project_mcp_config_file,
            write_project_mcp_config_file,
            read_global_web_tools_config_file,
            write_global_web_tools_config_file,
            read_project_web_tools_config_file,
            write_project_web_tools_config_file,
            read_global_bot_connector_config_file,
            write_global_bot_connector_config_file,
            read_global_project_catalog_file,
            write_global_project_catalog_file,
            read_global_ftp_credentials_file,
            write_global_ftp_credentials_file,
            open_external_url,
            copy_resource_file_to_clipboard,
            save_resource_file,
            persist_project_chat_asset,
            read_local_file,
            open_desktop_devtools,
            classify_runner_command,
            run_runner_command,
            record_runner_permission_decision,
            list_runner_permission_decisions,
            discover_provider_models,
            test_provider_model,
            liuagent_builtin_tool_definitions,
            liuagent_execute_tool,
            liuagent_upload_provider_file,
            liuagent_start_local_chat,
            liuagent_pause_local_chat,
            liuagent_classify_permission_reply,
            bot_start_feishu_local_listener,
            bot_stop_feishu_local_listener,
            bot_list_feishu_local_listeners,
            bot_scan_feishu_chats,
            liuagent_prepare_agent_invocation,
            liuagent_recover_runtime_state,
            liuagent_refresh_runtime_job,
            liuagent_cancel_runtime_job,
            liuagent_list_runtime_events,
            liuagent_list_runtime_outbox,
            liuagent_ack_runtime_outbox,
            liuagent_save_offline_cache,
            liuagent_load_offline_cache,
            liuagent_cleanup_offline_cache,
            project_chat_store::project_chat_list_sessions,
            project_chat_store::project_chat_list_all_sessions,
            project_chat_store::project_chat_upsert_session,
            project_chat_store::project_chat_replace_sessions,
            project_chat_store::project_chat_read_runtime,
            project_chat_store::project_chat_read_message_snapshot,
            project_chat_store::project_chat_write_runtime,
            project_chat_store::project_chat_delete_session,
            project_chat_store::local_ai_task_list,
            project_chat_store::local_ai_task_replace,
            project_chat_store::local_record_list,
            project_chat_store::local_record_write,
            project_chat_store::agent_supervision_search_answers,
            project_chat_store::agent_supervision_get_answer,
            project_chat_store::agent_supervision_find_answer
        ])
        .setup(|app| {
            let plugin_registry = liuagent_core::plugin_system::builtin_plugins_registry()
                .map_err(|error| error.to_string())?;
            let plugin_snapshot = plugin_registry.snapshot();
            eprintln!(
                "[plugin-registry] registered {} builtin plugin(s), {} capability(ies)",
                plugin_snapshot.plugins.len(),
                plugin_snapshot.capabilities.len()
            );
            app.manage(plugin_registry);

            if let (Some(window), Some(icon)) = (
                app.get_webview_window("main"),
                app.default_window_icon().cloned(),
            ) {
                window.set_icon(icon)?;
            }
            #[cfg(debug_assertions)]
            {
                let app_handle = app.handle().clone();
                let open_inspector = MenuItem::with_id(
                    &app_handle,
                    "open_web_inspector",
                    "打开 Web Inspector",
                    true,
                    Some("CmdOrCtrl+Alt+I"),
                )?;
                let developer_menu = Submenu::with_id_and_items(
                    &app_handle,
                    "developer",
                    "开发",
                    true,
                    &[&open_inspector],
                )?;
                let menu = Menu::default(&app_handle)?;
                menu.append(&developer_menu)?;
                app_handle.set_menu(menu)?;
                app_handle.on_menu_event(|app_handle, event| {
                    if event.id() == "open_web_inspector" {
                        if let Some(window) = app_handle.get_webview_window("main") {
                            window.open_devtools();
                        }
                    }
                });
            }
            bot::feishu::start_persisted_local_listeners(app.handle().clone());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running AI Employee Factory desktop app");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clipboard_resource_helpers_decode_and_name_files() {
        let (bytes, mime_type) =
            decode_clipboard_data_url("data:image/png;base64,QUJDRA==", "application/octet-stream")
                .unwrap();
        assert_eq!(bytes, b"ABCD");
        assert_eq!(mime_type, "image/png");
        assert_eq!(
            resolve_clipboard_file_name("", "https://example.test/files/demo.png?x=1", ""),
            "demo.png"
        );
        assert_eq!(
            resolve_clipboard_file_name("liuAgent 图片", "data:image/png;base64,AAAA", "image/png"),
            "liuAgent 图片.png"
        );
        assert_eq!(
            sanitize_clipboard_file_name("../不安全/文件?.png"),
            "_不安全_文件_.png"
        );
        assert_eq!(
            project_chat_asset_path_component("用户-1"),
            "e794a8e688b72d31"
        );
        assert_eq!(normalize_project_chat_asset_kind("", "video/mp4"), "video");
    }

    #[test]
    fn desktop_update_endpoint_accepts_http_and_https() {
        let http =
            desktop_update_endpoint("http://127.0.0.1:8000/api/desktop-updates/latest").unwrap();
        assert_eq!(http.scheme(), "http");
        assert!(http.as_str().contains("target={{target}}"));

        let https =
            desktop_update_endpoint("https://updates.example.com/api/desktop-updates/latest")
                .unwrap();
        assert_eq!(https.scheme(), "https");

        assert!(desktop_update_endpoint("ftp://updates.example.com/latest").is_err());
    }

    #[test]
    fn workspace_write_rejects_stale_hash_and_supports_revert() {
        let root = std::env::temp_dir().join(format!(
            "ai-employee-diff-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let root = fs::canonicalize(root).unwrap();
        let target = root.join("sample.txt");
        fs::write(&target, "before\n").unwrap();
        let baseline_hash = text_fingerprint("before\n");
        let saved = write_workspace_file(
            root.to_string_lossy().to_string(),
            "sample.txt".to_string(),
            "after\n".to_string(),
            baseline_hash,
        )
        .unwrap();
        assert_eq!(fs::read_to_string(&target).unwrap(), "after\n");
        let changes = liuagent_core::list_changes(&root).unwrap();
        assert_eq!(changes.len(), 1);
        assert_eq!(changes[0].path, "sample.txt");
        assert_eq!(changes[0].review_status, "pending");
        assert!(write_workspace_file(
            root.to_string_lossy().to_string(),
            "sample.txt".to_string(),
            "stale\n".to_string(),
            text_fingerprint("before\n"),
        )
        .is_err());
        liuagent_core::revert_change(&root, "sample.txt", &saved.content_hash).unwrap();
        assert_eq!(fs::read_to_string(&target).unwrap(), "before\n");
        assert!(liuagent_core::list_changes(&root).unwrap().is_empty());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn workspace_write_creates_new_file_and_tracks_baseline() {
        let root = std::env::temp_dir().join(format!(
            "ai-employee-new-file-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let root = fs::canonicalize(root).unwrap();
        let saved = write_workspace_file(
            root.to_string_lossy().to_string(),
            "AIENTRY.md".to_string(),
            "# AIENTRY.md\n".to_string(),
            String::new(),
        )
        .unwrap();
        assert_eq!(saved.path, "AIENTRY.md");
        assert_eq!(
            fs::read_to_string(root.join("AIENTRY.md")).unwrap(),
            "# AIENTRY.md\n"
        );
        let changes = liuagent_core::list_changes(&root).unwrap();
        assert_eq!(changes.len(), 1);
        assert_eq!(changes[0].change_type, "added");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn workspace_directory_delete_removes_nested_agent_files_without_removing_root() {
        let root = std::env::temp_dir().join(format!(
            "ai-employee-delete-agent-directory-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let agent_directory = root.join("agents").join("frontend-architect");
        fs::create_dir_all(agent_directory.join("resources")).unwrap();
        fs::write(agent_directory.join("AGENT.md"), "# Frontend Architect\n").unwrap();
        fs::write(
            agent_directory.join("resources").join("notes.md"),
            "keep no residue",
        )
        .unwrap();
        let root = fs::canonicalize(root).unwrap();

        assert!(delete_workspace_directory(
            root.to_string_lossy().to_string(),
            "agents/frontend-architect".to_string(),
        )
        .unwrap());
        assert!(root.exists());
        assert!(!root.join("agents").join("frontend-architect").exists());
        assert!(!delete_workspace_directory(
            root.to_string_lossy().to_string(),
            "agents/frontend-architect".to_string(),
        )
        .unwrap());
        assert!(
            delete_workspace_directory(root.to_string_lossy().to_string(), String::new()).is_err()
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn workspace_read_reports_missing_nested_file_consistently() {
        let root = std::env::temp_dir().join(format!(
            "ai-employee-missing-read-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let root = fs::canonicalize(root).unwrap();

        let result = read_workspace_file(
            root.to_string_lossy().to_string(),
            "agents/local-agent-test/AGENT.md".to_string(),
        );

        assert!(matches!(result, Err(ref error) if error == "文件不存在"));
        let saved = write_workspace_file(
            root.to_string_lossy().to_string(),
            "agents/local-agent-test/AGENT.md".to_string(),
            "# Test Agent\n".to_string(),
            String::new(),
        )
        .unwrap();
        assert_eq!(saved.path, "agents/local-agent-test/AGENT.md");
        assert_eq!(
            fs::read_to_string(root.join("agents/local-agent-test/AGENT.md")).unwrap(),
            "# Test Agent\n"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn workspace_write_creates_empty_file_in_missing_workspace() {
        let root = std::env::temp_dir().join(format!(
            "ai-employee-empty-entry-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        assert!(!root.exists());

        let saved = write_workspace_file(
            root.to_string_lossy().to_string(),
            "rules\\AIENTRY.md".to_string(),
            String::new(),
            String::new(),
        )
        .unwrap();

        assert_eq!(saved.path, "rules/AIENTRY.md");
        assert_eq!(saved.size, 0);
        assert!(root.join("rules\\AIENTRY.md").is_file());
        assert_eq!(
            fs::read(root.join("rules\\AIENTRY.md")).unwrap(),
            Vec::<u8>::new()
        );
        fs::remove_dir_all(root).unwrap();
    }
}
