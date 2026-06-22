//! 本地命令工具。
//!
//! 命令执行必须限定在 workspace 内，并按风险分类接入 Permission Gate。

use serde_json::{json, Value};
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

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

    run_shell_command(&root, &cwd, &cmd, timeout_ms, max_output_chars)
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
) -> Result<(Value, String), ToolError> {
    let temp_base = command_temp_base();
    let stdout_path = temp_base.with_extension("stdout");
    let stderr_path = temp_base.with_extension("stderr");
    let stdout_file = File::create(&stdout_path).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("create stdout failed: {err}"),
        )
    })?;
    let stderr_file = File::create(&stderr_path).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("create stderr failed: {err}"),
        )
    })?;

    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_string());
    let started = Instant::now();
    let mut child = Command::new(shell)
        .arg("-lc")
        .arg(cmd)
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_file))
        .stderr(Stdio::from(stderr_file))
        .spawn()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("spawn command failed: {err}"),
            )
        })?;

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
                    "tool.execution_failed",
                    format!("wait command failed: {err}"),
                ));
            }
        }
    };

    let duration_ms = started.elapsed().as_millis() as u64;
    let (stdout, stdout_truncated) = read_output_file(&stdout_path, max_output_chars);
    let (stderr, stderr_truncated) = read_output_file(&stderr_path, max_output_chars);
    cleanup_temp_outputs(&stdout_path, &stderr_path);
    let truncated = stdout_truncated || stderr_truncated;

    if timed_out {
        return Err(ToolError::new(
            "tool.timeout",
            format!("command timed out after {timeout_ms}ms"),
        ));
    }

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
            "cwd": workspace_relative_path(root, cwd)
        }),
        summary,
    ))
}

fn command_temp_base() -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    std::env::temp_dir().join(format!("liuagent_command_{nonce}"))
}

fn read_output_file(path: &Path, max_chars: usize) -> (String, bool) {
    let raw = fs::read(path).unwrap_or_default();
    let output = String::from_utf8_lossy(&raw).to_string();
    truncate_chars(&output, max_chars)
}

fn truncate_chars(value: &str, max_chars: usize) -> (String, bool) {
    if value.chars().count() <= max_chars {
        return (value.to_string(), false);
    }
    let truncated = value.chars().take(max_chars).collect::<String>();
    (truncated, true)
}

fn cleanup_temp_outputs(stdout_path: &Path, stderr_path: &Path) {
    let _ = fs::remove_file(stdout_path);
    let _ = fs::remove_file(stderr_path);
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
