use std::fs;
use std::path::{Path, PathBuf};

use super::manifest::PluginManifest;

#[derive(Debug)]
pub enum PluginLoaderError {
    RootNotDirectory(PathBuf),
    ReadDirectory(String),
    ReadManifest { path: PathBuf, message: String },
    ParseManifest { path: PathBuf, message: String },
    InvalidManifest { path: PathBuf, message: String },
}

impl std::fmt::Display for PluginLoaderError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::RootNotDirectory(path) => write!(
                formatter,
                "plugin root is not a directory: {}",
                path.display()
            ),
            Self::ReadDirectory(message) => {
                write!(formatter, "failed to read plugin directory: {message}")
            }
            Self::ReadManifest { path, message } => write!(
                formatter,
                "failed to read plugin manifest {}: {message}",
                path.display()
            ),
            Self::ParseManifest { path, message } => write!(
                formatter,
                "failed to parse plugin manifest {}: {message}",
                path.display()
            ),
            Self::InvalidManifest { path, message } => write!(
                formatter,
                "invalid plugin manifest {}: {message}",
                path.display()
            ),
        }
    }
}

impl std::error::Error for PluginLoaderError {}

#[derive(Debug, Default)]
pub struct PluginLoader;

impl PluginLoader {
    pub fn new() -> Self {
        Self
    }

    pub fn load_manifest(path: impl AsRef<Path>) -> Result<PluginManifest, PluginLoaderError> {
        let manifest_path = path.as_ref().to_path_buf();
        let content = fs::read_to_string(&manifest_path).map_err(|error| {
            PluginLoaderError::ReadManifest {
                path: manifest_path.clone(),
                message: error.to_string(),
            }
        })?;
        let manifest: PluginManifest =
            serde_json::from_str(&content).map_err(|error| PluginLoaderError::ParseManifest {
                path: manifest_path.clone(),
                message: error.to_string(),
            })?;
        manifest
            .validate()
            .map_err(|error| PluginLoaderError::InvalidManifest {
                path: manifest_path,
                message: error.to_string(),
            })?;
        Ok(manifest)
    }

    pub fn discover_manifests(root: impl AsRef<Path>) -> Result<Vec<PathBuf>, PluginLoaderError> {
        let root = root.as_ref();
        if !root.is_dir() {
            return Err(PluginLoaderError::RootNotDirectory(root.to_path_buf()));
        }
        let entries = fs::read_dir(root)
            .map_err(|error| PluginLoaderError::ReadDirectory(error.to_string()))?;
        let mut manifests = Vec::new();
        for entry in entries {
            let entry =
                entry.map_err(|error| PluginLoaderError::ReadDirectory(error.to_string()))?;
            let path = entry.path();
            if path.is_dir() {
                let manifest_path = path.join("plugin.json");
                if manifest_path.is_file() {
                    manifests.push(manifest_path);
                }
            } else if path.file_name().and_then(|name| name.to_str()) == Some("plugin.json") {
                manifests.push(path);
            }
        }
        manifests.sort();
        Ok(manifests)
    }

    pub fn load_directory(
        root: impl AsRef<Path>,
    ) -> Result<Vec<PluginManifest>, PluginLoaderError> {
        Self::discover_manifests(root)?
            .into_iter()
            .map(Self::load_manifest)
            .collect()
    }
}
