//! liuAgent 本地核心入口。
//!
//! 这里放 CLI、Tauri Desktop 后续可共用的本地工具运行时。Vue 只负责展示和交互，
//! 服务端只负责配置/数据；本模块负责用户电脑上的受控工具执行。

mod adapters;
mod args;
mod audit;
mod definitions;
mod gateway;
mod permission;
mod planning;
mod runtime;
mod security;
mod state;
mod tools;
mod types;
mod workspace;

pub use definitions::builtin_tool_definitions;
pub use gateway::prepare_agent_invocation;
pub use runtime::start_local_chat_with_event_sink;
pub use runtime::{
    ack_local_runtime_outbox, list_local_runtime_events, list_local_runtime_outbox,
    recover_local_runtime_state,
};
pub use types::{
    AgentInvocationRequest, AgentInvocationResult, LocalChatRequest, LocalChatResult,
    LocalRuntimeEventsRequest, LocalRuntimeEventsResult, LocalRuntimeOutboxAckRequest,
    LocalRuntimeOutboxRequest, LocalRuntimeOutboxResult, LocalRuntimeRecoveryRequest,
    LocalRuntimeRecoveryResult, ToolDefinition, ToolError, ToolExecutionRequest,
    ToolExecutionResult,
};

use tools::command::{check_command_risk, run_command, run_command_with_output_sink};
use tools::file::{apply_patch, delete_file, list_files, read_file, search_text, write_file};
use tools::mcp::{call_mcp_tool, list_mcp_tools, read_mcp_resource};
use tools::network::{download_file, http_get, http_post};
pub fn execute_tool(request: ToolExecutionRequest) -> ToolExecutionResult {
    execute_tool_with_command_output_sink(request, None)
}

pub(crate) fn execute_tool_with_command_output_sink(
    request: ToolExecutionRequest,
    command_output_sink: Option<&dyn Fn(&str, &str)>,
) -> ToolExecutionResult {
    let tool_call_id = normalized_tool_call_id(request.tool_call_id);
    let name = request.name.trim().to_string();
    let result = match name.as_str() {
        "list_files" => list_files(&request.workspace_path, &request.arguments),
        "read_file" => read_file(&request.workspace_path, &request.arguments),
        "search_text" => search_text(&request.workspace_path, &request.arguments),
        "write_file" => write_file(
            &tool_call_id,
            &request.workspace_path,
            &request.arguments,
            request.permission_decision.as_ref(),
        ),
        "delete_file" => delete_file(
            &tool_call_id,
            &request.workspace_path,
            &request.arguments,
            request.permission_decision.as_ref(),
        ),
        "apply_patch" => apply_patch(
            &tool_call_id,
            &request.workspace_path,
            &request.arguments,
            request.permission_decision.as_ref(),
        ),
        "check_command_risk" => check_command_risk(&request.workspace_path, &request.arguments),
        "run_command" if command_output_sink.is_some() => run_command_with_output_sink(
            &tool_call_id,
            &request.workspace_path,
            &request.arguments,
            request.permission_decision.as_ref(),
            command_output_sink,
        ),
        "run_command" => run_command(
            &tool_call_id,
            &request.workspace_path,
            &request.arguments,
            request.permission_decision.as_ref(),
        ),
        "http_get" => http_get(&request.workspace_path, &request.arguments),
        "http_post" => http_post(
            &tool_call_id,
            &request.workspace_path,
            &request.arguments,
            request.permission_decision.as_ref(),
        ),
        "download_file" => download_file(
            &tool_call_id,
            &request.workspace_path,
            &request.arguments,
            request.permission_decision.as_ref(),
        ),
        "list_mcp_tools" => list_mcp_tools(&request.workspace_path, &request.arguments),
        "read_mcp_resource" => read_mcp_resource(&request.workspace_path, &request.arguments),
        "call_mcp_tool" => call_mcp_tool(
            &tool_call_id,
            &request.workspace_path,
            &request.arguments,
            request.permission_decision.as_ref(),
        ),
        _ => Err(ToolError::new(
            "tool.not_found",
            format!("unknown liuAgent local tool: {name}"),
        )),
    };

    match result {
        Ok((content, summary)) => ToolExecutionResult::ok(tool_call_id, name, content, summary),
        Err(error) => ToolExecutionResult::failed(tool_call_id, name, error),
    }
}

