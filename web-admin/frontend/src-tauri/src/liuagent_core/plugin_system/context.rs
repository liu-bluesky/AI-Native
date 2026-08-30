#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PluginContext {
    pub plugin_id: String,
    pub project_id: String,
    pub chat_session_id: String,
    pub workspace_path: String,
}

#[derive(Debug, Default)]
pub struct PluginContextBuilder {
    plugin_id: String,
    project_id: String,
    chat_session_id: String,
    workspace_path: String,
}

impl PluginContextBuilder {
    pub fn new(plugin_id: impl Into<String>) -> Self {
        Self {
            plugin_id: plugin_id.into(),
            ..Self::default()
        }
    }

    pub fn project_id(mut self, project_id: impl Into<String>) -> Self {
        self.project_id = project_id.into();
        self
    }

    pub fn chat_session_id(mut self, chat_session_id: impl Into<String>) -> Self {
        self.chat_session_id = chat_session_id.into();
        self
    }

    pub fn workspace_path(mut self, workspace_path: impl Into<String>) -> Self {
        self.workspace_path = workspace_path.into();
        self
    }

    pub fn build(self) -> Result<PluginContext, String> {
        let plugin_id = self.plugin_id.trim().to_string();
        if plugin_id.is_empty() {
            return Err("plugin context requires plugin_id".to_string());
        }
        Ok(PluginContext {
            plugin_id,
            project_id: self.project_id.trim().to_string(),
            chat_session_id: self.chat_session_id.trim().to_string(),
            workspace_path: self.workspace_path.trim().to_string(),
        })
    }
}
