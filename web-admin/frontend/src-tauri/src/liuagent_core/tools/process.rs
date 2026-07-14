//! 后台进程会话注册表。
//!
//! `run_command(background=true)` 只负责创建会话；后续状态、日志、输入和终止
//! 全部通过 `process(action=...)` 这一条模型工具管理。

use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crate::liuagent_core::args::{number_arg, required_string_arg};
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};
use crate::liuagent_core::workspace::{resolve_workspace_root, workspace_relative_path};

const MAX_LOG_LINES: i64 = 2_000;
const DEFAULT_WAIT_TIMEOUT_MS: i64 = 5_000;
const MAX_WAIT_TIMEOUT_MS: i64 = 5 * 60 * 1_000;
const FINISHED_SESSION_LIMIT: usize = 100;

static PROCESS_REGISTRY: OnceLock<Mutex<HashMap<String, Arc<ProcessSession>>>> = OnceLock::new();
static SESSION_SEQUENCE: AtomicU64 = AtomicU64::new(1);

fn registry() -> &'static Mutex<HashMap<String, Arc<ProcessSession>>> {
    PROCESS_REGISTRY.get_or_init(|| Mutex::new(HashMap::new()))
}

#[derive(Default)]
struct ProcessOutput {
    bytes: Vec<u8>,
    poll_cursor: usize,
    truncated: bool,
}

struct ProcessState {
    status: String,
    exit_code: Option<i32>,
    terminating: bool,
    updated_at_epoch_ms: u128,
}

struct ProcessSession {
    id: String,
    command: String,
    workspace_path: PathBuf,
    cwd: String,
    pid: u32,
    started_at_epoch_ms: u128,
    started: Instant,
    max_output_bytes: usize,
    child: Mutex<Child>,
    state: Mutex<ProcessState>,
    output: Mutex<ProcessOutput>,
    state_path: PathBuf,
    log_path: PathBuf,
}

impl ProcessSession {
    fn append_output(&self, stream: &str, bytes: &[u8]) {
        if bytes.is_empty() {
            return;
        }
        let mut tagged = Vec::with_capacity(bytes.len() + 16);
        if stream == "stderr" {
            tagged.extend_from_slice(b"[stderr] ");
        }
        tagged.extend_from_slice(bytes);

        if let Ok(mut output) = self.output.lock() {
            output.bytes.extend_from_slice(&tagged);
            if output.bytes.len() > self.max_output_bytes {
                let remove_count = output.bytes.len() - self.max_output_bytes;
                output.bytes.drain(..remove_count);
                output.poll_cursor = output.poll_cursor.saturating_sub(remove_count);
                output.truncated = true;
            }
        }
        append_log(&self.log_path, &tagged);
    }

    fn refresh(&self) -> Result<(), ToolError> {
        let status = {
            let mut child = self.child.lock().map_err(|_| {
                ToolError::new("tool.execution_failed", "process child lock poisoned")
            })?;
            child.try_wait().map_err(|err| {
                ToolError::new(
                    "tool.execution_failed",
                    format!("poll process failed: {err}"),
                )
            })?
        };
        if let Some(status) = status {
            self.mark_exited(status)?;
        }
        Ok(())
    }

