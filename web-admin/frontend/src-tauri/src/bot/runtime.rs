use serde_json::{json, Map, Value};

use crate::bot::types::{
    BotChannelPermission, BotChatRequest, BotConfirmationPolicy, BotDelegatedUserPermission,
    BotOAuthPermission, BotPermissionContract, BotRunnerPermission,
};
use crate::liuagent_core::{
    self, LocalChatPromptPart, LocalChatRequest, LocalChatResult, ToolError,
};

const BOT_CONNECTOR_PROMPT_SOURCE: &str = "bot_connector.system_prompt";

pub fn start_bot_chat_with_event_sink<F>(request: BotChatRequest, event_sink: F) -> LocalChatResult
where
    F: Fn(Value),
{
    let chat_session_id = request.chat_session_id.trim().to_string();
    let local_request = build_local_chat_request(request);
    if local_request.message.trim().is_empty() {
        return LocalChatResult::failed(
            chat_session_id,
            ToolError::new("bot.message_required", "bot message is required"),
        );
    }
    if let Err(error) = validate_bot_model_runtime(&local_request) {
        return LocalChatResult::failed(chat_session_id, error);
    }
    liuagent_core::start_local_chat_with_event_sink(local_request, event_sink)
}

pub fn build_local_chat_request(request: BotChatRequest) -> LocalChatRequest {
    let connector_prompt = request.connector.system_prompt.trim().to_string();
    let mut system_prompt_parts = Vec::new();
    if !connector_prompt.is_empty() {
        system_prompt_parts.push(LocalChatPromptPart {
            source: BOT_CONNECTOR_PROMPT_SOURCE.to_string(),
            priority: Some(100),
            content: connector_prompt,
        });
    }

    let provider_id = first_non_empty([
        request.provider_id.as_deref(),
        Some(request.connector.provider_id.as_str()),
    ]);
    let model_name = first_non_empty([
        request.model_name.as_deref(),
        Some(request.connector.model_name.as_str()),
    ]);
    let permission_contract = normalize_permission_contract(&request);

    LocalChatRequest {
        project_id: request.project_id,
        chat_session_id: request.chat_session_id,
        message_id: request.message_id,
        assistant_message_id: request.assistant_message_id,
        message: request.message,
        workspace_path: request.workspace_path,
        history: request.history,
        provider_id,
        model_name,
        system_prompt: None,
        system_prompt_parts,
        temperature: None,
        model_runtime: request.model_runtime,
        ai_entry_file: None,
        attachments: request.attachments,
        media_tools: Vec::new(),
        mcp_config: with_bot_context(
            request.mcp_config,
            json!({
                "connector": request.connector,
                "sourceContext": request.source_context,
                "permissionContract": permission_contract,
                "runtime": {
                    "source": "tauri_bot_local_chat",
                    "executionAuthority": "delegated_user_desktop_runner",
                    "promptPolicy": "connector_system_prompt_only"
                }
            }),
        ),
        backend_context: request.backend_context,
        permission_decision: request.permission_decision,
        resume_from_checkpoint: false,
    }
}

fn normalize_permission_contract(request: &BotChatRequest) -> BotPermissionContract {
    let mut contract = request.permission_contract.clone().unwrap_or_default();
    let platform = request.connector.platform.trim();
    let connector_id = request.connector.connector_id.trim();
    let owner_username = request.connector.owner_username.trim();
    let sandbox_mode = first_non_empty([
        Some(request.connector.sandbox_mode.as_str()),
        Some("workspace-write"),
    ])
    .unwrap_or_else(|| "workspace-write".to_string());
    let high_risk_confirm = request.connector.high_risk_tool_confirm.unwrap_or(true);

    if contract.channel.scope.trim().is_empty() {
        contract.channel = BotChannelPermission {
            platform: platform.to_string(),
            connector_id: connector_id.to_string(),
            scope: "transport_only".to_string(),
            can_receive_messages: true,
            can_reply_messages: true,
            can_download_attachments: true,
        };
    }
    if contract.delegated_user.username.trim().is_empty() {
        contract.delegated_user = BotDelegatedUserPermission {
            username: owner_username.to_string(),
            project_id: request.project_id.clone(),
            project_access: "owner_visible_projects_only".to_string(),
            provider_access: "same_as_project_chat_user_provider_scope".to_string(),
            tool_access: "same_as_desktop_project_chat_tools".to_string(),
        };
    }
    if contract.runner.mode.trim().is_empty() {
        contract.runner = BotRunnerPermission {
            mode: "desktop_local_agent".to_string(),
            workspace_path: request.workspace_path.clone(),
            sandbox_mode,
            command_execution: "desktop_runner_confirmed".to_string(),
            file_mutation: "desktop_runner_confirmed".to_string(),
            deployment: "project_deploy_config_and_separate_confirmation".to_string(),
        };
    }
    if contract.oauth.policy.trim().is_empty() {
        contract.oauth = BotOAuthPermission {
            policy: "user_scoped_oauth_only".to_string(),
            allowed_scopes: Vec::new(),
        };
    }
    if contract.confirmations.high_risk_tools.trim().is_empty() {
        let high_risk_value = if high_risk_confirm {
            "confirm"
        } else {
            "policy_defined"
        };
        contract.confirmations = BotConfirmationPolicy {
            shell_commands: "confirm".to_string(),
            file_writes: "confirm".to_string(),
            external_side_effects: "confirm".to_string(),
            deployments: "separate_confirm".to_string(),
            high_risk_tools: high_risk_value.to_string(),
        };
    }
    contract
}

fn first_non_empty<'a>(values: impl IntoIterator<Item = Option<&'a str>>) -> Option<String> {
    values
        .into_iter()
        .flatten()
        .map(str::trim)
        .find(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn validate_bot_model_runtime(request: &LocalChatRequest) -> Result<(), ToolError> {
    let Some(runtime) = request.model_runtime.as_ref() else {
        return Err(bot_model_runtime_unconfigured_error());
    };
    let mode = runtime.mode.as_deref().unwrap_or("").trim();
    if mode != "direct-openai-compatible" {
        return Err(bot_model_runtime_unconfigured_error());
    }
    let model_name =
        first_non_empty([runtime.model_name.as_deref(), request.model_name.as_deref()]);
    let base_url = runtime.base_url.as_deref().unwrap_or("").trim();
    if model_name.is_none() || base_url.is_empty() {
        return Err(bot_model_runtime_unconfigured_error());
    }
    Ok(())
}

fn bot_model_runtime_unconfigured_error() -> ToolError {
    ToolError::new(
        "bot.model_runtime_unconfigured",
        "机器人未配置可用的桌面模型运行时，已跳过回复。",
    )
}

fn with_bot_context(mcp_config: Value, bot_context: Value) -> Value {
    let object = match mcp_config {
        Value::Object(object) => object,
        _ => Map::new(),
    };
    let mut object = object;
    object.insert("_bot_context".to_string(), bot_context);
    Value::Object(object)
}
