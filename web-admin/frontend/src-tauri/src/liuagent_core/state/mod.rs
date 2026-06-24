//! 本地状态、transcript、checkpoint 和恢复回放。

use serde::Serialize;
use serde_json::{json, Value};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use super::adapters::protocol::{
    approval_required_event, message_event, state_changed_event, tool_result_event,
};
use super::gateway::{epoch_millis, sanitize_path_segment};
use super::types::{ToolError, ToolExecutionResult};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeArtifactPaths {
    pub state_path: String,
    pub transcript_path: String,
    pub audit_path: String,
    pub checkpoint_path: String,
    pub active_session_path: String,
    pub session_history_path: String,
    pub outbox_path: String,
    pub runtime_events: Vec<Value>,
}

pub struct RuntimePersistenceInput<'a> {
    pub workspace_root: &'a Path,
    pub project_id: &'a str,
    pub chat_session_id: &'a str,
    pub session_id: &'a str,
    pub user_message_id: &'a str,
    pub assistant_message_id: &'a str,
    pub user_message: &'a str,
    pub assistant_content: &'a str,
    pub run_status: &'a str,
    pub waiting_for: Option<&'a str>,
    pub model_runtime: Value,
    pub tool_results: &'a [ToolExecutionResult],
    pub operations: Value,
    pub audit_logs: &'a [Value],
}

