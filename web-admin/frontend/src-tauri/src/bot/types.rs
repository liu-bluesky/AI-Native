use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::liuagent_core::{
    LocalBackendContext, LocalChatAttachment, LocalChatMessage, LocalModelRuntimeConfig,
    PermissionDecisionInput,
};

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct BotConnectorConfig {
    pub connector_id: String,
    pub platform: String,
    pub name: String,
    #[serde(default)]
    pub system_prompt: String,
    #[serde(default)]
    pub provider_id: String,
    #[serde(default)]
    pub model_name: String,
    #[serde(default)]
    pub reply_identity: String,
    #[serde(default)]
    pub owner_username: String,
    #[serde(default)]
    pub sandbox_mode: String,
    #[serde(default)]
    pub high_risk_tool_confirm: Option<bool>,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct BotSourceContext {
    #[serde(default)]
    pub source_type: String,
    #[serde(default)]
    pub external_chat_id: String,
    #[serde(default)]
    pub external_chat_name: String,
    #[serde(default)]
    pub external_message_id: String,
    #[serde(default)]
    pub thread_id: String,
    #[serde(default)]
    pub raw: Value,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct BotPermissionContract {
    #[serde(default)]
    pub channel: BotChannelPermission,
    #[serde(default)]
    pub delegated_user: BotDelegatedUserPermission,
    #[serde(default)]
    pub runner: BotRunnerPermission,
    #[serde(default)]
    pub oauth: BotOAuthPermission,
    #[serde(default)]
    pub confirmations: BotConfirmationPolicy,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct BotChannelPermission {
    #[serde(default)]
    pub platform: String,
    #[serde(default)]
    pub connector_id: String,
    #[serde(default)]
    pub scope: String,
    #[serde(default)]
    pub can_receive_messages: bool,
    #[serde(default)]
    pub can_reply_messages: bool,
    #[serde(default)]
    pub can_download_attachments: bool,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct BotDelegatedUserPermission {
    #[serde(default)]
    pub username: String,
    #[serde(default)]
    pub project_id: String,
    #[serde(default)]
    pub project_access: String,
    #[serde(default)]
    pub provider_access: String,
    #[serde(default)]
    pub tool_access: String,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct BotRunnerPermission {
    #[serde(default)]
    pub mode: String,
    #[serde(default)]
    pub workspace_path: String,
    #[serde(default)]
    pub sandbox_mode: String,
    #[serde(default)]
    pub command_execution: String,
    #[serde(default)]
    pub file_mutation: String,
    #[serde(default)]
    pub deployment: String,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct BotOAuthPermission {
    #[serde(default)]
    pub policy: String,
    #[serde(default)]
    pub allowed_scopes: Vec<String>,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct BotConfirmationPolicy {
    #[serde(default)]
    pub shell_commands: String,
    #[serde(default)]
    pub file_writes: String,
    #[serde(default)]
    pub external_side_effects: String,
    #[serde(default)]
    pub deployments: String,
    #[serde(default)]
    pub high_risk_tools: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BotChatRequest {
    pub project_id: String,
    pub chat_session_id: String,
    pub message_id: Option<String>,
    pub assistant_message_id: Option<String>,
    pub message: String,
    pub workspace_path: String,
    #[serde(default)]
    pub history: Vec<LocalChatMessage>,
    pub connector: BotConnectorConfig,
    #[serde(default)]
    pub source_context: BotSourceContext,
    #[serde(default)]
    pub permission_contract: Option<BotPermissionContract>,
    pub provider_id: Option<String>,
    pub model_name: Option<String>,
    pub model_runtime: Option<LocalModelRuntimeConfig>,
    #[serde(default)]
    pub attachments: Vec<LocalChatAttachment>,
    #[serde(default)]
    pub mcp_config: Value,
    pub backend_context: Option<LocalBackendContext>,
    pub permission_decision: Option<PermissionDecisionInput>,
}
