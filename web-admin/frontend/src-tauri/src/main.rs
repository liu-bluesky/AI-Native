use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::{Read, Write};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tauri::{Emitter, Manager};

type ExternalAgentSessionStore = Arc<Mutex<HashMap<String, ExternalAgentSessionState>>>;
static EXTERNAL_AGENT_OUTPUT_COUNTER: AtomicU64 = AtomicU64::new(0);
const EXTERNAL_AGENT_SESSION_EVENT: &str = "ai-employee://external-agent-session";

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

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExternalAgentLaunchPlan {
    agent_type: String,
    label: String,
    command: String,
    args: Vec<String>,
    workspace_path: String,
    installed: bool,
    executable_path: String,
    version: String,
    risk_level: String,
    requires_approval: bool,
    can_launch: bool,
    blocked_reason: String,
    summary: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExternalAgentRunResult {
    agent_type: String,
    label: String,
    command: String,
    args: Vec<String>,
    workspace_path: String,
    stdout: String,
    stderr: String,
    exit_code: i32,
    duration_ms: u128,
    timed_out: bool,
    truncated: bool,
    risk_level: String,
    requires_approval: bool,
    blocked_reason: String,
    summary: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ExternalAgentSessionLog {
    seq: u64,
    stream: String,
    content: String,
    created_at_epoch_ms: u64,
}

struct ExternalAgentSessionState {
    session_id: String,
    agent_type: String,
    label: String,
    command: String,
    args: Vec<String>,
    workspace_path: String,
    status: String,
    exit_code: Option<i32>,
    started_at_epoch_ms: u64,
    updated_at_epoch_ms: u64,
    next_seq: u64,
    logs: Vec<ExternalAgentSessionLog>,
    final_output_path: String,
    final_output: String,
    blocked_reason: String,
    summary: String,
    child_process_id: Option<u32>,
    child: Option<Arc<Mutex<Box<dyn portable_pty::Child + Send + Sync>>>>,
    process_child: Option<Arc<Mutex<Child>>>,
    stdin: Option<Arc<Mutex<Box<dyn Write + Send>>>>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ExternalAgentSessionSnapshot {
    session_id: String,
    agent_type: String,
    label: String,
    command: String,
    args: Vec<String>,
    workspace_path: String,
    status: String,
    exit_code: Option<i32>,
    started_at_epoch_ms: u64,
    updated_at_epoch_ms: u64,
    logs: Vec<ExternalAgentSessionLog>,
    next_seq: u64,
    final_output: String,
    blocked_reason: String,
    summary: String,
    #[serde(default)]
    stdin_open: bool,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ExternalAgentSessionEvent {
    event_type: String,
    session_id: String,
    status: String,
    stream: String,
    log: Option<ExternalAgentSessionLog>,
    snapshot: ExternalAgentSessionSnapshot,
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
    RuntimeInfo {
        platform: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
        desktop_bridge_version: "0.1.0".to_string(),
    }
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
fn prepare_external_agent_launch(
    agent_type: String,
    workspace_path: String,
    prompt: Option<String>,
) -> Result<ExternalAgentLaunchPlan, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    let normalized_agent_type = normalize_external_agent_type(&agent_type);
    Ok(build_external_agent_launch_plan(
        &normalized_agent_type,
        &root,
        prompt,
    ))
}

#[tauri::command]
async fn run_external_agent_once(
    agent_type: String,
    workspace_path: String,
    prompt: String,
    timeout_ms: Option<u64>,
) -> Result<ExternalAgentRunResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        run_external_agent_once_blocking(agent_type, workspace_path, prompt, timeout_ms)
    })
    .await
    .map_err(|err| format!("外部 Agent 后台任务异常：{err}"))?
}

fn run_external_agent_once_blocking(
    agent_type: String,
    workspace_path: String,
    prompt: String,
    timeout_ms: Option<u64>,
) -> Result<ExternalAgentRunResult, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    let normalized_agent_type = normalize_external_agent_type(&agent_type);
    let normalized_prompt = prompt.trim().to_string();
    if normalized_prompt.is_empty() {
        return Err("缺少外部 Agent 试运行提示词".to_string());
    }
    let mut plan =
        build_external_agent_launch_plan(&normalized_agent_type, &root, Some(normalized_prompt));
    if !plan.can_launch {
        return Ok(ExternalAgentRunResult {
            agent_type: plan.agent_type,
            label: plan.label,
            command: plan.command,
            args: plan.args,
            workspace_path: plan.workspace_path,
            stdout: String::new(),
            stderr: String::new(),
            exit_code: -1,
            duration_ms: 0,
            timed_out: false,
            truncated: false,
            risk_level: plan.risk_level,
            requires_approval: plan.requires_approval,
            blocked_reason: plan.blocked_reason,
            summary: "外部 Agent 试运行被启动计划拦截".to_string(),
        });
    }

    let timeout = Duration::from_millis(timeout_ms.unwrap_or(15_000).clamp(5_000, 60_000));
    let final_output_path = external_agent_final_output_path(&plan.agent_type);
    attach_external_agent_final_output_arg(&mut plan, &final_output_path);
    Ok(execute_external_agent_plan(
        plan,
        timeout,
        final_output_path,
    ))
}

