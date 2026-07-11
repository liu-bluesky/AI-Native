//! Project deploy tools.
//!
//! These tools let the desktop agent read deploy configuration and directly
//! deploy workspace files. Credentials are supplied by the backend deploy
//! settings, not by the model prompt.

use chrono::Local;
use reqwest::blocking::Client;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION};
use reqwest::Url;
use serde_json::{json, Value};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use crate::liuagent_core::args::{bool_arg, number_arg, required_string_arg, string_arg};
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};
use crate::liuagent_core::workspace::{
    resolve_workspace_child, resolve_workspace_root, workspace_relative_path,
};

const MAX_UPLOAD_BYTES: u64 = 200 * 1024 * 1024;
const MAX_UPLOAD_FILES: usize = 20_000;

#[derive(Debug)]
struct UploadEntry {
    path: PathBuf,
    upload_path: String,
    original_path: String,
    name: String,
    size: u64,
}

#[derive(Debug)]
enum UploadSource {
    File {
        path: PathBuf,
        relative_path: String,
        size: u64,
    },
    Directory {
        entries: Vec<UploadEntry>,
        root_directory: String,
        display_path: String,
        total_size: u64,
    },
}

impl UploadSource {
    fn size(&self) -> u64 {
        match self {
            Self::File { size, .. } => *size,
            Self::Directory { total_size, .. } => *total_size,
        }
    }

    fn display_path(&self) -> &str {
        match self {
            Self::File { relative_path, .. } => relative_path,
            Self::Directory { display_path, .. } => display_path,
        }
    }

    fn file_count(&self) -> usize {
        match self {
            Self::File { .. } => 1,
            Self::Directory { entries, .. } => entries.len(),
        }
    }

    fn source_type(&self) -> &str {
        match self {
            Self::File { .. } => "file",
            Self::Directory { .. } => "directory",
        }
    }
}

pub fn get_project_deploy_options(arguments: &Value) -> Result<(Value, String), ToolError> {
    let api_base_url = string_arg(arguments, "_backend_api_base_url", "");
    let backend_token = string_arg(arguments, "_backend_token", "");
    if api_base_url.is_empty() || backend_token.is_empty() {
        return Err(ToolError::new(
            "deploy.backend_context_missing",
            "缺少后端连接上下文，不能读取项目部署配置",
        ));
    }
    let project_id = required_string_arg(arguments, "project_id")?;
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let endpoint = deploy_options_url(&api_base_url, &project_id)?;

    let mut headers = HeaderMap::new();
    let auth =
        HeaderValue::from_str(&format!("Bearer {}", backend_token.trim())).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid backend auth header: {err}"),
            )
        })?;
    headers.insert(AUTHORIZATION, auth);
    let client = Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create http client failed: {err}"),
            )
        })?;
    let response = client
        .get(endpoint.clone())
        .headers(headers)
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read deploy options failed: {err}"),
            )
        })?;
    let status = response.status().as_u16();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read deploy options response failed: {err}"),
        )
    })?;
    let body = serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({"raw": text}));
    if !(200..300).contains(&status) {
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "read deploy options failed with HTTP {status}: {}",
                safe_error_detail(&body)
            ),
        ));
    }

    let configured = body
        .get("configured")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let profile_count = body
        .get("profiles")
        .and_then(Value::as_array)
        .map(Vec::len)
        .unwrap_or(0);
    let summary = if configured {
        format!("已读取项目 {project_id} 的部署配置：{profile_count} 个环境档位")
    } else {
        format!("项目 {project_id} 未启用或未配置部署档位")
    };

    Ok((
        json!({
            "status": status,
            "project_id": project_id,
            "response": body,
        }),
        summary,
    ))
}

