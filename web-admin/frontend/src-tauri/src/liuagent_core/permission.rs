//! Permission Gate。
//!
//! 所有写文件、命令、网络写入和 MCP 变更类工具都必须先经过这里生成权限请求。

use serde_json::Value;

use super::types::{PermissionDecisionInput, PermissionOption, PermissionRequest, ToolError};

const CACHED_SESSION_GRANT_PREFIX: &str = "__liuagent_cached_session_grant:";

pub fn require_approval(
    tool_call_id: &str,
    action: &str,
    risk: &str,
    scope: &str,
    reason: &str,
    preview: Value,
    decision: Option<&PermissionDecisionInput>,
) -> Result<(), ToolError> {
    if is_approved(tool_call_id, action, decision) {
        return Ok(());
    }
    Err(permission_required_error(PermissionRequest {
        request_id: permission_request_id(tool_call_id, action),
        action: action.to_string(),
        risk: risk.to_string(),
        reason: reason.to_string(),
        scope: scope.to_string(),
        preview,
        options: vec![
            PermissionOption {
                decision: "approve_once".to_string(),
                label: "允许一次".to_string(),
                grant_scope: Some("once".to_string()),
            },
            PermissionOption {
                decision: "approve_session".to_string(),
                label: "本会话允许".to_string(),
                grant_scope: Some("session".to_string()),
            },
            PermissionOption {
                decision: "deny".to_string(),
                label: "拒绝".to_string(),
                grant_scope: None,
            },
        ],
    }))
}

fn is_approved(
    tool_call_id: &str,
    action: &str,
    decision: Option<&PermissionDecisionInput>,
) -> bool {
    let Some(decision) = decision else {
        return false;
    };
    let decision_value = decision.decision.trim();
    let grant_scope = decision.grant_scope.as_deref().unwrap_or("").trim();
    let _comment = decision.comment.as_deref().unwrap_or("").trim();
    if is_full_access_decision(decision) {
        return true;
    }
    let expected_request_id = permission_request_id(tool_call_id, action);
    if decision_value == "approve_once" {
        if !grant_scope.is_empty() && grant_scope != "once" {
            return false;
        }
        return decision
            .request_id
            .as_deref()
            .map(str::trim)
            .map(|value| value == expected_request_id)
            .unwrap_or(true);
    }
    if decision_value == "approve_session" {
        if !matches!(grant_scope, "session" | "current_session") {
            return false;
        }
        if let Some(request_id) = decision.request_id.as_deref().map(str::trim) {
            return request_id == expected_request_id;
        }
        return _comment == cached_session_grant_comment(action);
    }
    false
}

pub fn is_full_access_decision(decision: &PermissionDecisionInput) -> bool {
    let decision_value = decision.decision.trim();
    let grant_scope = decision.grant_scope.as_deref().unwrap_or("").trim();
    if decision_value != "approve_session" {
        return false;
    }
    matches!(
        grant_scope,
        "session_full_access" | "full_access" | "workspace_full_access"
    )
}

fn permission_required_error(request: PermissionRequest) -> ToolError {
    let details = serde_json::to_string(&request).unwrap_or_else(|_| "{}".to_string());
    ToolError::new("permission.required", details)
}

pub fn permission_request_id(tool_call_id: &str, action: &str) -> String {
    format!(
        "perm_{}_{}",
        sanitize_id(tool_call_id),
        action.replace('.', "_")
    )
}

pub fn cached_session_grant_comment(action: &str) -> String {
    format!("{CACHED_SESSION_GRANT_PREFIX}{action}")
}

fn sanitize_id(value: &str) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '_' || ch == '-' {
                ch
            } else {
                '_'
            }
        })
        .collect()
}
