use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tauri::{Emitter, Manager};

mod liuagent_core;

#[derive(Debug, Serialize)]
struct PickPathResult {
    cancelled: bool,
    path: String,
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
    let live_events = Arc::new(Mutex::new(Vec::new()));
    let live_events_for_worker = Arc::clone(&live_events);
    match tauri::async_runtime::spawn_blocking(move || {
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
            chat_session_id,
            liuagent_core::ToolError::new(
                "runtime.join_failed",
                format!("local chat worker failed: {error}"),
            ),
        ),
    }
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
    let root = resolve_workspace_root(&workspace_path)?;
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
    let root = resolve_workspace_root(&workspace_path)?;
    let target = resolve_workspace_child(&root, path)?;
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
    })
}

#[tauri::command]
fn preview_workspace_diff(
    workspace_path: String,
    path: Option<String>,
) -> Result<WorkspaceDiffPreviewResult, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    let relative_path = resolve_existing_workspace_relative_path(&root, path.unwrap_or_default())?;
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
    let reason = [status.stderr, summary.stderr.clone(), diff.stderr.clone()]
        .into_iter()
        .map(|value| value.trim().to_string())
        .find(|value| !value.is_empty())
        .unwrap_or_default();
    let (summary_text, summary_truncated) = truncate_text(summary.stdout, 8_000);
    let (diff_text, diff_truncated) = truncate_text(diff.stdout, 30_000);
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
            "当前命令只生成写入前确认摘要，不执行文件写入".to_string()
        } else {
            "没有检测到内容变化".to_string()
        },
    })
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
    let root = PathBuf::from(raw)
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

fn resolve_existing_workspace_relative_path(
    root: &Path,
    raw_path: String,
) -> Result<String, String> {
    let raw = raw_path.trim();
    if raw.is_empty() {
        return Ok(String::new());
    }
    let resolved = resolve_workspace_child(root, raw.to_string())?;
    Ok(workspace_relative_path(root, &resolved))
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
    let parent = candidate
        .parent()
        .ok_or_else(|| "缺少父目录".to_string())?
        .canonicalize()
        .map_err(|err| format!("父目录不可访问：{err}"))?;
    if !parent.starts_with(root) {
        return Err("路径必须位于项目工作区内".to_string());
    }
    Ok(parent.join(
        candidate
            .file_name()
            .ok_or_else(|| "缺少文件名".to_string())?,
    ))
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

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            pick_workspace_directory,
            detect_executors,
            get_runtime_info,
            list_workspace_files,
            read_workspace_file,
            preview_workspace_diff,
            prepare_workspace_file_write,
            classify_runner_command,
            run_runner_command,
            record_runner_permission_decision,
            list_runner_permission_decisions,
            liuagent_builtin_tool_definitions,
            liuagent_execute_tool,
            liuagent_upload_provider_file,
            liuagent_start_local_chat,
            liuagent_prepare_agent_invocation,
            liuagent_recover_runtime_state,
            liuagent_list_runtime_events,
            liuagent_list_runtime_outbox,
            liuagent_ack_runtime_outbox
        ])
        .run(tauri::generate_context!())
        .expect("error while running AI Employee Factory desktop app");
}
