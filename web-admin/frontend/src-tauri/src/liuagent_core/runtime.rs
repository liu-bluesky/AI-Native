//! 本地 agent 会话运行时。
//!
//! 这是桌面端 local-first 主线的最小会话入口：Vue 负责展示，Tauri/Rust 在用户本机
//! 记录需求、执行本地工具并返回事件摘要。后续模型循环会在这里继续扩展，而不是回到
//! 服务端 Docker 执行用户本地工具。

use reqwest::blocking::{Client, Response};
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use reqwest::Url;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs;
use std::path::PathBuf;
use std::time::Duration;
use std::time::{SystemTime, UNIX_EPOCH};

use super::adapters::protocol::{
    approval_required_event, model_call_started_event, model_step_event, tool_call_started_event,
    tool_result_event,
};
use super::audit::build_tool_audit_logs;
use super::definitions::builtin_tool_definitions;
use super::permission::{cached_session_grant_comment, permission_request_id};
use super::state::recover_runtime_session;
#[cfg(test)]
use super::state::recover_runtime_state;
use super::state::{
    delete_runtime_outbox_entries, list_runtime_events as read_runtime_events,
    list_runtime_outbox as read_runtime_outbox, write_runtime_artifacts, RuntimePersistenceInput,
};
use super::types::{
    AgentInvocationRequest, AgentInvocationResult, LocalChatMessage, LocalChatRequest,
    LocalChatResult, LocalModelRuntimeConfig, LocalRuntimeEventsRequest, LocalRuntimeEventsResult,
    LocalRuntimeOutboxAckRequest, LocalRuntimeOutboxRequest, LocalRuntimeOutboxResult,
    LocalRuntimeRecoveryRequest, LocalRuntimeRecoveryResult, ToolError, ToolExecutionRequest,
};
use super::planning;
use super::workspace::resolve_workspace_root;
use super::{execute_tool, normalized_tool_call_id, prepare_agent_invocation};

const REQUIREMENT_SCHEMA_VERSION: u32 = 1;
const DEFAULT_MODEL_TIMEOUT_MS: u64 = 45_000;
const DEFAULT_MAX_TOKENS: u32 = 1024;
const DEFAULT_MAX_VERIFICATION_REPROMPTS: usize = 1;
const MODEL_CONNECTION_TIMEOUT_MAX_ATTEMPTS: usize = 5;
const PERMISSION_CACHE_VERSION: u32 = 1;

pub fn start_local_chat(request: LocalChatRequest) -> LocalChatResult {
    let chat_session_id = request.chat_session_id.trim().to_string();
    match start_local_chat_inner(request, None) {
        Ok(result) => result,
        Err(error) => LocalChatResult::failed(chat_session_id, error),
    }
}

pub fn start_local_chat_with_event_sink<F>(
    request: LocalChatRequest,
    event_sink: F,
) -> LocalChatResult
where
    F: Fn(Value),
{
    let chat_session_id = request.chat_session_id.trim().to_string();
    match start_local_chat_inner(request, Some(&event_sink)) {
        Ok(result) => result,
        Err(error) => LocalChatResult::failed(chat_session_id, error),
    }
}

pub fn recover_local_runtime_state(
    request: LocalRuntimeRecoveryRequest,
) -> LocalRuntimeRecoveryResult {
    match recover_local_runtime_state_inner(&request) {
        Ok(result) => result,
        Err(error) => LocalRuntimeRecoveryResult::failed(request, error),
    }
}

pub fn list_local_runtime_events(request: LocalRuntimeEventsRequest) -> LocalRuntimeEventsResult {
    match list_local_runtime_events_inner(&request) {
        Ok(result) => result,
        Err(error) => LocalRuntimeEventsResult::failed(request, error),
    }
}

pub fn list_local_runtime_outbox(request: LocalRuntimeOutboxRequest) -> LocalRuntimeOutboxResult {
    let project_id = request.project_id.clone();
    let chat_session_id = request.chat_session_id.clone().unwrap_or_default();
    let workspace_path = request.workspace_path.clone();
    match list_local_runtime_outbox_inner(&request) {
        Ok(result) => result,
        Err(error) => {
            LocalRuntimeOutboxResult::failed(project_id, chat_session_id, workspace_path, error)
        }
    }
}

pub fn ack_local_runtime_outbox(request: LocalRuntimeOutboxAckRequest) -> LocalRuntimeOutboxResult {
    let project_id = request.project_id.clone();
    let chat_session_id = request.chat_session_id.clone();
    let workspace_path = request.workspace_path.clone();
    match ack_local_runtime_outbox_inner(&request) {
        Ok(result) => result,
        Err(error) => {
            LocalRuntimeOutboxResult::failed(project_id, chat_session_id, workspace_path, error)
        }
    }
}

fn recover_local_runtime_state_inner(
    request: &LocalRuntimeRecoveryRequest,
) -> Result<LocalRuntimeRecoveryResult, ToolError> {
    let project_id = required_non_empty(&request.project_id, "projectId")?;
    let chat_session_id = required_non_empty(&request.chat_session_id, "chatSessionId")?;
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    let (state, runtime_events) =
        recover_runtime_session(&workspace_root, &project_id, &chat_session_id)?;
    let status = state["run_state"]["status"]
        .as_str()
        .unwrap_or("unknown")
        .to_string();
    Ok(LocalRuntimeRecoveryResult {
        ok: true,
        project_id,
        chat_session_id,
        workspace_path: workspace_root.to_string_lossy().to_string(),
        state,
        runtime_events,
        summary: format!("recovered local runtime state: {status}"),
        error_code: String::new(),
        error: String::new(),
    })
}

fn list_local_runtime_events_inner(
    request: &LocalRuntimeEventsRequest,
) -> Result<LocalRuntimeEventsResult, ToolError> {
    let project_id = required_non_empty(&request.project_id, "projectId")?;
    let chat_session_id = required_non_empty(&request.chat_session_id, "chatSessionId")?;
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    let events = read_runtime_events(
        &workspace_root,
        &project_id,
        &chat_session_id,
        request.after_event_id.as_deref(),
        request.limit.unwrap_or(200),
    )?;
    Ok(LocalRuntimeEventsResult {
        ok: true,
        project_id,
        chat_session_id,
        workspace_path: workspace_root.to_string_lossy().to_string(),
        summary: format!("loaded {} local runtime events", events.len()),
        events,
        error_code: String::new(),
        error: String::new(),
    })
}

fn list_local_runtime_outbox_inner(
    request: &LocalRuntimeOutboxRequest,
) -> Result<LocalRuntimeOutboxResult, ToolError> {
    let project_id = required_non_empty(&request.project_id, "projectId")?;
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    let chat_session_id = request
        .chat_session_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .unwrap_or_default();
    let entries = read_runtime_outbox(
        &workspace_root,
        &project_id,
        if chat_session_id.is_empty() {
            None
        } else {
            Some(chat_session_id.as_str())
        },
        request.limit.unwrap_or(200),
    )?;
    Ok(LocalRuntimeOutboxResult {
        ok: true,
        project_id,
        chat_session_id,
        workspace_path: workspace_root.to_string_lossy().to_string(),
        summary: format!("loaded {} local outbox entries", entries.len()),
        entries,
        deleted_count: 0,
        error_code: String::new(),
        error: String::new(),
    })
}

fn ack_local_runtime_outbox_inner(
    request: &LocalRuntimeOutboxAckRequest,
) -> Result<LocalRuntimeOutboxResult, ToolError> {
    let project_id = required_non_empty(&request.project_id, "projectId")?;
    let chat_session_id = required_non_empty(&request.chat_session_id, "chatSessionId")?;
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    let deleted_count = delete_runtime_outbox_entries(
        &workspace_root,
        &project_id,
        &chat_session_id,
        &request.event_ids,
    )?;
    Ok(LocalRuntimeOutboxResult {
        ok: true,
        project_id,
        chat_session_id,
        workspace_path: workspace_root.to_string_lossy().to_string(),
        entries: Vec::new(),
        deleted_count,
        summary: format!("acked {deleted_count} local outbox entries"),
        error_code: String::new(),
        error: String::new(),
    })
}

fn start_local_chat_inner(
    request: LocalChatRequest,
    event_sink: Option<&dyn Fn(Value)>,
) -> Result<LocalChatResult, ToolError> {
    let project_id = required_non_empty(&request.project_id, "projectId")?;
    let chat_session_id = required_non_empty(&request.chat_session_id, "chatSessionId")?;
    let user_message = required_non_empty(&request.message, "message")?;
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    let session_id = format!("local_{}", epoch_millis());

    // 规划门：Implementation 型请求在未确认前先返回任务树，等待用户确认。
    // Query 型请求或已确认（plan_decision.approved=true）的请求直接放行。
    let plan_approved = request
        .plan_decision
        .as_ref()
        .map(|decision| decision.approved)
        .unwrap_or(false);
    if !plan_approved
        && planning::assess_request_type(&user_message) == planning::RequestType::Implementation
    {
        return Ok(build_plan_required_result(
            &session_id,
            &chat_session_id,
            &user_message,
            &workspace_root,
            &project_id,
        ));
    }

    let gateway_result = prepare_local_chat_invocation(&request, &user_message)?;
    let user_message_id = normalized_id(request.message_id.as_deref(), "local_user");
    let assistant_message_id =
        normalized_id(request.assistant_message_id.as_deref(), "local_assistant");
    let model_request = build_model_request(&request, &user_message);
    let agent_loop = run_agent_loop(
        &chat_session_id,
        &session_id,
        &model_request,
        &workspace_root,
        request.permission_decision.clone(),
        event_sink,
    );
    let model_result = agent_loop.final_model_result();
    let planned_tools = agent_loop.planned_tools.clone();
    let tool_results = agent_loop.tool_results.clone();
    let awaiting_permission = agent_loop.awaiting_permission;
    let run_ok = agent_loop.ok();

    let assistant_content = build_assistant_content(
        &project_id,
        &workspace_root,
        &user_message,
        &request.history,
        &model_result,
        &tool_results,
        &planned_tools,
        run_ok,
        awaiting_permission,
        agent_loop.stopped_reason.as_str(),
        agent_loop.summary().as_str(),
        agent_loop.error().as_str(),
    );
    let operations = build_operations(&session_id, &agent_loop);
    let run_status = if awaiting_permission {
        "waiting_approval"
    } else if run_ok {
        "completed"
    } else {
        "failed"
    };
    let waiting_for = if awaiting_permission {
        Some("approval")
    } else {
        None
    };
    let audit_logs = build_tool_audit_logs(
        &session_id,
        &tool_results,
        request.permission_decision.as_ref(),
        epoch_millis(),
    );
    let runtime_artifacts = write_runtime_artifacts(RuntimePersistenceInput {
        workspace_root: &workspace_root,
        project_id: &project_id,
        chat_session_id: &chat_session_id,
        session_id: &session_id,
        user_message_id: &user_message_id,
        assistant_message_id: &assistant_message_id,
        user_message: &user_message,
        assistant_content: &assistant_content,
        run_status,
        waiting_for,
        model_runtime: agent_loop.audit_value(),
        tool_results: &tool_results,
        operations: operations.clone(),
        audit_logs: &audit_logs,
    })?;
    let runtime_events = runtime_artifacts.runtime_events.clone();
    let requirement_path = requirement_record_path(&workspace_root, &project_id, &chat_session_id);
    write_requirement_record(
        &requirement_path,
        json!({
            "record_type": "desktop-local-agent-requirement",
            "version": REQUIREMENT_SCHEMA_VERSION,
            "storage_scope": "desktop-workspace",
            "storage_mode": "local-first",
            "gateway_protocol": "Agent Gateway",
            "project_id": project_id,
            "chat_session_id": chat_session_id,
            "session_id": session_id,
            "workspace_path": workspace_root.to_string_lossy(),
            "title": user_message,
            "root_goal": user_message,
            "latest_status": run_status,
            "phase": "local_chat",
            "step": if awaiting_permission { "waiting_tool_permission" } else if !planned_tools.is_empty() { "model_and_tool_execution" } else { "model_execution" },
            "workflow_skill": {
                "id": "liuagent-cli",
                "source": "docs/liuAgent-cli",
                "runtime": "tauri"
            },
            "agent_gateway": {
                "invocation": gateway_result.invocation.clone(),
                "requirement_session": gateway_result.requirement_session.clone(),
                "project_context_bundle": gateway_result.project_context_bundle.clone(),
                "prompt_bundle": gateway_result.prompt_bundle.clone(),
                "tool_manifest_bundle": gateway_result.tool_manifest_bundle.clone(),
                "agent_runtime_session": gateway_result.agent_runtime_session.clone()
            },
            "runtime_state": runtime_artifacts.clone(),
            "task_lifecycle": {
                "status": run_status,
                "waiting_for": waiting_for,
                "stopped_reason": agent_loop.stopped_reason.as_str(),
                "candidate_solutions": &agent_loop.candidate_solutions,
                "attempts": &agent_loop.attempts,
                "verification": &agent_loop.verification,
            },
            "task_tree": planning::TaskTree::finalize(
                &session_id,
                &user_message,
                agent_loop.stopped_reason.as_str(),
                awaiting_permission,
                run_ok,
            ),
            "blockers": build_runtime_blockers(
                &session_id,
                agent_loop.stopped_reason.as_str(),
                awaiting_permission,
                &planned_tools,
            ),
            "current_task_node": {
                "id": format!("node-execute-{session_id}"),
                "title": "桌面端本地对话与工具执行",
                "status": run_status,
                "stage_key": "local_chat"
            },
            "task_branches": [
                {
                    "id": "local-node-run",
                    "title": "在桌面端本机执行模型选择的本地工具",
                    "status": run_status,
                    "stage_key": "execution"
                }
            ],
            "history": [
                {
                    "event": "user_message",
                    "message_id": user_message_id,
                    "content": user_message,
                    "created_at_epoch_ms": epoch_millis()
                },
                {
                    "event": "model_results",
                    "round_count": agent_loop.model_steps.len(),
                    "final_mode": model_result.mode,
                    "final_provider_id": model_result.provider_id,
                    "final_model_name": model_result.model_name,
                    "final_ok": model_result.ok,
                    "final_status": model_result.status,
                    "final_summary": model_result.summary,
                    "final_error_code": model_result.error_code,
                    "stopped_reason": agent_loop.stopped_reason,
                    "created_at_epoch_ms": epoch_millis()
                },
                {
                    "event": "tool_results",
                    "tool_count": tool_results.len(),
                    "ok": !tool_results.is_empty() && tool_results.iter().all(|item| item.ok),
                    "summaries": tool_results.iter().map(|item| json!({
                        "tool_name": item.name.as_str(),
                        "tool_call_id": item.tool_call_id.as_str(),
                        "ok": item.ok,
                        "summary": item.summary.as_str(),
                        "error_code": item.error_code.as_str()
                    })).collect::<Vec<_>>(),
                    "created_at_epoch_ms": epoch_millis()
                },
                {
                    "event": "assistant_message",
                    "message_id": assistant_message_id,
                    "content": assistant_content,
                    "created_at_epoch_ms": epoch_millis()
                }
            ],
            "model_runtime": agent_loop.audit_value(),
            "tool_results": json!(tool_results),
            "audit_logs": audit_logs,
            "sync_status": "local_only",
            "updated_at_epoch_ms": epoch_millis()
        }),
    )?;

    let result_error_code = if awaiting_permission {
        "permission.required".to_string()
    } else if run_ok {
        String::new()
    } else if !agent_loop.error_code().is_empty() {
        agent_loop.error_code()
    } else if let Some(result) = tool_results.iter().find(|result| !result.ok) {
        result.error_code.clone()
    } else if !model_result.error_code.trim().is_empty() {
        model_result.error_code.clone()
    } else {
        "model.unavailable".to_string()
    };
    let result_error = if run_ok {
        String::new()
    } else if !agent_loop.error().is_empty() {
        agent_loop.error()
    } else if let Some(result) = tool_results.iter().find(|result| !result.ok) {
        result.error.clone()
    } else if !model_result.error.trim().is_empty() {
        model_result.error.clone()
    } else {
        model_result.summary.clone()
    };
    let result_summary = if awaiting_permission {
        "桌面端本地对话等待用户授权".to_string()
    } else if run_ok {
        if tool_results.is_empty() {
            "桌面端本地对话已完成".to_string()
        } else {
            format!(
                "桌面端本地对话已完成，{} 轮模型调用中顺序执行 {} 个模型工具调用",
                agent_loop.model_steps.len(),
                tool_results.len()
            )
        }
    } else if !agent_loop.summary().is_empty() {
        agent_loop.summary()
    } else if let Some(result) = tool_results.iter().find(|result| !result.ok) {
        result.summary.clone()
    } else {
        model_result.summary.clone()
    };

    Ok(LocalChatResult {
        ok: run_ok,
        plan_status: String::new(),
        session_id,
        chat_session_id,
        requirement_record_path: requirement_path.to_string_lossy().to_string(),
        gateway_result: Some(gateway_result),
        assistant_content,
        model_result: agent_loop.audit_value(),
        tool_results,
        operations,
        runtime_events,
        summary: result_summary,
        error_code: result_error_code,
        error: result_error,
    })
}

