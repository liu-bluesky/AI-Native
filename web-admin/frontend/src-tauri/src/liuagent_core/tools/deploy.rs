//! Project deploy tools.
//!
//! These tools let the desktop agent read deploy configuration and either
//! upload local artifacts to the artifact module or directly deploy workspace
//! files through backend atomic capabilities. Credentials are supplied by the
//! backend deploy settings, not by the model prompt.

use reqwest::blocking::{multipart, Client};
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION};
use reqwest::Url;
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use crate::liuagent_core::args::{bool_arg, number_arg, required_string_arg, string_arg};
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};
use crate::liuagent_core::workspace::{
    resolve_workspace_child, resolve_workspace_root, workspace_relative_path,
};

const MAX_UPLOAD_BYTES: u64 = 200 * 1024 * 1024;
const MAX_UPLOAD_FILES: usize = 20_000;

#[derive(Debug)]
struct UploadEntry {
    path: PathBuf,
    upload_path: String,
    original_path: String,
    name: String,
    size: u64,
}

#[derive(Debug)]
enum UploadSource {
    File {
        path: PathBuf,
        relative_path: String,
        size: u64,
    },
    Directory {
        entries: Vec<UploadEntry>,
        root_directory: String,
        display_path: String,
        total_size: u64,
    },
}

impl UploadSource {
    fn size(&self) -> u64 {
        match self {
            Self::File { size, .. } => *size,
            Self::Directory { total_size, .. } => *total_size,
        }
    }

    fn display_path(&self) -> &str {
        match self {
            Self::File { relative_path, .. } => relative_path,
            Self::Directory { display_path, .. } => display_path,
        }
    }

    fn file_count(&self) -> usize {
        match self {
            Self::File { .. } => 1,
            Self::Directory { entries, .. } => entries.len(),
        }
    }

    fn source_type(&self) -> &str {
        match self {
            Self::File { .. } => "file",
            Self::Directory { .. } => "directory",
        }
    }
}

pub fn get_project_deploy_options(arguments: &Value) -> Result<(Value, String), ToolError> {
    let api_base_url = string_arg(arguments, "_backend_api_base_url", "");
    let backend_token = string_arg(arguments, "_backend_token", "");
    if api_base_url.is_empty() || backend_token.is_empty() {
        return Err(ToolError::new(
            "deploy.backend_context_missing",
            "缺少后端连接上下文，不能读取项目部署配置",
        ));
    }
    let project_id = required_string_arg(arguments, "project_id")?;
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let endpoint = deploy_options_url(&api_base_url, &project_id)?;

    let mut headers = HeaderMap::new();
    let auth =
        HeaderValue::from_str(&format!("Bearer {}", backend_token.trim())).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid backend auth header: {err}"),
            )
        })?;
    headers.insert(AUTHORIZATION, auth);
    let client = Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create http client failed: {err}"),
            )
        })?;
    let response = client
        .get(endpoint.clone())
        .headers(headers)
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read deploy options failed: {err}"),
            )
        })?;
    let status = response.status().as_u16();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read deploy options response failed: {err}"),
        )
    })?;
    let body = serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({"raw": text}));
    if !(200..300).contains(&status) {
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "read deploy options failed with HTTP {status}: {}",
                safe_error_detail(&body)
            ),
        ));
    }

    let configured = body
        .get("configured")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let profile_count = body
        .get("profiles")
        .and_then(Value::as_array)
        .map(Vec::len)
        .unwrap_or(0);
    let summary = if configured {
        format!("已读取项目 {project_id} 的部署配置：{profile_count} 个环境档位")
    } else {
        format!("项目 {project_id} 未启用或未配置部署档位")
    };

    Ok((
        json!({
            "status": status,
            "project_id": project_id,
            "response": body,
        }),
        summary,
    ))
}

