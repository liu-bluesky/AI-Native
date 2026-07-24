use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use super::types::ToolError;
use super::workspace::{resolve_workspace_write_target, workspace_relative_path};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct FileChangeSnapshot {
    path: String,
    existed: bool,
    baseline_base64: String,
    baseline_hash: String,
    created_at_epoch_ms: u64,
    #[serde(default = "default_review_status")]
    review_status: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileChangeReviewItem {
    pub path: String,
    pub change_type: String,
    pub baseline_hash: String,
    pub current_hash: String,
    pub created_at_epoch_ms: u64,
    pub review_status: String,
}

fn default_review_status() -> String {
    "pending".to_string()
}

fn review_dir(root: &Path) -> PathBuf {
    root.join(".ai-employee").join("file-change-review")
}

fn fingerprint(bytes: &[u8]) -> String {
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in bytes {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("fnv1a64:{hash:016x}")
}

fn snapshot_path(root: &Path, relative_path: &str) -> PathBuf {
    review_dir(root).join(format!("{}.json", fingerprint(relative_path.as_bytes())))
}

fn read_snapshot(path: &Path) -> Result<FileChangeSnapshot, ToolError> {
    let raw = fs::read_to_string(path).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read review snapshot failed: {err}"),
        )
    })?;
    serde_json::from_str(&raw).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("parse review snapshot failed: {err}"),
        )
    })
}

pub fn capture_baseline(root: &Path, target: &Path) -> Result<(), ToolError> {
    let relative_path = workspace_relative_path(root, target);
    let destination = snapshot_path(root, &relative_path);
    if destination.exists() {
        let existing = read_snapshot(&destination)?;
        if existing.review_status != "accepted" {
            return Ok(());
        }
    }
    let existed = target.exists();
    let baseline = if existed {
        fs::read(target).map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read baseline failed: {err}"),
            )
        })?
    } else {
        Vec::new()
    };
    fs::create_dir_all(review_dir(root)).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("create review dir failed: {err}"),
        )
    })?;
    let snapshot = FileChangeSnapshot {
        path: relative_path,
        existed,
        baseline_base64: STANDARD.encode(&baseline),
        baseline_hash: fingerprint(&baseline),
        created_at_epoch_ms: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|value| value.as_millis() as u64)
            .unwrap_or(0),
        review_status: default_review_status(),
    };
    let payload = serde_json::to_vec(&snapshot).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("encode review snapshot failed: {err}"),
        )
    })?;
    fs::write(destination, payload).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("write review snapshot failed: {err}"),
        )
    })
}

pub fn list_changes(root: &Path) -> Result<Vec<FileChangeReviewItem>, String> {
    let directory = review_dir(root);
    if !directory.exists() {
        return Ok(Vec::new());
    }
    let mut items = Vec::new();
    for entry in fs::read_dir(directory).map_err(|err| format!("无法读取变更审查目录：{err}"))?
    {
        let path = entry.map_err(|err| err.to_string())?.path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let snapshot = read_snapshot(&path).map_err(|err| err.message)?;
        let target =
            resolve_workspace_write_target(root, &snapshot.path).map_err(|err| err.message)?;
        let current = if target.exists() {
            fs::read(&target).map_err(|err| format!("无法读取当前文件：{err}"))?
        } else {
            Vec::new()
        };
        items.push(FileChangeReviewItem {
            path: snapshot.path,
            change_type: if !snapshot.existed {
                "added"
            } else if !target.exists() {
                "deleted"
            } else {
                "modified"
            }
            .to_string(),
            baseline_hash: snapshot.baseline_hash,
            current_hash: fingerprint(&current),
            created_at_epoch_ms: snapshot.created_at_epoch_ms,
            review_status: snapshot.review_status,
        });
    }
    items.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(items)
}

pub fn accept_change(root: &Path, relative_path: &str, expected_hash: &str) -> Result<(), String> {
    let target = resolve_workspace_write_target(root, relative_path).map_err(|err| err.message)?;
    let current = if target.exists() {
        fs::read(&target).map_err(|err| err.to_string())?
    } else {
        Vec::new()
    };
    if !expected_hash.is_empty() && fingerprint(&current) != expected_hash {
        return Err("文件已被外部修改，请刷新后重新审查".to_string());
    }
    let path = snapshot_path(root, relative_path);
    let mut snapshot = read_snapshot(&path).map_err(|err| err.message)?;
    snapshot.review_status = "accepted".to_string();
    let payload = serde_json::to_vec(&snapshot).map_err(|err| err.to_string())?;
    fs::write(path, payload).map_err(|err| format!("无法完成确认：{err}"))?;
    Ok(())
}

pub fn revert_change(root: &Path, relative_path: &str, expected_hash: &str) -> Result<(), String> {
    let metadata_path = snapshot_path(root, relative_path);
    let snapshot = read_snapshot(&metadata_path).map_err(|err| err.message)?;
    let target = resolve_workspace_write_target(root, relative_path).map_err(|err| err.message)?;
    let current = if target.exists() {
        fs::read(&target).map_err(|err| err.to_string())?
    } else {
        Vec::new()
    };
    if !expected_hash.is_empty() && fingerprint(&current) != expected_hash {
        return Err("文件已被外部修改，已阻止撤回覆盖".to_string());
    }
    if snapshot.existed {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|err| err.to_string())?;
        }
        let baseline = STANDARD
            .decode(snapshot.baseline_base64)
            .map_err(|err| err.to_string())?;
        fs::write(&target, baseline).map_err(|err| format!("恢复文件失败：{err}"))?;
    } else if target.exists() {
        fs::remove_file(&target).map_err(|err| format!("撤回新增文件失败：{err}"))?;
    }
    fs::remove_file(metadata_path).map_err(|err| format!("清理审查快照失败：{err}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_workspace() -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "ai-employee-file-review-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&path).unwrap();
        path
    }

    #[test]
    fn accepted_change_gets_new_baseline_on_next_edit() {
        let root = fs::canonicalize(temp_workspace()).unwrap();
        let target = root.join("sample.txt");
        fs::write(&target, "before\n").unwrap();
        capture_baseline(&root, &target).unwrap();
        fs::write(&target, "first\n").unwrap();
        let first = list_changes(&root).unwrap().remove(0);
        accept_change(&root, &first.path, &first.current_hash).unwrap();

        capture_baseline(&root, &target).unwrap();
        fs::write(&target, "second\n").unwrap();
        let second = list_changes(&root).unwrap().remove(0);
        assert_eq!(second.review_status, "pending");
        revert_change(&root, &second.path, &second.current_hash).unwrap();
        assert_eq!(fs::read_to_string(&target).unwrap(), "first\n");
        fs::remove_dir_all(root).unwrap();
    }
}
