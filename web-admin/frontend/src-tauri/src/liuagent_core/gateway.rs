//! Agent Gateway 最小本地入口。
//!
//! 这里只做标准 invocation/session 元数据准备和本地 requirement 记录，不执行模型和工具。

use serde_json::{json, Value};
use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use super::definitions::builtin_tool_definitions;
use super::types::{
    AgentInvocationRequest, AgentInvocationResult, AgentRuntimeSessionSummary,
    ProjectContextBundleSummary, PromptBundleSummary, RequirementSessionSummary, ToolError,
    ToolManifestBundleSummary,
};
use super::workspace::resolve_workspace_root;

const GATEWAY_REQUIREMENT_SCHEMA_VERSION: u32 = 1;

pub fn prepare_agent_invocation(request: AgentInvocationRequest) -> AgentInvocationResult {
    let chat_session_id = request.chat_session_id.trim().to_string();
    match prepare_agent_invocation_inner(request) {
        Ok(result) => result,
        Err(error) => AgentInvocationResult::failed(chat_session_id, error),
    }
}

pub fn prepare_agent_invocation_inner(
    request: AgentInvocationRequest,
) -> Result<AgentInvocationResult, ToolError> {
    let project_id = required_non_empty(&request.project_id, "projectId")?;
    let chat_session_id = required_non_empty(&request.chat_session_id, "chatSessionId")?;
    let user_message = required_non_empty(&request.user_message, "userMessage")?;
    let workspace_root = resolve_workspace_root(&request.workspace_path)?;
    let source = normalized_optional(request.source.as_deref(), "project_chat");
    let adapter_kind = normalized_optional(request.adapter_kind.as_deref(), "desktop");
    let invocation_id = normalized_optional(
        request.invocation_id.as_deref(),
        &format!(
            "inv_{}_{}",
            sanitize_path_segment(&chat_session_id),
            epoch_millis()
        ),
    );
    let requirement_id = format!("req_{}", sanitize_path_segment(&chat_session_id));
    let runtime_session_id = format!("runtime_{}", epoch_millis());
    let requirement_path = requirement_record_path(&workspace_root, &project_id, &chat_session_id);
    let state_path = workspace_root
        .join(".ai-employee")
        .join("agent-runtime-v2")
        .join("task-runs")
        .join(format!(
            "{}.json",
            sanitize_path_segment(&runtime_session_id)
        ));
    let agent_id = normalized_optional(request.agent_id.as_deref(), "project-default-agent");
    let prompt_bundle_id = normalized_optional(
        request.prompt_bundle_id.as_deref(),
        "project-default-prompt",
    );
    let tool_bundle_id =
        normalized_optional(request.tool_bundle_id.as_deref(), "desktop-builtin-tools");
    let builtin_tool_count = builtin_tool_definitions().len();

    let requirement_session = RequirementSessionSummary {
        requirement_id: requirement_id.clone(),
        project_id: project_id.clone(),
        chat_session_id: chat_session_id.clone(),
        source: source.clone(),
        root_goal: user_message.clone(),
        sync_state: "local_only".to_string(),
        local_record_path: requirement_path.to_string_lossy().to_string(),
    };
    let project_context_bundle = ProjectContextBundleSummary {
        project_id: project_id.clone(),
        agent_id: agent_id.clone(),
        source: "backend-metadata".to_string(),
    };
    let prompt_bundle = PromptBundleSummary {
        prompt_bundle_id: prompt_bundle_id.clone(),
        source: "backend-metadata".to_string(),
    };
    let tool_manifest_bundle = ToolManifestBundleSummary {
        tool_bundle_id: tool_bundle_id.clone(),
        builtin_tool_count,
        source: "desktop-tauri".to_string(),
    };
    let agent_runtime_session = AgentRuntimeSessionSummary {
        runtime_session_id: runtime_session_id.clone(),
        adapter_kind: adapter_kind.clone(),
        workspace_path: workspace_root.to_string_lossy().to_string(),
        state_path: state_path.to_string_lossy().to_string(),
    };
    let invocation = json!({
        "invocationId": invocation_id,
        "source": source,
        "adapterKind": adapter_kind,
        "projectId": project_id,
        "chatSessionId": chat_session_id,
        "agentId": agent_id,
        "userMessage": user_message,
        "workspaceBinding": {
            "workspacePath": workspace_root.to_string_lossy(),
            "scope": "desktop-local",
            "serverCanAccess": false
        },
        "recordPolicy": {
            "recordRequirement": request.record_requirement.unwrap_or(true),
            "recordTaskTree": true,
            "recordWorkFacts": true,
            "recordAuditSummary": true,
            "canonicalEntry": "Unified MCP"
        },
        "capabilities": request.capabilities
    });

    write_requirement_record(
        &requirement_path,
        json!({
            "record_type": "desktop-agent-gateway-requirement",
            "version": GATEWAY_REQUIREMENT_SCHEMA_VERSION,
            "storage_scope": "desktop-workspace",
            "storage_mode": "local-first",
            "project_id": project_id,
            "chat_session_id": requirement_session.chat_session_id,
            "title": requirement_session.root_goal,
            "root_goal": requirement_session.root_goal,
            "latest_status": "prepared",
            "phase": "agent_gateway",
            "step": "prepare_agent_invocation",
            "workflow_skill": {
                "id": "liuagent-cli-agent-gateway",
                "source": "docs/liuAgent-cli/design/15-agent-gateway-mcp.md",
                "runtime": "tauri"
            },
            "agent_gateway": {
                "invocation": invocation,
                "requirement_session": requirement_session,
                "project_context_bundle": project_context_bundle,
                "prompt_bundle": prompt_bundle,
                "tool_manifest_bundle": tool_manifest_bundle,
                "agent_runtime_session": agent_runtime_session
            },
            "task_tree": {
                "id": format!("local-tree-{}", sanitize_path_segment(&request.chat_session_id)),
                "chat_session_id": request.chat_session_id,
                "title": user_message,
                "root_goal": user_message,
                "status": "prepared",
                "current_node_id": "local-node-agent-gateway",
                "progress_percent": 10
            },
            "current_task_node": {
                "id": "local-node-agent-gateway",
                "title": "通过 Agent Gateway 创建本地运行会话",
                "status": "done",
                "stage_key": "agent_gateway"
            },
            "task_branches": [
                {
                    "id": "local-node-agent-gateway",
                    "title": "通过 Agent Gateway 创建本地运行会话",
                    "status": "done",
                    "stage_key": "agent_gateway"
                }
            ],
            "history": [
                {
                    "event": "agent_invocation_prepared",
                    "source": source,
                    "adapter_kind": adapter_kind,
                    "created_at_epoch_ms": epoch_millis()
                }
            ],
            "sync_status": "local_only",
            "updated_at_epoch_ms": epoch_millis()
        }),
    )?;

    Ok(AgentInvocationResult {
        ok: true,
        invocation,
        requirement_session,
        project_context_bundle,
        prompt_bundle,
        tool_manifest_bundle,
        agent_runtime_session,
        requirement_record_path: requirement_path.to_string_lossy().to_string(),
        summary: "Agent Gateway invocation prepared locally".to_string(),
        error_code: String::new(),
        error: String::new(),
    })
}

