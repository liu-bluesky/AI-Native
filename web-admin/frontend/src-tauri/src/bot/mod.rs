//! Desktop bot business boundary.
//!
//! This module owns robot connector semantics and converts platform messages
//! into the desktop local-agent runtime request. The local-agent runtime stays
//! in `liuagent_core`; bot-specific prompts, connector metadata, and source
//! context belong here.

mod runtime;
mod types;

pub mod feishu;
pub use runtime::start_bot_chat_with_event_sink;
pub use types::BotChatRequest;

#[cfg(test)]
mod tests {
    use super::runtime::{build_local_chat_request, start_bot_chat_with_event_sink};
    use super::types::{BotChatRequest, BotConnectorConfig, BotSourceContext};
    use serde_json::json;

    fn base_request() -> BotChatRequest {
        BotChatRequest {
            project_id: "proj-1".to_string(),
            chat_session_id: "chat-1".to_string(),
            message_id: Some("msg-1".to_string()),
            assistant_message_id: Some("assistant-1".to_string()),
            message: "列出项目".to_string(),
            workspace_path: "/tmp/workspace".to_string(),
            history: Vec::new(),
            connector: BotConnectorConfig {
                connector_id: "conn-1".to_string(),
                platform: "feishu".to_string(),
                name: "飞书机器人".to_string(),
                system_prompt: String::new(),
                provider_id: "provider-from-connector".to_string(),
                model_name: "model-from-connector".to_string(),
                reply_identity: "bot".to_string(),
                owner_username: "tester".to_string(),
                sandbox_mode: "workspace-write".to_string(),
                high_risk_tool_confirm: Some(true),
            },
            source_context: BotSourceContext {
                source_type: "group_message".to_string(),
                external_chat_id: "oc-1".to_string(),
                external_chat_name: "研发群".to_string(),
                external_message_id: "om-1".to_string(),
                thread_id: String::new(),
                raw: json!({"event": "message"}),
            },
            permission_contract: None,
            provider_id: None,
            model_name: None,
            model_runtime: None,
            attachments: Vec::new(),
            mcp_config: json!({}),
            backend_context: None,
            permission_decision: None,
        }
    }

    #[test]
    fn configured_connector_prompt_is_the_only_bot_prompt() {
        let mut request = base_request();
        request.connector.system_prompt = "只回答项目问题".to_string();

        let local_request = build_local_chat_request(request);

        assert_eq!(local_request.system_prompt, None);
        assert_eq!(local_request.system_prompt_parts.len(), 1);
        assert_eq!(
            local_request.system_prompt_parts[0].source,
            "bot_connector.system_prompt"
        );
        assert_eq!(
            local_request.system_prompt_parts[0].content,
            "只回答项目问题"
        );
        assert_eq!(
            local_request.provider_id.as_deref(),
            Some("provider-from-connector")
        );
        assert_eq!(
            local_request.model_name.as_deref(),
            Some("model-from-connector")
        );
    }

    #[test]
    fn blank_connector_prompt_does_not_add_a_bot_prompt() {
        let request = base_request();

        let local_request = build_local_chat_request(request);

        assert_eq!(local_request.system_prompt, None);
        assert!(local_request.system_prompt_parts.is_empty());
        assert_eq!(
            local_request.mcp_config["_bot_context"]["connector"]["connectorId"],
            "conn-1"
        );
        assert_eq!(
            local_request.mcp_config["_bot_context"]["sourceContext"]["externalChatName"],
            "研发群"
        );
        assert_eq!(
            local_request.mcp_config["_bot_context"]["permissionContract"]["channel"]["scope"],
            "transport_only"
        );
        assert_eq!(
            local_request.mcp_config["_bot_context"]["permissionContract"]["delegatedUser"]
                ["username"],
            "tester"
        );
        assert_eq!(
            local_request.mcp_config["_bot_context"]["permissionContract"]["runner"]["mode"],
            "desktop_local_agent"
        );
        assert_eq!(
            local_request.mcp_config["_bot_context"]["permissionContract"]["confirmations"]
                ["highRiskTools"],
            "confirm"
        );
    }

    #[test]
    fn request_provider_overrides_connector_default() {
        let mut request = base_request();
        request.provider_id = Some("provider-request".to_string());
        request.model_name = Some("model-request".to_string());

        let local_request = build_local_chat_request(request);

        assert_eq!(
            local_request.provider_id.as_deref(),
            Some("provider-request")
        );
        assert_eq!(local_request.model_name.as_deref(), Some("model-request"));
    }

    #[test]
    fn missing_model_runtime_does_not_return_mock_bot_reply() {
        let result = start_bot_chat_with_event_sink(base_request(), |_| {});

        assert!(!result.ok);
        assert_eq!(result.error_code, "bot.model_runtime_unconfigured");
        assert!(result.assistant_content.trim().is_empty());
        assert!(!result.summary.contains("已在桌面端本机走通"));
        assert!(!result.summary.contains("desktop-bot-global"));
        assert!(!result.summary.contains("本地骨架回复"));
    }
}
