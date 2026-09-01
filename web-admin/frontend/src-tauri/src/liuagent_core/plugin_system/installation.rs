use std::cmp::Ordering;
use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use semver::Version;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::loader::{PluginLoader, PluginLoaderError};
use super::manifest::PluginManifest;
use super::registry::{PluginRegistry, PluginRegistryError};

const INSTALLED_DIR: &str = "installed";
const STAGING_DIR: &str = "staging";
const CACHE_DIR: &str = "cache";
const CONFIG_DIR: &str = "config";
const LOCK_FILE: &str = "plugin-lock.json";

#[derive(Debug)]
pub enum PluginInstallError {
    Io(String),
    InvalidSource(String),
    InvalidManifest(PluginLoaderError),
    DestinationExists(PathBuf),
    Registry(String),
}

impl std::fmt::Display for PluginInstallError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(message) => write!(formatter, "plugin install I/O error: {message}"),
            Self::InvalidSource(message) => write!(formatter, "invalid plugin source: {message}"),
            Self::InvalidManifest(error) => write!(formatter, "invalid plugin manifest: {error}"),
            Self::DestinationExists(path) => {
                write!(
                    formatter,
                    "plugin version is already installed: {}",
                    path.display()
                )
            }
            Self::Registry(message) => write!(formatter, "plugin registry error: {message}"),
        }
    }
}

impl std::error::Error for PluginInstallError {}

