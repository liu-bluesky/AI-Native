//! 本地文件只读工具。
//!
//! 这些工具可以直接给 CLI 和桌面端共用；写入类工具后续必须接入权限确认。

use serde_json::{json, Value};
use std::fs;
use std::path::Path;
use std::process::{Command, Stdio};

use crate::liuagent_core::args::{bool_arg, number_arg, required_string_arg, string_arg};
use crate::liuagent_core::file_change_review::capture_baseline;
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
    Ok((
        json!({
            "path": workspace_relative_path(&root, &target),
            "entries": entries,
            "truncated": truncated
        }),
        summary,
    ))
}

pub fn read_file(workspace_path: &str, arguments: &Value) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let path = required_string_arg(arguments, "path")?;
    enforce_cli_entry_file_read_policy(arguments, &path)?;
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
    let lines: Vec<&str> = text.lines().collect();
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
    enforce_cli_entry_file_search_policy(arguments, &path, &glob)?;
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
        arguments,
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
    Ok((
        json!({
            "query": query,
            "path": workspace_relative_path(&root, &target),
            "glob": glob,
            "matches": matches,
            "truncated": truncated
        }),
        summary,
    ))
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
        .ok_or_else(|| {
            ToolError::new(
                "tool.schema_invalid",
                "missing required argument: content. Re-emit write_file with both path and full content, or use apply_patch for partial edits.",
            )
        })?
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
    let previous_content = if exists {
        fs::read_to_string(&target).unwrap_or_default()
    } else {
        String::new()
    };
    capture_baseline(&root, &target)?;
    fs::write(&target, content.as_bytes())
        .map_err(|err| ToolError::new("tool.execution_failed", format!("write failed: {err}")))?;
    let (added, removed, diff) =
        build_file_diff_preview(&relative_path, &previous_content, &content);
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
            "bytes": next_size,
            "added": added,
            "removed": removed,
            "diff": diff
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

    let previous_content = if previous_size <= 200_000 {
        fs::read_to_string(&target).unwrap_or_default()
    } else {
        String::new()
    };
    capture_baseline(&root, &target)?;
    fs::remove_file(&target)
        .map_err(|err| ToolError::new("tool.execution_failed", format!("delete failed: {err}")))?;
    let exists_after = target.exists();
    if exists_after {
        return Err(ToolError::new(
            "tool.execution_failed",
            "delete command returned but file still exists",
        ));
    }
    let (added, removed, diff) = build_file_diff_preview(&relative_path, &previous_content, "");
    Ok((
        json!({
            "path": relative_path,
            "deleted": true,
            "exists_after": false,
            "previous_size": previous_size,
            "added": added,
            "removed": removed,
            "diff": diff
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
    let patch = normalize_apply_patch_input(&root, &patch)?;
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
    for path in &changed_files {
        let target = resolve_workspace_write_target(&root, path)?;
        capture_baseline(&root, &target)?;
    }
    run_git_apply(&root, &patch, false)?;
    let summary = format!(
        "应用 patch：{} 个文件变更。{}",
        changed_files.len(),
        summary_arg
    );
    let (added, removed) = diff_line_stats(&patch);
    Ok((
        json!({
            "changed_files": changed_files,
            "applied": true,
            "added": added,
            "removed": removed,
            "diff": patch
        }),
        summary,
    ))
}

fn normalize_apply_patch_input(root: &Path, patch: &str) -> Result<String, ToolError> {
    if !patch.lines().any(|line| line.trim() == "*** Begin Patch") {
        return Ok(patch.to_string());
    }
    codex_patch_to_git_diff(root, patch)
}

fn codex_patch_to_git_diff(root: &Path, patch: &str) -> Result<String, ToolError> {
    #[derive(Debug)]
    struct Update {
        path: String,
        lines: Vec<String>,
    }

    let mut updates = Vec::<Update>::new();
    let mut current: Option<Update> = None;
    let mut seen_begin = false;
    let mut seen_end = false;

    for raw_line in patch.lines() {
        let line = raw_line.trim_end_matches('\r');
        if line == "*** Begin Patch" {
            seen_begin = true;
            continue;
        }
        if line == "*** End Patch" {
            if let Some(update) = current.take() {
                updates.push(update);
            }
            seen_end = true;
            continue;
        }
        if let Some(path) = line.strip_prefix("*** Update File: ") {
            if let Some(update) = current.take() {
                updates.push(update);
            }
            current = Some(Update {
                path: path.trim().to_string(),
                lines: Vec::new(),
            });
            continue;
        }
        if line.starts_with("*** Add File: ")
            || line.starts_with("*** Delete File: ")
            || line.starts_with("*** Move to: ")
        {
            return Err(ToolError::new(
                "tool.schema_invalid",
                "Codex apply_patch format currently supports Update File hunks only",
            ));
        }
        if !seen_begin || line.starts_with("@@") || line == "*** End of File" {
            continue;
        }
        if let Some(update) = current.as_mut() {
            if line.starts_with(' ') || line.starts_with('+') || line.starts_with('-') {
                update.lines.push(line.to_string());
            } else if !line.trim().is_empty() {
                return Err(ToolError::new(
                    "tool.schema_invalid",
                    format!("invalid Codex patch line for {}: {}", update.path, line),
                ));
            }
        }
    }
    if !seen_begin || !seen_end {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "invalid Codex apply_patch envelope",
        ));
    }
    if updates.is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "patch does not contain changed files",
        ));
    }

    let mut git_diff = Vec::<String>::new();
    for update in updates {
        let relative_path = normalize_patch_path(&update.path);
        if relative_path.is_empty()
            || Path::new(&relative_path).is_absolute()
            || relative_path.split('/').any(|part| part == "..")
        {
            return Err(ToolError::new(
                "workspace.out_of_scope",
                "patch path escapes workspace",
            ));
        }
        let target = root.join(&relative_path);
        let before = fs::read_to_string(&target).map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read patch target failed: {relative_path}: {err}"),
            )
        })?;
        let before_lines = before.lines().map(str::to_string).collect::<Vec<_>>();
        let after_lines = apply_codex_update_lines(&relative_path, &before_lines, &update.lines)?;
        let diff = build_unified_diff(&relative_path, &before_lines, &after_lines);
        if !diff.is_empty() {
            git_diff.push(diff);
        }
    }
    if git_diff.is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "patch does not contain changed files",
        ));
    }
    Ok(git_diff.join("\n"))
}