pub fn deploy_workspace_files_to_target(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let api_base_url = string_arg(arguments, "_backend_api_base_url", "");
    let backend_token = string_arg(arguments, "_backend_token", "");
    if api_base_url.is_empty() || backend_token.is_empty() {
        return Err(ToolError::new(
            "deploy.backend_context_missing",
            "缺少后端连接上下文，不能从桌面端直连部署",
        ));
    }
    let project_id = required_string_arg(arguments, "project_id")?;
    let workspace_root = resolve_workspace_root(workspace_path)?;
    let upload_source = upload_source_arg(&workspace_root, arguments)?;
    if upload_source.size() == 0 {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "deploy source is empty",
        ));
    }
    if upload_source.size() > MAX_UPLOAD_BYTES {
        return Err(ToolError::new(
            "tool.output_too_large",
            format!("deploy source is larger than {} bytes", MAX_UPLOAD_BYTES),
        ));
    }

    let profile = string_arg(arguments, "profile", "prod");
    let component = string_arg(arguments, "component", "");
    let artifact_name = string_arg(arguments, "artifact_name", "")
        .trim()
        .to_string();
    let artifact_name = if artifact_name.is_empty() {
        default_artifact_name(&upload_source)
    } else {
        Path::new(&artifact_name)
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("deploy-source")
            .to_string()
    };
    let artifact_kind = string_arg(arguments, "artifact_kind", "source-bundle");
    let version = string_arg(arguments, "version", "");
    let requirement = string_arg(arguments, "requirement", "");
    let plan = string_arg(arguments, "plan", "");
    let chat_session_id = string_arg(arguments, "chat_session_id", "");
    let task_tree_node_id = string_arg(arguments, "task_tree_node_id", "");
    let target_ids = target_ids_arg(arguments);
    let timeout_ms = number_arg(arguments, "timeout_ms", 600_000, 1_000, 1_800_000) as u64;
    let run_deploy_command = bool_arg(arguments, "run_deploy_command", true);
    let manifest = upload_manifest_arg(arguments, &upload_source)?;
    let relative_path = upload_source.display_path().to_string();

    require_approval(
        tool_call_id,
        "deploy.direct.upload",
        "high",
        "network",
        &format!(
            "通过桌面智能体把 {} 直接部署到项目 {} 的已配置目标",
            relative_path, project_id
        ),
        json!({
            "project_id": project_id,
            "profile": profile,
            "component": component,
            "artifact_path": relative_path,
            "artifact_name": artifact_name,
            "artifact_kind": artifact_kind,
            "source_type": upload_source.source_type(),
            "file_count": upload_source.file_count(),
            "size": upload_source.size(),
            "target_ids": target_ids,
            "run_deploy_command": run_deploy_command,
            "timeout_ms": timeout_ms,
            "requirement": requirement,
            "plan": plan,
        }),
        permission_decision,
    )?;

    let mut headers = HeaderMap::new();
    let auth =
        HeaderValue::from_str(&format!("Bearer {}", backend_token.trim())).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid backend auth header: {err}"),
            )
        })?;
    headers.insert(AUTHORIZATION, auth);
    let client = Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create http client failed: {err}"),
            )
        })?;
    let prepare_endpoint = direct_deploy_prepare_url(&api_base_url, &project_id)?;
    let prepare_response = client
        .post(prepare_endpoint)
        .headers(headers.clone())
        .json(&json!({
            "profile": profile,
            "component": component,
            "target_ids": target_ids,
        }))
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("prepare direct deploy failed: {err}"),
            )
        })?;
    let prepare_status = prepare_response.status().as_u16();
    let prepare_text = prepare_response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read direct deploy prepare response failed: {err}"),
        )
    })?;
    let prepare_body = serde_json::from_str::<Value>(&prepare_text)
        .unwrap_or_else(|_| json!({"raw": prepare_text}));
    if !(200..300).contains(&prepare_status) {
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "prepare direct deploy failed with HTTP {prepare_status}: {}",
                safe_error_detail(&prepare_body)
            ),
        ));
    }
    let prepared_targets = prepare_body
        .get("targets")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut upload_results = Vec::new();
    for target in prepared_targets {
        upload_results.push(upload_source_to_ftp(&upload_source, &target)?);
    }

    let complete_endpoint = direct_deploy_complete_url(&api_base_url, &project_id)?;
    let response = client
        .post(complete_endpoint)
        .headers(headers)
        .json(&json!({
            "profile": profile,
            "component": component,
            "target_ids": target_ids,
            "artifact_name": artifact_name,
            "artifact_kind": artifact_kind,
            "version": version,
            "size": upload_source.size(),
            "file_count": upload_source.file_count(),
            "manifest": manifest,
            "run_deploy_command": run_deploy_command,
            "chat_session_id": chat_session_id,
            "task_tree_node_id": task_tree_node_id,
            "requirement": requirement,
            "plan": plan,
            "upload_results": upload_results,
        }))
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("complete direct deploy failed: {err}"),
            )
        })?;
    let status = response.status().as_u16();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read direct deploy completion failed: {err}"),
        )
    })?;
    let body = serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({"raw": text}));
    if !(200..300).contains(&status) {
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "complete direct deploy failed with HTTP {status}: {}",
                safe_error_detail(&body)
            ),
        ));
    }

    let deployment_status = body.get("status").and_then(Value::as_str).unwrap_or("");
    let deployment_id = body.get("run_id").and_then(Value::as_str).unwrap_or("");
    let deployment_confirmed_success = body
        .get("deployment_confirmed_success")
        .and_then(Value::as_bool)
        .unwrap_or(deployment_status == "success");
    let summary = direct_deploy_summary(deployment_id, deployment_status, &relative_path);

    Ok((
        json!({
            "status": status,
            "project_id": project_id,
            "profile": profile,
            "component": component,
            "artifact_path": relative_path,
            "artifact_name": artifact_name,
            "artifact_kind": artifact_kind,
            "source_type": upload_source.source_type(),
            "file_count": upload_source.file_count(),
            "size": upload_source.size(),
            "deployment_id": deployment_id,
            "deployment_status": deployment_status,
            "deployment_confirmed_success": deployment_confirmed_success,
            "deployment_claim_policy": if deployment_confirmed_success {
                "deployment_success_may_be_reported"
            } else {
                "direct_deploy_not_success_do_not_claim_deployment_success"
            },
            "response": body,
        }),
        summary,
    ))
}