/// 规划门早返回：生成任务树并等待用户确认，不触发模型调用。
fn build_plan_required_result(
    session_id: &str,
    chat_session_id: &str,
    user_message: &str,
    workspace_root: &PathBuf,
    project_id: &str,
) -> LocalChatResult {
    let task_tree = planning::TaskTree::for_implementation(session_id, user_message);
    let requirement_path = requirement_record_path(workspace_root, project_id, chat_session_id);
    let _ = write_requirement_record(
        &requirement_path,
        json!({
            "record_type": "desktop-local-agent-requirement",
            "version": REQUIREMENT_SCHEMA_VERSION,
            "project_id": project_id,
            "chat_session_id": chat_session_id,
            "session_id": session_id,
            "root_goal": user_message,
            "plan_status": "plan_required",
            "task_tree": task_tree,
            "updated_at_epoch_ms": epoch_millis()
        }),
    );
    LocalChatResult {
        ok: true,
        plan_status: "plan_required".to_string(),
        session_id: session_id.to_string(),
        chat_session_id: chat_session_id.to_string(),
        requirement_record_path: requirement_path.to_string_lossy().to_string(),
        gateway_result: None,
        assistant_content: String::new(),
        model_result: json!({}),
        tool_results: Vec::new(),
        operations: json!([]),
        runtime_events: Vec::new(),
        summary: "需要用户确认执行计划".to_string(),
        error_code: String::new(),
        error: String::new(),
    }
}

fn build_runtime_blockers(
    session_id: &str,
    stopped_reason: &str,
    awaiting_permission: bool,
    planned_tools: &[PlannedLocalTool],
) -> Value {
    if awaiting_permission {
        let tool_name = planned_tools
            .last()
            .map(|t| t.name.as_str())
            .unwrap_or("unknown");
        json!([planning::BlockerRecord::permission_required(
            session_id,
            &format!("node-execute-{session_id}"),
            tool_name,
        )])
    } else if stopped_reason == "verification_failed" {
        json!([planning::BlockerRecord::verification_failed(
            session_id,
            &format!("node-verify-{session_id}"),
        )])
    } else {
        json!([])
    }
}

fn prepare_local_chat_invocation(
    request: &LocalChatRequest,
    user_message: &str,
) -> Result<AgentInvocationResult, ToolError> {
    let result = prepare_agent_invocation(AgentInvocationRequest {
        invocation_id: None,
        source: Some("project_chat".to_string()),
        adapter_kind: Some("desktop".to_string()),
        project_id: request.project_id.clone(),
        chat_session_id: request.chat_session_id.clone(),
        user_message: user_message.to_string(),
        workspace_path: request.workspace_path.clone(),
        agent_id: None,
        prompt_bundle_id: None,
        tool_bundle_id: None,
        capabilities: vec![
            "local_runner".to_string(),
            "mcp_recording".to_string(),
            "desktop_tools".to_string(),
        ],
        record_requirement: Some(true),
    });
    if result.ok {
        Ok(result)
    } else {
        Err(ToolError::new(result.error_code, result.error))
    }
}

fn build_assistant_content(
    project_id: &str,
    workspace_root: &PathBuf,
    user_message: &str,
    history: &[LocalChatMessage],
    model_result: &ModelStepResult,
    tool_results: &[super::types::ToolExecutionResult],
    planned_tools: &[PlannedLocalTool],
    agent_loop_ok: bool,
    awaiting_permission: bool,
    stopped_reason: &str,
    loop_summary: &str,
    loop_error: &str,
) -> String {
    if agent_loop_ok
        && model_result.ok
        && !model_result.compat_text_tool_call_detected
        && !model_result.content.trim().is_empty()
    {
        return model_result.content.trim().to_string();
    }
    let workspace_name = workspace_root
        .file_name()
        .map(|value| value.to_string_lossy().to_string())
        .unwrap_or_else(|| workspace_root.to_string_lossy().to_string());
    let history_count = history
        .iter()
        .filter(|item| {
            ["user", "assistant"].contains(&item.role.trim()) && !item.content.trim().is_empty()
        })
        .count();
    let model_step_failed = !model_result.ok && model_result.status == "failed";
    let loop_failed = !agent_loop_ok && !awaiting_permission;
    let mut lines = if awaiting_permission {
        vec!["本地智能体等待授权，任务尚未完成。".to_string()]
    } else if model_step_failed && model_result.error_code == "model.connection_timeout" {
        if tool_results.is_empty() {
            vec!["模型连接超时，本轮未执行任何本机工具，也未修改文件。".to_string()]
        } else {
            vec!["模型连接超时，已执行的本机工具见下方摘要；本轮尚未完成最终修改。".to_string()]
        }
    } else if model_result.error_code == "model.connection_timeout" {
        if tool_results.is_empty() {
            vec!["模型连接超时，本轮未执行任何本机工具，也未修改文件。".to_string()]
        } else {
            vec!["模型连接超时，已执行的本机工具见下方摘要；本轮尚未完成最终修改。".to_string()]
        }
    } else if model_step_failed {
        if tool_results.is_empty() {
            vec!["模型调用失败，本轮未执行任何本机工具，也未修改文件。".to_string()]
        } else {
            vec!["模型调用失败，已执行的本机工具见下方摘要；本轮尚未完成最终修改。".to_string()]
        }
    } else if loop_failed {
        match stopped_reason {
            "verification_failed" => {
                vec!["本地智能体未完成任务：验证没有通过。".to_string()]
            }
            "repeated_failure" => {
                vec!["本地智能体未完成任务：相同失败重复出现，已暂停自动循环。".to_string()]
            }
            _ => vec!["本地智能体执行失败，用户请求尚未完成。".to_string()],
        }
    } else {
        vec!["已在桌面端本机走通一轮本地智能体对话。".to_string()]
    };
    lines.extend([
        format!("项目：{project_id}"),
        format!("工作区：{workspace_name}"),
        format!("你的输入：{user_message}"),
        format!("本地历史上下文：{} 条", history_count),
    ]);
    lines.push(format!(
        "模型步骤：{}（{} / {}）。",
        model_result.status, model_result.provider_id, model_result.model_name
    ));
    if !model_result.summary.trim().is_empty() {
        lines.push(format!("模型说明：{}", model_result.summary));
    }
    if loop_failed {
        let detail = if !loop_summary.trim().is_empty() {
            loop_summary.trim()
        } else {
            loop_error.trim()
        };
        if !detail.is_empty() {
            lines.push(format!("停止原因：{detail}"));
        }
    }
    if !tool_results.is_empty() {
        if let Some((index, tool_result)) = tool_results
            .iter()
            .enumerate()
            .find(|(_, result)| result.error_code == "permission.required")
        {
            let tool_name = planned_tools
                .get(index)
                .map(|tool| tool.name.as_str())
                .unwrap_or(tool_result.name.as_str());
            let tool_summary = planned_tools
                .get(index)
                .map(|tool| tool.summary.as_str())
                .unwrap_or(tool_result.summary.as_str());
            lines.push(format!(
                "本机工具需要授权：{}，影响范围：{}。",
                tool_name, tool_summary
            ));
            lines.push(
                "请在当前回答气泡中选择允许或拒绝；允许后会用同一个工具调用继续执行。".to_string(),
            );
        } else {
            let success_count = tool_results.iter().filter(|item| item.ok).count();
            let failure_count = tool_results.len().saturating_sub(success_count);
            lines.push(format!(
                "本机工具执行摘要：共 {} 个，成功 {} 个，失败 {} 个。",
                tool_results.len(),
                success_count,
                failure_count
            ));
            let mut tool_counts: Vec<(String, usize)> = Vec::new();
            for tool_result in tool_results {
                let name = String::from(tool_result.name.trim());
                if name.is_empty() {
                    continue;
                }
                if let Some((_existing, count)) = tool_counts
                    .iter_mut()
                    .find(|(existing, _)| existing == &name)
                {
                    *count += 1;
                } else {
                    tool_counts.push((name, 1));
                }
            }
            if !tool_counts.is_empty() {
                let tool_summary = tool_counts
                    .iter()
                    .map(|(name, count)| format!("{name} x{count}"))
                    .collect::<Vec<_>>()
                    .join("，");
                lines.push(format!("工具类型：{tool_summary}。"));
            }
            let mutating_tool_count = tool_results
                .iter()
                .filter(|item| {
                    matches!(
                        item.name.as_str(),
                        "write_file" | "apply_patch" | "delete_file" | "run_command"
                    )
                })
                .count();
            if loop_failed && mutating_tool_count == 0 {
                lines.push(
                    "本轮没有执行写文件、补丁、删除或命令工具，因此没有完成文件修改。".to_string(),
                );
            }
            if let Some(failed) = tool_results.iter().find(|item| !item.ok) {
                lines.push(format!(
                    "最近失败工具：{} {}",
                    failed.error_code, failed.error
                ));
            }
        }
    } else if model_result.ok {
        if model_result.compat_text_tool_call_detected {
            lines.push(
                "模型正文包含开发期兼容工具请求，但本轮没有标准 tool_calls；已按退出条件拒绝执行。"
                    .to_string(),
            );
        } else {
            lines.push("模型未返回结构化工具调用，本轮未执行任何本机工具。".to_string());
        }
    } else if model_step_failed
        && (!model_result.error_code.trim().is_empty() || !model_result.error.trim().is_empty())
    {
        lines.push(format!(
            "失败详情：{}{}",
            model_result.error_code.trim(),
            if model_result.error.trim().is_empty() {
                String::new()
            } else {
                format!(" {}", model_result.error.trim())
            }
        ));
    }
    lines.join("\n")
}

#[derive(Debug, Clone, Serialize)]
struct PlannedLocalTool {
    tool_call_id: String,
    name: String,
    arguments: Value,
    summary: String,
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeModelMessage {
    role: String,
    content: String,
    tool_call_id: Option<String>,
    tool_calls: Vec<PlannedLocalTool>,
}

impl RuntimeModelMessage {
    fn simple(role: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: role.into(),
            content: content.into(),
            tool_call_id: None,
            tool_calls: Vec::new(),
        }
    }

    fn assistant_tool_call(content: impl Into<String>, tool_calls: Vec<PlannedLocalTool>) -> Self {
        Self {
            role: "assistant".to_string(),
            content: content.into(),
            tool_call_id: None,
            tool_calls,
        }
    }