    fn mark_exited(&self, exit_status: ExitStatus) -> Result<(), ToolError> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| ToolError::new("tool.execution_failed", "process state lock poisoned"))?;
        if state.status != "running" {
            return Ok(());
        }
        let exit_code = exit_status.code().unwrap_or(-1);
        state.exit_code = Some(exit_code);
        state.status = if state.terminating {
            "killed".to_string()
        } else {
            "exited".to_string()
        };
        state.updated_at_epoch_ms = epoch_millis();
        drop(state);
        self.persist_state()
    }

    fn persist_state(&self) -> Result<(), ToolError> {
        let state = self
            .state
            .lock()
            .map_err(|_| ToolError::new("tool.execution_failed", "process state lock poisoned"))?;
        write_json(
            &self.state_path,
            json!({
                "record_type": "liuagent-process-session",
                "version": 1,
                "session_id": self.id,
                "command": self.command,
                "workspace_path": self.workspace_path.to_string_lossy(),
                "cwd": self.cwd,
                "pid": self.pid,
                "status": state.status,
                "exit_code": state.exit_code,
                "started_at_epoch_ms": self.started_at_epoch_ms,
                "updated_at_epoch_ms": state.updated_at_epoch_ms,
                "log_path": self.log_path.to_string_lossy(),
            }),
        )
    }

    fn snapshot(&self, consume_output: bool) -> Result<Value, ToolError> {
        self.refresh()?;
        let state = self
            .state
            .lock()
            .map_err(|_| ToolError::new("tool.execution_failed", "process state lock poisoned"))?;
        let mut output = self
            .output
            .lock()
            .map_err(|_| ToolError::new("tool.execution_failed", "process output lock poisoned"))?;
        let new_output = if consume_output {
            let bytes = output.bytes[output.poll_cursor..].to_vec();
            output.poll_cursor = output.bytes.len();
            String::from_utf8_lossy(&bytes).to_string()
        } else {
            String::new()
        };
        let preview_start = output.bytes.len().saturating_sub(2_000);
        let preview = String::from_utf8_lossy(&output.bytes[preview_start..]).to_string();
        Ok(json!({
            "session_id": self.id,
            "command": self.command,
            "status": state.status,
            "pid": self.pid,
            "cwd": self.cwd,
            "uptime_ms": self.started.elapsed().as_millis() as u64,
            "exit_code": state.exit_code,
            "output": new_output,
            "output_preview": preview,
            "truncated": output.truncated,
            "log_path": self.log_path.to_string_lossy(),
        }))
    }
}

pub fn spawn_background_process(
    root: &Path,
    cwd: &Path,
    command_text: &str,
    max_output_chars: usize,
) -> Result<(Value, String), ToolError> {
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_string());
    let mut command = Command::new(shell);
    command
        .arg("-lc")
        .arg(command_text)
        .current_dir(cwd)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    configure_process_group(&mut command);

    let mut child = command.spawn().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("spawn background process failed: {err}"),
        )
    })?;
    let pid = child.id();
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let session_id = next_session_id();
    let session_dir = root
        .join(".ai-employee")
        .join("liuagent-processes")
        .join(&session_id);
    fs::create_dir_all(&session_dir).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("create process session directory failed: {err}"),
        )
    })?;
    let started_at_epoch_ms = epoch_millis();
    let session = Arc::new(ProcessSession {
        id: session_id.clone(),
        command: command_text.to_string(),
        workspace_path: root.to_path_buf(),
        cwd: workspace_relative_path(root, cwd),
        pid,
        started_at_epoch_ms,
        started: Instant::now(),
        max_output_bytes: max_output_chars,
        child: Mutex::new(child),
        state: Mutex::new(ProcessState {
            status: "running".to_string(),
            exit_code: None,
            terminating: false,
            updated_at_epoch_ms: started_at_epoch_ms,
        }),
        output: Mutex::new(ProcessOutput::default()),
        state_path: session_dir.join("state.json"),
        log_path: session_dir.join("process.log"),
    });
    session.persist_state()?;

    if let Some(stdout) = stdout {
        spawn_output_reader(Arc::clone(&session), "stdout", stdout);
    }
    if let Some(stderr) = stderr {
        spawn_output_reader(Arc::clone(&session), "stderr", stderr);
    }
    spawn_exit_watcher(Arc::clone(&session));

    let mut sessions = registry()
        .lock()
        .map_err(|_| ToolError::new("tool.execution_failed", "process registry lock poisoned"))?;
    prune_finished_sessions(&mut sessions);
    sessions.insert(session_id.clone(), Arc::clone(&session));
    drop(sessions);

    Ok((
        json!({
            "status": "running",
            "session_id": session_id,
            "pid": pid,
            "command": command_text,
            "cwd": workspace_relative_path(root, cwd),
            "log_path": session.log_path.to_string_lossy(),
        }),
        format!("后台进程已启动，session_id={}，pid={pid}", session.id),
    ))
}

