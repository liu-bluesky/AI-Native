//! 本地运行复盘候选。
//!
//! 只记录聚合指标和可审核的优化建议，不保存用户对话或模型思维内容，
//! 也不直接修改提示词、模型配置或权限策略。

use serde_json::{json, Value};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;

use super::gateway::epoch_millis;
use super::paths::desktop_runtime_root;
use super::types::ToolError;

pub fn record_runtime_learning_candidate(
    workspace_root: &Path,
    project_id: &str,
    chat_session_id: &str,
    session_id: &str,
    run_status: &str,
    diagnostic: &Value,
) -> Result<Value, ToolError> {
    let recommendations = build_recommendations(diagnostic);
    let now = epoch_millis();
    let record = json!({
        "record_type": "liuagent-learning-candidate",
        "version": 1,
        "status": "pending_review",
        "automatic_application": false,
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "session_id": session_id,
        "run_status": run_status,
        "diagnostic": diagnostic,
        "recommendations": recommendations,
        "privacy": {
            "stores_raw_user_content": false,
            "stores_raw_assistant_content": false,
            "stores_reasoning_content": false,
        },
        "created_at_epoch_ms": now,
    });
    let path = desktop_runtime_root(workspace_root)
        .join("learning")
        .join("candidates.jsonl");
    let parent = path.parent().ok_or_else(|| {
        ToolError::new(
            "learning.path_invalid",
            "learning candidate path has no parent",
        )
    })?;
    fs::create_dir_all(parent).map_err(|error| {
        ToolError::new(
            "learning.directory_create_failed",
            format!("failed to create learning directory: {error}"),
        )
    })?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| {
            ToolError::new(
                "learning.write_failed",
                format!("failed to open learning candidate log: {error}"),
            )
        })?;
    serde_json::to_writer(&mut file, &record).map_err(|error| {
        ToolError::new(
            "learning.serialize_failed",
            format!("failed to serialize learning candidate: {error}"),
        )
    })?;
    file.write_all(b"\n").map_err(|error| {
        ToolError::new(
            "learning.write_failed",
            format!("failed to append learning candidate: {error}"),
        )
    })?;
    Ok(record)
}

fn build_recommendations(diagnostic: &Value) -> Vec<Value> {
    let mut recommendations = Vec::new();
    let preflight_calls = diagnostic["preflight_model_call_count"]
        .as_u64()
        .unwrap_or(0);
    let total_ms = diagnostic["total_duration_ms"].as_u64().unwrap_or(0);
    let preflight_ms = diagnostic["preflight_duration_ms"].as_u64().unwrap_or(0);
    let prompt_tokens = diagnostic["prompt_stack"]["estimated_tokens"]
        .as_u64()
        .unwrap_or(0);
    let history_messages = diagnostic["history_message_count"].as_u64().unwrap_or(0);

    if preflight_calls >= 2
        && total_ms >= 1_500
        && preflight_ms.saturating_mul(100) >= total_ms * 35
    {
        recommendations.push(json!({
            "kind": "preflight_overhead",
            "severity": "high",
            "evidence": { "preflight_model_call_count": preflight_calls, "preflight_duration_ms": preflight_ms, "total_duration_ms": total_ms },
            "suggested_change": "评估将历史筛选或任务路由改为本地规则/缓存命中后跳过；保留复杂或低置信任务的模型路由。",
        }));
    }
    if prompt_tokens >= 4_000 {
        recommendations.push(json!({
            "kind": "prompt_budget",
            "severity": "medium",
            "evidence": { "estimated_system_prompt_tokens": prompt_tokens },
            "suggested_change": "审查提示词来源，合并重复规则，并为系统提示词设置预算和截断告警。",
        }));
    }
    if history_messages >= 12 && preflight_calls > 0 {
        recommendations.push(json!({
            "kind": "history_compaction",
            "severity": "medium",
            "evidence": { "history_message_count": history_messages },
            "suggested_change": "对已确认完成的历史轮次生成摘要缓存，避免每轮把完整历史再次送入历史筛选模型。",
        }));
    }
    if recommendations.is_empty() {
        recommendations.push(json!({
            "kind": "baseline",
            "severity": "info",
            "suggested_change": "保留本次聚合指标，等待更多运行样本后再提出策略调整。",
        }));
    }
    recommendations
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn persists_redacted_learning_candidate_with_preflight_recommendation() {
        let directory = std::env::temp_dir().join(format!("liuagent-learning-{}", epoch_millis()));
        let diagnostic = json!({
            "total_duration_ms": 4_000,
            "preflight_duration_ms": 2_000,
            "preflight_model_call_count": 2,
            "history_message_count": 4,
            "prompt_stack": { "estimated_tokens": 120 },
        });
        let record = record_runtime_learning_candidate(
            &directory,
            "project",
            "chat",
            "session",
            "completed",
            &diagnostic,
        )
        .unwrap();

        assert_eq!(record["status"], "pending_review");
        assert_eq!(record["automatic_application"], false);
        assert_eq!(record["privacy"]["stores_raw_user_content"], false);
        assert_eq!(record["recommendations"][0]["kind"], "preflight_overhead");
        assert!(directory
            .join(".ai-employee/desktop-agent-runtime/learning/candidates.jsonl")
            .exists());
        let _ = fs::remove_dir_all(directory);
    }
}