#[tauri::command]
fn start_external_agent_session(
    app: tauri::AppHandle,
    sessions: tauri::State<'_, ExternalAgentSessionStore>,
    agent_type: String,
    workspace_path: String,
    prompt: String,
) -> Result<ExternalAgentSessionSnapshot, String> {
    let root = resolve_workspace_root(&workspace_path)?;
    let normalized_agent_type = normalize_external_agent_type(&agent_type);
    let normalized_prompt = prompt.trim().to_string();
    if normalized_prompt.is_empty() {
        return Err("缺少外部 Agent 任务内容".to_string());
    }
    let mut plan =
        build_external_agent_launch_plan(&normalized_agent_type, &root, Some(normalized_prompt));
    if !plan.can_launch {
        let now = current_epoch_millis();
        let state = ExternalAgentSessionState {
            session_id: format!("external-agent-session-{now}"),
            agent_type: plan.agent_type,
            label: plan.label,
            command: plan.command,
            args: plan.args,
            workspace_path: plan.workspace_path,
            status: "blocked".to_string(),
            exit_code: Some(-1),
            started_at_epoch_ms: now,
            updated_at_epoch_ms: now,
            next_seq: 1,
            logs: Vec::new(),
            final_output_path: String::new(),
            final_output: String::new(),
            blocked_reason: plan.blocked_reason,
            summary: "外部 Agent Runner 会话被启动计划拦截".to_string(),
            child_process_id: None,
            child: None,
            process_child: None,
            stdin: None,
        };
        persist_external_agent_session_snapshot(&app, &state)?;
        emit_external_agent_session_event(&app, "blocked", &state, "system", None);
        return Ok(external_agent_session_snapshot(&state, 0));
    }

    let final_output_path = external_agent_final_output_path(&plan.agent_type);
    attach_external_agent_final_output_arg(&mut plan, &final_output_path);
    if external_agent_uses_stdout_final_output(&plan.agent_type) {
        return start_external_agent_pipe_session(app, sessions, plan, final_output_path);
    }
    let pty_system = native_pty_system();
    let pair = pty_system
        .openpty(PtySize {
            rows: 32,
            cols: 120,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|err| format!("创建 PTY 失败：{err}"))?;
    let mut command = CommandBuilder::new(&plan.command);
    command.args(&plan.args);
    command.cwd(Path::new(&plan.workspace_path));
    let child = pair
        .slave
        .spawn_command(command)
        .map_err(|err| format!("外部 Agent PTY 进程启动失败：{err}"))?;
    let reader = pair
        .master
        .try_clone_reader()
        .map_err(|err| format!("读取 PTY 输出失败：{err}"))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|err| format!("打开 PTY 输入失败：{err}"))?;
    drop(pair.slave);
    let child_process_id = child.process_id();
    let child = Arc::new(Mutex::new(child));
    let now = current_epoch_millis();
    let session_id = format!("external-agent-session-{now}");
    let state = ExternalAgentSessionState {
        session_id: session_id.clone(),
        agent_type: plan.agent_type,
        label: plan.label.clone(),
        command: plan.command,
        args: plan.args,
        workspace_path: plan.workspace_path,
        status: "running".to_string(),
        exit_code: None,
        started_at_epoch_ms: now,
        updated_at_epoch_ms: now,
        next_seq: 1,
        logs: vec![ExternalAgentSessionLog {
            seq: 0,
            stream: "system".to_string(),
            content: format!("{} Runner 会话已启动\n", plan.label),
            created_at_epoch_ms: now,
        }],
        final_output_path: final_output_path.clone(),
        final_output: String::new(),
        blocked_reason: String::new(),
        summary: format!("{} PTY Runner 会话运行中", plan.label),
        child_process_id,
        child: Some(child.clone()),
        process_child: None,
        stdin: Some(Arc::new(Mutex::new(writer))),
    };

    {
        let mut store = sessions.lock().map_err(|err| err.to_string())?;
        persist_external_agent_session_snapshot(&app, &state)?;
        emit_external_agent_session_event(&app, "started", &state, "system", None);
        store.insert(session_id.clone(), state);
    }
    spawn_external_agent_log_reader(
        app.clone(),
        sessions.inner().clone(),
        session_id.clone(),
        "pty",
        reader,
    );
    spawn_external_agent_waiter(app, sessions.inner().clone(), session_id.clone(), child);

    let store = sessions.lock().map_err(|err| err.to_string())?;
    store
        .get(&session_id)
        .map(|state| external_agent_session_snapshot(state, 0))
        .ok_or_else(|| "Runner 会话启动后状态丢失".to_string())
}

fn start_external_agent_pipe_session(
    app: tauri::AppHandle,
    sessions: tauri::State<'_, ExternalAgentSessionStore>,
    plan: ExternalAgentLaunchPlan,
    final_output_path: String,
) -> Result<ExternalAgentSessionSnapshot, String> {
    let mut command = Command::new(&plan.command);
    command
        .args(&plan.args)
        .current_dir(Path::new(&plan.workspace_path))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    configure_command_process_group(&mut command);
    let mut child = command
        .spawn()
        .map_err(|err| format!("外部 Agent 进程启动失败：{err}"))?;
    let child_process_id = Some(child.id());
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let child = Arc::new(Mutex::new(child));
    let now = current_epoch_millis();
    let session_id = format!("external-agent-session-{now}");
    let state = ExternalAgentSessionState {
        session_id: session_id.clone(),
        agent_type: plan.agent_type,
        label: plan.label.clone(),
        command: plan.command,
        args: plan.args,
        workspace_path: plan.workspace_path,
        status: "running".to_string(),
        exit_code: None,
        started_at_epoch_ms: now,
        updated_at_epoch_ms: now,
        next_seq: 1,
        logs: vec![ExternalAgentSessionLog {
            seq: 0,
            stream: "system".to_string(),
            content: format!("{} one-shot Runner 已启动，等待最终响应输出\n", plan.label),
            created_at_epoch_ms: now,
        }],
        final_output_path,
        final_output: String::new(),
        blocked_reason: String::new(),
        summary: format!("{} one-shot Runner 会话运行中", plan.label),
        child_process_id,
        child: None,
        process_child: Some(child.clone()),
        stdin: None,
    };

    {
        let mut store = sessions.lock().map_err(|err| err.to_string())?;
        persist_external_agent_session_snapshot(&app, &state)?;
        emit_external_agent_session_event(&app, "started", &state, "system", None);
        store.insert(session_id.clone(), state);
    }
    if let Some(stdout) = stdout {
        spawn_external_agent_log_reader(
            app.clone(),
            sessions.inner().clone(),
            session_id.clone(),
            "stdout",
            stdout,
        );
    }
    if let Some(stderr) = stderr {
        spawn_external_agent_log_reader(
            app.clone(),
            sessions.inner().clone(),
            session_id.clone(),
            "stderr",
            stderr,
        );
    }
    spawn_external_agent_process_waiter(app, sessions.inner().clone(), session_id.clone(), child);

    let store = sessions.lock().map_err(|err| err.to_string())?;
    store
        .get(&session_id)
        .map(|state| external_agent_session_snapshot(state, 0))
        .ok_or_else(|| "Runner 会话启动后状态丢失".to_string())
}

