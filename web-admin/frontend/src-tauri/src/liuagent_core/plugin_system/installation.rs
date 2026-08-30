use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use super::loader::{PluginLoader, PluginLoaderError};
use super::manifest::PluginManifest;
use super::registry::{PluginRegistry, PluginRegistryError};

const INSTALLED_DIR: &str = "installed";
const STAGING_DIR: &str = "staging";
const CACHE_DIR: &str = "cache";
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
        let plugin_root = plugin_root.as_ref();
        let destination = plugin_root
            .join(INSTALLED_DIR)
            .join(&manifest.id)
            .join(&manifest.version);
        if destination.exists() {
            return Err(PluginInstallError::DestinationExists(destination));
        }

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
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)?;
        }
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
        let installed_root = plugin_root.as_ref().join(INSTALLED_DIR);
        if !installed_root.is_dir() {
            return Ok(0);
        }
        let mut loaded = 0;
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
                let manifest_path = version_entry.path().join("plugin.json");
                if !manifest_path.is_file() {
                    continue;
                }
                let manifest = PluginLoader::load_manifest(&manifest_path)
                    .map_err(PluginInstallError::InvalidManifest)?;
                registry
                    .register(manifest)
                    .map_err(|error: PluginRegistryError| {
                        PluginInstallError::Registry(error.to_string())
                    })?;
                loaded += 1;
            }
        }
        Ok(loaded)
    }
}

fn update_lock_file(plugin_root: &Path, entry: PluginLockEntry) -> Result<(), PluginInstallError> {
    fs::create_dir_all(plugin_root.join(CACHE_DIR))?;
    let mut lock = PluginInstaller::read_lock_file(plugin_root)?;
    lock.plugins
        .retain(|item| !(item.id == entry.id && item.version == entry.version));
    lock.plugins.push(entry);
    lock.plugins.sort_by(|left, right| {
        left.id
            .cmp(&right.id)
            .then(left.version.cmp(&right.version))
    });
    let content = serde_json::to_string_pretty(&lock)
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
    fn installs_plugin_directory_and_records_versioned_path() {
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
}
