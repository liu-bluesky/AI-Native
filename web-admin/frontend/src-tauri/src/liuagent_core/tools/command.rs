//! 本地命令工具。
//!
//! 命令执行必须限定在 workspace 内，并按风险分类接入 Permission Gate。

use serde_json::{json, Value};
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crate::liuagent_core::args::{number_arg, required_string_arg, string_arg};
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};
use crate::liuagent_core::workspace::{
    resolve_workspace_child, resolve_workspace_root, workspace_relative_path,
};

const DEFAULT_COMMAND_TIMEOUT_MS: i64 = 30_000;
const DEFAULT_LONG_COMMAND_TIMEOUT_MS: i64 = 2 * 60 * 60 * 1_000;
const MAX_COMMAND_TIMEOUT_MS: i64 = 6 * 60 * 60 * 1_000;
const COMMAND_HEARTBEAT_INTERVAL_MS: u64 = 30_000;

pub fn check_command_risk(
    _workspace_path: &str,
    arguments: &Value,
) -> Result<(Value, String), ToolError> {
    let cmd = required_string_arg(arguments, "cmd")?;
    let (risk, reasons) = classify_command_risk(&cmd);
    let requires_approval = risk != "safe";
    let summary = format!("命令风险：{risk}");
    Ok((
        json!({
            "cmd": cmd,
            "risk": risk,
            "reasons": reasons,
            "requires_approval": requires_approval,
            "suggested_preview": {
                "cmd": cmd,
                "cwd": string_arg(arguments, "cwd", "."),
                "risk": risk
            }
        }),
        summary,
    ))
}

pub fn run_command(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    run_command_with_output_sink(
        tool_call_id,
        workspace_path,
        arguments,
        permission_decision,
        None,
    )
}

pub fn run_command_with_output_sink(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
    output_sink: Option<&dyn Fn(&str, &str)>,
) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let cmd = required_string_arg(arguments, "cmd")?;
    let cwd_arg = string_arg(arguments, "cwd", ".");
    let default_timeout_ms = default_command_timeout_ms(&cmd);
    let background_on_timeout = is_long_running_command(&cmd);
    let timeout_ms = number_arg(
        arguments,
        "timeout_ms",
        default_timeout_ms,
        1_000,
        MAX_COMMAND_TIMEOUT_MS,
    ) as u64;
    let max_output_chars =
        number_arg(arguments, "max_output_chars", 20_000, 1_000, 100_000) as usize;
    let cwd = resolve_workspace_child(&root, &cwd_arg, true)?;
    if !cwd.is_dir() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "cwd is not a directory",
        ));
    }

    let (risk, reasons) = classify_command_risk(&cmd);
    if risk != "safe" {
        require_approval(
            tool_call_id,
            "command.run",
            &risk,
            "workspace",
            &format!("执行本地命令：{cmd}"),
            json!({
                "cmd": cmd,
                "cwd": workspace_relative_path(&root, &cwd),
                "risk": risk,
                "reasons": reasons,
                "timeout_ms": timeout_ms,
                "max_output_chars": max_output_chars
            }),
            permission_decision,
        )?;
    }

    run_shell_command(
        &root,
        &cwd,
        &cmd,
        timeout_ms,
        max_output_chars,
        output_sink,
        background_on_timeout,
    )
}