fn upload_source_to_ftp(source: &UploadSource, target: &Value) -> Result<Value, ToolError> {
    let host = target
        .get("host")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    let port = target.get("port").and_then(Value::as_u64).unwrap_or(21);
    let username = target
        .get("username")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let password = target
        .get("password")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let remote_path = target
        .get("remote_path")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let max_threads = target
        .get("max_upload_threads")
        .and_then(Value::as_u64)
        .unwrap_or(4)
        .clamp(1, 32) as usize;
    if host.is_empty() || username.is_empty() || password.is_empty() || remote_path.is_empty() {
        return Err(ToolError::new(
            "deploy.ftp_config_missing",
            "桌面直连 FTP 配置不完整",
        ));
    }
    let backup_source_path = match source {
        UploadSource::File { relative_path, .. } => [
            remote_path.trim_end_matches('/'),
            Path::new(relative_path)
                .file_name()
                .and_then(|value| value.to_str())
                .unwrap_or("deploy-file"),
        ]
        .into_iter()
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>()
        .join("/"),
        UploadSource::Directory { .. } => remote_path.clone(),
    };
    let backup =
        curl_ftp_backup_remote_path(host, port, &username, &password, &backup_source_path)?;
    let files = match source {
        UploadSource::File {
            path,
            relative_path,
            size,
        } => vec![(
            path.clone(),
            Path::new(relative_path)
                .file_name()
                .and_then(|v| v.to_str())
                .unwrap_or("deploy-file")
                .to_string(),
            *size,
        )],
        UploadSource::Directory { entries, .. } => entries
            .iter()
            .map(|entry| (entry.path.clone(), entry.upload_path.clone(), entry.size))
            .collect(),
    };
    let mut groups: std::collections::BTreeMap<String, Vec<(PathBuf, String, u64)>> =
        std::collections::BTreeMap::new();
    for file in files {
        let root = file.1.split('/').next().unwrap_or(&file.1).to_string();
        groups.entry(root).or_default().push(file);
    }
    let tasks = Arc::new(Mutex::new(groups.into_values().collect::<Vec<_>>()));
    let root_task_count = tasks.lock().map(|items| items.len()).unwrap_or(0);
    let uploaded = Arc::new(Mutex::new(Vec::<Value>::new()));
    let worker_count = max_threads.min(root_task_count).max(1);
    let mut workers = Vec::new();
    for _ in 0..worker_count {
        let tasks = Arc::clone(&tasks);
        let uploaded = Arc::clone(&uploaded);
        let host = host.to_string();
        let username = username.clone();
        let password = password.clone();
        let remote_path = remote_path.clone();
        workers.push(thread::spawn(move || -> Result<(), String> {
            loop {
                let task = tasks
                    .lock()
                    .map_err(|_| "FTP任务队列不可用".to_string())?
                    .pop();
                let Some(files) = task else { break };
                curl_ftp_upload_task(&host, port, &username, &password, &remote_path, &files)?;
                for (_, relative_path, size) in files {
                    uploaded
                        .lock()
                        .map_err(|_| "FTP结果队列不可用".to_string())?
                        .push(json!({"path": relative_path, "size": size}));
                }
            }
            Ok(())
        }));
    }
    for worker in workers {
        worker
            .join()
            .map_err(|_| ToolError::new("tool.execution_failed", "FTP上传线程异常退出"))?
            .map_err(|error| ToolError::new("tool.execution_failed", error))?;
    }
    let uploaded_files = uploaded
        .lock()
        .map_err(|_| ToolError::new("tool.execution_failed", "FTP上传结果不可用"))?
        .clone();
    Ok(json!({
        "ok": true,
        "target_id": target.get("id").and_then(Value::as_str).unwrap_or(""),
        "file_count": uploaded_files.len(),
        "root_task_count": root_task_count,
        "worker_count": worker_count,
        "max_upload_threads": max_threads,
        "backup_status": backup.get("status").and_then(Value::as_str).unwrap_or(""),
        "backup_path": backup.get("path").and_then(Value::as_str).unwrap_or(""),
        "backup_at": backup.get("at").and_then(Value::as_str).unwrap_or(""),
        "files": uploaded_files.into_iter().take(200).collect::<Vec<_>>(),
    }))
}