fn apply_codex_update_lines(
    path: &str,
    before_lines: &[String],
    patch_lines: &[String],
) -> Result<Vec<String>, ToolError> {
    let mut after = Vec::<String>::new();
    let mut source_index = 0usize;
    for patch_line in patch_lines {
        let (marker, text) = patch_line.split_at(1);
        match marker {
            " " => {
                let found =
                    find_context_line(before_lines, source_index, text).ok_or_else(|| {
                        ToolError::new(
                            "tool.schema_invalid",
                            format!("Codex patch context not found in {path}: {text}"),
                        )
                    })?;
                after.extend(before_lines[source_index..found].iter().cloned());
                after.push(before_lines[found].clone());
                source_index = found + 1;
            }
            "-" => {
                let found =
                    find_context_line(before_lines, source_index, text).ok_or_else(|| {
                        ToolError::new(
                            "tool.schema_invalid",
                            format!("Codex patch removal not found in {path}: {text}"),
                        )
                    })?;
                after.extend(before_lines[source_index..found].iter().cloned());
                source_index = found + 1;
            }
            "+" => after.push(text.to_string()),
            _ => {
                return Err(ToolError::new(
                    "tool.schema_invalid",
                    format!("invalid Codex patch marker in {path}: {marker}"),
                ));
            }
        }
    }
    after.extend(before_lines[source_index..].iter().cloned());
    Ok(after)
}

fn find_context_line(lines: &[String], start: usize, expected: &str) -> Option<usize> {
    lines
        .iter()
        .enumerate()
        .skip(start)
        .find_map(|(index, line)| if line == expected { Some(index) } else { None })
}