pub fn process_tool(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let action = required_string_arg(arguments, "action")?.to_ascii_lowercase();
    match action.as_str() {
        "list" => list_processes(&root),
        "poll" | "log" | "wait" | "kill" | "write" | "submit" | "close" => {
            let session_id = required_string_arg(arguments, "session_id")?;
            let session = scoped_session(&root, &session_id)?;
            match action.as_str() {
                "poll" => {
                    let content = session.snapshot(true)?;
                    let status = content["status"].as_str().unwrap_or("unknown").to_string();
                    Ok((content, format!("进程 {session_id} 状态：{status}")))
                }
                "log" => process_log(&session, arguments),
                "wait" => process_wait(&session, arguments),
                "kill" => {
                    let preview = session.snapshot(false)?;
                    require_approval(
                        tool_call_id,
                        "command.process.kill",
                        "medium",
                        "workspace",
                        "终止正在运行的后台进程会话",
                        json!({
                            "action": "kill",
                            "session_id": session.id.as_str(),
                            "pid": preview["pid"],
                            "command": preview["command"],
                            "cwd": preview["cwd"],
                            "status": preview["status"],
                        }),
                        decision,
                    )?;
                    process_kill(&session)
                }
                "write" => process_write(&session, raw_string_arg(arguments, "data"), false),
                "submit" => process_write(&session, raw_string_arg(arguments, "data"), true),
                "close" => process_close(&session),
                _ => unreachable!(),
            }
        }
        _ => Err(ToolError::new(
            "tool.schema_invalid",
            "unknown process action; expected list, poll, log, wait, kill, write, submit, or close",
        )),
    }
}

fn list_processes(root: &Path) -> Result<(Value, String), ToolError> {
    let sessions = registry()
        .lock()
        .map_err(|_| ToolError::new("tool.execution_failed", "process registry lock poisoned"))?;
    let scoped = sessions
        .values()
        .filter(|session| session.workspace_path == root)
        .cloned()
        .collect::<Vec<_>>();
    drop(sessions);
    let mut items = Vec::with_capacity(scoped.len());
    for session in scoped {
        items.push(session.snapshot(false)?);
    }
    items.sort_by(|left, right| {
        right["session_id"]
            .as_str()
            .cmp(&left["session_id"].as_str())
    });
    let count = items.len();
    Ok((
        json!({"processes": items, "count": count}),
        format!("共 {count} 个后台进程会话"),
    ))
}

fn process_log(
    session: &Arc<ProcessSession>,
    arguments: &Value,
) -> Result<(Value, String), ToolError> {
    session.refresh()?;
    let limit = number_arg(arguments, "limit", 200, 1, MAX_LOG_LINES) as usize;
    let offset = number_arg(arguments, "offset", 0, 0, i64::MAX) as usize;
    let raw = fs::read_to_string(&session.log_path).unwrap_or_default();
    let lines = raw.lines().collect::<Vec<_>>();
    let total_lines = lines.len();
    let selected = if offset == 0 {
        &lines[total_lines.saturating_sub(limit)..]
    } else {
        let start = offset.min(total_lines);
        let end = start.saturating_add(limit).min(total_lines);
        &lines[start..end]
    };
    let state = session
        .state
        .lock()
        .map_err(|_| ToolError::new("tool.execution_failed", "process state lock poisoned"))?;
    Ok((
        json!({
            "session_id": session.id,
            "status": state.status,
            "output": selected.join("\n"),
            "offset": offset,
            "limit": limit,
            "total_lines": total_lines,
            "exit_code": state.exit_code,
        }),
        format!("读取进程 {} 日志，共 {} 行", session.id, total_lines),
    ))
}

fn process_wait(
    session: &Arc<ProcessSession>,
    arguments: &Value,
) -> Result<(Value, String), ToolError> {
    let timeout_ms = number_arg(
        arguments,
        "timeout_ms",
        DEFAULT_WAIT_TIMEOUT_MS,
        1,
        MAX_WAIT_TIMEOUT_MS,
    ) as u64;
    let started = Instant::now();
    loop {
        let snapshot = session.snapshot(false)?;
        if snapshot["status"] != "running" {
            return Ok((
                session.snapshot(true)?,
                format!("进程 {} 已结束", session.id),
            ));
        }
        if started.elapsed() >= Duration::from_millis(timeout_ms) {
            return Ok((
                json!({
                    "session_id": session.id,
                    "status": "timeout",
                    "process_status": "running",
                    "timeout_ms": timeout_ms,
                    "output_preview": snapshot["output_preview"],
                }),
                format!("等待 {}ms 后进程 {} 仍在运行", timeout_ms, session.id),
            ));
        }
        thread::sleep(Duration::from_millis(25));
    }
}

