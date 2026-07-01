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
use std::cell::{Cell, RefCell};
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;
use std::time::{SystemTime, UNIX_EPOCH};

use super::adapters::protocol::{
    approval_required_event, command_finished_event, command_output_chunk_event,
    command_started_event, model_call_started_event, model_step_event, progress_update_event,
    tool_call_started_event, tool_result_event,
};
use super::audit::build_tool_audit_logs;
use super::definitions::builtin_tool_definitions;
use super::permission::{
    cached_session_grant_comment, is_full_access_decision, permission_request_id,
};
use super::planning;
use super::state::recover_runtime_session;
use super::state::{
    append_runtime_event, cleanup_synced_offline_cache, delete_runtime_outbox_entries,
    list_runtime_events as read_runtime_events, list_runtime_outbox as read_runtime_outbox,
    load_offline_cache_record, recover_runtime_state, save_offline_cache_record,
    write_runtime_artifacts, RuntimeArtifactPaths, RuntimePersistenceInput,
};
use super::tools::command::classify_command_risk;
use super::types::{
    AgentInvocationRequest, AgentInvocationResult, AgentRunAttachmentRoute,
    AgentRunAttachmentSummary, AgentRunContext, AgentRunHistoryContext,
    AgentRunHistoryMessageSummary, AgentRunProjectContext, AgentRunRuntimeContext,
    AgentRunUserRequest, ClarityAssessment, LocalBackendContext, LocalChatAttachment,
    LocalChatMessage, LocalChatRequest, LocalChatResult, LocalModelRuntimeConfig,
    LocalRuntimeEventsRequest, LocalRuntimeEventsResult, LocalRuntimeJobRequest,
    LocalRuntimeJobResult, LocalRuntimeOutboxAckRequest, LocalRuntimeOutboxRequest,
    LocalRuntimeOutboxResult, LocalRuntimeRecoveryRequest, LocalRuntimeRecoveryResult,
    MemoryWritePlan, MemoryWritePlanItem, ModelCompatibilityProfile, Observation,
    OfflineCacheCleanupRequest, OfflineCacheLoadRequest, OfflineCacheResult,
    OfflineCacheSaveRequest, PlanNode, PlanState, PromptStack, PromptStackItem,
    ProviderFileUploadRequest, ProviderFileUploadResult, RetryDecision, RunState,
    RuntimeSchedulerState, TaskGoal, ToolBatchState, ToolError, ToolExecutionRequest,
    VerificationCheck, VerificationReport,
};
use super::workspace::resolve_workspace_root;
use super::workspace::{resolve_workspace_child, workspace_relative_path};
use super::{
    execute_tool, execute_tool_with_command_output_sink, normalized_tool_call_id,
    prepare_agent_invocation,
};

const REQUIREMENT_SCHEMA_VERSION: u32 = 1;
const DEFAULT_MODEL_TIMEOUT_MS: u64 = 120_000;
const DEFAULT_MAX_VERIFICATION_REPROMPTS: usize = 1;
const MODEL_CONNECTION_TIMEOUT_MAX_ATTEMPTS: usize = 5;
const PERMISSION_CACHE_VERSION: u32 = 1;
const TOOL_OBSERVATION_TEXT_PREVIEW_CHARS: usize = 6_000;
const TOOL_OBSERVATION_MATCH_PREVIEW_CHARS: usize = 500;
const TOOL_OBSERVATION_MAX_ARRAY_ITEMS: usize = 80;

#[cfg(test)]
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

pub fn refresh_local_runtime_job(request: LocalRuntimeJobRequest) -> LocalRuntimeJobResult {
    match refresh_local_runtime_job_inner(&request) {
        Ok(job) => LocalRuntimeJobResult::ok(
            request.workspace_path.clone(),
            job,
            "refreshed local runtime background job".to_string(),
        ),
        Err(error) => LocalRuntimeJobResult::failed(request, error),
    }
}

pub fn cancel_local_runtime_job(request: LocalRuntimeJobRequest) -> LocalRuntimeJobResult {
    match cancel_local_runtime_job_inner(&request) {
        Ok(job) => LocalRuntimeJobResult::ok(
            request.workspace_path.clone(),
            job,
            "cancelled local runtime background job".to_string(),
        ),
        Err(error) => LocalRuntimeJobResult::failed(request, error),
    }
}