#[tauri::command]
fn get_external_agent_session(
    app: tauri::AppHandle,
    sessions: tauri::State<'_, ExternalAgentSessionStore>,
    session_id: String,
    since_seq: Option<u64>,
) -> Result<ExternalAgentSessionSnapshot, String> {
    let normalized_session_id = session_id.trim().to_string();
    {
        let store = sessions.lock().map_err(|err| err.to_string())?;
        if let Some(state) = store.get(&normalized_session_id) {
            return Ok(external_agent_session_snapshot(
                state,
                since_seq.unwrap_or(0),
            ));
        }
    }
    let snapshot = read_external_agent_session_snapshot(&app, &normalized_session_id)?
        .ok_or_else(|| "Runner 会话不存在".to_string())?;
    let snapshot = normalize_detached_external_agent_session_snapshot(&app, snapshot)?;
    Ok(filter_external_agent_session_snapshot_logs(
        snapshot,
        since_seq.unwrap_or(0),
    ))
}

#[tauri::command]
fn list_external_agent_sessions(
    app: tauri::AppHandle,
    sessions: tauri::State<'_, ExternalAgentSessionStore>,
    limit: Option<usize>,
) -> Result<Vec<ExternalAgentSessionSnapshot>, String> {
    let max_items = limit.unwrap_or(20).clamp(1, 100);
    let live_session_ids: HashSet<String> = sessions
        .lock()
        .map(|store| store.keys().cloned().collect())
        .unwrap_or_default();
    let mut snapshots = read_external_agent_session_snapshots(&app)?
        .into_iter()
        .map(|snapshot| {
            if live_session_ids.contains(&snapshot.session_id) {
                Ok(snapshot)
            } else {
                normalize_detached_external_agent_session_snapshot(&app, snapshot)
            }
        })
        .collect::<Result<Vec<_>, _>>()?;
    if let Ok(store) = sessions.lock() {
        for state in store.values() {
            let snapshot = external_agent_session_snapshot(state, 0);
            if let Some(existing) = snapshots
                .iter_mut()
                .find(|item| item.session_id == snapshot.session_id)
            {
                *existing = snapshot;
            } else {
                snapshots.push(snapshot);
            }
        }
    }
    snapshots.sort_by(|a, b| b.updated_at_epoch_ms.cmp(&a.updated_at_epoch_ms));
    snapshots.truncate(max_items);
    Ok(snapshots)
}

#[tauri::command]
fn cancel_external_agent_session(
    app: tauri::AppHandle,
    sessions: tauri::State<'_, ExternalAgentSessionStore>,
    session_id: String,
) -> Result<ExternalAgentSessionSnapshot, String> {
    let normalized_session_id = session_id.trim().to_string();
    let (child_process_id, child, process_child) = {
        let mut store = sessions.lock().map_err(|err| err.to_string())?;
        let state = store
            .get_mut(&normalized_session_id)
            .ok_or_else(|| "Runner 会话不存在".to_string())?;
        state.status = "cancelling".to_string();
        state.updated_at_epoch_ms = current_epoch_millis();
        let log = push_external_agent_session_log(state, "system", "正在取消 Runner 会话\n");
        state.stdin = None;
        persist_external_agent_session_snapshot(&app, state)?;
        emit_external_agent_session_event(&app, "log", state, "system", log);
        (
            state.child_process_id,
            state.child.clone(),
            state.process_child.clone(),
        )
    };
    signal_external_agent_process_tree(child_process_id);
    if let Some(child) = child {
        if let Ok(mut child) = child.try_lock() {
            let _ = child.kill();
        }
    }
    if let Some(process_child) = process_child {
        if let Ok(mut process_child) = process_child.try_lock() {
            let _ = process_child.kill();
        }
    }
    let mut store = sessions.lock().map_err(|err| err.to_string())?;
    let state = store
        .get_mut(&normalized_session_id)
        .ok_or_else(|| "Runner 会话不存在".to_string())?;
    state.status = "cancelled".to_string();
    state.exit_code = Some(-15);
    state.summary = format!("{} Runner 会话已取消", state.label);
    state.child_process_id = None;
    state.child = None;
    state.process_child = None;
    state.updated_at_epoch_ms = current_epoch_millis();
    let log = push_external_agent_session_log(state, "system", "Runner 会话已取消\n");
    persist_external_agent_session_snapshot(&app, state)?;
    emit_external_agent_session_event(&app, "cancelled", state, "system", log);
    Ok(external_agent_session_snapshot(state, 0))
}