pub fn upload_deploy_artifact(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let api_base_url = string_arg(arguments, "_backend_api_base_url", "");
    let backend_token = string_arg(arguments, "_backend_token", "");
    if api_base_url.is_empty() || backend_token.is_empty() {
        return Err(ToolError::new(
            "deploy.backend_context_missing",
            "缺少后端连接上下文，不能从桌面端直连上传部署产物",
        ));
    }
    let project_id = required_string_arg(arguments, "project_id")?;
    let workspace_root = resolve_workspace_root(workspace_path)?;
    let upload_source = upload_source_arg(&workspace_root, arguments)?;
    if upload_source.size() == 0 {
        return Err(ToolError::new("tool.schema_invalid", "artifact is empty"));
    }
    if upload_source.size() > MAX_UPLOAD_BYTES {
        return Err(ToolError::new(
            "tool.output_too_large",
            format!("artifact is larger than {} bytes", MAX_UPLOAD_BYTES),
        ));
    }

    let profile = string_arg(arguments, "profile", "prod");
    let component = string_arg(arguments, "component", "");
    let artifact_name = string_arg(arguments, "artifact_name", "")
        .trim()
        .to_string();
    let artifact_name = if artifact_name.is_empty() {
        default_artifact_name(&upload_source)
    } else {
        Path::new(&artifact_name)
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("deploy-artifact")
            .to_string()
    };
    let artifact_kind = string_arg(arguments, "artifact_kind", "source-bundle");
    let version = string_arg(arguments, "version", "");
    let requirement = string_arg(arguments, "requirement", "");
    let plan = string_arg(arguments, "plan", "");
    let chat_session_id = string_arg(arguments, "chat_session_id", "");
    let task_tree_node_id = string_arg(arguments, "task_tree_node_id", "");
    let auto_deploy = bool_arg(arguments, "auto_deploy", false);
    let ai_deploy = bool_arg(arguments, "ai_deploy", true);
    let timeout_ms = number_arg(arguments, "timeout_ms", 120_000, 1_000, 600_000) as u64;
    let target_ids = target_ids_arg(arguments);
    let manifest = upload_manifest_arg(arguments, &upload_source)?;
    let relative_path = upload_source.display_path().to_string();

    require_approval(
        tool_call_id,
        "deploy.artifact.upload",
        if auto_deploy { "high" } else { "medium" },
        "network",
        &format!(
            "上传部署产物 {} 到项目 {}{}",
            relative_path,
            project_id,
            if auto_deploy {
                " 并触发服务端部署"
            } else {
                ""
            }
        ),
        json!({
            "project_id": project_id,
            "profile": profile,
            "component": component,
            "artifact_path": relative_path,
            "artifact_name": artifact_name,
            "artifact_kind": artifact_kind,
            "source_type": upload_source.source_type(),
            "file_count": upload_source.file_count(),
            "size": upload_source.size(),
            "auto_deploy": auto_deploy,
            "ai_deploy": ai_deploy,
            "target_ids": target_ids,
            "timeout_ms": timeout_ms,
        }),
        permission_decision,
    )?;

    let endpoint = deploy_upload_url(&api_base_url, &project_id)?;
    let form = multipart::Form::new()
        .text("profile", profile.clone())
        .text("component", component.clone())
        .text("artifact_name", artifact_name.clone())
        .text("artifact_kind", artifact_kind.clone())
        .text("version", version)
        .text("size", upload_source.size().to_string())
        .text(
            "target_ids_json",
            serde_json::to_string(&target_ids).unwrap_or_else(|_| "[]".to_string()),
        )
        .text(
            "manifest_json",
            serde_json::to_string(&manifest).unwrap_or_else(|_| "{}".to_string()),
        )
        .text("chat_session_id", chat_session_id)
        .text("task_tree_node_id", task_tree_node_id)
        .text("requirement", requirement)
        .text("plan", plan)
        .text(
            "auto_deploy",
            if auto_deploy { "true" } else { "false" }.to_string(),
        )
        .text(
            "ai_deploy",
            if ai_deploy { "true" } else { "false" }.to_string(),
        );
    let form = add_upload_parts(form, &upload_source, &artifact_name)?;

    let mut headers = HeaderMap::new();
    let auth =
        HeaderValue::from_str(&format!("Bearer {}", backend_token.trim())).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid backend auth header: {err}"),
            )
        })?;
    headers.insert(AUTHORIZATION, auth);
    let client = Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create http client failed: {err}"),
            )
        })?;
    let response = client
        .post(endpoint.clone())
        .headers(headers)
        .multipart(form)
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("deploy artifact upload failed: {err}"),
            )
        })?;
    let status = response.status().as_u16();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read upload response failed: {err}"),
        )
    })?;
    let body = serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({"raw": text}));
    if !(200..300).contains(&status) {
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "deploy artifact upload failed with HTTP {status}: {}",
                safe_error_detail(&body)
            ),
        ));
    }
    let artifact_id = body
        .get("artifact")
        .and_then(|artifact| artifact.get("id"))
        .and_then(Value::as_str)
        .unwrap_or("");
    let artifact_status = body.get("status").and_then(Value::as_str).unwrap_or("");
    let deployment = body.get("deployment").filter(|value| value.is_object());
    let deployment_status = deployment
        .and_then(|value| value.get("status"))
        .and_then(Value::as_str)
        .unwrap_or("");
    let deployment_id = deployment
        .and_then(|value| value.get("id"))
        .and_then(Value::as_str)
        .unwrap_or("");
    let deployment_confirmed_success = deployment_status == "success";
    let summary = deploy_upload_summary(
        artifact_id,
        artifact_status,
        auto_deploy,
        deployment_id,
        deployment_status,
    );
    Ok((
        json!({
            "status": status,
            "project_id": project_id,
            "profile": profile,
            "component": component,
            "artifact_path": relative_path,
            "artifact_name": artifact_name,
            "artifact_kind": artifact_kind,
            "source_type": upload_source.source_type(),
            "file_count": upload_source.file_count(),
            "size": upload_source.size(),
            "auto_deploy": auto_deploy,
            "artifact_status": artifact_status,
            "deployment_id": deployment_id,
            "deployment_status": deployment_status,
            "deployment_confirmed_success": deployment_confirmed_success,
            "deployment_claim_policy": if deployment_confirmed_success {
                "deployment_success_may_be_reported"
            } else {
                "artifact_uploaded_only_do_not_claim_deployment_success"
            },
            "response": body,
        }),
        summary,
    ))
}