fn curl_ftp_backup_remote_path(
    host: &str,
    port: u64,
    username: &str,
    password: &str,
    remote_path: &str,
) -> Result<Value, ToolError> {
    let backup_path = ftp_backup_path(remote_path);
    let root_url = ftp_remote_url(host, port, "", "")
        .map_err(|error| ToolError::new("tool.execution_failed", error))?;
    let config = format!(
        "silent\nshow-error\nfail\nuser = \"{}:{}\"\nquote = \"RNFR {}\"\nquote = \"RNTO {}\"\nurl = \"{}\"\n",
        curl_config_escape(username),
        curl_config_escape(password),
        curl_config_escape(remote_path),
        curl_config_escape(&backup_path),
        curl_config_escape(&root_url),
    );
    let mut child = Command::new("curl")
        .args(["--config", "-"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| {
            ToolError::new("tool.execution_failed", format!("启动FTP备份失败：{error}"))
        })?;
    if let Some(stdin) = child.stdin.as_mut() {
        stdin.write_all(config.as_bytes()).map_err(|error| {
            ToolError::new(
                "tool.execution_failed",
                format!("写入FTP备份任务失败：{error}"),
            )
        })?;
    }
    let output = child.wait_with_output().map_err(|error| {
        ToolError::new("tool.execution_failed", format!("等待FTP备份失败：{error}"))
    })?;
    let now = Local::now();
    if output.status.success() {
        return Ok(json!({
            "status": "renamed",
            "path": backup_path,
            "at": now.to_rfc3339(),
        }));
    }
    let error = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if error.contains("550") || error.to_lowercase().contains("not found") {
        return Ok(json!({"status": "missing", "path": "", "at": ""}));
    }
    Err(ToolError::new(
        "tool.execution_failed",
        format!("FTP备份远端目录失败：{error}"),
    ))
}

fn ftp_backup_path(remote_path: &str) -> String {
    let normalized = remote_path.trim().trim_end_matches('/');
    let (parent, name) = normalized
        .rsplit_once('/')
        .map(|(parent, name)| (parent, name))
        .unwrap_or(("", normalized));
    let backup_name = format!(
        "{}_备份_{}",
        if name.is_empty() { normalized } else { name },
        Local::now().format("%Y年%m月%d日_%H时%M分%S秒")
    );
    if parent.is_empty() {
        backup_name
    } else {
        format!("{parent}/{backup_name}")
    }
}

fn curl_ftp_upload_task(
    host: &str,
    port: u64,
    username: &str,
    password: &str,
    remote_root: &str,
    files: &[(PathBuf, String, u64)],
) -> Result<(), String> {
    if files.is_empty() {
        return Ok(());
    }
    let config = curl_ftp_task_config(host, port, username, password, remote_root, files)?;
    let mut child = Command::new("curl")
        .args(["--config", "-"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("启动FTP上传失败：{error}"))?;
    if let Some(stdin) = child.stdin.as_mut() {
        stdin
            .write_all(config.as_bytes())
            .map_err(|error| format!("写入FTP任务失败：{error}"))?;
    }
    let output = child
        .wait_with_output()
        .map_err(|error| format!("等待FTP上传失败：{error}"))?;
    if output.status.success() {
        Ok(())
    } else {
        Err(format!(
            "FTP上传失败：{}",
            String::from_utf8_lossy(&output.stderr).trim()
        ))
    }
}

fn curl_ftp_task_config(
    host: &str,
    port: u64,
    username: &str,
    password: &str,
    remote_root: &str,
    files: &[(PathBuf, String, u64)],
) -> Result<String, String> {
    let mut config = String::from("silent\nshow-error\nfail\nftp-create-dirs\n");
    config.push_str(&format!(
        "user = \"{}:{}\"\n",
        curl_config_escape(username),
        curl_config_escape(password)
    ));
    for (local_path, relative_path, _) in files {
        let remote = ftp_remote_url(host, port, remote_root, relative_path)?;
        config.push_str(&format!(
            "upload-file = \"{}\"\nurl = \"{}\"\n",
            curl_config_escape(&local_path.to_string_lossy()),
            curl_config_escape(&remote)
        ));
    }
    Ok(config)
}

fn ftp_remote_url(
    host: &str,
    port: u64,
    remote_root: &str,
    relative_path: &str,
) -> Result<String, String> {
    let mut url = Url::parse(&format!("ftp://{host}:{port}/"))
        .map_err(|error| format!("FTP服务器地址无效：{error}"))?;
    let remote_path = [
        remote_root.trim_matches('/'),
        relative_path.trim_matches('/'),
    ]
    .into_iter()
    .filter(|value| !value.is_empty())
    .collect::<Vec<_>>()
    .join("/");
    url.set_path(&remote_path);
    Ok(url.to_string())
}

fn curl_config_escape(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace(['\r', '\n'], "")
}

fn upload_source_arg(workspace_root: &Path, arguments: &Value) -> Result<UploadSource, ToolError> {
    let explicit_paths = string_list_arg(arguments, "artifact_paths");
    if !explicit_paths.is_empty() {
        return upload_source_from_paths(workspace_root, arguments, explicit_paths);
    }

    let artifact_path_arg = required_string_arg(arguments, "artifact_path")?;
    let artifact_path = resolve_workspace_child(workspace_root, &artifact_path_arg, true)?;
    if artifact_path.is_file() {
        let size = file_size(&artifact_path)?;
        if size == 0 {
            return Err(ToolError::new(
                "tool.schema_invalid",
                "artifact file is empty",
            ));
        }
        return Ok(UploadSource::File {
            relative_path: workspace_relative_path(workspace_root, &artifact_path),
            path: artifact_path,
            size,
        });
    }
    if artifact_path.is_dir() {
        let root_directory = workspace_relative_path(workspace_root, &artifact_path);
        let entries = collect_directory_entries(workspace_root, &artifact_path, &artifact_path)?;
        return directory_upload_source(entries, root_directory.clone(), root_directory);
    }
    Err(ToolError::new(
        "tool.schema_invalid",
        "artifact_path must point to a file or directory inside the workspace",
    ))
}

fn upload_source_from_paths(
    workspace_root: &Path,
    arguments: &Value,
    raw_paths: Vec<String>,
) -> Result<UploadSource, ToolError> {
    let root_arg = string_arg(arguments, "artifact_root", "");
    let relative_base = if root_arg.trim().is_empty() {
        workspace_root.to_path_buf()
    } else {
        let resolved = resolve_workspace_child(workspace_root, &root_arg, true)?;
        if !resolved.is_dir() {
            return Err(ToolError::new(
                "tool.schema_invalid",
                "artifact_root must point to a directory inside the workspace",
            ));
        }
        resolved
    };
    let root_directory = if root_arg.trim().is_empty() {
        ".".to_string()
    } else {
        workspace_relative_path(workspace_root, &relative_base)
    };
    let mut entries = Vec::new();
    for raw_path in raw_paths {
        let path = resolve_workspace_child(workspace_root, &raw_path, true)?;
        if !path.is_file() {
            return Err(ToolError::new(
                "tool.schema_invalid",
                format!("artifact_paths item must point to a file: {raw_path}"),
            ));
        }
        entries.push(upload_entry(workspace_root, &relative_base, &path)?);
    }
    directory_upload_source(entries, root_directory, "selected files".to_string())
}

fn directory_upload_source(
    entries: Vec<UploadEntry>,
    root_directory: String,
    display_path: String,
) -> Result<UploadSource, ToolError> {
    if entries.is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "artifact directory does not contain files",
        ));
    }
    if entries.len() > MAX_UPLOAD_FILES {
        return Err(ToolError::new(
            "tool.output_too_large",
            format!("too many artifact files; maximum is {MAX_UPLOAD_FILES}"),
        ));
    }
    let total_size = entries.iter().map(|entry| entry.size).sum::<u64>();
    Ok(UploadSource::Directory {
        entries,
        root_directory,
        display_path,
        total_size,
    })
}