    fn tool_observation(tool_call_id: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: "tool".to_string(),
            content: content.into(),
            tool_call_id: Some(tool_call_id.into()),
            tool_calls: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
struct AgentLoopResult {
    model_steps: Vec<ModelStepResult>,
    planned_tools: Vec<PlannedLocalTool>,
    tool_results: Vec<super::types::ToolExecutionResult>,
    candidate_solutions: Vec<AgentLoopCandidateSolution>,
    attempts: Vec<AgentLoopAttempt>,
    verification: AgentLoopVerification,
    stopped_reason: String,
    awaiting_permission: bool,
}

impl AgentLoopResult {
    fn final_model_result(&self) -> ModelStepResult {
        self.model_steps
            .last()
            .cloned()
            .unwrap_or_else(|| ModelStepResult::empty_loop_result())
    }

    fn ok(&self) -> bool {
        if self.awaiting_permission {
            return false;
        }
        match self.stopped_reason.as_str() {
            "repeated_failure" | "verification_failed" => return false,
            _ => {}
        }
        let final_result = self.final_model_result();
        final_result.ok || matches!(final_result.status.as_str(), "mock" | "unconfigured")
    }

    fn error_code(&self) -> String {
        match self.stopped_reason.as_str() {
            "repeated_failure" => "agent_loop.repeated_failure".to_string(),
            "verification_failed" => "agent_loop.verification_failed".to_string(),
            _ => String::new(),
        }
    }

    fn error(&self) -> String {
        match self.stopped_reason.as_str() {
            "repeated_failure" => {
                "agent loop repeated the same failed strategy and failure signature".to_string()
            }
            "verification_failed" => {
                "agent loop could not verify the user goal after failed attempts".to_string()
            }
            _ => String::new(),
        }
    }

    fn summary(&self) -> String {
        match self.stopped_reason.as_str() {
            "repeated_failure" => {
                "Agent Loop 检测到相同方案和相同失败签名重复出现，已暂停自动循环。".to_string()
            }
            "verification_failed" => {
                "Agent Loop 检测到失败方案尚未被新方案验证通过，已暂停并等待重新规划。".to_string()
            }
            _ => String::new(),
        }
    }

    fn audit_value(&self) -> Value {
        let mut value = self.final_model_result().audit_value();
        if let Some(object) = value.as_object_mut() {
            object.insert(
                "agent_loop".to_string(),
                json!({
                    "round_count": self.model_steps.len(),
                    "tool_round_count": self.tool_round_count(),
                    "tool_call_count": self.tool_results.len(),
                    "planned_tool_call_count": self.planned_tools.len(),
                    "stopped_reason": self.stopped_reason,
                    "awaiting_permission": self.awaiting_permission,
                    "model_steps": self.model_steps,
                    "planned_tools": self.planned_tools,
                    "candidate_solutions": self.candidate_solutions,
                    "attempts": self.attempts,
                    "verification": self.verification,
                }),
            );
        }
        value
    }

    fn tool_round_count(&self) -> usize {
        self.model_steps
            .iter()
            .filter(|step| !step.tool_calls.is_empty())
            .count()
    }
}

#[derive(Debug, Clone, Serialize)]
struct AgentLoopAttempt {
    attempt_id: String,
    strategy_name: String,
    strategy_signature: String,
    failure_signature: String,
    status: String,
    tool_call_id: String,
    tool_name: String,
    summary: String,
    error_code: String,
}

#[derive(Debug, Clone, Serialize)]
struct AgentLoopCandidateSolution {
    candidate_id: String,
    strategy_name: String,
    strategy_signature: String,
    score: i32,
    risk: String,
    verifiability: String,
    status: String,
    tool_call_id: String,
    tool_name: String,
    verification_plan: Vec<String>,
    reason: String,
}

#[derive(Debug, Clone, Serialize)]
struct AgentLoopVerification {
    status: String,
    summary: String,
    evidence: Vec<String>,
}

fn run_agent_loop(
    run_key: &str,
    runtime_session_id: &str,
    base_request: &ModelStepRequest,
    workspace_root: &PathBuf,
    permission_decision: Option<super::types::PermissionDecisionInput>,
    event_sink: Option<&dyn Fn(Value)>,
) -> AgentLoopResult {
    run_agent_loop_with(
        run_key,
        runtime_session_id,
        base_request,
        workspace_root,
        permission_decision,
        event_sink,
        &run_model_step,
        &execute_tool,
    )
}

fn run_agent_loop_with(
    run_key: &str,
    runtime_session_id: &str,
    base_request: &ModelStepRequest,
    workspace_root: &PathBuf,
    permission_decision: Option<super::types::PermissionDecisionInput>,
    event_sink: Option<&dyn Fn(Value)>,
    model_runner: &dyn Fn(&ModelStepRequest) -> ModelStepResult,
    tool_runner: &dyn Fn(ToolExecutionRequest) -> super::types::ToolExecutionResult,
) -> AgentLoopResult {
    let mut messages = base_request.messages.clone();
    let mut model_steps = Vec::new();
    let mut planned_tools = Vec::new();
    let mut tool_results = Vec::new();
    let mut candidate_solutions = Vec::new();
    let mut attempts = Vec::new();
    let mut verification_reprompts = 0usize;
    let mut permission_cache = load_session_permission_cache(workspace_root, run_key);
    let stopped_reason: String;
    let mut awaiting_permission = false;

    loop {
        let request = base_request.with_messages(messages.clone());
        let model_step_index = model_steps.len() + 1;
        emit_model_call_started_event(
            event_sink,
            runtime_session_id,
            run_key,
            model_step_index,
            &request,
        );
        let model_result = model_runner(&request);
        let current_planned_tools =
            rank_local_tool_candidates(plan_local_tools(run_key, &model_result), &attempts);
        let model_content = model_result.content.clone();
        model_steps.push(model_result.clone());
        emit_model_step_event(
            event_sink,
            runtime_session_id,
            run_key,
            model_steps.len(),
            &model_result,
        );

        if !model_result.ok {
            stopped_reason = "model_failed".to_string();
            break;
        }
        if current_planned_tools.is_empty() {
            if has_unresolved_failed_attempt(&attempts) {
                if verification_reprompts < DEFAULT_MAX_VERIFICATION_REPROMPTS {
                    verification_reprompts += 1;
                    messages.push(RuntimeModelMessage::simple(
                        "user",
                        unresolved_failure_replan_message(&attempts, &candidate_solutions),
                    ));
                    continue;
                }
                stopped_reason = "verification_failed".to_string();
                break;
            }
            stopped_reason = "no_tool_calls".to_string();
            break;
        }
        messages.push(RuntimeModelMessage::assistant_tool_call(
            model_content,
            current_planned_tools.clone(),
        ));

        let planned_tool_count = current_planned_tools.len();
        for (tool_index, tool) in current_planned_tools.into_iter().enumerate() {
            let mut candidate =
                build_agent_loop_candidate(&tool, candidate_solutions.len() + 1, &attempts);
            candidate.status = "selected".to_string();
            planned_tools.push(tool.clone());
            let effective_permission_decision = effective_permission_decision(
                &tool,
                permission_decision.as_ref(),
                &permission_cache,
            );
            emit_tool_call_started_event(
                event_sink,
                runtime_session_id,
                run_key,
                &tool,
                tool_index + 1,
                planned_tool_count,
            );
            let result = tool_runner(ToolExecutionRequest {
                tool_call_id: Some(tool.tool_call_id.clone()),
                name: tool.name.clone(),
                arguments: tool.arguments.clone(),
                workspace_path: workspace_root.to_string_lossy().to_string(),
                permission_decision: effective_permission_decision.clone(),
            });
            emit_tool_result_event(event_sink, runtime_session_id, run_key, &result);
            let permission_denied = is_permission_denied_decision(permission_decision.as_ref())
                && result.error_code == "permission.required";
            if result.error_code == "permission.required" && !permission_denied {
                emit_approval_required_event(event_sink, runtime_session_id, run_key, &result);
                awaiting_permission = true;
                candidate.status = "waiting_approval".to_string();
                candidate_solutions.push(candidate);
                tool_results.push(result);
                stopped_reason = "waiting_approval".to_string();
                return finalize_agent_loop_result(
                    model_steps,
                    planned_tools,
                    tool_results,
                    candidate_solutions,
                    attempts,
                    stopped_reason,
                    awaiting_permission,
                );
            }
            if result.ok {
                record_session_permission_grant(
                    &mut permission_cache,
                    workspace_root,
                    run_key,
                    &tool,
                    effective_permission_decision.as_ref(),
                );
            }

            let attempt = build_agent_loop_attempt(&tool, &result, attempts.len() + 1);
            let repeated_failure = !attempt.failure_signature.is_empty()
                && attempts.iter().any(|item: &AgentLoopAttempt| {
                    item.status == "failed"
                        && item.strategy_signature == attempt.strategy_signature
                        && item.failure_signature == attempt.failure_signature
                });
            let observation_content =
                tool_observation_content(&result, permission_denied, Some(&attempt));
            messages.push(RuntimeModelMessage::tool_observation(
                result.tool_call_id.clone(),
                observation_content,
            ));
            attempts.push(attempt);
            candidate.status = if result.ok { "passed" } else { "abandoned" }.to_string();
            candidate_solutions.push(candidate);
            tool_results.push(result);
            if repeated_failure {
                stopped_reason = "repeated_failure".to_string();
                return finalize_agent_loop_result(
                    model_steps,
                    planned_tools,
                    tool_results,
                    candidate_solutions,
                    attempts,
                    stopped_reason,
                    awaiting_permission,
                );
            }
        }
    }

    finalize_agent_loop_result(
        model_steps,
        planned_tools,
        tool_results,
        candidate_solutions,
        attempts,
        stopped_reason,
        awaiting_permission,
    )
}

fn emit_model_step_event(
    event_sink: Option<&dyn Fn(Value)>,
    runtime_session_id: &str,
    chat_session_id: &str,
    index: usize,
    result: &ModelStepResult,
) {
    if let Some(sink) = event_sink {
        sink(model_step_event(
            format!("evt_{runtime_session_id}_model_{index}"),
            runtime_session_id,
            chat_session_id,
            json!({
                "index": index,
                "ok": result.ok,
                "status": result.status,
                "mode": result.mode,
                "provider_id": result.provider_id,
                "model_name": result.model_name,
                "summary": result.summary,
                "error_code": result.error_code,
                "error": result.error,
                "tool_call_count": result.tool_calls.len(),
                "created_at_epoch_ms": epoch_millis(),
            }),
            epoch_millis(),
        ));
    }
}

fn emit_model_call_started_event(
    event_sink: Option<&dyn Fn(Value)>,
    runtime_session_id: &str,
    chat_session_id: &str,
    index: usize,
    request: &ModelStepRequest,
) {
    if let Some(sink) = event_sink {
        sink(model_call_started_event(
            format!("evt_{runtime_session_id}_model_{index}_started"),
            runtime_session_id,
            chat_session_id,
            json!({
                "index": index,
                "status": "running",
                "mode": request.mode.as_str(),
                "provider_id": request.provider_id.as_str(),
                "model_name": request.model_name.as_str(),
                "message_count": request.messages.len(),
                "created_at_epoch_ms": epoch_millis(),
            }),
            epoch_millis(),
        ));
    }
}

fn emit_tool_call_started_event(
    event_sink: Option<&dyn Fn(Value)>,
    runtime_session_id: &str,
    chat_session_id: &str,
    tool: &PlannedLocalTool,
    tool_index: usize,
    tool_count: usize,
) {
    if let Some(sink) = event_sink {
        let arguments_preview = serde_json::to_string(&tool.arguments)
            .map(|value| truncate_inline(&value, 500))
            .unwrap_or_default();
        sink(tool_call_started_event(
            format!(
                "evt_{}_tool_{}_started",
                runtime_session_id,
                sanitize_path_segment(&tool.tool_call_id)
            ),
            runtime_session_id,
            chat_session_id,
            json!({
                "tool_call_id": tool.tool_call_id.as_str(),
                "tool_name": tool.name.as_str(),
                "summary": tool.summary.as_str(),
                "tool_index": tool_index,
                "tool_count": tool_count,
                "arguments": &tool.arguments,
                "arguments_preview": arguments_preview,
                "created_at_epoch_ms": epoch_millis(),
            }),
            epoch_millis(),
        ));
    }
}

fn truncate_inline(value: &str, max_chars: usize) -> String {
    let normalized = value.split_whitespace().collect::<Vec<_>>().join(" ");
    if normalized.chars().count() <= max_chars {
        return normalized;
    }
    let mut output = normalized.chars().take(max_chars).collect::<String>();
    output.push('…');
    output
}

fn emit_tool_result_event(
    event_sink: Option<&dyn Fn(Value)>,
    runtime_session_id: &str,
    chat_session_id: &str,
    result: &super::types::ToolExecutionResult,
) {
    if let Some(sink) = event_sink {
        sink(tool_result_event(
            format!(
                "evt_{}_{}",
                runtime_session_id,
                sanitize_path_segment(&result.tool_result_id)
            ),
            runtime_session_id,
            chat_session_id,
            result,
            epoch_millis(),
        ));
    }
}

fn emit_approval_required_event(
    event_sink: Option<&dyn Fn(Value)>,
    runtime_session_id: &str,
    chat_session_id: &str,
    result: &super::types::ToolExecutionResult,
) {
    if let Some(permission_request) = result.content.get("permissionRequest") {
        if let Some(sink) = event_sink {
            sink(approval_required_event(
                format!(
                    "evt_{}_approval_{}",
                    runtime_session_id,
                    sanitize_path_segment(&result.tool_call_id)
                ),
                runtime_session_id,
                chat_session_id,
                permission_request.clone(),
                epoch_millis(),
            ));
        }
    }
}

fn finalize_agent_loop_result(
    model_steps: Vec<ModelStepResult>,
    planned_tools: Vec<PlannedLocalTool>,
    tool_results: Vec<super::types::ToolExecutionResult>,
    candidate_solutions: Vec<AgentLoopCandidateSolution>,
    attempts: Vec<AgentLoopAttempt>,
    stopped_reason: String,
    awaiting_permission: bool,
) -> AgentLoopResult {
    let verification = build_agent_loop_verification(
        &stopped_reason,
        awaiting_permission,
        &model_steps,
        &attempts,
    );
    AgentLoopResult {
        model_steps,
        planned_tools,
        tool_results,
        candidate_solutions,
        attempts,
        verification,
        stopped_reason,
        awaiting_permission,
    }
}

fn build_agent_loop_verification(
    stopped_reason: &str,
    awaiting_permission: bool,
    model_steps: &[ModelStepResult],
    attempts: &[AgentLoopAttempt],
) -> AgentLoopVerification {
    if awaiting_permission {
        return AgentLoopVerification {
            status: "waiting_approval".to_string(),
            summary: "等待用户授权后继续同一个 Agent Loop。".to_string(),
            evidence: vec!["permission.required".to_string()],
        };
    }
    let final_step = model_steps.last();
    match stopped_reason {
        "no_tool_calls" => AgentLoopVerification {
            status: "passed".to_string(),
            summary: "模型已停止请求工具，且没有未解决的失败方案。".to_string(),
            evidence: vec![
                format!("model_steps={}", model_steps.len()),
                format!("attempts={}", attempts.len()),
            ],
        },
        "verification_failed" => AgentLoopVerification {
            status: "failed".to_string(),
            summary: "存在失败方案未被后续成功方案覆盖，不能把当前需求判定为完成。".to_string(),
            evidence: unresolved_failure_evidence(attempts),
        },
        "repeated_failure" => AgentLoopVerification {
            status: "paused".to_string(),
            summary: "相同方案和失败签名重复出现，暂停自动循环。".to_string(),
            evidence: unresolved_failure_evidence(attempts),
        },
        "model_failed" => AgentLoopVerification {
            status: final_step
                .map(|step| step.status.clone())
                .unwrap_or_else(|| "failed".to_string()),
            summary: final_step
                .map(|step| step.summary.clone())
                .unwrap_or_else(|| "模型步骤失败。".to_string()),
            evidence: final_step
                .map(|step| vec![step.error_code.clone()])
                .unwrap_or_default(),
        },
        other => AgentLoopVerification {
            status: "stopped".to_string(),
            summary: format!("Agent Loop 停止原因：{other}"),
            evidence: vec![format!("stopped_reason={other}")],
        },
    }
}

fn build_agent_loop_attempt(
    tool: &PlannedLocalTool,
    result: &super::types::ToolExecutionResult,
    index: usize,
) -> AgentLoopAttempt {
    let strategy_signature = tool_strategy_signature(tool);
    let failure_signature = if result.ok {
        String::new()
    } else {
        tool_failure_signature(tool, result)
    };
    AgentLoopAttempt {
        attempt_id: format!("attempt-{index}"),
        strategy_name: format!("{} {}", tool.name, compact_json(&tool.arguments, 120)),
        strategy_signature,
        failure_signature,
        status: if result.ok { "passed" } else { "failed" }.to_string(),
        tool_call_id: tool.tool_call_id.clone(),
        tool_name: tool.name.clone(),
        summary: result.summary.clone(),
        error_code: result.error_code.clone(),
    }
}

fn build_agent_loop_candidate(
    tool: &PlannedLocalTool,
    index: usize,
    attempts: &[AgentLoopAttempt],
) -> AgentLoopCandidateSolution {
    let strategy_signature = tool_strategy_signature(tool);
    let abandoned_count = attempts
        .iter()
        .filter(|attempt| {
            attempt.status == "failed" && attempt.strategy_signature == strategy_signature
        })
        .count() as i32;
    let risk = tool_risk_level(&tool.name).to_string();
    let verifiability = tool_verifiability(&tool.name).to_string();
    let score = tool_candidate_score(&tool.name, abandoned_count);
    AgentLoopCandidateSolution {
        candidate_id: format!("candidate-{index}"),
        strategy_name: format!("{} {}", tool.name, compact_json(&tool.arguments, 120)),
        strategy_signature,
        score,
        risk,
        verifiability,
        status: "pending".to_string(),
        tool_call_id: tool.tool_call_id.clone(),
        tool_name: tool.name.clone(),
        verification_plan: tool_verification_plan(&tool.name),
        reason: if abandoned_count > 0 {
            "该方案签名已失败过，除非没有更高分候选，否则应切换方案。".to_string()
        } else {
            "基于工具风险、可验证性和历史失败次数排序。".to_string()
        },
    }
}

fn rank_local_tool_candidates(
    mut tools: Vec<PlannedLocalTool>,
    attempts: &[AgentLoopAttempt],
) -> Vec<PlannedLocalTool> {
    tools.sort_by(|left, right| {
        let left_score = candidate_sort_score(left, attempts);
        let right_score = candidate_sort_score(right, attempts);
        right_score
            .cmp(&left_score)
            .then_with(|| left.name.cmp(&right.name))
    });
    tools
}

fn candidate_sort_score(tool: &PlannedLocalTool, attempts: &[AgentLoopAttempt]) -> i32 {
    let signature = tool_strategy_signature(tool);
    let failed_count = attempts
        .iter()
        .filter(|attempt| attempt.status == "failed" && attempt.strategy_signature == signature)
        .count() as i32;
    tool_candidate_score(&tool.name, failed_count)
}

fn tool_candidate_score(tool_name: &str, failed_count: i32) -> i32 {
    let base = match tool_name.trim() {
        "list_files" => 90,
        "read_file" => 86,
        "search_files" => 84,
        "get_file_info" => 82,
        "run_command" => 68,
        "write_file" | "apply_patch" => 62,
        "download_file" => 58,
        "call_mcp_tool" => 54,
        "http_post" => 42,
        "delete_file" => 35,
        _ => 50,
    };
    base - failed_count * 50
}

fn tool_risk_level(tool_name: &str) -> &'static str {
    match tool_name.trim() {
        "delete_file" | "http_post" | "call_mcp_tool" => "high",
        "write_file" | "apply_patch" | "run_command" | "download_file" => "medium",
        _ => "low",
    }
}

fn tool_verifiability(tool_name: &str) -> &'static str {
    match tool_name.trim() {
        "delete_file" | "write_file" | "apply_patch" | "download_file" => "strong",
        "read_file" | "list_files" | "search_files" | "get_file_info" | "run_command" => "direct",
        _ => "manual",
    }
}

