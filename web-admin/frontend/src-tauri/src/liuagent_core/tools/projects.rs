//! Local project catalog tools for the desktop runtime.
//!
//! Desktop chat reads the same global project catalog as the project list UI.
//! Feishu bot sessions keep using list_bot_projects / switch_project_workspace.

use serde_json::{json, Value};
use std::path::PathBuf;

use crate::liuagent_core::args::{number_arg, required_string_arg, string_arg};
use crate::liuagent_core::types::ToolError;
use crate::liuagent_core::{read_global_project_catalog, DesktopProjectCatalogEntry};

pub fn list_projects(arguments: &Value) -> Result<(Value, String), ToolError> {
    list_catalog_projects(arguments, project_catalog()?, 20)
}

pub fn list_bot_projects(arguments: &Value) -> Result<(Value, String), ToolError> {
    list_catalog_projects(arguments, project_catalog()?, 50)
}

fn list_catalog_projects(
    arguments: &Value,
    projects: Vec<DesktopProjectCatalogEntry>,
    default_page_size: i64,
) -> Result<(Value, String), ToolError> {
    let page = number_arg(arguments, "page", 1, 1, 10_000);
    let page_size = number_arg(arguments, "page_size", default_page_size, 1, 100);
    let name = string_arg(arguments, "name", "");
    let keyword = name.to_lowercase();
    let filtered = projects
        .iter()
        .filter(|project| {
            keyword.is_empty()
                || [
                    project.id.as_str(),
                    project.name.as_str(),
                    project.description.as_str(),
                ]
                .iter()
                .any(|value| value.to_lowercase().contains(keyword.as_str()))
        })
        .collect::<Vec<_>>();
    let total = filtered.len();
    let offset = ((page - 1) as usize).saturating_mul(page_size as usize);
    let items = filtered
        .into_iter()
        .skip(offset)
        .take(page_size as usize)
        .map(|project| {
            json!({
                "project_id": project.id,
                "name": project.name,
                "description": project.description,
                "workspace_path": project.workspace_path,
                "workspace_status": workspace_status(project.workspace_path.as_str()),
            })
        })
        .collect::<Vec<_>>();
    let count = items.len();

    Ok((
        json!({
            "page": page,
            "page_size": page_size,
            "name": name,
            "projects": items,
            "count": count,
            "total": total,
            "note": "项目列表来自桌面本机全局项目目录，与项目页面同源，不依赖后端登录或机器人连接器配置；workspace_status=ready 表示该工作区可切换。",
        }),
        format!("已读取桌面项目目录：本页 {count} 个，总计 {total} 个"),
    ))
}

pub fn switch_project_workspace(arguments: &Value) -> Result<(Value, String), ToolError> {
    switch_project_workspace_from_catalog(arguments, project_catalog()?)
}

fn switch_project_workspace_from_catalog(
    arguments: &Value,
    projects: Vec<DesktopProjectCatalogEntry>,
) -> Result<(Value, String), ToolError> {
    let requested_project_id = required_string_arg(arguments, "project_id")?;
    let project = projects
        .into_iter()
        .find(|item| item.id == requested_project_id)
        .ok_or_else(|| {
            ToolError::new(
                "projects.bot_project_not_found",
                "桌面全局项目目录中没有该 project_id",
            )
        })?;
    let workspace_path = resolve_workspace_path(project.workspace_path.as_str())?;
    let project_name = if project.name.is_empty() {
        requested_project_id.clone()
    } else {
        project.name
    };

    Ok((
        json!({
            "project_id": requested_project_id,
            "project_name": project_name,
            "workspace_path": workspace_path.to_string_lossy()
        }),
        format!(
            "已切换到项目工作区：{}",
            if project_name.is_empty() {
                requested_project_id.as_str()
            } else {
                project_name.as_str()
            }
        ),
    ))
}

pub fn get_project(arguments: &Value) -> Result<(Value, String), ToolError> {
    get_project_from_catalog(arguments, project_catalog()?)
}

