//! 本地状态、transcript、checkpoint 和恢复回放。

use serde::Serialize;
use serde_json::{json, Value};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use super::adapters::protocol::{message_event, state_changed_event};
use super::execution::build_tool_execution_record_value;
use super::gateway::{epoch_millis, sanitize_path_segment};
use super::paths::desktop_runtime_root;
use super::types::{LocalChatMessage, ToolError, ToolExecutionResult};

static RUNTIME_STATE_WRITE_LOCK: OnceLock<Mutex<()>> = OnceLock::new();

fn runtime_state_write_lock() -> &'static Mutex<()> {
    RUNTIME_STATE_WRITE_LOCK.get_or_init(|| Mutex::new(()))
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeArtifactPaths {
    pub state_path: String,
    pub transcript_path: String,
    pub audit_path: String,
    pub checkpoint_path: String,
    pub active_session_path: String,
    pub session_history_path: String,
    pub conversation_path: String,
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
    pub agent_run_context: Value,
    pub observations: Value,
    pub scheduler_state: Value,
    pub verification_report: Value,
    pub task_goal: Value,
    pub clarity_assessment: Value,
    pub plan_state: Value,
    pub retry_decision: Value,
    pub memory_write_plan: Value,
    pub tool_results: &'a [ToolExecutionResult],
    pub operations: Value,
    pub audit_logs: &'a [Value],
}

pub fn write_runtime_artifacts(
    input: RuntimePersistenceInput<'_>,
) -> Result<RuntimeArtifactPaths, ToolError> {
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
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
    ensure_parent(&paths.conversation_path)?;
    ensure_parent(&paths.outbox_path)?;

    let now = epoch_millis();
    let pending_permissions = input
        .tool_results
        .iter()
        .filter(|result| result.error_code == "permission.required")
        .filter_map(|result| result.content.get("permissionRequest").cloned())
        .collect::<Vec<_>>();
    let pending_user_questions = input
        .tool_results
        .iter()
        .filter(|result| result.error_code == "interaction.user_input_required")
        .filter_map(|result| result.content.get("userQuestionRequest").cloned())
        .collect::<Vec<_>>();
    let pending_tool_calls = input
        .tool_results
        .iter()
        .filter(|result| !result.ok)
        .map(|result| result.tool_call_id.clone())
        .collect::<Vec<_>>();
    let scheduler_run_state = input
        .scheduler_state
        .get("runState")
        .or_else(|| input.scheduler_state.get("run_state"))
        .cloned()
        .unwrap_or_else(|| json!({}));
    let pending_request_id = scheduler_run_state
        .get("pendingRequestId")
        .or_else(|| scheduler_run_state.get("pending_request_id"))
        .and_then(Value::as_str)
        .map(str::to_string)
        .unwrap_or_else(|| {
            pending_permissions
                .first()
                .and_then(|value| value.get("requestId"))
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string()
        });
    let pending_tool_batch_id = scheduler_run_state
        .get("pendingToolBatchId")
        .or_else(|| scheduler_run_state.get("pending_tool_batch_id"))
        .and_then(Value::as_str)
        .map(str::to_string)
        .unwrap_or_else(|| {
            pending_tool_calls
                .first()
                .map(|tool_call_id| format!("tool_batch_{}", sanitize_path_segment(tool_call_id)))
                .unwrap_or_default()
        });
    let run_state = if scheduler_run_state
        .as_object()
        .is_some_and(|object| !object.is_empty())
    {
        scheduler_run_state
    } else {
        json!({
            "version": "run-state/v1",
            "status": input.run_status,
            "waiting_for": input.waiting_for.unwrap_or(""),
            "pending_request_id": pending_request_id,
            "pending_tool_call_ids": pending_tool_calls,
            "pending_tool_batch_id": pending_tool_batch_id,
            "pending_adapter_action_id": "",
            "updated_at_epoch_ms": now
        })
    };
    let transcript_events = build_transcript_events(&input, now);
    let mut model_runtime = input.model_runtime.clone();
    if let Some(runtime_object) = model_runtime.as_object_mut() {
        runtime_object.insert("context".to_string(), input.agent_run_context.clone());
    } else {
        model_runtime = json!({
            "raw": model_runtime,
            "context": input.agent_run_context.clone()
        });
    }
    let mut persisted_run_state =
        merge_runtime_run_state(run_state, pending_permissions, pending_user_questions);
    let interruption_reason = input
        .retry_decision
        .get("failure_type")
        .and_then(Value::as_str)
        .unwrap_or("");
    if input.run_status == "paused" {
        if let Some(run_state_object) = persisted_run_state.as_object_mut() {
            run_state_object.insert("paused".to_string(), json!(true));
            run_state_object.insert("checkpoint_ready".to_string(), json!(true));
            run_state_object.insert("recoverable".to_string(), json!(true));
            run_state_object.insert(
                "interruption_reason".to_string(),
                json!(interruption_reason),
            );
        }
    }
    let state = json!({
        "record_type": "liuagent-runtime-session-state",
        "version": 1,
        "project_id": input.project_id,
        "chat_session_id": input.chat_session_id,
        "session_id": input.session_id,
        "run_state": persisted_run_state,
        "model_runtime": model_runtime,
        "current_state": {
            "status": input.run_status,
            "waiting_for": input.waiting_for.unwrap_or(""),
            "scheduler_state": input.scheduler_state.clone(),
            "observations": input.observations.clone(),
            "task_goal": input.task_goal.clone(),
            "verification_report": input.verification_report.clone(),
            "clarity_assessment": input.clarity_assessment.clone(),
            "plan_state": input.plan_state.clone(),
            "retry_decision": input.retry_decision.clone(),
            "memory_write_plan": input.memory_write_plan.clone(),
            "updated_at_epoch_ms": now
        },
        "operations": input.operations,
        "tool_results": input.tool_results,
        "execution_records": input
            .tool_results
            .iter()
            .map(build_tool_execution_record_value)
            .collect::<Vec<_>>(),
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
            "checkpoint_ready": input.run_status == "paused",
            "recoverable": input.run_status == "paused",
            "interruption_reason": interruption_reason,
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
            "checkpoint_ready": input.run_status == "paused",
            "recoverable": input.run_status == "paused",
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
            "checkpoint_ready": input.run_status == "paused",
            "recoverable": input.run_status == "paused",
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
                "step": if input.waiting_for == Some("approval") {
                    "waiting_tool_permission"
                } else if input.waiting_for == Some("user_question") {
                    "waiting_user_question"
                } else {
                    "model_tool_loop"
                },
                "status": input.run_status,
                "goal": input.user_message,
                "facts": [
                    format!("runtime_state_path={}", paths.state_path.to_string_lossy()),
                    format!("tool_result_count={}", input.tool_results.len()),
                    format!("memory_write_plan={}", compact_json_string(&input.memory_write_plan))
                ],
                "verification": [
                    format!("runtime_status={}", input.run_status)
                ],
                "risks": if input.waiting_for == Some("approval") {
                    vec!["waiting_for_permission"]
                } else if input.waiting_for == Some("user_question") {
                    vec!["waiting_for_user_input"]
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
        conversation_path: paths.conversation_path.to_string_lossy().to_string(),
        outbox_path: paths.outbox_path.to_string_lossy().to_string(),
        runtime_events: transcript_events,
    })
}

fn merge_runtime_run_state(
    mut run_state: Value,
    pending_permissions: Vec<Value>,
    pending_user_questions: Vec<Value>,
) -> Value {
    if !run_state
        .as_object()
        .is_some_and(|object| !object.is_empty())
    {
        run_state = json!({});
    }
    if let Some(object) = run_state.as_object_mut() {
        object.insert(
            "pending_permissions".to_string(),
            json!(pending_permissions),
        );
        object.insert(
            "pending_user_questions".to_string(),
            json!(pending_user_questions),
        );
        object
            .entry("pending_adapter_actions".to_string())
            .or_insert_with(|| json!([]));
    }
    run_state
}

pub fn append_runtime_event(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    event: &Value,
) -> Result<(), ToolError> {
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.transcript_path)?;
    append_jsonl(&paths.transcript_path, &[event.clone()])?;
    persist_runtime_event_checkpoint(&paths, project_id, chat_session_id, event, None)
}

