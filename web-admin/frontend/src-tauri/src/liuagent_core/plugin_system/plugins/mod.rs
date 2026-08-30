//! 首批内置插件定义。

use super::{PluginRegistry, PluginRegistryError};

#[path = "builtin-filesystem/mod.rs"]
mod builtin_filesystem;
#[path = "builtin-media-audio/mod.rs"]
mod builtin_media_audio;
#[path = "builtin-media-image/mod.rs"]
mod builtin_media_image;
#[path = "builtin-media-transcription/mod.rs"]
mod builtin_media_transcription;
#[path = "builtin-media-video/mod.rs"]
mod builtin_media_video;

pub use builtin_filesystem::{
    apply_patch, builtin_filesystem_tool_definitions, delete_file, list_files,
    list_local_resources, read_file, read_local_resource, register_builtin_filesystem, search_text,
    write_file,
};
pub use builtin_media_audio::{
    builtin_media_audio_tool_definitions, execute_builtin_media_audio_tool,
    register_builtin_media_audio,
};
pub use builtin_media_image::{
    builtin_media_image_tool_definitions, execute_builtin_media_image_tool,
    register_builtin_media_image,
};
pub use builtin_media_transcription::{
    builtin_media_transcription_tool_definitions, execute_builtin_media_transcription_tool,
    register_builtin_media_transcription,
};
pub use builtin_media_video::{
    builtin_media_video_tool_definitions, execute_builtin_media_video_tool,
    register_builtin_media_video,
};

/// 创建并注册当前版本内置插件。
///
/// 后续新增内置插件时，只需要在这里追加注册步骤，Runtime 不需要感知具体插件模块。
pub fn builtin_plugins_registry() -> Result<PluginRegistry, PluginRegistryError> {
    let mut registry = PluginRegistry::new();
    register_builtin_media_image(&mut registry)?;
    register_builtin_media_video(&mut registry)?;
    register_builtin_media_audio(&mut registry)?;
    register_builtin_media_transcription(&mut registry)?;
    register_builtin_filesystem(&mut registry)?;
    Ok(registry)
}

#[cfg(test)]
mod tests {
    use super::builtin_plugins_registry;

    #[test]
    fn registers_all_current_builtin_plugins() {
        let registry = builtin_plugins_registry().unwrap();
        let plugins: Vec<_> = registry.list_plugins().collect();

        assert_eq!(plugins.len(), 5);
        assert!(plugins
            .iter()
            .any(|plugin| plugin.manifest.id == "builtin-media-image"));
        assert!(plugins
            .iter()
            .any(|plugin| plugin.manifest.id == "builtin-media-video"));
        assert!(plugins
            .iter()
            .any(|plugin| plugin.manifest.id == "builtin-media-audio"));
        assert!(plugins
            .iter()
            .any(|plugin| plugin.manifest.id == "builtin-media-transcription"));
    }
}
