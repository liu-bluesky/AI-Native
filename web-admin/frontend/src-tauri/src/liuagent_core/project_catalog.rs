//! Desktop-global project catalog used by bot project/workspace tools.
//!
//! The catalog is intentionally independent of browser localStorage, backend
//! login state, and individual bot connector configuration.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::PathBuf;

use super::paths::{desktop_runtime_root, ensure_desktop_runtime_migrated};

pub const PROJECT_CATALOG_VERSION: u32 = 1;
const MAX_PROJECT_CATALOG_ENTRIES: usize = 1_000;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopProjectCatalog {
    #[serde(default = "default_project_catalog_version")]
    pub version: u32,
    #[serde(default)]
    pub projects: Vec<DesktopProjectCatalogEntry>,
}

impl Default for DesktopProjectCatalog {
    fn default() -> Self {
        Self {
            version: PROJECT_CATALOG_VERSION,
            projects: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct DesktopProjectCatalogEntry {
    #[serde(default, alias = "project_id")]
    pub id: String,
    #[serde(default, alias = "project_name", alias = "projectName")]
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default, rename = "workspace_path", alias = "workspacePath")]
    pub workspace_path: String,
    #[serde(default, rename = "deploy_settings", alias = "deploySettings")]
    pub deploy_settings: Value,
}

pub fn global_project_catalog_path() -> Result<PathBuf, String> {
    let home = env::var_os("HOME")
        .map(PathBuf::from)
        .ok_or_else(|| "缺少 HOME，无法定位全局项目目录".to_string())?;
    ensure_desktop_runtime_migrated(&home)
        .map_err(|err| format!("迁移旧全局桌面 Runtime 数据失败：{err}"))?;
    Ok(desktop_runtime_root(&home)
        .join("projects")
        .join("catalog.json"))
}

pub fn read_global_project_catalog() -> Result<DesktopProjectCatalog, String> {
    let path = global_project_catalog_path()?;
    if !path.exists() {
        return Ok(DesktopProjectCatalog::default());
    }
    if !path.is_file() {
        return Err("全局项目目录路径不是文件".to_string());
    }
    let content =
        fs::read_to_string(&path).map_err(|err| format!("无法读取全局项目目录：{err}"))?;
    parse_project_catalog_content(&content)
}

pub fn write_global_project_catalog(
    catalog: DesktopProjectCatalog,
) -> Result<DesktopProjectCatalog, String> {
    let normalized = normalize_project_catalog(catalog)?;
    let path = global_project_catalog_path()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("无法创建全局项目目录：{err}"))?;
    }
    let content = serde_json::to_string_pretty(&normalized)
        .map_err(|err| format!("无法序列化全局项目目录：{err}"))?;
    fs::write(&path, format!("{content}\n"))
        .map_err(|err| format!("无法写入全局项目目录：{err}"))?;
    Ok(normalized)
}

pub fn parse_project_catalog_content(content: &str) -> Result<DesktopProjectCatalog, String> {
    let raw = content.trim();
    let catalog: DesktopProjectCatalog =
        serde_json::from_str(if raw.is_empty() || raw == "undefined" {
            "{}"
        } else {
            raw
        })
        .map_err(|err| format!("全局项目目录 JSON 解析失败：{err}"))?;
    normalize_project_catalog(catalog)
}

pub fn find_global_project_catalog_entry(
    project_id: &str,
) -> Result<Option<DesktopProjectCatalogEntry>, String> {
    let normalized_project_id = project_id.trim();
    if normalized_project_id.is_empty() {
        return Ok(None);
    }
    Ok(read_global_project_catalog()?
        .projects
        .into_iter()
        .find(|project| project.id == normalized_project_id))
}

fn default_project_catalog_version() -> u32 {
    PROJECT_CATALOG_VERSION
}