fn process_kill(session: &Arc<ProcessSession>) -> Result<(Value, String), ToolError> {
    session.refresh()?;
    {
        let mut state = session
            .state
            .lock()
            .map_err(|_| ToolError::new("tool.execution_failed", "process state lock poisoned"))?;
        if state.status != "running" {
            drop(state);
            return Ok((
                session.snapshot(false)?,
                format!("进程 {} 已经结束", session.id),
            ));
        }
        state.terminating = true;
    }
    terminate_process_group(&session.child, session.pid)?;
    let deadline = Instant::now() + Duration::from_secs(2);
    while Instant::now() < deadline {
        session.refresh()?;
        let status = session
            .state
            .lock()
            .map_err(|_| ToolError::new("tool.execution_failed", "process state lock poisoned"))?
            .status
            .clone();
        if status != "running" {
            return Ok((
                session.snapshot(false)?,
                format!("进程 {} 已终止", session.id),
            ));
        }
        thread::sleep(Duration::from_millis(25));
    }
    force_kill_process_group(&session.child, session.pid)?;
    let force_deadline = Instant::now() + Duration::from_secs(2);
    while Instant::now() < force_deadline {
        session.refresh()?;
        let status = session
            .state
            .lock()
            .map_err(|_| ToolError::new("tool.execution_failed", "process state lock poisoned"))?
            .status
            .clone();
        if status != "running" {
            break;
        }
        thread::sleep(Duration::from_millis(25));
    }
    Ok((
        session.snapshot(false)?,
        format!("进程 {} 已强制终止", session.id),
    ))
}

fn process_write(
    session: &Arc<ProcessSession>,
    mut data: String,
    submit: bool,
) -> Result<(Value, String), ToolError> {
    session.refresh()?;
    let state = session
        .state
        .lock()
        .map_err(|_| ToolError::new("tool.execution_failed", "process state lock poisoned"))?;
    if state.status != "running" {
        return Err(ToolError::new(
            "process.not_running",
            format!("process {} is not running", session.id),
        ));
    }
    drop(state);
    if submit {
        data.push('\n');
    }
    let mut child = session
        .child
        .lock()
        .map_err(|_| ToolError::new("tool.execution_failed", "process child lock poisoned"))?;
    let stdin = child
        .stdin
        .as_mut()
        .ok_or_else(|| ToolError::new("process.stdin_closed", "process stdin is not available"))?;
    stdin.write_all(data.as_bytes()).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("write process stdin failed: {err}"),
        )
    })?;
    stdin.flush().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("flush process stdin failed: {err}"),
        )
    })?;
    Ok((
        json!({
            "session_id": session.id,
            "status": "ok",
            "bytes_written": data.len(),
            "submitted": submit,
        }),
        format!("已向进程 {} 写入 {} 字节", session.id, data.len()),
    ))
}

fn process_close(session: &Arc<ProcessSession>) -> Result<(Value, String), ToolError> {
    let mut child = session
        .child
        .lock()
        .map_err(|_| ToolError::new("tool.execution_failed", "process child lock poisoned"))?;
    let was_open = child.stdin.take().is_some();
    Ok((
        json!({
            "session_id": session.id,
            "status": if was_open { "ok" } else { "already_closed" },
        }),
        if was_open {
            format!("已关闭进程 {} 的 stdin", session.id)
        } else {
            format!("进程 {} 的 stdin 已关闭", session.id)
        },
    ))
}

fn scoped_session(root: &Path, session_id: &str) -> Result<Arc<ProcessSession>, ToolError> {
    let sessions = registry()
        .lock()
        .map_err(|_| ToolError::new("tool.execution_failed", "process registry lock poisoned"))?;
    let session = sessions.get(session_id).cloned().ok_or_else(|| {
        ToolError::new(
            "process.not_found",
            format!("no process session with ID {session_id}"),
        )
    })?;
    if session.workspace_path != root {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "process session belongs to another workspace",
        ));
    }
    Ok(session)
}

fn spawn_output_reader(
    session: Arc<ProcessSession>,
    stream: &'static str,
    mut reader: impl Read + Send + 'static,
) {
    thread::spawn(move || {
        let mut buffer = [0_u8; 4096];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) => break,
                Ok(count) => session.append_output(stream, &buffer[..count]),
                Err(_) => break,
            }
        }
    });
}

fn spawn_exit_watcher(session: Arc<ProcessSession>) {
    thread::spawn(move || loop {
        if session.refresh().is_err() {
            return;
        }
        let running = session
            .state
            .lock()
            .map(|state| state.status == "running")
            .unwrap_or(false);
        if !running {
            return;
        }
        thread::sleep(Duration::from_millis(100));
    });
}

