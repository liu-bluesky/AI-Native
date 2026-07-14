//! liuAgent Core 对外数据结构。
//!
//! 这些结构需要保持 JSON 友好，方便 CLI、Desktop 和未来 Web Bridge 使用同一套协议。

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolExecutionRequest {
    pub tool_call_id: Option<String>,
    pub name: String,
    #[serde(default)]
    pub arguments: Value,
    pub workspace_path: String,
    pub permission_decision: Option<PermissionDecisionInput>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalChatRequest {
    pub project_id: String,
    pub chat_session_id: String,
    pub message_id: Option<String>,
    pub assistant_message_id: Option<String>,
    pub message: String,
    pub workspace_path: String,
    #[serde(default)]
    pub history: Vec<LocalChatMessage>,
    pub provider_id: Option<String>,
    pub model_name: Option<String>,
    pub system_prompt: Option<String>,
    #[serde(default)]
    pub system_prompt_parts: Vec<LocalChatPromptPart>,
    pub temperature: Option<f64>,
    pub model_runtime: Option<LocalModelRuntimeConfig>,
    #[serde(default, alias = "ai_entry_file")]
    pub ai_entry_file: Option<String>,
    #[serde(default)]
    pub attachments: Vec<LocalChatAttachment>,
    #[serde(default)]
    pub mcp_config: Value,
    pub backend_context: Option<LocalBackendContext>,
    pub permission_decision: Option<PermissionDecisionInput>,
}

impl Default for LocalChatRequest {
    fn default() -> Self {
        Self {
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
            mcp_config: json!({}),
            backend_context: None,
            permission_decision: None,
        }
    }
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LocalBackendContext {
    pub api_base_url: String,
    pub token: String,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LocalChatPromptPart {
    pub source: String,
    pub priority: Option<i64>,
    pub content: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalRuntimeRecoveryRequest {
    pub project_id: String,
    pub chat_session_id: String,
    pub workspace_path: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalRuntimeJobRequest {
    pub workspace_path: String,
    pub state_path: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalRuntimeOutboxRequest {
    pub project_id: String,
    pub chat_session_id: Option<String>,
    pub workspace_path: String,
    pub limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalRuntimeOutboxAckRequest {
    pub project_id: String,
    pub chat_session_id: String,
    pub workspace_path: String,
    #[serde(default)]
    pub event_ids: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalRuntimeEventsRequest {
    pub project_id: String,
    pub chat_session_id: String,
    pub workspace_path: String,
    pub after_event_id: Option<String>,
    pub limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OfflineCacheSaveRequest {
    pub workspace_path: String,
    pub cache_kind: String,
    pub project_id: Option<String>,
    pub chat_session_id: Option<String>,
    pub provider_id: Option<String>,
    #[serde(default)]
    pub payload: Value,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OfflineCacheLoadRequest {
    pub workspace_path: String,
    pub cache_kind: String,
    pub project_id: Option<String>,
    pub chat_session_id: Option<String>,
    pub provider_id: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OfflineCacheCleanupRequest {
    pub workspace_path: String,
    pub project_id: String,
    pub chat_session_id: String,
    #[serde(default)]
    pub event_ids: Vec<String>,
    #[serde(default)]
    pub server_refs: Value,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LocalChatMessage {
    pub role: String,
    pub content: String,
    #[serde(default, alias = "reasoning_content")]
    pub reasoning_content: Option<String>,
    #[serde(default, alias = "source_kind")]
    pub source_kind: Option<String>,
    #[serde(default)]
    pub diagnostic: Option<bool>,
    #[serde(default)]
    pub visibility: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LocalChatAttachment {
    pub attachment_id: Option<String>,
    pub name: String,
    pub mime_type: Option<String>,
    pub size: Option<u64>,
    pub kind: Option<String>,
    pub routing_mode: Option<String>,
    pub extraction_status: Option<String>,
    pub data_url: Option<String>,
    pub extracted_text: Option<String>,
    pub provider_file_id: Option<String>,
    pub error: Option<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentRunContext {
    pub version: String,
    pub project_id: String,
    pub chat_session_id: String,
    pub run_id: String,
    pub workspace_path: String,
    pub user_request: AgentRunUserRequest,
    pub history_context: AgentRunHistoryContext,
    pub project_context: AgentRunProjectContext,
    pub runtime_context: AgentRunRuntimeContext,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentRunUserRequest {
    pub raw: String,
    pub normalized: String,
    pub attachments: Vec<AgentRunAttachmentSummary>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentRunAttachmentSummary {
    pub attachment_id: String,
    pub name: String,
    pub mime_type: String,
    pub kind: String,
    pub routing_mode: String,
    pub extraction_status: String,
    pub has_data_url: bool,
    pub has_extracted_text: bool,
    pub has_provider_file_id: bool,
    pub error: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentRunHistoryContext {
    pub conversation_summary: String,
    pub recent_user_messages: Vec<AgentRunHistoryMessageSummary>,
    pub recent_assistant_messages: Vec<AgentRunHistoryMessageSummary>,
    pub excluded_diagnostics: Vec<AgentRunHistoryMessageSummary>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentRunHistoryMessageSummary {
    pub role: String,
    pub source_kind: String,
    pub visibility: String,
    pub diagnostic: bool,
    pub content_preview: String,
    pub reasoning_content_preview: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentRunProjectContext {
    pub project_id: String,
    pub chat_session_id: String,
    pub workspace_path: String,
    pub chat_settings: Value,
    pub workspace_snapshot: Value,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentRunRuntimeContext {
    pub provider_id: String,
    pub model_name: String,
    pub mode: String,
    pub model_capabilities: Vec<String>,
    pub prompt_stack: PromptStack,
    pub provider_profile: ModelCompatibilityProfile,
    pub attachment_routes: Vec<AgentRunAttachmentRoute>,
    pub available_tools: Vec<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ModelCompatibilityProfile {
    pub version: String,
    pub provider_id: String,
    pub model_name: String,
    pub mode: String,
    pub supports_tools: bool,
    pub supports_reasoning_content_replay: bool,
    pub requires_reasoning_content_replay: bool,
    pub supports_image_url: bool,
    pub image_input_status: String,
    pub image_part_count: usize,
    pub tool_role_mode: String,
    pub stream_mode: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentRunAttachmentRoute {
    pub attachment_id: String,
    pub name: String,
    pub routing_mode: String,
    pub mime_type: String,
    pub requested_image_input: bool,
    pub included_as_image_part: bool,
    pub included_as_text_context: bool,
    pub downgrade_reason: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Observation {
    pub observation_id: String,
    pub source: String,
    pub visibility: String,
    pub summary: String,
    pub content_ref: String,
    pub tool_call_id: String,
    pub error_code: String,
    pub created_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeSchedulerState {
    pub version: String,
    pub status: String,
    pub waiting_for: String,
    pub run_state: RunState,
    pub tool_batches: Vec<ToolBatchState>,
    pub model_round_count: usize,
    pub tool_round_count: usize,
    pub planned_tool_count: usize,
    pub completed_tool_count: usize,
    pub failed_tool_count: usize,
    pub pending_tool_call_ids: Vec<String>,
    pub next_action: String,
    pub stopped_reason: String,
    pub updated_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct RunState {
    pub version: String,
    pub status: String,
    pub waiting_for: String,
    pub pending_request_id: String,
    pub pending_tool_call_ids: Vec<String>,
    pub pending_tool_batch_id: String,
    pub pending_adapter_action_id: String,
    pub updated_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ToolBatchState {
    pub batch_id: String,
    pub status: String,
    pub tool_call_ids: Vec<String>,
    pub pending_tool_call_ids: Vec<String>,
    pub completed_tool_call_ids: Vec<String>,
    pub failed_tool_call_ids: Vec<String>,
    pub created_at_epoch_ms: u128,
    pub updated_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct PromptStack {
    pub version: String,
    pub items: Vec<PromptStackItem>,
    pub resolved_system_prompt_hash: String,
    pub resolved_system_prompt_preview: String,
    pub warnings: Vec<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct PromptStackItem {
    pub source: String,
    pub priority: i64,
    pub content_hash: String,
    pub content_preview: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ClarityAssessment {
    pub version: String,
    pub score: u8,
    pub task_type: String,
    pub goal_clear: bool,
    pub target_clear: bool,
    pub scope_clear: bool,
    pub expected_result_clear: bool,
    pub requires_confirmation: bool,
    pub confirmation_reason: String,
    pub interpretation: String,
    pub ambiguities: Vec<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct TaskGoal {
    pub version: String,
    pub goal_id: String,
    pub title: String,
    pub user_request: String,
    pub intent: String,
    pub target_object: String,
    pub success_criteria: Vec<String>,
    pub constraints: Vec<String>,
    pub created_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct PlanState {
    pub version: String,
    pub plan_id: String,
    pub status: String,
    pub root_goal: String,
    pub nodes: Vec<PlanNode>,
    pub current_node_id: String,
    pub destructive_steps: Vec<String>,
    pub created_at_epoch_ms: u128,
    pub updated_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct PlanNode {
    pub node_id: String,
    pub title: String,
    pub status: String,
    pub verification_result: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct RetryDecision {
    pub version: String,
    pub decision_id: String,
    pub route: String,
    pub failure_type: String,
    pub reason: String,
    pub retry_allowed: bool,
    pub max_attempts: usize,
    pub observed_attempts: usize,
    pub exit_condition: String,
    pub created_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct MemoryWritePlan {
    pub version: String,
    pub items: Vec<MemoryWritePlanItem>,
    pub long_memory_candidates: Vec<String>,
    pub created_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct MemoryWritePlanItem {
    pub scope: String,
    pub target: String,
    pub content: String,
    pub status: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct VerificationReport {
    pub version: String,
    pub verification_id: String,
    pub target_node_id: String,
    pub overall_status: String,
    pub checks: Vec<VerificationCheck>,
    pub evidence: Vec<String>,
    pub created_at_epoch_ms: u128,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct VerificationCheck {
    #[serde(rename = "type")]
    pub check_type: String,
    pub status: String,
    pub summary: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderFileUploadRequest {
    pub provider_id: Option<String>,
    pub base_url: String,
    pub api_key: String,
    pub filename: String,
    pub mime_type: Option<String>,
    pub purpose: Option<String>,
    #[serde(default)]
    pub file_bytes: Vec<u8>,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderFileUploadResult {
    pub ok: bool,
    pub provider_id: String,
    pub provider_file_id: String,
    pub filename: String,
    pub mime_type: String,
    pub purpose: String,
    pub status: String,
    pub raw: Value,
    pub error_code: String,
    pub error: String,
}

impl ProviderFileUploadResult {
    pub fn failed(request: ProviderFileUploadRequest, error: ToolError) -> Self {
        Self {
            ok: false,
            provider_id: request.provider_id.unwrap_or_default(),
            provider_file_id: String::new(),
            filename: request.filename,
            mime_type: request.mime_type.unwrap_or_default(),
            purpose: request.purpose.unwrap_or_default(),
            status: "failed".to_string(),
            raw: json!({}),
            error_code: error.code,
            error: error.message,
        }
    }
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LocalModelRuntimeConfig {
    pub mode: Option<String>,
    pub provider_id: Option<String>,
    pub model_name: Option<String>,
    pub base_url: Option<String>,
    pub api_key: Option<String>,
    pub api_key_env: Option<String>,
    pub gateway_url: Option<String>,
    pub temperature: Option<f64>,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalChatResult {
    pub ok: bool,
    pub plan_status: String,
    pub session_id: String,
    pub chat_session_id: String,
    pub requirement_record_path: String,
    pub gateway_result: Option<AgentInvocationResult>,
    pub assistant_content: String,
    pub assistant_reasoning_content: String,
    pub model_result: Value,
    pub tool_results: Vec<ToolExecutionResult>,
    pub operations: Value,
    pub runtime_events: Vec<Value>,
    pub conversation_lifecycle: Value,
    pub summary: String,
    pub user_visible_error_summary: String,
    pub diagnostic: Value,
    pub error_code: String,
    pub error: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalPermissionReplyResult {
    pub ok: bool,
    pub decision: String,
    pub request_id: String,
    pub tool_name: String,
    pub reasoning: String,
    pub error_code: String,
    pub error: String,
}

impl LocalPermissionReplyResult {
    pub fn failed(error: ToolError) -> Self {
        Self {
            ok: false,
            decision: "not_an_approval".to_string(),
            request_id: String::new(),
            tool_name: String::new(),
            reasoning: String::new(),
            error_code: error.code,
            error: error.message,
        }
    }
}

impl LocalChatResult {
    pub fn failed(chat_session_id: String, error: ToolError) -> Self {
        let error_code = error.code;
        let error_message = error.message;
        Self {
            ok: false,
            plan_status: String::new(),
            session_id: String::new(),
            chat_session_id,
            requirement_record_path: String::new(),
            gateway_result: None,
            assistant_content: String::new(),
            assistant_reasoning_content: String::new(),
            model_result: json!({}),
            tool_results: Vec::new(),
            operations: json!([]),
            runtime_events: Vec::new(),
            conversation_lifecycle: json!({
                "version": "desktop-conversation-lifecycle/v1",
                "status": "failed",
                "nodes": []
            }),
            summary: error_message.clone(),
            user_visible_error_summary: error_message.clone(),
            diagnostic: json!({
                "version": "response-format/v1",
                "diagnostic_separated": true,
                "error_code": error_code.clone(),
                "error": error_message.clone()
            }),
            error_code,
            error: error_message,
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalRuntimeRecoveryResult {
    pub ok: bool,
    pub project_id: String,
    pub chat_session_id: String,
    pub workspace_path: String,
    pub state: Value,
    pub runtime_events: Vec<Value>,
    pub summary: String,
    pub error_code: String,
    pub error: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalRuntimeJobResult {
    pub ok: bool,
    pub workspace_path: String,
    pub job: Value,
    pub summary: String,
    pub error_code: String,
    pub error: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalRuntimeOutboxResult {
    pub ok: bool,
    pub project_id: String,
    pub chat_session_id: String,
    pub workspace_path: String,
    pub entries: Vec<Value>,
    pub deleted_count: usize,
    pub summary: String,
    pub error_code: String,
    pub error: String,
}

impl LocalRuntimeOutboxResult {
    pub fn failed(
        project_id: String,
        chat_session_id: String,
        workspace_path: String,
        error: ToolError,
    ) -> Self {
        Self {
            ok: false,
            project_id,
            chat_session_id,
            workspace_path,
            entries: Vec::new(),
            deleted_count: 0,
            summary: error.message.clone(),
            error_code: error.code,
            error: error.message,
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalRuntimeEventsResult {
    pub ok: bool,
    pub project_id: String,
    pub chat_session_id: String,
    pub workspace_path: String,
    pub events: Vec<Value>,
    pub summary: String,
    pub error_code: String,
    pub error: String,
}

impl LocalRuntimeEventsResult {
    pub fn failed(request: LocalRuntimeEventsRequest, error: ToolError) -> Self {
        Self {
            ok: false,
            project_id: request.project_id,
            chat_session_id: request.chat_session_id,
            workspace_path: request.workspace_path,
            events: Vec::new(),
            summary: error.message.clone(),
            error_code: error.code,
            error: error.message,
        }
    }
}

impl LocalRuntimeRecoveryResult {
    pub fn failed(request: LocalRuntimeRecoveryRequest, error: ToolError) -> Self {
        Self {
            ok: false,
            project_id: request.project_id,
            chat_session_id: request.chat_session_id,
            workspace_path: request.workspace_path,
            state: json!({}),
            runtime_events: Vec::new(),
            summary: error.message.clone(),
            error_code: error.code,
            error: error.message,
        }
    }
}

impl LocalRuntimeJobResult {
    pub fn ok(workspace_path: String, job: Value, summary: String) -> Self {
        Self {
            ok: true,
            workspace_path,
            job,
            summary,
            error_code: String::new(),
            error: String::new(),
        }
    }

    pub fn failed(request: LocalRuntimeJobRequest, error: ToolError) -> Self {
        Self {
            ok: false,
            workspace_path: request.workspace_path,
            job: json!({}),
            summary: error.message.clone(),
            error_code: error.code,
            error: error.message,
        }
    }
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentInvocationRequest {
    pub invocation_id: Option<String>,
    pub source: Option<String>,
    pub adapter_kind: Option<String>,
    pub project_id: String,
    pub chat_session_id: String,
    pub user_message: String,
    pub workspace_path: String,
    pub agent_id: Option<String>,
    pub prompt_bundle_id: Option<String>,
    pub tool_bundle_id: Option<String>,
    #[serde(default)]
    pub capabilities: Vec<String>,
    #[serde(default)]
    pub record_requirement: Option<bool>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentInvocationResult {
    pub ok: bool,
    pub invocation: Value,
    pub requirement_session: RequirementSessionSummary,
    pub project_context_bundle: ProjectContextBundleSummary,
    pub prompt_bundle: PromptBundleSummary,
    pub tool_manifest_bundle: ToolManifestBundleSummary,
    pub agent_runtime_session: AgentRuntimeSessionSummary,
    pub requirement_record_path: String,
    pub summary: String,
    pub error_code: String,
    pub error: String,
}

impl AgentInvocationResult {
    pub fn failed(chat_session_id: String, error: ToolError) -> Self {
        Self {
            ok: false,
            invocation: json!({}),
            requirement_session: RequirementSessionSummary::empty(chat_session_id),
            project_context_bundle: ProjectContextBundleSummary::empty(),
            prompt_bundle: PromptBundleSummary::empty(),
            tool_manifest_bundle: ToolManifestBundleSummary::empty(),
            agent_runtime_session: AgentRuntimeSessionSummary::empty(),
            requirement_record_path: String::new(),
            summary: error.message.clone(),
            error_code: error.code,
            error: error.message,
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OfflineCacheResult {
    pub ok: bool,
    pub workspace_path: String,
    pub result: Value,
    pub summary: String,
    pub error_code: String,
    pub error: String,
}

impl OfflineCacheResult {
    pub fn ok(workspace_path: String, result: Value) -> Self {
        let summary = result
            .get("summary")
            .and_then(Value::as_str)
            .unwrap_or("offline cache operation completed")
            .to_string();
        Self {
            ok: true,
            workspace_path,
            result,
            summary,
            error_code: String::new(),
            error: String::new(),
        }
    }

    pub fn failed(workspace_path: String, error: ToolError) -> Self {
        Self {
            ok: false,
            workspace_path,
            result: json!({}),
            summary: error.message.clone(),
            error_code: error.code,
            error: error.message,
        }
    }
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct RequirementSessionSummary {
    pub requirement_id: String,
    pub project_id: String,
    pub chat_session_id: String,
    pub source: String,
    pub root_goal: String,
    pub sync_state: String,
    pub local_record_path: String,
}

impl RequirementSessionSummary {
    fn empty(chat_session_id: String) -> Self {
        Self {
            requirement_id: String::new(),
            project_id: String::new(),
            chat_session_id,
            source: String::new(),
            root_goal: String::new(),
            sync_state: "failed".to_string(),
            local_record_path: String::new(),
        }
    }
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ProjectContextBundleSummary {
    pub project_id: String,
    pub agent_id: String,
    pub source: String,
}

impl ProjectContextBundleSummary {
    fn empty() -> Self {
        Self {
            project_id: String::new(),
            agent_id: String::new(),
            source: String::new(),
        }
    }
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct PromptBundleSummary {
    pub prompt_bundle_id: String,
    pub source: String,
}

impl PromptBundleSummary {
    fn empty() -> Self {
        Self {
            prompt_bundle_id: String::new(),
            source: String::new(),
        }
    }
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ToolManifestBundleSummary {
    pub tool_bundle_id: String,
    pub builtin_tool_count: usize,
    pub source: String,
}

impl ToolManifestBundleSummary {
    fn empty() -> Self {
        Self {
            tool_bundle_id: String::new(),
            builtin_tool_count: 0,
            source: String::new(),
        }
    }
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AgentRuntimeSessionSummary {
    pub runtime_session_id: String,
    pub adapter_kind: String,
    pub workspace_path: String,
    pub state_path: String,
}

impl AgentRuntimeSessionSummary {
    fn empty() -> Self {
        Self {
            runtime_session_id: String::new(),
            adapter_kind: String::new(),
            workspace_path: String::new(),
            state_path: String::new(),
        }
    }
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ToolExecutionResult {
    pub tool_result_id: String,
    pub tool_call_id: String,
    pub name: String,
    pub ok: bool,
    pub content: Value,
    pub summary: String,
    pub error_code: String,
    pub error: String,
}

impl ToolExecutionResult {
    pub fn ok(tool_call_id: String, name: String, content: Value, summary: String) -> Self {
        Self {
            tool_result_id: format!("result_{tool_call_id}"),
            tool_call_id,
            name,
            ok: true,
            content,
            summary,
            error_code: String::new(),
            error: String::new(),
        }
    }

    pub fn failed(tool_call_id: String, name: String, error: ToolError) -> Self {
        let status = tool_error_status(&error.code);
        let content = if error.code == "permission.required" {
            serde_json::from_str::<Value>(&error.message)
                .map(|request| json!({"permissionRequest": request}))
                .unwrap_or_else(|_| json!({}))
        } else if status == "no_signal" {
            json!({
                "status": status,
                "status_reason": "timeout_without_completion_evidence",
                "terminal": false,
                "requires_judgement": true
            })
        } else if is_recoverable_tool_error(&error.code) {
            json!({
                "status": status,
                "terminal": false,
                "recoverable": true,
                "recovery_scope": "model_can_retry_or_degrade"
            })
        } else {
            json!({
                "status": status,
                "terminal": status == "failed"
            })
        };
        Self {
            tool_result_id: format!("result_{tool_call_id}"),
            tool_call_id,
            name,
            ok: false,
            content,
            summary: error.message.clone(),
            error_code: error.code,
            error: error.message,
        }
    }
}

fn tool_error_status(error_code: &str) -> &'static str {
    match error_code {
        "tool.timeout" => "no_signal",
        "permission.required" => "waiting",
        _ => "failed",
    }
}

fn is_recoverable_tool_error(error_code: &str) -> bool {
    matches!(
        error_code,
        "tool.schema_invalid"
            | "web_search.unconfigured"
            | "web_extract.unconfigured"
            | "tool.disabled"
            | "mcp.config_missing"
            | "mcp.config_invalid"
            | "mcp.failed"
    )
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolDefinition {
    pub name: &'static str,
    pub description: &'static str,
    pub action: &'static str,
    pub risk: &'static str,
    pub requires_approval: bool,
    pub scope: &'static str,
    pub input_schema: Value,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct PermissionDecisionInput {
    pub request_id: Option<String>,
    pub decision: String,
    pub grant_scope: Option<String>,
    pub comment: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionRequest {
    pub request_id: String,
    pub action: String,
    pub risk: String,
    pub reason: String,
    pub scope: String,
    pub preview: Value,
    pub options: Vec<PermissionOption>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionOption {
    pub decision: String,
    pub label: String,
    pub grant_scope: Option<String>,
}

#[derive(Debug)]
pub struct ToolError {
    pub code: String,
    pub message: String,
}

impl ToolError {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
}
