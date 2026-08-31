use std::fs;
use std::path::{Component, Path, PathBuf};

use serde::Serialize;

use super::installation::enabled_installed_plugin_versions;
use super::manifest::{CapabilityKind, CapabilityManifest, PluginManifest};
use super::PluginInstallError;

const SKILLS_DIR: &str = "skills";
const SKILL_FILE_NAME: &str = "SKILL.md";
const MAX_SKILL_SIZE_BYTES: u64 = 512 * 1024;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginSkillSummary {
    pub plugin_id: String,
    pub plugin_version: String,
    pub skill_id: String,
    pub name: String,
    pub description: String,
    pub when_to_use: Vec<String>,
    pub required_tool_names: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct PluginSkillDocument {
    pub summary: PluginSkillSummary,
    pub content: String,
}

impl PluginSkillDocument {
    fn new(
        plugin_id: impl Into<String>,
        plugin_version: impl Into<String>,
        skill_id: impl Into<String>,
        name: impl Into<String>,
        description: impl Into<String>,
        when_to_use: Vec<String>,
        required_tool_names: Vec<String>,
        content: String,
    ) -> Self {
        Self {
            summary: PluginSkillSummary {
                plugin_id: plugin_id.into(),
                plugin_version: plugin_version.into(),
                skill_id: skill_id.into(),
                name: name.into(),
                description: description.into(),
                when_to_use,
                required_tool_names,
            },
            content,
        }
    }
}

pub fn available_plugin_skills(
    plugin_root: impl AsRef<Path>,
) -> Result<Vec<PluginSkillSummary>, PluginInstallError> {
    let mut documents = builtin_plugin_skill_documents();
    documents.extend(discover_installed_skill_documents(plugin_root)?);
    documents.sort_by(|left, right| {
        left.summary
            .plugin_id
            .cmp(&right.summary.plugin_id)
            .then(left.summary.skill_id.cmp(&right.summary.skill_id))
            .then(
                left.summary
                    .plugin_version
                    .cmp(&right.summary.plugin_version)
                    .reverse(),
            )
    });
    Ok(documents
        .into_iter()
        .map(|document| document.summary)
        .collect())
}

pub fn load_plugin_skill(
    plugin_root: impl AsRef<Path>,
    plugin_id: &str,
    skill_id: &str,
) -> Result<PluginSkillDocument, PluginInstallError> {
    let plugin_id = normalized_identifier(plugin_id, "plugin_id")?;
    let skill_id = normalized_identifier(skill_id, "skill_id")?;

    if let Some(document) = builtin_plugin_skill_documents()
        .into_iter()
        .find(|document| {
            document.summary.plugin_id == plugin_id
                && document.summary.skill_id == skill_id
        })
    {
        return Ok(document);
    }

    let documents = discover_installed_skill_documents(plugin_root)?;
    documents
        .into_iter()
        .find(|document| {
            document.summary.plugin_id == plugin_id
                && document.summary.skill_id == skill_id
        })
        .ok_or_else(|| {
            PluginInstallError::InvalidSource(format!(
                "plugin skill was not found in active plugin: {plugin_id}/{skill_id}"
            ))
        })
}

pub fn discover_installed_skill_documents(
    plugin_root: impl AsRef<Path>,
) -> Result<Vec<PluginSkillDocument>, PluginInstallError> {
    let mut documents = Vec::new();
    for (version_directory, manifest) in enabled_installed_plugin_versions(plugin_root)? {
        documents.extend(discover_plugin_skill_documents(
            &version_directory,
            &manifest,
        )?);
    }
    Ok(documents)
}

fn discover_plugin_skill_documents(
    plugin_directory: &Path,
    manifest: &PluginManifest,
) -> Result<Vec<PluginSkillDocument>, PluginInstallError> {
    let skills_root = plugin_directory.join(SKILLS_DIR);
    if !skills_root.is_dir() {
        return Ok(Vec::new());
    }
    if fs::symlink_metadata(&skills_root)?.file_type().is_symlink() {
        return Err(PluginInstallError::InvalidSource(format!(
            "symlink is not allowed in plugin skills: {}",
            skills_root.display()
        )));
    }

    let mut files = Vec::new();
    collect_skill_files(&skills_root, &mut files)?;
    files.sort();

    files
        .into_iter()
        .map(|path| {
            let content = read_skill_content(&path)?;
            let relative_path = path
                .strip_prefix(plugin_directory)
                .map_err(|error| PluginInstallError::InvalidSource(error.to_string()))?;
            let capability = manifest
                .capabilities
                .iter()
                .filter(|capability| capability.kind == CapabilityKind::Skill)
                .find(|capability| capability_skill_path(capability) == Some(relative_path));
            let relative_parent = relative_path
                .parent()
                .filter(|parent| !parent.as_os_str().is_empty())
                .unwrap_or_else(|| Path::new(SKILLS_DIR));
            let relative_skill_components = relative_parent
                .iter()
                .filter_map(|component| component.to_str())
                .skip(1)
                .map(sanitize_skill_component)
                .collect::<Vec<_>>();
            let fallback_id = format!(
                "{}.{}",
                manifest.id,
                if relative_skill_components.is_empty() {
                    "default".to_string()
                } else {
                    relative_skill_components.join(".")
                }
            );
            let heading = markdown_heading(&content);
            let skill_id = capability
                .map(|capability| capability.id.clone())
                .unwrap_or(fallback_id);
            let name = capability
                .map(|capability| capability.name.clone())
                .filter(|name| !name.trim().is_empty())
                .or_else(|| heading.clone())
                .unwrap_or_else(|| skill_id.clone());
            let description = capability
                .map(|capability| capability.description.clone())
                .filter(|description| !description.trim().is_empty())
                .unwrap_or_else(|| markdown_description(&content, heading.as_deref()));
            let when_to_use = capability
                .and_then(|capability| capability.selection.as_ref())
                .map(|selection| selection.when_to_use.clone())
                .unwrap_or_default();
            let required_tool_names = capability
                .map(|capability| required_tool_names(manifest, capability))
                .unwrap_or_default();

            Ok(PluginSkillDocument::new(
                manifest.id.clone(),
                manifest.version.clone(),
                skill_id,
                name,
                description,
                when_to_use,
                required_tool_names,
                content,
            ))
        })
        .collect()
}

fn required_tool_names(
    manifest: &PluginManifest,
    skill_capability: &CapabilityManifest,
) -> Vec<String> {
    let Some(selection) = skill_capability.selection.as_ref() else {
        return Vec::new();
    };
    let mut tool_names = selection
        .recommends
        .iter()
        .filter_map(|capability_id| {
            manifest
                .capabilities
                .iter()
                .find(|capability| {
                    capability.id == *capability_id && capability.kind == CapabilityKind::Tool
                })
                .map(|capability| capability.name.trim().to_string())
        })
        .filter(|name| !name.is_empty())
        .collect::<Vec<_>>();
    tool_names.sort();
    tool_names.dedup();
    tool_names
}

fn capability_skill_path(capability: &CapabilityManifest) -> Option<&Path> {
    let path = capability.metadata.as_ref()?.get("skillFile")?.as_str()?;
    let path = Path::new(path);
    is_safe_relative_path(path).then_some(path)
}

fn collect_skill_files(root: &Path, files: &mut Vec<PathBuf>) -> Result<(), PluginInstallError> {
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() {
            return Err(PluginInstallError::InvalidSource(format!(
                "symlink is not allowed in plugin skills: {}",
                path.display()
            )));
        }
        if metadata.is_dir() {
            collect_skill_files(&path, files)?;
        } else if metadata.is_file()
            && path.file_name().and_then(|name| name.to_str()) == Some(SKILL_FILE_NAME)
        {
            files.push(path);
        }
    }
    Ok(())
}