pub fn deploy_workspace_files_to_target(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let api_base_url = string_arg(arguments, "_backend_api_base_url", "");
    let backend_token = string_arg(arguments, "_backend_token", "");
    if api_base_url.is_empty() || backend_token.is_empty() {
        return Err(ToolError::new(
            "deploy.backend_context_missing",
            "缺少后端连接上下文，不能从桌面端直连部署",
        ));
    }
    let project_id = required_string_arg(arguments, "project_id")?;
    let workspace_root = resolve_workspace_root(workspace_path)?;
    let upload_source = upload_source_arg(&workspace_root, arguments)?;
    if upload_source.size() == 0 {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "deploy source is empty",
        ));
    }
    if upload_source.size() > MAX_UPLOAD_BYTES {
        return Err(ToolError::new(
            "tool.output_too_large",
            format!("deploy source is larger than {} bytes", MAX_UPLOAD_BYTES),
        ));
    }

    let profile = string_arg(arguments, "profile", "prod");
    let component = string_arg(arguments, "component", "");
    let artifact_name = string_arg(arguments, "artifact_name", "")
        .trim()
        .to_string();
    let artifact_name = if artifact_name.is_empty() {
        default_artifact_name(&upload_source)
    } else {
        Path::new(&artifact_name)
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("deploy-source")
            .to_string()
    };
    let artifact_kind = string_arg(arguments, "artifact_kind", "source-bundle");
    let version = string_arg(arguments, "version", "");
    let requirement = string_arg(arguments, "requirement", "");
    let plan = string_arg(arguments, "plan", "");
    let chat_session_id = string_arg(arguments, "chat_session_id", "");
    let task_tree_node_id = string_arg(arguments, "task_tree_node_id", "");
    let target_ids = target_ids_arg(arguments);
    let timeout_ms = number_arg(arguments, "timeout_ms", 600_000, 1_000, 1_800_000) as u64;
    let run_deploy_command = bool_arg(arguments, "run_deploy_command", true);
    let manifest = upload_manifest_arg(arguments, &upload_source)?;
    let relative_path = upload_source.display_path().to_string();

    require_approval(
        tool_call_id,
        "deploy.direct.upload",
        "high",
        "network",
        &format!(
            "通过桌面智能体把 {} 直接部署到项目 {} 的已配置目标",
            relative_path, project_id
        ),
        json!({
            "project_id": project_id,
            "profile": profile,
            "component": component,
            "artifact_path": relative_path,
            "artifact_name": artifact_name,
            "artifact_kind": artifact_kind,
            "source_type": upload_source.source_type(),
            "file_count": upload_source.file_count(),
            "size": upload_source.size(),
            "target_ids": target_ids,
            "run_deploy_command": run_deploy_command,
            "timeout_ms": timeout_ms,
            "requirement": requirement,
            "plan": plan,
        }),
        permission_decision,
    )?;

    let endpoint = direct_deploy_url(&api_base_url, &project_id)?;
    let form = multipart::Form::new()
        .text("profile", profile.clone())
        .text("component", component.clone())
        .text("artifact_name", artifact_name.clone())
        .text("artifact_kind", artifact_kind.clone())
        .text("version", version)
        .text("size", upload_source.size().to_string())
        .text(
            "target_ids_json",
            serde_json::to_string(&target_ids).unwrap_or_else(|_| "[]".to_string()),
        )
        .text(
            "manifest_json",
            serde_json::to_string(&manifest).unwrap_or_else(|_| "{}".to_string()),
        )
        .text(
            "run_deploy_command",
            if run_deploy_command { "true" } else { "false" }.to_string(),
        )
        .text("chat_session_id", chat_session_id)
        .text("task_tree_node_id", task_tree_node_id)
        .text("requirement", requirement)
        .text("plan", plan);
    let form = add_upload_parts(form, &upload_source, &artifact_name)?;

    let mut headers = HeaderMap::new();
    let auth =
        HeaderValue::from_str(&format!("Bearer {}", backend_token.trim())).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid backend auth header: {err}"),
            )
        })?;
    headers.insert(AUTHORIZATION, auth);
    let client = Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create http client failed: {err}"),
            )
        })?;
    let response = client
        .post(endpoint)
        .headers(headers)
        .multipart(form)
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("direct deploy failed: {err}"),
            )
        })?;
    let status = response.status().as_u16();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read direct deploy response failed: {err}"),
        )
    })?;
    let body = serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({"raw": text}));
    if !(200..300).contains(&status) {
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "direct deploy failed with HTTP {status}: {}",
                safe_error_detail(&body)
            ),
        ));
    }

    let deployment_status = body.get("status").and_then(Value::as_str).unwrap_or("");
    let deployment_id = body.get("run_id").and_then(Value::as_str).unwrap_or("");
    let deployment_confirmed_success = body
        .get("deployment_confirmed_success")
        .and_then(Value::as_bool)
        .unwrap_or(deployment_status == "success");
    let summary = direct_deploy_summary(deployment_id, deployment_status, &relative_path);

    Ok((
        json!({
            "status": status,
            "project_id": project_id,
            "profile": profile,
            "component": component,
            "artifact_path": relative_path,
            "artifact_name": artifact_name,
            "artifact_kind": artifact_kind,
            "source_type": upload_source.source_type(),
            "file_count": upload_source.file_count(),
            "size": upload_source.size(),
            "deployment_id": deployment_id,
            "deployment_status": deployment_status,
            "deployment_confirmed_success": deployment_confirmed_success,
            "deployment_claim_policy": if deployment_confirmed_success {
                "deployment_success_may_be_reported"
            } else {
                "direct_deploy_not_success_do_not_claim_deployment_success"
            },
            "response": body,
        }),
        summary,
    ))
}