pub fn write_runtime_artifacts(
    input: RuntimePersistenceInput<'_>,
) -> Result<RuntimeArtifactPaths, ToolError> {
    let paths = runtime_artifact_paths(
        input.workspace_root,
        input.project_id,
        input.chat_session_id,
    );
    ensure_parent(&paths.state_path)?;
    ensure_parent(&paths.transcript_path)?;
    ensure_parent(&paths.audit_path)?;
    ensure_parent(&paths.checkpoint_path)?;
    ensure_parent(&paths.active_session_path)?;
    ensure_parent(&paths.session_history_path)?;
    ensure_parent(&paths.outbox_path)?;

    let now = epoch_millis();
    let pending_permissions = input
        .tool_results
        .iter()
        .filter(|result| result.error_code == "permission.required")
        .filter_map(|result| result.content.get("permissionRequest").cloned())
        .collect::<Vec<_>>();
    let pending_tool_calls = input
        .tool_results
        .iter()
        .filter(|result| !result.ok)
        .map(|result| result.tool_call_id.clone())
        .collect::<Vec<_>>();
    let transcript_events = build_transcript_events(&input, now);
    let state = json!({
        "record_type": "liuagent-runtime-session-state",
        "version": 1,
        "project_id": input.project_id,
        "chat_session_id": input.chat_session_id,
        "session_id": input.session_id,
        "run_state": {
            "status": input.run_status,
            "waiting_for": input.waiting_for.unwrap_or(""),
            "pending_request_id": pending_permissions
                .first()
                .and_then(|value| value.get("requestId"))
                .and_then(Value::as_str)
                .unwrap_or(""),
            "pending_tool_call_ids": pending_tool_calls,
            "pending_permissions": pending_permissions,
            "pending_adapter_actions": [],
            "updated_at_epoch_ms": now
        },
        "model_runtime": input.model_runtime,
        "operations": input.operations,
        "tool_results": input.tool_results,
        "artifact_paths": {
            "state_path": paths.state_path.to_string_lossy(),
            "transcript_path": paths.transcript_path.to_string_lossy(),
            "audit_path": paths.audit_path.to_string_lossy(),
            "checkpoint_path": paths.checkpoint_path.to_string_lossy()
        },
        "updated_at_epoch_ms": now
    });
    write_json(&paths.state_path, &state)?;
    write_json(
        &paths.checkpoint_path,
        &json!({
            "record_type": "liuagent-runtime-checkpoint",
            "version": 1,
            "project_id": input.project_id,
            "chat_session_id": input.chat_session_id,
            "session_id": input.session_id,
            "state_path": paths.state_path.to_string_lossy(),
            "latest_status": input.run_status,
            "state": state,
            "created_at_epoch_ms": now
        }),
    )?;
    append_jsonl(&paths.transcript_path, &transcript_events)?;
    append_jsonl(&paths.audit_path, input.audit_logs)?;
    write_json(
        &paths.active_session_path,
        &json!({
            "record_type": "query-mcp-active-session",
            "version": 1,
            "project_id": input.project_id,
            "chat_session_id": input.chat_session_id,
            "session_id": input.session_id,
            "runtime_state_path": paths.state_path.to_string_lossy(),
            "latest_status": input.run_status,
            "updated_at_epoch_ms": now
        }),
    )?;
    write_json(
        &paths.session_history_path,
        &json!({
            "record_type": "query-mcp-session-history",
            "version": 1,
            "project_id": input.project_id,
            "chat_session_id": input.chat_session_id,
            "session_id": input.session_id,
            "runtime_state_path": paths.state_path.to_string_lossy(),
            "latest_status": input.run_status,
            "updated_at_epoch_ms": now
        }),
    )?;
    append_jsonl(
        &paths.outbox_path,
        &[json!({
            "event_id": format!("lqe-{}-{}", sanitize_path_segment(input.chat_session_id), now),
            "project_id": input.project_id,
            "chat_session_id": input.chat_session_id,
            "session_id": input.session_id,
            "root_goal": input.user_message,
            "source_kind": "desktop_local_agent",
            "memory_type": "work-facts",
            "content": format!("liuAgent local runtime status={}；assistant={}；tools={}", input.run_status, truncate_text(input.assistant_content, 600), input.tool_results.len()),
            "importance": 0.6,
            "purpose_tags": ["query-mcp", "local-outbox", "desktop-local-agent"],
            "trajectory": {
                "kind": "work-facts",
                "session_id": input.session_id,
                "phase": "local_chat",
                "step": if input.waiting_for == Some("approval") { "waiting_tool_permission" } else { "model_tool_loop" },
                "status": input.run_status,
                "goal": input.user_message,
                "facts": [
                    format!("runtime_state_path={}", paths.state_path.to_string_lossy()),
                    format!("tool_result_count={}", input.tool_results.len())
                ],
                "verification": [
                    format!("runtime_status={}", input.run_status)
                ],
                "risks": if input.waiting_for == Some("approval") {
                    vec!["waiting_for_permission"]
                } else {
                    Vec::<&str>::new()
                }
            },
            "created_at": now.to_string(),
            "updated_at": now.to_string()
        })],
    )?;

    Ok(RuntimeArtifactPaths {
        state_path: paths.state_path.to_string_lossy().to_string(),
        transcript_path: paths.transcript_path.to_string_lossy().to_string(),
        audit_path: paths.audit_path.to_string_lossy().to_string(),
        checkpoint_path: paths.checkpoint_path.to_string_lossy().to_string(),
        active_session_path: paths.active_session_path.to_string_lossy().to_string(),
        session_history_path: paths.session_history_path.to_string_lossy().to_string(),
        outbox_path: paths.outbox_path.to_string_lossy().to_string(),
        runtime_events: transcript_events,
    })
}

pub fn append_runtime_event(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    event: &Value,
) -> Result<(), ToolError> {
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.transcript_path)?;
    append_jsonl(&paths.transcript_path, &[event.clone()])
}