pub fn load_or_import_conversation_history(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    legacy_history: &[LocalChatMessage],
) -> Result<Vec<LocalChatMessage>, ToolError> {
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.conversation_path)?;
    let messages = read_conversation_messages(&paths.conversation_path, project_id, chat_session_id)?;
    if !messages.is_empty() || legacy_history.is_empty() {
        return Ok(messages);
    }
    let imported = legacy_history
        .iter()
        .enumerate()
        .filter(|(_, message)| is_conversation_message(message))
        .map(|(index, message)| {
            conversation_event(
                project_id,
                chat_session_id,
                message,
                "legacy_history_import",
                (index + 1) as u64,
            )
        })
        .collect::<Vec<_>>();
    append_jsonl(&paths.conversation_path, &imported)?;
    read_conversation_messages(&paths.conversation_path, project_id, chat_session_id)
}

pub fn append_conversation_message(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    message: &LocalChatMessage,
    source: &str,
) -> Result<(), ToolError> {
    if !is_conversation_message(message) {
        return Ok(());
    }
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.conversation_path)?;
    let existing_events = read_conversation_events(&paths.conversation_path, project_id, chat_session_id)?;
    let existing = existing_events
        .iter()
        .filter(|event| event.get("record_type").and_then(Value::as_str) == Some("liuagent-conversation-message"))
        .filter_map(|event| serde_json::from_value::<LocalChatMessage>(event.clone()).ok())
        .collect::<Vec<_>>();
    let message_id = message.message_id.as_deref().map(str::trim).unwrap_or("");
    if !message_id.is_empty() && existing.iter().any(|entry| {
        entry.message_id.as_deref().map(str::trim) == Some(message_id)
            && entry.role == message.role
    }) {
        return Ok(());
    }
    let seq = next_conversation_seq(&existing_events);
    append_jsonl(
        &paths.conversation_path,
        &[conversation_event(project_id, chat_session_id, message, source, seq)],
    )
}

pub fn load_conversation_events(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> Result<Vec<Value>, ToolError> {
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    read_conversation_events(&paths.conversation_path, project_id, chat_session_id)
}

pub fn append_conversation_runtime_event(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    runtime_event: &Value,
) -> Result<(), ToolError> {
    let runtime_event_type = runtime_event.get("type").and_then(Value::as_str).unwrap_or("");
    let record_type = match runtime_event_type {
        "model_step" => "liuagent-conversation-model-step",
        "turn_started" => "liuagent-conversation-turn-start",
        "turn_ended" => "liuagent-conversation-turn-end",
        "step_started" => "liuagent-conversation-step-start",
        "step_ended" => "liuagent-conversation-step-end",
        "tool_call_started" => "liuagent-conversation-tool-call",
        "tool_result" => "liuagent-conversation-tool-result",
        "state_changed" => "liuagent-conversation-run-state",
        _ => return Ok(()),
    };
    let source_event_id = runtime_event
        .get("event_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| ToolError::new("state.invalid", "runtime event is missing event_id"))?;
    let payload = runtime_event.get("payload").cloned().unwrap_or_else(|| json!({}));
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.conversation_path)?;
    let events = read_conversation_events(&paths.conversation_path, project_id, chat_session_id)?;
    if events.iter().any(|event| {
        event.get("source_runtime_event_id").and_then(Value::as_str) == Some(source_event_id)
    }) {
        return Ok(());
    }
    let now = epoch_millis();
    append_jsonl(&paths.conversation_path, &[json!({
        "record_type": record_type,
        "version": 2,
        "event_id": format!("conversation-runtime-{}", sanitize_path_segment(source_event_id)),
        "source_runtime_event_id": source_event_id,
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "runtime_session_id": runtime_event.get("runtime_session_id").cloned().unwrap_or(Value::Null),
        "seq": next_conversation_seq(&events),
        "payload": payload,
        "created_at_epoch_ms": now
    })])
}

pub fn append_conversation_model_message(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    message_id: &str,
    message: Value,
) -> Result<(), ToolError> {
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.conversation_path)?;
    let events = read_conversation_events(&paths.conversation_path, project_id, chat_session_id)?;
    if events.iter().any(|event| {
        event.get("record_type").and_then(Value::as_str) == Some("liuagent-conversation-model-message")
            && event.get("message_id").and_then(Value::as_str) == Some(message_id)
    }) {
        return Ok(());
    }
    let now = epoch_millis();
    append_jsonl(&paths.conversation_path, &[json!({
        "record_type": "liuagent-conversation-model-message",
        "version": 2,
        "event_id": format!("conversation-model-message-{}-{}", sanitize_path_segment(message_id), now),
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "message_id": message_id,
        "message": message,
        "seq": next_conversation_seq(&events),
        "created_at_epoch_ms": now
    })])
}

pub fn append_conversation_run_state(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    runtime_session_id: &str,
    status: &str,
    reason: &str,
) -> Result<(), ToolError> {
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.conversation_path)?;
    let events = read_conversation_events(&paths.conversation_path, project_id, chat_session_id)?;
    let now = epoch_millis();
    append_jsonl(&paths.conversation_path, &[json!({
        "record_type": "liuagent-conversation-run-state",
        "version": 2,
        "event_id": format!("conversation-run-{}-{}", sanitize_path_segment(runtime_session_id), now),
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "runtime_session_id": runtime_session_id,
        "status": status,
        "reason": reason,
        "seq": next_conversation_seq(&events),
        "created_at_epoch_ms": now
    })])
}

pub fn append_conversation_checkpoint_if_needed(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> Result<(), ToolError> {
    const RETAIN_EVENT_COUNT: usize = 24;
    const MIN_EVENT_COUNT: usize = 48;
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.conversation_path)?;
    let events = read_conversation_events(&paths.conversation_path, project_id, chat_session_id)?;
    if events.len() <= MIN_EVENT_COUNT {
        return Ok(());
    }
    let covered = &events[..events.len().saturating_sub(RETAIN_EVENT_COUNT)];
    let Some(covers_through_seq) = covered.last().and_then(|event| event.get("seq")).and_then(Value::as_u64) else {
        return Ok(());
    };
    if events.iter().any(|event| {
        event.get("record_type").and_then(Value::as_str) == Some("liuagent-conversation-checkpoint")
            && event.get("covers_through_seq").and_then(Value::as_u64) == Some(covers_through_seq)
    }) {
        return Ok(());
    }
    let summary = covered
        .iter()
        .filter_map(|event| {
            if event.get("record_type").and_then(Value::as_str)
                != Some("liuagent-conversation-message") {
                return None;
            }
            let role = event.get("role").and_then(Value::as_str).unwrap_or("message");
            let content = event.get("content").and_then(Value::as_str).unwrap_or("").trim();
            (!content.is_empty()).then(|| format!("{role}: {}", truncate_conversation_text(content, 500)))
        })
        .collect::<Vec<_>>()
        .join("\n");
    if summary.is_empty() {
        return Ok(());
    }
    let now = epoch_millis();
    append_jsonl(&paths.conversation_path, &[json!({
        "record_type": "liuagent-conversation-checkpoint",
        "version": 2,
        "event_id": format!("conversation-checkpoint-{}-{}", sanitize_path_segment(chat_session_id), now),
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "seq": next_conversation_seq(&events),
        "covers_through_seq": covers_through_seq,
        "summary": summary,
        "source": "deterministic_local_compaction",
        "created_at_epoch_ms": now
    })])
}