fn upload_source_arg(workspace_root: &Path, arguments: &Value) -> Result<UploadSource, ToolError> {
    let explicit_paths = string_list_arg(arguments, "artifact_paths");
    if !explicit_paths.is_empty() {
        return upload_source_from_paths(workspace_root, arguments, explicit_paths);
    }

    let artifact_path_arg = required_string_arg(arguments, "artifact_path")?;
    let artifact_path = resolve_workspace_child(workspace_root, &artifact_path_arg, true)?;
    if artifact_path.is_file() {
        let size = file_size(&artifact_path)?;
        if size == 0 {
            return Err(ToolError::new(
                "tool.schema_invalid",
                "artifact file is empty",
            ));
        }
        return Ok(UploadSource::File {
            relative_path: workspace_relative_path(workspace_root, &artifact_path),
            path: artifact_path,
            size,
        });
    }
    if artifact_path.is_dir() {
        let root_directory = workspace_relative_path(workspace_root, &artifact_path);
        let entries = collect_directory_entries(workspace_root, &artifact_path, &artifact_path)?;
        return directory_upload_source(entries, root_directory.clone(), root_directory);
    }
    Err(ToolError::new(
        "tool.schema_invalid",
        "artifact_path must point to a file or directory inside the workspace",
    ))
}