pub fn upload_provider_file(request: ProviderFileUploadRequest) -> ProviderFileUploadResult {
    match upload_provider_file_inner(&request) {
        Ok(result) => result,
        Err(error) => ProviderFileUploadResult::failed(request, error),
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

pub fn save_local_offline_cache(request: OfflineCacheSaveRequest) -> OfflineCacheResult {
    let workspace_path = request.workspace_path.clone();
    match save_local_offline_cache_inner(&request) {
        Ok(result) => OfflineCacheResult::ok(workspace_path, result),
        Err(error) => OfflineCacheResult::failed(workspace_path, error),
    }
}

pub fn load_local_offline_cache(request: OfflineCacheLoadRequest) -> OfflineCacheResult {
    let workspace_path = request.workspace_path.clone();
    match load_local_offline_cache_inner(&request) {
        Ok(result) => OfflineCacheResult::ok(workspace_path, result),
        Err(error) => OfflineCacheResult::failed(workspace_path, error),
    }
}

pub fn cleanup_local_offline_cache(request: OfflineCacheCleanupRequest) -> OfflineCacheResult {
    let workspace_path = request.workspace_path.clone();
    match cleanup_local_offline_cache_inner(&request) {
        Ok(result) => OfflineCacheResult::ok(workspace_path, result),
        Err(error) => OfflineCacheResult::failed(workspace_path, error),
    }
}

fn recover_local_runtime_state_inner(
    request: &LocalRuntimeRecoveryRequest,
) -> Result<LocalRuntimeRecoveryResult, ToolError> {
    let project_id = required_non_empty(&request.project_id, "projectId")?;
    let chat_session_id = required_non_empty(&request.chat_session_id, "chatSessionId")?;
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    let (mut state, runtime_events) =
        recover_runtime_session(&workspace_root, &project_id, &chat_session_id)?;
    let background_jobs = collect_runtime_background_jobs(&state);
    let resume_judgement = build_resume_judgement(&state, &background_jobs);
    if let Some(object) = state.as_object_mut() {
        object.insert("background_jobs".to_string(), background_jobs.clone());
        object.insert("resume_judgement".to_string(), resume_judgement);
    }
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

fn collect_runtime_background_jobs(state: &Value) -> Value {
    let mut jobs = Vec::new();
    let tool_results = state
        .get("tool_results")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    for result in tool_results {
        let Some(job) = result
            .get("content")
            .and_then(|content| content.get("background_job"))
        else {
            continue;
        };
        let state_path = job
            .get("state_path")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim();
        let mut refreshed = job.clone();
        if !state_path.is_empty() {
            if let Ok(raw) = fs::read_to_string(state_path) {
                if let Ok(value) = serde_json::from_str::<Value>(&raw) {
                    refreshed = value;
                }
            }
        }
        jobs.push(refreshed);
    }
    Value::Array(jobs)
}

fn refresh_local_runtime_job_inner(request: &LocalRuntimeJobRequest) -> Result<Value, ToolError> {
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    read_command_job_state_for_workspace(&workspace_root, &request.state_path)
}

fn cancel_local_runtime_job_inner(request: &LocalRuntimeJobRequest) -> Result<Value, ToolError> {
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    let state_path = resolve_command_job_state_path(&workspace_root, &request.state_path)?;
    let mut job = read_command_job_state_path(&state_path)?;
    let status = job
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if ["succeeded", "failed", "cancelled"].contains(&status.as_str()) {
        return Ok(job);
    }
    let pid = job.get("pid").and_then(Value::as_u64).unwrap_or(0);
    if pid == 0 || pid > i32::MAX as u64 {
        return Err(ToolError::new(
            "runtime_job.invalid_pid",
            "background job does not contain a valid pid",
        ));
    }
    cancel_process(pid as i32)?;
    if let Some(object) = job.as_object_mut() {
        object.insert("status".to_string(), json!("cancelled"));
        object.insert("cancelled_at_epoch_ms".to_string(), json!(epoch_millis()));
        object.insert("updated_at_epoch_ms".to_string(), json!(epoch_millis()));
    }
    fs::write(
        &state_path,
        serde_json::to_vec_pretty(&job).map_err(|err| {
            ToolError::new(
                "runtime_job.serialize_failed",
                format!("serialize background job state failed: {err}"),
            )
        })?,
    )
    .map_err(|err| {
        ToolError::new(
            "runtime_job.write_failed",
            format!("write background job state failed: {err}"),
        )
    })?;
    Ok(job)
}

fn read_command_job_state_for_workspace(
    workspace_root: &Path,
    state_path: &str,
) -> Result<Value, ToolError> {
    let state_path = resolve_command_job_state_path(workspace_root, state_path)?;
    read_command_job_state_path(&state_path)
}

fn read_command_job_state_path(state_path: &Path) -> Result<Value, ToolError> {
    let raw = fs::read_to_string(state_path).map_err(|err| {
        ToolError::new(
            "runtime_job.read_failed",
            format!("read background job state failed: {err}"),
        )
    })?;
    serde_json::from_str::<Value>(&raw).map_err(|err| {
        ToolError::new(
            "runtime_job.parse_failed",
            format!("parse background job state failed: {err}"),
        )
    })
}

fn resolve_command_job_state_path(
    workspace_root: &Path,
    raw_state_path: &str,
) -> Result<PathBuf, ToolError> {
    let raw_state_path = raw_state_path.trim();
    if raw_state_path.is_empty() {
        return Err(ToolError::new(
            "runtime_job.state_path_required",
            "background job state_path is required",
        ));
    }
    let path = PathBuf::from(raw_state_path);
    let absolute = if path.is_absolute() {
        path
    } else {
        workspace_root.join(path)
    };
    let canonical_workspace = workspace_root.canonicalize().map_err(|err| {
        ToolError::new(
            "workspace.invalid",
            format!("canonicalize workspace failed: {err}"),
        )
    })?;
    let parent = absolute.parent().ok_or_else(|| {
        ToolError::new(
            "runtime_job.invalid_state_path",
            "background job state_path has no parent directory",
        )
    })?;
    let canonical_parent = parent.canonicalize().map_err(|err| {
        ToolError::new(
            "runtime_job.invalid_state_path",
            format!("canonicalize background job path failed: {err}"),
        )
    })?;
    let allowed_root = canonical_workspace
        .join(".ai-employee")
        .join("liuagent-command-jobs");
    if !canonical_parent.starts_with(&allowed_root) {
        return Err(ToolError::new(
            "runtime_job.out_of_scope",
            "background job state_path is outside the workspace job directory",
        ));
    }
    Ok(absolute)
}

#[cfg(unix)]
fn cancel_process(pid: i32) -> Result<(), ToolError> {
    let group_status = Command::new("kill")
        .arg("-TERM")
        .arg("--")
        .arg(format!("-{pid}"))
        .stderr(Stdio::null())
        .status()
        .map_err(|err| {
            ToolError::new(
                "runtime_job.cancel_failed",
                format!("send terminate signal failed: {err}"),
            )
        })?;
    if group_status.success() {
        Ok(())
    } else {
        let pid_status = Command::new("kill")
            .arg("-TERM")
            .arg(pid.to_string())
            .stderr(Stdio::null())
            .status()
            .map_err(|err| {
                ToolError::new(
                    "runtime_job.cancel_failed",
                    format!("send terminate signal failed: {err}"),
                )
            })?;
        if pid_status.success() {
            Ok(())
        } else {
            Err(ToolError::new(
                "runtime_job.cancel_failed",
                format!("kill exited with status {group_status}; fallback exited with status {pid_status}"),
            ))
        }
    }
}

#[cfg(not(unix))]
fn cancel_process(_pid: i32) -> Result<(), ToolError> {
    Err(ToolError::new(
        "runtime_job.cancel_unsupported",
        "background job cancel is not supported on this platform",
    ))
}

fn build_resume_judgement(state: &Value, background_jobs: &Value) -> Value {
    let jobs = background_jobs.as_array().cloned().unwrap_or_default();
    let has_running = jobs.iter().any(|job| {
        job.get("status")
            .and_then(Value::as_str)
            .map(|status| status == "running")
            .unwrap_or(false)
    });
    let has_succeeded = jobs.iter().any(|job| {
        job.get("status")
            .and_then(Value::as_str)
            .map(|status| status == "succeeded")
            .unwrap_or(false)
    });
    let has_failed = jobs.iter().any(|job| {
        job.get("status")
            .and_then(Value::as_str)
            .map(|status| status == "failed")
            .unwrap_or(false)
    });
    let status = state["current_state"]["verification_report"]["overall_status"]
        .as_str()
        .or_else(|| state["current_state"]["verification_report"]["status"].as_str())
        .unwrap_or("");
    let decision = if has_running {
        "continue_waiting"
    } else if has_succeeded {
        "ask_ai_to_verify_completion"
    } else if has_failed {
        "ask_ai_to_inspect_failure"
    } else if status == "no_signal" {
        "ask_ai_to_judge"
    } else {
        "none"
    };
    json!({
        "version": "resume-judgement/v1",
        "decision": decision,
        "background_job_count": jobs.len(),
        "has_running_job": has_running,
        "has_succeeded_job": has_succeeded,
        "has_failed_job": has_failed,
        "next_actions": match decision {
            "continue_waiting" => vec!["refresh_job_status", "continue_waiting", "cancel_job"],
            "ask_ai_to_verify_completion" => vec!["read_job_logs", "verify_goal", "continue_agent_loop"],
            "ask_ai_to_inspect_failure" => vec!["read_job_logs", "diagnose_failure", "propose_retry_or_fix"],
            "ask_ai_to_judge" => vec!["inspect_runtime_state", "read_latest_events", "decide_next_step"],
            _ => Vec::<&str>::new(),
        }
    })
}

fn save_local_offline_cache_inner(request: &OfflineCacheSaveRequest) -> Result<Value, ToolError> {
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    save_offline_cache_record(
        &workspace_root,
        &request.cache_kind,
        request.project_id.as_deref(),
        request.chat_session_id.as_deref(),
        request.provider_id.as_deref(),
        request.payload.clone(),
    )
}

fn load_local_offline_cache_inner(request: &OfflineCacheLoadRequest) -> Result<Value, ToolError> {
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    load_offline_cache_record(
        &workspace_root,
        &request.cache_kind,
        request.project_id.as_deref(),
        request.chat_session_id.as_deref(),
        request.provider_id.as_deref(),
    )
}

fn cleanup_local_offline_cache_inner(
    request: &OfflineCacheCleanupRequest,
) -> Result<Value, ToolError> {
    let project_id = required_non_empty(&request.project_id, "projectId")?;
    let chat_session_id = required_non_empty(&request.chat_session_id, "chatSessionId")?;
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    cleanup_synced_offline_cache(
        &workspace_root,
        &project_id,
        &chat_session_id,
        &request.event_ids,
        request.server_refs.clone(),
    )
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

    let gateway_result = prepare_local_chat_invocation(&request, &user_message)?;
    let user_message_id = normalized_id(request.message_id.as_deref(), "local_user");
    let assistant_message_id =
        normalized_id(request.assistant_message_id.as_deref(), "local_assistant");
    let mut model_request = build_model_request(&request, &user_message);
    let task_goal = build_task_goal(&session_id, &user_message, &model_request);
    let initial_task_tree = planning::TaskTree::for_goal(&session_id, &task_goal);
    model_request.task_goal = Some(task_goal.clone());
    model_request.task_tree = Some(initial_task_tree);
    let prompt_stack = resolve_prompt_stack(&request, &model_request);
    let clarity_assessment = assess_clarity(&user_message, &request, &model_request);
    let plan_created_at = epoch_millis();
    let agent_run_context = build_agent_run_context(
        &project_id,
        &chat_session_id,
        &session_id,
        &workspace_root,
        &request,
        &user_message,
        &model_request,
        &prompt_stack,
    );
    let collected_runtime_events = RefCell::new(Vec::<Value>::new());
    let collecting_event_sink = |event: Value| {
        collected_runtime_events.borrow_mut().push(event.clone());
        let _ = append_runtime_event(&workspace_root, &project_id, &chat_session_id, &event);
        if let Some(sink) = event_sink {
            sink(event);
        }
    };
    let runtime_event_sink: Option<&dyn Fn(Value)> = Some(&collecting_event_sink);
    let plan_confirmation_request_id =
        plan_confirmation_request_id(&chat_session_id, &user_message_id);
    let replayed_permission_tool = replay_pending_permission_tool_if_available(
        &workspace_root,
        &project_id,
        &chat_session_id,
        &session_id,
        &request,
        runtime_event_sink,
    );
    if let Some(replayed) = replayed_permission_tool.as_ref() {
        let mut messages = model_request.messages.clone();
        messages.push(RuntimeModelMessage::assistant_tool_call(
            "用户已授权，继续执行之前等待授权的本地工具。",
            replayed.reasoning_content.clone(),
            vec![replayed.tool.clone()],
        ));
        let attempt = build_agent_loop_attempt(&replayed.tool, &replayed.result, 1);
        messages.push(RuntimeModelMessage::tool_observation(
            replayed.result.tool_call_id.clone(),
            tool_observation_content(&replayed.result, false, Some(&attempt)),
        ));
        model_request = model_request.with_messages(messages);
    }
    let mut agent_loop = if clarity_assessment.requires_confirmation
        && !has_plan_confirmation(&request, &plan_confirmation_request_id)
        && replayed_permission_tool.is_none()
    {
        build_plan_confirmation_agent_loop(
            &session_id,
            &chat_session_id,
            &plan_confirmation_request_id,
            &user_message,
            &clarity_assessment,
            runtime_event_sink,
        )
    } else {
        run_agent_loop(
            &chat_session_id,
            &session_id,
            &model_request,
            &prompt_stack,
            &workspace_root,
            request.permission_decision.clone(),
            runtime_event_sink,
        )
    };
    if let Some(replayed) = replayed_permission_tool {
        agent_loop.planned_tools.insert(0, replayed.tool);
        agent_loop.tool_results.insert(0, replayed.result);
    }
    let model_result = agent_loop.final_model_result();
    let planned_tools = agent_loop.planned_tools.clone();
    let tool_results = agent_loop.tool_results.clone();
    let awaiting_permission = agent_loop.awaiting_permission;
    let run_ok = agent_loop.ok();

    let response_format = format_local_chat_response(
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
    let assistant_content = response_format.assistant_content.clone();
    let operations = build_operations(&session_id, &agent_loop);
    let run_status = if awaiting_permission {
        "waiting_approval"
    } else if run_ok {
        "completed"
    } else {
        "failed"
    };
    let waiting_for = if awaiting_permission {
        if agent_loop.stopped_reason == "waiting_plan_confirmation" {
            Some("plan_confirmation")
        } else {
            Some("approval")
        }
    } else {
        None
    };
    let audit_logs = build_tool_audit_logs(
        &session_id,
        &tool_results,
        request.permission_decision.as_ref(),
        epoch_millis(),
    );
    let verification_report = build_verification_report(
        run_status,
        waiting_for,
        &agent_loop,
        &planned_tools,
        &tool_results,
        &task_goal,
    );
    let scheduler_state = build_runtime_scheduler_state(
        run_status,
        waiting_for,
        &agent_loop,
        &planned_tools,
        &tool_results,
    );
    let dynamic_task_tree = planning::TaskTree::finalize_for_goal(
        &session_id,
        &task_goal,
        agent_loop.stopped_reason.as_str(),
        awaiting_permission,
        run_ok,
    );
    let plan_state = create_plan_state(
        &session_id,
        &task_goal,
        &clarity_assessment,
        run_status,
        plan_created_at,
        Some(&agent_loop),
        &dynamic_task_tree,
    );
    let observations = build_observations(
        &session_id,
        &model_result,
        &tool_results,
        run_status,
        waiting_for,
        agent_loop.stopped_reason.as_str(),
        agent_loop.summary().as_str(),
        agent_loop.error_code().as_str(),
    );
    let conversation_lifecycle = build_conversation_lifecycle(
        &session_id,
        &chat_session_id,
        &user_message_id,
        &assistant_message_id,
        &user_message,
        run_status,
        waiting_for,
        &model_request,
        &agent_loop,
        &tool_results,
        &assistant_content,
    );
    let retry_decision = route_failure(
        &session_id,
        run_status,
        waiting_for,
        &agent_loop,
        &tool_results,
        &model_result,
    );
    let memory_write_plan = classify_memory_writes(
        &project_id,
        &chat_session_id,
        &session_id,
        &user_message,
        run_status,
        waiting_for,
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
        agent_run_context: serde_json::to_value(&agent_run_context).unwrap_or_else(|_| json!({})),
        observations: serde_json::to_value(&observations).unwrap_or_else(|_| json!([])),
        scheduler_state: serde_json::to_value(&scheduler_state).unwrap_or_else(|_| json!({})),
        verification_report: serde_json::to_value(&verification_report)
            .unwrap_or_else(|_| json!({})),
        task_goal: serde_json::to_value(&task_goal).unwrap_or_else(|_| json!({})),
        clarity_assessment: serde_json::to_value(&clarity_assessment).unwrap_or_else(|_| json!({})),
        plan_state: serde_json::to_value(&plan_state).unwrap_or_else(|_| json!({})),
        retry_decision: serde_json::to_value(&retry_decision).unwrap_or_else(|_| json!({})),
        memory_write_plan: serde_json::to_value(&memory_write_plan).unwrap_or_else(|_| json!({})),
        tool_results: &tool_results,
        operations: operations.clone(),
        audit_logs: &audit_logs,
    })?;
    let runtime_events = merge_runtime_events(
        collected_runtime_events.borrow().as_slice(),
        runtime_artifacts.runtime_events.as_slice(),
    );
    let requirement_path = requirement_record_path(&workspace_root, &project_id, &chat_session_id);
    let requirement_record = build_local_chat_requirement_record(
        &project_id,
        &chat_session_id,
        &session_id,
        &workspace_root,
        &user_message,
        &user_message_id,
        &assistant_message_id,
        run_status,
        waiting_for,
        awaiting_permission,
        run_ok,
        &model_request,
        &model_result,
        &agent_loop,
        &planned_tools,
        &tool_results,
        &agent_run_context,
        &observations,
        &scheduler_state,
        &verification_report,
        &task_goal,
        &clarity_assessment,
        &plan_state,
        &retry_decision,
        &memory_write_plan,
        operations.clone(),
        &gateway_result,
        runtime_artifacts.clone(),
        &dynamic_task_tree,
        &audit_logs,
        &assistant_content,
        conversation_lifecycle.clone(),
    );
    write_requirement_record(&requirement_path, requirement_record)?;

    let result_error_code = if waiting_for == Some("plan_confirmation") {
        "planning.confirmation_required".to_string()
    } else if awaiting_permission {
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
    let result_summary = if waiting_for == Some("plan_confirmation") {
        "桌面端本地对话等待用户确认执行计划".to_string()
    } else if awaiting_permission {
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
        assistant_reasoning_content: model_result.reasoning_content,
        model_result: agent_loop.audit_value(),
        tool_results,
        operations,
        runtime_events,
        conversation_lifecycle,
        summary: result_summary,
        user_visible_error_summary: response_format.user_visible_error_summary,
        diagnostic: response_format.diagnostic,
        error_code: result_error_code,
        error: result_error,
    })
}

fn build_runtime_blockers(
    session_id: &str,
    stopped_reason: &str,
    awaiting_permission: bool,
    planned_tools: &[PlannedLocalTool],
) -> Value {
    if awaiting_permission {
        let tool_name = planned_tools.last().map(|t| t.name.as_str()).unwrap_or(
            if stopped_reason == "waiting_plan_confirmation" {
                "planning_gate"
            } else {
                "unknown"
            },
        );
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

fn build_local_chat_requirement_record(
    project_id: &str,
    chat_session_id: &str,
    session_id: &str,
    workspace_root: &PathBuf,
    user_message: &str,
    user_message_id: &str,
    assistant_message_id: &str,
    run_status: &str,
    waiting_for: Option<&str>,
    awaiting_permission: bool,
    _run_ok: bool,
    model_request: &ModelStepRequest,
    model_result: &ModelStepResult,
    agent_loop: &AgentLoopResult,
    planned_tools: &[PlannedLocalTool],
    tool_results: &[super::types::ToolExecutionResult],
    agent_run_context: &AgentRunContext,
    observations: &[Observation],
    scheduler_state: &RuntimeSchedulerState,
    verification_report: &VerificationReport,
    task_goal: &TaskGoal,
    clarity_assessment: &ClarityAssessment,
    plan_state: &PlanState,
    retry_decision: &RetryDecision,
    memory_write_plan: &MemoryWritePlan,
    operations: Value,
    gateway_result: &AgentInvocationResult,
    runtime_artifacts: RuntimeArtifactPaths,
    dynamic_task_tree: &planning::TaskTree,
    audit_logs: &[Value],
    assistant_content: &str,
    conversation_lifecycle: Value,
) -> Value {
    let intent_analysis = build_requirement_intent_analysis(user_message, &model_request.messages);
    let related_context = build_requirement_related_context(
        project_id,
        chat_session_id,
        workspace_root,
        &intent_analysis,
        gateway_result,
    );
    let contextual_plan = build_requirement_contextual_plan(
        user_message,
        &intent_analysis,
        &related_context,
        planned_tools,
        awaiting_permission,
    );
    let mut model_input_snapshots = vec![build_requirement_understanding_snapshot(
        session_id,
        user_message_id,
        user_message,
        &intent_analysis,
        &related_context,
        task_goal,
    )];
    model_input_snapshots.extend(agent_loop.model_input_snapshots.clone());
    let actions_taken =
        build_requirement_actions_taken(agent_loop, planned_tools, tool_results, model_result);
    let current_state_delta = build_requirement_current_state_delta(
        run_status,
        waiting_for,
        agent_loop,
        planned_tools,
        tool_results,
        agent_run_context,
        observations,
        scheduler_state,
        verification_report,
        task_goal,
        clarity_assessment,
        plan_state,
        retry_decision,
        memory_write_plan,
        &runtime_artifacts,
        dynamic_task_tree,
    );
    let current_state = build_requirement_current_state(
        user_message,
        run_status,
        waiting_for,
        &current_state_delta,
        &runtime_artifacts,
    );
    let related_context_count = related_context
        .get("items")
        .and_then(Value::as_array)
        .map(Vec::len)
        .unwrap_or(0);
    let mut record = serde_json::Map::new();
    record.insert(
        "record_type".to_string(),
        json!("desktop-local-agent-requirement"),
    );
    record.insert("version".to_string(), json!(REQUIREMENT_SCHEMA_VERSION));
    record.insert(
        "id".to_string(),
        json!(format!("req_{}", sanitize_path_segment(chat_session_id))),
    );
    record.insert("name".to_string(), json!(truncate_inline(user_message, 80)));
    record.insert(
        "description".to_string(),
        intent_analysis["current_request_summary"].clone(),
    );
    record.insert(
        "tags".to_string(),
        json!(["requirement", "context", "task-tree", "desktop-local-agent"]),
    );
    record.insert("storage_scope".to_string(), json!("desktop-workspace"));
    record.insert("storage_mode".to_string(), json!("local-first"));
    record.insert("gateway_protocol".to_string(), json!("Agent Gateway"));
    record.insert("project_id".to_string(), json!(project_id));
    record.insert("chat_session_id".to_string(), json!(chat_session_id));
    record.insert("session_id".to_string(), json!(session_id));
    record.insert(
        "workspace_path".to_string(),
        json!(workspace_root.to_string_lossy()),
    );
    record.insert("title".to_string(), json!(user_message));
    record.insert("root_goal".to_string(), json!(user_message));
    record.insert("task_goal".to_string(), json!(task_goal));
    record.insert("original_request".to_string(), json!(user_message));
    record.insert("intent_analysis".to_string(), intent_analysis.clone());
    record.insert("related_context".to_string(), related_context.clone());
    record.insert("contextual_plan".to_string(), contextual_plan);
    record.insert(
        "model_input_snapshots".to_string(),
        json!(model_input_snapshots),
    );
    record.insert("actions_taken".to_string(), actions_taken);
    record.insert("clarity_assessment".to_string(), json!(clarity_assessment));
    record.insert("plan_state".to_string(), json!(plan_state));
    record.insert("retry_decision".to_string(), json!(retry_decision));
    record.insert("memory_write_plan".to_string(), json!(memory_write_plan));
    record.insert("current_state_delta".to_string(), current_state_delta);
    record.insert("current_state".to_string(), current_state);
    record.insert("latest_status".to_string(), json!(run_status));
    record.insert("phase".to_string(), json!("local_chat"));
    record.insert(
        "step".to_string(),
        json!(if awaiting_permission {
            "waiting_tool_permission"
        } else if !planned_tools.is_empty() {
            "model_and_tool_execution"
        } else {
            "model_execution"
        }),
    );
    record.insert(
        "workflow_skill".to_string(),
        json!({
            "id": "liuagent-cli",
            "source": "docs/liuAgent-cli",
            "runtime": "tauri"
        }),
    );
    record.insert(
        "agent_gateway".to_string(),
        json!({
            "invocation": gateway_result.invocation.clone(),
            "requirement_session": gateway_result.requirement_session.clone(),
            "project_context_bundle": gateway_result.project_context_bundle.clone(),
            "prompt_bundle": gateway_result.prompt_bundle.clone(),
            "tool_manifest_bundle": gateway_result.tool_manifest_bundle.clone(),
            "agent_runtime_session": gateway_result.agent_runtime_session.clone()
        }),
    );
    record.insert("runtime_state".to_string(), json!(runtime_artifacts));
    record.insert(
        "task_lifecycle".to_string(),
        json!({
            "status": run_status,
            "waiting_for": waiting_for,
            "stopped_reason": agent_loop.stopped_reason.as_str(),
            "candidate_solutions": &agent_loop.candidate_solutions,
            "attempts": &agent_loop.attempts,
            "verification": &agent_loop.verification
        }),
    );
    record.insert("task_tree".to_string(), json!(dynamic_task_tree));
    record.insert(
        "blockers".to_string(),
        build_runtime_blockers(
            session_id,
            agent_loop.stopped_reason.as_str(),
            awaiting_permission,
            planned_tools,
        ),
    );
    record.insert(
        "current_task_node".to_string(),
        json!(current_task_node_value(dynamic_task_tree)),
    );
    record.insert(
        "task_branches".to_string(),
        json!(task_branch_values(dynamic_task_tree)),
    );
    record.insert(
        "history".to_string(),
        json!([
            {
                "event": "user_message",
                "message_id": user_message_id,
                "content": user_message,
                "created_at_epoch_ms": epoch_millis()
            },
            {
                "event": "requirement_understanding",
                "intent_analysis": intent_analysis,
                "related_context_count": related_context_count,
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
        ]),
    );
    record.insert("model_runtime".to_string(), agent_loop.audit_value());
    record.insert("tool_results".to_string(), json!(tool_results));
    record.insert("operations".to_string(), operations);
    record.insert("conversation_lifecycle".to_string(), conversation_lifecycle);
    record.insert("audit_logs".to_string(), json!(audit_logs));
    record.insert("sync_status".to_string(), json!("local_only"));
    record.insert("updated_at_epoch_ms".to_string(), json!(epoch_millis()));
    Value::Object(record)
}

fn build_requirement_intent_analysis(
    user_message: &str,
    model_messages: &[RuntimeModelMessage],
) -> Value {
    let targets = extract_file_path_candidates(user_message);
    let target_object = targets
        .last()
        .cloned()
        .or_else(|| infer_recent_target_path(model_messages))
        .unwrap_or_else(|| "current user request".to_string());
    let keywords = requirement_keywords(user_message);
    json!({
        "current_request_summary": truncate_inline(user_message, 160),
        "current_request_understanding": {
            "target_object": target_object,
            "target_capability": infer_requirement_capability(user_message),
            "keywords": keywords,
            "constraints": infer_requirement_constraints(user_message),
            "context_lookup": build_context_lookup(user_message, &targets)
        },
        "focus": infer_requirement_focus(user_message),
        "task_type": infer_requirement_task_type(user_message),
        "relationship": "related",
        "related_objects": targets,
        "context_strategy": "continue_chain",
        "context_queries": requirement_keywords(user_message),
        "context_include": [
            "current_state",
            "recent_requirement_summary",
            "project_context_bundle",
            "tool_manifest_bundle"
        ],
        "needs_user_confirmation": false,
        "reason": "本地桌面智能体按 chat_session_id 续写同一需求链；无关需求由上层入口创建新的 chat_session_id。"
    })
}

fn build_requirement_related_context(
    project_id: &str,
    chat_session_id: &str,
    workspace_root: &PathBuf,
    intent_analysis: &Value,
    gateway_result: &AgentInvocationResult,
) -> Value {
    json!({
        "strategy": intent_analysis["context_strategy"].clone(),
        "items": [
            {
                "source": "local_current_state",
                "relationship": "related",
                "reason": "同一 chat_session_id 下的本地 requirement、runtime state 和 task tree 是当前会话连续执行的权威来源。",
                "project_id": project_id,
                "chat_session_id": chat_session_id,
                "workspace_path": workspace_root.to_string_lossy()
            },
            {
                "source": "agent_gateway.project_context_bundle",
                "relationship": "related",
                "reason": "Agent Gateway 为本轮运行绑定项目上下文。",
                "summary": gateway_result.project_context_bundle.clone()
            },
            {
                "source": "agent_gateway.tool_manifest_bundle",
                "relationship": "related",
                "reason": "任务处理循环只能使用该工具包中暴露的桌面本地工具。",
                "summary": gateway_result.tool_manifest_bundle.clone()
            }
        ]
    })
}

fn build_requirement_contextual_plan(
    user_message: &str,
    intent_analysis: &Value,
    related_context: &Value,
    planned_tools: &[PlannedLocalTool],
    awaiting_permission: bool,
) -> Value {
    json!({
        "current_request_summary": intent_analysis["current_request_summary"].clone(),
        "final_intent": intent_analysis["focus"].clone(),
        "execution_focus": if planned_tools.is_empty() {
            "answer_with_model_context"
        } else {
            "model_tool_loop"
        },
        "execution_boundary": {
            "only_handle_current_request": true,
            "requires_permission_to_continue": awaiting_permission,
            "workspace_local_first": true
        },
        "context_used": related_context["items"].clone(),
        "planned_tool_count": planned_tools.len(),
        "plan": [
            "用需求理解结果压缩本轮重点和上下文检索方向",
            "只把相关 current_state、项目上下文和工具清单送入任务处理循环",
            "执行模型选择的标准 tool_calls，并把工具结果回传给模型",
            "结束后写回 actions_taken、current_state_delta、任务树和验证信息"
        ],
        "original_request": user_message
    })
}

fn build_requirement_understanding_snapshot(
    session_id: &str,
    user_message_id: &str,
    user_message: &str,
    intent_analysis: &Value,
    related_context: &Value,
    task_goal: &TaskGoal,
) -> Value {
    let prompt = json!({
        "user_message": user_message,
        "task_goal": task_goal,
        "intent_analysis": intent_analysis,
        "related_context": related_context
    });
    let prompt_raw = serde_json::to_string(&prompt).unwrap_or_else(|_| prompt.to_string());
    json!({
        "turn_id": format!("{session_id}-understanding"),
        "message_id": user_message_id,
        "loop": "requirement_understanding",
        "prompt_version": "desktop-local-agent-requirement-understanding/v1",
        "model_name": "local-deterministic-requirement-parser",
        "input_summary": "基于用户当前原文生成需求理解和上下文检索方向。",
        "context_package": {
            "task_goal": task_goal,
            "current_request_summary": intent_analysis["current_request_summary"].clone(),
            "related_work_summary": [],
            "current_state_used": "local requirement/current_state candidates",
            "task_focus": intent_analysis["focus"].clone()
        },
        "messages_hash": fnv1a_hex(&prompt_raw),
        "messages_redacted": [
            {
                "role": "user",
                "content_preview": truncate_inline(user_message, 600)
            }
        ],
        "created_at_epoch_ms": epoch_millis()
    })
}

fn build_task_processing_snapshot(
    session_id: &str,
    model_step_index: usize,
    request: &ModelStepRequest,
    prompt_stack: &PromptStack,
) -> Value {
    let messages_raw = serde_json::to_string(&request.messages)
        .unwrap_or_else(|_| format!("{:?}", request.messages));
    json!({
        "turn_id": format!("{session_id}-task-processing-{model_step_index}"),
        "message_id": format!("model-step-{model_step_index}"),
        "loop": "task_processing",
        "prompt_version": "desktop-local-agent-task-processing/v1",
        "model_name": request.model_name,
        "provider_id": request.provider_id,
        "mode": request.mode,
        "prompt_stack": prompt_stack,
        "input_summary": format!("任务处理循环第 {model_step_index} 次模型请求。"),
        "context_package": {
            "task_goal": request.task_goal.as_ref(),
            "task_tree": request.task_tree.as_ref(),
            "current_task_node": request
                .task_tree
                .as_ref()
                .map(current_task_node_value)
                .unwrap_or_else(|| json!({})),
            "current_request_summary": request
                .messages
                .iter()
                .rev()
                .find(|message| message.role == "user")
                .map(|message| truncate_inline(&message.content, 180))
                .unwrap_or_default(),
            "related_work_summary": request
                .messages
                .iter()
                .filter(|message| message.role == "tool")
                .map(|message| truncate_inline(&message.content, 180))
                .collect::<Vec<_>>(),
            "current_state_used": "messages supplied to model runner",
            "task_focus": "complete current request with standard tool_calls"
        },
        "messages_hash": fnv1a_hex(&messages_raw),
        "messages_redacted": request.messages.iter().map(|message| json!({
            "role": message.role,
            "tool_call_id": message.tool_call_id,
            "tool_call_count": message.tool_calls.len(),
            "content_preview": truncate_inline(&message.content, 700)
        })).collect::<Vec<_>>(),
        "created_at_epoch_ms": epoch_millis()
    })
}

fn lifecycle_node_status_for_run(run_status: &str, waiting_for: Option<&str>) -> &'static str {
    if waiting_for.is_some() {
        return "waiting";
    }
    match run_status {
        "completed" => "completed",
        "failed" => "failed",
        "waiting_approval" => "waiting",
        _ => "running",
    }
}

fn model_result_lifecycle_status(model_result: &ModelStepResult) -> &'static str {
    if model_result.ok {
        return "completed";
    }
    if model_result.error_code == "model.connection_timeout" {
        return "no_signal";
    }
    "failed"
}

fn lifecycle_final_status_for_run(run_status: &str, waiting_for: Option<&str>) -> &'static str {
    if waiting_for.is_some() {
        return "waiting";
    }
    match run_status {
        "completed" => "ended",
        "failed" => "failed",
        "waiting_approval" => "waiting",
        _ => "running",
    }
}

fn tool_lifecycle_node_kind(tool_name: &str) -> &'static str {
    match tool_name.trim() {
        "read_file" => "file_read",
        "list_files" | "search_text" => "file_search",
        "write_file" | "apply_patch" | "delete_file" => "file_edit",
        "run_command" | "check_command_risk" => "command",
        "call_mcp_tool" | "list_mcp_tools" | "read_mcp_resource" => "mcp_call",
        _ => "tool",
    }
}

fn tool_result_status(result: &super::types::ToolExecutionResult) -> String {
    if result.ok {
        return "completed".to_string();
    }
    if result.error_code == "permission.required" {
        return "waiting".to_string();
    }
    result
        .content
        .get("status")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("failed")
        .to_string()
}

fn conversation_context_messages(model_request: &ModelStepRequest) -> Vec<Value> {
    model_request
        .messages
        .iter()
        .enumerate()
        .map(|(index, message)| {
            json!({
                "index": index,
                "role": message.role,
                "tool_call_id": message.tool_call_id,
                "tool_call_count": message.tool_calls.len(),
                "content_preview": truncate_inline(&message.content, 1200),
            })
        })
        .collect()
}

fn build_conversation_lifecycle(
    session_id: &str,
    chat_session_id: &str,
    user_message_id: &str,
    assistant_message_id: &str,
    user_message: &str,
    run_status: &str,
    waiting_for: Option<&str>,
    model_request: &ModelStepRequest,
    agent_loop: &AgentLoopResult,
    tool_results: &[super::types::ToolExecutionResult],
    assistant_content: &str,
) -> Value {
    let started_at = epoch_millis();
    let total_context_messages = model_request.messages.len();
    let mut nodes = Vec::<Value>::new();
    nodes.push(json!({
        "id": format!("{session_id}:start"),
        "type": "start",
        "title": "开始",
        "status": "completed",
        "message_id": user_message_id,
        "message_role": "user",
        "summary": truncate_inline(user_message, 220),
        "context_ref": {
            "source": "conversation_context.messages",
            "start_index": 0,
            "end_index": total_context_messages,
            "model_step_index": 0
        },
        "index": 0,
        "created_at_epoch_ms": started_at,
    }));

    let understanding_summary = agent_loop
        .model_steps
        .first()
        .map(|step| truncate_inline(&step.summary, 260))
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "已创建本地模型请求并进入需求理解。".to_string());
    nodes.push(json!({
        "id": format!("{session_id}:understand_requirement"),
        "type": "understand_requirement",
        "title": "理解需求",
        "status": if agent_loop.model_steps.is_empty() && run_status == "failed" { "failed" } else { "completed" },
        "summary": understanding_summary,
        "model_message_count": model_request.messages.len(),
        "model_step_count": agent_loop.model_steps.len(),
        "context_ref": {
            "source": "conversation_context.messages",
            "start_index": 0,
            "end_index": total_context_messages,
            "model_step_index": 1
        },
        "index": 1,
        "created_at_epoch_ms": started_at,
    }));

    for (index, result) in tool_results.iter().enumerate() {
        let tool_name = result.name.trim();
        let content = result.content.as_object().cloned().unwrap_or_default();
        let path = content
            .get("path")
            .or_else(|| content.get("cwd"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim()
            .to_string();
        nodes.push(json!({
            "id": format!("{session_id}:execute_task:{}", result.tool_call_id),
            "type": "execute_task",
            "kind": tool_lifecycle_node_kind(tool_name),
            "title": if tool_name.is_empty() { "执行任务".to_string() } else { format!("执行任务：{tool_name}") },
            "status": tool_result_status(result),
            "terminal": result.content.get("terminal").and_then(Value::as_bool).unwrap_or(result.ok || result.error_code != "tool.timeout"),
            "requires_judgement": result.content.get("requires_judgement").and_then(Value::as_bool).unwrap_or(false),
            "summary": result.summary.as_str(),
            "tool_call_id": result.tool_call_id.as_str(),
            "tool_result_id": result.tool_result_id.as_str(),
            "tool_name": tool_name,
            "path": path,
            "error_code": result.error_code.as_str(),
            "error": result.error.as_str(),
            "context_ref": {
                "source": "conversation_context.messages",
                "start_index": 0,
                "end_index": total_context_messages,
                "tool_call_id": result.tool_call_id.as_str()
            },
            "index": index + 2,
            "created_at_epoch_ms": started_at,
        }));
    }

    if tool_results.is_empty() {
        nodes.push(json!({
            "id": format!("{session_id}:execute_task:none"),
            "type": "execute_task",
            "kind": "model",
            "title": "执行任务",
            "status": lifecycle_node_status_for_run(run_status, waiting_for),
            "summary": if agent_loop.model_steps.is_empty() {
                "尚未完成模型执行。".to_string()
            } else {
                "模型未请求本地工具，直接整理结果。".to_string()
            },
            "model_step_count": agent_loop.model_steps.len(),
            "context_ref": {
                "source": "conversation_context.messages",
                "start_index": 0,
                "end_index": total_context_messages,
                "model_step_index": agent_loop.model_steps.len()
            },
            "index": 2,
            "created_at_epoch_ms": started_at,
        }));
    }

    let final_summary = if waiting_for == Some("plan_confirmation") {
        "等待用户确认执行计划。".to_string()
    } else if waiting_for == Some("approval") {
        "等待用户授权后继续执行。".to_string()
    } else if agent_loop.stopped_reason == "tool_no_signal" {
        "当前步骤暂无完成或失败证据，任务已保留现场等待恢复判断。".to_string()
    } else if agent_loop.final_model_result().error_code == "model.connection_timeout" {
        "模型请求暂无返回信号，不能据此判断任务失败；已保留上下文等待恢复判断。".to_string()
    } else if run_status == "completed" {
        truncate_inline(assistant_content, 320)
    } else {
        agent_loop.error()
    };
    nodes.push(json!({
        "id": format!("{session_id}:final_solution"),
        "type": "final_solution",
        "title": "最终方案",
        "status": if agent_loop.stopped_reason == "tool_no_signal" {
            "no_signal"
        } else if agent_loop.final_model_result().error_code == "model.connection_timeout" {
            model_result_lifecycle_status(&agent_loop.final_model_result())
        } else {
            lifecycle_final_status_for_run(run_status, waiting_for)
        },
        "message_id": assistant_message_id,
        "message_role": "assistant",
        "summary": final_summary,
        "context_ref": {
            "source": "conversation_context.messages",
            "start_index": 0,
            "end_index": total_context_messages,
            "model_step_index": agent_loop.model_steps.len()
        },
        "index": nodes.len(),
        "created_at_epoch_ms": started_at,
    }));

    json!({
        "version": "desktop-conversation-lifecycle/v1",
        "session_id": session_id,
        "chat_session_id": chat_session_id,
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message_id,
        "status": lifecycle_final_status_for_run(run_status, waiting_for),
        "run_status": run_status,
        "waiting_for": waiting_for.unwrap_or(""),
        "model_step_count": agent_loop.model_steps.len(),
        "tool_call_count": tool_results.len(),
        "conversation_context": {
            "version": "desktop-conversation-context/v1",
            "storage": "single_snapshot_with_index_ranges",
            "messages": conversation_context_messages(model_request)
        },
        "nodes": nodes,
    })
}

fn build_agent_run_context(
    project_id: &str,
    chat_session_id: &str,
    run_id: &str,
    workspace_root: &PathBuf,
    request: &LocalChatRequest,
    user_message: &str,
    model_request: &ModelStepRequest,
    prompt_stack: &PromptStack,
) -> AgentRunContext {
    AgentRunContext {
        version: "agent-run-context/v1".to_string(),
        project_id: project_id.to_string(),
        chat_session_id: chat_session_id.to_string(),
        run_id: run_id.to_string(),
        workspace_path: workspace_root.to_string_lossy().to_string(),
        user_request: AgentRunUserRequest {
            raw: user_message.to_string(),
            normalized: normalize_agent_user_request(user_message),
            attachments: request
                .attachments
                .iter()
                .map(build_agent_run_attachment_summary)
                .collect(),
        },
        history_context: build_agent_run_history_context(&request.history),
        project_context: AgentRunProjectContext {
            project_id: project_id.to_string(),
            chat_session_id: chat_session_id.to_string(),
            workspace_path: workspace_root.to_string_lossy().to_string(),
            chat_settings: json!({
                "has_system_prompt": request
                    .system_prompt
                    .as_deref()
                    .map(str::trim)
                    .map(|value| !value.is_empty())
                    .unwrap_or(false),
                "temperature": request.temperature,
                "history_count": request.history.len()
            }),
            workspace_snapshot: json!({
                "root": workspace_root.to_string_lossy(),
                "attachments_count": request.attachments.len()
            }),
        },
        runtime_context: AgentRunRuntimeContext {
            provider_id: model_request.provider_id.clone(),
            model_name: model_request.model_name.clone(),
            mode: model_request.mode.clone(),
            model_capabilities: infer_model_capabilities(model_request),
            prompt_stack: prompt_stack.clone(),
            provider_profile: build_provider_capability_profile(model_request),
            attachment_routes: build_agent_run_attachment_routes(
                &request.attachments,
                model_request,
            ),
            available_tools: builtin_tool_definitions()
                .into_iter()
                .map(|definition| definition.name.to_string())
                .collect(),
        },
    }
}

fn normalize_agent_user_request(user_message: &str) -> String {
    user_message
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn build_agent_run_attachment_summary(
    attachment: &LocalChatAttachment,
) -> AgentRunAttachmentSummary {
    AgentRunAttachmentSummary {
        attachment_id: attachment.attachment_id.clone().unwrap_or_default(),
        name: attachment.name.clone(),
        mime_type: attachment.mime_type.clone().unwrap_or_default(),
        kind: attachment.kind.clone().unwrap_or_default(),
        routing_mode: attachment.routing_mode.clone().unwrap_or_default(),
        extraction_status: attachment.extraction_status.clone().unwrap_or_default(),
        has_data_url: attachment
            .data_url
            .as_deref()
            .map(str::trim)
            .map(|value| !value.is_empty())
            .unwrap_or(false),
        has_extracted_text: attachment
            .extracted_text
            .as_deref()
            .map(str::trim)
            .map(|value| !value.is_empty())
            .unwrap_or(false),
        has_provider_file_id: attachment
            .provider_file_id
            .as_deref()
            .map(str::trim)
            .map(|value| !value.is_empty())
            .unwrap_or(false),
        error: attachment.error.clone().unwrap_or_default(),
    }
}

fn build_agent_run_history_context(history: &[LocalChatMessage]) -> AgentRunHistoryContext {
    let recent_user_messages = history
        .iter()
        .filter(|message| normalize_model_message_role(&message.role) == "user")
        .rev()
        .take(5)
        .map(build_agent_run_history_message_summary)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    let recent_assistant_messages = history
        .iter()
        .filter(|message| normalize_model_message_role(&message.role) == "assistant")
        .filter(|message| !should_exclude_history_message_from_model_context(message))
        .rev()
        .take(5)
        .map(build_agent_run_history_message_summary)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    let excluded_diagnostics = history
        .iter()
        .filter(|message| should_exclude_history_message_from_model_context(message))
        .rev()
        .take(10)
        .map(build_agent_run_history_message_summary)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect::<Vec<_>>();
    let conversation_summary = format!(
        "history_total={}, excluded_diagnostics={}",
        history.len(),
        excluded_diagnostics.len()
    );

    AgentRunHistoryContext {
        conversation_summary,
        recent_user_messages,
        recent_assistant_messages,
        excluded_diagnostics,
    }
}

fn build_agent_run_history_message_summary(
    message: &LocalChatMessage,
) -> AgentRunHistoryMessageSummary {
    AgentRunHistoryMessageSummary {
        role: normalize_model_message_role(&message.role).to_string(),
        source_kind: message.source_kind.clone().unwrap_or_default(),
        visibility: message.visibility.clone().unwrap_or_default(),
        diagnostic: message.diagnostic.unwrap_or(false),
        content_preview: truncate_inline(&message.content, 260),
        reasoning_content_preview: message
            .reasoning_content
            .as_deref()
            .map(|value| truncate_inline(value, 160))
            .unwrap_or_default(),
    }
}

fn infer_model_capabilities(model_request: &ModelStepRequest) -> Vec<String> {
    let mut capabilities = vec!["text".to_string(), "tool_calls".to_string()];
    if model_request
        .messages
        .iter()
        .any(|message| !message.content_parts.is_empty())
    {
        capabilities.push("image_input".to_string());
    }
    capabilities
}

fn build_provider_capability_profile(
    model_request: &ModelStepRequest,
) -> ModelCompatibilityProfile {
    let image_part_count = model_request
        .messages
        .iter()
        .flat_map(|message| message.content_parts.iter())
        .filter(|part| matches!(part, RuntimeModelContentPart::ImageUrl { .. }))
        .count();
    let is_openai_compatible = normalize_model_mode(Some(&model_request.mode)) != "mock";
    ModelCompatibilityProfile {
        version: "model-compatibility-profile/v1".to_string(),
        provider_id: model_request.provider_id.clone(),
        model_name: model_request.model_name.clone(),
        mode: model_request.mode.clone(),
        supports_tools: is_openai_compatible,
        supports_reasoning_content_replay: true,
        requires_reasoning_content_replay: model_request.messages.iter().any(|message| {
            normalize_model_message_role(&message.role) == "assistant"
                && !message.tool_calls.is_empty()
                && !message.reasoning_content.trim().is_empty()
        }),
        supports_image_url: image_part_count > 0,
        image_input_status: if image_part_count > 0 {
            "requested_by_attachment_routing"
        } else {
            "not_requested"
        }
        .to_string(),
        image_part_count,
        tool_role_mode: "tool_role".to_string(),
        stream_mode: "non_stream".to_string(),
    }
}

fn build_agent_run_attachment_routes(
    attachments: &[LocalChatAttachment],
    model_request: &ModelStepRequest,
) -> Vec<AgentRunAttachmentRoute> {
    let image_part_count = model_request
        .messages
        .iter()
        .flat_map(|message| message.content_parts.iter())
        .filter(|part| matches!(part, RuntimeModelContentPart::ImageUrl { .. }))
        .count();
    let mut remaining_image_parts = image_part_count;
    attachments
        .iter()
        .map(|attachment| {
            let routing_mode = attachment
                .routing_mode
                .as_deref()
                .map(str::trim)
                .unwrap_or("")
                .to_string();
            let requested_image_input =
                routing_mode == "inline_image" || routing_mode == "provider_file";
            let has_image_data_url = attachment
                .data_url
                .as_deref()
                .map(str::trim)
                .is_some_and(|value| value.starts_with("data:image/"));
            let included_as_image_part =
                requested_image_input && has_image_data_url && remaining_image_parts > 0;
            if included_as_image_part {
                remaining_image_parts = remaining_image_parts.saturating_sub(1);
            }
            let included_as_text_context = attachment
                .extracted_text
                .as_deref()
                .map(str::trim)
                .is_some_and(|value| !value.is_empty())
                || !included_as_image_part;
            let downgrade_reason = if included_as_image_part {
                String::new()
            } else if !requested_image_input {
                "routing_mode_text_or_metadata_only".to_string()
            } else if !has_image_data_url {
                "missing_image_data_url".to_string()
            } else {
                "image_part_not_emitted".to_string()
            };
            AgentRunAttachmentRoute {
                attachment_id: attachment.attachment_id.clone().unwrap_or_default(),
                name: attachment.name.clone(),
                routing_mode,
                mime_type: attachment.mime_type.clone().unwrap_or_default(),
                requested_image_input,
                included_as_image_part,
                included_as_text_context,
                downgrade_reason,
            }
        })
        .collect()
}

fn build_observations(
    session_id: &str,
    model_result: &ModelStepResult,
    tool_results: &[super::types::ToolExecutionResult],
    run_status: &str,
    waiting_for: Option<&str>,
    stopped_reason: &str,
    runtime_summary: &str,
    runtime_error_code: &str,
) -> Vec<Observation> {
    let created_at_epoch_ms = epoch_millis();
    let mut observations = Vec::new();
    observations.push(Observation {
        observation_id: format!("{session_id}-obs-model-final"),
        source: "model_output".to_string(),
        visibility: "model_context".to_string(),
        summary: if model_result.summary.trim().is_empty() {
            truncate_inline(&model_result.content, 220)
        } else {
            truncate_inline(&model_result.summary, 220)
        },
        content_ref: "model_runtime".to_string(),
        tool_call_id: String::new(),
        error_code: model_result.error_code.clone(),
        created_at_epoch_ms,
    });
    observations.extend(
        tool_results
            .iter()
            .enumerate()
            .map(|(index, result)| Observation {
                observation_id: format!("{session_id}-obs-tool-{}", index + 1),
                source: "tool_result".to_string(),
                visibility: if result.error_code == "permission.required" {
                    "user_visible".to_string()
                } else {
                    "model_context".to_string()
                },
                summary: truncate_inline(&result.summary, 240),
                content_ref: format!("tool_results[{index}]"),
                tool_call_id: result.tool_call_id.clone(),
                error_code: result.error_code.clone(),
                created_at_epoch_ms,
            }),
    );
    if run_status != "completed" || waiting_for.is_some() || !stopped_reason.trim().is_empty() {
        let summary = if !runtime_summary.trim().is_empty() {
            runtime_summary
        } else if let Some(waiting_for) = waiting_for {
            return observations
                .into_iter()
                .chain(std::iter::once(Observation {
                    observation_id: format!("{session_id}-obs-runtime"),
                    source: "runtime_error".to_string(),
                    visibility: "user_visible".to_string(),
                    summary: format!("当前等待 {waiting_for}，运行暂停。"),
                    content_ref: "run_state".to_string(),
                    tool_call_id: String::new(),
                    error_code: runtime_error_code.to_string(),
                    created_at_epoch_ms,
                }))
                .collect();
        } else {
            "运行未完成。"
        };
        observations.push(Observation {
            observation_id: format!("{session_id}-obs-runtime"),
            source: "runtime_error".to_string(),
            visibility: "user_visible".to_string(),
            summary: truncate_inline(summary, 240),
            content_ref: "run_state".to_string(),
            tool_call_id: String::new(),
            error_code: runtime_error_code.to_string(),
            created_at_epoch_ms,
        });
    }
    observations
}

fn build_runtime_scheduler_state(
    run_status: &str,
    waiting_for: Option<&str>,
    agent_loop: &AgentLoopResult,
    planned_tools: &[PlannedLocalTool],
    tool_results: &[super::types::ToolExecutionResult],
) -> RuntimeSchedulerState {
    let now = epoch_millis();
    let failed_tool_count = tool_results.iter().filter(|result| !result.ok).count();
    let pending_tool_call_ids = tool_results
        .iter()
        .filter(|result| !result.ok)
        .map(|result| result.tool_call_id.clone())
        .collect::<Vec<_>>();
    let next_action = if waiting_for == Some("plan_confirmation") {
        "wait_for_plan_confirmation"
    } else if waiting_for == Some("approval") {
        "wait_for_approval"
    } else if run_status == "completed" {
        "finish"
    } else if failed_tool_count > 0 {
        "retry_or_report_tool_failure"
    } else if !agent_loop.error_code().is_empty() {
        "retry_or_report_runtime_failure"
    } else {
        "report_model_failure"
    };
    let pending_request_id = tool_results
        .iter()
        .find(|result| result.error_code == "permission.required")
        .and_then(|result| result.content.get("permissionRequest"))
        .and_then(|request| request.get("requestId"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let tool_batches = build_tool_batch_states(planned_tools, tool_results, now);
    let pending_tool_batch_id = tool_batches
        .iter()
        .find(|batch| !batch.pending_tool_call_ids.is_empty())
        .map(|batch| batch.batch_id.clone())
        .unwrap_or_default();
    let run_state = RunState {
        version: "run-state/v1".to_string(),
        status: run_status.to_string(),
        waiting_for: waiting_for.unwrap_or("").to_string(),
        pending_request_id,
        pending_tool_call_ids: pending_tool_call_ids.clone(),
        pending_tool_batch_id,
        pending_adapter_action_id: String::new(),
        updated_at_epoch_ms: now,
    };

    RuntimeSchedulerState {
        version: "runtime-scheduler-state/v1".to_string(),
        status: run_status.to_string(),
        waiting_for: waiting_for.unwrap_or("").to_string(),
        run_state,
        tool_batches,
        model_round_count: agent_loop.model_steps.len(),
        tool_round_count: agent_loop.tool_round_count(),
        planned_tool_count: planned_tools.len(),
        completed_tool_count: tool_results.iter().filter(|result| result.ok).count(),
        failed_tool_count,
        pending_tool_call_ids,
        next_action: next_action.to_string(),
        stopped_reason: agent_loop.stopped_reason.clone(),
        updated_at_epoch_ms: now,
    }
}

fn build_tool_batch_states(
    planned_tools: &[PlannedLocalTool],
    tool_results: &[super::types::ToolExecutionResult],
    now: u128,
) -> Vec<ToolBatchState> {
    if planned_tools.is_empty() && tool_results.is_empty() {
        return Vec::new();
    }
    let mut tool_call_ids = planned_tools
        .iter()
        .map(|tool| tool.tool_call_id.clone())
        .collect::<Vec<_>>();
    for result in tool_results {
        if !tool_call_ids.iter().any(|id| id == &result.tool_call_id) {
            tool_call_ids.push(result.tool_call_id.clone());
        }
    }
    let completed_tool_call_ids = tool_results
        .iter()
        .filter(|result| result.ok)
        .map(|result| result.tool_call_id.clone())
        .collect::<Vec<_>>();
    let failed_tool_call_ids = tool_results
        .iter()
        .filter(|result| !result.ok)
        .map(|result| result.tool_call_id.clone())
        .collect::<Vec<_>>();
    let pending_tool_call_ids = tool_call_ids
        .iter()
        .filter(|tool_call_id| {
            !tool_results
                .iter()
                .any(|result| &result.tool_call_id == *tool_call_id && result.ok)
        })
        .cloned()
        .collect::<Vec<_>>();
    let status = if !pending_tool_call_ids.is_empty() {
        "waiting"
    } else if !failed_tool_call_ids.is_empty() {
        "failed"
    } else {
        "completed"
    };
    let batch_seed = tool_call_ids
        .first()
        .cloned()
        .unwrap_or_else(|| "empty".to_string());
    vec![ToolBatchState {
        batch_id: format!("tool_batch_{}", sanitize_path_segment(&batch_seed)),
        status: status.to_string(),
        tool_call_ids,
        pending_tool_call_ids,
        completed_tool_call_ids,
        failed_tool_call_ids,
        created_at_epoch_ms: now,
        updated_at_epoch_ms: now,
    }]
}

fn normalize_system_prompt_parts(request: &LocalChatRequest) -> Vec<(usize, String, i64, String)> {
    let mut parts = request
        .system_prompt_parts
        .iter()
        .enumerate()
        .filter_map(|(index, part)| {
            let content = part.content.trim();
            if content.is_empty() {
                return None;
            }
            let source = if part.source.trim().is_empty() {
                format!("system_prompt_part_{}", index + 1)
            } else {
                part.source.trim().to_string()
            };
            Some((
                index,
                source,
                part.priority.unwrap_or(100),
                content.to_string(),
            ))
        })
        .collect::<Vec<_>>();
    parts.sort_by(|left, right| right.2.cmp(&left.2).then_with(|| left.0.cmp(&right.0)));
    parts
}

fn resolve_prompt_stack(
    local_request: &LocalChatRequest,
    model_request: &ModelStepRequest,
) -> PromptStack {
    let structured_parts = normalize_system_prompt_parts(local_request);
    let items = if structured_parts.is_empty() {
        model_request
            .messages
            .iter()
            .filter(|message| normalize_model_message_role(&message.role) == "system")
            .enumerate()
            .map(|(index, message)| PromptStackItem {
                source: if index == 0 {
                    "project_or_combined_system_prompt".to_string()
                } else {
                    "additional_system_prompt".to_string()
                },
                priority: 100_i64.saturating_sub(index as i64),
                content_hash: format!("fnv1a:{}", fnv1a_hex(&message.content)),
                content_preview: truncate_inline(&message.content, 500),
            })
            .collect::<Vec<_>>()
    } else {
        structured_parts
            .iter()
            .map(|(_, source, priority, content)| PromptStackItem {
                source: source.clone(),
                priority: *priority,
                content_hash: format!("fnv1a:{}", fnv1a_hex(content)),
                content_preview: truncate_inline(content, 500),
            })
            .collect::<Vec<_>>()
    };
    let resolved_system_prompt = model_request
        .messages
        .iter()
        .filter(|message| normalize_model_message_role(&message.role) == "system")
        .map(|message| message.content.trim())
        .filter(|content| !content.is_empty())
        .collect::<Vec<_>>()
        .join("\n\n");
    let mut warnings = Vec::new();
    if items.is_empty() {
        warnings.push("missing_system_prompt".to_string());
    }
    if structured_parts.is_empty() && items.len() > 1 {
        warnings.push("multiple_system_prompts_string_compat_mode".to_string());
    }

    PromptStack {
        version: "prompt-stack/v1".to_string(),
        items,
        resolved_system_prompt_hash: if resolved_system_prompt.is_empty() {
            String::new()
        } else {
            format!("fnv1a:{}", fnv1a_hex(&resolved_system_prompt))
        },
        resolved_system_prompt_preview: truncate_inline(&resolved_system_prompt, 700),
        warnings,
    }
}

fn prompt_stack_from_model_request(model_request: &ModelStepRequest) -> PromptStack {
    let request = LocalChatRequest {
        project_id: String::new(),
        chat_session_id: String::new(),
        message_id: None,
        assistant_message_id: None,
        message: String::new(),
        workspace_path: String::new(),
        history: Vec::new(),
        provider_id: None,
        model_name: None,
        system_prompt: None,
        system_prompt_parts: Vec::new(),
        temperature: None,
        model_runtime: None,
        ai_entry_file: None,
        attachments: Vec::new(),
        backend_context: None,
        permission_decision: None,
    };
    resolve_prompt_stack(&request, model_request)
}

fn build_requirement_actions_taken(
    agent_loop: &AgentLoopResult,
    planned_tools: &[PlannedLocalTool],
    tool_results: &[super::types::ToolExecutionResult],
    model_result: &ModelStepResult,
) -> Value {
    json!({
        "model_steps": agent_loop.model_steps.iter().enumerate().map(|(index, step)| json!({
            "index": index + 1,
            "mode": step.mode,
            "provider_id": step.provider_id,
            "model_name": step.model_name,
            "status": step.status,
            "ok": step.ok,
            "summary": step.summary,
            "tool_call_count": step.tool_calls.len(),
            "error_code": step.error_code
        })).collect::<Vec<_>>(),
        "planned_tools": planned_tools.iter().map(|tool| json!({
            "tool_call_id": tool.tool_call_id,
            "tool_name": tool.name,
            "summary": tool.summary,
            "arguments_hash": fnv1a_hex(&tool.arguments.to_string())
        })).collect::<Vec<_>>(),
        "tool_results": tool_results.iter().map(|result| json!({
            "tool_call_id": result.tool_call_id,
            "tool_name": result.name,
            "ok": result.ok,
            "summary": result.summary,
            "error_code": result.error_code
        })).collect::<Vec<_>>(),
        "final_model_status": model_result.status,
        "stopped_reason": agent_loop.stopped_reason
    })
}

fn assess_clarity(
    user_message: &str,
    _request: &LocalChatRequest,
    model_request: &ModelStepRequest,
) -> ClarityAssessment {
    let targets = extract_file_path_candidates(user_message);
    let task_type = classify_clarity_task_type(user_message);
    let goal_clear = !normalize_agent_user_request(user_message).is_empty();
    let target_clear = !targets.is_empty()
        || matches!(task_type.as_str(), "query" | "explanation")
        || infer_recent_target_path(&model_request.messages).is_some();
    let scope_clear = !user_message.contains("随便")
        && !user_message.contains("都行")
        && !user_message.contains("看着办");
    let expected_result_clear = user_message.contains("回复")
        || user_message.contains("开发")
        || user_message.contains("修改")
        || user_message.contains("修复")
        || user_message.contains("检测")
        || user_message.contains("验证")
        || user_message.contains("暂停")
        || matches!(task_type.as_str(), "query" | "explanation");
    let requires_confirmation = matches!(task_type.as_str(), "destructive" | "deployment")
        || matches!(task_type.as_str(), "implementation");
    let mut ambiguities = Vec::new();
    if !target_clear {
        ambiguities.push("target_not_explicit".to_string());
    }
    if !scope_clear {
        ambiguities.push("scope_open_ended".to_string());
    }
    if !expected_result_clear {
        ambiguities.push("expected_result_not_explicit".to_string());
    }
    let score = [goal_clear, target_clear, scope_clear, expected_result_clear]
        .iter()
        .filter(|value| **value)
        .count() as u8
        + if ambiguities.is_empty() { 1 } else { 0 };

    ClarityAssessment {
        version: "clarity-assessment/v1".to_string(),
        score: score.min(5),
        task_type,
        goal_clear,
        target_clear,
        scope_clear,
        expected_result_clear,
        requires_confirmation,
        confirmation_reason: if requires_confirmation {
            "state_changing_request_requires_plan_confirmation".to_string()
        } else {
            String::new()
        },
        interpretation: truncate_inline(user_message, 220),
        ambiguities,
    }
}

fn classify_clarity_task_type(user_message: &str) -> String {
    if contains_any(user_message, &["删除", "清空", "覆盖", "重置", "rm -rf"]) {
        "destructive".to_string()
    } else if contains_any(user_message, &["部署", "发布", "上线", "打包"]) {
        "deployment".to_string()
    } else if contains_any(
        user_message,
        &[
            "开发", "修改", "修复", "实现", "继续", "开始", "改造", "写入",
        ],
    ) {
        "implementation".to_string()
    } else if contains_any(user_message, &["区别", "说明", "解释", "理解"]) {
        "explanation".to_string()
    } else if user_message.contains("？") || user_message.contains('?') {
        "query".to_string()
    } else {
        "ambiguous".to_string()
    }
}

fn plan_confirmation_request_id(chat_session_id: &str, user_message_id: &str) -> String {
    format!(
        "plan_confirm_{}_{}",
        sanitize_path_segment(chat_session_id),
        sanitize_path_segment(user_message_id)
    )
}

fn has_plan_confirmation(request: &LocalChatRequest, expected_request_id: &str) -> bool {
    let Some(decision) = request.permission_decision.as_ref() else {
        return false;
    };
    if is_full_access_decision(decision) {
        return true;
    }
    let decision_value = decision.decision.trim();
    if !matches!(decision_value, "approve_once" | "approve_session") {
        return false;
    }
    let grant_scope = decision.grant_scope.as_deref().unwrap_or("").trim();
    if decision_value == "approve_once" && !grant_scope.is_empty() && grant_scope != "once" {
        return false;
    }
    if decision_value == "approve_session" && !matches!(grant_scope, "session" | "current_session")
    {
        return false;
    }
    decision
        .request_id
        .as_deref()
        .map(str::trim)
        .map(|request_id| request_id == expected_request_id)
        .unwrap_or(false)
}

fn build_plan_confirmation_agent_loop(
    runtime_session_id: &str,
    chat_session_id: &str,
    request_id: &str,
    user_message: &str,
    clarity: &ClarityAssessment,
    event_sink: Option<&dyn Fn(Value)>,
) -> AgentLoopResult {
    let tool_call_id = format!("call_{request_id}");
    let plan_summary = if clarity.task_type == "destructive" {
        "执行前需要确认含删除、清空、覆盖或重置风险的计划。"
    } else if clarity.task_type == "deployment" {
        "执行前需要确认部署、发布或打包计划。"
    } else {
        "执行前需要确认会改变项目状态的开发计划。"
    };
    let permission_request = json!({
        "requestId": request_id,
        "action": "confirm_plan",
        "risk": if clarity.task_type == "destructive" || clarity.task_type == "deployment" {
            "high"
        } else {
            "medium"
        },
        "reason": plan_summary,
        "scope": "current_chat_task",
        "preview": {
            "taskType": clarity.task_type,
            "score": clarity.score,
            "interpretation": clarity.interpretation,
            "ambiguities": clarity.ambiguities,
            "userRequest": truncate_inline(user_message, 500)
        },
        "options": [
            {
                "decision": "approve_once",
                "label": "确认执行计划",
                "grantScope": "once"
            },
            {
                "decision": "deny",
                "label": "拒绝",
                "grantScope": null
            }
        ]
    });
    let tool_result = super::types::ToolExecutionResult {
        tool_result_id: format!("result_{tool_call_id}"),
        tool_call_id,
        name: "planning_gate".to_string(),
        ok: false,
        content: json!({
            "permissionRequest": permission_request,
            "planningGate": {
                "version": "planning-gate/v1",
                "requires_confirmation": true,
                "confirmation_reason": clarity.confirmation_reason,
                "task_type": clarity.task_type,
                "user_request": truncate_inline(user_message, 500)
            }
        }),
        summary: "需要确认执行计划后继续。".to_string(),
        error_code: "permission.required".to_string(),
        error: "需要确认执行计划后继续。".to_string(),
    };
    emit_approval_required_event(
        event_sink,
        runtime_session_id,
        chat_session_id,
        &tool_result,
    );
    finalize_agent_loop_result(
        Vec::new(),
        Vec::new(),
        Vec::new(),
        vec![tool_result],
        Vec::new(),
        Vec::new(),
        "waiting_plan_confirmation".to_string(),
        true,
    )
}

fn create_plan_state(
    session_id: &str,
    task_goal: &TaskGoal,
    clarity: &ClarityAssessment,
    run_status: &str,
    created_at_epoch_ms: u128,
    agent_loop: Option<&AgentLoopResult>,
    task_tree: &planning::TaskTree,
) -> PlanState {
    let verification_summary = agent_loop
        .map(|loop_result| loop_result.verification.summary.clone())
        .unwrap_or_default();
    let mut nodes = task_tree
        .nodes
        .iter()
        .filter(|node| node.node_type != "goal")
        .map(|node| PlanNode {
            node_id: node.node_id.clone(),
            title: node.title.clone(),
            status: node.status.clone(),
            verification_result: node
                .verification_result
                .clone()
                .unwrap_or_else(|| verification_summary.clone()),
        })
        .collect::<Vec<_>>();
    if clarity.requires_confirmation {
        nodes.insert(
            0,
            PlanNode {
                node_id: format!("node-confirm-{session_id}"),
                title: "记录需要确认的状态变更请求".to_string(),
                status: if run_status == "waiting_approval" {
                    "waiting".to_string()
                } else {
                    "recorded".to_string()
                },
                verification_result: clarity.confirmation_reason.clone(),
            },
        );
    }

    PlanState {
        version: "plan-state/v1".to_string(),
        plan_id: format!("plan_{session_id}"),
        status: match run_status {
            "completed" => "completed",
            "waiting_approval" => "blocked",
            "failed" => "failed",
            _ => "running",
        }
        .to_string(),
        root_goal: truncate_inline(&task_goal.user_request, 260),
        nodes,
        current_node_id: task_tree.current_node_id.clone(),
        destructive_steps: if clarity.task_type == "destructive" {
            vec![truncate_inline(&task_goal.user_request, 160)]
        } else {
            Vec::new()
        },
        created_at_epoch_ms,
        updated_at_epoch_ms: epoch_millis(),
    }
}

fn route_failure(
    session_id: &str,
    run_status: &str,
    waiting_for: Option<&str>,
    agent_loop: &AgentLoopResult,
    tool_results: &[super::types::ToolExecutionResult],
    model_result: &ModelStepResult,
) -> RetryDecision {
    let repeated_attempts = agent_loop
        .attempts
        .iter()
        .filter(|attempt| attempt.status == "failed")
        .count();
    let (route, failure_type, reason, retry_allowed, exit_condition) = if run_status == "completed"
    {
        ("none", "none", "本轮已完成，无需重试。", false, "已完成。")
    } else if waiting_for == Some("plan_confirmation") {
        (
            "draft",
            "plan_confirmation_required",
            "状态变更请求等待用户确认执行计划，运行时不会提前调用模型或本地工具。",
            false,
            "用户确认或拒绝当前 plan confirmation request。",
        )
    } else if waiting_for == Some("approval") {
        (
            "draft",
            "permission_required",
            "工具调用等待用户授权，运行时不自动重试副作用动作。",
            false,
            "用户允许或拒绝当前 permission request。",
        )
    } else if let Some(result) = tool_results.iter().find(|result| !result.ok) {
        route_tool_failure(result, repeated_attempts)
    } else if !model_result.ok {
        route_model_failure(model_result)
    } else if agent_loop.stopped_reason == "verification_failed" {
        (
            "plan",
            "verification_failed",
            "验证未通过，需要重新规划或补救一次。",
            repeated_attempts < 2,
            "补救验证通过，或重复失败后进入 blocked。",
        )
    } else {
        (
            "draft",
            "unknown",
            "未识别到可自动恢复的失败类型。",
            false,
            "输出可见失败摘要。",
        )
    };

    RetryDecision {
        version: "retry-decision/v1".to_string(),
        decision_id: format!("retry_{session_id}_{}", epoch_millis()),
        route: route.to_string(),
        failure_type: failure_type.to_string(),
        reason: reason.to_string(),
        retry_allowed,
        max_attempts: 2,
        observed_attempts: repeated_attempts,
        exit_condition: exit_condition.to_string(),
        created_at_epoch_ms: epoch_millis(),
    }
}

fn route_tool_failure(
    result: &super::types::ToolExecutionResult,
    repeated_attempts: usize,
) -> (&'static str, &'static str, &'static str, bool, &'static str) {
    let code = result.error_code.as_str();
    if code.contains("permission") {
        (
            "draft",
            "permission_required",
            "权限门阻止了副作用工具执行。",
            false,
            "等待用户授权或拒绝。",
        )
    } else if code.contains("drift_detected") {
        (
            "plan",
            "goal_drift_detected",
            "副作用工具目标偏离本轮 TaskGoal，需要回到当前目标范围重新规划。",
            repeated_attempts < 2,
            "工具目标回到 TaskGoal 范围内并验证通过，重复偏离后 blocked。",
        )
    } else if code.contains("not_found") || result.summary.contains("不存在") {
        (
            "search",
            "path_not_found",
            "目标路径不存在，下一步应先搜索或列目录。",
            repeated_attempts < 2,
            "找到候选路径后重试，重复失败后 blocked。",
        )
    } else if code.contains("schema") || code.contains("argument") {
        (
            "tool",
            "schema_invalid",
            "工具参数不满足 schema，可安全修正参数后再试。",
            repeated_attempts < 2,
            "参数修复后工具成功，重复失败后 blocked。",
        )
    } else {
        (
            "plan",
            "tool_failed",
            "工具失败类型不明确，需要重新规划。",
            repeated_attempts < 2,
            "新计划成功或重复失败后 blocked。",
        )
    }
}

fn route_model_failure(
    model_result: &ModelStepResult,
) -> (&'static str, &'static str, &'static str, bool, &'static str) {
    if model_result.error.contains("image_url") || model_result.error.contains("unsupported") {
        (
            "plan",
            "provider_payload_incompatible",
            "模型供应商不兼容当前 payload，需要切换兼容策略。",
            true,
            "降级 payload 后成功，或提示能力限制。",
        )
    } else if model_result.error.contains("reasoning_content") {
        (
            "plan",
            "reasoning_replay_required",
            "模型供应商要求 continuation 回传 reasoning_content。",
            true,
            "回传 reasoning_content 后成功，或提示能力限制。",
        )
    } else {
        (
            "draft",
            "model_failed",
            "模型调用失败，当前切片只记录可解释路由。",
            false,
            "输出用户可见失败摘要。",
        )
    }
}

fn classify_memory_writes(
    project_id: &str,
    chat_session_id: &str,
    session_id: &str,
    user_message: &str,
    run_status: &str,
    waiting_for: Option<&str>,
) -> MemoryWritePlan {
    let mut items = vec![
        MemoryWritePlanItem {
            scope: "short".to_string(),
            target: "state.json.current_state".to_string(),
            content: format!(
                "status={} waiting_for={}",
                run_status,
                waiting_for.unwrap_or("")
            ),
            status: "written".to_string(),
        },
        MemoryWritePlanItem {
            scope: "project".to_string(),
            target: format!("requirements/{project_id}/{chat_session_id}.json"),
            content: truncate_inline(user_message, 220),
            status: "written".to_string(),
        },
        MemoryWritePlanItem {
            scope: "project".to_string(),
            target: format!("query-mcp/outbox/{project_id}__{chat_session_id}.jsonl"),
            content: format!("session_id={session_id}; status={run_status}"),
            status: "queued".to_string(),
        },
    ];
    if run_status == "completed" {
        items.push(MemoryWritePlanItem {
            scope: "long".to_string(),
            target: "deferred".to_string(),
            content: "本轮完成后可由上层记忆能力判断是否沉淀长期经验。".to_string(),
            status: "candidate_only".to_string(),
        });
    }

    MemoryWritePlan {
        version: "memory-write-plan/v1".to_string(),
        items,
        long_memory_candidates: if run_status == "completed" {
            vec![truncate_inline(user_message, 180)]
        } else {
            Vec::new()
        },
        created_at_epoch_ms: epoch_millis(),
    }
}

fn contains_any(value: &str, needles: &[&str]) -> bool {
    needles.iter().any(|needle| value.contains(needle))
}

fn build_requirement_current_state_delta(
    run_status: &str,
    waiting_for: Option<&str>,
    agent_loop: &AgentLoopResult,
    planned_tools: &[PlannedLocalTool],
    tool_results: &[super::types::ToolExecutionResult],
    agent_run_context: &AgentRunContext,
    observations: &[Observation],
    scheduler_state: &RuntimeSchedulerState,
    verification_report: &VerificationReport,
    task_goal: &TaskGoal,
    clarity_assessment: &ClarityAssessment,
    plan_state: &PlanState,
    retry_decision: &RetryDecision,
    memory_write_plan: &MemoryWritePlan,
    runtime_artifacts: &RuntimeArtifactPaths,
    dynamic_task_tree: &planning::TaskTree,
) -> Value {
    json!({
        "latest_status": run_status,
        "waiting_for": waiting_for.unwrap_or(""),
        "model_round_count": agent_loop.model_steps.len(),
        "planned_tool_count": planned_tools.len(),
        "tool_result_count": tool_results.len(),
        "changed_or_inspected_targets": changed_or_inspected_targets(planned_tools),
        "agent_run_context": agent_run_context,
        "observations": observations,
        "scheduler_state": scheduler_state,
        "task_goal": task_goal,
        "task_tree": dynamic_task_tree,
        "current_task_node": current_task_node_value(dynamic_task_tree),
        "task_branches": task_branch_values(dynamic_task_tree),
        "clarity_assessment": clarity_assessment,
        "plan_state": plan_state,
        "retry_decision": retry_decision,
        "memory_write_plan": memory_write_plan,
        "verification": agent_loop.verification,
        "verification_report": verification_report,
        "runtime_state_path": runtime_artifacts.state_path,
        "transcript_path": runtime_artifacts.transcript_path,
        "outbox_path": runtime_artifacts.outbox_path
    })
}

fn build_verification_report(
    run_status: &str,
    waiting_for: Option<&str>,
    agent_loop: &AgentLoopResult,
    planned_tools: &[PlannedLocalTool],
    tool_results: &[super::types::ToolExecutionResult],
    task_goal: &TaskGoal,
) -> VerificationReport {
    let tool_failures = tool_results
        .iter()
        .filter(|result| !result.ok)
        .collect::<Vec<_>>();
    let side_effect_tool_count = planned_tools
        .iter()
        .filter(|tool| is_side_effect_tool(&tool.name))
        .count();
    let blocked_side_effect_count = tool_results
        .iter()
        .filter(|result| {
            is_side_effect_tool(&result.name) && result.error_code == "permission.required"
        })
        .count();
    let targets = changed_or_inspected_targets(planned_tools);
    let mut checks = vec![
        VerificationCheck {
            check_type: "fact".to_string(),
            status: if tool_failures.is_empty() {
                "passed"
            } else {
                "failed"
            }
            .to_string(),
            summary: if tool_results.is_empty() {
                "本轮未执行本机工具，事实验证基于模型返回状态。".to_string()
            } else {
                format!(
                    "本轮执行 {} 个本机工具，失败 {} 个。",
                    tool_results.len(),
                    tool_failures.len()
                )
            },
        },
        VerificationCheck {
            check_type: "logic".to_string(),
            status: agent_loop.verification.status.clone(),
            summary: if agent_loop.verification.summary.trim().is_empty() {
                "模型未提供额外自检摘要，按运行状态完成基础逻辑校验。".to_string()
            } else {
                agent_loop.verification.summary.clone()
            },
        },
        VerificationCheck {
            check_type: "constraint".to_string(),
            status: if waiting_for.is_some() {
                "blocked"
            } else {
                "passed"
            }
            .to_string(),
            summary: if waiting_for.is_some() {
                format!(
                    "当前等待 {}，未继续执行需要授权的副作用动作。",
                    waiting_for.unwrap_or("")
                )
            } else {
                "副作用动作均通过本地权限与工具执行层处理。".to_string()
            },
        },
        VerificationCheck {
            check_type: "goal".to_string(),
            status: agent_loop.verification.status.clone(),
            summary: if agent_loop.verification.summary.trim().is_empty() {
                format!(
                    "当前目标 {} 已进入运行状态，目标对象：{}。",
                    task_goal.goal_id, task_goal.target_object
                )
            } else {
                format!(
                    "{} 目标：{}。",
                    agent_loop.verification.summary, task_goal.title
                )
            },
        },
    ];
    checks.push(VerificationCheck {
        check_type: "tool_execution".to_string(),
        status: if tool_failures.is_empty() {
            "passed"
        } else if blocked_side_effect_count > 0 {
            "blocked"
        } else {
            "failed"
        }
        .to_string(),
        summary: format!(
            "计划工具 {} 个，实际结果 {} 个，副作用工具 {} 个，权限阻塞副作用 {} 个。",
            planned_tools.len(),
            tool_results.len(),
            side_effect_tool_count,
            blocked_side_effect_count
        ),
    });
    checks.push(VerificationCheck {
        check_type: "target_scope".to_string(),
        status: if targets.is_empty() && side_effect_tool_count > 0 {
            "failed"
        } else {
            "passed"
        }
        .to_string(),
        summary: if targets.is_empty() {
            "本轮未解析到工具目标路径。".to_string()
        } else {
            format!("本轮工具目标：{}。", targets.join("，"))
        },
    });
    let mut evidence = agent_loop.verification.evidence.clone();
    evidence.push(format!(
        "local_tool_execution planned={} results={} side_effects={} permission_blocked_side_effects={}",
        planned_tools.len(),
        tool_results.len(),
        side_effect_tool_count,
        blocked_side_effect_count
    ));
    if !targets.is_empty() {
        evidence.push(format!("local_targets={}", targets.join(",")));
    }
    evidence.push(format!("task_goal_id={}", task_goal.goal_id));
    evidence.push(format!("task_goal_intent={}", task_goal.intent));

    VerificationReport {
        version: "verification-report/v1".to_string(),
        verification_id: format!("verify_{}", epoch_millis()),
        target_node_id: task_goal.goal_id.clone(),
        overall_status: if run_status == "completed" {
            "passed"
        } else if waiting_for.is_some() {
            "blocked"
        } else {
            "failed"
        }
        .to_string(),
        checks,
        evidence,
        created_at_epoch_ms: epoch_millis(),
    }
}

fn is_side_effect_tool(tool_name: &str) -> bool {
    matches!(
        tool_name.trim(),
        "write_file" | "apply_patch" | "delete_file" | "run_command" | "download_file"
    )
}

fn build_requirement_current_state(
    user_message: &str,
    run_status: &str,
    waiting_for: Option<&str>,
    current_state_delta: &Value,
    runtime_artifacts: &RuntimeArtifactPaths,
) -> Value {
    json!({
        "summary": format!(
            "当前本地智能体需求状态={}{}；最近目标：{}",
            run_status,
            waiting_for
                .map(|value| format!("，waiting_for={value}"))
                .unwrap_or_default(),
            truncate_inline(user_message, 120)
        ),
        "completed": if run_status == "completed" {
            vec![truncate_inline(user_message, 160)]
        } else {
            Vec::<String>::new()
        },
        "capabilities_and_limits": [
            "本地 requirement 记录保存需求理解、上下文包、模型输入快照、动作和状态增量。",
            "完整模型 messages 只保存在本地记录中；服务端同步使用摘要和 hash。"
        ],
        "recent_artifacts": {
            "runtime_state_path": runtime_artifacts.state_path,
            "transcript_path": runtime_artifacts.transcript_path,
            "checkpoint_path": runtime_artifacts.checkpoint_path
        },
        "last_delta": current_state_delta
    })
}

fn current_task_node_value(task_tree: &planning::TaskTree) -> Value {
    task_tree
        .nodes
        .iter()
        .find(|node| node.node_id == task_tree.current_node_id)
        .map(|node| task_node_value(task_tree, node, true))
        .unwrap_or_else(|| json!({}))
}

fn task_branch_values(task_tree: &planning::TaskTree) -> Vec<Value> {
    task_tree
        .nodes
        .iter()
        .map(|node| task_node_value(task_tree, node, node.node_id == task_tree.current_node_id))
        .collect()
}

fn task_node_value(
    task_tree: &planning::TaskTree,
    node: &planning::TaskNode,
    is_current: bool,
) -> Value {
    let children_ids = task_tree
        .nodes
        .iter()
        .filter(|candidate| candidate.parent_id.as_deref() == Some(node.node_id.as_str()))
        .map(|candidate| candidate.node_id.clone())
        .collect::<Vec<_>>();
    json!({
        "id": node.node_id,
        "node_id": node.node_id,
        "parent_id": node.parent_id,
        "title": node.title,
        "status": node.status,
        "node_kind": node.node_type,
        "type": node.node_type,
        "is_current": is_current,
        "is_destructive": node.is_destructive,
        "verification_result": node.verification_result,
        "children_ids": children_ids,
        "summary": node.title,
    })
}

fn changed_or_inspected_targets(planned_tools: &[PlannedLocalTool]) -> Vec<String> {
    planned_tools
        .iter()
        .filter_map(|tool| {
            argument_string(&tool.arguments, "path")
                .or_else(|| argument_string(&tool.arguments, "target"))
                .or_else(|| argument_string(&tool.arguments, "file"))
        })
        .collect()
}

fn build_task_goal(
    session_id: &str,
    user_message: &str,
    model_request: &ModelStepRequest,
) -> TaskGoal {
    let targets = extract_file_path_candidates(user_message);
    let target_object = targets
        .last()
        .cloned()
        .or_else(|| infer_recent_target_path(&model_request.messages))
        .unwrap_or_else(|| "current user request".to_string());
    let intent = infer_requirement_task_type(user_message).to_string();
    let title = truncate_inline(user_message, 120);
    let mut success_criteria = vec![
        "围绕本轮用户目标推进，不以关键词命中强制副作用工具。".to_string(),
        "模型工具调用结果能回传到同一任务目标下继续判断。".to_string(),
        "最终状态必须有验证报告或明确阻塞原因。".to_string(),
    ];
    if intent == "modification" {
        success_criteria.push("修改类任务需要说明涉及目标、执行结果和验证证据。".to_string());
    } else if intent == "question" {
        success_criteria.push("查询类任务不要求写入文件，直接回答用户问题。".to_string());
    }
    let mut constraints = infer_requirement_constraints(user_message);
    constraints.push("高风险或副作用动作必须经过本地权限策略。".to_string());

    TaskGoal {
        version: "task-goal/v1".to_string(),
        goal_id: format!("goal_{session_id}"),
        title,
        user_request: user_message.to_string(),
        intent,
        target_object,
        success_criteria,
        constraints,
        created_at_epoch_ms: epoch_millis(),
    }
}

fn requirement_keywords(user_message: &str) -> Vec<String> {
    let mut keywords = extract_file_path_candidates(user_message);
    for token in user_message.split(|ch: char| {
        ch.is_whitespace()
            || matches!(
                ch,
                ',' | '，' | '.' | '。' | ':' | '：' | ';' | '；' | '(' | ')' | '（' | '）'
            )
    }) {
        let token = token.trim();
        if token.chars().count() >= 2 && keywords.len() < 12 {
            let value = token.chars().take(40).collect::<String>();
            if !keywords.iter().any(|item| item == &value) {
                keywords.push(value);
            }
        }
    }
    if keywords.is_empty() {
        keywords.push(truncate_inline(user_message, 40));
    }
    keywords.truncate(12);
    keywords
}

fn infer_requirement_capability(user_message: &str) -> String {
    if user_message.contains("修改") || user_message.contains("改造") {
        "modify_existing_artifact".to_string()
    } else if user_message.contains("修复") || user_message.contains("解决") {
        "fix_problem".to_string()
    } else if user_message.contains("查询") || user_message.contains("查看") {
        "answer_or_inspect".to_string()
    } else {
        "handle_current_request".to_string()
    }
}

fn infer_requirement_constraints(user_message: &str) -> Vec<String> {
    let mut constraints = Vec::new();
    if user_message.contains("不要兜底") || user_message.contains("不兜底") {
        constraints.push("禁止以兜底、兼容或静默降级掩盖根因。".to_string());
    }
    if user_message.contains("本质解决") || user_message.contains("根因") {
        constraints.push("优先定位并修正根因，收敛到唯一规范入口。".to_string());
    }
    if constraints.is_empty() {
        constraints.push("只围绕本轮用户输入处理，不主动扩大范围。".to_string());
    }
    constraints
}

fn build_context_lookup(user_message: &str, targets: &[String]) -> Vec<String> {
    let mut lookup = vec![
        "local requirement current_state".to_string(),
        "project context bundle".to_string(),
        "desktop tool manifest".to_string(),
    ];
    lookup.extend(
        targets
            .iter()
            .map(|target| format!("workspace target {target}")),
    );
    if user_message.contains("历史") || user_message.contains("最近") {
        lookup.push("recent requirement history".to_string());
    }
    lookup
}

fn infer_requirement_focus(user_message: &str) -> String {
    let capability = infer_requirement_capability(user_message);
    format!("{capability}: {}", truncate_inline(user_message, 120))
}

fn infer_requirement_task_type(user_message: &str) -> &'static str {
    if user_message.contains("删除")
        || user_message.contains("清空")
        || user_message.contains("移除")
        || user_message.contains("覆盖")
    {
        "destructive"
    } else if user_message.contains("部署")
        || user_message.contains("发布")
        || user_message.contains("上线")
    {
        "deployment"
    } else if user_message.contains("文档")
        || user_message.contains(".md")
        || user_message.contains("说明")
        || user_message.contains("计划")
    {
        "documentation"
    } else if user_message.contains("工作流")
        || user_message.contains("任务树")
        || user_message.contains("执行流")
        || user_message.contains("恢复续跑")
        || user_message.contains("MCP")
    {
        "governance"
    } else if user_message.contains("最近") || user_message.contains("历史") {
        "history_recall"
    } else if user_message.contains("修复") || user_message.contains("解决") {
        "bugfix"
    } else if user_message.contains("分析")
        || user_message.contains("看看")
        || user_message.contains("确认")
        || user_message.contains("为什么")
    {
        "analysis"
    } else if user_message.contains("修改") || user_message.contains("改造") {
        "modification"
    } else if user_message.contains("吗")
        || user_message.contains("?")
        || user_message.contains("？")
    {
        "question"
    } else {
        "other"
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

#[derive(Debug, Clone)]
struct ResponseFormattingResult {
    assistant_content: String,
    user_visible_error_summary: String,
    diagnostic: Value,
}

fn format_local_chat_response(
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
) -> ResponseFormattingResult {
    if agent_loop_ok
        && model_result.ok
        && !model_result.compat_text_tool_call_detected
        && !model_result.content.trim().is_empty()
    {
        let assistant_content =
            deployment_claim_safe_assistant_content(model_result.content.trim(), tool_results);
        return ResponseFormattingResult {
            assistant_content,
            user_visible_error_summary: String::new(),
            diagnostic: json!({
                "version": "response-format/v1",
                "visibility": "model_content",
                "diagnostic_separated": false,
                "deployment_claim_adjusted": deployment_claim_needs_adjustment(model_result.content.trim(), tool_results)
            }),
        };
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
            vec![
                "模型请求暂无返回信号，本轮未拿到完成或失败证据；已保留上下文等待恢复判断。"
                    .to_string(),
            ]
        } else {
            vec![
                "模型请求暂无返回信号，已执行的本机工具见下方摘要；不能据此判断任务失败。"
                    .to_string(),
            ]
        }
    } else if model_result.error_code == "model.connection_timeout" {
        if tool_results.is_empty() {
            vec!["模型请求暂无返回信号，本轮未执行任何本机工具，也未修改文件。".to_string()]
        } else {
            vec![
                "模型请求暂无返回信号，已执行的本机工具见下方摘要；任务状态需要恢复判断。"
                    .to_string(),
            ]
        }
    } else if model_step_failed {
        if tool_results.is_empty() {
            vec!["模型调用失败，本轮未执行任何本机工具，也未修改文件。".to_string()]
        } else {
            vec!["模型调用失败，已执行的本机工具见下方摘要；本轮尚未完成最终修改。".to_string()]
        }
    } else if loop_failed {
        match stopped_reason {
            "tool_no_signal" => {
                vec![
                    "本地智能体已暂停：当前步骤暂无完成或失败证据，可能仍在执行或需要恢复判断。"
                        .to_string(),
                ]
            }
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
    let user_visible_error_summary = user_visible_model_error_summary(model_result, loop_error);
    if !model_result.summary.trim().is_empty() {
        lines.push(format!(
            "模型说明：{}",
            user_visible_model_summary(model_result)
        ));
    }
    if loop_failed {
        let detail = if !loop_summary.trim().is_empty() {
            loop_summary.trim()
        } else {
            loop_error.trim()
        };
        if !detail.is_empty() {
            lines.push(format!(
                "停止原因：{}",
                truncate_inline(&strip_response_diagnostic_tail(detail), 180)
            ));
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
                    "最近失败工具：{} {}。完整诊断见运行详情。",
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
    } else if model_step_failed {
        lines.push(format!(
            "失败摘要：{}。完整诊断见运行详情。",
            user_visible_error_summary
        ));
    }
    ResponseFormattingResult {
        assistant_content: lines.join("\n"),
        user_visible_error_summary,
        diagnostic: json!({
            "version": "response-format/v1",
            "diagnostic_separated": true,
            "model_error_code": model_result.error_code,
            "model_error": model_result.error,
            "model_summary": model_result.summary,
            "loop_error": loop_error,
            "loop_summary": loop_summary,
            "stopped_reason": stopped_reason,
            "tool_failure_count": tool_results.iter().filter(|item| !item.ok).count()
        }),
    }
}

fn deployment_claim_safe_assistant_content(
    content: &str,
    tool_results: &[super::types::ToolExecutionResult],
) -> String {
    if !deployment_claim_needs_adjustment(content, tool_results) {
        return content.trim().to_string();
    }
    let mut lines = vec![
        "部署操作尚未确认成功。".to_string(),
        "后端没有返回 deployment.status=success，因此不能判定为“部署完成”。".to_string(),
    ];
    if let Some(summary) = latest_deploy_upload_summary(tool_results) {
        lines.push(format!("工具结果：{summary}"));
    }
    lines.push("下面是模型原始总结，已按实际状态降级为参考：".to_string());
    lines.push(strip_deployment_success_claims(content));
    lines.join("\n")
}

fn deployment_claim_needs_adjustment(
    content: &str,
    tool_results: &[super::types::ToolExecutionResult],
) -> bool {
    content_claims_deployment_success(content)
        && has_deploy_upload_without_confirmed_success(tool_results)
}

fn content_claims_deployment_success(content: &str) -> bool {
    let normalized = content.trim();
    if normalized.is_empty() {
        return false;
    }
    [
        "部署完成",
        "部署成功",
        "已部署",
        "已经部署",
        "上线完成",
        "上线成功",
        "发布完成",
        "发布成功",
    ]
    .iter()
    .any(|needle| normalized.contains(needle))
}

fn has_deploy_upload_without_confirmed_success(
    tool_results: &[super::types::ToolExecutionResult],
) -> bool {
    tool_results.iter().any(|result| {
        result.ok
            && matches!(
                result.name.trim(),
                "upload_deploy_artifact" | "deploy_workspace_files_to_target"
            )
            && !deploy_upload_confirmed_success(result)
    })
}

fn deploy_upload_confirmed_success(result: &super::types::ToolExecutionResult) -> bool {
    result
        .content
        .get("deployment_confirmed_success")
        .and_then(Value::as_bool)
        .unwrap_or(false)
        || result
            .content
            .get("response")
            .and_then(|value| value.get("deployment"))
            .and_then(|value| value.get("status"))
            .and_then(Value::as_str)
            .map(str::trim)
            == Some("success")
}

fn latest_deploy_upload_summary(
    tool_results: &[super::types::ToolExecutionResult],
) -> Option<String> {
    tool_results
        .iter()
        .rev()
        .find(|result| {
            result.ok
                && matches!(
                    result.name.trim(),
                    "upload_deploy_artifact" | "deploy_workspace_files_to_target"
                )
        })
        .map(|result| result.summary.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn strip_deployment_success_claims(content: &str) -> String {
    content
        .replace("## ✅ 部署完成", "## 产物上传结果")
        .replace("### ✅ 部署完成", "### 产物上传结果")
        .replace("✅ 部署完成", "产物已上传")
        .replace("部署完成", "产物上传完成")
        .replace("部署成功", "产物上传成功")
        .replace("上线完成", "产物上传完成")
        .replace("上线成功", "产物上传成功")
        .replace("发布完成", "产物上传完成")
        .replace("发布成功", "产物上传成功")
}

#[allow(clippy::too_many_arguments)]
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
    format_local_chat_response(
        project_id,
        workspace_root,
        user_message,
        history,
        model_result,
        tool_results,
        planned_tools,
        agent_loop_ok,
        awaiting_permission,
        stopped_reason,
        loop_summary,
        loop_error,
    )
    .assistant_content
}

fn user_visible_model_summary(model_result: &ModelStepResult) -> String {
    if model_result.ok {
        return truncate_inline(&model_result.summary, 240);
    }
    user_visible_model_error_summary(model_result, &model_result.error)
}

fn user_visible_model_error_summary(
    model_result: &ModelStepResult,
    fallback_error: &str,
) -> String {
    let detail = if !model_result.summary.trim().is_empty() {
        model_result.summary.trim()
    } else if !model_result.error.trim().is_empty() {
        model_result.error.trim()
    } else {
        fallback_error.trim()
    };
    let detail = strip_response_diagnostic_tail(detail);
    let code = model_result.error_code.trim();
    let summary = if detail.trim().is_empty() {
        "模型步骤失败".to_string()
    } else {
        truncate_inline(detail.trim(), 180)
    };
    if code.is_empty() {
        summary
    } else {
        format!("{code} {summary}")
    }
}

fn strip_response_diagnostic_tail(detail: &str) -> String {
    let mut cleaned = detail.trim().to_string();
    for marker in [" request={", " request=[", "\nrequest={", "\nrequest=["] {
        if let Some(index) = cleaned.find(marker) {
            cleaned.truncate(index);
        }
    }
    for marker in [" response_headers={", "\nresponse_headers={"] {
        if let Some(index) = cleaned.find(marker) {
            cleaned.truncate(index);
        }
    }
    cleaned.trim().to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PlannedLocalTool {
    tool_call_id: String,
    name: String,
    arguments: Value,
    summary: String,
}

struct ReplayedPermissionTool {
    tool: PlannedLocalTool,
    result: super::types::ToolExecutionResult,
    reasoning_content: String,
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeModelMessage {
    role: String,
    content: String,
    reasoning_content: String,
    content_parts: Vec<RuntimeModelContentPart>,
    tool_call_id: Option<String>,
    tool_calls: Vec<PlannedLocalTool>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum RuntimeModelContentPart {
    Text { text: String },
    ImageUrl { image_url: RuntimeModelImageUrl },
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeModelImageUrl {
    url: String,
}

impl RuntimeModelMessage {
    fn simple(role: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: role.into(),
            content: content.into(),
            reasoning_content: String::new(),
            content_parts: Vec::new(),
            tool_call_id: None,
            tool_calls: Vec::new(),
        }
    }

    fn with_content_parts(
        role: impl Into<String>,
        content: impl Into<String>,
        content_parts: Vec<RuntimeModelContentPart>,
    ) -> Self {
        Self {
            role: role.into(),
            content: content.into(),
            reasoning_content: String::new(),
            content_parts,
            tool_call_id: None,
            tool_calls: Vec::new(),
        }
    }

    fn assistant_tool_call(
        content: impl Into<String>,
        reasoning_content: impl Into<String>,
        tool_calls: Vec<PlannedLocalTool>,
    ) -> Self {
        Self {
            role: "assistant".to_string(),
            content: content.into(),
            reasoning_content: reasoning_content.into(),
            content_parts: Vec::new(),
            tool_call_id: None,
            tool_calls,
        }
    }

    fn tool_observation(tool_call_id: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: "tool".to_string(),
            content: content.into(),
            reasoning_content: String::new(),
            content_parts: Vec::new(),
            tool_call_id: Some(tool_call_id.into()),
            tool_calls: Vec::new(),
        }
    }
}

fn replay_pending_permission_tool_if_available(
    workspace_root: &PathBuf,
    project_id: &str,
    chat_session_id: &str,
    runtime_session_id: &str,
    request: &LocalChatRequest,
    event_sink: Option<&dyn Fn(Value)>,
) -> Option<ReplayedPermissionTool> {
    let decision = request.permission_decision.as_ref()?;
    if decision.decision.trim() == "deny" {
        return None;
    }
    let (pending_tool, reasoning_content) =
        recover_pending_permission_tool(workspace_root, project_id, chat_session_id, decision)?;
    let mut tool = pending_tool;
    tool.summary = if tool.summary.trim().is_empty() {
        "继续已授权的本地工具调用".to_string()
    } else {
        format!("{}；继续已授权的本地工具调用", tool.summary.trim())
    };
    emit_tool_call_started_event(
        event_sink,
        runtime_session_id,
        chat_session_id,
        &tool,
        1,
        1,
        None,
    );
    emit_command_started_for_tool(
        event_sink,
        runtime_session_id,
        chat_session_id,
        &tool,
        request.permission_decision.as_ref(),
    );
    let command_stream_index = Cell::new(0usize);
    let command_stream_sink = |stream: &str, text: &str| {
        let index = command_stream_index.get() + 1;
        command_stream_index.set(index);
        if let Some(sink) = event_sink {
            emit_command_output_chunk(
                sink,
                runtime_session_id,
                chat_session_id,
                &tool,
                &command_arg(&tool),
                stream,
                text,
                false,
                Some(index),
            );
        }
    };
    let tool_request = ToolExecutionRequest {
        tool_call_id: Some(tool.tool_call_id.clone()),
        name: tool.name.clone(),
        arguments: tool_arguments_with_backend_context(
            &tool,
            &request.project_id,
            request.backend_context.as_ref(),
            tool.arguments.clone(),
        ),
        workspace_path: workspace_root.to_string_lossy().to_string(),
        permission_decision: Some(decision.clone()),
    };
    let result = if tool.name.trim() == "run_command" {
        execute_tool_with_command_output_sink(tool_request, Some(&command_stream_sink))
    } else {
        execute_tool(tool_request)
    };
    emit_command_result_events(
        event_sink,
        runtime_session_id,
        chat_session_id,
        &tool,
        &result,
    );
    emit_tool_result_event(
        event_sink,
        runtime_session_id,
        chat_session_id,
        &tool,
        &result,
    );
    Some(ReplayedPermissionTool {
        tool,
        result,
        reasoning_content,
    })
}

fn recover_pending_permission_tool(
    workspace_root: &PathBuf,
    project_id: &str,
    chat_session_id: &str,
    decision: &super::types::PermissionDecisionInput,
) -> Option<(PlannedLocalTool, String)> {
    let request_id = decision.request_id.as_deref().map(str::trim)?;
    if request_id.is_empty() {
        return None;
    }
    let state = recover_runtime_state(workspace_root, project_id, chat_session_id).ok()?;
    if state["run_state"]["status"].as_str().unwrap_or_default() != "waiting_approval" {
        return None;
    }
    let tool_call_id = state["tool_results"]
        .as_array()?
        .iter()
        .find_map(|result| {
            let error_code = value_str_any(result, &["errorCode", "error_code"]);
            if error_code != "permission.required" {
                return None;
            }
            let result_request_id = value_str_any(
                &result["content"]["permissionRequest"],
                &["requestId", "request_id"],
            );
            if result_request_id != request_id {
                return None;
            }
            let tool_call_id = value_str_any(result, &["toolCallId", "tool_call_id"]);
            if tool_call_id.is_empty() {
                None
            } else {
                Some(tool_call_id)
            }
        })?;
    let tool = state["model_runtime"]["agent_loop"]["planned_tools"]
        .as_array()?
        .iter()
        .find(|tool| value_str_any(tool, &["tool_call_id", "toolCallId"]) == tool_call_id)
        .and_then(|tool| serde_json::from_value::<PlannedLocalTool>(tool.clone()).ok())?;
    let reasoning_content = state["model_runtime"]["agent_loop"]["model_steps"]
        .as_array()
        .and_then(|steps| {
            steps.iter().find_map(|step| {
                let has_tool_call = step["tool_calls"].as_array().is_some_and(|tools| {
                    tools.iter().any(|tool| {
                        value_str_any(tool, &["tool_call_id", "toolCallId"]) == tool_call_id
                    })
                });
                if has_tool_call {
                    Some(value_str_any(
                        step,
                        &["reasoning_content", "reasoningContent"],
                    ))
                } else {
                    None
                }
            })
        })
        .filter(|value| !value.trim().is_empty())?;
    Some((tool, reasoning_content))
}

fn value_str_any(value: &Value, keys: &[&str]) -> String {
    keys.iter()
        .find_map(|key| value.get(*key).and_then(Value::as_str))
        .unwrap_or_default()
        .trim()
        .to_string()
}

fn merge_runtime_events(primary: &[Value], secondary: &[Value]) -> Vec<Value> {
    let mut merged = Vec::new();
    for event in primary.iter().chain(secondary.iter()) {
        let event_id = event
            .get("event_id")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim();
        let already_present = !event_id.is_empty()
            && merged.iter().any(|existing: &Value| {
                existing
                    .get("event_id")
                    .and_then(Value::as_str)
                    .map(|value| value == event_id)
                    .unwrap_or(false)
            });
        if !already_present {
            merged.push(event.clone());
        }
    }
    merged
}

#[derive(Debug, Clone, Serialize)]
struct AgentLoopResult {
    model_steps: Vec<ModelStepResult>,
    model_input_snapshots: Vec<Value>,
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
            "repeated_failure" | "verification_failed" | "tool_no_signal" => return false,
            _ => {}
        }
        let final_result = self.final_model_result();
        final_result.ok || matches!(final_result.status.as_str(), "mock" | "unconfigured")
    }

    fn error_code(&self) -> String {
        match self.stopped_reason.as_str() {
            "repeated_failure" => "agent_loop.repeated_failure".to_string(),
            "verification_failed" => "agent_loop.verification_failed".to_string(),
            "tool_no_signal" => "agent_loop.no_signal".to_string(),
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
            "tool_no_signal" => {
                "tool stopped without completion evidence; task state is no_signal".to_string()
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
                    "model_input_snapshots": self.model_input_snapshots,
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
    prompt_stack: &PromptStack,
    workspace_root: &PathBuf,
    permission_decision: Option<super::types::PermissionDecisionInput>,
    event_sink: Option<&dyn Fn(Value)>,
) -> AgentLoopResult {
    run_agent_loop_with(
        run_key,
        runtime_session_id,
        base_request,
        prompt_stack,
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
    prompt_stack: &PromptStack,
    workspace_root: &PathBuf,
    permission_decision: Option<super::types::PermissionDecisionInput>,
    event_sink: Option<&dyn Fn(Value)>,
    model_runner: &dyn Fn(&ModelStepRequest) -> ModelStepResult,
    tool_runner: &dyn Fn(ToolExecutionRequest) -> super::types::ToolExecutionResult,
) -> AgentLoopResult {
    let mut messages = base_request.messages.clone();
    let mut model_steps = Vec::new();
    let mut model_input_snapshots = Vec::new();
    let mut planned_tools = Vec::new();
    let mut tool_results: Vec<super::types::ToolExecutionResult> = Vec::new();
    let mut candidate_solutions = Vec::new();
    let mut attempts = Vec::new();
    let mut verification_reprompts = 0usize;
    let mut permission_cache = load_session_permission_cache(workspace_root, run_key);
    let stopped_reason: String;
    let mut awaiting_permission = false;

    loop {
        let request = base_request.with_messages(messages.clone());
        let model_step_index = model_steps.len() + 1;
        model_input_snapshots.push(build_task_processing_snapshot(
            runtime_session_id,
            model_step_index,
            &request,
            prompt_stack,
        ));
        emit_model_call_started_event(
            event_sink,
            runtime_session_id,
            run_key,
            model_step_index,
            &request,
        );
        let model_result = model_runner(&request);
        let current_planned_tools = rank_local_tool_candidates(
            plan_local_tools(run_key, &model_result)
                .into_iter()
                .map(|tool| {
                    repair_planned_tool_arguments(
                        tool,
                        &messages,
                        Some(&model_result),
                        workspace_root,
                    )
                })
                .collect(),
            &attempts,
        );
        let model_content = model_result.content.clone();
        model_steps.push(model_result.clone());
        emit_progress_update_event(
            event_sink,
            runtime_session_id,
            run_key,
            model_steps.len(),
            &model_result,
            &current_planned_tools,
            &request,
        );
        emit_model_step_event(
            event_sink,
            runtime_session_id,
            run_key,
            model_steps.len(),
            &model_result,
            &request,
        );

        if !model_result.ok {
            stopped_reason = "model_failed".to_string();
            break;
        }
        if current_planned_tools.is_empty() {
            if has_unresolved_failed_attempt(&attempts, &model_result.content) {
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
            model_result.reasoning_content.clone(),
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
                Some(&request),
            );
            emit_command_started_for_tool(
                event_sink,
                runtime_session_id,
                run_key,
                &tool,
                effective_permission_decision.as_ref(),
            );
            let command_stream_index = Cell::new(0usize);
            let command_stream_sink = |stream: &str, text: &str| {
                let index = command_stream_index.get() + 1;
                command_stream_index.set(index);
                if let Some(sink) = event_sink {
                    emit_command_output_chunk(
                        sink,
                        runtime_session_id,
                        run_key,
                        &tool,
                        &command_arg(&tool),
                        stream,
                        text,
                        false,
                        Some(index),
                    );
                }
            };
            let tool_request = ToolExecutionRequest {
                tool_call_id: Some(tool.tool_call_id.clone()),
                name: tool.name.clone(),
                arguments: tool_arguments_with_backend_context(
                    &tool,
                    &request.project_id,
                    request.backend_context.as_ref(),
                    tool_arguments_with_file_access_policy(&tool, &request),
                ),
                workspace_path: workspace_root.to_string_lossy().to_string(),
                permission_decision: effective_permission_decision.clone(),
            };
            let result = if let Some(drift_result) = drift_check_tool_result(&tool, &request) {
                drift_result
            } else if tool.name.trim() == "run_command" {
                execute_tool_with_command_output_sink(tool_request, Some(&command_stream_sink))
            } else {
                tool_runner(tool_request)
            };
            emit_command_result_events(event_sink, runtime_session_id, run_key, &tool, &result);
            emit_tool_result_event(event_sink, runtime_session_id, run_key, &tool, &result);
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
                    model_input_snapshots,
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
            let no_signal = tool_result_status(&result) == "no_signal";
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
            let continue_after_recoverable_failure =
                should_continue_after_recoverable_failure(&result, &attempts);
            attempts.push(attempt);
            candidate.status = if result.ok { "passed" } else { "abandoned" }.to_string();
            candidate_solutions.push(candidate);
            tool_results.push(result);
            if no_signal {
                stopped_reason = "tool_no_signal".to_string();
                return finalize_agent_loop_result(
                    model_steps,
                    model_input_snapshots,
                    planned_tools,
                    tool_results,
                    candidate_solutions,
                    attempts,
                    stopped_reason,
                    awaiting_permission,
                );
            }
            if repeated_failure && !continue_after_recoverable_failure {
                stopped_reason = "repeated_failure".to_string();
                return finalize_agent_loop_result(
                    model_steps,
                    model_input_snapshots,
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
        model_input_snapshots,
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
    request: &ModelStepRequest,
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
                "content_preview": truncate_inline(&result.content, 700),
                "reasoning_content": result.reasoning_content,
                "error_code": result.error_code,
                "error": result.error,
                "tool_call_count": result.tool_calls.len(),
                "task_goal": request.task_goal.as_ref(),
                "current_task_node": request
                    .task_tree
                    .as_ref()
                    .map(current_task_node_value)
                    .unwrap_or_else(|| json!({})),
                "created_at_epoch_ms": epoch_millis(),
            }),
            epoch_millis(),
        ));
    }
}

fn emit_progress_update_event(
    event_sink: Option<&dyn Fn(Value)>,
    runtime_session_id: &str,
    chat_session_id: &str,
    index: usize,
    result: &ModelStepResult,
    planned_tools: &[PlannedLocalTool],
    request: &ModelStepRequest,
) {
    let planned_tool_count = planned_tools.len();
    if planned_tool_count == 0 {
        return;
    }
    let summary = progress_update_summary(result, planned_tools);
    if summary.trim().is_empty() {
        return;
    }
    let current_focus = progress_update_focus(result, planned_tools);
    let next_action = progress_update_next_action(planned_tools);
    let planned_tool_previews = progress_update_tool_previews(planned_tools);
    let arguments_preview = planned_tool_previews
        .iter()
        .take(3)
        .map(|item| {
            let name = item.get("name").and_then(Value::as_str).unwrap_or("tool");
            let preview = item
                .get("arguments_preview")
                .and_then(Value::as_str)
                .unwrap_or("");
            format!("{name} {preview}")
        })
        .collect::<Vec<_>>()
        .join("；");
    if let Some(sink) = event_sink {
        sink(progress_update_event(
            format!("evt_{runtime_session_id}_progress_{index}"),
            runtime_session_id,
            chat_session_id,
            json!({
                "index": index,
                "status": "running",
                "summary": summary,
                "current_focus": current_focus,
                "work_direction": current_focus,
                "next_action": next_action,
                "tool_call_count": planned_tool_count,
                "planned_tools": planned_tool_previews,
                "arguments_preview": truncate_inline(&arguments_preview, 2_000),
                "task_goal": request.task_goal.as_ref(),
                "current_task_node": request
                    .task_tree
                    .as_ref()
                    .map(current_task_node_value)
                    .unwrap_or_else(|| json!({})),
                "provider_id": result.provider_id.as_str(),
                "model_name": result.model_name.as_str(),
                "created_at_epoch_ms": epoch_millis(),
            }),
            epoch_millis(),
        ));
    }
}

fn progress_update_summary(result: &ModelStepResult, planned_tools: &[PlannedLocalTool]) -> String {
    let content_summary = truncate_inline(&result.content, 500);
    if !content_summary.trim().is_empty() {
        return content_summary;
    }
    let mut tool_summaries = planned_tools
        .iter()
        .take(3)
        .map(describe_planned_tool_intent)
        .filter(|summary| !summary.trim().is_empty())
        .collect::<Vec<_>>();
    if planned_tools.len() > tool_summaries.len() {
        tool_summaries.push(format!(
            "另有 {} 个工具调用",
            planned_tools.len() - tool_summaries.len()
        ));
    }
    if tool_summaries.is_empty() {
        return format!("准备执行模型请求的 {} 个本地工具调用", planned_tools.len());
    }
    truncate_inline(&format!("准备{}", tool_summaries.join("；")), 500)
}

fn progress_update_focus(result: &ModelStepResult, planned_tools: &[PlannedLocalTool]) -> String {
    let content_summary = truncate_inline(&result.content, 220);
    if !content_summary.trim().is_empty() {
        return content_summary;
    }
    let has_write = planned_tools
        .iter()
        .any(|tool| matches!(tool.name.trim(), "write_file" | "apply_patch"));
    if has_write {
        return "进入代码修改阶段".to_string();
    }
    let has_read = planned_tools.iter().any(|tool| {
        matches!(
            tool.name.trim(),
            "list_files" | "read_file" | "search_files" | "search_text" | "get_file_info"
        )
    });
    if has_read {
        return "收集实现所需的文件结构和现有页面风格".to_string();
    }
    "推进当前任务".to_string()
}

fn progress_update_next_action(planned_tools: &[PlannedLocalTool]) -> String {
    if planned_tools.is_empty() {
        return String::new();
    }
    let descriptions = planned_tools
        .iter()
        .take(3)
        .map(describe_planned_tool_intent)
        .filter(|value| !value.trim().is_empty())
        .collect::<Vec<_>>();
    if descriptions.is_empty() {
        return format!("执行 {} 个本地工具调用", planned_tools.len());
    }
    let mut text = descriptions.join("；");
    if planned_tools.len() > descriptions.len() {
        text.push_str(&format!(
            "；另有 {} 个工具调用",
            planned_tools.len() - descriptions.len()
        ));
    }
    truncate_inline(&text, 360)
}

fn progress_update_tool_previews(planned_tools: &[PlannedLocalTool]) -> Vec<Value> {
    planned_tools
        .iter()
        .map(|tool| {
            let arguments_preview = format_tool_arguments_preview(&tool.arguments, 2_000);
            json!({
                "tool_call_id": tool.tool_call_id.as_str(),
                "name": tool.name.as_str(),
                "summary": tool.summary.as_str(),
                "arguments": summarize_tool_arguments(&tool.arguments),
                "arguments_preview": arguments_preview,
            })
        })
        .collect()
}

fn format_tool_arguments_preview(arguments: &Value, limit: usize) -> String {
    let preview = summarize_tool_arguments(arguments);
    serde_json::to_string(&preview)
        .map(|value| truncate_inline(&value, limit))
        .unwrap_or_default()
}

fn summarize_tool_arguments(arguments: &Value) -> Value {
    match arguments {
        Value::Object(map) => {
            let mut summarized = serde_json::Map::new();
            for (key, value) in map {
                summarized.insert(key.clone(), summarize_tool_argument_value(key, value));
            }
            Value::Object(summarized)
        }
        other => other.clone(),
    }
}

fn summarize_tool_argument_value(key: &str, value: &Value) -> Value {
    let Some(text) = value.as_str() else {
        return value.clone();
    };
    if !matches!(key, "content" | "patch") {
        return value.clone();
    }
    let char_count = text.chars().count();
    if char_count <= 800 {
        return json!({
            "chars": char_count,
            "value": text,
        });
    }
    let head = text.chars().take(500).collect::<String>();
    let tail = text
        .chars()
        .rev()
        .take(200)
        .collect::<String>()
        .chars()
        .rev()
        .collect::<String>();
    json!({
        "chars": char_count,
        "head": head,
        "tail": tail,
        "truncated_for_preview": true,
    })
}

fn describe_planned_tool_intent(tool: &PlannedLocalTool) -> String {
    match tool.name.trim() {
        "list_files" => {
            let path = argument_string(&tool.arguments, "path").unwrap_or_else(|| ".".to_string());
            if path.trim() == "." {
                "查看工作区目录，确认可复用页面和实现入口".to_string()
            } else {
                format!("查看 {} 目录，确认已有文件结构", path.trim())
            }
        }
        "read_file" => {
            let path = argument_string(&tool.arguments, "path").unwrap_or_default();
            let range = planned_tool_line_range(&tool.arguments);
            if path.trim().is_empty() {
                "读取目标文件内容，判断下一步修改位置".to_string()
            } else if path.contains("register") {
                format!("读取 {path}{range}，复用注册页的视觉风格和表单交互")
            } else if path.contains("login") {
                format!("读取 {path}{range}，判断现有登录页能否复用或改造")
            } else {
                format!("读取 {path}{range}，定位实现需要参考的代码")
            }
        }
        "search_text" | "search_files" => {
            let query = argument_string(&tool.arguments, "query")
                .or_else(|| argument_string(&tool.arguments, "pattern"))
                .unwrap_or_default();
            let glob = argument_string(&tool.arguments, "glob").unwrap_or_default();
            if query.trim().is_empty() {
                "搜索相关文件，定位实现入口".to_string()
            } else if glob.trim().is_empty() {
                format!("搜索 “{}”，定位相关实现位置", query.trim())
            } else {
                format!(
                    "在 {} 中搜索 “{}”，定位相关实现位置",
                    glob.trim(),
                    query.trim()
                )
            }
        }
        "write_file" => {
            let path = argument_string(&tool.arguments, "path").unwrap_or_default();
            if path.trim().is_empty() {
                "写入新文件，产出实现结果".to_string()
            } else {
                format!("写入 {path}，产出实现结果")
            }
        }
        "apply_patch" => "应用代码补丁，修改现有实现".to_string(),
        "run_command" => {
            let cmd = command_arg(tool);
            if cmd.trim().is_empty() {
                "运行命令验证当前实现".to_string()
            } else {
                format!("运行 `{}` 验证当前实现", truncate_inline(&cmd, 120))
            }
        }
        _ => {
            let summary = tool.summary.trim();
            if summary.is_empty() {
                format!("调用本地工具 {}", tool.name.trim())
            } else {
                summary.to_string()
            }
        }
    }
}

fn tool_arguments_with_file_access_policy(
    tool: &PlannedLocalTool,
    request: &ModelStepRequest,
) -> Value {
    if !matches!(tool.name.trim(), "read_file" | "search_text") {
        return tool.arguments.clone();
    }
    let mut arguments = tool.arguments.clone();
    let Some(object) = arguments.as_object_mut() else {
        return arguments;
    };
    object.insert(
        "file_access_policy".to_string(),
        build_file_access_policy_for_request(request),
    );
    arguments
}

fn tool_arguments_with_backend_context(
    tool: &PlannedLocalTool,
    project_id: &str,
    backend_context: Option<&LocalBackendContext>,
    mut arguments: Value,
) -> Value {
    if !matches!(
        tool.name.trim(),
        "get_project_deploy_options"
            | "upload_deploy_artifact"
            | "deploy_workspace_files_to_target"
    ) {
        return arguments;
    }
    let Some(context) = backend_context else {
        return arguments;
    };
    let Some(object) = arguments.as_object_mut() else {
        return arguments;
    };
    if object
        .get("project_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .is_none()
    {
        let normalized_project_id = project_id.trim();
        if !normalized_project_id.is_empty() {
            object.insert("project_id".to_string(), json!(normalized_project_id));
        }
    }
    object.insert(
        "_backend_api_base_url".to_string(),
        json!(context.api_base_url.trim()),
    );
    object.insert("_backend_token".to_string(), json!(context.token.trim()));
    arguments
}

fn build_file_access_policy_for_request(request: &ModelStepRequest) -> Value {
    const CLI_ENTRY_FILES: [&str; 3] = ["AGENTS.md", "CLAUDE.md", "HERMES.md"];
    let ai_entry_file = normalize_policy_path(&request.ai_entry_file);
    let user_message_lower = request.user_message.to_lowercase();
    let explicit_cli_entry_files = CLI_ENTRY_FILES
        .iter()
        .filter_map(|name| {
            let normalized = normalize_policy_path(name);
            if !normalized.is_empty() && user_message_lower.contains(&normalized.to_lowercase()) {
                Some(normalized)
            } else {
                None
            }
        })
        .collect::<Vec<_>>();
    json!({
        "surface": "desktop_project_chat",
        "ai_entry_file": ai_entry_file,
        "cli_entry_files": CLI_ENTRY_FILES.map(normalize_policy_path),
        "explicit_cli_entry_files": explicit_cli_entry_files,
    })
}

fn normalize_policy_path(value: &str) -> String {
    value
        .trim()
        .replace('\\', "/")
        .trim_start_matches("./")
        .to_string()
}

fn planned_tool_line_range(arguments: &Value) -> String {
    let Some(start) = arguments.get("start_line").and_then(Value::as_i64) else {
        return String::new();
    };
    let end = arguments.get("end_line").and_then(Value::as_i64);
    match end {
        Some(end) if end > start => format!(" 第 {start}-{end} 行"),
        _ => format!(" 第 {start} 行起"),
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
                "task_goal": request.task_goal.as_ref(),
                "current_task_node": request
                    .task_tree
                    .as_ref()
                    .map(current_task_node_value)
                    .unwrap_or_else(|| json!({})),
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
    request: Option<&ModelStepRequest>,
) {
    if let Some(sink) = event_sink {
        let arguments_preview = format_tool_arguments_preview(&tool.arguments, 500);
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
                "task_goal": request.and_then(|item| item.task_goal.as_ref()),
                "current_task_node": request
                    .and_then(|item| item.task_tree.as_ref())
                    .map(current_task_node_value)
                    .unwrap_or_else(|| json!({})),
                "created_at_epoch_ms": epoch_millis(),
            }),
            epoch_millis(),
        ));
    }
}

fn emit_command_started_for_tool(
    event_sink: Option<&dyn Fn(Value)>,
    runtime_session_id: &str,
    chat_session_id: &str,
    tool: &PlannedLocalTool,
    permission_decision: Option<&super::types::PermissionDecisionInput>,
) {
    if !should_emit_command_execution_events(tool, permission_decision) {
        return;
    }
    let Some(sink) = event_sink else {
        return;
    };
    let cmd = command_arg(tool);
    let cwd = argument_string(&tool.arguments, "cwd").unwrap_or_else(|| ".".to_string());
    sink(command_started_event(
        format!(
            "evt_{}_command_{}_started",
            runtime_session_id,
            sanitize_path_segment(&tool.tool_call_id)
        ),
        runtime_session_id,
        chat_session_id,
        json!({
            "tool_call_id": tool.tool_call_id.as_str(),
            "tool_name": tool.name.as_str(),
            "cmd": cmd,
            "cwd": cwd,
            "status": "running",
            "created_at_epoch_ms": epoch_millis(),
        }),
        epoch_millis(),
    ));
}

fn emit_command_result_events(
    event_sink: Option<&dyn Fn(Value)>,
    runtime_session_id: &str,
    chat_session_id: &str,
    tool: &PlannedLocalTool,
    result: &super::types::ToolExecutionResult,
) {
    if tool.name.trim() != "run_command" || result.error_code == "permission.required" {
        return;
    }
    let Some(sink) = event_sink else {
        return;
    };
    let cmd = command_arg(tool);
    let cwd = result
        .content
        .get("cwd")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .or_else(|| argument_string(&tool.arguments, "cwd"))
        .unwrap_or_else(|| ".".to_string());
    let stdout = result
        .content
        .get("stdout")
        .and_then(Value::as_str)
        .unwrap_or("");
    let stderr = result
        .content
        .get("stderr")
        .and_then(Value::as_str)
        .unwrap_or("");
    let streamed = result
        .content
        .get("streamed")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if !streamed && !stdout.trim().is_empty() {
        emit_command_output_chunk(
            sink,
            runtime_session_id,
            chat_session_id,
            tool,
            &cmd,
            "stdout",
            stdout,
            false,
            None,
        );
    }
    if !streamed && !stderr.trim().is_empty() {
        emit_command_output_chunk(
            sink,
            runtime_session_id,
            chat_session_id,
            tool,
            &cmd,
            "stderr",
            stderr,
            false,
            None,
        );
    }
    if result.ok && stdout.trim().is_empty() && stderr.trim().is_empty() {
        emit_command_output_chunk(
            sink,
            runtime_session_id,
            chat_session_id,
            tool,
            &cmd,
            "stdout",
            "(no output)",
            true,
            None,
        );
    }
    sink(command_finished_event(
        format!(
            "evt_{}_command_{}_finished",
            runtime_session_id,
            sanitize_path_segment(&tool.tool_call_id)
        ),
        runtime_session_id,
        chat_session_id,
        json!({
            "tool_call_id": tool.tool_call_id.as_str(),
            "tool_name": tool.name.as_str(),
            "cmd": cmd,
            "cwd": cwd,
            "ok": result.ok,
            "status": tool_result_status(result),
            "terminal": result.content.get("terminal").and_then(Value::as_bool).unwrap_or(result.ok || result.error_code != "tool.timeout"),
            "requires_judgement": result.content.get("requires_judgement").and_then(Value::as_bool).unwrap_or(false),
            "exit_code": result.content.get("exit_code").and_then(Value::as_i64),
            "duration_ms": result.content.get("duration_ms").and_then(Value::as_u64),
            "summary": result.summary.as_str(),
            "error_code": result.error_code.as_str(),
            "error": result.error.as_str(),
            "created_at_epoch_ms": epoch_millis(),
        }),
        epoch_millis(),
    ));
}

fn emit_command_output_chunk(
    sink: &dyn Fn(Value),
    runtime_session_id: &str,
    chat_session_id: &str,
    tool: &PlannedLocalTool,
    cmd: &str,
    stream: &str,
    text: &str,
    empty: bool,
    chunk_index: Option<usize>,
) {
    let chunk_suffix = chunk_index
        .map(|index| index.to_string())
        .unwrap_or_else(|| "final".to_string());
    sink(command_output_chunk_event(
        format!(
            "evt_{}_command_{}_{}_chunk_{}",
            runtime_session_id,
            sanitize_path_segment(&tool.tool_call_id),
            stream,
            chunk_suffix
        ),
        runtime_session_id,
        chat_session_id,
        json!({
            "tool_call_id": tool.tool_call_id.as_str(),
            "tool_name": tool.name.as_str(),
            "cmd": cmd,
            "stream": stream,
            "text": truncate_inline(text, 4_000),
            "empty": empty,
            "created_at_epoch_ms": epoch_millis(),
        }),
        epoch_millis(),
    ));
}

fn should_emit_command_execution_events(
    tool: &PlannedLocalTool,
    permission_decision: Option<&super::types::PermissionDecisionInput>,
) -> bool {
    if tool.name.trim() != "run_command" {
        return false;
    }
    let cmd = command_arg(tool);
    if cmd.is_empty() {
        return false;
    }
    let approved = permission_decision
        .map(|decision| decision.decision.trim().starts_with("approve"))
        .unwrap_or(false);
    if approved {
        return true;
    }
    let (risk, _) = classify_command_risk(&cmd);
    risk == "safe"
}

fn command_arg(tool: &PlannedLocalTool) -> String {
    argument_string(&tool.arguments, "cmd")
        .or_else(|| argument_string(&tool.arguments, "command"))
        .unwrap_or_default()
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
    tool: &PlannedLocalTool,
    result: &super::types::ToolExecutionResult,
) {
    if let Some(sink) = event_sink {
        let mut event = tool_result_event(
            format!(
                "evt_{}_{}",
                runtime_session_id,
                sanitize_path_segment(&result.tool_result_id)
            ),
            runtime_session_id,
            chat_session_id,
            result,
            epoch_millis(),
        );
        if let Some(payload) = event.get_mut("payload").and_then(Value::as_object_mut) {
            payload.insert("arguments".to_string(), tool.arguments.clone());
            payload.insert(
                "arguments_preview".to_string(),
                json!(format_tool_arguments_preview(&tool.arguments, 2_000)),
            );
        }
        sink(event);
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
            let mut payload = permission_request.clone();
            if let Some(object) = payload.as_object_mut() {
                object.insert("tool_call_id".to_string(), json!(result.tool_call_id));
                object.insert("tool_name".to_string(), json!(result.name));
            }
            sink(approval_required_event(
                format!(
                    "evt_{}_approval_{}",
                    runtime_session_id,
                    sanitize_path_segment(&result.tool_call_id)
                ),
                runtime_session_id,
                chat_session_id,
                payload,
                epoch_millis(),
            ));
        }
    }
}

fn finalize_agent_loop_result(
    model_steps: Vec<ModelStepResult>,
    model_input_snapshots: Vec<Value>,
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
        model_input_snapshots,
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
        if stopped_reason == "waiting_plan_confirmation" {
            return AgentLoopVerification {
                status: "waiting_approval".to_string(),
                summary: "等待用户确认执行计划后继续同一个 Agent Loop。".to_string(),
                evidence: vec!["planning.confirmation_required".to_string()],
            };
        }
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
        "tool_no_signal" => AgentLoopVerification {
            status: "no_signal".to_string(),
            summary: "工具步骤没有完成或失败证据，任务保持可恢复的暂无信号状态。".to_string(),
            evidence: attempts
                .last()
                .map(|attempt| {
                    vec![
                        format!("strategy={}", attempt.strategy_signature),
                        format!("failure={}", attempt.failure_signature),
                    ]
                })
                .unwrap_or_else(|| vec!["tool_no_signal".to_string()]),
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

fn repair_planned_tool_arguments(
    mut tool: PlannedLocalTool,
    messages: &[RuntimeModelMessage],
    model_result: Option<&ModelStepResult>,
    workspace_root: &PathBuf,
) -> PlannedLocalTool {
    if tool.name.trim() == "write_file"
        && argument_string(&tool.arguments, "path").is_none()
        && argument_string(&tool.arguments, "content").is_some()
    {
        if let Some(path) = infer_target_path_from_model_result(model_result)
            .or_else(|| infer_recent_target_path(messages))
        {
            if let Some(object) = tool.arguments.as_object_mut() {
                object.insert("path".to_string(), json!(path.clone()));
                tool.summary = if tool.summary.trim().is_empty() {
                    format!("自动补全 write_file path={path}")
                } else {
                    format!("{}；自动补全 path={path}", tool.summary.trim())
                };
            }
        }
    }
    if tool.name.trim() == "search_text" {
        repair_search_text_file_path(&mut tool, workspace_root);
    }
    tool
}

fn repair_search_text_file_path(tool: &mut PlannedLocalTool, workspace_root: &PathBuf) {
    let Some(path) = argument_string(&tool.arguments, "path") else {
        return;
    };
    let Ok(target) = resolve_workspace_child(workspace_root, &path, true) else {
        return;
    };
    if !target.is_file() {
        return;
    }
    let Some(object) = tool.arguments.as_object_mut() else {
        return;
    };
    let file_name = target
        .file_name()
        .map(|value| value.to_string_lossy().to_string())
        .unwrap_or_default();
    if file_name.is_empty() {
        return;
    }
    let parent = target
        .parent()
        .map(|value| workspace_relative_path(workspace_root, value))
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| ".".to_string());
    object.insert("path".to_string(), json!(parent.clone()));
    object
        .entry("glob".to_string())
        .or_insert_with(|| json!(file_name.clone()));
    tool.summary = if tool.summary.trim().is_empty() {
        format!("自动修正 search_text path={path} 为目录 {parent}，glob={file_name}")
    } else {
        format!(
            "{}；自动修正 search_text path={path} 为目录 {parent}，glob={file_name}",
            tool.summary.trim()
        )
    };
}

fn drift_check_tool_result(
    tool: &PlannedLocalTool,
    request: &ModelStepRequest,
) -> Option<super::types::ToolExecutionResult> {
    if !is_side_effect_tool(&tool.name) || tool.name.trim() == "run_command" {
        return None;
    }
    let task_goal = request.task_goal.as_ref()?;
    let requested_targets = extract_file_path_candidates(&task_goal.user_request);
    if requested_targets.is_empty() {
        return None;
    }
    let tool_target = tool_target_path(tool)?;
    let normalized_tool_target = normalize_scope_path(&tool_target);
    let in_scope = requested_targets
        .iter()
        .map(|target| normalize_scope_path(target))
        .any(|target| paths_share_scope(&target, &normalized_tool_target));
    if in_scope {
        return None;
    }
    let expected = requested_targets.join(", ");
    let summary = format!(
        "DriftCheck 阻止了偏离目标的副作用工具：本轮目标路径为 {expected}，但工具试图修改 {tool_target}。"
    );
    Some(super::types::ToolExecutionResult {
        tool_result_id: format!("result_{}", tool.tool_call_id),
        tool_call_id: tool.tool_call_id.clone(),
        name: tool.name.clone(),
        ok: false,
        content: json!({
            "driftCheck": {
                "status": "blocked",
                "expectedTargets": requested_targets,
                "actualTarget": tool_target,
                "taskGoal": task_goal,
            }
        }),
        summary: summary.clone(),
        error_code: "agent_loop.drift_detected".to_string(),
        error: summary,
    })
}

fn tool_target_path(tool: &PlannedLocalTool) -> Option<String> {
    argument_string(&tool.arguments, "path")
        .or_else(|| argument_string(&tool.arguments, "target"))
        .or_else(|| argument_string(&tool.arguments, "file"))
}

fn normalize_scope_path(path: &str) -> String {
    path.trim()
        .trim_start_matches("./")
        .trim_matches('/')
        .split('/')
        .filter(|segment| !segment.is_empty() && *segment != ".")
        .collect::<Vec<_>>()
        .join("/")
}

fn paths_share_scope(expected: &str, actual: &str) -> bool {
    if expected.is_empty() || actual.is_empty() {
        return false;
    }
    expected == actual
        || actual.starts_with(&format!("{expected}/"))
        || expected.starts_with(&format!("{actual}/"))
}

fn argument_string(arguments: &Value, key: &str) -> Option<String> {
    arguments
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn infer_recent_target_path(messages: &[RuntimeModelMessage]) -> Option<String> {
    for message in messages.iter().rev() {
        if message.role.trim() != "user" {
            continue;
        }
        let candidates = extract_file_path_candidates(&message.content);
        if let Some(candidate) = candidates.last() {
            return Some(candidate.clone());
        }
    }
    None
}

fn infer_target_path_from_model_result(model_result: Option<&ModelStepResult>) -> Option<String> {
    let model_result = model_result?;
    let mut texts = Vec::new();
    if !model_result.summary.trim().is_empty() {
        texts.push(model_result.summary.as_str());
    }
    if !model_result.content.trim().is_empty() {
        texts.push(model_result.content.as_str());
    }
    if !model_result.reasoning_content.trim().is_empty() {
        texts.push(model_result.reasoning_content.as_str());
    }
    for text in texts {
        if let Some(candidate) = infer_target_path_from_text(text) {
            return Some(candidate);
        }
    }
    None
}

fn infer_target_path_from_text(text: &str) -> Option<String> {
    let candidates = extract_file_path_candidates(text);
    candidates.last().cloned()
}

fn extract_file_path_candidates(text: &str) -> Vec<String> {
    let mut candidates = Vec::new();
    let mut current = String::new();
    for ch in text.chars() {
        if ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.' | '/') {
            current.push(ch);
            continue;
        }
        push_file_path_candidate(&mut candidates, &current, ch == ':');
        current.clear();
    }
    push_file_path_candidate(&mut candidates, &current, false);
    candidates
}

fn push_file_path_candidate(output: &mut Vec<String>, raw: &str, preceded_by_url_scheme: bool) {
    if preceded_by_url_scheme || raw.starts_with("//") {
        return;
    }
    let candidate = raw
        .trim_matches(|ch: char| matches!(ch, '/' | '-' | '_'))
        .trim_end_matches('.');
    if candidate.is_empty() || candidate.contains("..") {
        return;
    }
    if looks_like_file_path(candidate) {
        output.push(candidate.to_string());
    }
}

fn looks_like_file_path(candidate: &str) -> bool {
    if candidate.contains("://") || candidate.contains("//") {
        return false;
    }
    let Some(file_name) = candidate.rsplit('/').next() else {
        return false;
    };
    if file_name.is_empty() || file_name == "." {
        return false;
    }
    if file_name.starts_with('.') && file_name.len() > 1 {
        return true;
    }
    if file_name.contains('.') {
        return true;
    }
    candidate.contains('/')
        || file_name
            .chars()
            .next()
            .map(char::is_uppercase)
            .unwrap_or(false)
}

fn has_unresolved_failed_attempt(attempts: &[AgentLoopAttempt], final_content: &str) -> bool {
    let last_failed = attempts
        .iter()
        .rposition(|attempt| attempt.status == "failed");
    let Some(last_failed) = last_failed else {
        return false;
    };
    let last_passed = attempts
        .iter()
        .rposition(|attempt| attempt.status == "passed");
    if last_passed
        .map(|index| index > last_failed)
        .unwrap_or(false)
    {
        return false;
    }
    if attempts[last_failed..]
        .iter()
        .all(is_degradable_bootstrap_failure)
        && final_content_acknowledges_degraded_tool_path(final_content)
    {
        return false;
    }
    true
}

fn is_degradable_bootstrap_failure(attempt: &AgentLoopAttempt) -> bool {
    matches!(attempt.error_code.as_str(), "mcp.adapter_missing")
}

fn final_content_acknowledges_degraded_tool_path(content: &str) -> bool {
    let content = content.trim();
    !content.is_empty()
        && (content.contains("降级")
            || content.contains("adapter")
            || content.contains("MCP")
            || content.contains("mcp"))
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
        if is_full_access_decision(decision) {
            return Some(decision.clone());
        }
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
        "upload_deploy_artifact" => Some("deploy.artifact.upload"),
        "deploy_workspace_files_to_target" => Some("deploy.direct.upload"),
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
    let recovery_instruction = tool_recovery_instruction(result, permission_denied);
    let recoverable = is_recoverable_tool_failure(result, permission_denied);
    json!({
        "tool_call_id": result.tool_call_id,
        "tool_name": result.name,
        "status": status,
        "ok": result.ok,
        "recoverable": recoverable,
        "summary": result.summary,
        "error_code": if permission_denied { "permission.denied" } else { result.error_code.as_str() },
        "error": if permission_denied { "user denied permission request" } else { result.error.as_str() },
        "content": compact_tool_observation_content(&result.name, &result.content),
        "content_compacted_for_model": true,
        "attempt": attempt_payload,
        "recovery_instruction": recovery_instruction,
        "retry_instruction": if result.ok || permission_denied {
            ""
        } else if !recovery_instruction.is_empty() {
            recovery_instruction.as_str()
        } else if recoverable {
            "这是可恢复工具错误。请修正工具参数、改用不依赖该工具的方案，或在当前目标不硬依赖该工具时降级继续；不要把单个可恢复工具失败当成本轮任务失败。"
        } else {
            "当前方案验证失败。下一轮必须换一个不同 strategy_signature 的方案；不要原样重复同一个工具、参数和验证路径。"
        },
    })
    .to_string()
}

fn compact_tool_observation_content(tool_name: &str, content: &Value) -> Value {
    match tool_name.trim() {
        "read_file" => compact_read_file_observation(content),
        "search_text" | "search_files" => compact_search_observation(content),
        "list_files" => {
            compact_array_field_observation(content, "entries", TOOL_OBSERVATION_MAX_ARRAY_ITEMS)
        }
        "run_command" => compact_command_observation(content),
        _ => compact_generic_observation(content),
    }
}

fn compact_read_file_observation(content: &Value) -> Value {
    let Some(object) = content.as_object() else {
        return compact_generic_observation(content);
    };
    let mut compacted = object.clone();
    if let Some(text) = object.get("content").and_then(Value::as_str) {
        let (preview, truncated_for_model) =
            truncate_chars_with_flag(text, TOOL_OBSERVATION_TEXT_PREVIEW_CHARS);
        compacted.insert("content".to_string(), json!(preview));
        compacted.insert(
            "content_truncated_for_model".to_string(),
            json!(truncated_for_model),
        );
        compacted.insert("content_chars".to_string(), json!(text.chars().count()));
    }
    Value::Object(compacted)
}

fn compact_search_observation(content: &Value) -> Value {
    let Some(object) = content.as_object() else {
        return compact_generic_observation(content);
    };
    let mut compacted = object.clone();
    if let Some(matches) = object.get("matches").and_then(Value::as_array) {
        let total = matches.len();
        let compact_matches = matches
            .iter()
            .take(TOOL_OBSERVATION_MAX_ARRAY_ITEMS)
            .map(|item| {
                let Some(item_object) = item.as_object() else {
                    return compact_generic_observation(item);
                };
                let mut compact_item = item_object.clone();
                if let Some(text) = item_object.get("content").and_then(Value::as_str) {
                    let (preview, truncated_for_model) =
                        truncate_chars_with_flag(text, TOOL_OBSERVATION_MATCH_PREVIEW_CHARS);
                    compact_item.insert("content".to_string(), json!(preview));
                    compact_item.insert(
                        "content_truncated_for_model".to_string(),
                        json!(truncated_for_model),
                    );
                }
                Value::Object(compact_item)
            })
            .collect::<Vec<_>>();
        compacted.insert("matches".to_string(), json!(compact_matches));
        compacted.insert("matches_total".to_string(), json!(total));
        compacted.insert(
            "matches_truncated_for_model".to_string(),
            json!(total > TOOL_OBSERVATION_MAX_ARRAY_ITEMS),
        );
    }
    Value::Object(compacted)
}

fn compact_array_field_observation(content: &Value, field: &str, max_items: usize) -> Value {
    let Some(object) = content.as_object() else {
        return compact_generic_observation(content);
    };
    let mut compacted = object.clone();
    if let Some(items) = object.get(field).and_then(Value::as_array) {
        let total = items.len();
        compacted.insert(
            field.to_string(),
            Value::Array(items.iter().take(max_items).cloned().collect()),
        );
        compacted.insert(format!("{field}_total"), json!(total));
        compacted.insert(
            format!("{field}_truncated_for_model"),
            json!(total > max_items),
        );
    }
    Value::Object(compacted)
}

fn compact_command_observation(content: &Value) -> Value {
    let Some(object) = content.as_object() else {
        return compact_generic_observation(content);
    };
    let mut compacted = object.clone();
    for field in ["stdout", "stderr"] {
        if let Some(text) = object.get(field).and_then(Value::as_str) {
            let (preview, truncated_for_model) =
                truncate_chars_with_flag(text, TOOL_OBSERVATION_TEXT_PREVIEW_CHARS);
            compacted.insert(field.to_string(), json!(preview));
            compacted.insert(format!("{field}_chars"), json!(text.chars().count()));
            compacted.insert(
                format!("{field}_truncated_for_model"),
                json!(truncated_for_model),
            );
        }
    }
    Value::Object(compacted)
}

fn compact_generic_observation(content: &Value) -> Value {
    let raw = serde_json::to_string(content).unwrap_or_else(|_| content.to_string());
    if raw.chars().count() <= TOOL_OBSERVATION_TEXT_PREVIEW_CHARS {
        return content.clone();
    }
    let (preview, _) = truncate_chars_with_flag(&raw, TOOL_OBSERVATION_TEXT_PREVIEW_CHARS);
    json!({
        "preview": preview,
        "serialized_chars": raw.chars().count(),
        "truncated_for_model": true,
    })
}

fn truncate_chars_with_flag(value: &str, max_chars: usize) -> (String, bool) {
    let mut chars = value.chars();
    let output = chars.by_ref().take(max_chars).collect::<String>();
    let truncated = chars.next().is_some();
    (output, truncated)
}

fn is_recoverable_tool_failure(
    result: &super::types::ToolExecutionResult,
    permission_denied: bool,
) -> bool {
    if result.ok || permission_denied {
        return false;
    }
    if result
        .content
        .get("recoverable")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        return true;
    }
    matches!(
        result.error_code.as_str(),
        "tool.schema_invalid"
            | "tool.not_found"
            | "mcp.adapter_missing"
            | "mcp.server_not_found"
            | "mcp.config_invalid"
            | "mcp.failed"
    )
}

fn should_continue_after_recoverable_failure(
    result: &super::types::ToolExecutionResult,
    previous_attempts: &[AgentLoopAttempt],
) -> bool {
    if !is_recoverable_tool_failure(result, false) {
        return false;
    }
    let repeated_same_failure_count = previous_attempts
        .iter()
        .filter(|attempt| {
            attempt.status == "failed"
                && attempt.tool_name == result.name
                && attempt.error_code == result.error_code
                && attempt.summary == result.summary
        })
        .count();
    repeated_same_failure_count < max_recoverable_failure_repeats(result)
}

fn max_recoverable_failure_repeats(result: &super::types::ToolExecutionResult) -> usize {
    match result.error_code.as_str() {
        "mcp.adapter_missing" => 2,
        "tool.schema_invalid" => 1,
        _ => 1,
    }
}

fn tool_recovery_instruction(
    result: &super::types::ToolExecutionResult,
    permission_denied: bool,
) -> String {
    if result.ok || permission_denied {
        return String::new();
    }
    if result.name == "write_file"
        && result.error_code == "tool.schema_invalid"
        && result.error.contains("missing required argument: path")
    {
        return "write_file 调用失败：缺少必填字段 path。请从用户最近消息中提取目标文件名；如果用户提到 register.html，下一次必须使用 {\"path\":\"register.html\",\"content\":\"完整文件内容\",\"overwrite\":false}。不要再次省略 path。".to_string();
    }
    if result.name == "write_file"
        && result.error_code == "tool.schema_invalid"
        && result.error.contains("missing required argument: content")
    {
        return "write_file 调用失败：缺少必填字段 content。下一次必须同时提供 path 和完整 content；如果只想局部修改，请改用 apply_patch。".to_string();
    }
    if result.error_code == "tool.schema_invalid" {
        return format!(
            "{} 参数不符合工具契约：{}。下一轮必须修正参数字段后再调用，不要重复同一组参数。",
            result.name, result.error
        );
    }
    if result.error_code == "mcp.adapter_missing" {
        return "本地 MCP adapter 配置缺失，无法读取或调用该 MCP。若当前任务不硬依赖该 MCP，请继续完成本地可执行部分，并在最终结果说明 MCP 闭环未完成；若硬依赖该 MCP，请明确缺失的 adapter 配置。".to_string();
    }
    if matches!(
        result.error_code.as_str(),
        "mcp.server_not_found" | "mcp.config_invalid" | "mcp.failed"
    ) {
        return format!(
            "MCP 工具调用失败：{}。请判断该 MCP 是否是当前任务硬依赖；不是硬依赖时降级继续，硬依赖时明确配置或服务阻塞。",
            result.error
        );
    }
    String::new()
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
    project_id: String,
    mode: String,
    provider_id: String,
    model_name: String,
    base_url: String,
    api_key: String,
    gateway_url: String,
    temperature: f64,
    timeout_ms: u64,
    user_message: String,
    ai_entry_file: String,
    backend_context: Option<LocalBackendContext>,
    messages: Vec<RuntimeModelMessage>,
    task_goal: Option<TaskGoal>,
    task_tree: Option<planning::TaskTree>,
}

impl ModelStepRequest {
    fn with_messages(&self, messages: Vec<RuntimeModelMessage>) -> Self {
        Self {
            project_id: self.project_id.clone(),
            mode: self.mode.clone(),
            provider_id: self.provider_id.clone(),
            model_name: self.model_name.clone(),
            base_url: self.base_url.clone(),
            api_key: self.api_key.clone(),
            gateway_url: self.gateway_url.clone(),
            temperature: self.temperature,
            timeout_ms: self.timeout_ms,
            user_message: self.user_message.clone(),
            ai_entry_file: self.ai_entry_file.clone(),
            backend_context: self.backend_context.clone(),
            messages,
            task_goal: self.task_goal.clone(),
            task_tree: self.task_tree.clone(),
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
    reasoning_content: String,
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
            "reasoning_content": self.reasoning_content,
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
            reasoning_content: String::new(),
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
            reasoning_content: String::new(),
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
            reasoning_content: String::new(),
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

fn model_gateway_header(headers: &HeaderMap, names: &[&str]) -> String {
    for name in names {
        if let Some(value) = headers.get(*name).and_then(|value| value.to_str().ok()) {
            let normalized = value.trim();
            if !normalized.is_empty() {
                return normalized.to_string();
            }
        }
    }
    String::new()
}

fn model_gateway_body_diagnostic(body: &Value) -> Value {
    let messages_count = body
        .get("messages")
        .and_then(Value::as_array)
        .map(|items| items.len())
        .unwrap_or(0);
    let body_bytes = serde_json::to_vec(body)
        .map(|bytes| bytes.len())
        .unwrap_or(0);
    let message_roles = body
        .get("messages")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.get("role").and_then(Value::as_str))
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let message_diagnostics = body
        .get("messages")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .enumerate()
                .map(|(index, item)| {
                    let role = item.get("role").and_then(Value::as_str).unwrap_or("");
                    let content_chars = message_content_chars(item.get("content"));
                    let serialized_bytes =
                        serde_json::to_vec(item).map(|bytes| bytes.len()).unwrap_or(0);
                    json!({
                        "index": index,
                        "role": role,
                        "tool_call_id": item.get("tool_call_id").and_then(Value::as_str).unwrap_or(""),
                        "tool_call_count": item.get("tool_calls").and_then(Value::as_array).map(|values| values.len()).unwrap_or(0),
                        "content_chars": content_chars,
                        "serialized_bytes": serialized_bytes,
                    })
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let largest_messages = {
        let mut items = message_diagnostics.clone();
        items.sort_by(|left, right| {
            right
                .get("serialized_bytes")
                .and_then(Value::as_u64)
                .unwrap_or(0)
                .cmp(
                    &left
                        .get("serialized_bytes")
                        .and_then(Value::as_u64)
                        .unwrap_or(0),
                )
        });
        items.into_iter().take(5).collect::<Vec<_>>()
    };
    json!({
        "model": body.get("model").cloned().unwrap_or_else(|| json!("")),
        "temperature": body.get("temperature").cloned().unwrap_or(Value::Null),
        "stream": body.get("stream").cloned().unwrap_or(Value::Null),
        "tool_choice": body.get("tool_choice").cloned().unwrap_or(Value::Null),
        "body_bytes": body_bytes,
        "messages_count": messages_count,
        "message_roles": message_roles,
        "message_diagnostics": message_diagnostics,
        "largest_messages": largest_messages,
        "tool_call_integrity": validate_tool_call_message_integrity(
            body.get("messages").and_then(Value::as_array),
        ),
        "tools_count": body.get("tools").and_then(Value::as_array).map(|items| items.len()).unwrap_or(0),
    })
}

fn message_content_chars(content: Option<&Value>) -> usize {
    match content {
        Some(Value::String(value)) => value.chars().count(),
        Some(Value::Array(items)) => items
            .iter()
            .map(|item| {
                item.get("text")
                    .and_then(Value::as_str)
                    .map(str::chars)
                    .map(Iterator::count)
                    .unwrap_or_else(|| item.to_string().chars().count())
            })
            .sum(),
        Some(value) => value.to_string().chars().count(),
        None => 0,
    }
}

fn validate_tool_call_message_integrity(messages: Option<&Vec<Value>>) -> Value {
    let Some(messages) = messages else {
        return json!({
            "status": "unknown",
            "issue_count": 0,
            "issues": []
        });
    };
    let mut pending_tool_call_ids: Vec<String> = Vec::new();
    let mut issues = Vec::<Value>::new();
    for (index, message) in messages.iter().enumerate() {
        let role = message.get("role").and_then(Value::as_str).unwrap_or("");
        if role == "assistant" {
            pending_tool_call_ids.clear();
            if let Some(tool_calls) = message.get("tool_calls").and_then(Value::as_array) {
                pending_tool_call_ids.extend(tool_calls.iter().filter_map(|tool_call| {
                    tool_call
                        .get("id")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|value| !value.is_empty())
                        .map(str::to_string)
                }));
            }
            continue;
        }
        if role != "tool" {
            if !pending_tool_call_ids.is_empty() {
                issues.push(json!({
                    "index": index,
                    "code": "non_tool_before_all_tool_results",
                    "pending_tool_call_ids": pending_tool_call_ids,
                    "role": role,
                }));
                pending_tool_call_ids.clear();
            }
            continue;
        }
        let tool_call_id = message
            .get("tool_call_id")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or("");
        if tool_call_id.is_empty() {
            issues.push(json!({
                "index": index,
                "code": "tool_message_missing_tool_call_id",
            }));
            continue;
        }
        if let Some(position) = pending_tool_call_ids
            .iter()
            .position(|pending| pending == tool_call_id)
        {
            pending_tool_call_ids.remove(position);
        } else {
            issues.push(json!({
                "index": index,
                "code": "orphan_tool_message",
                "tool_call_id": tool_call_id,
            }));
        }
    }
    if !pending_tool_call_ids.is_empty() {
        issues.push(json!({
            "code": "missing_tool_messages",
            "pending_tool_call_ids": pending_tool_call_ids,
        }));
    }
    json!({
        "status": if issues.is_empty() { "ok" } else { "invalid" },
        "issue_count": issues.len(),
        "issues": issues,
    })
}

fn model_gateway_request_diagnostic(
    method: &str,
    endpoint: &str,
    provider_id: &str,
    model_name: &str,
    body: Option<&Value>,
) -> String {
    let parsed = Url::parse(endpoint).ok();
    let diagnostic = json!({
        "method": method,
        "url": endpoint,
        "path": parsed.as_ref().map(|url| url.path()).unwrap_or(""),
        "query": parsed.as_ref().and_then(|url| url.query()).unwrap_or(""),
        "provider_id": provider_id,
        "model": model_name,
        "body": body.map(model_gateway_body_diagnostic).unwrap_or_else(|| json!({})),
    });
    serde_json::to_string(&diagnostic).unwrap_or_else(|_| String::new())
}

fn model_gateway_upload_diagnostic(
    method: &str,
    endpoint: &str,
    provider_id: &str,
    filename: &str,
    mime_type: &str,
    purpose: &str,
    file_size: usize,
) -> String {
    let parsed = Url::parse(endpoint).ok();
    let diagnostic = json!({
        "method": method,
        "url": endpoint,
        "path": parsed.as_ref().map(|url| url.path()).unwrap_or(""),
        "query": parsed.as_ref().and_then(|url| url.query()).unwrap_or(""),
        "provider_id": provider_id,
        "body": {
            "filename": filename,
            "mime_type": mime_type,
            "purpose": purpose,
            "file_size": file_size,
        },
    });
    serde_json::to_string(&diagnostic).unwrap_or_else(|_| String::new())
}

fn model_gateway_http_error_message(
    status: u16,
    headers: &HeaderMap,
    body: &str,
    request_diagnostic: &str,
) -> String {
    let retry_after = model_gateway_header(headers, &["retry-after", "Retry-After"]);
    let request_id = model_gateway_header(
        headers,
        &[
            "x-request-id",
            "x-trace-id",
            "x-ratelimit-request-id",
            "cf-ray",
        ],
    );
    let body_preview = truncate_inline(body, 2_000);
    let mut parts = vec![format!("model gateway returned HTTP {status}")];
    if !request_diagnostic.trim().is_empty() {
        parts.push(format!("request={}", request_diagnostic.trim()));
    }
    if !retry_after.is_empty() {
        parts.push(format!("retry-after={retry_after}"));
    }
    if !request_id.is_empty() {
        parts.push(format!("request-id={request_id}"));
    }
    if !body_preview.is_empty() {
        parts.push(format!("body={body_preview}"));
    }
    parts.join("; ")
}

#[derive(Debug, Deserialize)]
struct OpenAiCompatibleResponse {
    choices: Option<Vec<OpenAiCompatibleChoice>>,
}

#[derive(Debug, Deserialize)]
struct OpenAiCompatibleChoice {
    message: Option<OpenAiCompatibleMessage>,
    delta: Option<OpenAiCompatibleMessage>,
}

#[derive(Debug, Deserialize)]
struct OpenAiCompatibleMessage {
    content: Option<Value>,
    reasoning_content: Option<Value>,
    tool_calls: Option<Vec<OpenAiCompatibleToolCall>>,
}

#[derive(Debug, Deserialize)]
struct OpenAiCompatibleToolCall {
    id: Option<String>,
    index: Option<usize>,
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
    let system_prompt_parts = normalize_system_prompt_parts(request);
    if system_prompt_parts.is_empty() {
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
    } else {
        messages.extend(
            system_prompt_parts
                .into_iter()
                .map(|(_, _, _, content)| RuntimeModelMessage::simple("system", content)),
        );
    }
    messages.extend(request.history.iter().filter_map(|message| {
        if should_exclude_history_message_from_model_context(message) {
            return None;
        }
        if ["user", "assistant", "system"].contains(&message.role.trim())
            && !message.content.trim().is_empty()
        {
            let mut runtime_message = RuntimeModelMessage::simple(
                message.role.trim().to_string(),
                message.content.clone(),
            );
            if message.role.trim() == "assistant" {
                runtime_message.reasoning_content = message
                    .reasoning_content
                    .as_deref()
                    .map(str::trim)
                    .unwrap_or("")
                    .to_string();
            }
            Some(runtime_message)
        } else {
            None
        }
    }));
    messages.push(build_user_message_with_attachments(
        user_message,
        &request.attachments,
    ));

    ModelStepRequest {
        project_id: request.project_id.trim().to_string(),
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
        timeout_ms: runtime
            .timeout_ms
            .unwrap_or(DEFAULT_MODEL_TIMEOUT_MS)
            .clamp(1_000, 120_000),
        user_message: user_message.to_string(),
        ai_entry_file: request
            .ai_entry_file
            .as_deref()
            .map(str::trim)
            .unwrap_or("")
            .to_string(),
        backend_context: request.backend_context.clone(),
        messages,
        task_goal: None,
        task_tree: None,
    }
}

fn should_exclude_history_message_from_model_context(message: &LocalChatMessage) -> bool {
    if !message.diagnostic.unwrap_or(false) {
        return false;
    }
    let visibility = message.visibility.as_deref().map(str::trim).unwrap_or("");
    visibility != "model_context"
}

fn build_user_message_with_attachments(
    user_message: &str,
    attachments: &[LocalChatAttachment],
) -> RuntimeModelMessage {
    if attachments.is_empty() {
        return RuntimeModelMessage::simple("user", user_message.to_string());
    }
    let attachment_context = build_attachment_prompt_context(attachments);
    let text_content = [user_message.trim(), attachment_context.trim()]
        .into_iter()
        .filter(|item| !item.is_empty())
        .collect::<Vec<_>>()
        .join("\n\n");
    let image_parts = attachments
        .iter()
        .filter_map(|attachment| {
            let routing_mode = attachment
                .routing_mode
                .as_deref()
                .map(str::trim)
                .unwrap_or("");
            if routing_mode != "inline_image" && routing_mode != "provider_file" {
                return None;
            }
            let data_url = attachment
                .data_url
                .as_deref()
                .map(str::trim)
                .filter(|value| value.starts_with("data:image/"))?;
            Some(RuntimeModelContentPart::ImageUrl {
                image_url: RuntimeModelImageUrl {
                    url: data_url.to_string(),
                },
            })
        })
        .collect::<Vec<_>>();
    if image_parts.is_empty() {
        return RuntimeModelMessage::simple("user", text_content);
    }
    let mut content_parts = Vec::with_capacity(1 + image_parts.len());
    content_parts.push(RuntimeModelContentPart::Text {
        text: text_content.clone(),
    });
    content_parts.extend(image_parts);
    RuntimeModelMessage::with_content_parts("user", text_content, content_parts)
}

fn build_attachment_prompt_context(attachments: &[LocalChatAttachment]) -> String {
    let blocks = attachments
        .iter()
        .enumerate()
        .map(|(index, attachment)| {
            let name = attachment.name.trim();
            let display_name = if name.is_empty() {
                format!("attachment-{}", index + 1)
            } else {
                name.to_string()
            };
            let mime_type = attachment
                .mime_type
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .unwrap_or("unknown");
            let kind = attachment
                .kind
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .unwrap_or("file");
            let status = attachment
                .extraction_status
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .unwrap_or("metadata_only");
            let routing_mode = attachment
                .routing_mode
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .unwrap_or("local_extract");
            let size_label = attachment
                .size
                .map(format_attachment_size)
                .unwrap_or_else(|| "unknown size".to_string());
            let mut lines = vec![
                format!("附件 {}：{}", index + 1, display_name),
                format!("- 类型：{kind}"),
                format!("- MIME：{mime_type}"),
                format!("- 大小：{size_label}"),
                format!("- 路由方式：{routing_mode}"),
                format!("- 处理状态：{status}"),
            ];
            if let Some(provider_file_id) = attachment
                .provider_file_id
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
            {
                lines.push(format!("- provider_file_id：{provider_file_id}"));
            }
            if let Some(error) = attachment
                .error
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
            {
                lines.push(format!("- 处理错误：{error}"));
            }
            if let Some(text) = attachment
                .extracted_text
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
            {
                lines.push("- 可读内容：".to_string());
                lines.push(text.to_string());
            } else if (routing_mode == "inline_image" || routing_mode == "provider_file")
                && attachment
                    .data_url
                    .as_deref()
                    .map(str::trim)
                    .is_some_and(|value| value.starts_with("data:image/"))
            {
                lines.push("- 图片内容已作为多模态 image_url 一并发送。".to_string());
            } else {
                lines.push("- 未抽取到可读内容，请基于元数据说明限制。".to_string());
            }
            lines.join("\n")
        })
        .collect::<Vec<_>>();
    if blocks.is_empty() {
        String::new()
    } else {
        format!("附件上下文：\n{}", blocks.join("\n\n"))
    }
}

fn format_attachment_size(size: u64) -> String {
    if size >= 1024 * 1024 {
        format!("{:.2} MB", size as f64 / 1024.0 / 1024.0)
    } else if size >= 1024 {
        format!("{:.2} KB", size as f64 / 1024.0)
    } else {
        format!("{size} B")
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

fn is_ollama_compatible_runtime(request: &ModelStepRequest) -> bool {
    let provider_id = request.provider_id.to_ascii_lowercase();
    if provider_id.contains("ollama") {
        return true;
    }
    Url::parse(request.base_url.trim())
        .ok()
        .and_then(|url| url.host_str().map(|host| (host.to_string(), url.port())))
        .is_some_and(|(host, port)| {
            let normalized_host = host.to_ascii_lowercase();
            matches!(normalized_host.as_str(), "127.0.0.1" | "localhost" | "::1")
                && port == Some(11434)
        })
}

fn run_openai_compatible_model_step(request: &ModelStepRequest) -> ModelStepResult {
    if request.base_url.trim().is_empty() {
        return ModelStepResult::skipped(
            request,
            "unconfigured",
            "direct-openai-compatible 模式缺少 baseUrl。",
        );
    }
    let is_ollama_compatible = is_ollama_compatible_runtime(request);
    if request.api_key.trim().is_empty() && !is_ollama_compatible {
        return ModelStepResult::skipped(
            request,
            "unconfigured",
            "direct-openai-compatible 模式缺少 apiKey 或 apiKeyEnv。",
        );
    }
    let normalized_model_name = request.model_name.trim();
    if normalized_model_name.is_empty() || normalized_model_name == "unconfigured" {
        return ModelStepResult::skipped(
            request,
            "unconfigured",
            format!(
                "direct-openai-compatible 模式缺少 modelName，已停止发送模型请求。provider_id={} base_url={}",
                request.provider_id,
                request.base_url
            ),
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
    if !request.api_key.trim().is_empty() {
        let auth_value = match HeaderValue::from_str(&format!("Bearer {}", request.api_key.trim()))
        {
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
    }

    let request_body =
        build_openai_compatible_request_body(request, normalized_model_name, is_ollama_compatible);

    let client = match Client::builder()
        .connect_timeout(Duration::from_millis(15_000))
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
                .json(&request_body)
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
        let headers = response.headers().clone();
        let response_body = response
            .text()
            .unwrap_or_else(|err| format!("failed to read model gateway error body: {err}"));
        let request_diagnostic = model_gateway_request_diagnostic(
            "POST",
            &endpoint,
            &request.provider_id,
            normalized_model_name,
            Some(&request_body),
        );
        return ModelStepResult::failed(
            request,
            "model.request_failed",
            model_gateway_http_error_message(status, &headers, &response_body, &request_diagnostic),
        );
    }
    let is_streaming_response = response
        .headers()
        .get("content-type")
        .and_then(|value| value.to_str().ok())
        .map(|value| value.to_ascii_lowercase().contains("text/event-stream"))
        .unwrap_or(false);
    let (content, reasoning_content, tool_calls) = if is_streaming_response {
        match parse_openai_compatible_streaming_response(response, &request.provider_id) {
            Ok(value) => value,
            Err(err) => return ModelStepResult::failed(request, "model.response_invalid", err),
        }
    } else {
        match parse_openai_compatible_json_response(response, &request.provider_id) {
            Ok(value) => value,
            Err(err) => return ModelStepResult::failed(request, "model.response_invalid", err),
        }
    };
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
        model_name: normalized_model_name.to_string(),
        status: "completed".to_string(),
        summary: format!(
            "模型已在桌面端本机调用：{} / {}，返回 {} 个工具调用",
            request.provider_id,
            normalized_model_name,
            tool_calls.len()
        ),
        content,
        reasoning_content,
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

fn build_openai_compatible_request_body(
    request: &ModelStepRequest,
    normalized_model_name: &str,
    is_ollama_compatible: bool,
) -> Value {
    let mut request_body = json!({
        "model": normalized_model_name,
        "temperature": request.temperature,
        "stream": true,
        "messages": request.messages.iter().map(openai_compatible_message_payload).collect::<Vec<_>>()
    });
    if !is_ollama_compatible {
        request_body["tools"] = json!(openai_compatible_tool_schemas());
        request_body["tool_choice"] = json!("auto");
    }
    request_body
}

fn parse_openai_compatible_json_response(
    response: Response,
    run_key: &str,
) -> Result<(String, String, Vec<PlannedLocalTool>), String> {
    let payload = response
        .json::<OpenAiCompatibleResponse>()
        .map_err(|err| format!("model response parse failed: {err}"))?;
    let message = payload
        .choices
        .and_then(|choices| choices.into_iter().next())
        .and_then(|choice| choice.message.or(choice.delta));
    let content = message
        .as_ref()
        .and_then(|message| stringify_model_content(message.content.clone()))
        .unwrap_or_default();
    let reasoning_content = message
        .as_ref()
        .and_then(|message| stringify_model_content(message.reasoning_content.clone()))
        .unwrap_or_default();
    let tool_calls = message
        .and_then(|message| collect_openai_tool_calls(run_key, message.tool_calls))
        .unwrap_or_default();
    Ok((content, reasoning_content, tool_calls))
}

fn parse_openai_compatible_streaming_response(
    response: Response,
    run_key: &str,
) -> Result<(String, String, Vec<PlannedLocalTool>), String> {
    let reader = BufReader::new(response);
    parse_openai_compatible_streaming_reader(reader, run_key)
}

fn parse_openai_compatible_streaming_reader<R: BufRead>(
    reader: R,
    run_key: &str,
) -> Result<(String, String, Vec<PlannedLocalTool>), String> {
    let mut content = String::new();
    let mut reasoning_content = String::new();
    let mut tool_chunks: Vec<OpenAiCompatibleToolCall> = Vec::new();
    for line in reader.lines() {
        let line = line.map_err(|err| format!("model stream read failed: {err}"))?;
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with(':') {
            continue;
        }
        let Some(data) = trimmed.strip_prefix("data:").map(str::trim) else {
            continue;
        };
        if data == "[DONE]" {
            break;
        }
        let payload = serde_json::from_str::<OpenAiCompatibleResponse>(data)
            .map_err(|err| format!("model stream chunk parse failed: {err}; chunk={data}"))?;
        for choice in payload.choices.unwrap_or_default() {
            let message = choice.delta.or(choice.message);
            let Some(message) = message else {
                continue;
            };
            if let Some(value) = stringify_model_content(message.content) {
                content.push_str(&value);
            }
            if let Some(value) = stringify_model_content(message.reasoning_content) {
                reasoning_content.push_str(&value);
            }
            if let Some(calls) = message.tool_calls {
                merge_openai_tool_call_chunks(&mut tool_chunks, calls);
            }
        }
    }
    let tool_calls = collect_openai_tool_calls(run_key, Some(tool_chunks)).unwrap_or_default();
    Ok((content, reasoning_content, tool_calls))
}

fn merge_openai_tool_call_chunks(
    target: &mut Vec<OpenAiCompatibleToolCall>,
    chunks: Vec<OpenAiCompatibleToolCall>,
) {
    for chunk in chunks {
        let index = chunk.index.unwrap_or(target.len());
        while target.len() <= index {
            target.push(OpenAiCompatibleToolCall {
                id: None,
                index: Some(target.len()),
                function: None,
            });
        }
        let current = &mut target[index];
        if current.id.is_none() {
            current.id = chunk.id.clone();
        }
        current.index = Some(index);
        if let Some(function) = chunk.function {
            let current_function =
                current
                    .function
                    .get_or_insert_with(|| OpenAiCompatibleFunctionCall {
                        name: None,
                        arguments: None,
                    });
            if let Some(name) = function.name {
                let existing = current_function.name.get_or_insert_with(String::new);
                existing.push_str(&name);
            }
            if let Some(arguments) = function.arguments {
                let piece = stringify_model_content(Some(arguments)).unwrap_or_default();
                let existing = current_function
                    .arguments
                    .get_or_insert_with(|| Value::String(String::new()));
                match existing {
                    Value::String(value) => value.push_str(&piece),
                    other => {
                        let mut combined =
                            stringify_model_content(Some(other.clone())).unwrap_or_default();
                        combined.push_str(&piece);
                        *other = Value::String(combined);
                    }
                }
            }
        }
    }
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
        return with_assistant_reasoning_content(
            json!({
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
            }),
            message,
        );
    }
    if !message.content_parts.is_empty() {
        return json!({
            "role": role,
            "content": message.content_parts
        });
    }
    with_assistant_reasoning_content(
        json!({
            "role": role,
            "content": message.content
        }),
        message,
    )
}

fn with_assistant_reasoning_content(mut payload: Value, message: &RuntimeModelMessage) -> Value {
    if normalize_model_message_role(&message.role) != "assistant" {
        return payload;
    }
    let reasoning_content = message.reasoning_content.trim();
    if reasoning_content.is_empty() {
        return payload;
    }
    if let Value::Object(map) = &mut payload {
        map.insert(
            "reasoning_content".to_string(),
            Value::String(reasoning_content.to_string()),
        );
    }
    payload
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
            let tool_call_id = tool_call
                .id
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(str::to_string)
                .unwrap_or_else(|| {
                    stable_tool_call_id_for_arguments(run_key, &name, &arguments, index)
                });
            Some(PlannedLocalTool {
                tool_call_id: normalized_tool_call_id(Some(tool_call_id)),
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

fn build_provider_files_url(base_url: &str) -> Result<String, ToolError> {
    let trimmed = base_url.trim().trim_end_matches('/');
    let endpoint = if trimmed.ends_with("/files") {
        trimmed.to_string()
    } else if trimmed.ends_with("/v1") {
        format!("{trimmed}/files")
    } else if trimmed.ends_with("/chat/completions") {
        format!("{}/files", trimmed.trim_end_matches("/chat/completions"))
    } else {
        format!("{trimmed}/v1/files")
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

fn multipart_escape(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\r', "")
        .replace('\n', "")
}

fn build_provider_file_multipart_body(
    boundary: &str,
    filename: &str,
    mime_type: &str,
    purpose: &str,
    file_bytes: &[u8],
) -> Vec<u8> {
    let mut body = Vec::new();
    if !purpose.trim().is_empty() {
        body.extend_from_slice(format!("--{boundary}\r\n").as_bytes());
        body.extend_from_slice(b"Content-Disposition: form-data; name=\"purpose\"\r\n\r\n");
        body.extend_from_slice(purpose.trim().as_bytes());
        body.extend_from_slice(b"\r\n");
    }
    body.extend_from_slice(format!("--{boundary}\r\n").as_bytes());
    body.extend_from_slice(
        format!(
            "Content-Disposition: form-data; name=\"file\"; filename=\"{}\"\r\n",
            multipart_escape(filename)
        )
        .as_bytes(),
    );
    body.extend_from_slice(format!("Content-Type: {mime_type}\r\n\r\n").as_bytes());
    body.extend_from_slice(file_bytes);
    body.extend_from_slice(b"\r\n");
    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());
    body
}

fn upload_provider_file_inner(
    request: &ProviderFileUploadRequest,
) -> Result<ProviderFileUploadResult, ToolError> {
    let base_url = request.base_url.trim();
    let api_key = request.api_key.trim();
    let filename = if request.filename.trim().is_empty() {
        "upload.bin"
    } else {
        request.filename.trim()
    };
    let mime_type = request
        .mime_type
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("application/octet-stream");
    let purpose = request
        .purpose
        .as_deref()
        .map(str::trim)
        .unwrap_or("file-extract");
    if base_url.is_empty() {
        return Err(ToolError::new(
            "model.schema_invalid",
            "provider baseUrl is required",
        ));
    }
    if api_key.is_empty() {
        return Err(ToolError::new(
            "model.schema_invalid",
            "provider apiKey is required",
        ));
    }
    if request.file_bytes.is_empty() {
        return Err(ToolError::new("model.schema_invalid", "上传文件为空"));
    }
    let endpoint = build_provider_files_url(base_url)?;
    let timeout_ms = request.timeout_ms.unwrap_or(120_000).clamp(1_000, 300_000);
    let boundary = format!("----liuagent-provider-file-{}", epoch_millis());
    let body = build_provider_file_multipart_body(
        &boundary,
        filename,
        mime_type,
        purpose,
        &request.file_bytes,
    );
    let mut headers = HeaderMap::new();
    headers.insert(
        CONTENT_TYPE,
        HeaderValue::from_str(&format!("multipart/form-data; boundary={boundary}")).map_err(
            |err| {
                ToolError::new(
                    "model.schema_invalid",
                    format!("invalid multipart header: {err}"),
                )
            },
        )?,
    );
    headers.insert(
        AUTHORIZATION,
        HeaderValue::from_str(&format!("Bearer {api_key}")).map_err(|err| {
            ToolError::new(
                "model.schema_invalid",
                format!("invalid api key header: {err}"),
            )
        })?,
    );
    let client = Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-provider-file-upload/0.1")
        .build()
        .map_err(|err| {
            ToolError::new("model.request_failed", format!("创建上传客户端失败：{err}"))
        })?;
    let response = client
        .post(endpoint.clone())
        .headers(headers)
        .body(body)
        .send()
        .map_err(|err| {
            ToolError::new("model.request_failed", format!("模型文件上传失败：{err}"))
        })?;
    let status = response.status().as_u16();
    let response_headers = response.headers().clone();
    let response_text = response.text().map_err(|err| {
        ToolError::new("model.response_invalid", format!("读取上传响应失败：{err}"))
    })?;
    if !(200..300).contains(&status) {
        let provider_id = request.provider_id.as_deref().map(str::trim).unwrap_or("");
        let request_diagnostic = model_gateway_upload_diagnostic(
            "POST",
            &endpoint,
            provider_id,
            filename,
            mime_type,
            purpose,
            request.file_bytes.len(),
        );
        return Err(ToolError::new(
            "model.request_failed",
            model_gateway_http_error_message(
                status,
                &response_headers,
                &response_text,
                &request_diagnostic,
            ),
        ));
    }
    let payload = serde_json::from_str::<Value>(&response_text).map_err(|err| {
        ToolError::new(
            "model.response_invalid",
            format!(
                "模型文件上传响应不是合法 JSON：{err}; body={}",
                truncate_inline(&response_text, 500)
            ),
        )
    })?;
    let provider_file_id = payload
        .get("id")
        .or_else(|| payload.get("file_id"))
        .or_else(|| payload.get("provider_file_id"))
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or("")
        .to_string();
    if provider_file_id.is_empty() {
        return Err(ToolError::new(
            "model.response_invalid",
            format!(
                "模型文件上传成功但未返回文件 id；body={}",
                truncate_inline(&response_text, 500)
            ),
        ));
    }
    let provider_id = request
        .provider_id
        .as_deref()
        .map(str::trim)
        .unwrap_or("")
        .to_string();
    let upload_status = payload
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or("uploaded")
        .to_string();
    Ok(ProviderFileUploadResult {
        ok: true,
        provider_id,
        provider_file_id,
        filename: filename.to_string(),
        mime_type: mime_type.to_string(),
        purpose: purpose.to_string(),
        status: upload_status,
        raw: payload,
        error_code: String::new(),
        error: String::new(),
    })
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
    use std::cell::RefCell;
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::thread;

    #[test]
    fn extracts_file_paths_without_fixed_extension_allowlist() {
        let candidates = extract_file_path_candidates(
            "更新 Dockerfile、scripts/deploy.sh、db/schema.sql 和 .env.local；参考 https://example.com/docs。",
        );

        assert!(candidates.contains(&"Dockerfile".to_string()));
        assert!(candidates.contains(&"scripts/deploy.sh".to_string()));
        assert!(candidates.contains(&"db/schema.sql".to_string()));
        assert!(candidates.contains(&".env.local".to_string()));
        assert!(!candidates.iter().any(|item| item.contains("example.com")));
    }

    #[test]
    fn repairs_write_file_path_from_latest_user_message() {
        let workspace_root = std::env::temp_dir();
        let messages = vec![RuntimeModelMessage::simple(
            "user",
            "浅色渐变商务风（南京嘉华运营平台）。 register.html这俩",
        )];
        let repaired = repair_planned_tool_arguments(
            PlannedLocalTool {
                tool_call_id: "call_write_register".to_string(),
                name: "write_file".to_string(),
                arguments: json!({"content": "<!doctype html><html></html>"}),
                summary: "标准模型工具调用：write_file".to_string(),
            },
            &messages,
            None,
            &workspace_root,
        );
        assert_eq!(repaired.arguments["path"], "register.html");
        assert!(repaired.summary.contains("自动补全 path=register.html"));
    }

    #[test]
    fn repairs_write_file_path_from_current_model_output() {
        let workspace_root = std::env::temp_dir();
        let messages = vec![RuntimeModelMessage::simple("user", "确认开始执行")];
        let model_result = ModelStepResult {
            ok: true,
            mode: "mock".to_string(),
            provider_id: "test".to_string(),
            model_name: "test-model".to_string(),
            status: "completed".to_string(),
            content: "将新增 index.html 作为官网首页，并链接到现有登录和注册页面。".to_string(),
            reasoning_content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: "写入新文件，产出实现结果".to_string(),
            error_code: String::new(),
            error: String::new(),
        };
        let repaired = repair_planned_tool_arguments(
            PlannedLocalTool {
                tool_call_id: "call_write_index".to_string(),
                name: "write_file".to_string(),
                arguments: json!({"content": "<!doctype html><html></html>"}),
                summary: "标准模型工具调用：write_file".to_string(),
            },
            &messages,
            Some(&model_result),
            &workspace_root,
        );
        assert_eq!(repaired.arguments["path"], "index.html");
        assert!(repaired.summary.contains("自动补全 path=index.html"));
    }

    #[test]
    fn repairs_search_text_file_path_to_directory_and_glob() {
        let dir = std::env::temp_dir().join(format!("liuagent_search_repair_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("register.html"), "<form></form>").unwrap();
        let workspace_root = dir.canonicalize().unwrap();
        let repaired = repair_planned_tool_arguments(
            PlannedLocalTool {
                tool_call_id: "call_search_register".to_string(),
                name: "search_text".to_string(),
                arguments: json!({"path": "register.html", "query": "<form"}),
                summary: "标准模型工具调用：search_text".to_string(),
            },
            &[],
            None,
            &workspace_root,
        );

        assert_eq!(repaired.arguments["path"], ".");
        assert_eq!(repaired.arguments["glob"], "register.html");
        assert!(repaired.summary.contains("自动修正 search_text"));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn progress_update_only_emits_for_visible_model_content_before_tools() {
        let events = RefCell::new(Vec::<Value>::new());
        let sink = |event: Value| events.borrow_mut().push(event);
        let result = ModelStepResult {
            ok: true,
            mode: "mock".to_string(),
            provider_id: "test".to_string(),
            model_name: "test-model".to_string(),
            status: "completed".to_string(),
            content: "我已经确认目标文件是 register.html，下一步读取 login.html。".to_string(),
            reasoning_content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: "visible progress".to_string(),
            error_code: String::new(),
            error: String::new(),
        };
        let planned_tools = vec![PlannedLocalTool {
            tool_call_id: "call_read_login".to_string(),
            name: "read_file".to_string(),
            arguments: json!({"path": "login.html"}),
            summary: "标准模型工具调用：read_file".to_string(),
        }];
        let request = test_model_request("读取 login.html");

        emit_progress_update_event(
            Some(&sink),
            "runtime-test",
            "chat-test",
            1,
            &result,
            &[],
            &request,
        );
        assert!(events.borrow().is_empty());

        emit_progress_update_event(
            Some(&sink),
            "runtime-test",
            "chat-test",
            1,
            &result,
            &planned_tools,
            &request,
        );
        let events = events.borrow();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0]["type"], "progress_update");
        assert!(events[0]["payload"]["summary"]
            .as_str()
            .unwrap()
            .contains("register.html"));
        assert_eq!(events[0]["payload"]["tool_call_count"], 1);
        assert!(events[0]["payload"]["current_task_node"].is_object());
        assert_eq!(
            events[0]["payload"]["planned_tools"][0]["arguments"]["path"],
            "login.html"
        );
        assert!(events[0]["payload"]["arguments_preview"]
            .as_str()
            .unwrap()
            .contains("\"path\":\"login.html\""));
    }

    #[test]
    fn progress_update_emits_tool_summary_when_model_content_is_empty() {
        let events = RefCell::new(Vec::<Value>::new());
        let sink = |event: Value| events.borrow_mut().push(event);
        let result = ModelStepResult {
            ok: true,
            mode: "mock".to_string(),
            provider_id: "test".to_string(),
            model_name: "test-model".to_string(),
            status: "completed".to_string(),
            content: String::new(),
            reasoning_content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: String::new(),
            error_code: String::new(),
            error: String::new(),
        };
        let planned_tools = vec![PlannedLocalTool {
            tool_call_id: "call_search".to_string(),
            name: "search_text".to_string(),
            arguments: json!({"path": ".", "query": "progress_update"}),
            summary: "标准模型工具调用：search_text".to_string(),
        }];
        let request = test_model_request("搜索 progress_update");

        emit_progress_update_event(
            Some(&sink),
            "runtime-test",
            "chat-test",
            1,
            &result,
            &planned_tools,
            &request,
        );

        let events = events.borrow();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0]["type"], "progress_update");
        assert!(events[0]["payload"]["summary"]
            .as_str()
            .unwrap()
            .contains("搜索"));
        assert_eq!(
            events[0]["payload"]["current_focus"],
            "收集实现所需的文件结构和现有页面风格"
        );
        assert!(events[0]["payload"]["next_action"]
            .as_str()
            .unwrap()
            .contains("搜索"));
        assert_eq!(events[0]["payload"]["tool_call_count"], 1);
        assert!(events[0]["payload"]["arguments_preview"]
            .as_str()
            .unwrap()
            .contains("progress_update"));
    }

    #[test]
    fn progress_update_shows_write_file_arguments_with_content_preview() {
        let events = RefCell::new(Vec::<Value>::new());
        let sink = |event: Value| events.borrow_mut().push(event);
        let result = ModelStepResult {
            ok: true,
            mode: "mock".to_string(),
            provider_id: "test".to_string(),
            model_name: "test-model".to_string(),
            status: "completed".to_string(),
            content: String::new(),
            reasoning_content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: String::new(),
            error_code: String::new(),
            error: String::new(),
        };
        let planned_tools = vec![PlannedLocalTool {
            tool_call_id: "call_write_index".to_string(),
            name: "write_file".to_string(),
            arguments: json!({
                "path": "index.html",
                "content": "x".repeat(240),
                "overwrite": false
            }),
            summary: "标准模型工具调用：write_file".to_string(),
        }];
        let request = test_model_request("确认开始执行");

        emit_progress_update_event(
            Some(&sink),
            "runtime-test",
            "chat-test",
            1,
            &result,
            &planned_tools,
            &request,
        );

        let events = events.borrow();
        let preview = events[0]["payload"]["arguments_preview"].as_str().unwrap();
        assert!(preview.contains("write_file"));
        assert!(preview.contains("\"path\":\"index.html\""));
        assert!(preview.contains("\"content\""));
        assert!(preview.contains("\"chars\":240"));
        assert!(preview.contains("\"value\""));
        assert!(preview.contains(&"x".repeat(200)));
        assert_eq!(
            events[0]["payload"]["planned_tools"][0]["arguments"]["path"],
            "index.html"
        );
        assert!(
            events[0]["payload"]["planned_tools"][0]["arguments"]["content"]["value"]
                .as_str()
                .unwrap()
                .contains(&"x".repeat(240))
        );
    }

    #[test]
    fn tool_result_event_includes_arguments_preview_on_schema_failure() {
        let events = RefCell::new(Vec::<Value>::new());
        let sink = |event: Value| events.borrow_mut().push(event);
        let tool = PlannedLocalTool {
            tool_call_id: "call_write_missing_path".to_string(),
            name: "write_file".to_string(),
            arguments: json!({
                "content": "<!doctype html><title>Index</title>",
                "overwrite": false
            }),
            summary: "标准模型工具调用：write_file".to_string(),
        };
        let result = super::super::types::ToolExecutionResult::failed(
            tool.tool_call_id.clone(),
            tool.name.clone(),
            ToolError::new("tool.schema_invalid", "missing required argument: path"),
        );

        emit_tool_result_event(Some(&sink), "runtime-test", "chat-test", &tool, &result);

        let events = events.borrow();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0]["type"], "tool_result");
        assert_eq!(events[0]["payload"]["arguments"]["overwrite"], false);
        let preview = events[0]["payload"]["arguments_preview"].as_str().unwrap();
        assert!(preview.contains("\"content\""));
        assert!(preview.contains("\"overwrite\":false"));
        assert!(!preview.contains("\"path\""));
        assert!(events[0]["payload"]["error_code"]
            .as_str()
            .unwrap()
            .contains("tool.schema_invalid"));
    }

    #[test]
    fn progress_update_shows_apply_patch_arguments_with_full_patch() {
        let events = RefCell::new(Vec::<Value>::new());
        let sink = |event: Value| events.borrow_mut().push(event);
        let result = ModelStepResult {
            ok: true,
            mode: "mock".to_string(),
            provider_id: "test".to_string(),
            model_name: "test-model".to_string(),
            status: "completed".to_string(),
            content: String::new(),
            reasoning_content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: String::new(),
            error_code: String::new(),
            error: String::new(),
        };
        let patch = "*** Begin Patch\n*** Update File: index.html\n@@\n-old\n+new\n*** End Patch";
        let planned_tools = vec![PlannedLocalTool {
            tool_call_id: "call_patch_index".to_string(),
            name: "apply_patch".to_string(),
            arguments: json!({
                "patch": patch,
                "summary": "update index"
            }),
            summary: "标准模型工具调用：apply_patch".to_string(),
        }];
        let request = test_model_request("修改 index.html");

        emit_progress_update_event(
            Some(&sink),
            "runtime-test",
            "chat-test",
            1,
            &result,
            &planned_tools,
            &request,
        );

        let events = events.borrow();
        let preview = events[0]["payload"]["arguments_preview"].as_str().unwrap();
        assert!(preview.contains("apply_patch"));
        assert!(preview.contains("*** Begin Patch"));
        assert!(preview.contains("+new"));
        assert_eq!(
            events[0]["payload"]["planned_tools"][0]["arguments"]["patch"]["value"],
            patch
        );
    }

    #[test]
    fn drift_check_blocks_side_effect_outside_explicit_target() {
        let mut request = test_model_request("修改 src/main.rs 并验证");
        let task_goal = build_task_goal("drift-test", "修改 src/main.rs 并验证", &request);
        request.task_goal = Some(task_goal.clone());
        request.task_tree = Some(planning::TaskTree::for_goal("drift-test", &task_goal));
        let tool = PlannedLocalTool {
            tool_call_id: "call_write_other".to_string(),
            name: "write_file".to_string(),
            arguments: json!({"path": "src/other.rs", "content": "changed"}),
            summary: "write other".to_string(),
        };

        let result = drift_check_tool_result(&tool, &request).expect("drift result");

        assert!(!result.ok);
        assert_eq!(result.error_code, "agent_loop.drift_detected");
        assert_eq!(result.content["driftCheck"]["actualTarget"], "src/other.rs");
    }

    #[test]
    fn drift_check_allows_side_effect_within_explicit_target() {
        let mut request = test_model_request("修改 src/main.rs 并验证");
        let task_goal = build_task_goal("drift-test", "修改 src/main.rs 并验证", &request);
        request.task_goal = Some(task_goal);
        let tool = PlannedLocalTool {
            tool_call_id: "call_write_target".to_string(),
            name: "write_file".to_string(),
            arguments: json!({"path": "src/main.rs", "content": "changed"}),
            summary: "write target".to_string(),
        };

        assert!(drift_check_tool_result(&tool, &request).is_none());
    }

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
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: None,
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
        assert_eq!(requirement["original_request"], "检查工作区");
        assert_eq!(
            requirement["intent_analysis"]["current_request_summary"],
            "检查工作区"
        );
        assert_eq!(requirement["task_goal"]["version"], "task-goal/v1");
        assert_eq!(requirement["task_goal"]["userRequest"], "检查工作区");
        assert_eq!(
            requirement["current_state_delta"]["task_goal"]["goalId"],
            requirement["task_goal"]["goalId"]
        );
        assert_eq!(
            requirement["task_tree"]["currentNodeId"],
            requirement["current_task_node"]["node_id"]
        );
        assert_eq!(
            requirement["current_state_delta"]["current_task_node"]["node_id"],
            requirement["current_task_node"]["node_id"]
        );
        assert!(requirement["task_branches"]
            .as_array()
            .expect("task branches")
            .iter()
            .any(|node| node["is_current"] == true));
        assert!(requirement["related_context"]["items"]
            .as_array()
            .expect("related context items")
            .iter()
            .any(|item| item["source"] == "agent_gateway.tool_manifest_bundle"));
        assert_eq!(
            requirement["contextual_plan"]["execution_boundary"]["workspace_local_first"],
            true
        );
        let snapshots = requirement["model_input_snapshots"]
            .as_array()
            .expect("model input snapshots");
        assert!(snapshots
            .iter()
            .any(|item| item["loop"] == "requirement_understanding"));
        assert!(snapshots
            .iter()
            .any(|item| item["loop"] == "task_processing"));
        let task_snapshot = snapshots
            .iter()
            .find(|item| item["loop"] == "task_processing")
            .expect("task processing snapshot");
        assert_eq!(task_snapshot["prompt_stack"]["version"], "prompt-stack/v1");
        assert_eq!(
            task_snapshot["context_package"]["task_goal"]["goalId"],
            requirement["task_goal"]["goalId"]
        );
        assert!(
            task_snapshot["context_package"]["current_task_node"]["node_id"]
                .as_str()
                .unwrap_or_default()
                .contains("node-analyze")
        );
        assert!(requirement["actions_taken"]["model_steps"].is_array());
        assert_eq!(
            requirement["current_state_delta"]["latest_status"],
            "completed"
        );
        assert_eq!(
            requirement["current_state_delta"]["verification_report"]["overallStatus"],
            "passed"
        );
        assert_eq!(
            requirement["current_state_delta"]["verification_report"]["version"],
            "verification-report/v1"
        );
        assert_eq!(
            requirement["current_state_delta"]["verification_report"]["targetNodeId"],
            requirement["task_goal"]["goalId"]
        );
        let verification_check_types = requirement["current_state_delta"]["verification_report"]
            ["checks"]
            .as_array()
            .expect("verification checks")
            .iter()
            .map(|check| check["type"].as_str().unwrap_or_default())
            .collect::<Vec<_>>();
        assert!(verification_check_types.contains(&"fact"));
        assert!(verification_check_types.contains(&"logic"));
        assert!(verification_check_types.contains(&"constraint"));
        assert!(verification_check_types.contains(&"goal"));
        assert_eq!(
            requirement["current_state_delta"]["clarity_assessment"]["version"],
            "clarity-assessment/v1"
        );
        assert_eq!(
            requirement["current_state_delta"]["plan_state"]["version"],
            "plan-state/v1"
        );
        assert_eq!(
            requirement["current_state_delta"]["retry_decision"]["route"],
            "none"
        );
        assert_eq!(
            requirement["current_state_delta"]["memory_write_plan"]["version"],
            "memory-write-plan/v1"
        );
        assert!(requirement["current_state"]["summary"]
            .as_str()
            .unwrap()
            .contains("completed"));
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
        assert!(result
            .runtime_events
            .iter()
            .any(|event| event["type"] == "model_call_started"));
        assert!(result.runtime_events.iter().any(|event| {
            event["type"] == "model_call_started"
                && event["payload"]["current_task_node"].is_object()
        }));
        assert!(result
            .runtime_events
            .iter()
            .any(|event| event["type"] == "model_step"));
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
            reasoning_content: String::new(),
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
            reasoning_content: String::new(),
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
            &prompt_stack_from_model_request(&request),
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
    fn agent_loop_preserves_reasoning_content_before_tool_observation_continuation() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_loop_reasoning_continuation_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("README.md"), "local agent loop").unwrap();
        let request = test_model_request("读取 README.md");
        let model_call_count = Cell::new(0);
        let emitted_events = RefCell::new(Vec::<Value>::new());
        let model_runner = |request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                let mut result = test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_read".to_string(),
                        name: "read_file".to_string(),
                        arguments: json!({"path": "README.md"}),
                        summary: "标准模型工具调用：read_file".to_string(),
                    }],
                );
                result.reasoning_content = "先确认文件是否存在，再读取内容。".to_string();
                return result;
            }

            let assistant_message = request
                .messages
                .iter()
                .find(|message| message.role == "assistant" && !message.tool_calls.is_empty())
                .expect("second model call must include assistant tool-call message");
            assert_eq!(
                assistant_message.reasoning_content,
                "先确认文件是否存在，再读取内容。"
            );
            let payload = openai_compatible_message_payload(assistant_message);
            assert_eq!(
                payload["reasoning_content"],
                "先确认文件是否存在，再读取内容。"
            );
            assert!(
                request.messages.iter().any(|message| message.role == "tool"
                    && message.content.contains("local agent loop")),
                "second model call must receive tool observation"
            );
            test_model_result("README.md 内容是 local agent loop", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);
        let event_sink = |event: Value| {
            emitted_events.borrow_mut().push(event);
        };

        let result = run_agent_loop_with(
            "chat-loop-reasoning-continuation-test",
            "runtime-chat-loop-reasoning-continuation-test",
            &request,
            &prompt_stack_from_model_request(&request),
            &dir,
            None,
            Some(&event_sink),
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(model_call_count.get(), 2);
        assert_eq!(result.model_steps.len(), 2);
        assert_eq!(result.tool_results.len(), 1);
        assert!(emitted_events.borrow().iter().any(|event| {
            event["type"] == "model_step"
                && event["payload"]["reasoning_content"] == "先确认文件是否存在，再读取内容。"
        }));
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
            &prompt_stack_from_model_request(&request),
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
            &prompt_stack_from_model_request(&request),
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
    fn agent_loop_allows_recoverable_mcp_adapter_error_before_pausing() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_loop_recoverable_mcp_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("读取 MCP 说明后继续本地任务");
        let model_call_count = Cell::new(0);
        let model_runner = |request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index > 0 {
                assert!(
                    request
                        .messages
                        .iter()
                        .any(|message| message.role == "tool"),
                    "model call after MCP failure must receive a tool observation"
                );
            }
            if index < 2 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: format!("call_mcp_{index}"),
                        name: "read_mcp_resource".to_string(),
                        arguments: json!({
                            "server": "query",
                            "uri": "query://usage-guide"
                        }),
                        summary: "标准模型工具调用：read_mcp_resource".to_string(),
                    }],
                );
            }
            test_model_result("MCP adapter 缺失，已降级继续本地任务。", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| {
            crate::liuagent_core::types::ToolExecutionResult::failed(
                request
                    .tool_call_id
                    .unwrap_or_else(|| "call_mcp".to_string()),
                request.name,
                ToolError::new(
                    "mcp.adapter_missing",
                    "read MCP adapter config failed: No such file or directory",
                ),
            )
        };

        let result = run_agent_loop_with(
            "chat-loop-recoverable-mcp-test",
            "runtime-chat-loop-recoverable-mcp-test",
            &request,
            &prompt_stack_from_model_request(&request),
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(result.stopped_reason, "no_tool_calls");
        assert_eq!(model_call_count.get(), 3);
        assert_eq!(result.tool_results.len(), 2);
        assert_eq!(result.tool_results[0].content["recoverable"], true);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn list_files_progress_intent_does_not_suggest_entry_file_hunting() {
        let intent = describe_planned_tool_intent(&PlannedLocalTool {
            tool_call_id: "call_list".to_string(),
            name: "list_files".to_string(),
            arguments: json!({"path": "."}),
            summary: "标准模型工具调用：list_files".to_string(),
        });

        assert!(intent.contains("实现入口"));
        assert!(!intent.contains("入口文件"));
    }

    #[test]
    fn agent_loop_blocks_cli_entry_file_read_when_not_configured_entry() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_loop_cli_entry_block_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("AGENTS.md"), "cli-only instructions").unwrap();
        let mut request = test_model_request("实现官网页面");
        request.ai_entry_file = "AIENTRY.md".to_string();
        let model_runner = |_request: &ModelStepRequest| {
            test_model_result(
                "",
                vec![PlannedLocalTool {
                    tool_call_id: "call_read_agents".to_string(),
                    name: "read_file".to_string(),
                    arguments: json!({"path": "AGENTS.md"}),
                    summary: "标准模型工具调用：read_file".to_string(),
                }],
            )
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-cli-entry-block-test",
            "runtime-cli-entry-block-test",
            &request,
            &prompt_stack_from_model_request(&request),
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(!result.ok());
        assert_eq!(result.tool_results[0].error_code, "entry_file.not_allowed");
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
            &prompt_stack_from_model_request(&request),
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
            &prompt_stack_from_model_request(&request),
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
            &prompt_stack_from_model_request(&request),
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
            &prompt_stack_from_model_request(&request),
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
    fn permission_continuation_replays_pending_tool_from_runtime_state() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_permission_replay_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let workspace_root = dir.canonicalize().unwrap();
        let planned_tool = PlannedLocalTool {
            tool_call_id: "call_write_replay".to_string(),
            name: "write_file".to_string(),
            arguments: json!({"path": "approved.txt", "content": "approved"}),
            summary: "标准模型工具调用：write_file".to_string(),
        };
        let pending_result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some(planned_tool.tool_call_id.clone()),
            name: planned_tool.name.clone(),
            arguments: planned_tool.arguments.clone(),
            workspace_path: workspace_root.to_string_lossy().to_string(),
            permission_decision: None,
        });
        assert_eq!(pending_result.error_code, "permission.required");
        write_runtime_artifacts(RuntimePersistenceInput {
            workspace_root: &workspace_root,
            project_id: "proj-replay",
            chat_session_id: "chat-replay",
            session_id: "local-replay-old",
            user_message_id: "msg-user",
            assistant_message_id: "msg-assistant",
            user_message: "写文件",
            assistant_content: "等待授权",
            run_status: "waiting_approval",
            waiting_for: Some("approval"),
            model_runtime: json!({
                "agent_loop": {
                    "model_steps": [
                        {
                            "reasoning_content": "先创建空文件，再等待用户授权写入。",
                            "tool_calls": [planned_tool.clone()]
                        }
                    ],
                    "planned_tools": [planned_tool.clone()]
                }
            }),
            agent_run_context: json!({"version": "agent-run-context/test"}),
            observations: json!([]),
            scheduler_state: json!({"version": "runtime-scheduler-state/test"}),
            verification_report: json!({"overall_status": "blocked"}),
            task_goal: json!({"version": "task-goal/test", "goalId": "goal-replay"}),
            clarity_assessment: json!({"version": "clarity-assessment/test"}),
            plan_state: json!({"version": "plan-state/test"}),
            retry_decision: json!({"version": "retry-decision/test"}),
            memory_write_plan: json!({"version": "memory-write-plan/test"}),
            tool_results: &[pending_result],
            operations: json!([]),
            audit_logs: &[],
        })
        .unwrap();
        let events = RefCell::new(Vec::<Value>::new());
        let sink = |event: Value| events.borrow_mut().push(event);
        let replayed = replay_pending_permission_tool_if_available(
            &workspace_root,
            "proj-replay",
            "chat-replay",
            "local-replay-new",
            &LocalChatRequest {
                project_id: "proj-replay".to_string(),
                chat_session_id: "chat-replay".to_string(),
                message_id: None,
                assistant_message_id: None,
                message: "写文件".to_string(),
                workspace_path: workspace_root.to_string_lossy().to_string(),
                history: Vec::new(),
                provider_id: None,
                model_name: None,
                system_prompt: None,
                system_prompt_parts: Vec::new(),
                temperature: None,
                model_runtime: None,
                ai_entry_file: None,
                attachments: Vec::new(),
                backend_context: None,
                permission_decision: Some(crate::liuagent_core::types::PermissionDecisionInput {
                    request_id: Some("perm_call_write_replay_file_write".to_string()),
                    decision: "approve_once".to_string(),
                    grant_scope: Some("once".to_string()),
                    comment: None,
                }),
            },
            Some(&sink),
        )
        .expect("pending tool should replay");

        assert!(replayed.result.ok, "{}", replayed.result.error);
        assert_eq!(
            replayed.reasoning_content,
            "先创建空文件，再等待用户授权写入。"
        );
        assert_eq!(
            fs::read_to_string(dir.join("approved.txt")).unwrap(),
            "approved"
        );
        let event_types = events
            .borrow()
            .iter()
            .map(|event| event["type"].as_str().unwrap_or("").to_string())
            .collect::<Vec<_>>();
        assert_eq!(event_types, vec!["tool_call_started", "tool_result"]);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn run_command_emits_command_trace_events() {
        let dir = std::env::temp_dir().join(format!("liuagent_command_trace_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("显示当前目录");
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_pwd".to_string(),
                        name: "run_command".to_string(),
                        arguments: json!({"cmd": "pwd"}),
                        summary: "标准模型工具调用：run_command".to_string(),
                    }],
                );
            }
            test_model_result("命令完成", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);
        let events = RefCell::new(Vec::<Value>::new());
        let sink = |event: Value| events.borrow_mut().push(event);

        let result = run_agent_loop_with(
            "chat-command-trace-test",
            "runtime-command-trace-test",
            &request,
            &prompt_stack_from_model_request(&request),
            &dir,
            None,
            Some(&sink),
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        let event_types = events
            .borrow()
            .iter()
            .map(|event| event["type"].as_str().unwrap_or("").to_string())
            .collect::<Vec<_>>();
        assert!(event_types.contains(&"command_started".to_string()));
        assert!(event_types.contains(&"command_output_chunk".to_string()));
        assert!(event_types.contains(&"command_finished".to_string()));
        let finished = events
            .borrow()
            .iter()
            .find(|event| event["type"] == "command_finished")
            .cloned()
            .unwrap();
        assert_eq!(finished["payload"]["exit_code"], 0);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn run_command_streams_distinct_output_chunk_events() {
        let dir = std::env::temp_dir().join(format!("liuagent_command_stream_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("分段输出");
        let model_call_count = Cell::new(0);
        let model_runner = |_request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if index == 0 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_stream".to_string(),
                        name: "run_command".to_string(),
                        arguments: json!({
                            "cmd": "printf first; sleep 0.1; printf second",
                            "timeout_ms": 5_000
                        }),
                        summary: "标准模型工具调用：run_command".to_string(),
                    }],
                );
            }
            test_model_result("命令完成", Vec::new())
        };
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);
        let events = RefCell::new(Vec::<Value>::new());
        let sink = |event: Value| events.borrow_mut().push(event);

        let result = run_agent_loop_with(
            "chat-command-stream-test",
            "runtime-command-stream-test",
            &request,
            &prompt_stack_from_model_request(&request),
            &dir,
            Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: Some("perm_call_stream_command_run".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
            Some(&sink),
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        let events = events.borrow();
        let chunks = events
            .iter()
            .filter(|event| event["type"] == "command_output_chunk")
            .collect::<Vec<_>>();
        assert!(chunks.len() >= 2, "{chunks:#?}");
        assert!(chunks
            .iter()
            .any(|event| event["payload"]["text"] == "first"));
        assert!(chunks
            .iter()
            .any(|event| event["payload"]["text"] == "second"));
        let event_ids = chunks
            .iter()
            .map(|event| event["event_id"].as_str().unwrap_or(""))
            .collect::<std::collections::HashSet<_>>();
        assert_eq!(event_ids.len(), chunks.len());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_marks_tool_timeout_as_no_signal_not_failed() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_loop_tool_no_signal_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let request = test_model_request("运行一个很慢的构建");
        let model_runner = |_request: &ModelStepRequest| {
            test_model_result(
                "",
                vec![PlannedLocalTool {
                    tool_call_id: "call_slow_read".to_string(),
                    name: "read_file".to_string(),
                    arguments: json!({"path": "large.log"}),
                    summary: "标准模型工具调用：read_file".to_string(),
                }],
            )
        };
        let tool_runner = |_request: ToolExecutionRequest| {
            crate::liuagent_core::types::ToolExecutionResult::failed(
                "call_slow_read".to_string(),
                "read_file".to_string(),
                ToolError::new("tool.timeout", "tool timed out after 1000ms"),
            )
        };

        let result = run_agent_loop_with(
            "chat-tool-no-signal-test",
            "runtime-tool-no-signal-test",
            &request,
            &prompt_stack_from_model_request(&request),
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(!result.ok());
        assert_eq!(result.stopped_reason, "tool_no_signal");
        assert_eq!(result.error_code(), "agent_loop.no_signal");
        assert_eq!(result.verification.status, "no_signal");
        assert_eq!(result.tool_results[0].content["status"], "no_signal");
        assert_eq!(result.tool_results[0].content["requires_judgement"], true);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn refresh_runtime_job_rejects_state_path_outside_workspace() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_runtime_job_scope_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();
        let outside = std::env::temp_dir().join(format!(
            "liuagent_runtime_job_outside_{}.json",
            epoch_millis()
        ));
        fs::write(&outside, "{}").unwrap();

        let result = refresh_local_runtime_job(LocalRuntimeJobRequest {
            workspace_path: dir.to_string_lossy().to_string(),
            state_path: outside.to_string_lossy().to_string(),
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "runtime_job.out_of_scope");
        let _ = fs::remove_dir_all(dir);
        let _ = fs::remove_file(outside);
    }

    #[test]
    fn cancel_runtime_job_marks_running_state_cancelled() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_runtime_job_cancel_{}", epoch_millis()));
        let job_dir = dir
            .join(".ai-employee")
            .join("liuagent-command-jobs")
            .join("cmd_test");
        fs::create_dir_all(&job_dir).unwrap();
        let state_path = job_dir.join("state.json");
        let mut child = Command::new("sleep").arg("5").spawn().unwrap();
        fs::write(
            &state_path,
            serde_json::to_vec_pretty(&json!({
                "record_type": "liuagent-command-job",
                "version": 1,
                "job_id": "cmd_test",
                "status": "running",
                "pid": child.id(),
                "state_path": state_path.to_string_lossy(),
                "stdout_log_path": job_dir.join("stdout.log").to_string_lossy(),
                "stderr_log_path": job_dir.join("stderr.log").to_string_lossy(),
            }))
            .unwrap(),
        )
        .unwrap();

        let result = cancel_local_runtime_job(LocalRuntimeJobRequest {
            workspace_path: dir.to_string_lossy().to_string(),
            state_path: state_path.to_string_lossy().to_string(),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.job["status"], "cancelled");
        let _ = child.wait();
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
            &prompt_stack_from_model_request(&request),
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
            &prompt_stack_from_model_request(&request),
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
            &prompt_stack_from_model_request(&request),
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
            &prompt_stack_from_model_request(&request),
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
    fn agent_loop_allows_many_exploration_rounds_for_non_implementation_tasks() {
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
            &prompt_stack_from_model_request(&request),
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
    fn agent_loop_does_not_force_side_effects_for_implementation_evidence() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_loop_no_forced_side_effect_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("README.md"), "hello").unwrap();
        let request = test_model_request("现在没有登录页在做一个登录页");
        let model_call_count = Cell::new(0);
        let saw_control_message = Cell::new(false);
        let model_runner = |request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if request.messages.iter().any(|message| {
                message.role == "user"
                    && message.content.contains("force_side_effect")
                    && message.content.contains("write_file")
            }) {
                saw_control_message.set(true);
            }
            if index >= 4 {
                return test_model_result("已完成现状分析，当前还没有进入写入。", Vec::new());
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
            "chat-loop-no-forced-side-effect-test",
            "runtime-chat-loop-no-forced-side-effect-test",
            &request,
            &prompt_stack_from_model_request(&request),
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(result.stopped_reason, "no_tool_calls");
        assert!(!saw_control_message.get());
        assert_eq!(model_call_count.get(), 5);
        assert_eq!(tool_call_count.get(), 4);
        assert_eq!(result.verification.status, "passed");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn agent_loop_allows_model_to_finish_after_exploration_without_forced_write() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_loop_finish_after_exploration_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("README.md"), "hello").unwrap();
        let request = test_model_request("创建登录页");
        let model_call_count = Cell::new(0);
        let saw_control_message = Cell::new(false);
        let model_runner = |request: &ModelStepRequest| {
            let index = model_call_count.get();
            model_call_count.set(index + 1);
            if request.messages.iter().any(|message| {
                message.role == "user"
                    && message.content.contains("force_side_effect")
                    && message.content.contains("write_file")
            }) {
                saw_control_message.set(true);
            }
            if index == 0 {
                return test_model_result(
                    "",
                    vec![PlannedLocalTool {
                        tool_call_id: "call_read_once".to_string(),
                        name: "read_file".to_string(),
                        arguments: json!({"path": "README.md"}),
                        summary: "标准模型工具调用：read_file".to_string(),
                    }],
                );
            }
            test_model_result("登录页已创建。", Vec::new())
        };
        let tool_call_count = Cell::new(0);
        let tool_runner = |request: ToolExecutionRequest| {
            tool_call_count.set(tool_call_count.get() + 1);
            execute_tool(request)
        };

        let result = run_agent_loop_with(
            "chat-loop-exploration-fake-finish-test",
            "runtime-chat-loop-exploration-fake-finish-test",
            &request,
            &prompt_stack_from_model_request(&request),
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        assert!(result.ok(), "{}", result.error());
        assert_eq!(result.stopped_reason, "no_tool_calls");
        assert!(!saw_control_message.get());
        assert_eq!(model_call_count.get(), 2);
        assert_eq!(tool_call_count.get(), 1);
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
            &prompt_stack_from_model_request(&request),
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
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.tool_results.len(), 1);
        assert_eq!(result.tool_results[0].name, "planning_gate");
        assert_eq!(result.error_code, "planning.confirmation_required");
        assert!(result
            .runtime_events
            .iter()
            .any(|event| event["type"] == "approval_required"));
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
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: Some(LocalModelRuntimeConfig {
                mode: Some("direct-openai-compatible".to_string()),
                provider_id: None,
                model_name: None,
                base_url: Some("https://api.example.com/v1".to_string()),
                api_key: None,
                api_key_env: None,
                gateway_url: None,
                temperature: None,
                timeout_ms: None,
            }),
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: None,
        };
        let model_request = build_model_request(&request, "你好");
        let result = run_model_step(&model_request);

        assert!(!result.ok);
        assert_eq!(result.mode, "direct-openai-compatible");
        assert_eq!(result.status, "unconfigured");
        assert!(result.summary.contains("apiKey"));
    }

    #[test]
    fn direct_model_runtime_allows_ollama_without_api_key_and_omits_tools() {
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
            assert!(!request.to_ascii_lowercase().contains("authorization:"));
            assert!(!request.contains("\"tools\""));
            assert!(!request.contains("\"tool_choice\""));

            let body = json!({
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok"
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
        let mut model_request = test_model_request("返回 ok");
        model_request.provider_id = "ollama-local".to_string();
        model_request.base_url = format!("http://{address}");
        model_request.api_key = String::new();
        model_request.timeout_ms = 5_000;

        let result = run_model_step(&model_request);
        server.join().unwrap();

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.content, "ok");
    }

    #[test]
    fn direct_model_runtime_streams_openai_compatible_response() {
        let model_request = test_model_request("读取 register.html");
        let request_body =
            build_openai_compatible_request_body(&model_request, "test-model", false);
        assert_eq!(request_body["stream"], true);
        assert!(request_body["tools"]
            .as_array()
            .is_some_and(|items| !items.is_empty()));

        let chunks = [
            json!({
                "choices": [{
                    "delta": {
                        "reasoning_content": "先读",
                        "content": "准备",
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_read_register",
                            "type": "function",
                            "function": {
                                "name": "read_",
                                "arguments": "{\"path\":\"register"
                            }
                        }]
                    }
                }]
            }),
            json!({
                "choices": [{
                    "delta": {
                        "reasoning_content": "文件",
                        "content": "读取",
                        "tool_calls": [{
                            "index": 0,
                            "function": {
                                "name": "file",
                                "arguments": ".html\",\"start_line\":1}"
                            }
                        }]
                    }
                }]
            }),
        ];
        let mut stream_body = String::new();
        for chunk in chunks {
            stream_body.push_str("data: ");
            stream_body.push_str(&chunk.to_string());
            stream_body.push_str("\n\n");
        }
        stream_body.push_str("data: [DONE]\n\n");

        let (content, reasoning_content, tool_calls) =
            parse_openai_compatible_streaming_reader(stream_body.as_bytes(), "test-provider")
                .unwrap();

        assert_eq!(content, "准备读取");
        assert_eq!(reasoning_content, "先读文件");
        assert_eq!(tool_calls.len(), 1);
        assert_eq!(tool_calls[0].tool_call_id, "call_read_register");
        assert_eq!(tool_calls[0].name, "read_file");
        assert_eq!(tool_calls[0].arguments["path"], "register.html");
        assert_eq!(tool_calls[0].arguments["start_line"], 1);
    }

    #[test]
    fn local_chat_attachments_build_text_and_image_parts() {
        let request = LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-test".to_string(),
            message_id: None,
            assistant_message_id: None,
            message: "请分析附件".to_string(),
            workspace_path: ".".to_string(),
            history: Vec::new(),
            provider_id: Some("openai".to_string()),
            model_name: Some("gpt-test".to_string()),
            system_prompt: None,
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            attachments: vec![
                LocalChatAttachment {
                    attachment_id: Some("att_doc".to_string()),
                    name: "需求.md".to_string(),
                    mime_type: Some("text/markdown".to_string()),
                    size: Some(12),
                    kind: Some("document".to_string()),
                    routing_mode: Some("local_extract".to_string()),
                    extraction_status: Some("text_extracted".to_string()),
                    data_url: None,
                    extracted_text: Some("这是文档内容".to_string()),
                    provider_file_id: None,
                    error: None,
                },
                LocalChatAttachment {
                    attachment_id: Some("att_img".to_string()),
                    name: "截图.png".to_string(),
                    mime_type: Some("image/png".to_string()),
                    size: Some(32),
                    kind: Some("image".to_string()),
                    routing_mode: Some("inline_image".to_string()),
                    extraction_status: Some("image_data_url".to_string()),
                    data_url: Some("data:image/png;base64,AAAA".to_string()),
                    extracted_text: None,
                    provider_file_id: None,
                    error: None,
                },
            ],
            backend_context: None,
            permission_decision: None,
        };
        let model_request = build_model_request(&request, "请分析附件");
        let user_message = model_request.messages.last().unwrap();
        assert!(user_message.content.contains("附件上下文"));
        assert!(user_message.content.contains("这是文档内容"));
        assert_eq!(user_message.content_parts.len(), 2);

        let payload = openai_compatible_message_payload(user_message);
        let content = payload["content"].as_array().unwrap();
        assert_eq!(content[0]["type"], "text");
        assert_eq!(content[1]["type"], "image_url");
        assert_eq!(
            content[1]["image_url"]["url"].as_str().unwrap(),
            "data:image/png;base64,AAAA"
        );
    }

    #[test]
    fn local_chat_local_extract_mode_skips_image_url_parts() {
        let request = LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-test".to_string(),
            message_id: None,
            assistant_message_id: None,
            message: "请分析附件".to_string(),
            workspace_path: ".".to_string(),
            history: Vec::new(),
            provider_id: Some("openai".to_string()),
            model_name: Some("gpt-test".to_string()),
            system_prompt: None,
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            backend_context: None,
            attachments: vec![LocalChatAttachment {
                attachment_id: Some("att_img".to_string()),
                name: "截图.png".to_string(),
                mime_type: Some("image/png".to_string()),
                size: Some(32),
                kind: Some("image".to_string()),
                routing_mode: Some("local_extract".to_string()),
                extraction_status: Some("metadata_only".to_string()),
                data_url: Some("data:image/png;base64,AAAA".to_string()),
                extracted_text: None,
                provider_file_id: None,
                error: None,
            }],
            permission_decision: None,
        };
        let model_request = build_model_request(&request, "请分析附件");
        let user_message = model_request.messages.last().unwrap();
        // local_extract routing must NOT emit image_url content parts even when
        // a data_url is present; the image should only appear as metadata text.
        assert!(
            user_message.content_parts.is_empty(),
            "local_extract mode should not produce image_url parts"
        );
        assert!(user_message.content.contains("附件上下文"));
        assert!(user_message.content.contains("路由方式：local_extract"));
    }

    #[test]
    fn local_model_transport_failure_is_not_reported_as_connection_timeout() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        drop(listener);

        let mut model_request = test_model_request("测试本地模型传输错误");
        model_request.base_url = format!("http://{address}/v1");
        model_request.model_name = "gpt-test".to_string();
        model_request.api_key = "test-key".to_string();
        model_request.timeout_ms = 5_000;

        let result = run_openai_compatible_model_step(&model_request);

        assert!(!result.ok);
        assert_eq!(result.error_code, "model.request_failed");
        assert!(!result.error.contains(&["模型连接", "超时"].concat()));
        assert!(!result.error.contains("已尝试"));
    }

    #[test]
    fn model_timeout_retries_five_attempts_then_fails() {
        let attempts = Cell::new(0usize);

        let result: Result<(), ModelRequestRetryFailure> =
            send_model_request_with_timeout_retry(MODEL_CONNECTION_TIMEOUT_MAX_ATTEMPTS, || {
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
            send_model_request_with_timeout_retry(MODEL_CONNECTION_TIMEOUT_MAX_ATTEMPTS, || {
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
    fn deploy_backend_context_is_injected_only_for_execution() {
        let tool = PlannedLocalTool {
            tool_call_id: "call_upload_artifact".to_string(),
            name: "upload_deploy_artifact".to_string(),
            arguments: json!({
                "project_id": "proj-test",
                "artifact_path": "dist/app.zip"
            }),
            summary: "upload artifact".to_string(),
        };
        let backend_context = LocalBackendContext {
            api_base_url: "http://127.0.0.1:8000/api".to_string(),
            token: "secret-token".to_string(),
        };

        assert!(tool.arguments.get("_backend_token").is_none());
        let execution_args = tool_arguments_with_backend_context(
            &tool,
            "proj-fallback",
            Some(&backend_context),
            tool.arguments.clone(),
        );

        assert_eq!(
            execution_args["_backend_api_base_url"],
            "http://127.0.0.1:8000/api"
        );
        assert_eq!(execution_args["_backend_token"], "secret-token");
        assert!(tool.arguments.get("_backend_token").is_none());
    }

    #[test]
    fn deploy_options_backend_context_is_injected_only_for_execution() {
        let tool = PlannedLocalTool {
            tool_call_id: "call_deploy_options".to_string(),
            name: "get_project_deploy_options".to_string(),
            arguments: json!({
                "project_id": "proj-test"
            }),
            summary: "read deploy options".to_string(),
        };
        let backend_context = LocalBackendContext {
            api_base_url: "http://127.0.0.1:8000/api".to_string(),
            token: "secret-token".to_string(),
        };

        assert!(tool.arguments.get("_backend_token").is_none());
        let execution_args = tool_arguments_with_backend_context(
            &tool,
            "proj-fallback",
            Some(&backend_context),
            tool.arguments.clone(),
        );

        assert_eq!(
            execution_args["_backend_api_base_url"],
            "http://127.0.0.1:8000/api"
        );
        assert_eq!(execution_args["_backend_token"], "secret-token");
        assert_eq!(execution_args["project_id"], "proj-test");
        assert!(tool.arguments.get("_backend_token").is_none());
    }

    #[test]
    fn deploy_tool_project_id_defaults_to_current_request_project() {
        let tool = PlannedLocalTool {
            tool_call_id: "call_deploy_options".to_string(),
            name: "get_project_deploy_options".to_string(),
            arguments: json!({}),
            summary: "read deploy options".to_string(),
        };
        let backend_context = LocalBackendContext {
            api_base_url: "http://127.0.0.1:8000/api".to_string(),
            token: "secret-token".to_string(),
        };

        let execution_args = tool_arguments_with_backend_context(
            &tool,
            "proj-current",
            Some(&backend_context),
            tool.arguments.clone(),
        );

        assert_eq!(execution_args["project_id"], "proj-current");
        assert_eq!(execution_args["_backend_token"], "secret-token");
    }

    #[test]
    fn tool_observation_compacts_large_read_file_content_for_model() {
        let large_content = "x".repeat(TOOL_OBSERVATION_TEXT_PREVIEW_CHARS + 200);
        let result = super::super::types::ToolExecutionResult::ok(
            "call_read_large".to_string(),
            "read_file".to_string(),
            json!({
                "path": "large.html",
                "content": large_content,
                "start_line": 1,
                "end_line": 500,
                "total_lines": 500,
                "truncated": false
            }),
            "读取 large.html 行 1-500/500".to_string(),
        );

        let observation = tool_observation_content(&result, false, None);
        let value = serde_json::from_str::<Value>(&observation).unwrap();

        assert_eq!(value["content_compacted_for_model"], true);
        assert_eq!(
            value["content"]["content"]
                .as_str()
                .unwrap()
                .chars()
                .count(),
            TOOL_OBSERVATION_TEXT_PREVIEW_CHARS
        );
        assert_eq!(value["content"]["content_truncated_for_model"], true);
        assert_eq!(
            value["content"]["content_chars"],
            TOOL_OBSERVATION_TEXT_PREVIEW_CHARS + 200
        );
    }

    #[test]
    fn model_gateway_diagnostic_reports_payload_size_and_tool_integrity() {
        let body = json!({
            "model": "test-model",
            "temperature": 0.1,
            "stream": true,
            "tool_choice": "auto",
            "tools": [{"type": "function"}],
            "messages": [
                {"role": "user", "content": "读取文件"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_read",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": "{\"path\":\"README.md\"}"
                            }
                        }
                    ]
                },
                {"role": "tool", "tool_call_id": "call_read", "content": "ok"}
            ]
        });

        let diagnostic = model_gateway_body_diagnostic(&body);

        assert!(diagnostic["body_bytes"].as_u64().unwrap_or(0) > 0);
        assert_eq!(diagnostic["messages_count"], 3);
        assert_eq!(diagnostic["tool_call_integrity"]["status"], "ok");
        assert!(diagnostic["message_diagnostics"]
            .as_array()
            .unwrap()
            .iter()
            .any(|item| item["role"] == "assistant" && item["tool_call_count"] == 1));
        assert!(diagnostic["largest_messages"].as_array().unwrap().len() <= 5);
    }

    #[test]
    fn direct_model_runtime_includes_gateway_error_body_and_headers() {
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

            let body = r#"{"error":{"message":"quota exceeded","type":"rate_limit"}}"#;
            let response = format!(
                "HTTP/1.1 429 Too Many Requests\r\nContent-Type: application/json\r\nRetry-After: 17\r\nX-Request-ID: req-test-429\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.as_bytes().len(),
                body
            );
            stream.write_all(response.as_bytes()).unwrap();
        });
        let mut model_request = test_model_request("解释 updateStrength");
        model_request.base_url = format!("http://{address}");
        model_request.timeout_ms = 5_000;

        let result = run_model_step(&model_request);
        server.join().unwrap();

        assert!(!result.ok);
        assert_eq!(result.error_code, "model.request_failed");
        assert!(result.error.contains("model gateway returned HTTP 429"));
        assert!(result.error.contains("retry-after=17"));
        assert!(result.error.contains("request-id=req-test-429"));
        assert!(result.error.contains("quota exceeded"));
        assert!(result.error.contains("\"method\":\"POST\""));
        assert!(result
            .error
            .contains(&format!("\"url\":\"http://{address}/v1/chat/completions\"")));
        assert!(result.error.contains("\"path\":\"/v1/chat/completions\""));
        assert!(result.error.contains("\"provider_id\":\"test-provider\""));
        assert!(result.error.contains("\"model\":\"test-model\""));
        assert!(result.error.contains("\"messages_count\":1"));
        assert!(result.summary.contains("quota exceeded"));
    }

    #[test]
    fn direct_model_runtime_rejects_empty_model_before_gateway_request() {
        let mut model_request = test_model_request("解释 updateStrength");
        model_request.model_name = "  ".to_string();

        let result = run_model_step(&model_request);

        assert!(!result.ok);
        assert_eq!(result.status, "unconfigured");
        assert!(result.summary.contains("缺少 modelName"));
        assert!(result.summary.contains("已停止发送模型请求"));
        assert!(!result.summary.contains("model gateway returned HTTP"));
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
        assert!(content.contains("失败摘要：model.request_failed model gateway returned HTTP 429"));
        assert!(!content.contains("失败详情："));
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
    fn deploy_upload_ready_does_not_allow_success_claim() {
        let request = test_model_request("部署登录注册页");
        let model_result =
            test_success_model_result(&request, "## ✅ 部署完成\n登录注册页已经部署成功。");
        let tool_results = vec![crate::liuagent_core::types::ToolExecutionResult::ok(
            "call_upload".to_string(),
            "upload_deploy_artifact".to_string(),
            json!({
                "artifact_status": "ready",
                "deployment_status": "",
                "deployment_confirmed_success": false,
                "response": {
                    "status": "ready",
                    "artifact": {"id": "artifact-1"},
                    "deployment": null
                }
            }),
            "部署产物 artifact-1 已上传，但没有返回部署执行记录：artifact 状态=ready；当前只能视为产物就绪，不能宣称部署完成".to_string(),
        )];

        let content = build_assistant_content(
            "proj-test",
            &PathBuf::from("/tmp/test"),
            "部署登录注册页",
            &[],
            &model_result,
            &tool_results,
            &[],
            true,
            false,
            "",
            "",
            "",
        );

        assert!(content.starts_with("部署操作尚未确认成功。"));
        assert!(content.contains("没有返回 deployment.status=success"));
        assert!(content.contains("不能宣称部署完成"));
        assert!(!content.starts_with("## ✅ 部署完成"));
    }

    #[test]
    fn deploy_success_claim_allowed_when_deployment_succeeded() {
        let request = test_model_request("部署登录注册页");
        let model_result =
            test_success_model_result(&request, "## ✅ 部署完成\n登录注册页已经部署成功。");
        let tool_results = vec![crate::liuagent_core::types::ToolExecutionResult::ok(
            "call_upload".to_string(),
            "upload_deploy_artifact".to_string(),
            json!({
                "artifact_status": "deployed",
                "deployment_status": "success",
                "deployment_confirmed_success": true,
                "response": {
                    "status": "deployed",
                    "artifact": {"id": "artifact-1"},
                    "deployment": {"id": "deploy-1", "status": "success"}
                }
            }),
            "部署产物 artifact-1 已上传并部署成功，deployment deploy-1 状态：success".to_string(),
        )];

        let content = build_assistant_content(
            "proj-test",
            &PathBuf::from("/tmp/test"),
            "部署登录注册页",
            &[],
            &model_result,
            &tool_results,
            &[],
            true,
            false,
            "",
            "",
            "",
        );

        assert!(content.starts_with("## ✅ 部署完成"));
        assert!(content.contains("部署成功"));
        assert!(!content.starts_with("部署操作尚未确认成功。"));
    }

    #[test]
    fn direct_deploy_blocked_does_not_allow_success_claim() {
        let request = test_model_request("直接部署登录注册页");
        let model_result =
            test_success_model_result(&request, "## ✅ 部署完成\n登录注册页已经部署成功。");
        let tool_results = vec![crate::liuagent_core::types::ToolExecutionResult::ok(
            "call_direct_deploy".to_string(),
            "deploy_workspace_files_to_target".to_string(),
            json!({
                "deployment_status": "blocked",
                "deployment_confirmed_success": false,
                "response": {
                    "status": "blocked",
                    "deployment_confirmed_success": false,
                    "stage": "blocked_missing_remote_executor"
                }
            }),
            "部署源 selected files 已由桌面智能体发起直连部署，但未确认成功：deployment 状态=blocked；不能宣称部署完成".to_string(),
        )];

        let content = build_assistant_content(
            "proj-test",
            &PathBuf::from("/tmp/test"),
            "直接部署登录注册页",
            &[],
            &model_result,
            &tool_results,
            &[],
            true,
            false,
            "",
            "",
            "",
        );

        assert!(content.starts_with("部署操作尚未确认成功。"));
        assert!(content.contains("deployment.status=success"));
        assert!(content.contains("deployment 状态=blocked"));
        assert!(!content.starts_with("## ✅ 部署完成"));
    }

    fn test_success_model_result(request: &ModelStepRequest, content: &str) -> ModelStepResult {
        ModelStepResult {
            ok: true,
            mode: request.mode.clone(),
            provider_id: request.provider_id.clone(),
            model_name: request.model_name.clone(),
            status: "completed".to_string(),
            content: content.to_string(),
            reasoning_content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: String::new(),
            error_code: String::new(),
            error: String::new(),
        }
    }

    #[test]
    fn response_formatter_keeps_full_diagnostic_out_of_assistant_content() {
        let request = test_model_request("继续");
        let model_result = ModelStepResult::failed(
            &request,
            "model.request_failed",
            "model gateway returned HTTP 429 request={\"method\":\"POST\",\"url\":\"http://127.0.0.1/v1/chat/completions\",\"messages_count\":12}",
        );

        let formatted = format_local_chat_response(
            "proj-test",
            &PathBuf::from("/tmp/test"),
            "继续",
            &[],
            &model_result,
            &[],
            &[],
            false,
            false,
            "model_failed",
            "",
            &model_result.error,
        );

        assert!(formatted
            .assistant_content
            .contains("失败摘要：model.request_failed model gateway returned HTTP 429"));
        assert!(!formatted.assistant_content.contains("\"messages_count\""));
        assert!(formatted.assistant_content.contains("完整诊断见运行详情"));
        assert!(formatted.diagnostic["model_error"]
            .as_str()
            .unwrap()
            .contains("\"messages_count\""));
        assert!(formatted
            .user_visible_error_summary
            .contains("model.request_failed model gateway returned HTTP 429"));
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
            assert!(!request.contains("\"max_tokens\""));
            assert!(request.contains("\"tools\""));
            assert!(request.contains("\"name\":\"read_file\""));

            let body = json!({
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "我会读取 README。",
                            "reasoning_content": "先确认需要读取的文件路径。",
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
        assert_eq!(result.reasoning_content, "先确认需要读取的文件路径。");
        assert_eq!(result.tool_calls.len(), 1);
        assert_eq!(result.tool_calls[0].tool_call_id, "call_readme");
        assert_eq!(result.tool_calls[0].name, "read_file");
        assert_eq!(result.tool_calls[0].arguments["path"], "README.md");
    }

    #[test]
    fn direct_agent_loop_continuation_request_preserves_reasoning_content() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_http_reasoning_continuation_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("README.md"), "local agent loop").unwrap();

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            for index in 0..2 {
                let (mut stream, _) = listener.accept().unwrap();
                let request = read_http_request(&mut stream);
                assert!(request.starts_with("POST /v1/chat/completions "));
                let body_start = request.find("\r\n\r\n").unwrap() + 4;
                let request_body = serde_json::from_str::<Value>(&request[body_start..]).unwrap();
                if index == 1 {
                    let messages = request_body["messages"].as_array().unwrap();
                    let assistant_message = messages
                        .iter()
                        .find(|message| {
                            message["role"] == "assistant"
                                && message["tool_calls"]
                                    .as_array()
                                    .is_some_and(|items| !items.is_empty())
                        })
                        .expect("continuation request must include assistant tool-call message");
                    assert_eq!(
                        assistant_message["reasoning_content"],
                        "先确认文件是否存在，再读取内容。"
                    );
                    assert!(
                        messages.iter().any(|message| message["role"] == "tool"
                            && message["content"]
                                .as_str()
                                .unwrap_or_default()
                                .contains("local agent loop")),
                        "continuation request must include tool observation"
                    );
                }

                let response_body = if index == 0 {
                    json!({
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "reasoning_content": "先确认文件是否存在，再读取内容。",
                                    "tool_calls": [
                                        {
                                            "id": "call_read",
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
                    .to_string()
                } else {
                    json!({
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "README.md 内容是 local agent loop"
                                }
                            }
                        ]
                    })
                    .to_string()
                };
                let response = format!(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                    response_body.as_bytes().len(),
                    response_body
                );
                stream.write_all(response.as_bytes()).unwrap();
            }
        });

        let mut request = test_model_request("读取 README.md");
        request.base_url = format!("http://{address}");
        request.timeout_ms = 5_000;
        let model_runner = |request: &ModelStepRequest| run_model_step(request);
        let tool_runner = |request: ToolExecutionRequest| execute_tool(request);

        let result = run_agent_loop_with(
            "chat-loop-http-reasoning-continuation-test",
            "runtime-chat-loop-http-reasoning-continuation-test",
            &request,
            &prompt_stack_from_model_request(&request),
            &dir,
            None,
            None,
            &model_runner,
            &tool_runner,
        );

        server.join().unwrap();
        assert!(result.ok(), "{}", result.error());
        assert_eq!(result.model_steps.len(), 2);
        assert_eq!(result.tool_results.len(), 1);
        assert_eq!(
            result.final_model_result().content,
            "README.md 内容是 local agent loop"
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn permission_resume_continuation_request_preserves_original_reasoning_content() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_permission_resume_reasoning_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();

        let first_request = LocalChatRequest {
            project_id: "proj-resume-reasoning".to_string(),
            chat_session_id: "chat-resume-reasoning".to_string(),
            message_id: Some("msg-user".to_string()),
            assistant_message_id: Some("msg-assistant".to_string()),
            message: "创建一个 demo.md 文件空内容".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: Some("test-provider".to_string()),
            model_name: Some("test-model".to_string()),
            system_prompt: None,
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: Some(LocalModelRuntimeConfig {
                mode: Some("direct-openai-compatible".to_string()),
                provider_id: Some("test-provider".to_string()),
                model_name: Some("test-model".to_string()),
                base_url: Some(format!("http://{address}")),
                api_key: Some("test-key".to_string()),
                api_key_env: None,
                gateway_url: None,
                temperature: Some(0.1),
                timeout_ms: Some(5_000),
            }),
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: Some(plan_confirmation_request_id(
                    "chat-resume-reasoning",
                    "msg-user",
                )),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        };

        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let request = read_http_request(&mut stream);
            assert!(request.starts_with("POST /v1/chat/completions "));
            let first_response_body = json!({
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning_content": "需要创建 demo.md 空文件，先请求写文件授权。",
                            "tool_calls": [
                                {
                                    "id": "call_write_demo",
                                    "type": "function",
                                    "function": {
                                        "name": "write_file",
                                        "arguments": "{\"path\":\"demo.md\",\"content\":\"\"}"
                                    }
                                }
                            ]
                        }
                    }
                ]
            })
            .to_string();
            let first_response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                first_response_body.as_bytes().len(),
                first_response_body
            );
            stream.write_all(first_response.as_bytes()).unwrap();

            let (mut stream, _) = listener.accept().unwrap();
            let request = read_http_request(&mut stream);
            assert!(request.starts_with("POST /v1/chat/completions "));
            let body_start = request.find("\r\n\r\n").unwrap() + 4;
            let request_body = serde_json::from_str::<Value>(&request[body_start..]).unwrap();
            let messages = request_body["messages"].as_array().unwrap();
            let assistant_message = messages
                .iter()
                .find(|message| {
                    message["role"] == "assistant"
                        && message["tool_calls"]
                            .as_array()
                            .is_some_and(|items| !items.is_empty())
                })
                .expect("permission resume continuation must include assistant tool-call message");
            assert_eq!(
                assistant_message["reasoning_content"],
                "需要创建 demo.md 空文件，先请求写文件授权。"
            );
            assert!(
                messages.iter().any(|message| message["role"] == "tool"
                    && message["content"]
                        .as_str()
                        .unwrap_or_default()
                        .contains("demo.md")),
                "permission resume continuation must include replayed tool observation"
            );
            let second_response_body = json!({
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "demo.md 已创建。"
                        }
                    }
                ]
            })
            .to_string();
            let second_response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                second_response_body.as_bytes().len(),
                second_response_body
            );
            stream.write_all(second_response.as_bytes()).unwrap();
        });

        let first_result = start_local_chat(first_request);
        assert!(!first_result.ok);
        assert_eq!(first_result.error_code, "permission.required");
        assert!(!dir.join("demo.md").exists());
        let permission_request_id = first_result.tool_results[0].content["permissionRequest"]
            ["requestId"]
            .as_str()
            .expect("permission request id")
            .to_string();

        let second_result = start_local_chat(LocalChatRequest {
            project_id: "proj-resume-reasoning".to_string(),
            chat_session_id: "chat-resume-reasoning".to_string(),
            message_id: Some("msg-user".to_string()),
            assistant_message_id: Some("msg-assistant".to_string()),
            message: "创建一个 demo.md 文件空内容".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: Some("test-provider".to_string()),
            model_name: Some("test-model".to_string()),
            system_prompt: None,
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: Some(LocalModelRuntimeConfig {
                mode: Some("direct-openai-compatible".to_string()),
                provider_id: Some("test-provider".to_string()),
                model_name: Some("test-model".to_string()),
                base_url: Some(format!("http://{address}")),
                api_key: Some("test-key".to_string()),
                api_key_env: None,
                gateway_url: None,
                temperature: Some(0.1),
                timeout_ms: Some(5_000),
            }),
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: Some(permission_request_id),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        server.join().unwrap();
        assert!(second_result.ok, "{}", second_result.error);
        assert!(dir.join("demo.md").exists());
        assert_eq!(fs::read_to_string(dir.join("demo.md")).unwrap(), "");
        let _ = fs::remove_dir_all(dir);
    }

    fn read_http_request(stream: &mut std::net::TcpStream) -> String {
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
        String::from_utf8_lossy(&request_bytes).to_string()
    }

    fn test_model_request(user_message: &str) -> ModelStepRequest {
        ModelStepRequest {
            project_id: "proj-test".to_string(),
            mode: "direct-openai-compatible".to_string(),
            provider_id: "test-provider".to_string(),
            model_name: "test-model".to_string(),
            base_url: "https://example.com/v1".to_string(),
            api_key: "test-key".to_string(),
            gateway_url: String::new(),
            temperature: 0.2,
            timeout_ms: 1_000,
            user_message: user_message.to_string(),
            ai_entry_file: String::new(),
            backend_context: None,
            messages: vec![RuntimeModelMessage::simple(
                "user",
                user_message.to_string(),
            )],
            task_goal: None,
            task_tree: None,
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
            reasoning_content: String::new(),
            tool_calls,
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: "test model result".to_string(),
            error_code: String::new(),
            error: String::new(),
        }
    }

    #[test]
    fn assistant_tool_call_payload_preserves_reasoning_content() {
        let message = RuntimeModelMessage::assistant_tool_call(
            "我需要读取文件。",
            "先判断用户要读取的路径，再调用本机工具。",
            vec![PlannedLocalTool {
                tool_call_id: "call_read".to_string(),
                name: "read_file".to_string(),
                arguments: json!({"path": "工作月报.md"}),
                summary: "标准模型工具调用：read_file".to_string(),
            }],
        );

        let payload = openai_compatible_message_payload(&message);

        assert_eq!(payload["role"], "assistant");
        assert_eq!(
            payload["reasoning_content"],
            "先判断用户要读取的路径，再调用本机工具。"
        );
        assert_eq!(payload["tool_calls"][0]["id"], "call_read");
        assert_eq!(
            payload["tool_calls"][0]["function"]["arguments"],
            "{\"path\":\"工作月报.md\"}"
        );
    }

    #[test]
    fn build_model_request_preserves_history_reasoning_content() {
        for (payload, expected) in [
            (
                json!({
                    "projectId": "proj-test",
                    "chatSessionId": "chat-test",
                    "message": "继续",
                    "workspacePath": ".",
                    "history": [
                        {
                            "role": "assistant",
                            "content": "上一轮回答",
                            "reasoningContent": "先保留前端 camelCase 推理内容。"
                        }
                    ]
                }),
                "先保留前端 camelCase 推理内容。",
            ),
            (
                json!({
                    "projectId": "proj-test",
                    "chatSessionId": "chat-test",
                    "message": "继续",
                    "workspacePath": ".",
                    "history": [
                        {
                            "role": "assistant",
                            "content": "上一轮回答",
                            "reasoning_content": "先保留服务端 snake_case 推理内容。"
                        }
                    ]
                }),
                "先保留服务端 snake_case 推理内容。",
            ),
        ] {
            let request = serde_json::from_value::<LocalChatRequest>(payload).unwrap();

            let model_request = build_model_request(&request, "继续");
            let assistant_message = model_request
                .messages
                .iter()
                .find(|message| message.role == "assistant")
                .expect("assistant history message");
            assert_eq!(assistant_message.reasoning_content, expected);

            let payload = openai_compatible_message_payload(assistant_message);
            assert_eq!(payload["reasoning_content"], expected);
        }
    }

    #[test]
    fn build_model_request_excludes_diagnostic_history_by_default() {
        let request = serde_json::from_value::<LocalChatRequest>(json!({
            "projectId": "proj-test",
            "chatSessionId": "chat-test",
            "message": "继续",
            "workspacePath": ".",
            "history": [
                {
                    "role": "assistant",
                    "content": "模型调用失败：model gateway returned HTTP 429",
                    "sourceKind": "desktop_local_agent_runtime",
                    "diagnostic": true,
                    "visibility": "user_visible"
                },
                {
                    "role": "assistant",
                    "content": "这条诊断允许进入模型上下文。",
                    "sourceKind": "desktop_local_agent_runtime",
                    "diagnostic": true,
                    "visibility": "model_context"
                },
                {
                    "role": "user",
                    "content": "上一轮用户问题"
                }
            ]
        }))
        .unwrap();

        let model_request = build_model_request(&request, "继续");
        let contents = model_request
            .messages
            .iter()
            .map(|message| message.content.as_str())
            .collect::<Vec<_>>();

        assert!(!contents
            .iter()
            .any(|content| content.contains("model gateway returned HTTP 429")));
        assert!(contents
            .iter()
            .any(|content| content.contains("这条诊断允许进入模型上下文")));
        assert!(contents
            .iter()
            .any(|content| content.contains("上一轮用户问题")));
    }

    #[test]
    fn build_model_request_records_structured_system_prompt_parts() {
        let request = serde_json::from_value::<LocalChatRequest>(json!({
            "projectId": "proj-test",
            "chatSessionId": "chat-prompt-parts",
            "message": "继续",
            "workspacePath": ".",
            "systemPrompt": "legacy combined prompt",
            "systemPromptParts": [
                {
                    "source": "system_config.desktop_agent_global_prompt",
                    "priority": 80,
                    "content": "全局提示"
                },
                {
                    "source": "project_chat_settings.system_prompt",
                    "priority": 100,
                    "content": "项目提示"
                }
            ]
        }))
        .unwrap();

        let model_request = build_model_request(&request, "继续");
        let system_messages = model_request
            .messages
            .iter()
            .filter(|message| message.role == "system")
            .collect::<Vec<_>>();
        assert_eq!(system_messages.len(), 2);
        assert_eq!(system_messages[0].content, "项目提示");
        assert_eq!(system_messages[1].content, "全局提示");

        let prompt_stack = resolve_prompt_stack(&request, &model_request);
        assert_eq!(prompt_stack.items.len(), 2);
        assert_eq!(
            prompt_stack.items[0].source,
            "project_chat_settings.system_prompt"
        );
        assert_eq!(prompt_stack.items[0].priority, 100);
        assert_eq!(
            prompt_stack.items[1].source,
            "system_config.desktop_agent_global_prompt"
        );
        assert_eq!(prompt_stack.items[1].priority, 80);
        assert!(!prompt_stack
            .warnings
            .contains(&"multiple_system_prompts_string_compat_mode".to_string()));
    }

    #[test]
    fn agent_run_context_records_excluded_diagnostics_without_model_history_pollution() {
        let request = serde_json::from_value::<LocalChatRequest>(json!({
            "projectId": "proj-test",
            "chatSessionId": "chat-context",
            "message": "继续",
            "workspacePath": ".",
            "modelRuntime": {
                "mode": "openai_compatible",
                "providerId": "local-provider",
                "modelName": "local-model"
            },
            "history": [
                {
                    "role": "assistant",
                    "content": "模型调用失败：model gateway returned HTTP 429",
                    "sourceKind": "desktop_local_agent_runtime",
                    "diagnostic": true,
                    "visibility": "user_visible"
                },
                {
                    "role": "assistant",
                    "content": "这条诊断允许进入模型上下文。",
                    "sourceKind": "desktop_local_agent_runtime",
                    "diagnostic": true,
                    "visibility": "model_context"
                },
                {
                    "role": "user",
                    "content": "上一轮用户问题"
                }
            ]
        }))
        .unwrap();
        let workspace_root = PathBuf::from(".");
        let model_request = build_model_request(&request, "继续");
        let prompt_stack = resolve_prompt_stack(&request, &model_request);
        let context = build_agent_run_context(
            "proj-test",
            "chat-context",
            "local-context",
            &workspace_root,
            &request,
            "继续",
            &model_request,
            &prompt_stack,
        );
        let model_contents = model_request
            .messages
            .iter()
            .map(|message| message.content.as_str())
            .collect::<Vec<_>>();

        assert_eq!(context.history_context.excluded_diagnostics.len(), 1);
        assert!(context.history_context.excluded_diagnostics[0]
            .content_preview
            .contains("HTTP 429"));
        assert!(!model_contents
            .iter()
            .any(|content| content.contains("HTTP 429")));
        assert!(model_contents
            .iter()
            .any(|content| content.contains("这条诊断允许进入模型上下文")));
    }

    #[test]
    fn agent_run_context_records_attachment_image_routes_and_downgrades() {
        let request = serde_json::from_value::<LocalChatRequest>(json!({
            "projectId": "proj-test",
            "chatSessionId": "chat-attachments",
            "message": "请分析附件",
            "workspacePath": ".",
            "providerId": "openai",
            "modelName": "gpt-test",
            "attachments": [
                {
                    "attachmentId": "att_img_inline",
                    "name": "截图.png",
                    "mimeType": "image/png",
                    "kind": "image",
                    "routingMode": "inline_image",
                    "extractionStatus": "image_data_url",
                    "dataUrl": "data:image/png;base64,AAAA"
                },
                {
                    "attachmentId": "att_img_local",
                    "name": "本地截图.png",
                    "mimeType": "image/png",
                    "kind": "image",
                    "routingMode": "local_extract",
                    "extractionStatus": "metadata_only",
                    "dataUrl": "data:image/png;base64,BBBB"
                }
            ]
        }))
        .unwrap();
        let model_request = build_model_request(&request, "请分析附件");
        let prompt_stack = resolve_prompt_stack(&request, &model_request);
        let context = build_agent_run_context(
            "proj-test",
            "chat-attachments",
            "local-attachments",
            &PathBuf::from("."),
            &request,
            "请分析附件",
            &model_request,
            &prompt_stack,
        );

        assert_eq!(context.runtime_context.attachment_routes.len(), 2);
        let inline_route = context
            .runtime_context
            .attachment_routes
            .iter()
            .find(|route| route.attachment_id == "att_img_inline")
            .unwrap();
        assert!(inline_route.requested_image_input);
        assert!(inline_route.included_as_image_part);
        assert!(inline_route.downgrade_reason.is_empty());

        let local_route = context
            .runtime_context
            .attachment_routes
            .iter()
            .find(|route| route.attachment_id == "att_img_local")
            .unwrap();
        assert!(!local_route.requested_image_input);
        assert!(!local_route.included_as_image_part);
        assert_eq!(
            local_route.downgrade_reason,
            "routing_mode_text_or_metadata_only"
        );
        assert_eq!(context.runtime_context.provider_profile.image_part_count, 1);
        assert!(context.runtime_context.provider_profile.supports_image_url);
        assert_eq!(
            context.runtime_context.prompt_stack.version,
            "prompt-stack/v1"
        );
    }

    #[test]
    fn planning_gate_records_state_changing_request_without_blocking_runtime() {
        let request = serde_json::from_value::<LocalChatRequest>(json!({
            "projectId": "proj-test",
            "chatSessionId": "chat-plan",
            "message": "修改 src/main.rs 并验证",
            "workspacePath": "."
        }))
        .unwrap();
        let model_request = build_model_request(&request, "修改 src/main.rs 并验证");
        let task_goal = build_task_goal("local-plan", &request.message, &model_request);
        let task_tree = planning::TaskTree::for_goal("local-plan", &task_goal);
        let clarity = assess_clarity(&request.message, &request, &model_request);
        let plan = create_plan_state(
            "local-plan",
            &task_goal,
            &clarity,
            "completed",
            123,
            None,
            &task_tree,
        );

        assert_eq!(clarity.task_type, "implementation");
        assert!(clarity.requires_confirmation);
        assert_eq!(plan.status, "completed");
        assert!(plan
            .nodes
            .iter()
            .any(|node| node.node_id == "node-confirm-local-plan"));
    }

    #[test]
    fn retry_router_classifies_path_failures_as_search() {
        let model_result = ModelStepResult::empty_loop_result();
        let tool_result = crate::liuagent_core::ToolExecutionResult {
            tool_result_id: "result_missing".to_string(),
            tool_call_id: "call_read_missing".to_string(),
            name: "read_file".to_string(),
            ok: false,
            content: json!({}),
            summary: "目标路径不存在".to_string(),
            error_code: "file.not_found".to_string(),
            error: "missing".to_string(),
        };
        let agent_loop = AgentLoopResult {
            model_steps: vec![model_result.clone()],
            model_input_snapshots: Vec::new(),
            planned_tools: Vec::new(),
            tool_results: vec![tool_result.clone()],
            candidate_solutions: Vec::new(),
            attempts: Vec::new(),
            verification: AgentLoopVerification {
                status: "failed".to_string(),
                summary: "missing file".to_string(),
                evidence: Vec::new(),
            },
            stopped_reason: "tool_failed".to_string(),
            awaiting_permission: false,
        };

        let decision = route_failure(
            "local-retry",
            "failed",
            None,
            &agent_loop,
            &[tool_result],
            &model_result,
        );

        assert_eq!(decision.route, "search");
        assert_eq!(decision.failure_type, "path_not_found");
        assert!(decision.retry_allowed);
    }

    #[test]
    fn observations_keep_runtime_and_permission_diagnostics_user_visible() {
        let model_result = ModelStepResult {
            ok: false,
            mode: "openai_compatible".to_string(),
            provider_id: "local-provider".to_string(),
            model_name: "local-model".to_string(),
            status: "failed".to_string(),
            content: String::new(),
            reasoning_content: String::new(),
            tool_calls: Vec::new(),
            allow_compat_text_tool_call: false,
            compat_text_tool_call_detected: false,
            summary: "model failed".to_string(),
            error_code: "model.unavailable".to_string(),
            error: "model unavailable".to_string(),
        };
        let tool_result = crate::liuagent_core::ToolExecutionResult {
            tool_result_id: "result_call_write".to_string(),
            tool_call_id: "call_write".to_string(),
            name: "write_file".to_string(),
            ok: false,
            content: json!({}),
            summary: "permission required".to_string(),
            error_code: "permission.required".to_string(),
            error: "permission required".to_string(),
        };

        let observations = build_observations(
            "local-observation",
            &model_result,
            &[tool_result],
            "waiting_approval",
            Some("approval"),
            "",
            "",
            "permission.required",
        );

        assert!(observations.iter().any(|observation| {
            observation.source == "model_output"
                && observation.visibility == "model_context"
                && observation.error_code == "model.unavailable"
        }));
        assert!(observations.iter().any(|observation| {
            observation.source == "tool_result"
                && observation.visibility == "user_visible"
                && observation.tool_call_id == "call_write"
        }));
        assert!(observations.iter().any(|observation| {
            observation.source == "runtime_error"
                && observation.visibility == "user_visible"
                && observation.summary.contains("approval")
        }));
    }

    #[test]
    fn runtime_scheduler_state_records_waiting_approval_and_pending_tools() {
        let planned_tool = PlannedLocalTool {
            tool_call_id: "call_write".to_string(),
            name: "write_file".to_string(),
            arguments: json!({"path": "a.txt", "content": "hello"}),
            summary: "write file".to_string(),
        };
        let tool_result = crate::liuagent_core::ToolExecutionResult {
            tool_result_id: "result_call_write".to_string(),
            tool_call_id: "call_write".to_string(),
            name: "write_file".to_string(),
            ok: false,
            content: json!({}),
            summary: "permission required".to_string(),
            error_code: "permission.required".to_string(),
            error: "permission required".to_string(),
        };
        let agent_loop = AgentLoopResult {
            model_steps: vec![ModelStepResult {
                ok: true,
                mode: "openai_compatible".to_string(),
                provider_id: "local-provider".to_string(),
                model_name: "local-model".to_string(),
                status: "completed".to_string(),
                content: String::new(),
                reasoning_content: String::new(),
                tool_calls: vec![planned_tool.clone()],
                allow_compat_text_tool_call: false,
                compat_text_tool_call_detected: false,
                summary: "planned tool".to_string(),
                error_code: String::new(),
                error: String::new(),
            }],
            model_input_snapshots: Vec::new(),
            planned_tools: vec![planned_tool.clone()],
            tool_results: vec![tool_result.clone()],
            candidate_solutions: Vec::new(),
            attempts: Vec::new(),
            verification: AgentLoopVerification {
                status: "blocked".to_string(),
                summary: "waiting approval".to_string(),
                evidence: Vec::new(),
            },
            stopped_reason: "waiting_approval".to_string(),
            awaiting_permission: true,
        };

        let scheduler_state = build_runtime_scheduler_state(
            "waiting_approval",
            Some("approval"),
            &agent_loop,
            &[planned_tool],
            &[tool_result],
        );

        assert_eq!(scheduler_state.status, "waiting_approval");
        assert_eq!(scheduler_state.waiting_for, "approval");
        assert_eq!(scheduler_state.run_state.status, "waiting_approval");
        assert_eq!(scheduler_state.run_state.pending_request_id, "");
        assert_eq!(
            scheduler_state.run_state.pending_tool_call_ids,
            vec!["call_write"]
        );
        assert_eq!(scheduler_state.tool_batches.len(), 1);
        assert_eq!(
            scheduler_state.tool_batches[0].pending_tool_call_ids,
            vec!["call_write"]
        );
        assert_eq!(scheduler_state.next_action, "wait_for_approval");
        assert_eq!(scheduler_state.pending_tool_call_ids, vec!["call_write"]);
        assert_eq!(scheduler_state.model_round_count, 1);
        assert_eq!(scheduler_state.tool_round_count, 1);
    }

    #[test]
    fn verification_report_records_blocked_side_effect_targets() {
        let planned_tool = PlannedLocalTool {
            tool_call_id: "call_write".to_string(),
            name: "write_file".to_string(),
            arguments: json!({"path": "docs/plan.md", "content": "hello"}),
            summary: "write file".to_string(),
        };
        let tool_result = crate::liuagent_core::ToolExecutionResult {
            tool_result_id: "result_call_write".to_string(),
            tool_call_id: "call_write".to_string(),
            name: "write_file".to_string(),
            ok: false,
            content: json!({}),
            summary: "permission required".to_string(),
            error_code: "permission.required".to_string(),
            error: "permission required".to_string(),
        };
        let agent_loop = AgentLoopResult {
            model_steps: Vec::new(),
            model_input_snapshots: Vec::new(),
            planned_tools: vec![planned_tool.clone()],
            tool_results: vec![tool_result.clone()],
            candidate_solutions: Vec::new(),
            attempts: Vec::new(),
            verification: AgentLoopVerification {
                status: "waiting_approval".to_string(),
                summary: "waiting approval".to_string(),
                evidence: vec!["permission.required".to_string()],
            },
            stopped_reason: "waiting_approval".to_string(),
            awaiting_permission: true,
        };

        let report = build_verification_report(
            "waiting_approval",
            Some("approval"),
            &agent_loop,
            &[planned_tool],
            &[tool_result],
            &TaskGoal {
                version: "task-goal/test".to_string(),
                goal_id: "goal-test".to_string(),
                title: "write protected file".to_string(),
                user_request: "write protected file".to_string(),
                intent: "modification".to_string(),
                target_object: "protected.txt".to_string(),
                success_criteria: vec!["permission is respected".to_string()],
                constraints: vec!["requires approval".to_string()],
                created_at_epoch_ms: epoch_millis(),
            },
        );

        assert_eq!(report.overall_status, "blocked");
        assert!(report
            .evidence
            .iter()
            .any(|item| item.contains("permission_blocked_side_effects=1")));
        assert!(report
            .evidence
            .iter()
            .any(|item| item.contains("local_targets=docs/plan.md")));
        let tool_execution_check = report
            .checks
            .iter()
            .find(|check| check.check_type == "tool_execution")
            .expect("tool execution check");
        assert_eq!(tool_execution_check.status, "blocked");
        assert!(tool_execution_check.summary.contains("权限阻塞副作用 1"));
        let target_scope_check = report
            .checks
            .iter()
            .find(|check| check.check_type == "target_scope")
            .expect("target scope check");
        assert_eq!(target_scope_check.status, "passed");
        assert!(target_scope_check.summary.contains("docs/plan.md"));
    }

    #[test]
    fn implementation_request_waits_for_plan_confirmation_before_agent_loop() {
        let dir = std::env::temp_dir().join(format!("liuagent_plan_gate_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();

        let result = start_local_chat(LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-plan-test".to_string(),
            message_id: Some("msg-user".to_string()),
            assistant_message_id: None,
            message: "实现规划机制模块".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: None,
            model_name: None,
            system_prompt: None,
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: None,
        });

        assert!(!result.ok);
        assert!(result.plan_status.is_empty());
        assert_eq!(result.error_code, "planning.confirmation_required");
        assert_eq!(
            result.model_result["agent_loop"]["round_count"].as_u64(),
            Some(0)
        );
        assert_eq!(result.tool_results.len(), 1);
        assert_eq!(result.tool_results[0].name, "planning_gate");
        assert_eq!(
            result.tool_results[0].content["permissionRequest"]["requestId"],
            plan_confirmation_request_id("chat-plan-test", "msg-user")
        );
        assert!(result
            .runtime_events
            .iter()
            .any(|event| event["type"] == "approval_required"));
        assert!(PathBuf::from(&result.requirement_record_path).exists());
        let req = serde_json::from_str::<Value>(
            &fs::read_to_string(&result.requirement_record_path).unwrap(),
        )
        .unwrap();
        assert!(req["plan_status"].as_str().unwrap_or_default().is_empty());
        assert_eq!(
            req["current_state_delta"]["waiting_for"],
            "plan_confirmation"
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn matching_plan_confirmation_allows_implementation_request_to_continue() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_plan_gate_confirmed_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();

        let result = start_local_chat(LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-plan-confirmed-test".to_string(),
            message_id: Some("msg-user".to_string()),
            assistant_message_id: None,
            message: "实现规划机制模块".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: None,
            model_name: None,
            system_prompt: None,
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: Some(plan_confirmation_request_id(
                    "chat-plan-confirmed-test",
                    "msg-user",
                )),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.model_result["mode"], "mock");
        assert!(result.tool_results.is_empty());
        assert!(result.error_code.is_empty());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn session_plan_confirmation_allows_implementation_request_to_continue() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_plan_gate_session_confirmed_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();

        let result = start_local_chat(LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-plan-session-confirmed-test".to_string(),
            message_id: Some("msg-user".to_string()),
            assistant_message_id: None,
            message: "实现规划机制模块".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: None,
            model_name: None,
            system_prompt: None,
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: Some(plan_confirmation_request_id(
                    "chat-plan-session-confirmed-test",
                    "msg-user",
                )),
                decision: "approve_session".to_string(),
                grant_scope: Some("session".to_string()),
                comment: None,
            }),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.model_result["mode"], "mock");
        assert!(result.tool_results.is_empty());
        assert!(result.error_code.is_empty());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn full_access_decision_allows_plan_confirmation_to_continue() {
        let dir =
            std::env::temp_dir().join(format!("liuagent_plan_gate_full_access_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();

        let result = start_local_chat(LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-plan-full-access-test".to_string(),
            message_id: Some("msg-user".to_string()),
            assistant_message_id: None,
            message: "实现规划机制模块".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: None,
            model_name: None,
            system_prompt: None,
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: None,
                decision: "approve_session".to_string(),
                grant_scope: Some("session_full_access".to_string()),
                comment: Some("desktop_local_agent_full_access".to_string()),
            }),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.model_result["mode"], "mock");
        assert!(result.tool_results.is_empty());
        assert!(result.error_code.is_empty());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn unrelated_permission_decision_does_not_bypass_plan_confirmation() {
        let dir = std::env::temp_dir().join(format!(
            "liuagent_plan_gate_wrong_decision_{}",
            epoch_millis()
        ));
        fs::create_dir_all(&dir).unwrap();

        let result = start_local_chat(LocalChatRequest {
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-plan-wrong-decision-test".to_string(),
            message_id: Some("msg-user".to_string()),
            assistant_message_id: None,
            message: "实现规划机制模块".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            history: Vec::new(),
            provider_id: None,
            model_name: None,
            system_prompt: None,
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: Some(crate::liuagent_core::types::PermissionDecisionInput {
                request_id: Some("perm_call_write_file.write".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "planning.confirmation_required");
        assert_eq!(result.tool_results.len(), 1);
        assert_eq!(result.tool_results[0].name, "planning_gate");
        assert_eq!(
            result.tool_results[0].content["permissionRequest"]["requestId"],
            plan_confirmation_request_id("chat-plan-wrong-decision-test", "msg-user")
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn query_request_runs_agent_loop() {
        let dir = std::env::temp_dir().join(format!("liuagent_query_loop_{}", epoch_millis()));
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
            system_prompt_parts: Vec::new(),
            temperature: None,
            model_runtime: None,
            ai_entry_file: None,
            attachments: Vec::new(),
            backend_context: None,
            permission_decision: None,
        });

        assert!(result.ok, "{}", result.error);
        assert!(result.plan_status.is_empty());
        assert_eq!(result.model_result["mode"], "mock");
        let _ = fs::remove_dir_all(dir);
    }
}
