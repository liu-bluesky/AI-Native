//! 本地审计摘要。
//!
//! 审计只保存必要摘要、风险、工具名、路径/域名等结构化信息，避免记录敏感全文。

use serde_json::{json, Value};

use super::gateway::sanitize_path_segment;
use super::types::{PermissionDecisionInput, ToolExecutionResult};

pub fn build_tool_audit_logs(
    session_id: &str,
    tool_results: &[ToolExecutionResult],
    permission_decision: Option<&PermissionDecisionInput>,
    created_at_epoch_ms: u128,
) -> Vec<Value> {
    tool_results
        .iter()
        .map(|result| {
            let permission_request = result
                .content
                .get("permissionRequest")
                .cloned()
                .unwrap_or_else(|| json!(null));
            let decision = permission_decision
                .map(|decision| {
                    json!({
                        "decision_id": format!(
                            "decision_{}_{}",
                            sanitize_path_segment(&result.tool_call_id),
                            sanitize_path_segment(decision.decision.as_str())
                        ),
                        "request_id": decision.request_id.as_deref().unwrap_or(""),
                        "decision": decision.decision,
                        "grant_scope": decision.grant_scope.as_deref().unwrap_or(""),
                        "comment": decision.comment.as_deref().unwrap_or(""),
                        "idempotency_key": format!(
                            "{}:{}:{}:{}",
                            session_id,
                            result.tool_call_id,
                            decision.request_id.as_deref().unwrap_or(""),
                            decision.decision
                        )
                    })
                })
                .unwrap_or_else(|| json!(null));
            json!({
                "audit_id": format!("audit_{}_{}", session_id, sanitize_path_segment(&result.tool_result_id)),
                "session_id": session_id,
                "tool_call_id": result.tool_call_id,
                "tool_result_id": result.tool_result_id,
                "tool_name": result.name,
                "request": permission_request,
                "decision": decision,
                "result": {
                    "tool_result_id": result.tool_result_id,
                    "ok": result.ok,
                    "summary": result.summary,
                    "error_code": result.error_code,
                    "error": result.error
                },
                "created_at_epoch_ms": created_at_epoch_ms
            })
        })
        .collect()
}