pub fn requirement_record_path(root: &PathBuf, project_id: &str, chat_session_id: &str) -> PathBuf {
    root.join(".ai-employee")
        .join("requirements")
        .join(sanitize_path_segment(project_id))
        .join(format!("{}.json", sanitize_path_segment(chat_session_id)))
}

pub fn write_requirement_record(path: &PathBuf, content: Value) -> Result<(), ToolError> {
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

pub fn sanitize_path_segment(value: &str) -> String {
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

pub fn epoch_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_millis())
        .unwrap_or(0)
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

fn normalized_optional(value: Option<&str>, fallback: &str) -> String {
    value
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .unwrap_or(fallback)
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prepares_gateway_invocation_and_requirement_record() {
        let dir = std::env::temp_dir().join(format!("liuagent_gateway_{}", epoch_millis()));
        fs::create_dir_all(&dir).unwrap();

        let result = prepare_agent_invocation(AgentInvocationRequest {
            invocation_id: None,
            source: Some("project_chat".to_string()),
            adapter_kind: Some("desktop".to_string()),
            project_id: "proj-test".to_string(),
            chat_session_id: "chat-test".to_string(),
            user_message: "本地执行需求".to_string(),
            workspace_path: dir.to_string_lossy().to_string(),
            agent_id: None,
            prompt_bundle_id: None,
            tool_bundle_id: None,
            capabilities: vec!["local_runner".to_string()],
            record_requirement: Some(true),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.requirement_session.source, "project_chat");
        assert_eq!(result.tool_manifest_bundle.builtin_tool_count, 18);
        assert!(PathBuf::from(&result.requirement_record_path).exists());
        let _ = fs::remove_dir_all(dir);
    }
}
