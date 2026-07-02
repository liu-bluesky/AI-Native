import { getStoredAuthProfile } from "@/utils/auth-storage.js";
import {
  hasNativeDesktopBridge,
  readNativeGlobalMcpConfigFile,
  readNativeProjectMcpConfigFile,
  writeNativeGlobalMcpConfigFile,
  writeNativeProjectMcpConfigFile,
} from "@/utils/native-desktop-bridge.js";
import {
  PLUGIN_INSTALL_DRAFT_STORAGE_PREFIX,
  PROJECT_DEPLOY_DRAFT_STORAGE_PREFIX,
  STATISTICS_ANALYSIS_DRAFT_STORAGE_PREFIX,
} from "@/modules/project-chat/constants/projectChatConstants.js";

const LOCAL_CONNECTOR_STORAGE_PREFIX = "project_chat.local_connector";
const GUIDE_TOUR_STORAGE_PREFIX = "project_chat.guide_tour";
const PROJECT_SELECTION_STORAGE_KEY = "project_id";
export const DEFAULT_LOCAL_MCP_CONFIG = {
  mcpServers: {
    "prompts.chat": {
      type: "http",
      url: "https://prompts.chat/api/mcp",
      enabled: true,
    },
  },
};

function chatSessionStorageKey(projectId) {
  const normalized = String(projectId || "").trim();
  return normalized ? `project_chat_session_${normalized}` : "";
}

function taskTreeSessionStorageKey(projectId) {
  const normalized = String(projectId || "").trim();
  return normalized ? `project_chat_task_tree_session_${normalized}` : "";
}

function workSessionStorageKey(projectId) {
  const normalized = String(projectId || "").trim();
  return normalized ? `project_chat_work_session_${normalized}` : "";
}

export function resolveCurrentUsername() {
  const profile = getStoredAuthProfile();
  return String(profile.username || "anonymous").trim() || "anonymous";
}

export function guideTourStorageKey(surface, username, roleId) {
  return [
    GUIDE_TOUR_STORAGE_PREFIX,
    String(surface || "").trim() || "chat",
    String(username || "").trim() || "anonymous",
    String(roleId || "").trim() || "user",
  ].join(".");
}

export function hasSeenGuideTour(surface, username, roleId) {
  if (typeof window === "undefined") return true;
  return (
    localStorage.getItem(guideTourStorageKey(surface, username, roleId)) === "1"
  );
}

export function markGuideTourSeen(surface, username, roleId) {
  if (typeof window === "undefined") return;
  localStorage.setItem(guideTourStorageKey(surface, username, roleId), "1");
}

export function readSelectedProjectId() {
  if (typeof window === "undefined") return "";
  return String(
    localStorage.getItem(PROJECT_SELECTION_STORAGE_KEY) || "",
  ).trim();
}

// 保持历史 project_id key 不变，只把浏览器存储副作用收敛到 service 层。
export function writeSelectedProjectId(projectId) {
  if (typeof window === "undefined") return;
  const normalized = String(projectId || "").trim();
  if (normalized) {
    localStorage.setItem(PROJECT_SELECTION_STORAGE_KEY, normalized);
    return;
  }
  localStorage.removeItem(PROJECT_SELECTION_STORAGE_KEY);
}

export function clearSelectedProjectId() {
  writeSelectedProjectId("");
}

function consumeJsonDraft(storageKey, expectedPrefix, normalizePayload) {
  const normalizedKey = String(storageKey || "").trim();
  if (!normalizedKey || !normalizedKey.startsWith(expectedPrefix)) {
    return null;
  }
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(normalizedKey);
    if (!raw) return null;
    // 草稿是从其它页面跳转过来的一次性载荷，读取后必须立刻清理，避免重复填充输入框。
    window.localStorage.removeItem(normalizedKey);
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return normalizePayload(parsed);
  } catch {
    try {
      window.localStorage.removeItem(normalizedKey);
    } catch {
      // ignore cleanup errors
    }
    return null;
  }
}