fn tool_verification_plan(tool_name: &str) -> Vec<String> {
    match tool_name.trim() {
        "delete_file" => vec!["确认目标文件 exists_after=false".to_string()],
        "write_file" | "apply_patch" => vec!["回读目标文件确认内容符合预期".to_string()],
        "download_file" => vec!["确认下载目标存在且大小大于 0".to_string()],
        "read_file" => vec!["确认读取内容与用户目标相关".to_string()],
        "list_files" | "search_files" => vec!["确认结果列表能支撑下一步定位".to_string()],
        "run_command" => vec!["检查退出码、stdout/stderr 与用户目标".to_string()],
        _ => vec!["检查工具结果 ok 与 summary".to_string()],
    }
}

fn has_unresolved_failed_attempt(attempts: &[AgentLoopAttempt]) -> bool {
    let last_failed = attempts
        .iter()
        .rposition(|attempt| attempt.status == "failed");
    let Some(last_failed) = last_failed else {
        return false;
    };
    let last_passed = attempts
        .iter()
        .rposition(|attempt| attempt.status == "passed");
    last_passed.map(|index| index < last_failed).unwrap_or(true)
}

fn unresolved_failure_evidence(attempts: &[AgentLoopAttempt]) -> Vec<String> {
    attempts
        .iter()
        .filter(|attempt| attempt.status == "failed")
        .map(|attempt| {
            format!(
                "{}:{}:{}",
                attempt.attempt_id, attempt.tool_name, attempt.failure_signature
            )
        })
        .collect()
}

fn unresolved_failure_replan_message(
    attempts: &[AgentLoopAttempt],
    candidates: &[AgentLoopCandidateSolution],
) -> String {
    let abandoned = attempts
        .iter()
        .filter(|attempt| attempt.status == "failed")
        .map(|attempt| {
            json!({
                "attempt_id": attempt.attempt_id,
                "tool_name": attempt.tool_name,
                "strategy_signature": attempt.strategy_signature,
                "failure_signature": attempt.failure_signature,
                "error_code": attempt.error_code,
                "summary": attempt.summary,
            })
        })
        .collect::<Vec<_>>();
    let candidate_summary = candidates
        .iter()
        .map(|candidate| {
            json!({
                "candidate_id": candidate.candidate_id,
                "tool_name": candidate.tool_name,
                "strategy_signature": candidate.strategy_signature,
                "score": candidate.score,
                "status": candidate.status,
            })
        })
        .collect::<Vec<_>>();
    json!({
        "agent_loop_control": "verification_failed_replan_required",
        "instruction": "用户目标尚未验证通过。不要结束回答；必须换一个未废弃 strategy_signature 的方案继续调用工具。如果没有可行方案，明确说明阻塞原因。",
        "abandoned_attempts": abandoned,
        "candidate_solutions": candidate_summary,
    })
    .to_string()
}

fn tool_strategy_signature(tool: &PlannedLocalTool) -> String {
    fnv1a_hex(&format!(
        "{}:{}",
        tool.name.trim(),
        compact_json(&tool.arguments, 800)
    ))
}

fn tool_failure_signature(
    tool: &PlannedLocalTool,
    result: &super::types::ToolExecutionResult,
) -> String {
    fnv1a_hex(&format!(
        "{}:{}:{}:{}",
        tool.name.trim(),
        result.error_code.trim(),
        result.error.trim(),
        result.summary.trim()
    ))
}

fn compact_json(value: &Value, limit: usize) -> String {
    let raw = serde_json::to_string(value).unwrap_or_else(|_| value.to_string());
    raw.chars().take(limit).collect()
}

fn is_permission_denied_decision(decision: Option<&super::types::PermissionDecisionInput>) -> bool {
    decision
        .map(|value| value.decision.trim() == "deny")
        .unwrap_or(false)
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct SessionPermissionGrant {
    action: String,
    tool_name: String,
    source_request_id: String,
    decision: String,
    grant_scope: String,
    created_at_epoch_ms: u128,
    last_used_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct SessionPermissionCache {
    version: u32,
    chat_session_id: String,
    grants: Vec<SessionPermissionGrant>,
    updated_at_epoch_ms: u128,
}

impl SessionPermissionCache {
    fn empty(chat_session_id: &str) -> Self {
        Self {
            version: PERMISSION_CACHE_VERSION,
            chat_session_id: chat_session_id.to_string(),
            grants: Vec::new(),
            updated_at_epoch_ms: epoch_millis(),
        }
    }
}

fn effective_permission_decision(
    tool: &PlannedLocalTool,
    incoming_decision: Option<&super::types::PermissionDecisionInput>,
    cache: &SessionPermissionCache,
) -> Option<super::types::PermissionDecisionInput> {
    let action = permission_action_for_tool(&tool.name)?;
    let expected_request_id = permission_request_id(&tool.tool_call_id, action);
    if let Some(decision) = incoming_decision {
        let decision_value = decision.decision.trim();
        let grant_scope = decision.grant_scope.as_deref().unwrap_or("").trim();
        let request_matches = decision
            .request_id
            .as_deref()
            .map(str::trim)
            .map(|value| value == expected_request_id)
            .unwrap_or(decision_value == "approve_once");
        if decision_value == "approve_once" && request_matches {
            return Some(decision.clone());
        }
        if decision_value == "approve_session"
            && matches!(grant_scope, "session" | "current_session")
            && request_matches
        {
            return Some(decision.clone());
        }
        if decision_value == "approve_session"
            && matches!(grant_scope, "session" | "current_session")
            && decision
                .request_id
                .as_deref()
                .map(str::trim)
                .is_some_and(|request_id| permission_request_id_matches_action(request_id, action))
        {
            return Some(super::types::PermissionDecisionInput {
                request_id: Some(expected_request_id),
                decision: "approve_session".to_string(),
                grant_scope: Some("session".to_string()),
                comment: decision.comment.clone(),
            });
        }
    }
    cache
        .grants
        .iter()
        .rev()
        .find(|grant| grant.action == action && grant.decision == "approve_session")
        .map(|grant| super::types::PermissionDecisionInput {
            request_id: None,
            decision: "approve_session".to_string(),
            grant_scope: Some("session".to_string()),
            comment: Some(cached_session_grant_comment(&grant.action)),
        })
}

fn record_session_permission_grant(
    cache: &mut SessionPermissionCache,
    workspace_root: &PathBuf,
    chat_session_id: &str,
    tool: &PlannedLocalTool,
    decision: Option<&super::types::PermissionDecisionInput>,
) {
    let Some(decision) = decision else {
        return;
    };
    if decision.decision.trim() != "approve_session" {
        return;
    }
    if !matches!(
        decision.grant_scope.as_deref().unwrap_or("").trim(),
        "session" | "current_session"
    ) {
        return;
    }
    let Some(action) = permission_action_for_tool(&tool.name) else {
        return;
    };
    let expected_request_id = permission_request_id(&tool.tool_call_id, action);
    let request_id = decision
        .request_id
        .as_deref()
        .map(str::trim)
        .filter(|value| *value == expected_request_id)
        .unwrap_or("");
    if request_id.is_empty() {
        return;
    }
    let now = epoch_millis();
    if let Some(grant) = cache
        .grants
        .iter_mut()
        .find(|grant| grant.action == action && grant.decision == "approve_session")
    {
        grant.tool_name = tool.name.clone();
        grant.source_request_id = request_id.to_string();
        grant.last_used_at_epoch_ms = now;
    } else {
        cache.grants.push(SessionPermissionGrant {
            action: action.to_string(),
            tool_name: tool.name.clone(),
            source_request_id: request_id.to_string(),
            decision: "approve_session".to_string(),
            grant_scope: "session".to_string(),
            created_at_epoch_ms: now,
            last_used_at_epoch_ms: now,
        });
    }
    cache.updated_at_epoch_ms = now;
    let _ = write_session_permission_cache(workspace_root, chat_session_id, cache);
}

fn permission_action_for_tool(tool_name: &str) -> Option<&'static str> {
    match tool_name.trim() {
        "write_file" | "apply_patch" => Some("file.write"),
        "delete_file" => Some("file.delete"),
        "run_command" => Some("command.run"),
        "http_post" => Some("network.write"),
        "download_file" => Some("network.read"),
        "call_mcp_tool" => Some("mcp.call"),
        _ => None,
    }
}

fn permission_request_id_matches_action(request_id: &str, action: &str) -> bool {
    let action_suffix = format!("_{}", action.replace('.', "_"));
    request_id.starts_with("perm_") && request_id.ends_with(&action_suffix)
}

fn load_session_permission_cache(
    workspace_root: &PathBuf,
    chat_session_id: &str,
) -> SessionPermissionCache {
    let path = session_permission_cache_path(workspace_root, chat_session_id);
    let Ok(raw) = fs::read_to_string(path) else {
        return SessionPermissionCache::empty(chat_session_id);
    };
    serde_json::from_str::<SessionPermissionCache>(&raw)
        .unwrap_or_else(|_| SessionPermissionCache::empty(chat_session_id))
}

fn write_session_permission_cache(
    workspace_root: &PathBuf,
    chat_session_id: &str,
    cache: &SessionPermissionCache,
) -> Result<(), ToolError> {
    let path = session_permission_cache_path(workspace_root, chat_session_id);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create permission cache directory failed: {err}"),
            )
        })?;
    }
    let raw = serde_json::to_string_pretty(cache).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("serialize permission cache failed: {err}"),
        )
    })?;
    fs::write(path, raw).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("write permission cache failed: {err}"),
        )
    })
}

