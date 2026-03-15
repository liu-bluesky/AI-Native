const CHAT_SETTINGS_ROUTE_PREFIX = "/ai/chat/settings";

const SETTINGS_PANEL_TARGETS = [
  { panel: "chat", prefixes: ["/chat"] },
  { panel: "system-config", prefixes: ["/system/config"] },
  { panel: "providers", prefixes: ["/llm/providers"] },
  { panel: "projects", prefixes: ["/projects"] },
  { panel: "agent-templates", prefixes: ["/agent-templates"] },
  { panel: "employees", prefixes: ["/employees", "/feedback", "/memory", "/sync"] },
  { panel: "skills", prefixes: ["/skills", "/skill-resources"] },
  { panel: "rules", prefixes: ["/rules"] },
  { panel: "users", prefixes: ["/users"] },
  { panel: "roles", prefixes: ["/roles"] },
  { panel: "api-keys", prefixes: ["/usage/keys"] },
]

function normalizePath(path) {
  const value = String(path || "").trim()
  if (!value) return ""
  if (value.startsWith("/")) return value
  return `/${value}`
}

export function isChatSettingsRoutePath(path) {
  return normalizePath(path).startsWith(CHAT_SETTINGS_ROUTE_PREFIX)
}

export function stripChatSettingsPrefix(path) {
  const normalized = normalizePath(path)
  if (!isChatSettingsRoutePath(normalized)) return normalized
  const stripped = normalized.slice(CHAT_SETTINGS_ROUTE_PREFIX.length)
  return normalizePath(stripped || "/chat")
}

export function inferSettingsPanelFromPath(path) {
  const normalized = isChatSettingsRoutePath(path)
    ? stripChatSettingsPrefix(path)
    : normalizePath(path)
  for (const item of SETTINGS_PANEL_TARGETS) {
    if (item.prefixes.some((prefix) => normalized === prefix || normalized.startsWith(`${prefix}/`))) {
      return item.panel
    }
  }
  return "chat"
}

export function buildChatSettingsRoute(targetPath = "/chat") {
  const normalizedTarget = normalizePath(targetPath || "/chat")
  if (isChatSettingsRoutePath(normalizedTarget)) return normalizedTarget
  if (normalizedTarget === "/") return `${CHAT_SETTINGS_ROUTE_PREFIX}/chat`
  return `${CHAT_SETTINGS_ROUTE_PREFIX}${normalizedTarget}`
}

export function resolveSettingsAwarePath(currentPath, targetPath, fallbackPath = "") {
  const normalizedTarget = normalizePath(targetPath)
  if (!normalizedTarget) return normalizePath(fallbackPath) || "/"
  if (isChatSettingsRoutePath(currentPath)) {
    const panel = inferSettingsPanelFromPath(normalizedTarget)
    if (panel !== "chat") {
      return buildChatSettingsRoute(normalizedTarget)
    }
  }
  return normalizedTarget || normalizePath(fallbackPath) || "/"
}

export function resolveSettingsAwarePanelPath(currentPath, panelId, fallbackPath) {
  if (isChatSettingsRoutePath(currentPath)) {
    if (panelId === "chat") return buildChatSettingsRoute("/chat")
    const matched = SETTINGS_PANEL_TARGETS.find((item) => item.panel === String(panelId || "").trim())
    const defaultPrefix = matched?.prefixes?.[0] || normalizePath(fallbackPath) || "/chat"
    return buildChatSettingsRoute(defaultPrefix)
  }
  return normalizePath(fallbackPath) || "/"
}