fn prune_finished_sessions(sessions: &mut HashMap<String, Arc<ProcessSession>>) {
    let finished_count = sessions
        .values()
        .filter(|session| {
            session
                .state
                .lock()
                .map(|state| state.status != "running")
                .unwrap_or(false)
        })
        .count();
    if finished_count <= FINISHED_SESSION_LIMIT {
        return;
    }
    let mut finished = sessions
        .values()
        .filter_map(|session| {
            session.state.lock().ok().and_then(|state| {
                (state.status != "running")
                    .then_some((session.id.clone(), state.updated_at_epoch_ms))
            })
        })
        .collect::<Vec<_>>();
    finished.sort_by_key(|(_, updated)| *updated);
    for (session_id, _) in finished
        .into_iter()
        .take(finished_count - FINISHED_SESSION_LIMIT)
    {
        sessions.remove(&session_id);
    }
}

fn next_session_id() -> String {
    let sequence = SESSION_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    format!("proc_{}_{}", epoch_millis(), sequence)
}

fn raw_string_arg(arguments: &Value, key: &str) -> String {
    arguments
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

fn append_log(path: &Path, bytes: &[u8]) {
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = file.write_all(bytes);
    }
}

fn write_json(path: &Path, value: Value) -> Result<(), ToolError> {
    let bytes = serde_json::to_vec_pretty(&value).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("serialize process state failed: {err}"),
        )
    })?;
    fs::write(path, bytes).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("write process state failed: {err}"),
        )
    })
}

pub(crate) fn configure_process_group(command: &mut Command) {
    #[cfg(unix)]
    unsafe {
        command.pre_exec(|| {
            if libc::setpgid(0, 0) == 0 {
                Ok(())
            } else {
                Err(std::io::Error::last_os_error())
            }
        });
    }
}

pub(crate) fn terminate_child_process_group(child: &mut Child) {
    let pid = child.id();
    #[cfg(unix)]
    unsafe {
        let _ = libc::killpg(pid as i32, libc::SIGTERM);
    }
    #[cfg(not(unix))]
    {
        let _ = child.kill();
    }
}

fn terminate_process_group(child: &Mutex<Child>, pid: u32) -> Result<(), ToolError> {
    #[cfg(unix)]
    unsafe {
        if libc::killpg(pid as i32, libc::SIGTERM) != 0 {
            let error = std::io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::ESRCH) {
                return Err(ToolError::new(
                    "tool.execution_failed",
                    format!("terminate process group failed: {error}"),
                ));
            }
        }
    }
    #[cfg(not(unix))]
    {
        child
            .lock()
            .map_err(|_| ToolError::new("tool.execution_failed", "process child lock poisoned"))?
            .kill()
            .map_err(|err| {
                ToolError::new(
                    "tool.execution_failed",
                    format!("terminate process failed: {err}"),
                )
            })?;
    }
    #[cfg(unix)]
    let _ = child;
    Ok(())
}

fn force_kill_process_group(child: &Mutex<Child>, pid: u32) -> Result<(), ToolError> {
    #[cfg(unix)]
    unsafe {
        if libc::killpg(pid as i32, libc::SIGKILL) != 0 {
            let error = std::io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::ESRCH) {
                return Err(ToolError::new(
                    "tool.execution_failed",
                    format!("kill process group failed: {error}"),
                ));
            }
        }
    }
    #[cfg(not(unix))]
    {
        child
            .lock()
            .map_err(|_| ToolError::new("tool.execution_failed", "process child lock poisoned"))?
            .kill()
            .map_err(|err| {
                ToolError::new(
                    "tool.execution_failed",
                    format!("kill process failed: {err}"),
                )
            })?;
    }
    #[cfg(unix)]
    let _ = child;
    Ok(())
}

pub(crate) fn force_kill_child_process_group(child: &mut Child) {
    let pid = child.id();
    #[cfg(unix)]
    unsafe {
        let _ = libc::killpg(pid as i32, libc::SIGKILL);
    }
    #[cfg(not(unix))]
    {
        let _ = child.kill();
    }
}

fn epoch_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_millis())
        .unwrap_or(0)
}

#[cfg(test)]
pub(crate) fn clear_process_registry_for_tests() {
    if let Ok(mut sessions) = registry().lock() {
        for session in sessions.values() {
            let _ = process_kill(session);
        }
        sessions.clear();
    }
}
