//! 本地文件只读工具。
//!
//! 这些工具可以直接给 CLI 和桌面端共用；写入类工具后续必须接入权限确认。

use serde_json::{json, Value};
use std::fs;
use std::path::Path;
use std::process::{Command, Stdio};

use crate::liuagent_core::args::{bool_arg, number_arg, required_string_arg, string_arg};
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};
use crate::liuagent_core::workspace::{
    resolve_workspace_child, resolve_workspace_root, resolve_workspace_write_target,
    workspace_relative_path,
};

pub fn list_files(workspace_path: &str, arguments: &Value) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let path = string_arg(arguments, "path", ".");
    let max_depth = number_arg(arguments, "max_depth", 2, 1, 5);
    let include_hidden = bool_arg(arguments, "include_hidden", false);
    let target = resolve_workspace_child(&root, &path, true)?;
    if !target.is_dir() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "path is not a directory",
        ));
    }

    let mut entries = Vec::new();
    let mut truncated = false;
    collect_file_entries(
        &root,
        &target,
        max_depth,
        include_hidden,
        &mut entries,
        &mut truncated,
    )?;
    let summary = format!(
        "列出 {} 个条目{}",
        entries.len(),
        if truncated { "（已截断）" } else { "" }
    );
    Ok((json!({"entries": entries, "truncated": truncated}), summary))
}

pub fn read_file(workspace_path: &str, arguments: &Value) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let path = required_string_arg(arguments, "path")?;
    let start_line = number_arg(arguments, "start_line", 1, 1, 1_000_000) as usize;
    let line_count = number_arg(arguments, "line_count", 200, 1, 5_000) as usize;
    let target = resolve_workspace_child(&root, &path, true)?;
    if !target.is_file() {
        return Err(ToolError::new("tool.schema_invalid", "path is not a file"));
    }
    let metadata = target.metadata().map_err(|err| {
        ToolError::new("tool.execution_failed", format!("metadata failed: {err}"))
    })?;
    if metadata.len() > 2 * 1024 * 1024 {
        return Err(ToolError::new(
            "tool.output_too_large",
            "file is larger than 2MB",
        ));
    }
    let raw = fs::read(&target)
        .map_err(|err| ToolError::new("tool.execution_failed", format!("read failed: {err}")))?;
    let text = String::from_utf8_lossy(&raw).to_string();
    let lines: Vec<&str> = text.split('\n').collect();
    let total_lines = lines.len();
    let from = start_line.saturating_sub(1).min(total_lines);
    let to = (from + line_count).min(total_lines);
    let content = lines[from..to].join("\n");
    let end_line = if to == 0 { 0 } else { to };
    let summary = format!(
        "读取 {} 行 {}-{}/{}",
        path, start_line, end_line, total_lines
    );
    Ok((
        json!({
            "path": workspace_relative_path(&root, &target),
            "content": content,
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total_lines,
            "truncated": end_line < total_lines
        }),
        summary,
    ))
}

pub fn search_text(workspace_path: &str, arguments: &Value) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let query = required_string_arg(arguments, "query")?;
    let path = string_arg(arguments, "path", ".");
    let glob = string_arg(arguments, "glob", "");
    let max_results = number_arg(arguments, "max_results", 50, 1, 200) as usize;
    let target = resolve_workspace_child(&root, &path, true)?;
    if !target.is_dir() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "path is not a directory",
        ));
    }

    let mut matches = Vec::new();
    let mut truncated = false;
    search_text_recursive(
        &root,
        &target,
        &query,
        &glob,
        max_results,
        &mut matches,
        &mut truncated,
    )?;
    let summary = format!(
        "搜索 \"{}\" 命中 {} 处{}",
        query,
        matches.len(),
        if truncated { "（已截断）" } else { "" }
    );
    Ok((json!({"matches": matches, "truncated": truncated}), summary))
}

