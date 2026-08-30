//! 插件基础设施。
//!
//! 该模块只负责插件元数据、注册、加载、生命周期和能力解析，不接管现有工具执行器。

pub mod adapters;
mod context;
mod installation;
mod lifecycle;
mod loader;
mod manifest;
pub mod plugins;
mod registry;
mod resolver;

pub use context::{PluginContext, PluginContextBuilder};
pub use installation::{
    InstalledPlugin, PluginInstallError, PluginInstaller, PluginLockEntry, PluginLockFile,
};
pub use lifecycle::{LifecycleEvent, LifecycleState, PluginLifecycle};
pub use loader::{PluginLoader, PluginLoaderError};
pub use manifest::{
    CapabilityKind, CapabilityManifest, CapabilitySelection, ManifestValidationError,
    PluginDependency, PluginLifecycleManifest, PluginManifest, PluginPermissions, PluginSource,
    PluginType, PluginUiManifest, RiskLevel,
};
pub use registry::{
    PluginRecord, PluginRegistry, PluginRegistryError, PluginRegistrySnapshot,
    RegisteredCapabilitySnapshot,
};
pub use resolver::{CapabilityMatch, CapabilityQuery, CapabilityResolver};

pub use plugins::builtin_plugins_registry;