fn session_permission_cache_path(workspace_root: &PathBuf, chat_session_id: &str) -> PathBuf {
    workspace_root
        .join(".ai-employee")
        .join("agent-runtime-v2")
        .join("permissions")
        .join(format!("{}.json", sanitize_path_segment(chat_session_id)))
}

fn tool_observation_content(
    result: &super::types::ToolExecutionResult,
    permission_denied: bool,
    attempt: Option<&AgentLoopAttempt>,
) -> String {
    let status = if result.ok {
        "ok"
    } else if permission_denied {
        "permission_denied"
    } else {
        "error"
    };
    let attempt_payload = attempt
        .map(|item| {
            json!({
                "attempt_id": item.attempt_id,
                "strategy_signature": item.strategy_signature,
                "failure_signature": item.failure_signature,
                "status": item.status,
            })
        })
        .unwrap_or_else(|| json!({}));
    json!({
        "tool_call_id": result.tool_call_id,
        "tool_name": result.name,
        "status": status,
        "ok": result.ok,
        "summary": result.summary,
        "error_code": if permission_denied { "permission.denied" } else { result.error_code.as_str() },
        "error": if permission_denied { "user denied permission request" } else { result.error.as_str() },
        "content": result.content,
        "attempt": attempt_payload,
        "retry_instruction": if result.ok || permission_denied {
            ""
        } else {
            "当前方案验证失败。下一轮必须换一个不同 strategy_signature 的方案；不要原样重复同一个工具、参数和验证路径。"
        },
    })
    .to_string()
}

fn plan_local_tools(run_key: &str, model_result: &ModelStepResult) -> Vec<PlannedLocalTool> {
    if !model_result.tool_calls.is_empty() {
        return model_result.tool_calls.clone();
    }
    if model_result.allow_compat_text_tool_call {
        if let Some(tool) = parse_compat_text_tool_request(run_key, &model_result.content) {
            return vec![tool];
        }
    }
    Vec::new()
}

fn parse_compat_text_tool_request(run_key: &str, content: &str) -> Option<PlannedLocalTool> {
    let trimmed = content.trim();
    if trimmed.is_empty() {
        return None;
    }
    let value = serde_json::from_str::<Value>(trimmed).ok()?;
    let tool_value = value.get("tool").or_else(|| value.get("tool_call"))?;
    let name = tool_value
        .get("name")
        .or_else(|| value.get("name"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|item| !item.is_empty())?;
    let arguments = tool_value
        .get("arguments")
        .or_else(|| tool_value.get("args"))
        .or_else(|| value.get("arguments"))
        .or_else(|| value.get("args"))
        .cloned()
        .unwrap_or_else(|| json!({}));
    Some(PlannedLocalTool {
        tool_call_id: normalized_tool_call_id(Some(
            tool_value
                .get("tool_call_id")
                .or_else(|| value.get("tool_call_id"))
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| stable_tool_call_id(run_key, name)),
        )),
        name: name.to_string(),
        summary: format!("开发期兼容正文工具请求：{name}"),
        arguments,
    })
}

fn stable_tool_call_id(run_key: &str, tool_name: &str) -> String {
    format!(
        "local_{}_{}",
        sanitize_path_segment(run_key),
        sanitize_path_segment(tool_name)
    )
}

fn stable_tool_call_id_for_arguments(
    run_key: &str,
    tool_name: &str,
    arguments: &Value,
    index: usize,
) -> String {
    let canonical_arguments =
        serde_json::to_string(arguments).unwrap_or_else(|_| arguments.to_string());
    format!(
        "local_{}_{}_{}_{}",
        sanitize_path_segment(run_key),
        sanitize_path_segment(tool_name),
        index,
        fnv1a_hex(&canonical_arguments)
    )
}