pub fn classify_command_risk(cmd: &str) -> (String, Vec<String>) {
    let normalized = cmd.trim().to_lowercase();
    let mut reasons = Vec::new();
    if normalized.is_empty() {
        return ("medium".to_string(), vec!["empty command".to_string()]);
    }
    if contains_credential_term(&normalized) {
        reasons.push("credential term detected".to_string());
        return ("critical".to_string(), reasons);
    }
    if contains_any(
        &normalized,
        &[
            "rm -rf",
            "sudo ",
            "git push",
            "chmod 777",
            "chown ",
            "kill -9",
            "mkfs",
            "dd if=",
        ],
    ) {
        reasons.push("destructive command pattern".to_string());
        return ("critical".to_string(), reasons);
    }
    if contains_any(
        &normalized,
        &[
            "npm install",
            "pnpm install",
            "pip install",
            "curl ",
            "wget ",
            "docker ",
            "brew install",
        ],
    ) {
        reasons.push("network/install/container command".to_string());
        return ("high".to_string(), reasons);
    }
    if contains_shell_control(&normalized) {
        reasons.push("shell control operator detected".to_string());
        return ("medium".to_string(), reasons);
    }
    if starts_with_any(
        &normalized,
        &[
            "npm run",
            "pnpm run",
            "pytest",
            "cargo test",
            "cargo check",
            "ruff ",
            "eslint ",
        ],
    ) {
        reasons.push("build/test command".to_string());
        return ("medium".to_string(), reasons);
    }
    if is_safe_read_command(&normalized) {
        reasons.push("read-only command".to_string());
        return ("safe".to_string(), reasons);
    }
    reasons.push("unknown command pattern".to_string());
    ("medium".to_string(), reasons)
}

fn default_command_timeout_ms(cmd: &str) -> i64 {
    if is_long_running_command(cmd) {
        DEFAULT_LONG_COMMAND_TIMEOUT_MS
    } else {
        DEFAULT_COMMAND_TIMEOUT_MS
    }
}

fn is_long_running_command(cmd: &str) -> bool {
    let normalized = cmd.trim().to_lowercase();
    if normalized.is_empty() {
        return false;
    }
    starts_with_any(
        &normalized,
        &[
            "npm run build",
            "npm run test",
            "pnpm run build",
            "pnpm run test",
            "yarn build",
            "yarn test",
            "cargo test",
            "cargo check",
            "cargo build",
            "pytest",
            "xcodebuild",
            "flutter build",
            "flutter test",
            "docker build",
            "docker compose build",
            "./gradlew",
            "gradle ",
            "make ",
        ],
    ) || contains_any(
        &normalized,
        &[
            " build",
            " test",
            " deploy",
            " package",
            " upload_deploy_artifacts",
            " package_deploy_artifacts",
        ],
    )
}