pub fn append_interrupted_conversation_closers(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> Result<Vec<Value>, ToolError> {
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.conversation_path)?;
    let events = read_conversation_events(&paths.conversation_path, project_id, chat_session_id)?;
    let latest_status = events.iter().rev().find_map(|event| {
        (event.get("record_type").and_then(Value::as_str) == Some("liuagent-conversation-run-state"))
            .then(|| event.get("status").and_then(Value::as_str))
            .flatten()
    });
    if matches!(latest_status, Some("completed" | "failed")) {
        return Ok(Vec::new());
    }
    let completed = events.iter().filter_map(|event| {
        (event.get("record_type").and_then(Value::as_str) == Some("liuagent-conversation-tool-result"))
            .then(|| event.get("payload"))
            .flatten()
            .and_then(|payload| payload.get("tool_call_id").or_else(|| payload.get("toolCallId")))
            .and_then(Value::as_str)
            .map(str::to_string)
    }).collect::<std::collections::HashSet<_>>();
    let pending = events.iter().filter_map(|event| {
        if event.get("record_type").and_then(Value::as_str) != Some("liuagent-conversation-tool-call") {
            return None;
        }
        let payload = event.get("payload")?;
        let tool_call_id = payload.get("tool_call_id")?.as_str()?.trim();
        (!tool_call_id.is_empty() && !completed.contains(tool_call_id)).then(|| (event, payload, tool_call_id.to_string()))
    }).collect::<Vec<_>>();
    if pending.is_empty() {
        return Ok(Vec::new());
    }
    let now = epoch_millis();
    let mut next_seq = next_conversation_seq(&events);
    let closers = pending.into_iter().map(|(call_event, payload, tool_call_id)| {
        let tool_name = payload.get("tool_name").and_then(Value::as_str).unwrap_or("tool");
        let started = call_event.get("source_runtime_event_id").is_some();
        let error_code = if started { "conversation.tool_outcome_unknown" } else { "conversation.tool_not_started" };
        let message = if started {
            "工具调用已记录但应用中断前未持久化结果；结果未知。只能在确认外部状态后重试，禁止盲目重复可能有副作用的操作。"
        } else {
            "工具调用在 Runtime 记录开始前中断；可由新的模型决策重新执行。"
        };
        let closer = json!({
            "record_type": "liuagent-conversation-tool-result",
            "version": 2,
            "event_id": format!("conversation-interrupted-result-{}-{}", sanitize_path_segment(&tool_call_id), next_seq),
            "project_id": project_id,
            "chat_session_id": chat_session_id,
            "seq": next_seq,
            "synthetic": true,
            "source_event_seq": call_event.get("seq").cloned().unwrap_or(Value::Null),
            "payload": {
                "tool_result_id": format!("interrupted_{tool_call_id}"),
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "ok": false,
                "content": {"status": "interrupted", "replay_policy": "verify_or_request_new_model_decision"},
                "summary": message,
                "error_code": error_code,
                "error": message
            },
            "created_at_epoch_ms": now
        });
        next_seq = next_seq.saturating_add(1);
        closer
    }).collect::<Vec<_>>();
    append_jsonl(&paths.conversation_path, &closers)?;
    Ok(closers)
}

pub fn pause_runtime_checkpoint(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    reason: &str,
) -> Result<(), ToolError> {
    let _write_guard = runtime_state_write_lock()
        .lock()
        .map_err(|_| ToolError::new("state.lock_failed", "runtime state lock is poisoned"))?;
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    ensure_parent(&paths.transcript_path)?;
    let latest_event = if paths.transcript_path.exists() {
        read_jsonl(&paths.transcript_path)?
            .into_iter()
            .last()
            .unwrap_or_else(|| json!({}))
    } else {
        json!({})
    };
    let runtime_session_id = runtime_event_session_id(&latest_event).to_string();
    let current_work_node = current_work_node_from_event(&latest_event);
    let now = epoch_millis();
    let pause_event = json!({
        "event_id": format!("evt_{}_paused_{}", sanitize_path_segment(&runtime_session_id), now),
        "runtime_session_id": runtime_session_id,
        "session_id": runtime_session_id,
        "run_id": runtime_session_id,
        "chat_session_id": chat_session_id,
        "type": "runtime_paused",
        "payload": {
            "status": "paused",
            "reason": reason,
            "checkpoint_ready": true,
            "recoverable": true,
            "current_work_node": current_work_node,
            "created_at_epoch_ms": now
        },
        "created_at_epoch_ms": now
    });
    append_jsonl(&paths.transcript_path, &[pause_event.clone()])?;
    persist_runtime_event_checkpoint(
        &paths,
        project_id,
        chat_session_id,
        &pause_event,
        Some(reason),
    )
}

fn persist_runtime_event_checkpoint(
    paths: &RuntimeArtifactPathBufs,
    project_id: &str,
    chat_session_id: &str,
    event: &Value,
    interruption_reason: Option<&str>,
) -> Result<(), ToolError> {
    ensure_parent(&paths.state_path)?;
    ensure_parent(&paths.checkpoint_path)?;
    ensure_parent(&paths.active_session_path)?;
    ensure_parent(&paths.session_history_path)?;
    let now = epoch_millis();
    let session_id = runtime_event_session_id(event);
    let mut state = read_json_or_default(&paths.state_path, json!({}))?;
    let previous_session_id = state
        .get("session_id")
        .and_then(Value::as_str)
        .unwrap_or("");
    let same_session = !session_id.is_empty() && session_id == previous_session_id;
    let previous_status = state
        .get("run_state")
        .and_then(|value| value.get("status"))
        .and_then(Value::as_str)
        .unwrap_or("");
    let paused = interruption_reason.is_some() || (same_session && previous_status == "paused");
    let status = if paused { "paused" } else { "running" };
    let reason = interruption_reason
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .or_else(|| {
            state
                .get("run_state")
                .and_then(|value| value.get("interruption_reason"))
                .and_then(Value::as_str)
        })
        .unwrap_or("")
        .to_string();
    let current_work_node = event
        .get("payload")
        .and_then(|payload| payload.get("current_work_node"))
        .filter(|value| !value.is_null())
        .cloned()
        .unwrap_or_else(|| current_work_node_from_event(event));
    let event_id = event.get("event_id").and_then(Value::as_str).unwrap_or("");
    let event_type = event.get("type").and_then(Value::as_str).unwrap_or("");
    let state_object = state.as_object_mut().ok_or_else(|| {
        ToolError::new("state.invalid", "runtime state root must be a JSON object")
    })?;
    state_object.insert(
        "record_type".to_string(),
        json!("liuagent-runtime-session-state"),
    );
    state_object.insert("version".to_string(), json!(1));
    state_object.insert("project_id".to_string(), json!(project_id));
    state_object.insert("chat_session_id".to_string(), json!(chat_session_id));
    if !session_id.is_empty() {
        state_object.insert("session_id".to_string(), json!(session_id));
    }
    let mut run_state = state_object
        .get("run_state")
        .cloned()
        .unwrap_or_else(|| json!({}));
    let run_state_object = run_state.as_object_mut().ok_or_else(|| {
        ToolError::new("state.invalid", "runtime run_state must be a JSON object")
    })?;
    run_state_object.insert("version".to_string(), json!("run-state/v1"));
    run_state_object.insert("status".to_string(), json!(status));
    run_state_object.insert("paused".to_string(), json!(paused));
    run_state_object.insert("checkpoint_ready".to_string(), json!(true));
    run_state_object.insert("recoverable".to_string(), json!(true));
    run_state_object.insert("interruption_reason".to_string(), json!(reason));
    run_state_object.insert("latest_event_id".to_string(), json!(event_id));
    run_state_object.insert("latest_event_type".to_string(), json!(event_type));
    run_state_object.insert("current_work_node".to_string(), current_work_node.clone());
    if event_type == "tool_call_started" {
        let tool_call_id = event
            .get("payload")
            .and_then(|payload| payload.get("tool_call_id"))
            .and_then(Value::as_str)
            .unwrap_or("");
        run_state_object.insert(
            "pending_tool_call_ids".to_string(),
            if tool_call_id.is_empty() {
                json!([])
            } else {
                json!([tool_call_id])
            },
        );
    } else if event_type == "tool_result" {
        run_state_object.insert("pending_tool_call_ids".to_string(), json!([]));
    }
    run_state_object.insert("updated_at_epoch_ms".to_string(), json!(now));
    state_object.insert("run_state".to_string(), run_state);
    let mut current_state = state_object
        .get("current_state")
        .cloned()
        .unwrap_or_else(|| json!({}));
    let current_state_object = current_state.as_object_mut().ok_or_else(|| {
        ToolError::new(
            "state.invalid",
            "runtime current_state must be a JSON object",
        )
    })?;
    current_state_object.insert("status".to_string(), json!(status));
    current_state_object.insert("paused".to_string(), json!(paused));
    current_state_object.insert("checkpoint_ready".to_string(), json!(true));
    current_state_object.insert("recoverable".to_string(), json!(true));
    current_state_object.insert("interruption_reason".to_string(), json!(reason));
    current_state_object.insert("current_work_node".to_string(), current_work_node);
    current_state_object.insert("latest_runtime_event".to_string(), event.clone());
    current_state_object.insert("updated_at_epoch_ms".to_string(), json!(now));
    state_object.insert("current_state".to_string(), current_state);
    if event_type == "tool_result" {
        append_unique_runtime_payload(
            state_object,
            "tool_results",
            event.get("payload").cloned().unwrap_or_else(|| json!({})),
            "tool_result_id",
        );
    } else if event_type == "model_step" {
        append_unique_runtime_payload(
            state_object,
            "model_steps",
            event.get("payload").cloned().unwrap_or_else(|| json!({})),
            "index",
        );
    }
    state_object.insert("updated_at_epoch_ms".to_string(), json!(now));
    atomic_write_json(&paths.state_path, &state)?;
    atomic_write_json(
        &paths.checkpoint_path,
        &json!({
            "record_type": "liuagent-runtime-checkpoint",
            "version": 2,
            "project_id": project_id,
            "chat_session_id": chat_session_id,
            "session_id": session_id,
            "state_path": paths.state_path.to_string_lossy(),
            "latest_status": status,
            "checkpoint_ready": true,
            "recoverable": true,
            "interruption_reason": reason,
            "latest_event_id": event_id,
            "latest_event_type": event_type,
            "state": state,
            "created_at_epoch_ms": now
        }),
    )?;
    let session_index = json!({
        "record_type": "query-mcp-active-session",
        "version": 1,
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "session_id": session_id,
        "runtime_state_path": paths.state_path.to_string_lossy(),
        "latest_status": status,
        "checkpoint_ready": true,
        "recoverable": true,
        "updated_at_epoch_ms": now
    });
    atomic_write_json(&paths.active_session_path, &session_index)?;
    atomic_write_json(
        &paths.session_history_path,
        &json!({
            "record_type": "query-mcp-session-history",
            "version": 1,
            "project_id": project_id,
            "chat_session_id": chat_session_id,
            "session_id": session_id,
            "runtime_state_path": paths.state_path.to_string_lossy(),
            "latest_status": status,
            "checkpoint_ready": true,
            "recoverable": true,
            "updated_at_epoch_ms": now
        }),
    )
}