impl From<io::Error> for PluginInstallError {
    fn from(error: io::Error) -> Self {
        Self::Io(error.to_string())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginLockEntry {
    pub id: String,
    pub version: String,
    pub source: String,
    pub install_path: String,
    pub enabled: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginLockFile {
    #[serde(default)]
    pub plugins: Vec<PluginLockEntry>,
}

#[derive(Debug, Clone)]
pub struct InstalledPlugin {
    pub manifest: PluginManifest,
    pub path: PathBuf,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InstalledPluginRecord {
    pub manifest: PluginManifest,
    pub path: PathBuf,
    pub enabled: bool,
    pub configured: bool,
}

pub struct PluginInstaller;

impl PluginInstaller {
    pub fn install_directory(
        source_directory: impl AsRef<Path>,
        plugin_root: impl AsRef<Path>,
        source_label: impl Into<String>,
    ) -> Result<InstalledPlugin, PluginInstallError> {
        let source_directory = source_directory.as_ref();
        if !source_directory.is_dir() {
            return Err(PluginInstallError::InvalidSource(format!(
                "source is not a directory: {}",
                source_directory.display()
            )));
        }
        let manifest_path = source_directory.join("plugin.json");
        if !manifest_path.is_file() {
            return Err(PluginInstallError::InvalidSource(
                "plugin.json is required at package root".to_string(),
            ));
        }
        let manifest = PluginLoader::load_manifest(&manifest_path)
            .map_err(PluginInstallError::InvalidManifest)?;
        validate_install_component(&manifest.version, "plugin version")?;
        let plugin_root = plugin_root.as_ref();
        let plugin_directory = plugin_root.join(INSTALLED_DIR).join(&manifest.id);
        let destination = plugin_directory.join(&manifest.version);

        let staging = plugin_root.join(STAGING_DIR).join(format!(
            "{}-{}-{}",
            manifest.id,
            manifest.version,
            std::process::id()
        ));
        if staging.exists() {
            fs::remove_dir_all(&staging)?;
        }
        copy_directory_without_symlinks(source_directory, &staging)?;
        if plugin_directory.exists() {
            fs::remove_dir_all(&plugin_directory)?;
        }
        fs::create_dir_all(&plugin_directory)?;
        fs::rename(&staging, &destination)?;

        let entry = PluginLockEntry {
            id: manifest.id.clone(),
            version: manifest.version.clone(),
            source: source_label.into(),
            install_path: destination.to_string_lossy().to_string(),
            enabled: manifest.enabled,
        };
        update_lock_file(plugin_root, entry)?;
        Ok(InstalledPlugin {
            manifest,
            path: destination,
        })
    }

    pub fn read_lock_file(
        plugin_root: impl AsRef<Path>,
    ) -> Result<PluginLockFile, PluginInstallError> {
        let path = plugin_root.as_ref().join(LOCK_FILE);
        if !path.is_file() {
            return Ok(PluginLockFile::default());
        }
        let content = fs::read_to_string(path)?;
        serde_json::from_str(&content).map_err(|error| PluginInstallError::Io(error.to_string()))
    }

    pub fn load_installed_into_registry(
        plugin_root: impl AsRef<Path>,
        registry: &mut PluginRegistry,
    ) -> Result<usize, PluginInstallError> {
        let mut loaded = 0;
        for (_, manifest) in enabled_installed_plugin_versions(plugin_root)? {
            registry
                .register(manifest)
                .map_err(|error: PluginRegistryError| {
                    PluginInstallError::Registry(error.to_string())
                })?;
            loaded += 1;
        }
        Ok(loaded)
    }

    pub fn list_installed(
        plugin_root: impl AsRef<Path>,
    ) -> Result<Vec<InstalledPluginRecord>, PluginInstallError> {
        let plugin_root = plugin_root.as_ref();
        let mut records = active_installed_plugins(plugin_root)?
            .into_iter()
            .map(|(path, manifest, enabled)| InstalledPluginRecord {
                configured: config_path(plugin_root, &manifest.id).is_file(),
                manifest,
                path,
                enabled,
            })
            .collect::<Vec<_>>();
        records.sort_by(|left, right| {
            left.manifest
                .id
                .cmp(&right.manifest.id)
                .then(compare_versions(
                    &right.manifest.version,
                    &left.manifest.version,
                ))
        });
        Ok(records)
    }

    pub fn set_enabled(
        plugin_root: impl AsRef<Path>,
        plugin_id: &str,
        enabled: bool,
    ) -> Result<InstalledPluginRecord, PluginInstallError> {
        let plugin_root = plugin_root.as_ref();
        let (path, manifest, _) = find_active_installed_plugin(plugin_root, plugin_id)?;
        let mut lock = Self::read_lock_file(plugin_root)?;
        lock.plugins
            .retain(|entry| entry.id != manifest.id);
        lock.plugins.push(PluginLockEntry {
            id: manifest.id.clone(),
            version: manifest.version.clone(),
            source: "managed".to_string(),
            install_path: path.to_string_lossy().to_string(),
            enabled,
        });
        write_lock_file(plugin_root, &lock)?;
        Ok(InstalledPluginRecord {
            configured: config_path(plugin_root, &manifest.id).is_file(),
            manifest,
            path,
            enabled,
        })
    }

    pub fn read_config(
        plugin_root: impl AsRef<Path>,
        plugin_id: &str,
    ) -> Result<Option<Value>, PluginInstallError> {
        let plugin_root = plugin_root.as_ref();
        let (_, manifest, _) = find_active_installed_plugin(plugin_root, plugin_id)?;
        let path = config_path(plugin_root, &manifest.id);
        if !path.is_file() {
            let legacy_path = legacy_config_path(plugin_root, &manifest.id, &manifest.version);
            if !legacy_path.is_file() {
                return Ok(None);
            }
            let content = fs::read_to_string(legacy_path)?;
            return serde_json::from_str(&content)
                .map(Some)
                .map_err(|error| PluginInstallError::Io(error.to_string()));
        }
        let content = fs::read_to_string(path)?;
        serde_json::from_str(&content)
            .map(Some)
            .map_err(|error| PluginInstallError::Io(error.to_string()))
    }

    pub fn write_config(
        plugin_root: impl AsRef<Path>,
        plugin_id: &str,
        config: &Value,
    ) -> Result<(), PluginInstallError> {
        let plugin_root = plugin_root.as_ref();
        let (_, manifest, _) = find_active_installed_plugin(plugin_root, plugin_id)?;
        if !config.is_object() {
            return Err(PluginInstallError::InvalidSource(
                "plugin config must be a JSON object".to_string(),
            ));
        }
        let path = config_path(plugin_root, &manifest.id);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let content = serde_json::to_string_pretty(config)
            .map_err(|error| PluginInstallError::Io(error.to_string()))?;
        let temporary = path.with_extension("json.tmp");
        fs::write(&temporary, content)?;
        fs::rename(temporary, path)?;
        Ok(())
    }
}

pub(crate) fn enabled_installed_plugin_versions(
    plugin_root: impl AsRef<Path>,
) -> Result<Vec<(PathBuf, PluginManifest)>, PluginInstallError> {
    Ok(active_installed_plugins(plugin_root)?
        .into_iter()
        .filter(|(_, _, enabled)| *enabled)
        .map(|(path, manifest, _)| (path, manifest))
        .collect())
}

fn active_installed_plugins(
    plugin_root: impl AsRef<Path>,
) -> Result<Vec<(PathBuf, PluginManifest, bool)>, PluginInstallError> {
    let mut selected = BTreeMap::<String, (PathBuf, PluginManifest, bool)>::new();
    for (path, manifest, enabled) in all_installed_plugin_versions(&plugin_root)? {
        let should_replace = selected.get(&manifest.id).is_none_or(|(_, current, _)| {
            compare_versions(&manifest.version, &current.version) == Ordering::Greater
        });
        if should_replace {
            selected.insert(manifest.id.clone(), (path, manifest, enabled));
        }
    }
    Ok(selected.into_values().collect())
}

fn all_installed_plugin_versions(
    plugin_root: impl AsRef<Path>,
) -> Result<Vec<(PathBuf, PluginManifest, bool)>, PluginInstallError> {
    let plugin_root = plugin_root.as_ref();
    let installed_root = plugin_root.join(INSTALLED_DIR);
    if !installed_root.is_dir() {
        return Ok(Vec::new());
    }
    let lock = PluginInstaller::read_lock_file(plugin_root)?;
    let mut records = Vec::new();
    for plugin_entry in fs::read_dir(&installed_root)? {
        let plugin_entry = plugin_entry?;
        if !plugin_entry.file_type()?.is_dir() {
            continue;
        }
        for version_entry in fs::read_dir(plugin_entry.path())? {
            let version_entry = version_entry?;
            if !version_entry.file_type()?.is_dir() {
                continue;
            }
            let version_directory = version_entry.path();
            let manifest_path = version_directory.join("plugin.json");
            if !manifest_path.is_file() {
                continue;
            }
            let manifest = PluginLoader::load_manifest(&manifest_path)
                .map_err(PluginInstallError::InvalidManifest)?;
            let enabled = installed_version_enabled(&lock, &manifest, &version_directory);
            records.push((version_directory, manifest, enabled));
        }
    }
    Ok(records)
}

fn find_active_installed_plugin(
    plugin_root: &Path,
    plugin_id: &str,
) -> Result<(PathBuf, PluginManifest, bool), PluginInstallError> {
    validate_install_component(plugin_id, "plugin id")?;
    active_installed_plugins(plugin_root)?
        .into_iter()
        .find(|(_, manifest, _)| manifest.id == plugin_id)
        .ok_or_else(|| {
            PluginInstallError::InvalidSource(format!(
                "active installed plugin was not found: {plugin_id}"
            ))
        })
}

fn config_path(plugin_root: &Path, plugin_id: &str) -> PathBuf {
    plugin_root.join(CONFIG_DIR).join(format!("{plugin_id}.json"))
}

fn legacy_config_path(plugin_root: &Path, plugin_id: &str, plugin_version: &str) -> PathBuf {
    plugin_root
        .join(CONFIG_DIR)
        .join(plugin_id)
        .join(format!("{plugin_version}.json"))
}

fn validate_install_component(value: &str, field: &str) -> Result<(), PluginInstallError> {
    if value.trim().is_empty()
        || value.contains('/')
        || value.contains('\\')
        || value.contains("..")
    {
        return Err(PluginInstallError::InvalidSource(format!(
            "{field} must be a safe path component"
        )));
    }
    Ok(())
}

fn installed_version_enabled(
    lock: &PluginLockFile,
    manifest: &PluginManifest,
    version_directory: &Path,
) -> bool {
    lock.plugins
        .iter()
        .find(|entry| {
            entry.id == manifest.id
                && entry.version == manifest.version
                && Path::new(&entry.install_path) == version_directory
        })
        .map(|entry| entry.enabled)
        .unwrap_or(manifest.enabled)
}

fn compare_versions(left: &str, right: &str) -> Ordering {
    match (Version::parse(left), Version::parse(right)) {
        (Ok(left), Ok(right)) => left.cmp(&right),
        _ => left.cmp(right),
    }
}

fn update_lock_file(plugin_root: &Path, entry: PluginLockEntry) -> Result<(), PluginInstallError> {
    fs::create_dir_all(plugin_root.join(CACHE_DIR))?;
    let mut lock = PluginInstaller::read_lock_file(plugin_root)?;
    lock.plugins
        .retain(|item| item.id != entry.id);
    lock.plugins.push(entry);
    lock.plugins.sort_by(|left, right| {
        left.id
            .cmp(&right.id)
            .then(left.version.cmp(&right.version))
    });
    write_lock_file(plugin_root, &lock)
}

fn write_lock_file(plugin_root: &Path, lock: &PluginLockFile) -> Result<(), PluginInstallError> {
    let content = serde_json::to_string_pretty(lock)
        .map_err(|error| PluginInstallError::Io(error.to_string()))?;
    let temporary = plugin_root.join("plugin-lock.json.tmp");
    fs::write(&temporary, content)?;
    fs::rename(temporary, plugin_root.join(LOCK_FILE))?;
    Ok(())
}

fn copy_directory_without_symlinks(
    source: &Path,
    destination: &Path,
) -> Result<(), PluginInstallError> {
    let metadata = fs::symlink_metadata(source)?;
    if metadata.file_type().is_symlink() {
        return Err(PluginInstallError::InvalidSource(format!(
            "symlink is not allowed: {}",
            source.display()
        )));
    }
    fs::create_dir_all(destination)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let source_path = entry.path();
        let destination_path = destination.join(entry.file_name());
        let metadata = fs::symlink_metadata(&source_path)?;
        if metadata.file_type().is_symlink() {
            return Err(PluginInstallError::InvalidSource(format!(
                "symlink is not allowed: {}",
                source_path.display()
            )));
        }
        if metadata.is_dir() {
            copy_directory_without_symlinks(&source_path, &destination_path)?;
        } else if metadata.is_file() {
            fs::copy(&source_path, &destination_path)?;
        } else {
            return Err(PluginInstallError::InvalidSource(format!(
                "unsupported filesystem entry: {}",
                source_path.display()
            )));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_directory(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "ai-employee-plugin-{name}-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn installs_plugin_directory_and_records_active_path() {
        let source = temp_directory("source");
        let root = temp_directory("root");
        fs::create_dir_all(source.join("skills/demo")).unwrap();
        fs::write(
            source.join("plugin.json"),
            r#"{"id":"vendor.demo","pluginType":"skill","name":"demo","displayName":"Demo","description":"Demo plugin","version":"1.2.3","source":"user","enabled":true}"#,
        )
        .unwrap();
        fs::write(source.join("skills/demo/SKILL.md"), "# Demo").unwrap();

        let installed = PluginInstaller::install_directory(&source, &root, "local-test").unwrap();
        assert_eq!(installed.manifest.id, "vendor.demo");
        assert!(installed.path.join("skills/demo/SKILL.md").is_file());
        let lock = PluginInstaller::read_lock_file(&root).unwrap();
        assert_eq!(lock.plugins.len(), 1);
        assert_eq!(lock.plugins[0].version, "1.2.3");
        assert_eq!(lock.plugins[0].source, "local-test");
        let _ = fs::remove_dir_all(source);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn rejects_symlinks_in_plugin_package() {
        let source = temp_directory("symlink-source");
        let root = temp_directory("symlink-root");
        fs::create_dir_all(&source).unwrap();
        fs::write(
            source.join("plugin.json"),
            r#"{"id":"vendor.demo","pluginType":"skill","name":"demo","displayName":"Demo","description":"Demo plugin","version":"1.0.0","source":"user"}"#,
        )
        .unwrap();
        #[cfg(unix)]
        std::os::unix::fs::symlink(source.join("plugin.json"), source.join("link.json")).unwrap();
        #[cfg(windows)]
        std::os::windows::fs::symlink_file(source.join("plugin.json"), source.join("link.json"))
            .unwrap();

        let result = PluginInstaller::install_directory(&source, &root, "local-test");
        assert!(matches!(result, Err(PluginInstallError::InvalidSource(_))));
        let _ = fs::remove_dir_all(source);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn selects_only_the_highest_enabled_plugin_version() {
        let root = temp_directory("versions");
        for version in ["1.0.0", "1.10.0", "1.2.0"] {
            let plugin = root.join("installed/vendor-demo").join(version);
            fs::create_dir_all(&plugin).unwrap();
            fs::write(
                plugin.join("plugin.json"),
                format!(
                    r#"{{"id":"vendor-demo","pluginType":"skill","name":"demo","displayName":"Demo","description":"Demo plugin","version":"{version}","source":"user","enabled":true}}"#
                ),
            )
            .unwrap();
        }

        let selected = enabled_installed_plugin_versions(&root).unwrap();
        assert_eq!(selected.len(), 1);
        assert_eq!(selected[0].1.version, "1.10.0");

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn prefers_a_stable_release_over_its_prerelease() {
        let root = temp_directory("prerelease-versions");
        for version in ["1.0.0-alpha.1", "1.0.0"] {
            let plugin = root.join("installed/vendor-demo").join(version);
            fs::create_dir_all(&plugin).unwrap();
            fs::write(
                plugin.join("plugin.json"),
                format!(
                    r#"{{"id":"vendor-demo","pluginType":"skill","name":"demo","displayName":"Demo","description":"Demo plugin","version":"{version}","source":"user","enabled":true}}"#
                ),
            )
            .unwrap();
        }

        let selected = enabled_installed_plugin_versions(&root).unwrap();
        assert_eq!(selected.len(), 1);
        assert_eq!(selected[0].1.version, "1.0.0");

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn manages_plugin_enabled_state_and_active_config() {
        let source = temp_directory("managed-source");
        let root = temp_directory("managed-root");
        fs::create_dir_all(&source).unwrap();
        fs::write(
            source.join("plugin.json"),
            r#"{"id":"vendor.demo","pluginType":"skill","name":"demo","displayName":"Demo","description":"Demo plugin","version":"1.0.0","source":"user","enabled":true}"#,
        )
        .unwrap();

        let installed = PluginInstaller::install_directory(&source, &root, "local-test").unwrap();
        let disabled =
            PluginInstaller::set_enabled(&root, &installed.manifest.id, false).unwrap();
        assert!(!disabled.enabled);
        assert!(!enabled_installed_plugin_versions(&root)
            .unwrap()
            .iter()
            .any(|(_, manifest)| manifest.id == "vendor.demo"));

        PluginInstaller::write_config(
            &root,
            "vendor.demo",
            &serde_json::json!({"endpoint":"https://example.test","api_key":"secret"}),
        )
        .unwrap();
        assert_eq!(
            PluginInstaller::read_config(&root, "vendor.demo")
                .unwrap()
                .unwrap()["endpoint"],
            "https://example.test"
        );
        assert!(root.join("config/vendor.demo.json").is_file());

        let enabled =
            PluginInstaller::set_enabled(&root, &installed.manifest.id, true).unwrap();
        assert!(enabled.enabled);
        assert!(enabled_installed_plugin_versions(&root)
            .unwrap()
            .iter()
            .any(|(_, manifest)| manifest.id == "vendor.demo"));

        let _ = fs::remove_dir_all(source);
        let _ = fs::remove_dir_all(root);
    }
}