fn collect_directory_entries(
    workspace_root: &Path,
    relative_base: &Path,
    directory: &Path,
) -> Result<Vec<UploadEntry>, ToolError> {
    let mut children = fs::read_dir(directory)
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read artifact directory failed: {err}"),
            )
        })?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read artifact directory entry failed: {err}"),
            )
        })?;
    children.sort_by_key(|entry| entry.path());
    let mut entries = Vec::new();
    for child in children {
        let file_type = child.file_type().map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read artifact file type failed: {err}"),
            )
        })?;
        if file_type.is_symlink() {
            return Err(ToolError::new(
                "workspace.out_of_scope",
                "artifact directory contains symlink; symlinks are not allowed",
            ));
        }
        let child_path = child.path();
        if file_type.is_dir() {
            entries.extend(collect_directory_entries(
                workspace_root,
                relative_base,
                &child_path,
            )?);
        } else if file_type.is_file() {
            entries.push(upload_entry(workspace_root, relative_base, &child_path)?);
        }
    }
    Ok(entries)
}

fn upload_entry(
    workspace_root: &Path,
    relative_base: &Path,
    path: &Path,
) -> Result<UploadEntry, ToolError> {
    let resolved = path.canonicalize().map_err(|err| {
        ToolError::new(
            "workspace.not_accessible",
            format!("path is not accessible: {err}"),
        )
    })?;
    if !resolved.starts_with(workspace_root) || !resolved.starts_with(relative_base) {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "artifact file escapes workspace or artifact_root",
        ));
    }
    let size = file_size(&resolved)?;
    let upload_path = resolved
        .strip_prefix(relative_base)
        .map(|value| value.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| workspace_relative_path(workspace_root, &resolved));
    if upload_path.trim().is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "artifact file path is empty",
        ));
    }
    Ok(UploadEntry {
        name: resolved
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("artifact-file")
            .to_string(),
        original_path: workspace_relative_path(workspace_root, &resolved),
        path: resolved,
        upload_path,
        size,
    })
}