fn current_work_node_from_event(event: &Value) -> Value {
    let payload = event.get("payload").cloned().unwrap_or_else(|| json!({}));
    if let Some(node) = payload
        .get("current_task_node")
        .filter(|value| value.as_object().is_some_and(|object| !object.is_empty()))
    {
        return node.clone();
    }
    json!({
        "kind": event.get("type").and_then(Value::as_str).unwrap_or("runtime"),
        "event_id": event.get("event_id").and_then(Value::as_str).unwrap_or(""),
        "model_step_index": payload.get("index").cloned().unwrap_or(Value::Null),
        "tool_call_id": payload.get("tool_call_id").cloned().unwrap_or(Value::Null),
        "tool_name": payload.get("tool_name").cloned().unwrap_or(Value::Null),
        "status": payload.get("status").cloned().unwrap_or_else(|| json!("running"))
    })
}

fn append_unique_runtime_payload(
    state_object: &mut serde_json::Map<String, Value>,
    field: &str,
    payload: Value,
    identity_field: &str,
) {
    let mut items = state_object
        .get(field)
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let identity = payload.get(identity_field).cloned().unwrap_or(Value::Null);
    let duplicate = !identity.is_null()
        && items
            .iter()
            .any(|item| item.get(identity_field) == Some(&identity));
    if !duplicate {
        items.push(payload);
    }
    state_object.insert(field.to_string(), Value::Array(items));
}