fn upload_source_from_paths(
    workspace_root: &Path,
    arguments: &Value,
    raw_paths: Vec<String>,
) -> Result<UploadSource, ToolError> {
    let root_arg = string_arg(arguments, "artifact_root", "");
    let relative_base = if root_arg.trim().is_empty() {
        workspace_root.to_path_buf()
    } else {
        let resolved = resolve_workspace_child(workspace_root, &root_arg, true)?;
        if !resolved.is_dir() {
            return Err(ToolError::new(
                "tool.schema_invalid",
                "artifact_root must point to a directory inside the workspace",
            ));
        }
        resolved
    };
    let root_directory = if root_arg.trim().is_empty() {
        ".".to_string()
    } else {
        workspace_relative_path(workspace_root, &relative_base)
    };
    let mut entries = Vec::new();
    for raw_path in raw_paths {
        let path = resolve_workspace_child(workspace_root, &raw_path, true)?;
        if !path.is_file() {
            return Err(ToolError::new(
                "tool.schema_invalid",
                format!("artifact_paths item must point to a file: {raw_path}"),
            ));
        }
        entries.push(upload_entry(workspace_root, &relative_base, &path)?);
    }
    directory_upload_source(entries, root_directory, "selected files".to_string())
}

fn directory_upload_source(
    entries: Vec<UploadEntry>,
    root_directory: String,
    display_path: String,
) -> Result<UploadSource, ToolError> {
    if entries.is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "artifact directory does not contain files",
        ));
    }
    if entries.len() > MAX_UPLOAD_FILES {
        return Err(ToolError::new(
            "tool.output_too_large",
            format!("too many artifact files; maximum is {MAX_UPLOAD_FILES}"),
        ));
    }
    let total_size = entries.iter().map(|entry| entry.size).sum::<u64>();
    Ok(UploadSource::Directory {
        entries,
        root_directory,
        display_path,
        total_size,
    })
}

fn collect_directory_entries(
    workspace_root: &Path,
    relative_base: &Path,
    directory: &Path,
) -> Result<Vec<UploadEntry>, ToolError> {
    let mut children = fs::read_dir(directory)
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read artifact directory failed: {err}"),
            )
        })?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read artifact directory entry failed: {err}"),
            )
        })?;
    children.sort_by_key(|entry| entry.path());
    let mut entries = Vec::new();
    for child in children {
        let file_type = child.file_type().map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read artifact file type failed: {err}"),
            )
        })?;
        if file_type.is_symlink() {
            return Err(ToolError::new(
                "workspace.out_of_scope",
                "artifact directory contains symlink; symlinks are not allowed",
            ));
        }
        let child_path = child.path();
        if file_type.is_dir() {
            entries.extend(collect_directory_entries(
                workspace_root,
                relative_base,
                &child_path,
            )?);
        } else if file_type.is_file() {
            entries.push(upload_entry(workspace_root, relative_base, &child_path)?);
        }
    }
    Ok(entries)
}

