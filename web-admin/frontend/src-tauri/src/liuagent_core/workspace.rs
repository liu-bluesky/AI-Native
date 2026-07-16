//! workspace 路径安全。
//!
//! 本地工具只能访问用户选择的 workspace。模型可以传入 workspace 内绝对路径，
//! 但 `../` 或外部绝对路径仍会被拒绝。

use std::path::{Component, Path, PathBuf};

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
    let candidate = if raw.is_empty() {
        root.to_path_buf()
    } else if PathBuf::from(raw).is_absolute() {
        PathBuf::from(raw)
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
    let raw_path = PathBuf::from(raw);
    let candidate = if raw_path.is_absolute() {
        raw_path
    } else {
        root.join(raw_path)
    };
    let candidate = normalize_path_lexically(&candidate);
    if !candidate.starts_with(root) {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "path escapes workspace",
        ));
    }
    let parent = candidate
        .parent()
        .ok_or_else(|| ToolError::new("tool.schema_invalid", "path must include a file name"))?;
    let mut existing_ancestor = parent;
    let mut missing_segments = Vec::new();
    while !existing_ancestor.exists() {
        let segment = existing_ancestor.file_name().ok_or_else(|| {
            ToolError::new("workspace.not_accessible", "path has no accessible parent")
        })?;
        missing_segments.push(segment.to_os_string());
        existing_ancestor = existing_ancestor.parent().ok_or_else(|| {
            ToolError::new("workspace.not_accessible", "path has no accessible parent")
        })?;
    }
    let canonical_ancestor = existing_ancestor.canonicalize().map_err(|err| {
        ToolError::new(
            "workspace.not_accessible",
            format!("parent path is not accessible: {err}"),
        )
    })?;
    if !canonical_ancestor.starts_with(root) {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "path escapes workspace",
        ));
    }
    let mut resolved_parent = canonical_ancestor;
    for segment in missing_segments.iter().rev() {
        resolved_parent.push(segment);
    }
    let target =
        resolved_parent.join(candidate.file_name().ok_or_else(|| {
            ToolError::new("tool.schema_invalid", "path must include a file name")
        })?);
    if target.symlink_metadata().is_ok() {
        let canonical_target = target.canonicalize().map_err(|err| {
            ToolError::new(
                "workspace.not_accessible",
                format!("target path is not accessible: {err}"),
            )
        })?;
        if !canonical_target.starts_with(root) {
            return Err(ToolError::new(
                "workspace.out_of_scope",
                "path escapes workspace",
            ));
        }
        return Ok(canonical_target);
    }
    Ok(target)
}

fn normalize_path_lexically(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(component.as_os_str()),
            Component::Normal(segment) => normalized.push(segment),
        }
    }
    normalized
}

pub fn workspace_relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .map(|value| value.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().replace('\\', "/"))
}