#[tauri::command]
fn hard_kill_external_agent_session(
    app: tauri::AppHandle,
    sessions: tauri::State<'_, ExternalAgentSessionStore>,
    session_id: String,
) -> Result<ExternalAgentSessionSnapshot, String> {
    let normalized_session_id = session_id.trim().to_string();
    let (child_process_id, child, process_child) = {
        let mut store = sessions.lock().map_err(|err| err.to_string())?;
        let state = store
            .get_mut(&normalized_session_id)
            .ok_or_else(|| "Runner 会话不存在".to_string())?;
        state.status = "cancelled".to_string();
        state.exit_code = Some(-15);
        state.summary = format!("{} Runner 会话已取消", state.label);
        state.stdin = None;
        state.updated_at_epoch_ms = current_epoch_millis();
        (
            state.child_process_id,
            state.child.clone(),
            state.process_child.clone(),
        )
    };
    signal_external_agent_process_tree(child_process_id);
    if let Some(child) = child {
        if let Ok(mut child) = child.try_lock() {
            let _ = child.kill();
        }
    }
    if let Some(process_child) = process_child {
        if let Ok(mut process_child) = process_child.try_lock() {
            let _ = process_child.kill();
        }
    }
    let (snapshot, event) = {
        let mut store = sessions.lock().map_err(|err| err.to_string())?;
        let state = store
            .get_mut(&normalized_session_id)
            .ok_or_else(|| "Runner 会话不存在".to_string())?;
        state.status = "cancelled".to_string();
        state.exit_code = Some(-15);
        state.summary = format!("{} Runner 会话已取消", state.label);
        state.child_process_id = None;
        state.child = None;
        state.process_child = None;
        state.stdin = None;
        state.updated_at_epoch_ms = current_epoch_millis();
        let log = push_external_agent_session_log(state, "system", "Runner 会话已终止\n");
        persist_external_agent_session_snapshot(&app, state)?;
        let snapshot = external_agent_session_minimal_snapshot(state, log.as_ref());
        let event = ExternalAgentSessionEvent {
            event_type: "cancelled".to_string(),
            session_id: state.session_id.clone(),
            status: state.status.clone(),
            stream: "system".to_string(),
            log,
            snapshot: snapshot.clone(),
        };
        (snapshot, event)
    };
    let _ = app.emit(EXTERNAL_AGENT_SESSION_EVENT, event);
    Ok(snapshot)
}