fn read_skill_content(path: &Path) -> Result<String, PluginInstallError> {
    let metadata = fs::metadata(path)?;
    if metadata.len() > MAX_SKILL_SIZE_BYTES {
        return Err(PluginInstallError::InvalidSource(format!(
            "skill file is too large: {}",
            path.display()
        )));
    }
    Ok(fs::read_to_string(path)?)
}

fn normalized_identifier(value: &str, field: &str) -> Result<String, PluginInstallError> {
    let value = value.trim();
    if value.is_empty() || value.contains('/') || value.contains('\\') || value.contains("..") {
        return Err(PluginInstallError::InvalidSource(format!(
            "{field} must be a non-empty identifier"
        )));
    }
    Ok(value.to_string())
}

fn is_safe_relative_path(path: &Path) -> bool {
    !path.is_absolute()
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn sanitize_skill_component(value: &str) -> String {
    value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '-' || character == '_' {
                character
            } else {
                '-'
            }
        })
        .collect()
}

fn markdown_heading(content: &str) -> Option<String> {
    content
        .lines()
        .map(str::trim)
        .find_map(|line| line.strip_prefix("# ").map(str::trim))
        .filter(|heading| !heading.is_empty())
        .map(str::to_string)
}

fn markdown_description(content: &str, heading: Option<&str>) -> String {
    content
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .find(|line| Some(*line) != heading)
        .unwrap_or("插件 Skill")
        .to_string()
}