fn upload_entry(
    workspace_root: &Path,
    relative_base: &Path,
    path: &Path,
) -> Result<UploadEntry, ToolError> {
    let resolved = path.canonicalize().map_err(|err| {
        ToolError::new(
            "workspace.not_accessible",
            format!("path is not accessible: {err}"),
        )
    })?;
    if !resolved.starts_with(workspace_root) || !resolved.starts_with(relative_base) {
        return Err(ToolError::new(
            "workspace.out_of_scope",
            "artifact file escapes workspace or artifact_root",
        ));
    }
    let size = file_size(&resolved)?;
    let upload_path = resolved
        .strip_prefix(relative_base)
        .map(|value| value.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| workspace_relative_path(workspace_root, &resolved));
    if upload_path.trim().is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "artifact file path is empty",
        ));
    }
    Ok(UploadEntry {
        name: resolved
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("artifact-file")
            .to_string(),
        original_path: workspace_relative_path(workspace_root, &resolved),
        path: resolved,
        upload_path,
        size,
    })
}

fn file_size(path: &Path) -> Result<u64, ToolError> {
    fs::metadata(path)
        .map(|metadata| metadata.len())
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read artifact metadata failed: {err}"),
            )
        })
}

fn default_artifact_name(source: &UploadSource) -> String {
    match source {
        UploadSource::File { path, .. } => path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("deploy-artifact")
            .to_string(),
        UploadSource::Directory {
            root_directory,
            display_path,
            ..
        } => Path::new(if root_directory == "." {
            display_path
        } else {
            root_directory
        })
        .file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.trim().is_empty() && *value != ".")
        .unwrap_or("deploy-artifact")
        .to_string(),
    }
}

fn upload_manifest_arg(arguments: &Value, source: &UploadSource) -> Result<Value, ToolError> {
    let mut manifest = manifest_arg(arguments)?;
    if let UploadSource::Directory {
        entries,
        root_directory,
        ..
    } = source
    {
        let manifest_object = manifest
            .as_object_mut()
            .ok_or_else(|| ToolError::new("tool.schema_invalid", "manifest must be an object"))?;
        manifest_object.insert("source_type".to_string(), json!("directory"));
        manifest_object.insert("root_directory".to_string(), json!(root_directory));
        manifest_object.insert(
            "file_entries".to_string(),
            Value::Array(
                entries
                    .iter()
                    .map(|entry| {
                        json!({
                            "path": entry.upload_path,
                            "original_path": entry.original_path,
                            "name": entry.name,
                            "size": entry.size,
                        })
                    })
                    .collect(),
            ),
        );
    }
    Ok(manifest)
}

fn add_upload_parts(
    mut form: multipart::Form,
    source: &UploadSource,
    artifact_name: &str,
) -> Result<multipart::Form, ToolError> {
    match source {
        UploadSource::File { path, .. } => {
            let file_part = multipart::Part::file(path).map_err(|err| {
                ToolError::new(
                    "tool.execution_failed",
                    format!("read artifact file failed: {err}"),
                )
            })?;
            Ok(form.part("file", file_part.file_name(artifact_name.to_string())))
        }
        UploadSource::Directory { entries, .. } => {
            for entry in entries {
                let content = fs::read(&entry.path).map_err(|err| {
                    ToolError::new(
                        "tool.execution_failed",
                        format!("read artifact file failed: {err}"),
                    )
                })?;
                form = form.part(
                    "files",
                    multipart::Part::bytes(content).file_name(entry.name.clone()),
                );
            }
            Ok(form)
        }
    }
}

