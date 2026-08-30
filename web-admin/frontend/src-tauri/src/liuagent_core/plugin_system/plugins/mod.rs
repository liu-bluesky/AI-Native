//! 首批内置插件定义。

use super::{PluginRegistry, PluginRegistryError};

mod builtin_media_image;

pub use builtin_media_image::{
    builtin_media_image_manifest, builtin_media_image_tool_definitions,
    execute_builtin_media_image_tool, register_builtin_media_image,
};

/// 创建并注册当前版本内置插件。
///
/// 后续新增内置插件时，只需要在这里追加注册步骤，Runtime 不需要感知具体插件模块。
pub fn builtin_plugins_registry() -> Result<PluginRegistry, PluginRegistryError> {
    let mut registry = PluginRegistry::new();
    register_builtin_media_image(&mut registry)?;
    Ok(registry)
}

#[cfg(test)]
mod tests {
    use super::builtin_plugins_registry;

    #[test]
    fn registers_all_current_builtin_plugins() {
        let registry = builtin_plugins_registry().unwrap();
        let plugins: Vec<_> = registry.list_plugins().collect();

        assert_eq!(plugins.len(), 1);
        assert_eq!(plugins[0].manifest.id, "builtin-media-image");
    }
}