fn builtin_plugin_skill_documents() -> Vec<PluginSkillDocument> {
    vec![
        PluginSkillDocument::new(
            "builtin-media-image",
            "1.0.0",
            "builtin.media.image.generation-skill",
            "builtin-image-generation",
            "指导 AI 判断图片生成请求、整理提示词并调用 generate_image。",
            vec!["用户要求生成新的图片或视觉素材".to_string()],
            vec!["generate_image".to_string()],
            include_str!("plugins/builtin-media-image/skills/image-generation/SKILL.md")
                .to_string(),
        ),
        PluginSkillDocument::new(
            "builtin-media-image",
            "1.0.0",
            "builtin.media.image.editing-skill",
            "builtin-image-editing",
            "指导 AI 判断图片编辑请求、校验资产 ID 并调用 edit_image。",
            vec!["用户要求修改当前会话中的已有图片".to_string()],
            vec!["edit_image".to_string()],
            include_str!("plugins/builtin-media-image/skills/image-editing/SKILL.md").to_string(),
        ),
        PluginSkillDocument::new(
            "builtin-plugin-system",
            "1.0.0",
            "builtin.plugin.system.management-skill",
            "plugin-management",
            "指导 AI 动态组合插件发现、安装、配置、启停和 Skill 加载能力。",
            vec![
                "用户要求安装、配置、启用、禁用或查看本机插件".to_string(),
                "需要判断插件 Skill 是否可用".to_string(),
            ],
            Vec::new(),
            include_str!("plugins/builtin-plugin-system/skills/plugin-management/SKILL.md")
                .to_string(),
        ),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn discovers_installed_skill_and_matches_manifest_capability() {
        let root = temp_root("discover");
        let plugin = root.join("installed/vendor-demo/1.0.0");
        fs::create_dir_all(plugin.join("skills/demo")).unwrap();
        fs::write(
            plugin.join("plugin.json"),
            r#"{
                "id":"vendor-demo",
                "pluginType":"skill",
                "name":"demo",
                "displayName":"Demo",
                "description":"Demo plugin",
                "version":"1.0.0",
                "source":"user",
                "capabilities":[{
                    "id":"vendor.demo.skill",
                    "kind":"skill",
                    "name":"Demo Skill",
                    "description":"Use the demo skill.",
                    "selection":{"whenToUse":["demo task"]},
                    "metadata":{"skillFile":"skills/demo/SKILL.md"}
                }]
            }"#,
        )
        .unwrap();
        fs::write(
            plugin.join("skills/demo/SKILL.md"),
            "# Demo Skill\n\nDo the demo task.",
        )
        .unwrap();

        let documents = discover_installed_skill_documents(&root).unwrap();
        assert_eq!(documents.len(), 1);
        assert_eq!(documents[0].summary.skill_id, "vendor.demo.skill");
        assert_eq!(documents[0].summary.when_to_use, vec!["demo task"]);
        assert!(documents[0].summary.required_tool_names.is_empty());
        assert!(documents[0].content.contains("Do the demo task."));

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn resolves_recommended_tool_names_for_installed_skill() {
        let root = temp_root("skill-required-tools");
        let plugin = root.join("installed/vendor-demo/1.0.0");
        fs::create_dir_all(plugin.join("skills/demo")).unwrap();
        fs::write(
            plugin.join("plugin.json"),
            r#"{
                "id":"vendor-demo",
                "pluginType":"tool",
                "name":"demo",
                "displayName":"Demo",
                "description":"Demo plugin",
                "version":"1.0.0",
                "source":"user",
                "capabilities":[
                    {"id":"vendor.demo.run","kind":"tool","name":"run_demo","description":"Run demo."},
                    {"id":"vendor.demo.skill","kind":"skill","name":"Demo Skill","description":"Use the demo skill.","selection":{"recommends":["vendor.demo.run"]},"metadata":{"skillFile":"skills/demo/SKILL.md"}}
                ]
            }"#,
        )
        .unwrap();
        fs::write(plugin.join("skills/demo/SKILL.md"), "# Demo Skill").unwrap();

        let documents = discover_installed_skill_documents(&root).unwrap();

        assert_eq!(documents[0].summary.required_tool_names, vec!["run_demo"]);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rejects_skill_identifier_path_traversal() {
        let error =
            load_plugin_skill("/tmp/unused", "vendor-demo", "../secret").unwrap_err();
        assert!(error.to_string().contains("skill_id"));
    }

    #[test]
    fn resolves_builtin_skill_without_a_version_argument() {
        let document = load_plugin_skill(
            "/tmp/unused",
            "builtin-media-image",
            "builtin.media.image.editing-skill",
        )
        .unwrap();

        assert_eq!(document.summary.skill_id, "builtin.media.image.editing-skill");
    }

    #[test]
    fn keeps_skills_with_the_same_id_from_different_plugins() {
        let root = temp_root("duplicate-skill-id");
        for plugin_id in ["vendor-first", "vendor-second"] {
            let plugin = root.join("installed").join(plugin_id).join("1.0.0");
            fs::create_dir_all(plugin.join("skills/demo")).unwrap();
            fs::write(
                plugin.join("plugin.json"),
                format!(
                    r#"{{
                        "id":"{plugin_id}",
                        "pluginType":"skill",
                        "name":"demo",
                        "displayName":"Demo",
                        "description":"Demo plugin",
                        "version":"1.0.0",
                        "source":"user",
                        "capabilities":[{{
                            "id":"shared.skill",
                            "kind":"skill",
                            "name":"Demo Skill",
                            "description":"Use the demo skill.",
                            "metadata":{{"skillFile":"skills/demo/SKILL.md"}}
                        }}]
                    }}"#
                ),
            )
            .unwrap();
            fs::write(plugin.join("skills/demo/SKILL.md"), "# Demo Skill").unwrap();
        }

        let skills = available_plugin_skills(&root).unwrap();
        assert_eq!(
            skills
                .iter()
                .filter(|skill| skill.skill_id == "shared.skill")
                .count(),
            2
        );

        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn rejects_a_symlinked_skills_root() {
        let root = temp_root("symlink-root");
        let plugin = root.join("installed/vendor-demo/1.0.0");
        let external_skills = root.join("external-skills");
        fs::create_dir_all(&plugin).unwrap();
        fs::create_dir_all(&external_skills).unwrap();
        fs::write(
            plugin.join("plugin.json"),
            r#"{
                "id":"vendor-demo",
                "pluginType":"skill",
                "name":"demo",
                "displayName":"Demo",
                "description":"Demo plugin",
                "version":"1.0.0",
                "source":"user"
            }"#,
        )
        .unwrap();
        std::os::unix::fs::symlink(&external_skills, plugin.join("skills")).unwrap();

        let error = discover_installed_skill_documents(&root).unwrap_err();
        assert!(error.to_string().contains("symlink"));

        fs::remove_dir_all(root).unwrap();
    }

    fn temp_root(label: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("ai-employee-plugin-skills-{label}-{nonce}"))
    }
}