pub fn write_file(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let path = required_string_arg(arguments, "path")?;
    let content = arguments
        .get("content")
        .and_then(Value::as_str)
        .ok_or_else(|| ToolError::new("tool.schema_invalid", "missing required argument: content"))?
        .to_string();
    let overwrite = bool_arg(arguments, "overwrite", false);
    let target = resolve_workspace_write_target(&root, &path)?;
    let exists = target.exists();
    if exists && !target.is_file() {
        return Err(ToolError::new("tool.schema_invalid", "path is not a file"));
    }
    if exists && !overwrite {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "file already exists; set overwrite=true to replace it",
        ));
    }
    let relative_path = workspace_relative_path(&root, &target);
    let previous_size = target
        .metadata()
        .map(|metadata| metadata.len())
        .unwrap_or(0);
    let next_size = content.len() as u64;
    let risk = if exists { "high" } else { "medium" };
    let reason = if exists {
        format!("覆盖本地文件 {relative_path}")
    } else {
        format!("创建本地文件 {relative_path}")
    };
    require_approval(
        tool_call_id,
        "file.write",
        risk,
        "workspace",
        &reason,
        json!({
            "path": relative_path,
            "exists": exists,
            "overwrite": overwrite,
            "previous_size": previous_size,
            "next_size": next_size
        }),
        permission_decision,
    )?;

    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            ToolError::new("tool.execution_failed", format!("create dir failed: {err}"))
        })?;
    }
    fs::write(&target, content.as_bytes())
        .map_err(|err| ToolError::new("tool.execution_failed", format!("write failed: {err}")))?;
    let summary = format!(
        "{} {}（{} 字节）",
        if exists { "覆盖" } else { "创建" },
        relative_path,
        next_size
    );
    Ok((
        json!({
            "path": relative_path,
            "created": !exists,
            "overwritten": exists,
            "bytes": next_size
        }),
        summary,
    ))
}

pub fn delete_file(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let path = required_string_arg(arguments, "path")?;
    let target = resolve_workspace_child(&root, &path, true)?;
    if !target.exists() {
        return Err(ToolError::new("tool.not_found", "file does not exist"));
    }
    if !target.is_file() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "delete_file only supports files",
        ));
    }
    let relative_path = workspace_relative_path(&root, &target);
    let previous_size = target
        .metadata()
        .map(|metadata| metadata.len())
        .unwrap_or(0);
    require_approval(
        tool_call_id,
        "file.delete",
        "high",
        "workspace",
        &format!("删除本地文件 {relative_path}"),
        json!({
            "path": relative_path,
            "exists": true,
            "size": previous_size,
            "recoverable": false
        }),
        permission_decision,
    )?;

    fs::remove_file(&target)
        .map_err(|err| ToolError::new("tool.execution_failed", format!("delete failed: {err}")))?;
    let exists_after = target.exists();
    if exists_after {
        return Err(ToolError::new(
            "tool.execution_failed",
            "delete command returned but file still exists",
        ));
    }
    Ok((
        json!({
            "path": relative_path,
            "deleted": true,
            "exists_after": false,
            "previous_size": previous_size
        }),
        format!("删除 {relative_path}，已验证文件不存在"),
    ))
}

pub fn apply_patch(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let patch = arguments
        .get("patch")
        .and_then(Value::as_str)
        .ok_or_else(|| ToolError::new("tool.schema_invalid", "missing required argument: patch"))?
        .to_string();
    let summary_arg = required_string_arg(arguments, "summary")?;
    if patch.trim().is_empty() {
        return Err(ToolError::new("tool.schema_invalid", "patch is required"));
    }
    let changed_files = extract_patch_paths(&patch)?;
    for path in &changed_files {
        let target = resolve_workspace_write_target(&root, path)?;
        if !target.starts_with(&root) {
            return Err(ToolError::new(
                "workspace.out_of_scope",
                "patch path escapes workspace",
            ));
        }
    }
    require_approval(
        tool_call_id,
        "file.write",
        "medium",
        "workspace",
        &format!("应用 patch：{summary_arg}"),
        json!({
            "summary": summary_arg,
            "changed_files": changed_files,
            "patch_chars": patch.len()
        }),
        permission_decision,
    )?;

    run_git_apply(&root, &patch, true)?;
    run_git_apply(&root, &patch, false)?;
    let summary = format!(
        "应用 patch：{} 个文件变更。{}",
        changed_files.len(),
        summary_arg
    );
    Ok((
        json!({
            "changed_files": changed_files,
            "applied": true
        }),
        summary,
    ))
}

fn collect_file_entries(
    root: &Path,
    directory: &Path,
    depth_left: i64,
    include_hidden: bool,
    entries: &mut Vec<Value>,
    truncated: &mut bool,
) -> Result<(), ToolError> {
    if *truncated || entries.len() >= 500 {
        *truncated = true;
        return Ok(());
    }
    let mut children = fs::read_dir(directory)
        .map_err(|err| ToolError::new("tool.execution_failed", format!("read dir failed: {err}")))?
        .filter_map(Result::ok)
        .collect::<Vec<_>>();
    children.sort_by_key(|entry| entry.file_name().to_string_lossy().to_lowercase());

    for child in children {
        let name = child.file_name().to_string_lossy().to_string();
        if !include_hidden && name.starts_with('.') {
            continue;
        }
        let metadata = match child.metadata() {
            Ok(value) => value,
            Err(_) => continue,
        };
        let path = child.path();
        entries.push(json!({
            "path": workspace_relative_path(root, &path),
            "type": if metadata.is_dir() { "directory" } else { "file" },
            "size": metadata.len()
        }));
        if entries.len() >= 500 {
            *truncated = true;
            break;
        }
        if metadata.is_dir() && depth_left > 1 {
            collect_file_entries(
                root,
                &path,
                depth_left - 1,
                include_hidden,
                entries,
                truncated,
            )?;
        }
        if *truncated {
            break;
        }
    }
    Ok(())
}