fn file_size(path: &Path) -> Result<u64, ToolError> {
    fs::metadata(path)
        .map(|metadata| metadata.len())
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read artifact metadata failed: {err}"),
            )
        })
}

fn default_artifact_name(source: &UploadSource) -> String {
    match source {
        UploadSource::File { path, .. } => path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("deploy-artifact")
            .to_string(),
        UploadSource::Directory {
            root_directory,
            display_path,
            ..
        } => Path::new(if root_directory == "." {
            display_path
        } else {
            root_directory
        })
        .file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.trim().is_empty() && *value != ".")
        .unwrap_or("deploy-artifact")
        .to_string(),
    }
}

fn upload_manifest_arg(arguments: &Value, source: &UploadSource) -> Result<Value, ToolError> {
    let mut manifest = manifest_arg(arguments)?;
    if let UploadSource::Directory {
        entries,
        root_directory,
        ..
    } = source
    {
        let manifest_object = manifest
            .as_object_mut()
            .ok_or_else(|| ToolError::new("tool.schema_invalid", "manifest must be an object"))?;
        manifest_object.insert("source_type".to_string(), json!("directory"));
        manifest_object.insert("root_directory".to_string(), json!(root_directory));
        manifest_object.insert(
            "file_entries".to_string(),
            Value::Array(
                entries
                    .iter()
                    .map(|entry| {
                        json!({
                            "path": entry.upload_path,
                            "original_path": entry.original_path,
                            "name": entry.name,
                            "size": entry.size,
                        })
                    })
                    .collect(),
            ),
        );
    }
    Ok(manifest)
}