fn build_unified_diff(path: &str, before_lines: &[String], after_lines: &[String]) -> String {
    if before_lines == after_lines {
        return String::new();
    }
    let mut prefix = 0usize;
    while prefix < before_lines.len()
        && prefix < after_lines.len()
        && before_lines[prefix] == after_lines[prefix]
    {
        prefix += 1;
    }
    let mut suffix = 0usize;
    while suffix + prefix < before_lines.len()
        && suffix + prefix < after_lines.len()
        && before_lines[before_lines.len() - 1 - suffix]
            == after_lines[after_lines.len() - 1 - suffix]
    {
        suffix += 1;
    }
    let before_end = before_lines.len().saturating_sub(suffix);
    let after_end = after_lines.len().saturating_sub(suffix);
    let context_before = if prefix > 0 { 1 } else { 0 };
    let context_after = if suffix > 0 { 1 } else { 0 };
    let old_start_index = prefix.saturating_sub(context_before);
    let new_start_index = prefix.saturating_sub(context_before);
    let old_end = (before_end + context_after).min(before_lines.len());
    let new_end = (after_end + context_after).min(after_lines.len());
    let old_count = old_end.saturating_sub(old_start_index);
    let new_count = new_end.saturating_sub(new_start_index);
    let mut lines = vec![
        format!("diff --git a/{path} b/{path}"),
        format!("--- a/{path}"),
        format!("+++ b/{path}"),
        format!(
            "@@ -{},{} +{},{} @@",
            old_start_index + 1,
            old_count,
            new_start_index + 1,
            new_count
        ),
    ];
    for line in &before_lines[old_start_index..prefix] {
        lines.push(format!(" {line}"));
    }
    for line in &before_lines[prefix..before_end] {
        lines.push(format!("-{line}"));
    }
    for line in &after_lines[prefix..after_end] {
        lines.push(format!("+{line}"));
    }
    for line in &before_lines[before_end..old_end] {
        lines.push(format!(" {line}"));
    }
    format!("{}\n", lines.join("\n"))
}

fn diff_line_stats(diff: &str) -> (usize, usize) {
    let mut added = 0;
    let mut removed = 0;
    for line in diff.lines() {
        if line.starts_with("+++") || line.starts_with("---") {
            continue;
        }
        if line.starts_with('+') {
            added += 1;
        } else if line.starts_with('-') {
            removed += 1;
        }
    }
    (added, removed)
}

fn build_file_diff_preview(path: &str, before: &str, after: &str) -> (usize, usize, String) {
    if before == after {
        return (0, 0, String::new());
    }
    let before_lines = split_diff_lines(before);
    let after_lines = split_diff_lines(after);
    let mut prefix = 0;
    while prefix < before_lines.len()
        && prefix < after_lines.len()
        && before_lines[prefix] == after_lines[prefix]
    {
        prefix += 1;
    }
    let mut suffix = 0;
    while suffix + prefix < before_lines.len()
        && suffix + prefix < after_lines.len()
        && before_lines[before_lines.len() - 1 - suffix]
            == after_lines[after_lines.len() - 1 - suffix]
    {
        suffix += 1;
    }
    let before_changed_end = before_lines.len().saturating_sub(suffix);
    let after_changed_end = after_lines.len().saturating_sub(suffix);
    let removed_lines = &before_lines[prefix..before_changed_end];
    let added_lines = &after_lines[prefix..after_changed_end];
    let added = added_lines.len();
    let removed = removed_lines.len();
    let mut diff_lines = Vec::new();
    diff_lines.push(format!("--- a/{path}"));
    diff_lines.push(format!("+++ b/{path}"));
    diff_lines.push(format!(
        "@@ -{},{} +{},{} @@",
        prefix + 1,
        removed.max(1),
        prefix + 1,
        added.max(1)
    ));
    let mut emitted = 0usize;
    for line in removed_lines.iter().take(80) {
        diff_lines.push(format!("-{line}"));
        emitted += 1;
    }
    for line in added_lines.iter().take(80) {
        diff_lines.push(format!("+{line}"));
        emitted += 1;
    }
    if removed + added > emitted {
        diff_lines.push(format!(
            "... diff truncated: {} changed lines total",
            removed + added
        ));
    }
    (added, removed, diff_lines.join("\n"))
}