fn deploy_upload_summary(
    artifact_id: &str,
    artifact_status: &str,
    auto_deploy: bool,
    deployment_id: &str,
    deployment_status: &str,
) -> String {
    let artifact_label = if artifact_id.trim().is_empty() {
        "部署产物".to_string()
    } else {
        format!("部署产物 {artifact_id}")
    };
    if deployment_status == "success" {
        let deployment_label = if deployment_id.trim().is_empty() {
            "deployment".to_string()
        } else {
            format!("deployment {deployment_id}")
        };
        return format!("{artifact_label} 已上传并部署成功，{deployment_label} 状态：success");
    }
    if !deployment_status.trim().is_empty() {
        return format!(
            "{artifact_label} 已上传，但部署未确认成功：artifact 状态={}，deployment 状态={}；不能宣称部署完成",
            artifact_status_label(artifact_status),
            deployment_status
        );
    }
    if auto_deploy {
        format!(
            "{artifact_label} 已上传，但没有返回部署执行记录：artifact 状态={}；当前只能视为产物就绪，不能宣称部署完成",
            artifact_status_label(artifact_status)
        )
    } else {
        format!(
            "{artifact_label} 已上传，未请求自动部署：artifact 状态={}；不能宣称部署完成",
            artifact_status_label(artifact_status)
        )
    }
}

fn direct_deploy_summary(
    deployment_id: &str,
    deployment_status: &str,
    source_path: &str,
) -> String {
    let source_label = if source_path.trim().is_empty() {
        "部署源".to_string()
    } else {
        format!("部署源 {source_path}")
    };
    if deployment_status == "success" {
        let deployment_label = if deployment_id.trim().is_empty() {
            "direct deployment".to_string()
        } else {
            format!("direct deployment {deployment_id}")
        };
        return format!(
            "{source_label} 已由桌面智能体直接部署并确认成功，{deployment_label} 状态：success"
        );
    }
    if !deployment_status.trim().is_empty() {
        return format!(
            "{source_label} 已由桌面智能体发起直连部署，但未确认成功：deployment 状态={}；不能宣称部署完成",
            deployment_status
        );
    }
    format!("{source_label} 已由桌面智能体发起直连部署，但没有返回部署执行记录；不能宣称部署完成")
}

fn artifact_status_label(value: &str) -> &str {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        "unknown"
    } else {
        trimmed
    }
}

fn deploy_options_url(api_base_url: &str, project_id: &str) -> Result<Url, ToolError> {
    let base = Url::parse(api_base_url.trim()).map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid api_base_url: {err}"),
        )
    })?;
    if !matches!(base.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "api_base_url must use http or https",
        ));
    }
    let clean_base = base.as_str().trim_end_matches('/').to_string();
    Url::parse(&format!(
        "{}/projects/{}/deploy-options",
        clean_base,
        url_path_escape(project_id)
    ))
    .map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid deploy options url: {err}"),
        )
    })
}

fn deploy_upload_url(api_base_url: &str, project_id: &str) -> Result<Url, ToolError> {
    let base = Url::parse(api_base_url.trim()).map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid api_base_url: {err}"),
        )
    })?;
    if !matches!(base.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "api_base_url must use http or https",
        ));
    }
    let clean_base = base.as_str().trim_end_matches('/').to_string();
    Url::parse(&format!(
        "{}/projects/{}/deploy-artifacts/upload",
        clean_base,
        url_path_escape(project_id)
    ))
    .map_err(|err| ToolError::new("tool.schema_invalid", format!("invalid upload url: {err}")))
}

fn direct_deploy_url(api_base_url: &str, project_id: &str) -> Result<Url, ToolError> {
    let base = Url::parse(api_base_url.trim()).map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid api_base_url: {err}"),
        )
    })?;
    if !matches!(base.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "api_base_url must use http or https",
        ));
    }
    let clean_base = base.as_str().trim_end_matches('/').to_string();
    Url::parse(&format!(
        "{}/projects/{}/deploy/direct-upload",
        clean_base,
        url_path_escape(project_id)
    ))
    .map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid direct deploy url: {err}"),
        )
    })
}

fn manifest_arg(arguments: &Value) -> Result<Value, ToolError> {
    match arguments.get("manifest") {
        None | Some(Value::Null) => Ok(json!({})),
        Some(Value::Object(_)) => Ok(arguments
            .get("manifest")
            .cloned()
            .unwrap_or_else(|| json!({}))),
        _ => Err(ToolError::new(
            "tool.schema_invalid",
            "manifest must be an object",
        )),
    }
}