fn direct_deploy_summary(
    deployment_id: &str,
    deployment_status: &str,
    source_path: &str,
) -> String {
    let source_label = if source_path.trim().is_empty() {
        "部署源".to_string()
    } else {
        format!("部署源 {source_path}")
    };
    if deployment_status == "success" {
        let deployment_label = if deployment_id.trim().is_empty() {
            "direct deployment".to_string()
        } else {
            format!("direct deployment {deployment_id}")
        };
        return format!(
            "{source_label} 已由桌面智能体直接部署并确认成功，{deployment_label} 状态：success"
        );
    }
    if !deployment_status.trim().is_empty() {
        return format!(
            "{source_label} 已由桌面智能体发起直连部署，但未确认成功：deployment 状态={}；不能宣称部署完成",
            deployment_status
        );
    }
    format!("{source_label} 已由桌面智能体发起直连部署，但没有返回部署执行记录；不能宣称部署完成")
}

fn deploy_options_url(api_base_url: &str, project_id: &str) -> Result<Url, ToolError> {
    let base = Url::parse(api_base_url.trim()).map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid api_base_url: {err}"),
        )
    })?;
    if !matches!(base.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "api_base_url must use http or https",
        ));
    }
    let clean_base = base.as_str().trim_end_matches('/').to_string();
    Url::parse(&format!(
        "{}/projects/{}/deploy-options",
        clean_base,
        url_path_escape(project_id)
    ))
    .map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid deploy options url: {err}"),
        )
    })
}

fn direct_deploy_prepare_url(api_base_url: &str, project_id: &str) -> Result<Url, ToolError> {
    direct_deploy_phase_url(api_base_url, project_id, "direct-prepare")
}

fn direct_deploy_complete_url(api_base_url: &str, project_id: &str) -> Result<Url, ToolError> {
    direct_deploy_phase_url(api_base_url, project_id, "direct-complete")
}

fn direct_deploy_phase_url(
    api_base_url: &str,
    project_id: &str,
    phase: &str,
) -> Result<Url, ToolError> {
    let base = Url::parse(api_base_url.trim()).map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid api_base_url: {err}"),
        )
    })?;
    let is_local = matches!(base.host_str(), Some("127.0.0.1" | "localhost" | "::1"));
    if base.scheme() != "https" && !is_local {
        return Err(ToolError::new(
            "deploy.insecure_credential_transport",
            "桌面直连 FTP 需要通过 HTTPS 或本机后端获取部署连接配置",
        ));
    }
    let clean_base = base.as_str().trim_end_matches('/');
    Url::parse(&format!(
        "{}/projects/{}/deploy/{}",
        clean_base,
        url_path_escape(project_id),
        phase
    ))
    .map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid direct deploy url: {err}"),
        )
    })
}

fn manifest_arg(arguments: &Value) -> Result<Value, ToolError> {
    match arguments.get("manifest") {
        None | Some(Value::Null) => Ok(json!({})),
        Some(Value::Object(_)) => Ok(arguments
            .get("manifest")
            .cloned()
            .unwrap_or_else(|| json!({}))),
        _ => Err(ToolError::new(
            "tool.schema_invalid",
            "manifest must be an object",
        )),
    }
}

