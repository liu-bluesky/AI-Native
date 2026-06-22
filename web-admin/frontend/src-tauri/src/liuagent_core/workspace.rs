//! workspace 路径安全。
//!
//! 本地工具只能访问用户选择的 workspace，拒绝绝对路径和 `../` 逃逸。

use std::path::{Path, PathBuf};

use super::types::ToolError;

pub fn resolve_workspace_root(workspace_path: &str) -> Result<PathBuf, ToolError> {
    let raw = workspace_path.trim();
    if raw.is_empty() {
        return Err(ToolError::new(
            "workspace.not_configured",
            "workspace_path is required",
        ));
    }
    let root = PathBuf::from(raw).canonicalize().map_err(|err| {
        ToolError::new(
            "workspace.not_accessible",
            format!("workspace is not accessible: {err}"),
        )
    })?;
    if !root.is_dir() {
        return Err(ToolError::new(
            "workspace.not_directory",
            "workspace is not a directory",
        ));
    }
    Ok(root)
}

pub fn resolve_workspace_child(
    root: &Path,
    raw_path: &str,
    must_exist: bool,
) -> Result<PathBuf, ToolError> {
    let raw = raw_path.trim();
    if PathBuf::from(raw).is_absolute() {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "absolute paths are not allowed",
        ));
    }
    let candidate = if raw.is_empty() {
        root.to_path_buf()
    } else {
        root.join(raw)
    };
    let resolved = if must_exist {
        candidate.canonicalize().map_err(|err| {
            ToolError::new(
                "workspace.not_accessible",
                format!("path is not accessible: {err}"),
            )
        })?
    } else {
        candidate
    };
    if !resolved.starts_with(root) {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "path escapes workspace",
        ));
    }
    Ok(resolved)
}

pub fn resolve_workspace_write_target(root: &Path, raw_path: &str) -> Result<PathBuf, ToolError> {
    let raw = raw_path.trim();
    if raw.is_empty() {
        return Err(ToolError::new("tool.schema_invalid", "path is required"));
    }
    if PathBuf::from(raw).is_absolute() {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "absolute paths are not allowed",
        ));
    }
    let candidate = root.join(raw);
    let parent = candidate
        .parent()
        .ok_or_else(|| ToolError::new("tool.schema_invalid", "path must include a file name"))?;
    let resolved_parent = if parent.exists() {
        parent.canonicalize().map_err(|err| {
            ToolError::new(
                "workspace.not_accessible",
                format!("parent path is not accessible: {err}"),
            )
        })?
    } else {
        parent.to_path_buf()
    };
    if !resolved_parent.starts_with(root) {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "path escapes workspace",
        ));
    }
    Ok(resolved_parent.join(
        candidate.file_name().ok_or_else(|| {
            ToolError::new("tool.schema_invalid", "path must include a file name")
        })?,
    ))
}

pub fn workspace_relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .map(|value| value.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().replace('\\', "/"))
}