fn normalized_tool_call_id(value: Option<String>) -> String {
    let raw = value.unwrap_or_default();
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        "local_call".to_string()
    } else {
        trimmed.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn registers_first_batch_builtin_tools() {
        let tools = builtin_tool_definitions();
        assert_eq!(tools.len(), 14);
        assert!(tools.iter().any(|item| item.name == "read_file"));
        assert!(tools.iter().any(|item| item.name == "delete_file"));
        assert!(tools.iter().any(|item| item.name == "run_command"));
        assert!(tools.iter().any(|item| item.name == "call_mcp_tool"));
    }

    #[test]
    fn checks_command_risk_without_executing() {
        let dir = test_workspace("command_risk");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_cmd".to_string()),
            name: "check_command_risk".to_string(),
            arguments: json!({"cmd": "rm -rf /"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(result.ok);
        assert_eq!(result.content["risk"], "critical");
        assert_eq!(result.content["requires_approval"], true);
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn safe_run_command_executes_without_permission() {
        let dir = test_workspace("run_safe");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_run_safe".to_string()),
            name: "run_command".to_string(),
            arguments: json!({"cmd": "pwd", "timeout_ms": 5000}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.content["exit_code"], 0);
        assert_eq!(
            result.content["stdout"].as_str().unwrap().trim(),
            dir.canonicalize().unwrap().to_string_lossy()
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn medium_run_command_requires_permission() {
        let dir = test_workspace("run_permission");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_run".to_string()),
            name: "run_command".to_string(),
            arguments: json!({"cmd": "cargo check", "timeout_ms": 5000}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "permission.required");
        assert_eq!(
            result.content["permissionRequest"]["requestId"],
            "perm_call_run_command_run"
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn approved_run_command_executes() {
        let dir = test_workspace("run_approved");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_run_ok".to_string()),
            name: "run_command".to_string(),
            arguments: json!({"cmd": "printf local-agent", "timeout_ms": 5000}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: Some("perm_call_run_ok_command_run".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.content["exit_code"], 0);
        assert_eq!(result.content["stdout"], "local-agent");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn run_command_rejects_cwd_escape() {
        let dir = test_workspace("run_escape");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_run_escape".to_string()),
            name: "run_command".to_string(),
            arguments: json!({"cmd": "pwd", "cwd": "../"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert!(
            result.error_code == "workspace.out_of_scope"
                || result.error_code == "workspace.not_accessible"
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn run_command_times_out() {
        let dir = test_workspace("run_timeout");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_run_timeout".to_string()),
            name: "run_command".to_string(),
            arguments: json!({"cmd": "sleep 2", "timeout_ms": 1000}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: Some("perm_call_run_timeout_command_run".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "tool.timeout");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn http_get_rejects_sensitive_headers() {
        let dir = test_workspace("http_header");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_http_header".to_string()),
            name: "http_get".to_string(),
            arguments: json!({
                "url": "https://example.com",
                "headers": {"Authorization": "Bearer secret"}
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "tool.schema_invalid");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn http_get_rejects_non_http_url() {
        let dir = test_workspace("http_scheme");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_http_scheme".to_string()),
            name: "http_get".to_string(),
            arguments: json!({"url": "file:///tmp/secret.txt"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "tool.schema_invalid");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn http_post_requires_permission_before_network_write() {
        let dir = test_workspace("http_post_permission");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_http_post".to_string()),
            name: "http_post".to_string(),
            arguments: json!({
                "url": "https://example.com/api",
                "body": {"hello": "world"}
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "permission.required");
        assert_eq!(
            result.content["permissionRequest"]["requestId"],
            "perm_call_http_post_network_write"
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn download_file_requires_permission_before_writing() {
        let dir = test_workspace("download_permission");
        let target = dir.join("download.txt");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_download".to_string()),
            name: "download_file".to_string(),
            arguments: json!({
                "url": "https://example.com/file.txt",
                "dest_path": "download.txt"
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "permission.required");
        assert_eq!(
            result.content["permissionRequest"]["requestId"],
            "perm_call_download_network_read"
        );
        assert!(!target.exists());
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn download_file_rejects_workspace_escape() {
        let dir = test_workspace("download_escape");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_download_escape".to_string()),
            name: "download_file".to_string(),
            arguments: json!({
                "url": "https://example.com/file.txt",
                "dest_path": "../outside.txt"
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: None,
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "workspace.out_of_scope");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn mcp_tools_report_missing_adapter_config() {
        let dir = test_workspace("mcp_pending");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_mcp".to_string()),
            name: "list_mcp_tools".to_string(),
            arguments: json!({}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "mcp.adapter_missing");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn mcp_adapter_lists_tools_and_reads_resources() {
        let dir = test_workspace("mcp_adapter_read");
        write_fake_mcp_adapter(&dir);

        let tools = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_mcp_list".to_string()),
            name: "list_mcp_tools".to_string(),
            arguments: json!({"server": "fake"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });
        assert!(tools.ok, "{}", tools.error);
        assert_eq!(tools.content["tools"][0]["name"], "echo");

        let resource = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_mcp_read".to_string()),
            name: "read_mcp_resource".to_string(),
            arguments: json!({"server": "fake", "uri": "fixture://hello"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });
        assert!(resource.ok, "{}", resource.error);
        assert_eq!(resource.content["content"], "hello from mcp");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn mcp_tool_call_requires_permission_and_executes_after_approval() {
        let dir = test_workspace("mcp_adapter_call");
        write_fake_mcp_adapter(&dir);

        let pending = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_mcp_tool".to_string()),
            name: "call_mcp_tool".to_string(),
            arguments: json!({
                "server": "fake",
                "tool": "echo",
                "arguments": {"text": "hello"}
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });
        assert!(!pending.ok);
        assert_eq!(pending.error_code, "permission.required");
        assert_eq!(
            pending.content["permissionRequest"]["requestId"],
            "perm_call_mcp_tool_mcp_call"
        );

        let approved = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_mcp_tool".to_string()),
            name: "call_mcp_tool".to_string(),
            arguments: json!({
                "server": "fake",
                "tool": "echo",
                "arguments": {"text": "hello"}
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: Some("perm_call_mcp_tool_mcp_call".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });
        assert!(approved.ok, "{}", approved.error);
        assert_eq!(
            approved.content["result"]["content"][0]["text"],
            "tool called"
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn executes_local_read_file_tool() {
        let dir = test_workspace("read_file");
        std::fs::write(dir.join("README.md"), "# Hello\nSecond\n").expect("write");

        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_1".to_string()),
            name: "read_file".to_string(),
            arguments: json!({"path": "README.md", "line_count": 1}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(result.ok);
        assert_eq!(result.tool_call_id, "call_1");
        assert_eq!(result.content["content"], "# Hello");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn write_file_requires_permission_before_writing() {
        let dir = test_workspace("write_permission");
        let target = dir.join("created.txt");

        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_write".to_string()),
            name: "write_file".to_string(),
            arguments: json!({"path": "created.txt", "content": "hello"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "permission.required");
        assert_eq!(
            result.content["permissionRequest"]["requestId"],
            "perm_call_write_file_write"
        );
        assert!(!target.exists());
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn write_file_executes_after_approve_once() {
        let dir = test_workspace("write_approved");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_write_ok".to_string()),
            name: "write_file".to_string(),
            arguments: json!({"path": "created.txt", "content": "hello"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: Some("perm_call_write_ok_file_write".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(result.ok);
        assert_eq!(result.content["created"], true);
        assert_eq!(
            std::fs::read_to_string(dir.join("created.txt")).unwrap(),
            "hello"
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn delete_file_requires_permission_before_deleting() {
        let dir = test_workspace("delete_permission");
        let target = dir.join("reademe.md");
        std::fs::write(&target, "delete me").expect("write fixture");

        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_delete".to_string()),
            name: "delete_file".to_string(),
            arguments: json!({"path": "reademe.md"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "permission.required");
        assert_eq!(
            result.content["permissionRequest"]["requestId"],
            "perm_call_delete_file_delete"
        );
        assert_eq!(result.content["permissionRequest"]["action"], "file.delete");
        assert!(target.exists(), "file must not be deleted before approval");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn delete_file_executes_after_approve_once_and_verifies_absence() {
        let dir = test_workspace("delete_approved");
        let target = dir.join("reademe.md");
        std::fs::write(&target, "delete me").expect("write fixture");

        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_delete_ok".to_string()),
            name: "delete_file".to_string(),
            arguments: json!({"path": "reademe.md"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: Some("perm_call_delete_ok_file_delete".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.content["deleted"], true);
        assert_eq!(result.content["exists_after"], false);
        assert!(!target.exists(), "file must be truly deleted on disk");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn delete_file_rejects_workspace_escape() {
        let dir = test_workspace("delete_escape");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_delete_escape".to_string()),
            name: "delete_file".to_string(),
            arguments: json!({"path": "../outside.txt"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: None,
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(!result.ok);
        assert!(
            result.error_code == "workspace.out_of_scope"
                || result.error_code == "workspace.not_accessible"
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn rejects_workspace_escape() {
        let dir = test_workspace("escape");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_2".to_string()),
            name: "read_file".to_string(),
            arguments: json!({"path": "../outside.txt"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert!(
            result.error_code == "workspace.out_of_scope"
                || result.error_code == "workspace.not_accessible"
        );
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn write_file_rejects_external_session_approval_without_request_id() {
        let dir = test_workspace("write_session_without_request");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_write_session".to_string()),
            name: "write_file".to_string(),
            arguments: json!({"path": "session.txt", "content": "blocked"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: None,
                decision: "approve_session".to_string(),
                grant_scope: Some("session".to_string()),
                comment: None,
            }),
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "permission.required");
        assert!(!dir.join("session.txt").exists());
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn write_file_rejects_workspace_escape() {
        let dir = test_workspace("write_escape");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_write_escape".to_string()),
            name: "write_file".to_string(),
            arguments: json!({"path": "../outside.txt", "content": "bad"}),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: None,
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "workspace.out_of_scope");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn apply_patch_requires_permission_before_writing() {
        let dir = test_workspace("patch_permission");
        let target = dir.join("hello.txt");
        std::fs::write(&target, "hello\nold\n").expect("write fixture");

        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_patch".to_string()),
            name: "apply_patch".to_string(),
            arguments: json!({
                "summary": "update hello fixture",
                "patch": hello_patch()
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: None,
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "permission.required");
        assert_eq!(
            result.content["permissionRequest"]["requestId"],
            "perm_call_patch_file_write"
        );
        assert_eq!(std::fs::read_to_string(target).unwrap(), "hello\nold\n");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn apply_patch_executes_after_approve_once() {
        let dir = test_workspace("patch_approved");
        let target = dir.join("hello.txt");
        std::fs::write(&target, "hello\nold\n").expect("write fixture");

        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_patch_ok".to_string()),
            name: "apply_patch".to_string(),
            arguments: json!({
                "summary": "update hello fixture",
                "patch": hello_patch()
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: Some("perm_call_patch_ok_file_write".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.content["applied"], true);
        assert_eq!(result.content["changed_files"][0], "hello.txt");
        assert_eq!(std::fs::read_to_string(target).unwrap(), "hello\nnew\n");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn apply_patch_accepts_codex_update_file_format() {
        let dir = test_workspace("patch_codex_update");
        let target = dir.join("hello.txt");
        std::fs::write(&target, "hello\nold\n").expect("write fixture");

        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_patch_codex_ok".to_string()),
            name: "apply_patch".to_string(),
            arguments: json!({
                "summary": "update hello fixture using Codex patch",
                "patch": "*** Begin Patch\n*** Update File: hello.txt\n@@\n hello\n-old\n+new\n*** End Patch\n"
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: Some("perm_call_patch_codex_ok_file_write".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(result.content["applied"], true);
        assert_eq!(result.content["changed_files"][0], "hello.txt");
        assert_eq!(std::fs::read_to_string(target).unwrap(), "hello\nnew\n");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn apply_patch_accepts_codex_insert_only_hunk() {
        let dir = test_workspace("patch_codex_insert");
        let target = dir.join("hello.txt");
        std::fs::write(&target, "hello\n").expect("write fixture");

        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_patch_codex_insert_ok".to_string()),
            name: "apply_patch".to_string(),
            arguments: json!({
                "summary": "insert hello fixture line using Codex patch",
                "patch": "*** Begin Patch\n*** Update File: hello.txt\n@@\n hello\n+new\n*** End Patch\n"
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: Some("perm_call_patch_codex_insert_ok_file_write".to_string()),
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(result.ok, "{}", result.error);
        assert_eq!(std::fs::read_to_string(target).unwrap(), "hello\nnew\n");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn apply_patch_rejects_workspace_escape() {
        let dir = test_workspace("patch_escape");
        let patch = "diff --git a/../outside.txt b/../outside.txt\n--- a/../outside.txt\n+++ b/../outside.txt\n@@ -1 +1 @@\n-old\n+new\n";

        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_patch_escape".to_string()),
            name: "apply_patch".to_string(),
            arguments: json!({
                "summary": "escape workspace",
                "patch": patch
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: None,
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "workspace.out_of_scope");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn apply_patch_rejects_patch_without_changed_files() {
        let dir = test_workspace("patch_empty");
        let result = execute_tool(ToolExecutionRequest {
            tool_call_id: Some("call_patch_empty".to_string()),
            name: "apply_patch".to_string(),
            arguments: json!({
                "summary": "empty patch",
                "patch": "@@ -1 +1 @@\n-old\n+new\n"
            }),
            workspace_path: dir.to_string_lossy().to_string(),
            permission_decision: Some(types::PermissionDecisionInput {
                request_id: None,
                decision: "approve_once".to_string(),
                grant_scope: Some("once".to_string()),
                comment: None,
            }),
        });

        assert!(!result.ok);
        assert_eq!(result.error_code, "tool.schema_invalid");
        let _ = std::fs::remove_dir_all(dir);
    }

    fn hello_patch() -> &'static str {
        "diff --git a/hello.txt b/hello.txt\n--- a/hello.txt\n+++ b/hello.txt\n@@ -1,2 +1,2 @@\n hello\n-old\n+new\n"
    }

    fn write_fake_mcp_adapter(dir: &PathBuf) {
        let adapter_dir = dir.join(".ai-employee").join("mcp-adapter");
        std::fs::create_dir_all(&adapter_dir).expect("create mcp adapter dir");
        std::fs::write(
            adapter_dir.join("servers.json"),
            json!({
                "servers": {
                    "fake": {
                        "command": "/bin/sh",
                        "args": ["fake-mcp.sh"],
                        "cwd": ".ai-employee/mcp-adapter"
                    }
                }
            })
            .to_string(),
        )
        .expect("write mcp config");
        std::fs::write(
            adapter_dir.join("fake-mcp.sh"),
            r#"while IFS= read -r line; do
case "$line" in
  *'"method":"tools/list"'*) echo '{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"echo","description":"Echo test tool","inputSchema":{"type":"object"}}]}}' ;;
  *'"method":"resources/read"'*) echo '{"jsonrpc":"2.0","id":2,"result":{"contents":[{"uri":"fixture://hello","mimeType":"text/plain","text":"hello from mcp"}]}}' ;;
  *'"method":"tools/call"'*) echo '{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"tool called"}],"isError":false}}' ;;
esac
done
"#,
        )
        .expect("write fake mcp script");
    }

    fn test_workspace(label: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or(0);
        let path = std::env::temp_dir().join(format!("liuagent_core_{label}_{nonce}"));
        std::fs::create_dir_all(&path).expect("create test workspace");
        path
    }
}
