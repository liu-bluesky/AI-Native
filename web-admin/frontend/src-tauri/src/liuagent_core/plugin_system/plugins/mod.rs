//! 首批内置插件定义。

use super::{PluginRegistry, PluginRegistryError};

#[path = "builtin-command/mod.rs"]
mod builtin_command;
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
#[path = "builtin-plugin-system/mod.rs"]
mod builtin_plugin_system;

pub(crate) use builtin_command::configure_process_group;
pub use builtin_command::{
    builtin_command_tool_definitions, check_command_risk, classify_command_risk, process_tool,
    register_builtin_command, run_command, run_command_with_output_sink_and_cancel,
    wait_for_background_process_notification,
};
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
pub use builtin_plugin_system::{
    builtin_plugin_system_tool_definitions, configure_plugin, disable_plugin, enable_plugin,
    install_plugin_from_directory, list_installed_plugins, read_plugin_config,
    register_builtin_plugin_system,
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
    register_builtin_command(&mut registry)?;
    register_builtin_plugin_system(&mut registry)?;
    Ok(registry)
}

#[cfg(test)]
mod tests {
    use super::builtin_plugins_registry;

    #[test]
    fn registers_all_current_builtin_plugins() {
        let registry = builtin_plugins_registry().unwrap();
        let plugins: Vec<_> = registry.list_plugins().collect();

        assert_eq!(plugins.len(), 7);
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
        assert!(plugins
            .iter()
            .any(|plugin| plugin.manifest.id == "builtin-filesystem"));
        assert!(plugins
            .iter()
            .any(|plugin| plugin.manifest.id == "builtin-command"));
        assert!(plugins
            .iter()
            .any(|plugin| plugin.manifest.id == "builtin-plugin-system"));
    }
}