fn fnv1a_hex(value: &str) -> String {
    let mut hash = 0xcbf29ce484222325u64;
    for byte in value.as_bytes() {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}

fn build_operations(session_id: &str, agent_loop: &AgentLoopResult) -> Value {
    let mut operations = vec![json!({
        "operationId": format!("local-agent:{session_id}"),
        "kind": "request",
        "title": "桌面本地 Agent Runtime",
        "summary": "已在 Tauri 本地创建会话并记录 requirement",
        "phase": "completed",
        "actionType": "none",
        "meta": {
            "source": "tauri_liuagent_local_chat",
            "session_id": session_id
        }
    })];
    for (index, model_result) in agent_loop.model_steps.iter().enumerate() {
        operations.push(json!({
            "operationId": format!("local-model:{session_id}:{}", index + 1),
            "kind": "model",
            "title": format!("本地模型步骤 {}", index + 1),
            "summary": model_result.summary.as_str(),
            "detail": model_result.error.as_str(),
            "phase": if model_result.ok { "completed" } else { "failed" },
            "actionType": "none",
            "meta": model_result.audit_value()
        }));
    }
    if !agent_loop.candidate_solutions.is_empty() {
        let detail = agent_loop
            .candidate_solutions
            .iter()
            .map(|candidate| {
                format!(
                    "{}. {} score={} status={} risk={} verify={}",
                    candidate.candidate_id,
                    candidate.tool_name,
                    candidate.score,
                    candidate.status,
                    candidate.risk,
                    candidate.verifiability
                )
            })
            .collect::<Vec<_>>()
            .join("\n");
        operations.push(json!({
            "operationId": format!("local-agent-candidates:{session_id}"),
            "kind": "plan",
            "title": "本地 Agent 方案排序",
            "summary": format!("已评估 {} 个候选方案", agent_loop.candidate_solutions.len()),
            "detail": detail,
            "phase": if agent_loop.ok() { "completed" } else { "running" },
            "actionType": "none",
            "meta": {
                "source": "tauri_liuagent_local_chat",
                "candidate_solutions": agent_loop.candidate_solutions.as_slice()
            }
        }));
    }
    for tool_result in &agent_loop.tool_results {
        operations.push(json!({
            "operationId": format!("local-tool:{}", tool_result.tool_call_id),
            "kind": "tool",
            "title": format!("本地工具：{}", tool_result.name),
            "summary": tool_result.summary.as_str(),
            "detail": if tool_result.ok { "" } else { tool_result.error.as_str() },
            "phase": if tool_result.ok { "completed" } else { "failed" },
            "actionType": "none",
            "meta": {
                "tool_result_id": tool_result.tool_result_id.as_str(),
                "tool_call_id": tool_result.tool_call_id.as_str(),
                "tool_name": tool_result.name.as_str(),
                "output_preview": tool_result.summary.as_str(),
                "error": tool_result.error.as_str()
            }
        }));
    }
    operations.push(json!({
        "operationId": format!("local-agent-verification:{session_id}"),
        "kind": "verification",
        "title": "本地 Agent 验证结果",
        "summary": agent_loop.verification.summary.as_str(),
        "detail": agent_loop.verification.evidence.join("\n"),
        "phase": match agent_loop.verification.status.as_str() {
            "passed" => "completed",
            "waiting_approval" => "waiting_user",
            "paused" => "blocked",
            "failed" => "failed",
            _ => "running",
        },
        "actionType": "none",
        "meta": {
            "source": "tauri_liuagent_local_chat",
            "verification": &agent_loop.verification
        }
    }));
    Value::Array(operations)
}

#[derive(Debug, Clone)]
struct ModelStepRequest {
    mode: String,
    provider_id: String,
    model_name: String,
    base_url: String,
    api_key: String,
    gateway_url: String,
    temperature: f64,
    max_tokens: u32,
    timeout_ms: u64,
    messages: Vec<RuntimeModelMessage>,
}

impl ModelStepRequest {
    fn with_messages(&self, messages: Vec<RuntimeModelMessage>) -> Self {
        Self {
            mode: self.mode.clone(),
            provider_id: self.provider_id.clone(),
            model_name: self.model_name.clone(),
            base_url: self.base_url.clone(),
            api_key: self.api_key.clone(),
            gateway_url: self.gateway_url.clone(),
            temperature: self.temperature,
            max_tokens: self.max_tokens,
            timeout_ms: self.timeout_ms,
            messages,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
struct ModelStepResult {
    ok: bool,
    mode: String,
    provider_id: String,
    model_name: String,
    status: String,
    content: String,
    tool_calls: Vec<PlannedLocalTool>,
    allow_compat_text_tool_call: bool,
    compat_text_tool_call_detected: bool,
    summary: String,
    error_code: String,
    error: String,
}

impl ModelStepResult {
    fn audit_value(&self) -> Value {
        json!({
            "ok": self.ok,
            "mode": self.mode,
            "provider_id": self.provider_id,
            "model_name": self.model_name,
            "status": self.status,
            "tool_calls": self.tool_calls.as_slice(),
            "tool_call_count": self.tool_calls.len(),
            "compat_text_tool_call_detected": self.compat_text_tool_call_detected,
            "summary": self.summary,
            "error_code": self.error_code,
            "error": self.error
        })
    }

    fn skipped(request: &ModelStepRequest, status: &str, summary: impl Into<String>) -> Self {
        Self {
            ok: false,
            mode: request.mode.clone(),
            provider_id: request.provider_id.clone(),
            model_name: request.model_name.clone(),
            status: status.to_string(),
            content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: summary.into(),
            error_code: String::new(),
            error: String::new(),
        }
    }

    fn failed(
        request: &ModelStepRequest,
        code: impl Into<String>,
        error: impl Into<String>,
    ) -> Self {
        let error = error.into();
        Self {
            ok: false,
            mode: request.mode.clone(),
            provider_id: request.provider_id.clone(),
            model_name: request.model_name.clone(),
            status: "failed".to_string(),
            content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: error.clone(),
            error_code: code.into(),
            error,
        }
    }

    fn empty_loop_result() -> Self {
        Self {
            ok: false,
            mode: "mock".to_string(),
            provider_id: "unconfigured".to_string(),
            model_name: "unconfigured".to_string(),
            status: "failed".to_string(),
            content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: "agent loop did not run any model step".to_string(),
            error_code: "agent_loop.empty".to_string(),
            error: "agent loop did not run any model step".to_string(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ModelRequestErrorKind {
    Timeout,
    Request,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ModelRequestError {
    kind: ModelRequestErrorKind,
    message: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ModelRequestRetryFailure {
    code: String,
    message: String,
    attempts: usize,
}

fn send_model_request_with_timeout_retry<T>(
    max_attempts: usize,
    mut send: impl FnMut() -> Result<T, ModelRequestError>,
) -> Result<T, ModelRequestRetryFailure> {
    let max_attempts = max_attempts.max(1);
    for attempt in 1..=max_attempts {
        match send() {
            Ok(value) => return Ok(value),
            Err(error)
                if error.kind == ModelRequestErrorKind::Timeout && attempt < max_attempts =>
            {
                continue;
            }
            Err(error) if error.kind == ModelRequestErrorKind::Timeout => {
                return Err(ModelRequestRetryFailure {
                    code: "model.connection_timeout".to_string(),
                    message: format!("模型连接超时，已尝试 {attempt} 次仍失败：{}", error.message),
                    attempts: attempt,
                });
            }
            Err(error) => {
                return Err(ModelRequestRetryFailure {
                    code: "model.request_failed".to_string(),
                    message: format!("模型请求失败：{}", error.message),
                    attempts: attempt,
                });
            }
        }
    }
    unreachable!("model request retry loop always returns");
}

#[derive(Debug, Deserialize)]
struct OpenAiCompatibleResponse {
    choices: Option<Vec<OpenAiCompatibleChoice>>,
}

#[derive(Debug, Deserialize)]
struct OpenAiCompatibleChoice {
    message: Option<OpenAiCompatibleMessage>,
}

#[derive(Debug, Deserialize)]
struct OpenAiCompatibleMessage {
    content: Option<Value>,
    tool_calls: Option<Vec<OpenAiCompatibleToolCall>>,
}

#[derive(Debug, Deserialize)]
struct OpenAiCompatibleToolCall {
    function: Option<OpenAiCompatibleFunctionCall>,
}

#[derive(Debug, Deserialize)]
struct OpenAiCompatibleFunctionCall {
    name: Option<String>,
    arguments: Option<Value>,
}

fn build_model_request(request: &LocalChatRequest, user_message: &str) -> ModelStepRequest {
    let runtime = request
        .model_runtime
        .clone()
        .unwrap_or(LocalModelRuntimeConfig {
            mode: None,
            provider_id: None,
            model_name: None,
            base_url: None,
            api_key: None,
            api_key_env: None,
            gateway_url: None,
            temperature: None,
            max_tokens: None,
            timeout_ms: None,
        });
    let mode = normalize_model_mode(runtime.mode.as_deref());
    let provider_id = first_non_empty(&[
        runtime.provider_id.as_deref(),
        request.provider_id.as_deref(),
    ])
    .unwrap_or("unconfigured")
    .to_string();
    let model_name =
        first_non_empty(&[runtime.model_name.as_deref(), request.model_name.as_deref()])
            .unwrap_or("unconfigured")
            .to_string();
    let api_key = resolve_api_key(&runtime);
    let mut messages = Vec::new();
    if let Some(system_prompt) = request
        .system_prompt
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        messages.push(RuntimeModelMessage::simple(
            "system",
            system_prompt.to_string(),
        ));
    }
    messages.extend(request.history.iter().filter_map(|message| {
        if ["user", "assistant", "system"].contains(&message.role.trim())
            && !message.content.trim().is_empty()
        {
            Some(RuntimeModelMessage::simple(
                message.role.trim().to_string(),
                message.content.clone(),
            ))
        } else {
            None
        }
    }));
    messages.push(RuntimeModelMessage::simple(
        "user",
        user_message.to_string(),
    ));

    ModelStepRequest {
        mode,
        provider_id,
        model_name,
        base_url: runtime.base_url.unwrap_or_default().trim().to_string(),
        api_key,
        gateway_url: runtime.gateway_url.unwrap_or_default().trim().to_string(),
        temperature: runtime
            .temperature
            .or(request.temperature)
            .unwrap_or(0.2)
            .clamp(0.0, 2.0),
        max_tokens: runtime
            .max_tokens
            .or(request.max_tokens)
            .unwrap_or(DEFAULT_MAX_TOKENS)
            .clamp(16, 8192),
        timeout_ms: runtime
            .timeout_ms
            .unwrap_or(DEFAULT_MODEL_TIMEOUT_MS)
            .clamp(1_000, 120_000),
        messages,
    }
}

fn run_model_step(request: &ModelStepRequest) -> ModelStepResult {
    match request.mode.as_str() {
        "direct-openai-compatible" => run_openai_compatible_model_step(request),
        "backend-gateway" => {
            if request.gateway_url.trim().is_empty() {
                return ModelStepResult::skipped(
                    request,
                    "unconfigured",
                    "后端模型网关地址未配置；本轮未执行真实模型调用。",
                );
            }
            ModelStepResult::skipped(
                request,
                "not_implemented",
                "后端模型网关契约尚未接入 Tauri；本轮保持本地工具执行，不把用户本地工具交给后端。",
            )
        }
        _ => ModelStepResult::skipped(
            request,
            "mock",
            "未配置桌面端可本地调用的模型运行时；本轮使用本地骨架回复。",
        ),
    }
}

fn run_openai_compatible_model_step(request: &ModelStepRequest) -> ModelStepResult {
    if request.base_url.trim().is_empty() {
        return ModelStepResult::skipped(
            request,
            "unconfigured",
            "direct-openai-compatible 模式缺少 baseUrl。",
        );
    }
    if request.api_key.trim().is_empty() {
        return ModelStepResult::skipped(
            request,
            "unconfigured",
            "direct-openai-compatible 模式缺少 apiKey 或 apiKeyEnv。",
        );
    }
    if request.model_name == "unconfigured" {
        return ModelStepResult::skipped(
            request,
            "unconfigured",
            "direct-openai-compatible 模式缺少 modelName。",
        );
    }

    let endpoint = match build_chat_completion_url(&request.base_url) {
        Ok(value) => value,
        Err(error) => {
            return ModelStepResult::failed(request, "model.schema_invalid", error.message)
        }
    };
    let mut headers = HeaderMap::new();
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
    let auth_value = match HeaderValue::from_str(&format!("Bearer {}", request.api_key.trim())) {
        Ok(value) => value,
        Err(err) => {
            return ModelStepResult::failed(
                request,
                "model.schema_invalid",
                format!("invalid api key header: {err}"),
            )
        }
    };
    headers.insert(AUTHORIZATION, auth_value);

    let body = json!({
        "model": request.model_name,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": false,
        "tools": openai_compatible_tool_schemas(),
        "tool_choice": "auto",
        "messages": request.messages.iter().map(openai_compatible_message_payload).collect::<Vec<_>>()
    });

    let client = match Client::builder()
        .timeout(Duration::from_millis(request.timeout_ms))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
    {
        Ok(value) => value,
        Err(err) => {
            return ModelStepResult::failed(
                request,
                "model.request_failed",
                format!("模型请求初始化失败：{err}"),
            )
        }
    };
    let response: Response =
        match send_model_request_with_timeout_retry(MODEL_CONNECTION_TIMEOUT_MAX_ATTEMPTS, || {
            client
                .post(endpoint.clone())
                .headers(headers.clone())
                .json(&body)
                .send()
                .map_err(|err| ModelRequestError {
                    kind: if err.is_timeout() {
                        ModelRequestErrorKind::Timeout
                    } else {
                        ModelRequestErrorKind::Request
                    },
                    message: err.to_string(),
                })
        }) {
            Ok(value) => value,
            Err(error) => return ModelStepResult::failed(request, error.code, error.message),
        };
    let status = response.status().as_u16();
    if !(200..300).contains(&status) {
        return ModelStepResult::failed(
            request,
            "model.request_failed",
            format!("model gateway returned HTTP {status}"),
        );
    }
    let payload = match response.json::<OpenAiCompatibleResponse>() {
        Ok(value) => value,
        Err(err) => {
            return ModelStepResult::failed(
                request,
                "model.response_invalid",
                format!("model response parse failed: {err}"),
            )
        }
    };
    let message = payload
        .choices
        .and_then(|choices| choices.into_iter().next())
        .and_then(|choice| choice.message);
    let content = message
        .as_ref()
        .and_then(|message| stringify_model_content(message.content.clone()))
        .unwrap_or_default();
    let tool_calls = message
        .and_then(|message| collect_openai_tool_calls(&request.provider_id, message.tool_calls))
        .unwrap_or_default();
    if content.trim().is_empty() && tool_calls.is_empty() {
        return ModelStepResult::failed(
            request,
            "model.empty_response",
            "model returned empty content",
        );
    }
    let compat_text_tool_call_detected =
        parse_compat_text_tool_request(&request.provider_id, &content).is_some();
    ModelStepResult {
        ok: true,
        mode: request.mode.clone(),
        provider_id: request.provider_id.clone(),
        model_name: request.model_name.clone(),
        status: "completed".to_string(),
        summary: format!(
            "模型已在桌面端本机调用：{} / {}，返回 {} 个工具调用",
            request.provider_id,
            request.model_name,
            tool_calls.len()
        ),
        content,
        tool_calls,
        allow_compat_text_tool_call: false,
        compat_text_tool_call_detected,
        error_code: String::new(),
        error: String::new(),
    }
}

fn openai_compatible_tool_schemas() -> Vec<Value> {
    builtin_tool_definitions()
        .into_iter()
        .map(|definition| {
            json!({
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.input_schema
                }
            })
        })
        .collect()
}

fn openai_compatible_message_payload(message: &RuntimeModelMessage) -> Value {
    let role = normalize_model_message_role(&message.role);
    if role == "tool" {
        return json!({
            "role": "tool",
            "tool_call_id": message.tool_call_id.as_deref().unwrap_or("local_call"),
            "content": message.content
        });
    }
    if role == "assistant" && !message.tool_calls.is_empty() {
        return json!({
            "role": "assistant",
            "content": message.content,
            "tool_calls": message.tool_calls.iter().map(|tool| {
                json!({
                    "id": tool.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "arguments": tool.arguments.to_string()
                    }
                })
            }).collect::<Vec<_>>()
        });
    }
    json!({
        "role": role,
        "content": message.content
    })
}

fn collect_openai_tool_calls(
    run_key: &str,
    tool_calls: Option<Vec<OpenAiCompatibleToolCall>>,
) -> Option<Vec<PlannedLocalTool>> {
    let planned = tool_calls?
        .into_iter()
        .enumerate()
        .filter_map(|(index, tool_call)| {
            let function = tool_call.function?;
            let name = function
                .name
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())?
                .to_string();
            let arguments = parse_openai_tool_arguments(function.arguments);
            Some(PlannedLocalTool {
                tool_call_id: normalized_tool_call_id(Some(stable_tool_call_id_for_arguments(
                    run_key, &name, &arguments, index,
                ))),
                summary: format!("标准模型工具调用：{name}"),
                name,
                arguments,
            })
        })
        .collect::<Vec<_>>();
    Some(planned)
}

fn parse_openai_tool_arguments(value: Option<Value>) -> Value {
    match value.unwrap_or_else(|| json!({})) {
        Value::String(raw) => serde_json::from_str::<Value>(&raw).unwrap_or_else(|_| json!({})),
        object @ Value::Object(_) => object,
        other => other,
    }
}

fn build_chat_completion_url(base_url: &str) -> Result<String, ToolError> {
    let trimmed = base_url.trim().trim_end_matches('/');
    let endpoint = if trimmed.ends_with("/chat/completions") {
        trimmed.to_string()
    } else if trimmed.ends_with("/v1") {
        format!("{trimmed}/chat/completions")
    } else {
        format!("{trimmed}/v1/chat/completions")
    };
    let url = Url::parse(&endpoint)
        .map_err(|err| ToolError::new("model.schema_invalid", format!("invalid baseUrl: {err}")))?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "model.schema_invalid",
            "model baseUrl only supports http and https",
        ));
    }
    Ok(url.to_string())
}

fn stringify_model_content(value: Option<Value>) -> Option<String> {
    match value? {
        Value::String(text) => Some(text),
        Value::Array(items) => {
            let parts = items
                .into_iter()
                .filter_map(|item| {
                    if let Some(text) = item.get("text").and_then(Value::as_str) {
                        return Some(text.to_string());
                    }
                    if let Some(text) = item.get("content").and_then(Value::as_str) {
                        return Some(text.to_string());
                    }
                    None
                })
                .collect::<Vec<_>>();
            Some(parts.join("\n"))
        }
        other => Some(other.to_string()),
    }
}

fn normalize_model_mode(value: Option<&str>) -> String {
    match value
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "direct-openai-compatible" | "openai-compatible" | "direct" => {
            "direct-openai-compatible".to_string()
        }
        "backend-gateway" | "gateway" => "backend-gateway".to_string(),
        _ => "mock".to_string(),
    }
}

fn normalize_model_message_role(value: &str) -> &str {
    match value.trim() {
        "system" => "system",
        "assistant" => "assistant",
        "tool" => "tool",
        _ => "user",
    }
}

fn resolve_api_key(runtime: &LocalModelRuntimeConfig) -> String {
    if let Some(value) = runtime
        .api_key
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        return value.to_string();
    }
    if let Some(env_name) = runtime
        .api_key_env
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        return std::env::var(env_name)
            .unwrap_or_default()
            .trim()
            .to_string();
    }
    String::new()
}

fn first_non_empty<'a>(values: &[Option<&'a str>]) -> Option<&'a str> {
    values
        .iter()
        .filter_map(|value| value.map(str::trim).filter(|item| !item.is_empty()))
        .next()
}

fn requirement_record_path(root: &PathBuf, project_id: &str, chat_session_id: &str) -> PathBuf {
    root.join(".ai-employee")
        .join("requirements")
        .join(sanitize_path_segment(project_id))
        .join(format!("{}.json", sanitize_path_segment(chat_session_id)))
}

fn write_requirement_record(path: &PathBuf, content: Value) -> Result<(), ToolError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create requirement directory failed: {err}"),
            )
        })?;
    }
    let raw = serde_json::to_string_pretty(&content).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("serialize requirement record failed: {err}"),
        )
    })?;
    fs::write(path, raw).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("write requirement record failed: {err}"),
        )
    })
}

fn required_non_empty(value: &str, field: &str) -> Result<String, ToolError> {
    let normalized = value.trim();
    if normalized.is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            format!("{field} is required"),
        ));
    }
    Ok(normalized.to_string())
}

fn normalized_id(value: Option<&str>, fallback_prefix: &str) -> String {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| format!("{}_{}", fallback_prefix, epoch_millis()))
}

fn sanitize_path_segment(value: &str) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' {
                ch
            } else {
                '_'
            }
        })
        .collect()
}