fn normalize_project_catalog(
    mut catalog: DesktopProjectCatalog,
) -> Result<DesktopProjectCatalog, String> {
    if catalog.projects.len() > MAX_PROJECT_CATALOG_ENTRIES {
        return Err(format!(
            "全局项目目录最多可包含 {MAX_PROJECT_CATALOG_ENTRIES} 个项目"
        ));
    }

    let mut project_ids = HashSet::with_capacity(catalog.projects.len());
    for (index, project) in catalog.projects.iter_mut().enumerate() {
        project.id = project.id.trim().to_string();
        project.name = project.name.trim().to_string();
        project.description = project.description.trim().to_string();
        project.workspace_path = project.workspace_path.trim().to_string();
        if !project.deploy_settings.is_object() {
            project.deploy_settings = json!({});
        }

        if project.id.is_empty() {
            return Err(format!("全局项目目录第 {} 条缺少项目 ID", index + 1));
        }
        if !project_ids.insert(project.id.clone()) {
            return Err(format!("全局项目目录存在重复项目 ID：{}", project.id));
        }
    }

    catalog.version = PROJECT_CATALOG_VERSION;
    Ok(catalog)
}

#[cfg(test)]
mod tests {
    use super::{parse_project_catalog_content, PROJECT_CATALOG_VERSION};
    use serde_json::json;

    #[test]
    fn parses_snake_case_workspace_paths() {
        let catalog = parse_project_catalog_content(
            r#"{
                "version": 9,
                "projects": [{
                    "id": "crm",
                    "project_name": "CRM",
                    "description": "客户关系管理",
                    "workspace_path": "/tmp/crm"
                }]
            }"#,
        )
        .unwrap();

        assert_eq!(catalog.version, PROJECT_CATALOG_VERSION);
        assert_eq!(catalog.projects.len(), 1);
        assert_eq!(catalog.projects[0].id, "crm");
        assert_eq!(catalog.projects[0].name, "CRM");
        assert_eq!(catalog.projects[0].workspace_path, "/tmp/crm");
        assert_eq!(catalog.projects[0].deploy_settings, json!({}));
    }

    #[test]
    fn parses_deploy_settings_from_catalog_entries() {
        let catalog = parse_project_catalog_content(
            r#"{
                "projects": [{
                    "id": "crm",
                    "name": "CRM",
                    "workspace_path": "/tmp/crm",
                    "deploy_settings": {
                        "enabled": true,
                        "default_profile": "prod",
                        "profiles": [{
                            "id": "prod",
                            "components": [{
                                "id": "app",
                                "targets": [{
                                    "id": "target-1",
                                    "ftp_credential_id": "ftp-1",
                                    "remote_path": "/www/site",
                                    "deploy_command": "./deploy.sh"
                                }]
                            }]
                        }]
                    }
                }]
            }"#,
        )
        .unwrap();

        assert_eq!(catalog.projects[0].deploy_settings["enabled"], true);
        assert_eq!(
            catalog.projects[0].deploy_settings["profiles"][0]["components"][0]["targets"][0]
                ["ftp_credential_id"],
            "ftp-1"
        );
        assert_eq!(
            catalog.projects[0].deploy_settings["profiles"][0]["components"][0]["targets"][0]
                ["remote_path"],
            "/www/site"
        );
    }

    #[test]
    fn serializes_deploy_settings_as_snake_case() {
        let catalog = parse_project_catalog_content(
            r#"{
                "projects": [{
                    "id": "crm",
                    "workspacePath": "/tmp/crm",
                    "deploySettings": {
                        "enabled": true,
                        "profiles": [{
                            "id": "prod",
                            "components": [{
                                "id": "app",
                                "targets": [{
                                    "ftp_credential_id": "ftp-1",
                                    "remote_path": "/www/site"
                                }]
                            }]
                        }]
                    }
                }]
            }"#,
        )
        .unwrap();
        let encoded = serde_json::to_value(&catalog).unwrap();

        assert!(encoded["projects"][0].get("deploy_settings").is_some());
        assert!(encoded["projects"][0].get("deploySettings").is_none());
        assert!(encoded["projects"][0].get("workspace_path").is_some());
        assert!(encoded["projects"][0].get("workspacePath").is_none());
        assert_eq!(encoded["projects"][0]["deploy_settings"]["enabled"], true);
        assert_eq!(
            encoded["projects"][0]["deploy_settings"]["profiles"][0]["components"][0]["targets"][0]
                ["ftp_credential_id"],
            "ftp-1"
        );
    }

    #[test]
    fn rejects_duplicate_project_ids() {
        let error = parse_project_catalog_content(
            r#"{
                "projects": [
                    {"id": "crm"},
                    {"id": "crm"}
                ]
            }"#,
        )
        .unwrap_err();

        assert!(error.contains("重复项目 ID"));
    }
}
