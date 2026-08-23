const LOCAL_FEATURES = Object.freeze({
  chat: true,
  tasks: true,
  workbench: true,
  projects: true,
  workLogs: true,
  supervision: true,
  mcpMonitor: true,
  voiceInput: true,
  voiceOutput: true,
  globalAssistant: true,
  connectors: true,
  ftpCredentials: true,
  changelog: true,
})

export function getLocalRuntimeConfig() {
  return { features: { ...LOCAL_FEATURES } }
}

export function isLocalRuntimeMode() {
  return true
}

export function isLocalFeatureEnabled() {
  return true
}

export function isLocalRuntimePathEnabled() {
  return true
}