fn epoch_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_millis())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::thread;

    #[test]
    fn local_chat_writes_requirement_and_tool_summary() {
        let dir = std::env::temp_dir().join(format!("liuagent_local_chat_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("README.md"), "local agent").unwrap();

        let result = start_local_chat(LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-test".to_string(),
            message_id: Some("msg-user".to_string()),
            assistant_message_id: Some("msg-assistant".to_string()),
            message: "检查工作区".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: None,
            model_name: None,
            system_prompt: None,
            temperature: None,
            max_tokens: None,
            model_runtime: None,
            permission_decision: None,
            plan_decision: None,
        });

        assert!(result.ok, "{}", result.error);
        assert!(result.assistant_content.contains("桌面端本机"));
        assert_eq!(result.model_result["mode"], "mock");
        assert!(result.tool_results.is_empty());
        assert!(PathBuf::from(&result.requirement_record_path).exists());
        let requirement = serde_json::from_str::<Value>(
            &fs::read_to_string(&result.requirement_record_path).unwrap(),
        )
        .unwrap();
        assert!(PathBuf::from(
            requirement["runtime_state"]["statePath"]
                .as_str()
                .expect("runtime state path")
        )
        .exists());
        let recovered = recover_runtime_state(&dir, "proj-test", "chat-test").unwrap();
        assert_eq!(recovered["run_state"]["status"], "completed");
        assert_eq!(recovered["chat_session_id"], "chat-test");
        assert!(result
            .runtime_events
            .iter()
            .any(|event| event["type"] == "state_changed"));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn plan_local_tools_use_standard_model_tool_calls() {
        let model_result = ModelStepResult {
            ok: true,
            mode: "mock".to_string(),
            provider_id: "test".to_string(),
            model_name: "test-model".to_string(),
            status: "completed".to_string(),
            content: String::new(),
            tool_calls: vec![PlannedLocalTool {
                tool_call_id: "call_write".to_string(),
                name: "write_file".to_string(),
                arguments: json!({
                    "path": "tmp/local-agent.txt",
                    "content": "hello local agent"
                }),
                summary: "标准模型工具调用：write_file".to_string(),
            }],
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: "standard tool call".to_string(),
            error_code: String::new(),
            error: String::new(),
        };

        let planned = plan_local_tools("chat-test", &model_result);

        assert_eq!(planned.len(), 1);
        assert_eq!(planned[0].name, "write_file");
        assert_eq!(planned[0].arguments["path"], "tmp/local-agent.txt");
        assert_eq!(planned[0].arguments["content"], "hello local agent");
    }

    #[test]
    fn compat_text_tool_request_is_disabled_by_default() {
        let model_result = ModelStepResult {
            ok: true,
            mode: "mock".to_string(),
            provider_id: "test".to_string(),
            model_name: "test-model".to_string(),
            status: "completed".to_string(),
            content: json!({
                "tool": {
                    "name": "delete_file",
                    "arguments": {
                        "path": "reademe.md"
                    }
                }
            })
            .to_string(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: true,
            summary: "legacy text tool call".to_string(),
            error_code: String::new(),
            error: String::new(),
        };

        let planned = plan_local_tools("chat-delete-test", &model_result);

        assert!(planned.is_empty());
    }

    #[test]
    fn agent_loop_feeds_tool_observation_back_to_model() {
        let dir = std::env::temp_dir().join(format!("liuagent_loop_read_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("README.md"), "local agent loop").unwrap();
        let request = test_model_request("读取 README.md");
        let model_call_count = Cell::new(0);
        let model_runner = |request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_read".to_string(),
                        name: "read_file".to_string(),
                        arguments: json!({"path": "README.md"}),
                        summary: "标准模型工具调用：read_file".to_string(),
                    }],
                );
            }
            assert!(
                request.messages.iter().any(|message| message.role == "tool"
                    && message.content.contains("local agent loop")),
                "second model call must receive tool observation"
            );
            test_model_result("README.md 内容是 local agent loop", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-test",
            "runtime-chat-loop-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(model_call_count.get(), 2);
        assert_eq!(result.model_steps.len(), 2);
        assert_eq!(result.tool_results.len(), 1);
        assert_eq!(result.stopped_reason, "no_tool_calls");
        assert_eq!(
            result.final_model_result().content,
            "README.md 内容是 local agent loop"
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_feeds_failure_signature_and_switch_instruction_to_model() {
        let dir = std::env::temp_dir().join(format!("liuagent_loop_switch_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("README.md"), "local agent loop").unwrap();
        let request = test_model_request("读取缺失文件后换方案");
        let model_call_count = Cell::new(0);
        let model_runner = |request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_missing".to_string(),
                        name: "read_file".to_string(),
                        arguments: json!({"path": "missing.md"}),
                        summary: "标准模型工具调用：read_file".to_string(),
                    }],
                );
            }
            if index == 1 {
                let observation = request
                    .messages
                    .iter()
                    .find(|message| message.role == "tool")
                    .map(|message| message.content.as_str())
                    .unwrap_or("");
                assert!(observation.contains("failure_signature"));
                assert!(observation.contains("不同 strategy_signature"));
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_list".to_string(),
                        name: "list_files".to_string(),
                        arguments: json!({"path": "."}),
                        summary: "标准模型工具调用：list_files".to_string(),
                    }],
                );
            }
            test_model_result("已改用列目录方案完成核对", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-switch-test",
            "runtime-chat-loop-switch-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(model_call_count.get(), 3);
        assert_eq!(result.tool_results.len(), 2);
        assert!(!result.attempts[0].failure_signature.is_empty());
        assert_ne!(
            result.attempts[0].strategy_signature,
            result.attempts[1].strategy_signature
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_pauses_when_same_failed_strategy_repeats() {
        let dir = std::env::temp_dir().join(format!("liuagent_loop_repeated_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("重复读取缺失文件");
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            model_call_count.set(model_call_count.get() + 1);
            test_model_result(
                "",
                vec![PlannedLocalTool {
                    tool_call_id: format!("call_missing_{}", model_call_count.get()),
                    name: "read_file".to_string(),
                    arguments: json!({"path": "missing.md"}),
                    summary: "标准模型工具调用：read_file".to_string(),
                }],
            )
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-repeated-test",
            "runtime-chat-loop-repeated-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(!result.ok());
        assert_eq!(result.stopped_reason, "repeated_failure");
        assert_eq!(model_call_count.get(), 2);
        assert_eq!(result.tool_results.len(), 2);
        assert_eq!(result.attempts.len(), 2);
        assert_eq!(
            result.attempts[0].strategy_signature,
            result.attempts[1].strategy_signature
        );
        assert_eq!(
            result.attempts[0].failure_signature,
            result.attempts[1].failure_signature
        );
        assert_eq!(result.error_code(), "agent_loop.repeated_failure");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_ranks_low_risk_verifiable_candidates_first() {
        let dir = std::env::temp_dir().join(format!("liuagent_loop_ranked_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("先检查再删除");
        let first_tool_name = std::cell::RefCell::new(String::new());
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![
                        PlannedLocalTool {
                            tool_call_id: "call_delete".to_string(),
                            name: "delete_file".to_string(),
                            arguments: json!({"path": "README.md"}),
                            summary: "标准模型工具调用：delete_file".to_string(),
                        },
                        PlannedLocalTool {
                            tool_call_id: "call_list".to_string(),
                            name: "list_files".to_string(),
                            arguments: json!({"path": "."}),
                            summary: "标准模型工具调用：list_files".to_string(),
                        },
                    ],
                );
            }
            test_model_result("已先检查目录", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| {
            if first_tool_name.borrow().is_empty() {
                first_tool_name.replace(request.name.clone());
            }
            crate::liuagent_core::types::ToolExecutionResult::ok(
                request.tool_call_id.unwrap_or_else(|| "call".to_string()),
                request.name,
                json!({"checked": true}),
                "ok".to_string(),
            )
        };

        let result = run_agent_loop_with(
            "chat-loop-ranked-test",
            "runtime-chat-loop-ranked-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(first_tool_name.borrow().as_str(), "list_files");
        assert_eq!(result.candidate_solutions.len(), 2);
        assert!(result.candidate_solutions[0].score >= result.candidate_solutions[1].score);
        assert_eq!(result.verification.status, "passed");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_reprompts_when_model_tries_to_finish_after_failed_attempt() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_loop_verify_retry_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("失败后不能直接结束");
        let model_call_count = Cell::new(0);
        let model_runner = |request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_missing".to_string(),
                        name: "read_file".to_string(),
                        arguments: json!({"path": "missing.md"}),
                        summary: "标准模型工具调用：read_file".to_string(),
                    }],
                );
            }
            if index == 1 {
                return test_model_result("我先结束", Vec::new());
            }
            if index > 2 {
                return test_model_result("已换方案完成验证", Vec::new());
            }
            let control_message = request
                .messages
                .iter()
                .rev()
                .find(|message| {
                    message
                        .content
                        .contains("verification_failed_replan_required")
                })
                .map(|message| message.content.as_str())
                .unwrap_or("");
            assert!(control_message.contains("未废弃 strategy_signature"));
            test_model_result(
                "",
                vec![PlannedLocalTool {
                    tool_call_id: "call_list".to_string(),
                    name: "list_files".to_string(),
                    arguments: json!({"path": "."}),
                    summary: "标准模型工具调用：list_files".to_string(),
                }],
            )
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-verify-retry-test",
            "runtime-chat-loop-verify-retry-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(model_call_count.get(), 4);
        assert_eq!(result.stopped_reason, "no_tool_calls");
        assert_eq!(result.verification.status, "passed");
        assert_eq!(result.tool_results.len(), 2);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_pauses_if_failed_attempt_remains_unverified_after_reprompt() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_loop_verify_failed_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("失败后仍然不换方案");
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_missing".to_string(),
                        name: "read_file".to_string(),
                        arguments: json!({"path": "missing.md"}),
                        summary: "标准模型工具调用：read_file".to_string(),
                    }],
                );
            }
            test_model_result("没有其他方案", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-verify-failed-test",
            "runtime-chat-loop-verify-failed-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(!result.ok());
        assert_eq!(model_call_count.get(), 3);
        assert_eq!(result.stopped_reason, "verification_failed");
        assert_eq!(result.error_code(), "agent_loop.verification_failed");
        assert_eq!(result.verification.status, "failed");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_stops_when_permission_is_required() {
        let dir = std::env::temp_dir().join(format!("liuagent_loop_permission_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("写文件");
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            model_call_count.set(model_call_count.get() + 1);
            test_model_result(
                "",
                vec![PlannedLocalTool {
                    tool_call_id: "call_write".to_string(),
                    name: "write_file".to_string(),
                    arguments: json!({"path": "new.txt", "content": "pending"}),
                    summary: "标准模型工具调用：write_file".to_string(),
                }],
            )
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-permission-test",
            "runtime-chat-loop-permission-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(!result.ok());
        assert!(result.awaiting_permission);
        assert_eq!(result.stopped_reason, "waiting_approval");
        assert_eq!(model_call_count.get(), 1);
        assert_eq!(result.tool_results.len(), 1);
        assert_eq!(result.tool_results[0].error_code, "permission.required");
        assert!(!dir.join("new.txt").exists());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_reuses_session_permission_for_same_action() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_loop_session_permission_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("写两个文件");
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![
                        PlannedLocalTool {
                            tool_call_id: "call_write_one".to_string(),
                            name: "write_file".to_string(),
                            arguments: json!({"path": "one.txt", "content": "one"}),
                            summary: "标准模型工具调用：write_file".to_string(),
                        },
                        PlannedLocalTool {
                            tool_call_id: "call_write_two".to_string(),
                            name: "write_file".to_string(),
                            arguments: json!({"path": "two.txt", "content": "two"}),
                            summary: "标准模型工具调用：write_file".to_string(),
                        },
                    ],
                );
            }
            test_model_result("写入完成", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-session-permission-test",
            "runtime-chat-loop-session-permission-test",
            &request,
            &dir,
            Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: Some("perm_call_write_one_file_write".to_string()),
                decision: "approve_session".to_string(),
                grant_scope: Some("session".to_string()),
                comment: None,
            }),
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(result.tool_results.len(), 2);
        assert_eq!(fs::read_to_string(dir.join("one.txt")).unwrap(), "one");
        assert_eq!(fs::read_to_string(dir.join("two.txt")).unwrap(), "two");
        assert!(session_permission_cache_path(&dir, "chat-loop-session-permission-test").exists());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_session_permission_survives_replayed_tool_call_id_change() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_loop_replayed_session_permission_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("reademe.md"), "# 南京嘉华 CRM 系统\n").unwrap();
        let request = test_model_request("删除 reademe.md");
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_replayed_delete".to_string(),
                        name: "delete_file".to_string(),
                        arguments: json!({"path": "reademe.md"}),
                        summary: "标准模型工具调用：delete_file".to_string(),
                    }],
                );
            }
            test_model_result("删除完成", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-replayed-session-permission-test",
            "runtime-chat-loop-replayed-session-permission-test",
            &request,
            &dir,
            Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: Some("perm_call_original_delete_file_delete".to_string()),
                decision: "approve_session".to_string(),
                grant_scope: Some("session".to_string()),
                comment: None,
            }),
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(model_call_count.get(), 2);
        assert_eq!(result.tool_results.len(), 1);
        assert!(
            result.tool_results[0].ok,
            "{}",
            result.tool_results[0].error
        );
        assert!(!dir.join("reademe.md").exists());
        assert!(
            session_permission_cache_path(&dir, "chat-loop-replayed-session-permission-test")
                .exists()
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_approve_once_does_not_survive_replayed_tool_call_id_change() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_loop_replayed_once_permission_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("reademe.md"), "# 南京嘉华 CRM 系统\n").unwrap();
        let request = test_model_request("删除 reademe.md");
        let model_runner = |_request: &ModelStepRequest| {
            test_model_result(
                "",
                vec![PlannedLocalTool {
                    tool_call_id: "call_replayed_delete_once".to_string(),
                    name: "delete_file".to_string(),
                    arguments: json!({"path": "reademe.md"}),
                    summary: "标准模型工具调用：delete_file".to_string(),
                }],
            )
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-replayed-once-permission-test",
            "runtime-chat-loop-replayed-once-permission-test",
            &request,
            &dir,
            Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: Some("perm_call_original_delete_file_delete".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(!result.ok());
        assert!(result.awaiting_permission);
        assert_eq!(result.stopped_reason, "waiting_approval");
        assert_eq!(result.tool_results[0].error_code, "permission.required");
        assert!(dir.join("reademe.md").exists());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_does_not_stop_on_tool_call_count() {
        let dir = std::env::temp_dir().join(format!("liuagent_loop_no_limit_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("README.md"), "hello").unwrap();
        let request = test_model_request("读取 README 后回答");
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index > 0 {
                return test_model_result("已读取 README。", Vec::new());
            }
            test_model_result(
                "",
                vec![PlannedLocalTool {
                    tool_call_id: "call_read".to_string(),
                    name: "read_file".to_string(),
                    arguments: json!({"path": "README.md"}),
                    summary: "标准模型工具调用：read_file".to_string(),
                }],
            )
        };
        let tool_call_count = Cell::new(0);
        let tool_runner = |request: ToolExecutionRequest| {
            tool_call_count.set(tool_call_count.get() + 1);
            execute_tool(request)
        };

        let result = run_agent_loop_with(
            "chat-loop-no-tool-count-limit-test",
            "runtime-chat-loop-no-tool-count-limit-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(result.stopped_reason, "no_tool_calls");
        assert_eq!(tool_call_count.get(), 1);
        assert_eq!(result.tool_results.len(), 1);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_does_not_stop_on_tool_round_count() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_loop_no_round_limit_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("README.md"), "hello").unwrap();
        let request = test_model_request("连续读取 README 后回答");
        let model_call_count = Cell::new(0);
        let model_runner = |request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index >= 13 {
                return test_model_result("已连续读取 README。", Vec::new());
            }
            if index > 0 {
                assert!(
                    request
                        .messages
                        .iter()
                        .any(|message| message.role == "tool" && message.content.contains("hello")),
                    "model call after tool execution must receive the tool observation"
                );
            }
            test_model_result(
                "",
                vec![PlannedLocalTool {
                    tool_call_id: format!("call_read_{index}"),
                    name: "read_file".to_string(),
                    arguments: json!({"path": "README.md"}),
                    summary: "标准模型工具调用：read_file".to_string(),
                }],
            )
        };
        let tool_call_count = Cell::new(0);
        let tool_runner = |request: ToolExecutionRequest| {
            tool_call_count.set(tool_call_count.get() + 1);
            execute_tool(request)
        };

        let result = run_agent_loop_with(
            "chat-loop-no-tool-round-limit-test",
            "runtime-chat-loop-no-tool-round-limit-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(result.stopped_reason, "no_tool_calls");
        assert_eq!(model_call_count.get(), 14);
        assert_eq!(tool_call_count.get(), 13);
        assert_eq!(result.tool_round_count(), 13);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_can_write_after_many_reads() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_loop_many_reads_then_write_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::create_dir_all(dir.join("login")).unwrap();
        fs::create_dir_all(dir.join("dashboard")).unwrap();
        fs::write(dir.join("login/index.html"), "<html>login</html>").unwrap();
        fs::write(dir.join("dashboard/index.html"), "<html>dashboard</html>").unwrap();
        let request = test_model_request("创建登录页");
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![
                        PlannedLocalTool {
                            tool_call_id: "call_read_one".to_string(),
                            name: "read_file".to_string(),
                            arguments: json!({"path": "login/index.html"}),
                            summary: "标准模型工具调用：read_file".to_string(),
                        },
                        PlannedLocalTool {
                            tool_call_id: "call_read_two".to_string(),
                            name: "read_file".to_string(),
                            arguments: json!({"path": "dashboard/index.html"}),
                            summary: "标准模型工具调用：read_file".to_string(),
                        },
                    ],
                );
            }
            if index == 1 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_write_login".to_string(),
                        name: "write_file".to_string(),
                        arguments: json!({
                            "path": "login.html",
                            "content": "<!doctype html><title>Login</title>"
                        }),
                        summary: "标准模型工具调用：write_file".to_string(),
                    }],
                );
            }
            test_model_result("登录页已创建。", Vec::new())
        };
        let write_dir = dir.clone();
        let tool_runner = move |request: ToolExecutionRequest| {
            if request.name == "write_file" {
                let path = request
                    .arguments
                    .get("path")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                let content = request
                    .arguments
                    .get("content")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                fs::write(write_dir.join(path), content).unwrap();
                return crate::liuagent_core::types::ToolExecutionResult::ok(
                    request.tool_call_id.unwrap_or_default(),
                    request.name,
                    json!({"path": path}),
                    format!("写入文件 {path}"),
                );
            }
            execute_tool(request)
        };

        let result = run_agent_loop_with(
            "chat-loop-many-reads-then-write-test",
            "runtime-chat-loop-many-reads-then-write-test",
            &request,
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(result.stopped_reason, "no_tool_calls");
        assert_eq!(result.tool_results.len(), 3);
        assert!(dir.join("login.html").exists());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn local_chat_does_not_delete_from_user_text_without_model_tool_call() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_local_no_text_delete_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let target = dir.join("reademe.md");
        fs::write(&target, "must stay").unwrap();

        let result = start_local_chat(LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-no-text-delete-test".to_string(),
            message_id: Some("msg-user".to_string()),
            assistant_message_id: Some("msg-assistant".to_string()),
            message: "删除文件 path:reademe.md".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: None,
            model_name: None,
            system_prompt: None,
            temperature: None,
            max_tokens: None,
            model_runtime: None,
            permission_decision: None,
            plan_decision: None,
        });

        assert!(result.ok, "{}", result.error);
        assert!(result.tool_results.is_empty());
        assert_ne!(result.error_code, "permission.required");
        assert!(target.exists(), "natural language must not delete files");
        assert_eq!(fs::read_to_string(&target).unwrap(), "must stay");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn direct_model_runtime_requires_local_credentials() {
        let request = LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-test".to_string(),
            message_id: None,
            assistant_message_id: None,
            message: "你好".to_string(),
            workspace_path: ".".to_string(),
            history: Vec::new(),
            provider_id: Some("openai".to_string()),
            model_name: Some("gpt-test".to_string()),
            system_prompt: None,
            temperature: None,
            max_tokens: None,
            model_runtime: Some(LocalModelRuntimeConfig {
                mode: Some("direct-openai-compatible".to_string()),
                provider_id: None,
                model_name: None,
                base_url: Some("https://api.example.com/v1".to_string()),
                api_key: None,
                api_key_env: None,
                gateway_url: None,
                temperature: None,
                max_tokens: None,
                timeout_ms: None,
            }),
            permission_decision: None,
            plan_decision: None,
        };
        let model_request = build_model_request(&request, "你好");
        let result = run_model_step(&model_request);

        assert!(!result.ok);
        assert_eq!(result.mode, "direct-openai-compatible");
        assert_eq!(result.status, "unconfigured");
        assert!(result.summary.contains("apiKey"));
    }

    #[test]
    fn model_timeout_retries_five_attempts_then_fails() {
        let attempts = Cell::new(0usize);

        let result: Result<(), ModelRequestRetryFailure> =
            send_model_request_with_timeout_retry(5, || {
                attempts.set(attempts.get() + 1);
                Err(ModelRequestError {
                    kind: ModelRequestErrorKind::Timeout,
                    message: "operation timed out".to_string(),
                })
            });

        let error = result.expect_err("timeout should fail after max attempts");
        assert_eq!(attempts.get(), 5);
        assert_eq!(error.attempts, 5);
        assert_eq!(error.code, "model.connection_timeout");
        assert!(error.message.contains("已尝试 5 次"));
    }

    #[test]
    fn model_non_timeout_error_does_not_retry() {
        let attempts = Cell::new(0usize);

        let result: Result<(), ModelRequestRetryFailure> =
            send_model_request_with_timeout_retry(5, || {
                attempts.set(attempts.get() + 1);
                Err(ModelRequestError {
                    kind: ModelRequestErrorKind::Request,
                    message: "model gateway returned HTTP 429".to_string(),
                })
            });

        let error = result.expect_err("request error should fail immediately");
        assert_eq!(attempts.get(), 1);
        assert_eq!(error.attempts, 1);
        assert_eq!(error.code, "model.request_failed");
        assert!(error.message.contains("HTTP 429"));
    }

    #[test]
    fn model_failure_assistant_content_does_not_claim_success() {
        let request = test_model_request("创建一个登录页");
        let model_result = ModelStepResult::failed(
            &request,
            "model.request_failed",
            "model gateway returned HTTP 429",
        );
        let content = build_assistant_content(
            "proj-test",
            &PathBuf::from("/tmp/test"),
            "创建一个登录页",
            &[],
            &model_result,
            &[],
            &[],
            false,
            false,
            "model_failed",
            "",
            "model gateway returned HTTP 429",
        );

        assert!(content.starts_with("模型调用失败"));
        assert!(!content.contains("已在桌面端本机走通一轮本地智能体对话"));
        assert!(content.contains("本轮未执行任何本机工具"));
        assert!(content.contains("model.request_failed model gateway returned HTTP 429"));
    }

    #[test]
    fn model_failure_after_tools_reports_executed_tools() {
        let request = test_model_request("创建一个注册页面");
        let model_result = ModelStepResult::failed(
            &request,
            "model.request_failed",
            "model gateway returned HTTP 429",
        );
        let tool_results = vec![crate::liuagent_core::types::ToolExecutionResult::ok(
            "call_read".to_string(),
            "read_file".to_string(),
            json!({"path": "login.html"}),
            "读取 login.html 行 1-200/453".to_string(),
        )];
        let content = build_assistant_content(
            "proj-test",
            &PathBuf::from("/tmp/test"),
            "创建一个注册页面",
            &[],
            &model_result,
            &tool_results,
            &[],
            false,
            false,
            "model_failed",
            "",
            "model gateway returned HTTP 429",
        );

        assert!(content.starts_with("模型调用失败"));
        assert!(content.contains("已执行的本机工具见下方摘要"));
        assert!(content.contains("本机工具执行摘要：共 1 个，成功 1 个，失败 0 个。"));
        assert!(!content.contains("本轮未执行任何本机工具"));
    }

    #[test]
    fn direct_model_runtime_calls_openai_compatible_chat_completions() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(std::time::Duration::from_secs(2)))
                .unwrap();
            let mut request_bytes = Vec::new();
            let mut buffer = [0_u8; 1024];
            let mut expected_len = None;
            loop {
                let read = stream.read(&mut buffer).unwrap();
                request_bytes.extend_from_slice(&buffer[..read]);
                if expected_len.is_none() {
                    let request = String::from_utf8_lossy(&request_bytes);
                    if let Some(header_end) = request.find("\r\n\r\n") {
                        let content_length = request
                            .lines()
                            .find_map(|line| {
                                line.strip_prefix("Content-Length:")
                                    .or_else(|| line.strip_prefix("content-length:"))
                                    .and_then(|value| value.trim().parse::<usize>().ok())
                            })
                            .unwrap_or(0);
                        expected_len = Some(header_end + 4 + content_length);
                    }
                }
                if expected_len.is_some_and(|len| request_bytes.len() >= len) {
                    break;
                }
            }
            let request = String::from_utf8_lossy(&request_bytes);
            assert!(request.starts_with("POST /v1/chat/completions "));
            assert!(request
                .to_ascii_lowercase()
                .contains("authorization: bearer test-key"));
            assert!(request.contains("\"tools\""));
            assert!(request.contains("\"name\":\"read_file\""));

            let body = json!({
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "我会读取 README。",
                            "tool_calls": [
                                {
                                    "id": "call_readme",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": "{\"path\":\"README.md\"}"
                                    }
                                }
                            ]
                        }
                    }
                ]
            })
            .to_string();
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.as_bytes().len(),
                body
            );
            stream.write_all(response.as_bytes()).unwrap();
        });
        let mut model_request = test_model_request("读取 README");
        model_request.base_url = format!("http://{address}");
        model_request.timeout_ms = 5_000;

        let result = run_model_step(&model_request);
        server.join().unwrap();

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.status, "completed");
        assert_eq!(result.content, "我会读取 README。");
        assert_eq!(result.tool_calls.len(), 1);
        assert_eq!(
            result.tool_calls[0].tool_call_id,
            stable_tool_call_id_for_arguments(
                "test-provider",
                "read_file",
                &json!({"path": "README.md"}),
                0
            )
        );
        assert_eq!(result.tool_calls[0].name, "read_file");
        assert_eq!(result.tool_calls[0].arguments["path"], "README.md");
    }

    fn test_model_request(user_message: &str) -> ModelStepRequest {
        ModelStepRequest {
            mode: "direct-openai-compatible".to_string(),
            provider_id: "test-provider".to_string(),
            model_name: "test-model".to_string(),
            base_url: "https://example.com/v1".to_string(),
            api_key: "test-key".to_string(),
            gateway_url: String::new(),
            temperature: 0.2,
            max_tokens: 1024,
            timeout_ms: 1_000,
            messages: vec![RuntimeModelMessage::simple(
                "user",
                user_message.to_string(),
            )],
        }
    }

    fn test_model_result(content: &str, tool_calls: Vec<PlannedLocalTool>) -> ModelStepResult {
        ModelStepResult {
            ok: true,
            mode: "direct-openai-compatible".to_string(),
            provider_id: "test-provider".to_string(),
            model_name: "test-model".to_string(),
            status: "completed".to_string(),
            content: content.to_string(),
            tool_calls,
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: "test model result".to_string(),
            error_code: String::new(),
            error: String::new(),
        }
    }

    #[test]
    fn plan_required_returned_for_implementation_request_without_decision() {
        let dir = std::env::temp_dir()
            .join(format!("liuagent_plan_required_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();

        let result = start_local_chat(LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-plan-test".to_string(),
            message_id: None,
            assistant_message_id: None,
            message: "实现规划机制模块".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: None,
            model_name: None,
            system_prompt: None,
            temperature: None,
            max_tokens: None,
            model_runtime: None,
            permission_decision: None,
            plan_decision: None,
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.plan_status, "plan_required");
        assert!(result.tool_results.is_empty());
        assert!(result.error_code.is_empty());
        assert!(PathBuf::from(&result.requirement_record_path).exists());
        let req = serde_json::from_str::<Value>(
            &fs::read_to_string(&result.requirement_record_path).unwrap(),
        ).unwrap();
        assert_eq!(req["plan_status"], "plan_required");
        assert_eq!(req["task_tree"]["nodes"].as_array().unwrap().len(), 4);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn query_request_bypasses_planning_gate() {
        let dir = std::env::temp_dir()
            .join(format!("liuagent_plan_bypass_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();

        let result = start_local_chat(LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-bypass-test".to_string(),
            message_id: None,
            assistant_message_id: None,
            message: "查看当前工作区".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: None,
            model_name: None,
            system_prompt: None,
            temperature: None,
            max_tokens: None,
            model_runtime: None,
            permission_decision: None,
            plan_decision: None,
        });

        // Query型: 规划门不触发，走正常 agent loop (mock)
        assert!(result.ok, "{}", result.error);
        assert_ne!(result.plan_status, "plan_required");
        let _ = fs::remove_dir_all(dir);
    }
}