#[tauri::command]
fn write_external_agent_session_input(
    app: tauri::AppHandle,
    sessions: tauri::State<'_, ExternalAgentSessionStore>,
    session_id: String,
    input: String,
    append_newline: Option<bool>,
) -> Result<ExternalAgentSessionSnapshot, String> {
    let normalized_session_id = session_id.trim().to_string();
    let mut content = input;
    if content.is_empty() {
        return Err("缺少要发送给 Runner 的输入".to_string());
    }
    if append_newline.unwrap_or(true) && !content.ends_with('\n') {
        content.push('\n');
    }
    let mut store = sessions.lock().map_err(|err| err.to_string())?;
    let state = store
        .get_mut(&normalized_session_id)
        .ok_or_else(|| "Runner 会话不存在".to_string())?;
    if state.status != "running" && state.status != "cancelling" {
        return Err("Runner 会话不在可输入状态".to_string());
    }
    let stdin = state
        .stdin
        .clone()
        .ok_or_else(|| "Runner stdin 不可用；该会话可能已结束或不支持输入".to_string())?;
    {
        let mut stream = stdin.lock().map_err(|err| err.to_string())?;
        stream
            .write_all(content.as_bytes())
            .map_err(|err| format!("写入 Runner stdin 失败：{err}"))?;
        stream
            .flush()
            .map_err(|err| format!("刷新 Runner stdin 失败：{err}"))?;
    }
    state.updated_at_epoch_ms = current_epoch_millis();
    let preview = if content.trim().is_empty() {
        "<empty>".to_string()
    } else if content.chars().count() > 120 {
        format!("{}...", content.chars().take(120).collect::<String>())
    } else {
        content.clone()
    };
    let log = push_external_agent_session_log(
        state,
        "stdin",
        &format!("[user input] {}\n", preview.trim_end()),
    );
    persist_external_agent_session_snapshot(&app, state)?;
    emit_external_agent_session_event(&app, "input", state, "stdin", log);
    Ok(external_agent_session_snapshot(state, 0))
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

fn normalize_external_agent_type(value: &str) -> String {
    match value.trim().to_lowercase().as_str() {
        "hermes" => "hermes".to_string(),
        "claude_code" | "claude-code" | "claude" => "claude_code".to_string(),
        _ => "codex_cli".to_string(),
    }
}

fn external_agent_launch_command(agent_type: &str) -> (&'static str, &'static str, Vec<String>) {
    match agent_type {
        "hermes" => ("Hermes", "hermes", vec!["-z".to_string()]),
        "claude_code" => ("Claude Code", "claude", vec!["--print".to_string()]),
        _ => (
            "Codex CLI",
            "codex",
            vec![
                "exec".to_string(),
                "--sandbox".to_string(),
                "workspace-write".to_string(),
                "--color".to_string(),
                "never".to_string(),
                "--ephemeral".to_string(),
            ],
        ),
    }
}

fn external_agent_final_output_path(agent_type: &str) -> String {
    if agent_type != "codex_cli" {
        return String::new();
    }
    let counter = EXTERNAL_AGENT_OUTPUT_COUNTER.fetch_add(1, Ordering::Relaxed);
    let file_name = format!(
        "ai-employee-codex-final-{}-{counter}.txt",
        current_epoch_millis()
    );
    std::env::temp_dir()
        .join(file_name)
        .to_string_lossy()
        .to_string()
}

fn attach_external_agent_final_output_arg(
    plan: &mut ExternalAgentLaunchPlan,
    final_output_path: &str,
) {
    if plan.agent_type != "codex_cli" || final_output_path.trim().is_empty() {
        return;
    }
    let prompt = plan.args.pop();
    plan.args.push("--output-last-message".to_string());
    plan.args.push(final_output_path.to_string());
    if let Some(prompt) = prompt {
        plan.args.push(prompt);
    }
}

fn build_external_agent_launch_plan(
    agent_type: &str,
    root: &Path,
    prompt: Option<String>,
) -> ExternalAgentLaunchPlan {
    let (label, command, mut args) = external_agent_launch_command(agent_type);
    if let Some(prompt) = prompt
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
    {
        args.push(prompt);
    }
    let status = detect_executor(command);
    let blocked_reason = if !status.installed {
        format!("未检测到 {label} 可执行文件")
    } else {
        String::new()
    };
    let can_launch = blocked_reason.is_empty();
    let command_preview = std::iter::once(command.to_string())
        .chain(args.iter().cloned())
        .collect::<Vec<_>>()
        .join(" ");

    ExternalAgentLaunchPlan {
        agent_type: agent_type.to_string(),
        label: label.to_string(),
        command: command.to_string(),
        args,
        workspace_path: root.to_string_lossy().to_string(),
        installed: status.installed,
        executable_path: status.path,
        version: status.version,
        risk_level: if can_launch {
            "approval_required"
        } else {
            "blocked"
        }
        .to_string(),
        requires_approval: can_launch,
        can_launch,
        blocked_reason,
        summary: format!("准备启动 {label}：{command_preview}；当前只生成启动计划，不创建进程"),
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
    let stderr_text = receive_process_output(stderr_receiver, Duration::from_millis(300));

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

fn execute_external_agent_plan(
    plan: ExternalAgentLaunchPlan,
    timeout: Duration,
    final_output_path: String,
) -> ExternalAgentRunResult {
    let started_at = Instant::now();
    let mut command = Command::new(&plan.command);
    command.args(&plan.args);
    command.current_dir(Path::new(&plan.workspace_path));
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    configure_command_process_group(&mut command);

    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(err) => {
            return ExternalAgentRunResult {
                agent_type: plan.agent_type,
                label: plan.label,
                command: plan.command,
                args: plan.args,
                workspace_path: plan.workspace_path,
                stdout: String::new(),
                stderr: err.to_string(),
                exit_code: -1,
                duration_ms: started_at.elapsed().as_millis(),
                timed_out: false,
                truncated: false,
                risk_level: plan.risk_level,
                requires_approval: plan.requires_approval,
                blocked_reason: err.to_string(),
                summary: "外部 Agent 进程启动失败".to_string(),
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
                signal_external_agent_process_tree(Some(child.id()));
                let _ = child.kill();
                break child.wait().ok();
            }
            Ok(None) => thread::sleep(Duration::from_millis(50)),
            Err(_) => break None,
        }
    };

    let mut output_incomplete = false;
    let stdout_text = receive_process_output_with_status(
        stdout_receiver,
        Duration::from_millis(800),
        &mut output_incomplete,
    );
    let stderr_text = receive_process_output_with_status(
        stderr_receiver,
        Duration::from_millis(800),
        &mut output_incomplete,
    );
    let final_output = read_external_agent_final_output(&final_output_path);
    let stdout_text = if final_output.trim().is_empty() {
        stdout_text
    } else {
        final_output
    };
    let (stdout_text, stdout_truncated) = truncate_text(stdout_text, 30_000);
    let (stderr_text, stderr_truncated) = truncate_text(stderr_text, 12_000);
    let exit_code = status.and_then(|value| value.code()).unwrap_or(-1);
    let blocked_reason = if timed_out {
        "外部 Agent 试运行超时，已终止进程；常见原因是 CLI 等待登录、网络、权限确认或模型响应"
            .to_string()
    } else if output_incomplete {
        "外部 Agent 已退出，但输出管道未及时关闭；已返回已收集到的结果".to_string()
    } else {
        String::new()
    };

    ExternalAgentRunResult {
        agent_type: plan.agent_type,
        label: plan.label.clone(),
        command: plan.command,
        args: plan.args,
        workspace_path: plan.workspace_path,
        stdout: stdout_text,
        stderr: stderr_text,
        exit_code,
        duration_ms: started_at.elapsed().as_millis(),
        timed_out,
        truncated: stdout_truncated || stderr_truncated || output_incomplete,
        risk_level: plan.risk_level,
        requires_approval: plan.requires_approval,
        blocked_reason,
        summary: if timed_out {
            format!("{} 试运行超时，已终止进程", plan.label)
        } else if output_incomplete {
            format!("{} 试运行完成，部分输出未及时关闭", plan.label)
        } else if exit_code == 0 {
            format!("{} 试运行完成", plan.label)
        } else {
            format!("{} 试运行结束，退出码 {}", plan.label, exit_code)
        },
    }
}

fn push_external_agent_session_log(
    state: &mut ExternalAgentSessionState,
    stream: &str,
    content: &str,
) -> Option<ExternalAgentSessionLog> {
    if content.is_empty() {
        return None;
    }
    let seq = state.next_seq;
    state.next_seq = state.next_seq.saturating_add(1);
    let log = ExternalAgentSessionLog {
        seq,
        stream: stream.to_string(),
        content: content.to_string(),
        created_at_epoch_ms: current_epoch_millis(),
    };
    state.logs.push(log.clone());
    if state.logs.len() > 1000 {
        let overflow = state.logs.len() - 1000;
        state.logs.drain(0..overflow);
    }
    state.updated_at_epoch_ms = current_epoch_millis();
    Some(log)
}

fn emit_external_agent_session_event(
    app: &tauri::AppHandle,
    event_type: &str,
    state: &ExternalAgentSessionState,
    stream: &str,
    log: Option<ExternalAgentSessionLog>,
) {
    let payload = external_agent_session_event_payload(event_type, state, stream, log);
    let _ = app.emit(EXTERNAL_AGENT_SESSION_EVENT, payload);
}

fn external_agent_session_event_payload(
    event_type: &str,
    state: &ExternalAgentSessionState,
    stream: &str,
    log: Option<ExternalAgentSessionLog>,
) -> ExternalAgentSessionEvent {
    ExternalAgentSessionEvent {
        event_type: event_type.to_string(),
        session_id: state.session_id.clone(),
        status: state.status.clone(),
        stream: stream.to_string(),
        log,
        snapshot: external_agent_session_snapshot(state, 0),
    }
}

fn spawn_external_agent_log_reader<R>(
    app: tauri::AppHandle,
    sessions: ExternalAgentSessionStore,
    session_id: String,
    stream_name: &'static str,
    mut stream: R,
) where
    R: Read + Send + 'static,
{
    thread::spawn(move || {
        let mut buffer = [0_u8; 4096];
        loop {
            match stream.read(&mut buffer) {
                Ok(0) => break,
                Ok(size) => {
                    let content = String::from_utf8_lossy(&buffer[..size]).to_string();
                    let mut event = None;
                    if let Ok(mut store) = sessions.lock() {
                        if let Some(state) = store.get_mut(&session_id) {
                            if is_external_agent_terminal_status(&state.status) {
                                continue;
                            }
                            let log = push_external_agent_session_log(state, stream_name, &content);
                            let _ = persist_external_agent_session_snapshot(&app, state);
                            event = Some(external_agent_session_event_payload(
                                "log",
                                state,
                                stream_name,
                                log,
                            ));
                        }
                    }
                    if let Some(payload) = event {
                        let _ = app.emit(EXTERNAL_AGENT_SESSION_EVENT, payload);
                    }
                }
                Err(err) => {
                    let mut event = None;
                    if let Ok(mut store) = sessions.lock() {
                        if let Some(state) = store.get_mut(&session_id) {
                            if is_external_agent_terminal_status(&state.status) {
                                break;
                            }
                            let log = push_external_agent_session_log(
                                state,
                                "system",
                                &format!("读取 {stream_name} 失败：{err}\n"),
                            );
                            let _ = persist_external_agent_session_snapshot(&app, state);
                            event = Some(external_agent_session_event_payload(
                                "error", state, "system", log,
                            ));
                        }
                    }
                    if let Some(payload) = event {
                        let _ = app.emit(EXTERNAL_AGENT_SESSION_EVENT, payload);
                    }
                    break;
                }
            }
        }
    });
}

fn spawn_external_agent_waiter(
    app: tauri::AppHandle,
    sessions: ExternalAgentSessionStore,
    session_id: String,
    child: Arc<Mutex<Box<dyn portable_pty::Child + Send + Sync>>>,
) {
    thread::spawn(move || {
        let status = {
            match child.lock() {
                Ok(mut child) => child.wait().ok(),
                Err(_) => None,
            }
        };
        let mut event = None;
        if let Ok(mut store) = sessions.lock() {
            if let Some(state) = store.get_mut(&session_id) {
                let exit_code = status
                    .map(|status| i32::try_from(status.exit_code()).unwrap_or(-1))
                    .unwrap_or(-1);
                if state.status == "cancelled" || state.status == "cancelling" {
                    state.status = "cancelled".to_string();
                    state.exit_code = Some(state.exit_code.unwrap_or(exit_code));
                    state.child_process_id = None;
                    state.child = None;
                    state.stdin = None;
                    state.updated_at_epoch_ms = current_epoch_millis();
                    let _ = persist_external_agent_session_snapshot(&app, state);
                    event = Some(external_agent_session_event_payload(
                        "cancelled",
                        state,
                        "system",
                        None,
                    ));
                    if let Some(payload) = event {
                        let _ = app.emit(EXTERNAL_AGENT_SESSION_EVENT, payload);
                    }
                    return;
                }
                let final_output_path = state.final_output_path.clone();
                let final_output = read_external_agent_final_output(&final_output_path);
                let final_output = if final_output.trim().is_empty() {
                    read_external_agent_stdout_final_output(
                        &state.agent_type,
                        &state.logs,
                        exit_code,
                    )
                } else {
                    final_output
                };
                state.exit_code = Some(exit_code);
                state.final_output = final_output;
                state.status = if state.status == "cancelled" || state.status == "cancelling" {
                    "cancelled".to_string()
                } else if exit_code == 0 {
                    "completed".to_string()
                } else {
                    "failed".to_string()
                };
                state.summary = format!("{} Runner 会话结束，退出码 {}", state.label, exit_code);
                state.child_process_id = None;
                state.child = None;
                state.stdin = None;
                state.updated_at_epoch_ms = current_epoch_millis();
                if !state.final_output.trim().is_empty() {
                    let final_output = state.final_output.clone();
                    let _ = push_external_agent_session_log(
                        state,
                        "final",
                        &format!("{final_output}\n"),
                    );
                }
                let log = push_external_agent_session_log(
                    state,
                    "system",
                    &format!("Runner 会话结束，退出码 {exit_code}\n"),
                );
                let _ = persist_external_agent_session_snapshot(&app, state);
                let event_type = match state.status.as_str() {
                    "completed" => "completed",
                    "cancelled" => "cancelled",
                    _ => "error",
                };
                event = Some(external_agent_session_event_payload(
                    event_type, state, "system", log,
                ));
            }
        }
        if let Some(payload) = event {
            let _ = app.emit(EXTERNAL_AGENT_SESSION_EVENT, payload);
        }
    });
}

fn spawn_external_agent_process_waiter(
    app: tauri::AppHandle,
    sessions: ExternalAgentSessionStore,
    session_id: String,
    child: Arc<Mutex<Child>>,
) {
    thread::spawn(move || {
        let status = {
            match child.lock() {
                Ok(mut child) => child.wait().ok(),
                Err(_) => None,
            }
        };
        let mut event = None;
        if let Ok(mut store) = sessions.lock() {
            if let Some(state) = store.get_mut(&session_id) {
                let exit_code = status
                    .map(|status| status.code().unwrap_or(-1))
                    .unwrap_or(-1);
                if state.status == "cancelled" || state.status == "cancelling" {
                    state.status = "cancelled".to_string();
                    state.exit_code = Some(state.exit_code.unwrap_or(exit_code));
                    state.child_process_id = None;
                    state.process_child = None;
                    state.updated_at_epoch_ms = current_epoch_millis();
                    let _ = persist_external_agent_session_snapshot(&app, state);
                    event = Some(external_agent_session_event_payload(
                        "cancelled",
                        state,
                        "system",
                        None,
                    ));
                    if let Some(payload) = event {
                        let _ = app.emit(EXTERNAL_AGENT_SESSION_EVENT, payload);
                    }
                    return;
                }
                let final_output_path = state.final_output_path.clone();
                let final_output = read_external_agent_final_output(&final_output_path);
                let final_output = if final_output.trim().is_empty() {
                    read_external_agent_stdout_final_output(
                        &state.agent_type,
                        &state.logs,
                        exit_code,
                    )
                } else {
                    final_output
                };
                state.exit_code = Some(exit_code);
                state.final_output = final_output;
                state.status = if state.status == "cancelled" || state.status == "cancelling" {
                    "cancelled".to_string()
                } else if exit_code == 0 {
                    "completed".to_string()
                } else {
                    "failed".to_string()
                };
                state.summary = format!("{} Runner 会话结束，退出码 {}", state.label, exit_code);
                state.child_process_id = None;
                state.process_child = None;
                state.updated_at_epoch_ms = current_epoch_millis();
                if !state.final_output.trim().is_empty() {
                    let final_output = state.final_output.clone();
                    let _ = push_external_agent_session_log(
                        state,
                        "final",
                        &format!("{final_output}\n"),
                    );
                }
                let log = push_external_agent_session_log(
                    state,
                    "system",
                    &format!("Runner 会话结束，退出码 {exit_code}\n"),
                );
                let _ = persist_external_agent_session_snapshot(&app, state);
                let event_type = match state.status.as_str() {
                    "completed" => "completed",
                    "cancelled" => "cancelled",
                    _ => "error",
                };
                event = Some(external_agent_session_event_payload(
                    event_type, state, "system", log,
                ));
            }
        }
        if let Some(payload) = event {
            let _ = app.emit(EXTERNAL_AGENT_SESSION_EVENT, payload);
        }
    });
}

fn read_external_agent_final_output(path: &str) -> String {
    let normalized_path = path.trim();
    if normalized_path.is_empty() {
        return String::new();
    }
    let output = fs::read_to_string(normalized_path).unwrap_or_default();
    let _ = fs::remove_file(normalized_path);
    truncate_text(output.trim().to_string(), 40_000).0
}

fn read_external_agent_stdout_final_output(
    agent_type: &str,
    logs: &[ExternalAgentSessionLog],
    exit_code: i32,
) -> String {
    if exit_code != 0 {
        return String::new();
    }
    if !external_agent_uses_stdout_final_output(agent_type) {
        return String::new();
    }
    let text = logs
        .iter()
        .filter(|item| {
            let stream = item.stream.trim();
            stream == "pty" || stream == "stdout"
        })
        .map(|item| item.content.as_str())
        .collect::<Vec<_>>()
        .join("");
    truncate_text(text.trim().to_string(), 40_000).0
}

fn external_agent_uses_stdout_final_output(agent_type: &str) -> bool {
    agent_type == "hermes" || agent_type == "claude_code"
}

fn external_agent_session_snapshot(
    state: &ExternalAgentSessionState,
    since_seq: u64,
) -> ExternalAgentSessionSnapshot {
    ExternalAgentSessionSnapshot {
        session_id: state.session_id.clone(),
        agent_type: state.agent_type.clone(),
        label: state.label.clone(),
        command: state.command.clone(),
        args: state.args.clone(),
        workspace_path: state.workspace_path.clone(),
        status: state.status.clone(),
        exit_code: state.exit_code,
        started_at_epoch_ms: state.started_at_epoch_ms,
        updated_at_epoch_ms: state.updated_at_epoch_ms,
        logs: state
            .logs
            .iter()
            .filter(|item| item.seq > since_seq)
            .cloned()
            .collect(),
        next_seq: state.next_seq,
        final_output: state.final_output.clone(),
        blocked_reason: state.blocked_reason.clone(),
        summary: state.summary.clone(),
        stdin_open: state.stdin.is_some(),
    }
}

fn external_agent_session_minimal_snapshot(
    state: &ExternalAgentSessionState,
    log: Option<&ExternalAgentSessionLog>,
) -> ExternalAgentSessionSnapshot {
    ExternalAgentSessionSnapshot {
        session_id: state.session_id.clone(),
        agent_type: state.agent_type.clone(),
        label: state.label.clone(),
        command: state.command.clone(),
        args: state.args.clone(),
        workspace_path: state.workspace_path.clone(),
        status: state.status.clone(),
        exit_code: state.exit_code,
        started_at_epoch_ms: state.started_at_epoch_ms,
        updated_at_epoch_ms: state.updated_at_epoch_ms,
        logs: log.cloned().into_iter().collect(),
        next_seq: state.next_seq,
        final_output: String::new(),
        blocked_reason: state.blocked_reason.clone(),
        summary: state.summary.clone(),
        stdin_open: state.stdin.is_some(),
    }
}

fn filter_external_agent_session_snapshot_logs(
    mut snapshot: ExternalAgentSessionSnapshot,
    since_seq: u64,
) -> ExternalAgentSessionSnapshot {
    snapshot.logs = snapshot
        .logs
        .into_iter()
        .filter(|item| item.seq > since_seq)
        .collect();
    snapshot
}

fn external_agent_session_snapshot_store_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    let dir = app_data_dir.join("external-agent-sessions");
    fs::create_dir_all(&dir).map_err(|err| err.to_string())?;
    Ok(dir)
}

fn external_agent_session_snapshot_path(
    app: &tauri::AppHandle,
    session_id: &str,
) -> Result<PathBuf, String> {
    let normalized = safe_store_file_token(session_id, 120);
    if normalized.is_empty() {
        return Err("缺少 Runner 会话 ID".to_string());
    }
    Ok(external_agent_session_snapshot_store_dir(app)?.join(format!("{normalized}.json")))
}

fn persist_external_agent_session_snapshot(
    app: &tauri::AppHandle,
    state: &ExternalAgentSessionState,
) -> Result<(), String> {
    let snapshot = external_agent_session_snapshot(state, 0);
    persist_external_agent_session_snapshot_value(app, &snapshot)
}

fn persist_external_agent_session_snapshot_value(
    app: &tauri::AppHandle,
    snapshot: &ExternalAgentSessionSnapshot,
) -> Result<(), String> {
    let path = external_agent_session_snapshot_path(app, &snapshot.session_id)?;
    let content = serde_json::to_string_pretty(&snapshot).map_err(|err| err.to_string())?;
    fs::write(path, content).map_err(|err| err.to_string())
}

fn normalize_detached_external_agent_session_snapshot(
    app: &tauri::AppHandle,
    mut snapshot: ExternalAgentSessionSnapshot,
) -> Result<ExternalAgentSessionSnapshot, String> {
    let status = snapshot.status.trim().to_string();
    if status != "running" && status != "cancelling" {
        return Ok(snapshot);
    }

    let now = current_epoch_millis();
    snapshot.updated_at_epoch_ms = now;
    snapshot.stdin_open = false;
    if status == "cancelling" {
        snapshot.status = "cancelled".to_string();
        snapshot.exit_code = Some(snapshot.exit_code.unwrap_or(-15));
        snapshot.summary = format!("{} Runner 会话已取消", snapshot.label);
        snapshot.logs.push(ExternalAgentSessionLog {
            seq: snapshot.next_seq,
            stream: "system".to_string(),
            content: "Runner 会话已取消\n".to_string(),
            created_at_epoch_ms: now,
        });
    } else {
        snapshot.status = "failed".to_string();
        snapshot.exit_code = Some(snapshot.exit_code.unwrap_or(-1));
        if snapshot.blocked_reason.trim().is_empty() {
            snapshot.blocked_reason =
                "Runner 会话没有可恢复的本机进程句柄，已停止标记为运行中".to_string();
        }
        snapshot.summary = format!("{} Runner 会话已中断", snapshot.label);
        snapshot.logs.push(ExternalAgentSessionLog {
            seq: snapshot.next_seq,
            stream: "system".to_string(),
            content: "Runner 会话没有可恢复的本机进程句柄，已停止标记为运行中\n".to_string(),
            created_at_epoch_ms: now,
        });
    }
    snapshot.next_seq = snapshot.next_seq.saturating_add(1);
    persist_external_agent_session_snapshot_value(app, &snapshot)?;
    Ok(snapshot)
}

fn is_external_agent_terminal_status(status: &str) -> bool {
    matches!(
        status.trim(),
        "blocked" | "completed" | "failed" | "cancelled" | "unavailable"
    )
}

fn configure_command_process_group(command: &mut Command) {
    #[cfg(unix)]
    unsafe {
        command.pre_exec(|| {
            if libc::setsid() == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
}

fn signal_external_agent_process_tree(child_process_id: Option<u32>) {
    #[cfg(unix)]
    if let Some(pid) = child_process_id {
        if pid > 0 {
            let pgid = -(pid as libc::pid_t);
            unsafe {
                let _ = libc::kill(pgid, libc::SIGTERM);
                thread::sleep(Duration::from_millis(80));
                let _ = libc::kill(pgid, libc::SIGKILL);
            }
            return;
        }
    }

    #[cfg(not(unix))]
    let _ = child_process_id;
}

fn read_external_agent_session_snapshot(
    app: &tauri::AppHandle,
    session_id: &str,
) -> Result<Option<ExternalAgentSessionSnapshot>, String> {
    let path = external_agent_session_snapshot_path(app, session_id)?;
    match fs::read_to_string(path) {
        Ok(content) if content.trim().is_empty() => Ok(None),
        Ok(content) => serde_json::from_str(&content)
            .map(Some)
            .map_err(|err| err.to_string()),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(err) => Err(err.to_string()),
    }
}

fn read_external_agent_session_snapshots(
    app: &tauri::AppHandle,
) -> Result<Vec<ExternalAgentSessionSnapshot>, String> {
    let dir = external_agent_session_snapshot_store_dir(app)?;
    let mut snapshots = Vec::new();
    let entries = fs::read_dir(dir).map_err(|err| err.to_string())?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        if let Ok(content) = fs::read_to_string(&path) {
            if let Ok(snapshot) = serde_json::from_str::<ExternalAgentSessionSnapshot>(&content) {
                snapshots.push(snapshot);
            }
        }
    }
    snapshots.sort_by(|a, b| b.updated_at_epoch_ms.cmp(&a.updated_at_epoch_ms));
    Ok(snapshots)
}

fn safe_store_file_token(value: &str, max_len: usize) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.') {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim_matches(['.', '_', '-'])
        .chars()
        .take(max_len)
        .collect()
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

fn receive_process_output_with_status(
    receiver: Option<mpsc::Receiver<String>>,
    timeout: Duration,
    output_incomplete: &mut bool,
) -> String {
    match receiver {
        Some(receiver) => match receiver.recv_timeout(timeout) {
            Ok(value) => value,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                *output_incomplete = true;
                String::new()
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => String::new(),
        },
        None => String::new(),
    }
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
        .manage(Arc::new(Mutex::new(HashMap::<
            String,
            ExternalAgentSessionState,
        >::new())))
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
            prepare_external_agent_launch,
            run_external_agent_once,
            start_external_agent_session,
            get_external_agent_session,
            list_external_agent_sessions,
            cancel_external_agent_session,
            hard_kill_external_agent_session,
            write_external_agent_session_input,
            record_runner_permission_decision,
            list_runner_permission_decisions
        ])
        .run(tauri::generate_context!())
        .expect("error while running AI Employee Factory desktop app");
}
