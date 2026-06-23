//! 本地命令工具。
//!
//! 命令执行必须限定在 workspace 内，并按风险分类接入 Permission Gate。

use serde_json::{json, Value};
use std::io::Read;
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use crate::liuagent_core::args::{number_arg, required_string_arg, string_arg};
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};
use crate::liuagent_core::workspace::{
    resolve_workspace_child, resolve_workspace_root, workspace_relative_path,
};

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
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
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

    run_shell_command(&root, &cwd, &cmd, timeout_ms, max_output_chars, output_sink)
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

fn run_shell_command(
    root: &Path,
    cwd: &Path,
    cmd: &str,
    timeout_ms: u64,
    max_output_chars: usize,
    output_sink: Option<&dyn Fn(&str, &str)>,
) -> Result<(Value, String), ToolError> {
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_string());
    let started = Instant::now();
    let mut child = Command::new(shell)
        .arg("-lc")
        .arg(cmd)
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("spawn command failed: {err}"),
            )
        })?;

    let timeout = Duration::from_millis(timeout_ms);
    let (tx, rx) = mpsc::channel::<(&'static str, String)>();
    let stdout_handle = child.stdout.take().map(|stream| {
        let tx = tx.clone();
        thread::spawn(move || read_command_stream("stdout", stream, tx))
    });
    let stderr_handle = child.stderr.take().map(|stream| {
        let tx = tx.clone();
        thread::spawn(move || read_command_stream("stderr", stream, tx))
    });
    drop(tx);

    let mut stdout = String::new();
    let mut stderr = String::new();
    let mut stdout_truncated = false;
    let mut stderr_truncated = false;
    let mut exit_code: Option<i32> = None;
    let mut timed_out = false;
    let mut channel_closed = false;

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
        match child.try_wait() {
            Ok(Some(status)) => {
                exit_code = Some(status.code().unwrap_or(-1));
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
) {
    let mut buffer = [0_u8; 4096];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) => {
                let chunk = String::from_utf8_lossy(&buffer[..count]).to_string();
                if tx.send((stream_name, chunk)).is_err() {
                    break;
                }
            }
            Err(_) => break,
        }
    }
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