fn split_diff_lines(value: &str) -> Vec<&str> {
    if value.is_empty() {
        Vec::new()
    } else {
        value.split('\n').collect::<Vec<_>>()
    }
}

fn enforce_cli_entry_file_read_policy(arguments: &Value, path: &str) -> Result<(), ToolError> {
    if is_cli_entry_file_access_blocked(arguments, path) {
        return Err(cli_entry_file_blocked_error(path));
    }
    Ok(())
}

fn enforce_cli_entry_file_search_policy(
    arguments: &Value,
    path: &str,
    glob: &str,
) -> Result<(), ToolError> {
    for candidate in [path, glob] {
        if candidate.trim().is_empty() {
            continue;
        }
        if is_cli_entry_file_access_blocked(arguments, candidate) {
            return Err(cli_entry_file_blocked_error(candidate));
        }
    }
    Ok(())
}

fn is_cli_entry_file_access_blocked(arguments: &Value, path: &str) -> bool {
    let normalized_path = normalize_policy_path(path);
    let Some(file_name) = normalized_path.rsplit('/').next() else {
        return false;
    };
    if !cli_entry_file_names(arguments)
        .iter()
        .any(|name| name.eq_ignore_ascii_case(file_name))
    {
        return false;
    }
    let allowed = allowed_cli_entry_file_names(arguments);
    !allowed
        .iter()
        .any(|name| name.eq_ignore_ascii_case(file_name))
}

fn cli_entry_file_blocked_error(path: &str) -> ToolError {
    ToolError::new(
        "entry_file.not_allowed",
        format!(
            "{path} 是 CLI 入口文件；桌面端本地智能体默认只读取项目配置的 AI 入口文件。只有用户明确要求读取该文件，或项目 AI 入口文件配置为该文件时才允许读取。"
        ),
    )
}

fn cli_entry_file_names(arguments: &Value) -> Vec<String> {
    policy_string_list(
        arguments,
        "cli_entry_files",
        &["AGENTS.md", "CLAUDE.md", "HERMES.md"],
    )
}

fn allowed_cli_entry_file_names(arguments: &Value) -> Vec<String> {
    let mut allowed = Vec::new();
    let ai_entry_file = policy_string(arguments, "ai_entry_file");
    if !ai_entry_file.is_empty() {
        if let Some(name) = normalize_policy_path(&ai_entry_file).rsplit('/').next() {
            allowed.push(name.to_string());
        }
    }
    allowed.extend(policy_string_list(
        arguments,
        "explicit_cli_entry_files",
        &[],
    ));
    allowed
}

fn policy_string(arguments: &Value, key: &str) -> String {
    arguments
        .get("file_access_policy")
        .and_then(|value| value.get(key))
        .and_then(Value::as_str)
        .map(normalize_policy_path)
        .unwrap_or_default()
}

fn policy_string_list(arguments: &Value, key: &str, fallback: &[&str]) -> Vec<String> {
    let values = arguments
        .get("file_access_policy")
        .and_then(|value| value.get(key))
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(normalize_policy_path)
                .filter(|value| !value.is_empty())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if values.is_empty() {
        fallback
            .iter()
            .map(|value| normalize_policy_path(value))
            .collect()
    } else {
        values
    }
}

fn normalize_policy_path(value: &str) -> String {
    value
        .trim()
        .replace('\\', "/")
        .trim_start_matches("./")
        .to_string()
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
    arguments: &Value,
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
            search_text_recursive(
                root,
                &path,
                query,
                glob,
                arguments,
                max_results,
                matches,
                truncated,
            )?;
        } else if metadata.is_file() && glob_matches(&name, glob) && metadata.len() <= 1024 * 1024 {
            let relative_path = workspace_relative_path(root, &path);
            if is_cli_entry_file_access_blocked(arguments, &relative_path) {
                continue;
            }
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
