use serde::Serialize;
use serde_json::{json, Value};

use super::types::ToolExecutionResult;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionErrorCategory {
    Input,
    Transient,
    ToolExecution,
    PostProcess,
    Business,
    Permission,
    Security,
    Harness,
}

impl ExecutionErrorCategory {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Input => "input",
            Self::Transient => "transient",
            Self::ToolExecution => "tool_execution",
            Self::PostProcess => "post_process",
            Self::Business => "business",
            Self::Permission => "permission",
            Self::Security => "security",
            Self::Harness => "harness",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionErrorPhase {
    Validate,
    Execute,
    Response,
    Parse,
    Persist,
    Feedback,
    Schedule,
}

impl ExecutionErrorPhase {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Validate => "validate",
            Self::Execute => "execute",
            Self::Response => "response",
            Self::Parse => "parse",
            Self::Persist => "persist",
            Self::Feedback => "feedback",
            Self::Schedule => "schedule",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionAction {
    Retry,
    Continue,
    Pause,
}

impl ExecutionAction {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Retry => "retry",
            Self::Continue => "continue",
            Self::Pause => "pause",
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolExecutionRecord {
    pub record_version: String,
    pub execution_id: String,
    pub tool_result_id: String,
    pub tool_call_id: String,
    pub tool_name: String,
    pub tool_status: String,
    pub post_process_status: String,
    pub error_category: String,
    pub error_phase: String,
    pub action: String,
    pub retryable: bool,
    pub task_continues: bool,
    pub error_code: String,
    pub error_message: String,
}

pub fn build_tool_execution_record(result: &ToolExecutionResult) -> ToolExecutionRecord {
    let post_process_error = result
        .content
        .get("postProcessError")
        .filter(|_| result.ok)
        .cloned()
        .unwrap_or_else(|| json!({}));
    let classification = if result.ok && result.content.get("postProcessError").is_some() {
        ErrorClassification {
            category: ExecutionErrorCategory::PostProcess,
            phase: ExecutionErrorPhase::Parse,
            action: ExecutionAction::Continue,
            retryable: false,
            task_continues: true,
        }
    } else {
        classify_error(&result.error_code, &result.error)
    };
    let tool_status = if result.ok {
        "succeeded"
    } else if result.error_code == "tool.timeout" {
        "unknown"
    } else {
        "failed"
    };
    let post_process_status = if result.ok && result.content.get("postProcessError").is_some() {
        "failed"
    } else if result.ok {
        "succeeded"
    } else {
        "skipped"
    };
    ToolExecutionRecord {
        record_version: "tool-execution-record/v1".to_string(),
        execution_id: result.tool_result_id.clone(),
        tool_result_id: result.tool_result_id.clone(),
        tool_call_id: result.tool_call_id.clone(),
        tool_name: result.name.clone(),
        tool_status: tool_status.to_string(),
        post_process_status: post_process_status.to_string(),
        error_category: classification.category.as_str().to_string(),
        error_phase: classification.phase.as_str().to_string(),
        action: classification.action.as_str().to_string(),
        retryable: classification.retryable,
        task_continues: classification.task_continues,
        error_code: post_process_error
            .get("code")
            .and_then(Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .unwrap_or(&result.error_code)
            .to_string(),
        error_message: result
            .content
            .get("postProcessError")
            .and_then(|value| value.get("message"))
            .and_then(Value::as_str)
            .unwrap_or(&result.error)
            .to_string(),
    }
}

pub fn build_tool_execution_record_value(result: &ToolExecutionResult) -> Value {
    serde_json::to_value(build_tool_execution_record(result)).unwrap_or_else(|_| json!({}))
}

struct ErrorClassification {
    category: ExecutionErrorCategory,
    phase: ExecutionErrorPhase,
    action: ExecutionAction,
    retryable: bool,
    task_continues: bool,
}

fn classify_error(code: &str, message: &str) -> ErrorClassification {
    let normalized_code = code.trim().to_ascii_lowercase();
    let normalized_message = message.trim().to_ascii_lowercase();
    let category = if normalized_code.contains("permission")
        || normalized_code.contains("auth")
        || normalized_code.contains("unauthorized")
    {
        ExecutionErrorCategory::Permission
    } else if normalized_code.contains("security")
        || normalized_code.contains("out_of_scope")
        || normalized_code.contains("dangerous")
    {
        ExecutionErrorCategory::Security
    } else if normalized_code.contains("post_process")
        || normalized_code.contains("parse")
        || normalized_code.contains("feedback")
    {
        ExecutionErrorCategory::PostProcess
    } else if normalized_code.contains("schema") || normalized_code.contains("argument") {
        ExecutionErrorCategory::Input
    } else if normalized_code.contains("business")
        || normalized_code.contains("conflict")
        || normalized_code.contains("not_found")
        || normalized_code.contains("validation")
    {
        ExecutionErrorCategory::Business
    } else if normalized_code.contains("timeout")
        || normalized_code.contains("network")
        || normalized_code.contains("connection")
        || normalized_code.contains("unavailable")
        || normalized_code.contains("rate_limit")
        || normalized_code.contains("mcp.failed")
        || normalized_message.contains("timeout")
        || normalized_message.contains("timed out")
        || normalized_message.contains("connection reset")
        || normalized_message.contains("connection refused")
        || normalized_message.contains("http 429")
        || normalized_message.contains("http 500")
        || normalized_message.contains("http 502")
        || normalized_message.contains("http 503")
        || normalized_message.contains("http 504")
    {
        ExecutionErrorCategory::Transient
    } else if normalized_code.starts_with("state.")
        || normalized_code.starts_with("runtime.")
        || normalized_code.starts_with("harness.")
    {
        ExecutionErrorCategory::Harness
    } else {
        ExecutionErrorCategory::ToolExecution
    };
    let phase = if matches!(category, ExecutionErrorCategory::Input) {
        ExecutionErrorPhase::Validate
    } else if matches!(category, ExecutionErrorCategory::PostProcess) {
        if normalized_code.contains("parse") {
            ExecutionErrorPhase::Parse
        } else if normalized_code.contains("persist") {
            ExecutionErrorPhase::Persist
        } else {
            ExecutionErrorPhase::Feedback
        }
    } else if matches!(category, ExecutionErrorCategory::Transient)
        && (normalized_code.contains("timeout") || normalized_code.contains("connection"))
    {
        ExecutionErrorPhase::Response
    } else if matches!(category, ExecutionErrorCategory::Harness) {
        ExecutionErrorPhase::Schedule
    } else {
        ExecutionErrorPhase::Execute
    };
    let action = match category {
        ExecutionErrorCategory::Permission
        | ExecutionErrorCategory::Security
        | ExecutionErrorCategory::Business
        | ExecutionErrorCategory::Harness => ExecutionAction::Pause,
        ExecutionErrorCategory::PostProcess => ExecutionAction::Continue,
        ExecutionErrorCategory::Transient => ExecutionAction::Retry,
        ExecutionErrorCategory::Input | ExecutionErrorCategory::ToolExecution => {
            ExecutionAction::Continue
        }
    };
    ErrorClassification {
        category,
        phase,
        retryable: matches!(action, ExecutionAction::Retry),
        task_continues: !matches!(action, ExecutionAction::Pause),
        action,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn result(code: &str, error: &str) -> ToolExecutionResult {
        ToolExecutionResult::failed(
            "call-1".to_string(),
            "plugin_tool".to_string(),
            super::super::types::ToolError::new(code, error),
        )
    }

    #[test]
    fn classifies_post_process_errors_as_continue() {
        let mut successful = ToolExecutionResult::ok(
            "call-1".to_string(),
            "plugin_tool".to_string(),
            json!({"postProcessError": "invalid response shape"}),
            "tool succeeded".to_string(),
        );
        successful.error_code = "tool.post_process_failed".to_string();
        successful.error = "invalid response shape".to_string();
        let record = build_tool_execution_record(&successful);

        assert_eq!(record.tool_status, "succeeded");
        assert_eq!(record.post_process_status, "failed");
        assert_eq!(record.action, "continue");
        assert!(record.task_continues);
    }

    #[test]
    fn classifies_transient_errors_as_retryable() {
        let record = build_tool_execution_record(&result("tool.timeout", "plugin request timeout"));

        assert_eq!(record.error_category, "transient");
        assert_eq!(record.action, "retry");
        assert!(record.retryable);
    }

    #[test]
    fn classifies_permission_errors_as_paused() {
        let record =
            build_tool_execution_record(&result("permission.required", "authorization required"));

        assert_eq!(record.error_category, "permission");
        assert_eq!(record.action, "pause");
        assert!(!record.task_continues);
    }
}