fn target_ids_arg(arguments: &Value) -> Vec<String> {
    arguments
        .get("target_ids")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .take(50)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn string_list_arg(arguments: &Value, key: &str) -> Vec<String> {
    arguments
        .get(key)
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn safe_error_detail(body: &Value) -> String {
    body.get("detail")
        .or_else(|| body.get("message"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| body.as_str().unwrap_or("request failed"))
        .chars()
        .take(1000)
        .collect()
}

fn url_path_escape(value: &str) -> String {
    value
        .bytes()
        .flat_map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                vec![byte as char]
            }
            _ => format!("%{byte:02X}").chars().collect(),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn direct_deploy_phase_urls_target_prepare_and_complete_endpoints() {
        let prepare = direct_deploy_prepare_url("http://127.0.0.1:8000/api", "proj-1").unwrap();
        let complete = direct_deploy_complete_url("http://127.0.0.1:8000/api", "proj-1").unwrap();

        assert_eq!(
            prepare.as_str(),
            "http://127.0.0.1:8000/api/projects/proj-1/deploy/direct-prepare"
        );
        assert_eq!(
            complete.as_str(),
            "http://127.0.0.1:8000/api/projects/proj-1/deploy/direct-complete"
        );
        assert!(direct_deploy_prepare_url("http://example.com/api", "proj-1").is_err());
    }

    #[test]
    fn direct_deploy_summary_reports_success_only_for_success() {
        let blocked = direct_deploy_summary("direct-run-1", "blocked", "selected files");
        assert!(blocked.contains("未确认成功"));
        assert!(blocked.contains("不能宣称部署完成"));
        assert!(!blocked.contains("部署成功"));

        let success = direct_deploy_summary("direct-run-1", "success", "selected files");
        assert!(success.contains("直接部署并确认成功"));
        assert!(success.contains("direct deployment direct-run-1 状态：success"));
    }

    #[test]
    fn ftp_task_uses_one_process_config_for_multiple_files() {
        let files = vec![
            (
                PathBuf::from("/tmp/site/js/a.js"),
                "js/a.js".to_string(),
                10,
            ),
            (
                PathBuf::from("/tmp/site/js/b.js"),
                "js/b.js".to_string(),
                20,
            ),
        ];
        let config = curl_ftp_task_config(
            "ftp.example.com",
            21,
            "ftp-user",
            "secret",
            "/www/site",
            &files,
        )
        .unwrap();

        assert_eq!(config.matches("user = ").count(), 1);
        assert_eq!(config.matches("upload-file = ").count(), 2);
        assert_eq!(config.matches("url = ").count(), 2);
        assert!(config.contains("/www/site/js/a.js"));
        assert!(config.contains("/www/site/js/b.js"));
    }

    #[test]
    fn ftp_backup_path_keeps_original_name_and_second_precision() {
        let backup = ftp_backup_path("/www/site");

        assert!(backup.starts_with("/www/site_备份_"));
        let timestamp = backup.trim_start_matches("/www/site_备份_");
        assert_eq!(timestamp.chars().count(), 21);
        assert!(timestamp.ends_with('秒'));
        assert!(timestamp.contains('年'));
        assert!(timestamp.contains('月'));
        assert!(timestamp.contains('日'));
        assert!(timestamp.contains('时'));
        assert!(timestamp.contains('分'));
    }

    #[test]
    fn directory_artifact_path_builds_directory_upload_manifest() {
        let root =
            std::env::temp_dir().join(format!("liuagent_deploy_dir_test_{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("site/login")).unwrap();
        fs::write(root.join("site/index.html"), b"<h1>ok</h1>").unwrap();
        fs::write(root.join("site/login/index.html"), b"login").unwrap();
        let root = root.canonicalize().unwrap();

        let args = json!({"artifact_path": "site"});
        let source = upload_source_arg(&root, &args).unwrap();
        let manifest = upload_manifest_arg(&args, &source).unwrap();

        assert_eq!(source.source_type(), "directory");
        assert_eq!(source.file_count(), 2);
        assert_eq!(manifest["source_type"], "directory");
        assert_eq!(manifest["root_directory"], "site");
        let paths: Vec<String> = manifest["file_entries"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| item["path"].as_str().unwrap().to_string())
            .collect();
        assert_eq!(paths, vec!["index.html", "login/index.html"]);

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn artifact_paths_preserve_relative_paths_from_artifact_root() {
        let root =
            std::env::temp_dir().join(format!("liuagent_deploy_paths_test_{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("login")).unwrap();
        fs::write(root.join("login/index.html"), b"login").unwrap();
        fs::write(root.join("register.html"), b"register").unwrap();
        let root = root.canonicalize().unwrap();

        let args = json!({
            "artifact_paths": ["login/index.html", "register.html"],
            "artifact_root": "."
        });
        let source = upload_source_arg(&root, &args).unwrap();
        let manifest = upload_manifest_arg(&args, &source).unwrap();

        assert_eq!(source.source_type(), "directory");
        assert_eq!(manifest["source_type"], "directory");
        let paths: Vec<String> = manifest["file_entries"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| item["path"].as_str().unwrap().to_string())
            .collect();
        assert_eq!(paths, vec!["login/index.html", "register.html"]);

        let _ = fs::remove_dir_all(&root);
    }
}