fn get_project_from_catalog(
    arguments: &Value,
    projects: Vec<DesktopProjectCatalogEntry>,
) -> Result<(Value, String), ToolError> {
    let project_id = required_string_arg(arguments, "project_id")?;
    let project = projects
        .into_iter()
        .find(|item| item.id == project_id)
        .ok_or_else(|| {
            ToolError::new("projects.not_found", "桌面全局项目目录中没有该 project_id")
        })?;
    let workspace_status = workspace_status(project.workspace_path.as_str());
    let project_name = if project.name.is_empty() {
        project_id.clone()
    } else {
        project.name.clone()
    };

    Ok((
        json!({
            "project_id": project_id,
            "name": project_name,
            "description": project.description,
            "workspace_path": project.workspace_path,
            "workspace_status": workspace_status,
            "bound_agent_count": 0,
            "active_bound_agent_count": 0,
            "bound_agents": [],
            "agent_binding_note": "本机项目目录不保存项目绑定智能体；bound_agent_count 为 0 只表示目录里没有这份数据，不代表项目未绑定智能体。selected_employee_ids 为空表示当前对话自动分配。",
            "project": {
                "id": project.id,
                "name": project_name,
                "description": project.description,
                "workspace_path": project.workspace_path,
                "workspace_status": workspace_status,
            },
        }),
        format!("已读取本机项目详情：{project_name}"),
    ))
}

fn project_catalog() -> Result<Vec<DesktopProjectCatalogEntry>, ToolError> {
    read_global_project_catalog()
        .map(|catalog| catalog.projects)
        .map_err(|error| {
            ToolError::new(
                "projects.catalog_unavailable",
                format!("无法读取桌面全局项目目录：{error}"),
            )
        })
}

fn workspace_status(raw: &str) -> &'static str {
    if raw.is_empty() {
        return "not_configured";
    }
    let path = PathBuf::from(raw.trim());
    if !path.is_absolute() {
        return "invalid";
    }
    match path.canonicalize() {
        Ok(path) if path.is_dir() => "ready",
        Ok(_) => "not_directory",
        Err(_) => "unavailable",
    }
}