fn compact_json_string(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| value.to_string())
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
    let normalized_after_event_id = after_event_id
        .map(str::trim)
        .filter(|value| !value.is_empty());
    let limit = limit.clamp(1, 1000);
    if normalized_after_event_id.is_none() {
        let start = events.len().saturating_sub(limit);
        return Ok(events.into_iter().skip(start).collect());
    }
    let mut started = false;
    let mut selected = Vec::new();
    for event in events {
        if !started {
            let event_id = event
                .get("event_id")
                .or_else(|| event.get("eventId"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if Some(event_id) == normalized_after_event_id {
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

pub fn save_offline_cache_record(
    workspace_root: &Path,
    cache_kind: &str,
    project_id: Option<&str>,
    chat_session_id: Option<&str>,
    provider_id: Option<&str>,
    payload: Value,
) -> Result<Value, ToolError> {
    let now = epoch_millis();
    match normalize_cache_kind(cache_kind).as_str() {
        "project" => {
            let project_id = required_cache_id(project_id, "projectId")?;
            let path = offline_project_index_path(workspace_root);
            ensure_parent(&path)?;
            let mut index = read_json_or_default(
                &path,
                json!({
                    "record_type": "liuagent-offline-project-index",
                    "version": 1,
                    "projects": []
                }),
            )?;
            let mut projects = index
                .get("projects")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            let mut record = payload;
            record["project_id"] = json!(project_id);
            record["projectId"] = json!(project_id);
            record["updated_at_epoch_ms"] = json!(now);
            projects.retain(|item| {
                item.get("project_id")
                    .or_else(|| item.get("projectId"))
                    .and_then(Value::as_str)
                    .map(|value| value != project_id)
                    .unwrap_or(true)
            });
            projects.insert(0, record.clone());
            index["projects"] = Value::Array(projects);
            index["updated_at_epoch_ms"] = json!(now);
            write_json(&path, &index)?;
            Ok(json!({
                "ok": true,
                "cache_kind": "project",
                "path": path.to_string_lossy(),
                "record": record
            }))
        }
        "session" => {
            let project_id = required_cache_id(project_id, "projectId")?;
            let chat_session_id = required_cache_id(chat_session_id, "chatSessionId")?;
            let path = offline_session_cache_path(workspace_root, project_id, chat_session_id);
            ensure_parent(&path)?;
            let mut record = payload;
            record["record_type"] = json!("liuagent-offline-session-cache");
            record["version"] = json!(1);
            record["project_id"] = json!(project_id);
            record["projectId"] = json!(project_id);
            record["chat_session_id"] = json!(chat_session_id);
            record["chatSessionId"] = json!(chat_session_id);
            record["updated_at_epoch_ms"] = json!(now);
            if record.get("sync_status").is_none() && record.get("syncStatus").is_none() {
                record["sync_status"] = json!("pending");
            }
            write_json(&path, &record)?;
            Ok(json!({
                "ok": true,
                "cache_kind": "session",
                "path": path.to_string_lossy(),
                "record": record
            }))
        }
        "conversation" => {
            let project_id = required_cache_id(project_id, "projectId")?;
            let chat_session_id = required_cache_id(chat_session_id, "chatSessionId")?;
            let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
            let messages = read_conversation_messages(
                &paths.conversation_path,
                project_id,
                chat_session_id,
            )?;
            let projection = messages.into_iter().map(|message| json!({
                "id": message.message_id,
                "role": message.role,
                "content": message.content,
                "images": message.images,
                "videos": message.videos,
                "audios": message.audios,
                "reasoningContent": message.reasoning_content,
                "sourceKind": message.source_kind,
                "diagnostic": message.diagnostic,
                "visibility": message.visibility,
                "mediaAssets": conversation_message_media_assets(&message),
            })).collect::<Vec<_>>();
            Ok(json!({
                "ok": true,
                "cache_kind": "conversation",
                "path": paths.conversation_path.to_string_lossy(),
                "record": { "messages": projection }
            }))
        }
        "runtime_config" => {
            let provider_id = required_cache_id(provider_id, "providerId")?;
            let path = offline_runtime_config_path(workspace_root, provider_id);
            ensure_parent(&path)?;
            let mut record = payload;
            record["record_type"] = json!("liuagent-offline-runtime-config-cache");
            record["version"] = json!(1);
            record["provider_id"] = json!(provider_id);
            record["providerId"] = json!(provider_id);
            record["updated_at_epoch_ms"] = json!(now);
            write_json(&path, &record)?;
            Ok(json!({
                "ok": true,
                "cache_kind": "runtime_config",
                "path": path.to_string_lossy(),
                "record": record
            }))
        }
        other => Err(ToolError::new(
            "cache.kind_invalid",
            format!("unsupported offline cache kind: {other}"),
        )),
    }
}

fn conversation_message_media_assets(message: &LocalChatMessage) -> Vec<Value> {
    let message_id = message.message_id.as_deref().unwrap_or("message");
    [("image", &message.images), ("video", &message.videos), ("audio", &message.audios)]
        .into_iter()
        .flat_map(|(kind, references)| {
            references.iter().enumerate().map(move |(index, reference)| {
                json!({
                    "assetId": format!("conversation-{}-{}-{}", sanitize_path_segment(message_id), kind, index + 1),
                    "kind": kind,
                    "mimeType": if kind == "image" { "image/*" } else if kind == "video" { "video/*" } else { "audio/*" },
                    "reference": reference,
                    "sourceMessageId": message_id,
                    "status": "available"
                })
            })
        })
        .collect()
}

pub fn load_offline_cache_record(
    workspace_root: &Path,
    cache_kind: &str,
    project_id: Option<&str>,
    chat_session_id: Option<&str>,
    provider_id: Option<&str>,
) -> Result<Value, ToolError> {
    match normalize_cache_kind(cache_kind).as_str() {
        "project" => {
            let path = offline_project_index_path(workspace_root);
            let index = read_json_or_default(
                &path,
                json!({
                    "record_type": "liuagent-offline-project-index",
                    "version": 1,
                    "projects": []
                }),
            )?;
            Ok(json!({
                "ok": true,
                "cache_kind": "project",
                "path": path.to_string_lossy(),
                "record": index
            }))
        }
        "session" => {
            let project_id = required_cache_id(project_id, "projectId")?;
            let chat_session_id = required_cache_id(chat_session_id, "chatSessionId")?;
            let path = offline_session_cache_path(workspace_root, project_id, chat_session_id);
            let record = read_json_or_default(&path, json!({}))?;
            Ok(json!({
                "ok": true,
                "cache_kind": "session",
                "path": path.to_string_lossy(),
                "record": record
            }))
        }
        "runtime_config" => {
            let provider_id = required_cache_id(provider_id, "providerId")?;
            let path = offline_runtime_config_path(workspace_root, provider_id);
            let record = read_json_or_default(&path, json!({}))?;
            Ok(json!({
                "ok": true,
                "cache_kind": "runtime_config",
                "path": path.to_string_lossy(),
                "record": record
            }))
        }
        other => Err(ToolError::new(
            "cache.kind_invalid",
            format!("unsupported offline cache kind: {other}"),
        )),
    }
}

pub fn cleanup_synced_offline_cache(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    event_ids: &[String],
    server_refs: Value,
) -> Result<Value, ToolError> {
    let deleted_count =
        delete_runtime_outbox_entries(workspace_root, project_id, chat_session_id, event_ids)?;
    let now = epoch_millis();
    let session_path = offline_session_cache_path(workspace_root, project_id, chat_session_id);
    let mut session_cache = read_json_or_default(&session_path, json!({}))?;
    if session_cache.is_object() {
        session_cache["sync_status"] = json!("synced");
        session_cache["syncStatus"] = json!("synced");
        session_cache["last_synced_at_epoch_ms"] = json!(now);
        session_cache["lastSyncedAtEpochMs"] = json!(now);
        session_cache["pending_outbox_count"] = json!(0);
        session_cache["pendingOutboxCount"] = json!(0);
        session_cache["server_refs"] = server_refs.clone();
        ensure_parent(&session_path)?;
        write_json(&session_path, &session_cache)?;
    }
    let maintenance_path = offline_maintenance_log_path(workspace_root);
    ensure_parent(&maintenance_path)?;
    append_jsonl(
        &maintenance_path,
        &[json!({
            "event_id": format!("cache-cleanup-{}-{}", sanitize_path_segment(chat_session_id), now),
            "event_type": "offline_cache_cleanup",
            "project_id": project_id,
            "chat_session_id": chat_session_id,
            "deleted_outbox_count": deleted_count,
            "server_refs": server_refs,
            "created_at_epoch_ms": now
        })],
    )?;
    Ok(json!({
        "ok": true,
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "deleted_outbox_count": deleted_count,
        "session_cache_path": session_path.to_string_lossy(),
        "maintenance_log_path": maintenance_path.to_string_lossy(),
        "summary": format!("cleaned {deleted_count} synced outbox entries")
    }))
}

struct RuntimeArtifactPathBufs {
    state_path: PathBuf,
    transcript_path: PathBuf,
    audit_path: PathBuf,
    checkpoint_path: PathBuf,
    active_session_path: PathBuf,
    session_history_path: PathBuf,
    conversation_path: PathBuf,
    outbox_path: PathBuf,
}

fn normalize_cache_kind(value: &str) -> String {
    str::trim(value).replace('-', "_").to_ascii_lowercase()
}

fn required_cache_id<'a>(value: Option<&'a str>, field_name: &str) -> Result<&'a str, ToolError> {
    value
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .ok_or_else(|| ToolError::new("cache.schema_invalid", format!("{field_name} is required")))
}

fn offline_project_index_path(workspace_root: &Path) -> PathBuf {
    desktop_runtime_root(workspace_root)
        .join("project-cache")
        .join("index.json")
}

fn offline_session_cache_path(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> PathBuf {
    desktop_runtime_root(workspace_root)
        .join("session-cache")
        .join(format!(
            "{}__{}.json",
            sanitize_path_segment(project_id),
            sanitize_path_segment(chat_session_id)
        ))
}

fn offline_runtime_config_path(workspace_root: &Path, provider_id: &str) -> PathBuf {
    desktop_runtime_root(workspace_root)
        .join("runtime-config")
        .join(format!("{}.json", sanitize_path_segment(provider_id)))
}

fn offline_maintenance_log_path(workspace_root: &Path) -> PathBuf {
    desktop_runtime_root(workspace_root).join("maintenance.jsonl")
}

fn runtime_artifact_paths(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> RuntimeArtifactPathBufs {
    let safe_project_id = sanitize_path_segment(project_id);
    let safe_chat_session_id = sanitize_path_segment(chat_session_id);
    let session_dir = desktop_runtime_root(workspace_root)
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
        conversation_path: session_dir.join("conversation.jsonl"),
        outbox_path: workspace_root
            .join(".ai-employee")
            .join("query-mcp")
            .join("outbox")
            .join(format!("{safe_project_id}__{safe_chat_session_id}.jsonl")),
    }
}

pub fn delete_local_chat_session_artifacts(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> Result<usize, ToolError> {
    let paths = runtime_artifact_paths(workspace_root, project_id, chat_session_id);
    let session_cache = offline_session_cache_path(workspace_root, project_id, chat_session_id);
    let requirement = workspace_root
        .join(".ai-employee")
        .join("requirements")
        .join(sanitize_path_segment(project_id))
        .join(format!("{}.json", sanitize_path_segment(chat_session_id)));
    let mut deleted = 0;
    let session_dir = paths
        .conversation_path
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_default();
    if session_dir.exists() {
        fs::remove_dir_all(&session_dir)
            .map_err(|err| ToolError::new("chat.session_delete_failed", err.to_string()))?;
        deleted += 1;
    }
    for path in [
        paths.active_session_path,
        paths.session_history_path,
        paths.outbox_path,
        session_cache,
        requirement,
    ] {
        match fs::remove_file(path) {
            Ok(()) => deleted += 1,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(ToolError::new(
                    "chat.session_delete_failed",
                    error.to_string(),
                ));
            }
        }
    }
    Ok(deleted)
}

fn is_conversation_message(message: &LocalChatMessage) -> bool {
    matches!(message.role.trim(), "user" | "assistant" | "system")
        && (!message.content.trim().is_empty()
            || !message.images.is_empty()
            || !message.videos.is_empty()
            || !message.audios.is_empty())
}

fn conversation_event(
    project_id: &str,
    chat_session_id: &str,
    message: &LocalChatMessage,
    source: &str,
    seq: u64,
) -> Value {
    let now = epoch_millis();
    let message_id = message
        .message_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| format!("legacy-{seq}-{now}"));
    json!({
        "record_type": "liuagent-conversation-message",
        "version": 2,
        "event_id": format!("conversation-{}-{}-{}", sanitize_path_segment(chat_session_id), sanitize_path_segment(&message_id), now),
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "message_id": message_id,
        "role": message.role.trim(),
        "content": message.content,
        "images": message.images,
        "videos": message.videos,
        "audios": message.audios,
        "reasoning_content": message.reasoning_content,
        "source_kind": message.source_kind,
        "diagnostic": message.diagnostic,
        "visibility": message.visibility,
        "source": source,
        "seq": seq,
        "created_at_epoch_ms": now
    })
}

fn next_conversation_seq(events: &[Value]) -> u64 {
    events
        .iter()
        .filter_map(|event| event.get("seq").and_then(Value::as_u64))
        .max()
        .unwrap_or(events.len() as u64)
        .saturating_add(1)
}

fn truncate_conversation_text(value: &str, max_chars: usize) -> String {
    let mut output = value.chars().take(max_chars).collect::<String>();
    if value.chars().count() > max_chars {
        output.push('…');
    }
    output
}

fn read_conversation_messages(
    path: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> Result<Vec<LocalChatMessage>, ToolError> {
    let messages = read_conversation_events(path, project_id, chat_session_id)?
        .into_iter()
        .filter_map(|event| {
        if event.get("record_type").and_then(Value::as_str)
            != Some("liuagent-conversation-message") {
            return None;
        }
        serde_json::from_value::<LocalChatMessage>(event).ok()
    }).filter(is_conversation_message).collect::<Vec<_>>();
    Ok(messages)
}

fn read_conversation_events(
    path: &Path,
    project_id: &str,
    chat_session_id: &str,
) -> Result<Vec<Value>, ToolError> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let raw_events = read_jsonl(path)?;
    for event in &raw_events {
        if event.get("project_id").and_then(Value::as_str) != Some(project_id)
            || event.get("chat_session_id").and_then(Value::as_str) != Some(chat_session_id)
        {
            continue;
        }
    }
    let mut indexed_events = raw_events
        .into_iter()
        .enumerate()
        .filter(|(_, event)| {
        event.get("project_id").and_then(Value::as_str) == Some(project_id)
            && event.get("chat_session_id").and_then(Value::as_str) == Some(chat_session_id)
            && matches!(
                event.get("record_type").and_then(Value::as_str),
                Some(
                    "liuagent-conversation-message"
                        | "liuagent-conversation-tool-call"
                        | "liuagent-conversation-tool-result"
                        | "liuagent-conversation-model-step"
                        | "liuagent-conversation-model-message"
                        | "liuagent-conversation-turn-start"
                        | "liuagent-conversation-turn-end"
                        | "liuagent-conversation-step-start"
                        | "liuagent-conversation-step-end"
                        | "liuagent-conversation-run-state"
                        | "liuagent-conversation-checkpoint"
                )
            )
        })
        .collect::<Vec<_>>();
    indexed_events.sort_by_key(|(index, event)| {
        event
            .get("seq")
            .and_then(Value::as_u64)
            .unwrap_or((*index as u64).saturating_add(1))
    });
    let mut expected_seq = None::<u64>;
    for (_, event) in &indexed_events {
        if event.get("version").and_then(Value::as_u64).unwrap_or(1) < 2 {
            continue;
        }
        let seq = event.get("seq").and_then(Value::as_u64).ok_or_else(|| {
            ToolError::new("state.conversation_sequence_invalid", "version 2 conversation event is missing seq")
        })?;
        if let Some(expected) = expected_seq {
            if seq != expected {
                return Err(ToolError::new(
                    "state.conversation_sequence_invalid",
                    format!("conversation event seq is not contiguous: expected {expected}, got {seq}"),
                ));
            }
        }
        expected_seq = Some(seq.saturating_add(1));
    }
    Ok(indexed_events
        .into_iter()
        .map(|(_, event)| event)
        .collect())
}

fn build_transcript_events(input: &RuntimePersistenceInput<'_>, now: u128) -> Vec<Value> {
    let pending_request_id = input
        .tool_results
        .iter()
        .find_map(|result| {
            if result.error_code == "permission.required" {
                result.content.get("permissionRequest")
            } else if result.error_code == "interaction.user_input_required" {
                result.content.get("userQuestionRequest")
            } else {
                None
            }
        })
        .and_then(|request| request.get("requestId"))
        .and_then(Value::as_str);
    let pending_tool_call_ids = input
        .tool_results
        .iter()
        .filter(|result| !result.ok)
        .map(|result| result.tool_call_id.clone())
        .collect::<Vec<_>>();
    let pending_tool_batch_id = input
        .scheduler_state
        .get("runState")
        .or_else(|| input.scheduler_state.get("run_state"))
        .and_then(|run_state| {
            run_state
                .get("pendingToolBatchId")
                .or_else(|| run_state.get("pending_tool_batch_id"))
        })
        .and_then(Value::as_str);
    vec![
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
        state_changed_event(
            format!("evt_{}_state", input.session_id),
            input.session_id,
            input.chat_session_id,
            "running",
            input.run_status,
            input.waiting_for,
            pending_request_id,
            &pending_tool_call_ids,
            pending_tool_batch_id,
            now,
        ),
    ]
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

fn atomic_write_json(path: &Path, value: &Value) -> Result<(), ToolError> {
    ensure_parent(path)?;
    let raw = serde_json::to_string_pretty(value).map_err(|err| {
        ToolError::new(
            "state.write_failed",
            format!("serialize state failed: {err}"),
        )
    })?;
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("runtime-state.json");
    let temporary_path = path.with_file_name(format!(
        ".{file_name}.{}.{}.tmp",
        std::process::id(),
        epoch_millis()
    ));
    fs::write(&temporary_path, raw).map_err(|err| {
        ToolError::new(
            "state.write_failed",
            format!("write temporary state failed: {err}"),
        )
    })?;
    fs::rename(&temporary_path, path).map_err(|err| {
        let _ = fs::remove_file(&temporary_path);
        ToolError::new(
            "state.write_failed",
            format!("replace runtime state failed: {err}"),
        )
    })
}

fn read_json_or_default(path: &Path, default_value: Value) -> Result<Value, ToolError> {
    if !path.exists() {
        return Ok(default_value);
    }
    let raw = fs::read_to_string(path).map_err(|err| {
        ToolError::new(
            "state.read_failed",
            format!("read json state failed: {err}"),
        )
    })?;
    if raw.trim().is_empty() {
        return Ok(default_value);
    }
    serde_json::from_str::<Value>(&raw)
        .map_err(|err| ToolError::new("state.invalid", format!("parse json state failed: {err}")))
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
    use crate::liuagent_core::types::{LocalChatMessage, ToolExecutionResult};

    #[test]
    fn conversation_log_rehydrates_assistant_options_without_frontend_history() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_conversation_history_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        let legacy_history = vec![
            LocalChatMessage {
                message_id: Some("user-1".to_string()),
                role: "user".to_string(),
                content: "给我三条处理路径".to_string(),
                images: Vec::new(),
                videos: Vec::new(),
                audios: Vec::new(),
                reasoning_content: None,
                source_kind: None,
                diagnostic: None,
                visibility: None,
            },
            LocalChatMessage {
                message_id: Some("assistant-1".to_string()),
                role: "assistant".to_string(),
                content: "1. 直接编辑\n2. 重新生成\n3. 先确认强度".to_string(),
                images: Vec::new(),
                videos: Vec::new(),
                audios: Vec::new(),
                reasoning_content: None,
                source_kind: None,
                diagnostic: None,
                visibility: None,
            },
        ];

        let imported = load_or_import_conversation_history(
            &dir,
            "proj-test",
            "chat-options",
            &legacy_history,
        )
        .unwrap();
        assert_eq!(imported.len(), 2);

        append_conversation_message(
            &dir,
            "proj-test",
            "chat-options",
            &LocalChatMessage {
                message_id: Some("user-2".to_string()),
                role: "user".to_string(),
                content: "1".to_string(),
                images: Vec::new(),
                videos: Vec::new(),
                audios: Vec::new(),
                reasoning_content: None,
                source_kind: None,
                diagnostic: None,
                visibility: None,
            },
            "runtime_user_message",
        )
        .unwrap();

        let restored = load_or_import_conversation_history(
            &dir,
            "proj-test",
            "chat-options",
            &[],
        )
        .unwrap();
        assert_eq!(restored.len(), 3);
        assert_eq!(restored[1].role, "assistant");
        assert!(restored[1].content.contains("1. 直接编辑"));
        assert_eq!(restored[2].content, "1");
        assert!(runtime_artifact_paths(&dir, "proj-test", "chat-options")
            .conversation_path
            .exists());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn conversation_runtime_events_are_ordered_and_idempotent() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_conversation_runtime_events_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        let tool_call_event = json!({
            "event_id": "evt_runtime_tool_call",
            "runtime_session_id": "runtime-1",
            "chat_session_id": "chat-runtime",
            "type": "tool_call_started",
            "payload": {
                "tool_call_id": "call-readme",
                "tool_name": "read_file",
                "summary": "读取 README",
                "arguments": {"path": "README.md"}
            }
        });
        let tool_result_event = json!({
            "event_id": "evt_runtime_tool_result",
            "runtime_session_id": "runtime-1",
            "chat_session_id": "chat-runtime",
            "type": "tool_result",
            "payload": {
                "toolResultId": "result_call-readme",
                "toolCallId": "call-readme",
                "name": "read_file",
                "ok": true,
                "content": {"content": "项目说明"},
                "summary": "读取完成",
                "errorCode": "",
                "error": ""
            }
        });

        append_conversation_runtime_event(
            &dir,
            "proj-runtime",
            "chat-runtime",
            &tool_call_event,
        )
        .unwrap();
        append_conversation_runtime_event(
            &dir,
            "proj-runtime",
            "chat-runtime",
            &tool_result_event,
        )
        .unwrap();
        append_conversation_runtime_event(
            &dir,
            "proj-runtime",
            "chat-runtime",
            &tool_result_event,
        )
        .unwrap();

        let events = load_conversation_events(&dir, "proj-runtime", "chat-runtime").unwrap();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0]["record_type"], "liuagent-conversation-tool-call");
        assert_eq!(events[0]["seq"], 1);
        assert_eq!(events[1]["record_type"], "liuagent-conversation-tool-result");
        assert_eq!(events[1]["seq"], 2);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn conversation_checkpoint_preserves_messages_and_records_coverage() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_conversation_checkpoint_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        for index in 0..49 {
            append_conversation_message(
                &dir,
                "proj-checkpoint",
                "chat-checkpoint",
                &LocalChatMessage {
                    message_id: Some(format!("message-{index}")),
                    role: if index % 2 == 0 { "user" } else { "assistant" }.to_string(),
                    content: format!("历史消息 {index}"),
                    images: Vec::new(),
                    videos: Vec::new(),
                    audios: Vec::new(),
                    reasoning_content: None,
                    source_kind: None,
                    diagnostic: None,
                    visibility: None,
                },
                "test",
            )
            .unwrap();
        }
        append_conversation_checkpoint_if_needed(&dir, "proj-checkpoint", "chat-checkpoint")
            .unwrap();
        let events = load_conversation_events(&dir, "proj-checkpoint", "chat-checkpoint").unwrap();
        assert_eq!(
            events
                .iter()
                .filter(|event| event["record_type"] == "liuagent-conversation-message")
                .count(),
            49
        );
        let checkpoint = events
            .iter()
            .find(|event| event["record_type"] == "liuagent-conversation-checkpoint")
            .expect("checkpoint should be appended");
        assert!(checkpoint["covers_through_seq"].as_u64().unwrap() > 0);
        assert!(checkpoint["summary"].as_str().unwrap().contains("历史消息"));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn interrupted_tool_calls_receive_one_durable_unknown_outcome_closer() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_conversation_interrupted_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        append_conversation_run_state(
            &dir,
            "proj-interrupted",
            "chat-interrupted",
            "runtime-interrupted",
            "running",
            "model_tool_loop_started",
        )
        .unwrap();
        append_conversation_runtime_event(
            &dir,
            "proj-interrupted",
            "chat-interrupted",
            &json!({
                "event_id": "evt-interrupted-tool",
                "runtime_session_id": "runtime-interrupted",
                "type": "tool_call_started",
                "payload": {
                    "tool_call_id": "call-write",
                    "tool_name": "write_file",
                    "arguments": {"path": "notes.md"}
                }
            }),
        )
        .unwrap();
        let closers = append_interrupted_conversation_closers(
            &dir,
            "proj-interrupted",
            "chat-interrupted",
        )
        .unwrap();
        assert_eq!(closers.len(), 1);
        assert_eq!(closers[0]["payload"]["tool_call_id"], "call-write");
        assert_eq!(
            closers[0]["payload"]["error_code"],
            "conversation.tool_outcome_unknown"
        );
        assert_eq!(
            append_interrupted_conversation_closers(
                &dir,
                "proj-interrupted",
                "chat-interrupted",
            )
            .unwrap()
            .len(),
            0
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn conversation_log_ignores_retired_tool_round_events_without_deleting_them() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_conversation_retired_event_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        let path = runtime_artifact_paths(&dir, "proj-retired", "chat-retired").conversation_path;
        ensure_parent(&path).unwrap();
        append_jsonl(&path, &[json!({
            "record_type": "liuagent-conversation-tool-round",
            "version": 1,
            "project_id": "proj-retired",
            "chat_session_id": "chat-retired"
        })])
        .unwrap();
        let events = load_conversation_events(&dir, "proj-retired", "chat-retired").unwrap();
        assert!(events.is_empty());
        assert!(path.is_file());
        assert!(read_jsonl(&path).unwrap().iter().any(|event| {
            event["record_type"] == "liuagent-conversation-tool-round"
        }));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn runtime_events_roll_checkpoint_and_pause_freezes_latest_node() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_event_checkpoint_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        append_runtime_event(
            &dir,
            "proj-test",
            "chat-event-checkpoint",
            &json!({
                "event_id": "evt_model_started",
                "runtime_session_id": "session-event-checkpoint",
                "chat_session_id": "chat-event-checkpoint",
                "type": "model_call_started",
                "payload": {
                    "index": 2,
                    "status": "running",
                    "current_task_node": {
                        "id": "node-2",
                        "title": "执行第二个节点",
                        "status": "in_progress"
                    }
                },
                "created_at_epoch_ms": epoch_millis()
            }),
        )
        .unwrap();

        let running = recover_runtime_state(&dir, "proj-test", "chat-event-checkpoint").unwrap();
        assert_eq!(running["run_state"]["status"], "running");
        assert_eq!(running["run_state"]["checkpoint_ready"], true);
        assert_eq!(running["run_state"]["current_work_node"]["id"], "node-2");

        pause_runtime_checkpoint(
            &dir,
            "proj-test",
            "chat-event-checkpoint",
            "network_interruption",
        )
        .unwrap();
        let paused = recover_runtime_state(&dir, "proj-test", "chat-event-checkpoint").unwrap();
        assert_eq!(paused["run_state"]["status"], "paused");
        assert_eq!(paused["run_state"]["recoverable"], true);
        assert_eq!(
            paused["run_state"]["interruption_reason"],
            "network_interruption"
        );
        assert_eq!(paused["run_state"]["current_work_node"]["id"], "node-2");
        let _ = fs::remove_dir_all(dir);
    }

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
            agent_run_context: json!({"version": "agent-run-context/test"}),
            observations: json!([]),
            scheduler_state: json!({"version": "runtime-scheduler-state/test"}),
            verification_report: json!({"overall_status": "blocked"}),
            task_goal: json!({"version": "task-goal/test", "goalId": "goal-state"}),
            clarity_assessment: json!({"version": "clarity-assessment/test"}),
            plan_state: json!({"version": "plan-state/test"}),
            retry_decision: json!({"version": "retry-decision/test"}),
            memory_write_plan: json!({"version": "memory-write-plan/test"}),
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
        assert_eq!(
            recovered["run_state"]["pending_permissions"][0]["requestId"],
            "perm_call_write_file_write"
        );
        assert!(recovered["run_state"]
            .get("pending_adapter_actions")
            .and_then(Value::as_array)
            .is_some());
        let transcript = fs::read_to_string(&paths.transcript_path).unwrap();
        assert!(!transcript.contains("\"type\":\"approval_required\""));
        assert!(transcript.contains("\"type\":\"state_changed\""));
        let (_state, events) = recover_runtime_session(&dir, "proj-test", "chat-state").unwrap();
        assert!(events.iter().any(|event| event["type"] == "state_changed"));
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
    fn saves_loads_and_cleans_offline_cache() {
        let dir = std::env::temp_dir().join(format!("liuagent_offline_cache_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();

        let project = save_offline_cache_record(
            &dir,
            "project",
            Some("proj-test"),
            None,
            None,
            json!({"name": "Test Project", "workspace_path": dir.to_string_lossy()}),
        )
        .unwrap();
        assert_eq!(project["ok"], true);
        let project_index = load_offline_cache_record(&dir, "project", None, None, None).unwrap();
        assert_eq!(
            project_index["record"]["projects"][0]["project_id"],
            "proj-test"
        );

        let session = save_offline_cache_record(
            &dir,
            "session",
            Some("proj-test"),
            Some("chat-test"),
            None,
            json!({"status": "in_progress", "messages": [{"role": "user"}]}),
        )
        .unwrap();
        assert_eq!(session["record"]["sync_status"], "pending");
        let loaded_session =
            load_offline_cache_record(&dir, "session", Some("proj-test"), Some("chat-test"), None)
                .unwrap();
        assert_eq!(loaded_session["record"]["status"], "in_progress");

        let paths = runtime_artifact_paths(&dir, "proj-test", "chat-test");
        ensure_parent(&paths.outbox_path).unwrap();
        append_jsonl(
            &paths.outbox_path,
            &[
                json!({"event_id": "evt-1", "created_at": "1"}),
                json!({"event_id": "evt-2", "created_at": "2"}),
            ],
        )
        .unwrap();
        let cleanup = cleanup_synced_offline_cache(
            &dir,
            "proj-test",
            "chat-test",
            &["evt-1".to_string()],
            json!({"server_message_ids": ["msg-1"]}),
        )
        .unwrap();
        assert_eq!(cleanup["deleted_outbox_count"], 1);
        let remaining = list_runtime_outbox(&dir, "proj-test", Some("chat-test"), 10).unwrap();
        assert_eq!(remaining.len(), 1);
        assert_eq!(remaining[0]["event_id"], "evt-2");
        let cleaned_session =
            load_offline_cache_record(&dir, "session", Some("proj-test"), Some("chat-test"), None)
                .unwrap();
        assert_eq!(cleaned_session["record"]["sync_status"], "synced");
        assert_eq!(cleaned_session["record"]["pending_outbox_count"], 0);
        assert!(offline_maintenance_log_path(&dir).exists());

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
            agent_run_context: json!({"version": "agent-run-context/test-old"}),
            observations: json!([]),
            scheduler_state: json!({"version": "runtime-scheduler-state/test-old"}),
            verification_report: json!({"overall_status": "failed"}),
            task_goal: json!({"version": "task-goal/test", "goalId": "goal-old"}),
            clarity_assessment: json!({"version": "clarity-assessment/test-old"}),
            plan_state: json!({"version": "plan-state/test-old"}),
            retry_decision: json!({"version": "retry-decision/test-old"}),
            memory_write_plan: json!({"version": "memory-write-plan/test-old"}),
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
            agent_run_context: json!({"version": "agent-run-context/test-new"}),
            observations: json!([]),
            scheduler_state: json!({"version": "runtime-scheduler-state/test-new"}),
            verification_report: json!({"overall_status": "failed"}),
            task_goal: json!({"version": "task-goal/test", "goalId": "goal-new"}),
            clarity_assessment: json!({"version": "clarity-assessment/test-new"}),
            plan_state: json!({"version": "plan-state/test-new"}),
            retry_decision: json!({"version": "retry-decision/test-new"}),
            memory_write_plan: json!({"version": "memory-write-plan/test-new"}),
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
            agent_run_context: json!({"version": "agent-run-context/test"}),
            observations: json!([]),
            scheduler_state: json!({"version": "runtime-scheduler-state/test"}),
            verification_report: json!({"overall_status": "failed"}),
            task_goal: json!({"version": "task-goal/test", "goalId": "goal-state-failed"}),
            clarity_assessment: json!({"version": "clarity-assessment/test"}),
            plan_state: json!({"version": "plan-state/test"}),
            retry_decision: json!({"version": "retry-decision/test"}),
            memory_write_plan: json!({"version": "memory-write-plan/test"}),
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
        assert_eq!(
            recovered["run_state"]["pending_tool_batch_id"],
            "tool_batch_call_missing"
        );
        assert!(PathBuf::from(&paths.checkpoint_path).exists());
        assert!(PathBuf::from(&paths.active_session_path).exists());
        assert!(PathBuf::from(&paths.session_history_path).exists());
        let transcript = fs::read_to_string(&paths.transcript_path).unwrap();
        assert!(!transcript.contains("\"type\":\"tool_result\""));
        assert_eq!(
            recovered["tool_results"][0]["toolResultId"],
            "result_call_missing"
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn runtime_event_polling_starts_from_tail_and_finalization_keeps_live_events_unique() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_runtime_event_tail_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        for index in 1..=5 {
            append_runtime_event(
                &dir,
                "proj-test",
                "chat-tail",
                &json!({
                    "event_id": format!("evt-tail-{index}"),
                    "runtime_session_id": "session-tail",
                    "chat_session_id": "chat-tail",
                    "type": "progress_update",
                    "payload": {"index": index},
                    "created_at_epoch_ms": epoch_millis()
                }),
            )
            .unwrap();
        }

        let tail = list_runtime_events(&dir, "proj-test", "chat-tail", None, 2).unwrap();
        assert_eq!(tail.len(), 2);
        assert_eq!(tail[0]["event_id"], "evt-tail-4");
        assert_eq!(tail[1]["event_id"], "evt-tail-5");

        let tool_result = ToolExecutionResult::ok(
            "call-live".to_string(),
            "read_file".to_string(),
            json!({"path": "README.md"}),
            "read README.md".to_string(),
        );
        let live_event_id = format!(
            "evt_session-tail_{}",
            sanitize_path_segment(&tool_result.tool_result_id)
        );
        append_runtime_event(
            &dir,
            "proj-test",
            "chat-tail",
            &json!({
                "event_id": live_event_id,
                "runtime_session_id": "session-tail",
                "chat_session_id": "chat-tail",
                "type": "tool_result",
                "payload": {
                    "tool_result_id": tool_result.tool_result_id,
                    "tool_call_id": tool_result.tool_call_id,
                    "tool_name": tool_result.name,
                    "ok": tool_result.ok,
                    "summary": tool_result.summary
                },
                "created_at_epoch_ms": epoch_millis()
            }),
        )
        .unwrap();

        write_runtime_artifacts(RuntimePersistenceInput {
            workspace_root: &dir,
            project_id: "proj-test",
            chat_session_id: "chat-tail",
            session_id: "session-tail",
            user_message_id: "user-tail",
            assistant_message_id: "assistant-tail",
            user_message: "read file",
            assistant_content: "done",
            run_status: "completed",
            waiting_for: None,
            model_runtime: json!({"status": "completed"}),
            agent_run_context: json!({"version": "agent-run-context/test"}),
            observations: json!([]),
            scheduler_state: json!({"version": "runtime-scheduler-state/test"}),
            verification_report: json!({"overall_status": "passed"}),
            task_goal: json!({"version": "task-goal/test", "goalId": "goal-tail"}),
            clarity_assessment: json!({"version": "clarity-assessment/test"}),
            plan_state: json!({"version": "plan-state/test"}),
            retry_decision: json!({"version": "retry-decision/test"}),
            memory_write_plan: json!({"version": "memory-write-plan/test"}),
            tool_results: &[tool_result],
            operations: json!([]),
            audit_logs: &[],
        })
        .unwrap();

        let events =
            read_jsonl(&runtime_artifact_paths(&dir, "proj-test", "chat-tail").transcript_path)
                .unwrap();
        assert_eq!(
            events
                .iter()
                .filter(|event| event["event_id"] == live_event_id)
                .count(),
            1
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn conversation_model_message_events_are_reloaded_for_replay() {
        let dir = std::env::temp_dir().join(format!("liuagent_conversation_model_snapshot_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        append_conversation_model_message(&dir, "proj-snapshot", "chat-snapshot", "message-1", json!({
            "role": "user", "content": "上一轮选项：1、轻度 2、明显"
        })).unwrap();
        let events = load_conversation_events(&dir, "proj-snapshot", "chat-snapshot").unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0]["record_type"], "liuagent-conversation-model-message");
        assert_eq!(events[0]["message"]["content"], "上一轮选项：1、轻度 2、明显");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn canonical_turn_and_step_events_are_durable() {
        let dir = std::env::temp_dir().join(format!("liuagent_conversation_boundaries_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        for (event_id, event_type) in [("turn-start", "turn_started"), ("step-start", "step_started"), ("step-end", "step_ended"), ("turn-end", "turn_ended")] {
            append_conversation_runtime_event(&dir, "proj-boundary", "chat-boundary", &json!({
                "event_id": event_id, "runtime_session_id": "runtime-boundary", "type": event_type, "payload": {}
            })).unwrap();
        }
        let events = load_conversation_events(&dir, "proj-boundary", "chat-boundary").unwrap();
        let record_types = events.iter().filter_map(|event| event["record_type"].as_str()).collect::<Vec<_>>();
        assert_eq!(record_types, vec!["liuagent-conversation-turn-start", "liuagent-conversation-step-start", "liuagent-conversation-step-end", "liuagent-conversation-turn-end"]);
        let _ = fs::remove_dir_all(dir);
    }
}