fn search_text_recursive(
    root: &Path,
    directory: &Path,
    query: &str,
    glob: &str,
    max_results: usize,
    matches: &mut Vec<Value>,
    truncated: &mut bool,
) -> Result<(), ToolError> {
    if *truncated || matches.len() >= max_results {
        *truncated = true;
        return Ok(());
    }
    let entries = fs::read_dir(directory).map_err(|err| {
        ToolError::new("tool.execution_failed", format!("read dir failed: {err}"))
    })?;
    let query_lower = query.to_lowercase();
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with('.') || matches!(name.as_str(), "node_modules" | "__pycache__") {
            continue;
        }
        let metadata = match entry.metadata() {
            Ok(value) => value,
            Err(_) => continue,
        };
        if metadata.is_dir() {
            search_text_recursive(root, &path, query, glob, max_results, matches, truncated)?;
        } else if metadata.is_file() && glob_matches(&name, glob) && metadata.len() <= 1024 * 1024 {
            if let Ok(raw) = fs::read_to_string(&path) {
                for (index, line) in raw.lines().enumerate() {
                    if line.to_lowercase().contains(&query_lower) {
                        matches.push(json!({
                            "path": workspace_relative_path(root, &path),
                            "line": index + 1,
                            "content": line.trim()
                        }));
                        if matches.len() >= max_results {
                            *truncated = true;
                            return Ok(());
                        }
                    }
                }
            }
        }
        if *truncated {
            break;
        }
    }
    Ok(())
}

fn glob_matches(name: &str, glob: &str) -> bool {
    let pattern = glob.trim();
    if pattern.is_empty() || pattern == "*" {
        return true;
    }
    if let Some(suffix) = pattern.strip_prefix("*.") {
        return name.ends_with(&format!(".{suffix}"));
    }
    name == pattern
}

fn extract_patch_paths(patch: &str) -> Result<Vec<String>, ToolError> {
    let mut changed = Vec::new();
    for line in patch.lines() {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("diff --git ") {
            let parts = rest.split_whitespace().collect::<Vec<_>>();
            if parts.len() >= 2 {
                push_patch_path(&mut changed, parts[0])?;
                push_patch_path(&mut changed, parts[1])?;
            }
        } else if trimmed.starts_with("--- ") || trimmed.starts_with("+++ ") {
            let path = trimmed
                .split_once(' ')
                .map(|(_, path)| path)
                .unwrap_or("")
                .trim();
            push_patch_path(&mut changed, path)?;
        }
    }
    if changed.is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "patch does not contain changed files",
        ));
    }
    Ok(changed)
}

fn push_patch_path(changed: &mut Vec<String>, raw: &str) -> Result<(), ToolError> {
    let path = normalize_patch_path(raw);
    if path.is_empty() {
        return Ok(());
    }
    if Path::new(&path).is_absolute() || path.split('/').any(|part| part == "..") {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "patch path escapes workspace",
        ));
    }
    if !changed.iter().any(|item| item == &path) {
        changed.push(path);
    }
    Ok(())
}

fn normalize_patch_path(raw: &str) -> String {
    let mut path = raw.trim();
    if path == "/dev/null" {
        return String::new();
    }
    if let Some((before_tab, _)) = path.split_once('\t') {
        path = before_tab.trim();
    }
    if path.starts_with('"') && path.ends_with('"') && path.len() >= 2 {
        path = &path[1..path.len() - 1];
    }
    if let Some(stripped) = path.strip_prefix("a/").or_else(|| path.strip_prefix("b/")) {
        return stripped.to_string();
    }
    path.to_string()
}

fn run_git_apply(root: &Path, patch: &str, check_only: bool) -> Result<(), ToolError> {
    let mut command = Command::new("git");
    command.arg("apply");
    if check_only {
        command.arg("--check");
    } else {
        command.arg("--verbose");
    }
    command
        .arg("--whitespace=fix")
        .arg("-")
        .current_dir(root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = command.spawn().map_err(|err| {
        ToolError::new("tool.execution_failed", format!("git apply failed: {err}"))
    })?;
    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        stdin.write_all(patch.as_bytes()).map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("write patch failed: {err}"),
            )
        })?;
    }
    let output = child.wait_with_output().map_err(|err| {
        ToolError::new("tool.execution_failed", format!("git apply failed: {err}"))
    })?;
    if output.status.success() {
        return Ok(());
    }
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    Err(ToolError::new(
        "tool.schema_invalid",
        if stderr.is_empty() { stdout } else { stderr },
    ))
}
