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
    pub temperature: Option<f64>,
    pub max_tokens: Option<u32>,
    pub model_runtime: Option<LocalModelRuntimeConfig>,
    pub permission_decision: Option<PermissionDecisionInput>,
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

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LocalChatMessage {
    pub role: String,
    pub content: String,
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
    pub max_tokens: Option<u32>,
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
    pub model_result: Value,
    pub tool_results: Vec<ToolExecutionResult>,
    pub operations: Value,
    pub runtime_events: Vec<Value>,
    pub summary: String,
    pub error_code: String,
    pub error: String,
}

impl LocalChatResult {
    pub fn failed(chat_session_id: String, error: ToolError) -> Self {
        Self {
            ok: false,
            plan_status: String::new(),
            session_id: String::new(),
            chat_session_id,
            requirement_record_path: String::new(),
            gateway_result: None,
            assistant_content: String::new(),
            model_result: json!({}),
            tool_results: Vec::new(),
            operations: json!([]),
            runtime_events: Vec::new(),
            summary: error.message.clone(),
            error_code: error.code,
            error: error.message,
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
        let content = if error.code == "permission.required" {
            serde_json::from_str::<Value>(&error.message)
                .map(|request| json!({"permissionRequest": request}))
                .unwrap_or_else(|_| json!({}))
        } else {
            json!({})
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