fn target_ids_arg(arguments: &Value) -> Vec<String> {
    arguments
        .get("target_ids")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .take(50)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn string_list_arg(arguments: &Value, key: &str) -> Vec<String> {
    arguments
        .get(key)
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn safe_error_detail(body: &Value) -> String {
    body.get("detail")
        .or_else(|| body.get("message"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| body.as_str().unwrap_or("request failed"))
        .chars()
        .take(1000)
        .collect()
}

fn url_path_escape(value: &str) -> String {
    value
        .bytes()
        .flat_map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                vec![byte as char]
            }
            _ => format!("%{byte:02X}").chars().collect(),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deploy_upload_summary_distinguishes_ready_artifact_from_successful_deployment() {
        let summary = deploy_upload_summary("artifact-1", "ready", true, "", "");

        assert!(summary.contains("已上传"));
        assert!(summary.contains("没有返回部署执行记录"));
        assert!(summary.contains("不能宣称部署完成"));
        assert!(!summary.contains("部署成功"));
    }

    #[test]
    fn deploy_upload_summary_reports_success_only_for_successful_deployment() {
        let summary = deploy_upload_summary("artifact-1", "deployed", true, "deploy-1", "success");

        assert!(summary.contains("部署成功"));
        assert!(summary.contains("deployment deploy-1 状态：success"));
        assert!(!summary.contains("不能宣称部署完成"));
    }

    #[test]
    fn direct_deploy_url_targets_direct_upload_endpoint() {
        let url = direct_deploy_url("http://127.0.0.1:8000/api", "proj-1").unwrap();

        assert_eq!(
            url.as_str(),
            "http://127.0.0.1:8000/api/projects/proj-1/deploy/direct-upload"
        );
    }

    #[test]
    fn direct_deploy_summary_reports_success_only_for_success() {
        let blocked = direct_deploy_summary("direct-run-1", "blocked", "selected files");
        assert!(blocked.contains("未确认成功"));
        assert!(blocked.contains("不能宣称部署完成"));
        assert!(!blocked.contains("部署成功"));

        let success = direct_deploy_summary("direct-run-1", "success", "selected files");
        assert!(success.contains("直接部署并确认成功"));
        assert!(success.contains("direct deployment direct-run-1 状态：success"));
    }

    #[test]
    fn directory_artifact_path_builds_directory_upload_manifest() {
        let root =
            std::env::temp_dir().join(format!("liuagent_deploy_dir_test_{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("site/login")).unwrap();
        fs::write(root.join("site/index.html"), b"<h1>ok</h1>").unwrap();
        fs::write(root.join("site/login/index.html"), b"login").unwrap();
        let root = root.canonicalize().unwrap();

        let args = json!({"artifact_path": "site"});
        let source = upload_source_arg(&root, &args).unwrap();
        let manifest = upload_manifest_arg(&args, &source).unwrap();

        assert_eq!(source.source_type(), "directory");
        assert_eq!(source.file_count(), 2);
        assert_eq!(manifest["source_type"], "directory");
        assert_eq!(manifest["root_directory"], "site");
        let paths: Vec<String> = manifest["file_entries"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| item["path"].as_str().unwrap().to_string())
            .collect();
        assert_eq!(paths, vec!["index.html", "login/index.html"]);

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn artifact_paths_preserve_relative_paths_from_artifact_root() {
        let root =
            std::env::temp_dir().join(format!("liuagent_deploy_paths_test_{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("login")).unwrap();
        fs::write(root.join("login/index.html"), b"login").unwrap();
        fs::write(root.join("register.html"), b"register").unwrap();
        let root = root.canonicalize().unwrap();

        let args = json!({
            "artifact_paths": ["login/index.html", "register.html"],
            "artifact_root": "."
        });
        let source = upload_source_arg(&root, &args).unwrap();
        let manifest = upload_manifest_arg(&args, &source).unwrap();

        assert_eq!(source.source_type(), "directory");
        assert_eq!(manifest["source_type"], "directory");
        let paths: Vec<String> = manifest["file_entries"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| item["path"].as_str().unwrap().to_string())
            .collect();
        assert_eq!(paths, vec!["login/index.html", "register.html"]);

        let _ = fs::remove_dir_all(&root);
    }
}