fn run_shell_command(
    root: &Path,
    cwd: &Path,
    cmd: &str,
    timeout_ms: u64,
    max_output_chars: usize,
    output_sink: Option<&dyn Fn(&str, &str)>,
    background_on_timeout: bool,
) -> Result<(Value, String), ToolError> {
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_string());
    let started = Instant::now();
    let job = if background_on_timeout {
        Some(CommandJobPaths::new(root)?)
    } else {
        None
    };
    let mut command = Command::new(shell);
    command
        .arg("-lc")
        .arg(cmd)
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(unix)]
    if background_on_timeout {
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
    let mut child = command.spawn().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("spawn command failed: {err}"),
        )
    })?;

    let timeout = Duration::from_millis(timeout_ms);
    let pid = child.id();
    if let Some(job) = &job {
        write_command_job_state(
            &job.state_path,
            json!({
                "record_type": "liuagent-command-job",
                "version": 1,
                "job_id": job.job_id,
                "status": "running",
                "pid": pid,
                "cmd": cmd,
                "cwd": workspace_relative_path(root, cwd),
                "stdout_log_path": job.stdout_path.to_string_lossy(),
                "stderr_log_path": job.stderr_path.to_string_lossy(),
                "started_at_epoch_ms": job.started_at_epoch_ms,
                "updated_at_epoch_ms": epoch_millis(),
            }),
        )?;
    }
    let (tx, rx) = mpsc::channel::<(&'static str, String)>();
    let stdout_handle = child.stdout.take().map(|stream| {
        let tx = tx.clone();
        let log_path = job.as_ref().map(|paths| paths.stdout_path.clone());
        thread::spawn(move || read_command_stream("stdout", stream, tx, log_path))
    });
    let stderr_handle = child.stderr.take().map(|stream| {
        let tx = tx.clone();
        let log_path = job.as_ref().map(|paths| paths.stderr_path.clone());
        thread::spawn(move || read_command_stream("stderr", stream, tx, log_path))
    });
    drop(tx);

    let mut stdout = String::new();
    let mut stderr = String::new();
    let mut stdout_truncated = false;
    let mut stderr_truncated = false;
    let mut exit_code: Option<i32> = None;
    let mut timed_out = false;
    let mut channel_closed = false;
    let mut last_heartbeat = started;

    while !channel_closed || exit_code.is_none() {
        match rx.recv_timeout(Duration::from_millis(20)) {
            Ok((stream, chunk)) => {
                if !chunk.is_empty() {
                    if let Some(sink) = output_sink {
                        sink(stream, &chunk);
                    }
                    if stream == "stderr" {
                        stderr_truncated |=
                            append_truncated_chunk(&mut stderr, &chunk, max_output_chars);
                    } else {
                        stdout_truncated |=
                            append_truncated_chunk(&mut stdout, &chunk, max_output_chars);
                    }
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                channel_closed = true;
            }
        }

        if exit_code.is_some() {
            continue;
        }
        if let Some(sink) = output_sink {
            if started.elapsed().as_millis() >= COMMAND_HEARTBEAT_INTERVAL_MS as u128
                && last_heartbeat.elapsed().as_millis() >= COMMAND_HEARTBEAT_INTERVAL_MS as u128
            {
                let elapsed_ms = started.elapsed().as_millis() as u64;
                sink(
                    "status",
                    &format!("command still running after {elapsed_ms}ms"),
                );
                last_heartbeat = Instant::now();
            }
        }
        match child.try_wait() {
            Ok(Some(status)) => {
                exit_code = Some(status.code().unwrap_or(-1));
            }
            Ok(None) if started.elapsed() >= timeout && background_on_timeout => {
                let duration_ms = started.elapsed().as_millis() as u64;
                if let Some(job) = job {
                    write_command_job_state(
                        &job.state_path,
                        json!({
                            "record_type": "liuagent-command-job",
                            "version": 1,
                            "job_id": job.job_id,
                            "status": "running",
                            "pid": pid,
                            "cmd": cmd,
                            "cwd": workspace_relative_path(root, cwd),
                            "stdout_log_path": job.stdout_path.to_string_lossy(),
                            "stderr_log_path": job.stderr_path.to_string_lossy(),
                            "state_path": job.state_path.to_string_lossy(),
                            "started_at_epoch_ms": job.started_at_epoch_ms,
                            "updated_at_epoch_ms": epoch_millis(),
                            "observation_window_ms": timeout_ms,
                            "duration_ms": duration_ms,
                        }),
                    )?;
                    spawn_command_job_waiter(
                        child,
                        stdout_handle,
                        stderr_handle,
                        job.clone(),
                        cmd.to_string(),
                        workspace_relative_path(root, cwd),
                        pid,
                    );
                    let truncated = stdout_truncated || stderr_truncated;
                    return Ok((
                        json!({
                            "status": "no_signal",
                            "status_reason": "observation_window_elapsed",
                            "terminal": false,
                            "requires_judgement": true,
                            "pid": pid,
                            "background_job": {
                                "job_id": job.job_id,
                                "pid": pid,
                                "state_path": job.state_path.to_string_lossy(),
                                "stdout_log_path": job.stdout_path.to_string_lossy(),
                                "stderr_log_path": job.stderr_path.to_string_lossy(),
                                "status": "running"
                            },
                            "stdout": stdout,
                            "stderr": stderr,
                            "duration_ms": duration_ms,
                            "truncated": truncated,
                            "streamed": output_sink.is_some(),
                            "cwd": workspace_relative_path(root, cwd),
                            "next_actions": ["check_background_job", "continue_waiting", "cancel_job", "ask_ai_to_judge"]
                        }),
                        format!(
                            "命令超过观察窗口 {}ms，已转为后台任务继续执行，pid={pid}",
                            timeout_ms
                        ),
                    ));
                }
            }
            Ok(None) if started.elapsed() >= timeout => {
                let _ = child.kill();
                let _ = child.wait();
                exit_code = Some(-1);
                timed_out = true;
            }
            Ok(None) => {}
            Err(err) => {
                return Err(ToolError::new(
                    "tool.execution_failed",
                    format!("wait command failed: {err}"),
                ));
            }
        }
    }

    if let Some(handle) = stdout_handle {
        let _ = handle.join();
    }
    if let Some(handle) = stderr_handle {
        let _ = handle.join();
    }

    let duration_ms = started.elapsed().as_millis() as u64;
    let truncated = stdout_truncated || stderr_truncated;

    if timed_out {
        return Err(ToolError::new(
            "tool.timeout",
            format!("command timed out after {timeout_ms}ms"),
        ));
    }

    let exit_code = exit_code.unwrap_or(-1);
    let summary = format!(
        "命令退出码 {}，耗时 {}ms{}",
        exit_code,
        duration_ms,
        if truncated { "，输出已截断" } else { "" }
    );
    Ok((
        json!({
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
            "truncated": truncated,
            "streamed": output_sink.is_some(),
            "cwd": workspace_relative_path(root, cwd)
        }),
        summary,
    ))
}

fn read_command_stream(
    stream_name: &'static str,
    mut stream: impl Read,
    tx: mpsc::Sender<(&'static str, String)>,
    log_path: Option<PathBuf>,
) {
    let mut buffer = [0_u8; 4096];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) => {
                let chunk = String::from_utf8_lossy(&buffer[..count]).to_string();
                if let Some(path) = &log_path {
                    append_command_log(path, &chunk);
                }
                if tx.send((stream_name, chunk)).is_err() && log_path.is_none() {
                    break;
                }
            }
            Err(_) => break,
        }
    }
}