pub fn recover_runtime_state(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> Result<Value, ToolError> {
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    let raw = fs::read_to_string(&paths.state_path).map_err(|err| {
        ToolError::new(
            "state.not_found",
            format!("read runtime state failed: {err}"),
        )
    })?;
    serde_json::from_str::<Value>(&raw).map_err(|err| {
        ToolError::new(
            "state.invalid",
            format!("parse runtime state failed: {err}"),
        )
    })
}

pub fn recover_runtime_session(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> Result<(Value, Vec<Value>), ToolError> {
    let state = recover_runtime_state(workspace_root, project_id, chat_session_id)?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    let runtime_session_id = state
        .get("session_id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let runtime_events = filter_runtime_events_by_session(
        read_jsonl(&paths.transcript_path)?,
        runtime_session_id.as_str(),
    );
    Ok((state, runtime_events))
}

pub fn list_runtime_events(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    after_event_id: Option<&str>,
    limit: usize,
) -> Result<Vec<Value>, ToolError> {
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    let events = read_jsonl(&paths.transcript_path)?;
    let mut started = after_event_id
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .is_none();
    let mut selected = Vec::new();
    let limit = limit.clamp(1, 1000);
    for event in events {
        if !started {
            let event_id = event
                .get("event_id")
                .or_else(|| event.get("eventId"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if Some(event_id) == after_event_id {
                started = true;
            }
            continue;
        }
        selected.push(event);
        if selected.len() >= limit {
            break;
        }
    }
    Ok(selected)
}

pub fn list_runtime_outbox(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: Option<&str>,
    limit: usize,
) -> Result<Vec<Value>, ToolError> {
    let safe_project_id = sanitize_path_segment(project_id);
    let outbox_dir = workspace_root
        .join(".ai-employee")
        .join("query-mcp")
        .join("outbox");
    let mut entries = Vec::new();
    let paths = if let Some(chat_session_id) = chat_session_id
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        vec![outbox_dir.join(format!(
            "{}__{}.jsonl",
            safe_project_id,
            sanitize_path_segment(chat_session_id)
        ))]
    } else {
        fs::read_dir(&outbox_dir)
            .map(|items| {
                items
                    .filter_map(Result::ok)
                    .map(|entry| entry.path())
                    .filter(|path| {
                        path.file_name()
                            .and_then(|name| name.to_str())
                            .map(|name| {
                                name.starts_with(&format!("{safe_project_id}__"))
                                    && name.ends_with(".jsonl")
                            })
                            .unwrap_or(false)
                    })
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default()
    };
    for path in paths {
        if !path.exists() {
            continue;
        }
        entries.extend(read_jsonl(&path)?);
    }
    entries.sort_by(|left, right| {
        let left_key = left
            .get("created_at")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let right_key = right
            .get("created_at")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        left_key.cmp(&right_key)
    });
    entries.truncate(limit.clamp(1, 1000));
    Ok(entries)
}

pub fn delete_runtime_outbox_entries(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    event_ids: &[String],
) -> Result<usize, ToolError> {
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    if !paths.outbox_path.exists() {
        return Ok(0);
    }
    let target_ids = event_ids
        .iter()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .collect::<std::collections::HashSet<_>>();
    if target_ids.is_empty() {
        let count = read_jsonl(&paths.outbox_path)?.len();
        write_jsonl(&paths.outbox_path, &[])?;
        return Ok(count);
    }
    let existing = read_jsonl(&paths.outbox_path)?;
    let mut kept = Vec::new();
    let mut deleted = 0usize;
    for entry in existing {
        let event_id = entry
            .get("event_id")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        if target_ids.contains(&event_id) {
            deleted += 1;
        } else {
            kept.push(entry);
        }
    }
    write_jsonl(&paths.outbox_path, &kept)?;
    Ok(deleted)
}

struct RuntimeArtifactPathBufs {
    state_path: PathBuf,
    transcript_path: PathBuf,
    audit_path: PathBuf,
    checkpoint_path: PathBuf,
    active_session_path: PathBuf,
    session_history_path: PathBuf,
    outbox_path: PathBuf,
}

fn runtime_artifact_paths(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> RuntimeArtifactPathBufs {
    let safe_project_id = sanitize_path_segment(project_id);
    let safe_chat_session_id = sanitize_path_segment(chat_session_id);
    let session_dir = workspace_root
        .join(".ai-employee")
        .join("agent-runtime-v2")
        .join("sessions")
        .join(&safe_chat_session_id);
    RuntimeArtifactPathBufs {
        state_path: session_dir.join("state.json"),
        transcript_path: session_dir.join("transcript.jsonl"),
        audit_path: session_dir.join("audit.jsonl"),
        checkpoint_path: session_dir.join("checkpoint.json"),
        active_session_path: workspace_root
            .join(".ai-employee")
            .join("query-mcp")
            .join("active-sessions")
            .join(format!("{safe_chat_session_id}.json")),
        session_history_path: workspace_root
            .join(".ai-employee")
            .join("query-mcp")
            .join("session-history")
            .join(format!("{safe_project_id}__{safe_chat_session_id}.json")),
        outbox_path: workspace_root
            .join(".ai-employee")
            .join("query-mcp")
            .join("outbox")
            .join(format!("{safe_project_id}__{safe_chat_session_id}.jsonl")),
    }
}

fn build_transcript_events(input: &RuntimePersistenceInput<'_>, now: u128) -> Vec<Value> {
    let pending_request_id = input
        .tool_results
        .iter()
        .find(|result| result.error_code == "permission.required")
        .and_then(|result| result.content.get("permissionRequest"))
        .and_then(|request| request.get("requestId"))
        .and_then(Value::as_str);
    let pending_tool_call_ids = input
        .tool_results
        .iter()
        .filter(|result| !result.ok)
        .map(|result| result.tool_call_id.clone())
        .collect::<Vec<_>>();
    let mut events = vec![
        message_event(
            format!("evt_{}_user", input.session_id),
            input.session_id,
            input.chat_session_id,
            "user",
            input.user_message_id,
            input.user_message,
            now,
        ),
        message_event(
            format!("evt_{}_assistant", input.session_id),
            input.session_id,
            input.chat_session_id,
            "assistant",
            input.assistant_message_id,
            input.assistant_content,
            now,
        ),
    ];
    for result in input
        .tool_results
        .iter()
        .filter(|result| result.error_code == "permission.required")
    {
        if let Some(permission_request) = result.content.get("permissionRequest") {
            events.push(approval_required_event(
                format!(
                    "evt_{}_approval_{}",
                    input.session_id,
                    sanitize_path_segment(&result.tool_call_id)
                ),
                input.session_id,
                input.chat_session_id,
                permission_request.clone(),
                now,
            ));
        }
    }
    events.push(state_changed_event(
        format!("evt_{}_state", input.session_id),
        input.session_id,
        input.chat_session_id,
        "running",
        input.run_status,
        input.waiting_for,
        pending_request_id,
        &pending_tool_call_ids,
        now,
    ));
    for result in input.tool_results {
        events.push(tool_result_event(
            format!(
                "evt_{}_{}",
                input.session_id,
                sanitize_path_segment(&result.tool_result_id)
            ),
            input.session_id,
            input.chat_session_id,
            result,
            now,
        ));
    }
    events
}

fn filter_runtime_events_by_session(events: Vec<Value>, runtime_session_id: &str) -> Vec<Value> {
    let normalized_session_id = runtime_session_id.trim();
    if normalized_session_id.is_empty() {
        return events;
    }
    events
        .into_iter()
        .filter(|event| runtime_event_session_id(event) == normalized_session_id)
        .collect()
}

fn runtime_event_session_id(event: &Value) -> &str {
    event
        .get("runtime_session_id")
        .or_else(|| event.get("runtimeSessionId"))
        .or_else(|| event.get("session_id"))
        .or_else(|| event.get("sessionId"))
        .or_else(|| event.get("run_id"))
        .or_else(|| event.get("runId"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
}

fn ensure_parent(path: &Path) -> Result<(), ToolError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            ToolError::new(
                "state.write_failed",
                format!("create runtime state directory failed: {err}"),
            )
        })?;
    }
    Ok(())
}

fn write_json(path: &Path, value: &Value) -> Result<(), ToolError> {
    let raw = serde_json::to_string_pretty(value).map_err(|err| {
        ToolError::new(
            "state.write_failed",
            format!("serialize state failed: {err}"),
        )
    })?;
    fs::write(path, raw)
        .map_err(|err| ToolError::new("state.write_failed", format!("write state failed: {err}")))
}

fn append_jsonl(path: &Path, values: &[Value]) -> Result<(), ToolError> {
    if values.is_empty() {
        return Ok(());
    }
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|err| ToolError::new("state.write_failed", format!("open jsonl failed: {err}")))?;
    for value in values {
        let line = serde_json::to_string(value).map_err(|err| {
            ToolError::new(
                "state.write_failed",
                format!("serialize jsonl failed: {err}"),
            )
        })?;
        writeln!(file, "{line}").map_err(|err| {
            ToolError::new("state.write_failed", format!("append jsonl failed: {err}"))
        })?;
    }
    Ok(())
}

fn write_jsonl(path: &Path, values: &[Value]) -> Result<(), ToolError> {
    let mut file = fs::OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(path)
        .map_err(|err| ToolError::new("state.write_failed", format!("open jsonl failed: {err}")))?;
    for value in values {
        let line = serde_json::to_string(value).map_err(|err| {
            ToolError::new(
                "state.write_failed",
                format!("serialize jsonl failed: {err}"),
            )
        })?;
        writeln!(file, "{line}").map_err(|err| {
            ToolError::new("state.write_failed", format!("write jsonl failed: {err}"))
        })?;
    }
    Ok(())
}

fn truncate_text(value: &str, max_chars: usize) -> String {
    value.chars().take(max_chars).collect()
}

fn read_jsonl(path: &Path) -> Result<Vec<Value>, ToolError> {
    let raw = fs::read_to_string(path).map_err(|err| {
        ToolError::new("state.not_found", format!("read transcript failed: {err}"))
    })?;
    let mut values = Vec::new();
    for (index, line) in raw.lines().enumerate() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let value = serde_json::from_str::<Value>(trimmed).map_err(|err| {
            ToolError::new(
                "state.invalid",
                format!("parse transcript line {} failed: {err}", index + 1),
            )
        })?;
        values.push(value);
    }
    Ok(values)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::liuagent_core::types::ToolExecutionResult;

    #[test]
    fn writes_recoverable_waiting_approval_state() {
        let dir = std::env::temp_dir().join(format!("liuagent_state_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let tool_result = ToolExecutionResult {
            tool_result_id: "result_call_write".to_string(),
            tool_call_id: "call_write".to_string(),
            name: "write_file".to_string(),
            ok: false,
            content: json!({
                "permissionRequest": {
                    "requestId": "perm_call_write_file_write",
                    "action": "file.write",
                    "risk": "medium",
                    "scope": "workspace",
                    "reason": "test",
                    "preview": {}
                }
            }),
            summary: "permission required".to_string(),
            error_code: "permission.required".to_string(),
            error: "permission required".to_string(),
        };

        let paths = write_runtime_artifacts(RuntimePersistenceInput {
            workspace_root: &dir,
            project_id: "proj-test",
            chat_session_id: "chat-state",
            session_id: "session-state",
            user_message_id: "user-1",
            assistant_message_id: "assistant-1",
            user_message: "write file",
            assistant_content: "waiting approval",
            run_status: "waiting_approval",
            waiting_for: Some("approval"),
            model_runtime: json!({"status": "completed"}),
            tool_results: &[tool_result],
            operations: json!([]),
            audit_logs: &[json!({"audit_id": "audit-test"})],
        })
        .unwrap();

        assert!(PathBuf::from(&paths.state_path).exists());
        assert!(PathBuf::from(&paths.transcript_path).exists());
        assert!(PathBuf::from(&paths.audit_path).exists());
        assert!(PathBuf::from(&paths.outbox_path).exists());
        let recovered = recover_runtime_state(&dir, "proj-test", "chat-state").unwrap();
        assert_eq!(recovered["run_state"]["status"], "waiting_approval");
        assert_eq!(
            recovered["run_state"]["pending_request_id"],
            "perm_call_write_file_write"
        );
        let transcript = fs::read_to_string(&paths.transcript_path).unwrap();
        assert!(transcript.contains("\"type\":\"approval_required\""));
        assert!(transcript.contains("\"type\":\"state_changed\""));
        let (_state, events) = recover_runtime_session(&dir, "proj-test", "chat-state").unwrap();
        assert!(events
            .iter()
            .any(|event| event["type"] == "approval_required"));
        let listed_events = list_runtime_events(
            &dir,
            "proj-test",
            "chat-state",
            Some("evt_session-state_user"),
            10,
        )
        .unwrap();
        assert!(listed_events
            .iter()
            .all(|event| event["event_id"] != "evt_session-state_user"));
        let outbox = list_runtime_outbox(&dir, "proj-test", Some("chat-state"), 10).unwrap();
        assert_eq!(outbox.len(), 1);
        assert_eq!(outbox[0]["source_kind"], "desktop_local_agent");
        let deleted = delete_runtime_outbox_entries(
            &dir,
            "proj-test",
            "chat-state",
            &[outbox[0]["event_id"].as_str().unwrap().to_string()],
        )
        .unwrap();
        assert_eq!(deleted, 1);
        assert!(
            list_runtime_outbox(&dir, "proj-test", Some("chat-state"), 10)
                .unwrap()
                .is_empty()
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn recovery_filters_transcript_events_to_current_runtime_session() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_state_session_filter_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let old_tool_result = ToolExecutionResult::ok(
            "old-result".to_string(),
            "read_file".to_string(),
            json!({"path": "old.md"}),
            "read old".to_string(),
        );
        let new_tool_result = ToolExecutionResult::ok(
            "new-result".to_string(),
            "read_file".to_string(),
            json!({"path": "new.md"}),
            "read new".to_string(),
        );

        write_runtime_artifacts(RuntimePersistenceInput {
            workspace_root: &dir,
            project_id: "proj-test",
            chat_session_id: "chat-mixed",
            session_id: "session-old",
            user_message_id: "user-old",
            assistant_message_id: "assistant-old",
            user_message: "old question",
            assistant_content: "old answer",
            run_status: "failed",
            waiting_for: None,
            model_runtime: json!({"status": "failed"}),
            tool_results: &[old_tool_result],
            operations: json!([]),
            audit_logs: &[],
        })
        .unwrap();
        write_runtime_artifacts(RuntimePersistenceInput {
            workspace_root: &dir,
            project_id: "proj-test",
            chat_session_id: "chat-mixed",
            session_id: "session-new",
            user_message_id: "user-new",
            assistant_message_id: "assistant-new",
            user_message: "new question",
            assistant_content: "new answer",
            run_status: "failed",
            waiting_for: None,
            model_runtime: json!({"status": "failed"}),
            tool_results: &[new_tool_result],
            operations: json!([]),
            audit_logs: &[],
        })
        .unwrap();

        let (_state, events) = recover_runtime_session(&dir, "proj-test", "chat-mixed").unwrap();
        assert!(!events.is_empty());
        assert!(events
            .iter()
            .all(|event| runtime_event_session_id(event) == "session-new"));
        assert!(events.iter().any(|event| {
            event["type"] == "message" && event["payload"]["message_id"] == "assistant-new"
        }));
        assert!(!events.iter().any(|event| {
            event["type"] == "message" && event["payload"]["message_id"] == "assistant-old"
        }));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn writes_recoverable_failed_state() {
        let dir = std::env::temp_dir().join(format!("liuagent_state_failed_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let tool_result = ToolExecutionResult {
            tool_result_id: "result_call_missing".to_string(),
            tool_call_id: "call_missing".to_string(),
            name: "read_file".to_string(),
            ok: false,
            content: json!({}),
            summary: "read failed".to_string(),
            error_code: "tool.execution_failed".to_string(),
            error: "read failed: missing.txt".to_string(),
        };

        let paths = write_runtime_artifacts(RuntimePersistenceInput {
            workspace_root: &dir,
            project_id: "proj-test",
            chat_session_id: "chat-state-failed",
            session_id: "session-state-failed",
            user_message_id: "user-1",
            assistant_message_id: "assistant-1",
            user_message: "read missing file",
            assistant_content: "tool failed",
            run_status: "failed",
            waiting_for: None,
            model_runtime: json!({"status": "completed"}),
            tool_results: &[tool_result],
            operations: json!([]),
            audit_logs: &[json!({"audit_id": "audit-failed"})],
        })
        .unwrap();

        let recovered = recover_runtime_state(&dir, "proj-test", "chat-state-failed").unwrap();
        assert_eq!(recovered["run_state"]["status"], "failed");
        assert_eq!(recovered["run_state"]["pending_request_id"], "");
        assert_eq!(
            recovered["run_state"]["pending_tool_call_ids"][0],
            "call_missing"
        );
        assert!(PathBuf::from(&paths.checkpoint_path).exists());
        assert!(PathBuf::from(&paths.active_session_path).exists());
        assert!(PathBuf::from(&paths.session_history_path).exists());
        let transcript = fs::read_to_string(&paths.transcript_path).unwrap();
        assert!(transcript.contains("\"type\":\"tool_result\""));
        assert!(transcript.contains("\"tool_result_id\":\"result_call_missing\""));
        let _ = fs::remove_dir_all(dir);
    }
}
