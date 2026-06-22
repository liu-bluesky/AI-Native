//! AgentEvent / AdapterCommand 协议最小构造器。
//!
//! Core 只生成稳定的结构化事件；CLI、Desktop 和 Web Bridge 在 adapter 层决定展示方式。

use serde_json::{json, Value};

use crate::liuagent_core::types::ToolExecutionResult;

pub fn message_event(
    event_id: String,
    runtime_session_id: &str,
    chat_session_id: &str,
    role: &str,
    message_id: &str,
    content: &str,
    created_at_epoch_ms: u128,
) -> Value {
    agent_runtime_event(
        event_id,
        runtime_session_id,
        chat_session_id,
        "message",
        json!({
            "role": role,
            "message_id": message_id,
            "content": content,
            "created_at_epoch_ms": created_at_epoch_ms
        }),
        created_at_epoch_ms,
    )
}

pub fn approval_required_event(
    event_id: String,
    runtime_session_id: &str,
    chat_session_id: &str,
    permission_request: Value,
    created_at_epoch_ms: u128,
) -> Value {
    agent_runtime_event(
        event_id,
        runtime_session_id,
        chat_session_id,
        "approval_required",
        permission_request,
        created_at_epoch_ms,
    )
}

pub fn state_changed_event(
    event_id: String,
    runtime_session_id: &str,
    chat_session_id: &str,
    from: &str,
    to: &str,
    waiting_for: Option<&str>,
    pending_request_id: Option<&str>,
    pending_tool_call_ids: &[String],
    created_at_epoch_ms: u128,
) -> Value {
    agent_runtime_event(
        event_id,
        runtime_session_id,
        chat_session_id,
        "state_changed",
        json!({
            "from": from,
            "to": to,
            "waiting_for": waiting_for.unwrap_or(""),
            "pending_request_id": pending_request_id.unwrap_or(""),
            "pending_tool_call_ids": pending_tool_call_ids,
            "pending_tool_batch_id": Value::Null,
            "pending_adapter_action_id": Value::Null,
            "created_at_epoch_ms": created_at_epoch_ms
        }),
        created_at_epoch_ms,
    )
}

pub fn tool_result_event(
    event_id: String,
    runtime_session_id: &str,
    chat_session_id: &str,
    result: &ToolExecutionResult,
    created_at_epoch_ms: u128,
) -> Value {
    agent_runtime_event(
        event_id,
        runtime_session_id,
        chat_session_id,
        "tool_result",
        json!({
            "tool_result_id": result.tool_result_id,
            "tool_call_id": result.tool_call_id,
            "tool_name": result.name,
            "ok": result.ok,
            "summary": result.summary,
            "error_code": result.error_code,
            "created_at_epoch_ms": created_at_epoch_ms
        }),
        created_at_epoch_ms,
    )
}

pub fn model_step_event(
    event_id: String,
    runtime_session_id: &str,
    chat_session_id: &str,
    payload: Value,
    created_at_epoch_ms: u128,
) -> Value {
    agent_runtime_event(
        event_id,
        runtime_session_id,
        chat_session_id,
        "model_step",
        payload,
        created_at_epoch_ms,
    )
}

pub fn model_call_started_event(
    event_id: String,
    runtime_session_id: &str,
    chat_session_id: &str,
    payload: Value,
    created_at_epoch_ms: u128,
) -> Value {
    agent_runtime_event(
        event_id,
        runtime_session_id,
        chat_session_id,
        "model_call_started",
        payload,
        created_at_epoch_ms,
    )
}

pub fn tool_call_started_event(
    event_id: String,
    runtime_session_id: &str,
    chat_session_id: &str,
    payload: Value,
    created_at_epoch_ms: u128,
) -> Value {
    agent_runtime_event(
        event_id,
        runtime_session_id,
        chat_session_id,
        "tool_call_started",
        payload,
        created_at_epoch_ms,
    )
}

fn agent_runtime_event(
    event_id: String,
    runtime_session_id: &str,
    chat_session_id: &str,
    event_type: &str,
    payload: Value,
    created_at_epoch_ms: u128,
) -> Value {
    json!({
        "event_id": event_id,
        "runtime_session_id": runtime_session_id,
        "session_id": runtime_session_id,
        "run_id": runtime_session_id,
        "chat_session_id": chat_session_id,
        "type": event_type,
        "payload": payload,
        "created_at_epoch_ms": created_at_epoch_ms
    })
}