export function consumeStatisticsAnalysisDraft(storageKey) {
  return consumeJsonDraft(
    storageKey,
    STATISTICS_ANALYSIS_DRAFT_STORAGE_PREFIX,
    (parsed) => ({
      prompt: String(parsed.prompt || "").trim(),
      scope: String(parsed.scope || "").trim(),
      project_id: String(parsed.project_id || "").trim(),
      link: String(parsed.link || "").trim(),
    }),
  );
}

export function consumePluginInstallDraft(storageKey) {
  return consumeJsonDraft(
    storageKey,
    PLUGIN_INSTALL_DRAFT_STORAGE_PREFIX,
    (parsed) => ({
      prompt: String(parsed.prompt || "").trim(),
      source: String(parsed.source || "").trim(),
    }),
  );
}

export function createProjectDeployDraft(payload = {}) {
  if (typeof window === "undefined") return "";
  const storageKey = `${PROJECT_DEPLOY_DRAFT_STORAGE_PREFIX}${Date.now()}:${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem(
    storageKey,
    JSON.stringify({
      prompt: String(payload.prompt || "").trim(),
      project_id: String(payload.project_id || "").trim(),
      artifact_id: String(payload.artifact_id || "").trim(),
      source: "deploy_artifact_panel",
    }),
  );
  return storageKey;
}

export function consumeProjectDeployDraft(storageKey) {
  return consumeJsonDraft(
    storageKey,
    PROJECT_DEPLOY_DRAFT_STORAGE_PREFIX,
    (parsed) => ({
      prompt: String(parsed.prompt || "").trim(),
      project_id: String(parsed.project_id || "").trim(),
      artifact_id: String(parsed.artifact_id || "").trim(),
      source: String(parsed.source || "").trim(),
    }),
  );
}

function writeProjectSessionMemory(key, sessionId) {
  if (typeof window === "undefined" || !key) return;
  const normalized = String(sessionId || "").trim();
  if (normalized) {
    localStorage.setItem(key, normalized);
    return;
  }
  localStorage.removeItem(key);
}

function readProjectSessionMemory(key) {
  if (typeof window === "undefined" || !key) return "";
  return String(localStorage.getItem(key) || "").trim();
}

function clearProjectSessionMemory(key) {
  if (typeof window === "undefined" || !key) return;
  localStorage.removeItem(key);
}

// 只记录项目维度最近一次会话 ID，完整运行态快照由 runtime storage 单独维护。
export function rememberChatSession(projectId, sessionId) {
  writeProjectSessionMemory(chatSessionStorageKey(projectId), sessionId);
}

export function restoreChatSession(projectId) {
  return readProjectSessionMemory(chatSessionStorageKey(projectId));
}

export function clearChatSessionMemory(projectId) {
  clearProjectSessionMemory(chatSessionStorageKey(projectId));
}

export function rememberTaskTreeSession(projectId, sessionId) {
  writeProjectSessionMemory(taskTreeSessionStorageKey(projectId), sessionId);
}

export function restoreTaskTreeSession(projectId) {
  return readProjectSessionMemory(taskTreeSessionStorageKey(projectId));
}

export function clearTaskTreeSessionMemory(projectId) {
  clearProjectSessionMemory(taskTreeSessionStorageKey(projectId));
}

export function rememberWorkSession(projectId, sessionId) {
  writeProjectSessionMemory(workSessionStorageKey(projectId), sessionId);
}

export function restoreWorkSession(projectId) {
  return readProjectSessionMemory(workSessionStorageKey(projectId));
}

export function clearWorkSessionMemory(projectId) {
  clearProjectSessionMemory(workSessionStorageKey(projectId));
}

export function localConnectorPreferenceStorageKey() {
  return `${LOCAL_CONNECTOR_STORAGE_PREFIX}.selected.${resolveCurrentUsername()}`;
}

export function localConnectorWorkspaceStorageKey(projectId, connectorId) {
  return [
    LOCAL_CONNECTOR_STORAGE_PREFIX,
    "workspace",
    resolveCurrentUsername(),
    String(projectId || "").trim() || "default",
    String(connectorId || "").trim() || "default",
  ].join(".");
}

export function readPreferredLocalConnectorId() {
  if (typeof window === "undefined") return "";
  return String(
    localStorage.getItem(localConnectorPreferenceStorageKey()) || "",
  ).trim();
}

export function writePreferredLocalConnectorId(connectorId) {
  if (typeof window === "undefined") return;
  const normalized = String(connectorId || "").trim();
  const key = localConnectorPreferenceStorageKey();
  if (normalized) {
    localStorage.setItem(key, normalized);
    return;
  }
  localStorage.removeItem(key);
}

export function readPreferredLocalWorkspacePath(projectId, connectorId) {
  if (typeof window === "undefined") return "";
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedConnectorId = String(connectorId || "").trim();
  if (!normalizedProjectId || !normalizedConnectorId) return "";
  return String(
    localStorage.getItem(
      localConnectorWorkspaceStorageKey(
        normalizedProjectId,
        normalizedConnectorId,
      ),
    ) || "",
  ).trim();
}

export function writePreferredLocalWorkspacePath(
  projectId,
  connectorId,
  workspacePath,
) {
  if (typeof window === "undefined") return;
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedConnectorId = String(connectorId || "").trim();
  if (!normalizedProjectId || !normalizedConnectorId) return;
  const normalizedWorkspacePath = String(workspacePath || "").trim();
  const key = localConnectorWorkspaceStorageKey(
    normalizedProjectId,
    normalizedConnectorId,
  );
  if (normalizedWorkspacePath) {
    localStorage.setItem(key, normalizedWorkspacePath);
    return;
  }
  localStorage.removeItem(key);
}

export function skillResourceDirectoryStorageKey(projectId) {
  return [
    LOCAL_CONNECTOR_STORAGE_PREFIX,
    "skill_dir",
    resolveCurrentUsername(),
    String(projectId || "").trim() || "default",
  ].join(".");
}

export function readPreferredSkillResourceDirectory(projectId) {
  if (typeof window === "undefined") return "";
  return String(
    localStorage.getItem(skillResourceDirectoryStorageKey(projectId)) || "",
  ).trim();
}

export function writePreferredSkillResourceDirectory(projectId, directoryPath) {
  if (typeof window === "undefined") return;
  const normalized = String(directoryPath || "").trim();
  const key = skillResourceDirectoryStorageKey(projectId);
  if (normalized) {
    localStorage.setItem(key, normalized);
    return;
  }
  localStorage.removeItem(key);
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function normalizeMcpServerName(value, fallback = "mcp-server") {
  const normalized = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-_.]+|[-_.]+$/g, "")
    .slice(0, 80);
  return normalized || fallback;
}

function inferMcpServerName(config, index = 0) {
  const explicitName = config?.name || config?.id || config?.server || config?.server_name;
  if (explicitName) {
    return normalizeMcpServerName(explicitName, `mcp-server-${index + 1}`);
  }
  const url = String(config?.url || config?.endpoint || config?.baseUrl || config?.base_url || "").trim();
  if (url) {
    try {
      const parsed = new URL(url);
      return normalizeMcpServerName(parsed.hostname.split(".")[0], `mcp-server-${index + 1}`);
    } catch {
      return normalizeMcpServerName(url.split("/").filter(Boolean).pop(), `mcp-server-${index + 1}`);
    }
  }
  const command = String(config?.command || "").trim();
  if (command) {
    const args = Array.isArray(config?.args) ? config.args.map((item) => String(item || "")) : [];
    const packageName = args.find((item) => item && !item.startsWith("-") && !item.startsWith("http"));
    return normalizeMcpServerName(packageName || command, `mcp-server-${index + 1}`);
  }
  return `mcp-server-${index + 1}`;
}

function normalizeMcpServerConfig(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const config = { ...source };
  const type = String(
    config.type ||
      config.transport ||
      (config.command ? "stdio" : config.url || config.endpoint || config.baseUrl || config.base_url ? "http" : ""),
  ).trim();
  if (type) config.type = type;
  delete config.transport;
  delete config.name;
  delete config.id;
  delete config.server;
  delete config.server_name;
  if (!config.url) {
    const url = config.endpoint || config.baseUrl || config.base_url;
    if (url) config.url = String(url || "").trim();
  }
  delete config.endpoint;
  delete config.baseUrl;
  delete config.base_url;
  if (Array.isArray(config.args)) {
    config.args = config.args.map((item) => String(item));
  }
  if (config.env && (typeof config.env !== "object" || Array.isArray(config.env))) {
    delete config.env;
  }
  if (config.headers && (typeof config.headers !== "object" || Array.isArray(config.headers))) {
    delete config.headers;
  }
  if (Object.prototype.hasOwnProperty.call(config, "enabled")) {
    config.enabled = Boolean(config.enabled);
  }
  return config;
}

function normalizeMcpServersFromArray(items) {
  const servers = {};
  for (const [index, item] of items.entries()) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const config = normalizeMcpServerConfig(item);
    const baseName = inferMcpServerName(item, index);
    let name = baseName;
    let suffix = 2;
    while (servers[name]) {
      name = `${baseName}-${suffix}`;
      suffix += 1;
    }
    servers[name] = config;
  }
  return servers;
}

function normalizeMcpServersFromObject(rawServers) {
  const servers = {};
  for (const [rawName, rawConfig] of Object.entries(rawServers || {})) {
    const name = normalizeMcpServerName(rawName);
    if (!name || !rawConfig || typeof rawConfig !== "object" || Array.isArray(rawConfig)) {
      continue;
    }
    servers[name] = normalizeMcpServerConfig(rawConfig);
  }
  return servers;
}

export function normalizeMcpConfig(value, fallback = {}) {
  const source =
    value && typeof value === "object" && !Array.isArray(value) ? value : fallback;
  const normalized = {
    ...(source && typeof source === "object" && !Array.isArray(source)
      ? source
      : {}),
  };
  let servers = {};
  let singleServerConfig = false;
  if (
    normalized.mcpServers &&
    typeof normalized.mcpServers === "object" &&
    !Array.isArray(normalized.mcpServers)
  ) {
    servers = normalizeMcpServersFromObject(normalized.mcpServers);
  } else if (
    normalized.servers &&
    typeof normalized.servers === "object" &&
    !Array.isArray(normalized.servers)
  ) {
    servers = normalizeMcpServersFromObject(normalized.servers);
  } else if (Array.isArray(normalized.mcpServers)) {
    servers = normalizeMcpServersFromArray(normalized.mcpServers);
  } else if (Array.isArray(normalized.servers)) {
    servers = normalizeMcpServersFromArray(normalized.servers);
  } else if (normalized.command || normalized.url || normalized.endpoint || normalized.baseUrl || normalized.base_url) {
    const config = normalizeMcpServerConfig(normalized);
    servers[inferMcpServerName(normalized, 0)] = config;
    singleServerConfig = true;
  }
  if (singleServerConfig) {
    return { mcpServers: servers };
  }
  const { servers: _legacyServers, ...rest } = normalized;
  return {
    ...rest,
    mcpServers: servers,
  };
}

export function formatMcpConfig(value) {
  return JSON.stringify(normalizeMcpConfig(value), null, 2);
}

export function parseMcpConfigText(text) {
  let parsed;
  try {
    parsed = JSON.parse(String(text || "").trim() || "{}");
  } catch (err) {
    throw new Error(`MCP 配置 JSON 解析失败：${err?.message || "格式错误"}`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("MCP 配置必须是 JSON 对象");
  }
  return normalizeMcpConfig(parsed);
}

export function globalMcpConfigPathLabel() {
  return "~/.ai-employee/mcp.json";
}

export function projectMcpConfigPathLabel() {
  return ".ai-employee/mcp.json";
}

export async function readGlobalMcpConfigFile() {
  if (!hasNativeDesktopBridge()) {
    return {
      scope: "global",
      path: globalMcpConfigPathLabel(),
      exists: false,
      content: formatMcpConfig(DEFAULT_LOCAL_MCP_CONFIG),
      config: cloneJson(DEFAULT_LOCAL_MCP_CONFIG),
      native: false,
    };
  }
  const result = await readNativeGlobalMcpConfigFile();
  const content = String(result?.content || formatMcpConfig(DEFAULT_LOCAL_MCP_CONFIG));
  return {
    scope: "global",
    path: String(result?.path || globalMcpConfigPathLabel()).trim(),
    exists: Boolean(result?.exists),
    content,
    config: parseMcpConfigText(content),
    native: true,
  };
}

export async function writeGlobalMcpConfigFile(config) {
  const content = formatMcpConfig(config);
  if (!hasNativeDesktopBridge()) {
    throw new Error("当前不是桌面端，无法写入全局 MCP 配置文件");
  }
  const result = await writeNativeGlobalMcpConfigFile(content);
  const normalizedContent = String(result?.content || content);
  return {
    scope: "global",
    path: String(result?.path || globalMcpConfigPathLabel()).trim(),
    exists: Boolean(result?.exists ?? true),
    content: normalizedContent,
    config: parseMcpConfigText(normalizedContent),
    native: true,
  };
}

export async function readProjectMcpConfigFile(workspacePath) {
  const normalizedWorkspacePath = String(workspacePath || "").trim();
  if (!normalizedWorkspacePath || !hasNativeDesktopBridge()) {
    return {
      scope: "project",
      path: projectMcpConfigPathLabel(),
      exists: false,
      content: formatMcpConfig({ mcpServers: {} }),
      config: { mcpServers: {} },
      native: false,
    };
  }
  const result = await readNativeProjectMcpConfigFile(normalizedWorkspacePath);
  const content = String(result?.content || formatMcpConfig({ mcpServers: {} }));
  return {
    scope: "project",
    path: String(result?.path || projectMcpConfigPathLabel()).trim(),
    exists: Boolean(result?.exists),
    content,
    config: parseMcpConfigText(content),
    native: true,
  };
}

export async function writeProjectMcpConfigFile(workspacePath, config) {
  const normalizedWorkspacePath = String(workspacePath || "").trim();
  if (!normalizedWorkspacePath) {
    throw new Error("缺少项目工作区路径，无法写入项目 MCP 配置文件");
  }
  if (!hasNativeDesktopBridge()) {
    throw new Error("当前不是桌面端，无法写入项目 MCP 配置文件");
  }
  const content = formatMcpConfig(config);
  const result = await writeNativeProjectMcpConfigFile(normalizedWorkspacePath, content);
  const normalizedContent = String(result?.content || content);
  return {
    scope: "project",
    path: String(result?.path || projectMcpConfigPathLabel()).trim(),
    exists: Boolean(result?.exists ?? true),
    content: normalizedContent,
    config: parseMcpConfigText(normalizedContent),
    native: true,
  };
}

export function mergeMcpConfigs(globalConfig, projectConfig) {
  const globalNormalized = normalizeMcpConfig(globalConfig);
  const projectNormalized = normalizeMcpConfig(projectConfig);
  return {
    ...globalNormalized,
    ...projectNormalized,
    mcpServers: {
      ...(globalNormalized.mcpServers || {}),
      ...(projectNormalized.mcpServers || {}),
    },
  };
}

export async function readEffectiveMcpConfigFile(workspacePath) {
  const [globalFile, projectFile] = await Promise.all([
    readGlobalMcpConfigFile(),
    readProjectMcpConfigFile(workspacePath),
  ]);
  return {
    global: globalFile,
    project: projectFile,
    config: mergeMcpConfigs(globalFile.config, projectFile.config),
  };
}