#[derive(Clone)]
struct CommandJobPaths {
    job_id: String,
    state_path: PathBuf,
    stdout_path: PathBuf,
    stderr_path: PathBuf,
    started_at_epoch_ms: u128,
}

impl CommandJobPaths {
    fn new(root: &Path) -> Result<Self, ToolError> {
        let started_at_epoch_ms = epoch_millis();
        let job_id = format!("cmd_{started_at_epoch_ms}");
        let dir = root
            .join(".ai-employee")
            .join("liuagent-command-jobs")
            .join(&job_id);
        fs::create_dir_all(&dir).map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create command job directory failed: {err}"),
            )
        })?;
        Ok(Self {
            job_id,
            state_path: dir.join("state.json"),
            stdout_path: dir.join("stdout.log"),
            stderr_path: dir.join("stderr.log"),
            started_at_epoch_ms,
        })
    }
}

fn spawn_command_job_waiter(
    mut child: std::process::Child,
    stdout_handle: Option<thread::JoinHandle<()>>,
    stderr_handle: Option<thread::JoinHandle<()>>,
    job: CommandJobPaths,
    cmd: String,
    cwd: String,
    pid: u32,
) {
    thread::spawn(move || {
        let status = child.wait();
        if let Some(handle) = stdout_handle {
            let _ = handle.join();
        }
        if let Some(handle) = stderr_handle {
            let _ = handle.join();
        }
        let previous_state = fs::read_to_string(&job.state_path)
            .ok()
            .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
            .unwrap_or_else(|| json!({}));
        if previous_state
            .get("status")
            .and_then(Value::as_str)
            .map(|value| value == "cancelled")
            .unwrap_or(false)
        {
            return;
        }
        let (job_status, exit_code, error) = match status {
            Ok(status) => {
                let exit_code = status.code().unwrap_or(-1);
                (
                    if exit_code == 0 {
                        "succeeded"
                    } else {
                        "failed"
                    },
                    exit_code,
                    String::new(),
                )
            }
            Err(err) => ("unknown", -1, format!("wait command job failed: {err}")),
        };
        let _ = write_command_job_state(
            &job.state_path,
            json!({
                "record_type": "liuagent-command-job",
                "version": 1,
                "job_id": job.job_id,
                "status": job_status,
                "pid": pid,
                "cmd": cmd,
                "cwd": cwd,
                "exit_code": exit_code,
                "error": error,
                "stdout_log_path": job.stdout_path.to_string_lossy(),
                "stderr_log_path": job.stderr_path.to_string_lossy(),
                "state_path": job.state_path.to_string_lossy(),
                "started_at_epoch_ms": job.started_at_epoch_ms,
                "updated_at_epoch_ms": epoch_millis(),
            }),
        );
    });
}

fn append_command_log(path: &Path, chunk: &str) {
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = file.write_all(chunk.as_bytes());
    }
}

