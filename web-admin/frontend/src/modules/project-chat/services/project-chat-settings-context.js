let currentProjectChatSettingsContext = null;

export function setProjectChatSettingsContext(context) {
  currentProjectChatSettingsContext = context || null;
}

export function getProjectChatSettingsContext() {
  return currentProjectChatSettingsContext;
}