fn resolve_workspace_path(raw: &str) -> Result<PathBuf, ToolError> {
    let workspace_path = raw.trim();
    if workspace_path.is_empty() {
        return Err(ToolError::new(
            "projects.workspace_not_configured",
            "该机器人项目没有配置本机工作区，无法切换",
        ));
    }
    let path = PathBuf::from(workspace_path);
    if !path.is_absolute() {
        return Err(ToolError::new(
            "projects.workspace_invalid",
            "项目工作区必须是绝对路径",
        ));
    }
    let canonical = path.canonicalize().map_err(|err| {
        ToolError::new(
            "projects.workspace_unavailable",
            format!("项目工作区不可访问：{err}"),
        )
    })?;
    if !canonical.is_dir() {
        return Err(ToolError::new(
            "projects.workspace_not_directory",
            "项目工作区不是目录",
        ));
    }
    Ok(canonical)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_catalog(workspace: &std::path::Path) -> Vec<DesktopProjectCatalogEntry> {
        vec![
            DesktopProjectCatalogEntry {
                id: "proj-workspace-test".to_string(),
                name: "CRM".to_string(),
                description: "客户关系管理".to_string(),
                workspace_path: workspace.to_string_lossy().to_string(),
                deploy_settings: json!({}),
            },
            DesktopProjectCatalogEntry {
                id: "proj-no-workspace".to_string(),
                name: "营销云".to_string(),
                description: "未配置工作区".to_string(),
                workspace_path: String::new(),
                deploy_settings: json!({}),
            },
        ]
    }

    #[test]
    fn desktop_and_bot_project_lists_read_the_same_catalog() {
        let workspace = std::env::temp_dir().join(format!(
            "liuagent-list-projects-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&workspace).unwrap();
        let catalog = sample_catalog(&workspace);
        let arguments = json!({});
        let (projects, list_summary) =
            list_catalog_projects(&arguments, catalog.clone(), 20).unwrap();

        assert_eq!(projects["total"], 2);
        assert_eq!(projects["count"], 2);
        assert_eq!(projects["projects"][0]["project_id"], "proj-workspace-test");
        assert_eq!(projects["projects"][0]["name"], "CRM");
        assert_eq!(projects["projects"][0]["workspace_status"], "ready");
        assert_eq!(
            projects["projects"][0]["workspace_path"],
            workspace.to_string_lossy().as_ref()
        );
        assert_eq!(projects["projects"][1]["project_id"], "proj-no-workspace");
        assert_eq!(
            projects["projects"][1]["workspace_status"],
            "not_configured"
        );
        assert_eq!(projects["projects"][1]["workspace_path"], "");
        assert!(list_summary.contains("桌面项目目录"));
        assert!(projects["note"]
            .as_str()
            .unwrap()
            .contains("与项目页面同源"));

        let (filtered, _) =
            list_catalog_projects(&json!({ "name": "营销" }), catalog.clone(), 20).unwrap();
        assert_eq!(filtered["total"], 1);
        assert_eq!(filtered["projects"][0]["project_id"], "proj-no-workspace");

        let _ = std::fs::remove_dir_all(workspace);
    }

    #[test]
    fn get_project_reads_catalog_without_backend_context() {
        let workspace = std::env::temp_dir().join(format!(
            "liuagent-get-project-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&workspace).unwrap();
        let catalog = sample_catalog(&workspace);
        let (result, summary) = get_project_from_catalog(
            &json!({ "project_id": "proj-workspace-test" }),
            catalog.clone(),
        )
        .unwrap();

        assert_eq!(result["project_id"], "proj-workspace-test");
        assert_eq!(result["name"], "CRM");
        assert_eq!(result["description"], "客户关系管理");
        assert_eq!(result["workspace_status"], "ready");
        assert_eq!(result["bound_agent_count"], 0);
        assert_eq!(result["active_bound_agent_count"], 0);
        assert_eq!(result["bound_agents"], json!([]));
        assert!(result["agent_binding_note"]
            .as_str()
            .unwrap()
            .contains("本机项目目录不保存项目绑定智能体"));
        assert_eq!(summary, "已读取本机项目详情：CRM");

        let missing =
            get_project_from_catalog(&json!({ "project_id": "unknown" }), catalog).unwrap_err();
        assert_eq!(missing.code, "projects.not_found");
        let _ = std::fs::remove_dir_all(workspace);
    }

    #[test]
    fn bot_project_tools_use_desktop_project_catalog_without_backend_context() {
        let workspace = std::env::temp_dir().join(format!(
            "liuagent-switch-project-workspace-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&workspace).unwrap();
        let canonical_workspace = workspace.canonicalize().unwrap();
        let catalog = sample_catalog(&workspace);
        let arguments = json!({ "project_id": "proj-workspace-test" });
        let (projects, list_summary) =
            list_catalog_projects(&arguments, catalog.clone(), 50).unwrap();
        assert_eq!(projects["total"], 2);
        assert_eq!(projects["projects"][0]["project_id"], "proj-workspace-test");
        assert_eq!(projects["projects"][0]["workspace_status"], "ready");
        assert!(list_summary.contains("桌面项目目录"));

        let result = switch_project_workspace_from_catalog(&arguments, catalog.clone());
        let (result, summary) = result.unwrap();

        assert_eq!(result["project_id"], "proj-workspace-test");
        assert_eq!(result["project_name"], "CRM");
        assert_eq!(
            result["workspace_path"],
            canonical_workspace.to_string_lossy().as_ref()
        );
        assert!(result.get("project").is_none());
        assert_eq!(summary, "已切换到项目工作区：CRM");

        let missing =
            switch_project_workspace_from_catalog(&json!({ "project_id": "unknown" }), catalog)
                .unwrap_err();
        assert_eq!(missing.code, "projects.bot_project_not_found");
        let _ = std::fs::remove_dir_all(workspace);
    }
}