fn write_command_job_state(path: &Path, value: Value) -> Result<(), ToolError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create command job state directory failed: {err}"),
            )
        })?;
    }
    let bytes = serde_json::to_vec_pretty(&value).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("serialize command job state failed: {err}"),
        )
    })?;
    fs::write(path, bytes).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("write command job state failed: {err}"),
        )
    })
}

fn epoch_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_millis())
        .unwrap_or(0)
}

fn append_truncated_chunk(output: &mut String, chunk: &str, max_chars: usize) -> bool {
    let current_len = output.chars().count();
    if current_len >= max_chars {
        return !chunk.is_empty();
    }
    let remaining = max_chars - current_len;
    let chunk_len = chunk.chars().count();
    if chunk_len <= remaining {
        output.push_str(chunk);
        false
    } else {
        output.extend(chunk.chars().take(remaining));
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn long_running_commands_default_to_hours_not_seconds() {
        assert_eq!(
            default_command_timeout_ms("npm run build"),
            DEFAULT_LONG_COMMAND_TIMEOUT_MS
        );
        assert_eq!(
            default_command_timeout_ms("cargo test"),
            DEFAULT_LONG_COMMAND_TIMEOUT_MS
        );
        assert_eq!(
            default_command_timeout_ms("pwd"),
            DEFAULT_COMMAND_TIMEOUT_MS
        );
    }

    #[test]
    fn command_timeout_accepts_hour_level_values() {
        let arguments = json!({"cmd": "npm run build", "timeout_ms": 3 * 60 * 60 * 1_000});
        let timeout_ms = number_arg(
            &arguments,
            "timeout_ms",
            default_command_timeout_ms("npm run build"),
            1_000,
            MAX_COMMAND_TIMEOUT_MS,
        );

        assert_eq!(timeout_ms, 3 * 60 * 60 * 1_000);
    }

    #[test]
    fn command_timeout_clamps_only_above_maximum() {
        let arguments = json!({"cmd": "npm run build", "timeout_ms": 24 * 60 * 60 * 1_000});
        let timeout_ms = number_arg(
            &arguments,
            "timeout_ms",
            default_command_timeout_ms("npm run build"),
            1_000,
            MAX_COMMAND_TIMEOUT_MS,
        );

        assert_eq!(timeout_ms, MAX_COMMAND_TIMEOUT_MS);
    }

    #[test]
    fn long_running_command_timeout_returns_background_job_no_signal() {
        let root = std::env::temp_dir().join(format!("liuagent_command_job_{}", epoch_millis()));
        fs::create_dir_all(&root).unwrap();

        let (content, summary) =
            run_shell_command(&root, &root, "sleep 0.2", 20, 20_000, None, true).unwrap();

        assert_eq!(content["status"], "no_signal");
        assert_eq!(content["terminal"], false);
        assert_eq!(content["requires_judgement"], true);
        assert!(content["background_job"]["pid"].as_u64().unwrap_or(0) > 0);
        let state_path = content["background_job"]["state_path"].as_str().unwrap();
        assert!(Path::new(state_path).exists());
        assert!(summary.contains("后台任务继续执行"));

        std::thread::sleep(Duration::from_millis(350));
        let state = fs::read_to_string(state_path).unwrap();
        assert!(state.contains("\"status\": \"succeeded\""), "{state}");
        let _ = fs::remove_dir_all(root);
    }
}

fn contains_credential_term(value: &str) -> bool {
    contains_any(
        value,
        &[
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "private_key",
        ],
    )
}

fn contains_any(value: &str, patterns: &[&str]) -> bool {
    patterns.iter().any(|pattern| value.contains(pattern))
}

fn starts_with_any(value: &str, patterns: &[&str]) -> bool {
    patterns.iter().any(|pattern| value.starts_with(pattern))
}

fn contains_shell_control(value: &str) -> bool {
    contains_any(value, &[";", "&&", "||", "|", "`", "$(", ">", "<"])
}

fn is_safe_read_command(value: &str) -> bool {
    value == "pwd"
        || value == "ls"
        || starts_with_any(value, &["ls ", "rg ", "git status", "git log"])
}
