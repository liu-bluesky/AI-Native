import { getStoredAuthProfile } from "@/utils/auth-storage.js";
import {
  hasNativeDesktopBridge,
  readNativeGlobalBotConnectorConfigFile,
  readNativeGlobalMcpConfigFile,
  readNativeGlobalWebToolsConfigFile,
  readNativeProjectMcpConfigFile,
  readNativeProjectWebToolsConfigFile,
  writeNativeGlobalBotConnectorConfigFile,
  writeNativeGlobalMcpConfigFile,
  writeNativeGlobalWebToolsConfigFile,
  writeNativeProjectMcpConfigFile,
  writeNativeProjectWebToolsConfigFile,
} from "@/utils/native-desktop-bridge.js";
import {
  PLUGIN_INSTALL_DRAFT_STORAGE_PREFIX,
  PROJECT_DEPLOY_DRAFT_STORAGE_PREFIX,
  STATISTICS_ANALYSIS_DRAFT_STORAGE_PREFIX,
} from "@/modules/project-chat/constants/projectChatConstants.js";
import {
  cloneJson,
  createJsonConfigEditor,
} from "@/modules/project-chat/services/jsonConfigEditor.js";

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
export const DEFAULT_WEB_TOOLS_CONFIG = {
  version: 1,
  backend: "",
  search: {
    backend: "",
  },
  extract: {
    backend: "",
  },
  providers: {
    managed: {
      search_url: "",
      search_token: "",
      extract_url: "",
      extract_token: "",
    },
    firecrawl: {
      api_key: "",
      api_url: "",
    },
    parallel: {
      api_key: "",
    },
    tavily: {
      api_key: "",
    },
    exa: {
      api_key: "",
    },
  },
};
export const DEFAULT_BOT_CONNECTOR_CONFIG = {
  version: 1,
  connectors: [],
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

export function globalMcpConfigPathLabel() {
  return "~/.ai-employee/mcp.json";
}

export function projectMcpConfigPathLabel() {
  return ".ai-employee/mcp.json";
}

export function normalizeWebToolsConfig(value, fallback = DEFAULT_WEB_TOOLS_CONFIG) {
  const source =
    value && typeof value === "object" && !Array.isArray(value) ? value : fallback;
  return cloneJson(source && typeof source === "object" && !Array.isArray(source) ? source : {});
}

export function formatWebToolsConfig(value) {
  return JSON.stringify(normalizeWebToolsConfig(value), null, 2);
}

function normalizeBotConnectorId(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 80);
}

function normalizeBotConnectorScannedChats(value) {
  const items = Array.isArray(value) ? value : [];
  const seen = new Set();
  const normalized = [];
  for (const item of items) {
    const chatId = String(item?.chat_id || item?.chatId || "").trim().slice(0, 200);
    if (!chatId || seen.has(chatId)) continue;
    seen.add(chatId);
    normalized.push({
      chat_id: chatId,
      chat_name: String(item?.chat_name || item?.chatName || item?.name || "")
        .trim()
        .slice(0, 200),
      chat_type: String(item?.chat_type || item?.chatType || item?.chat_mode || "group")
        .trim()
        .slice(0, 80),
      chat_mode: String(item?.chat_mode || item?.chatMode || "").trim().slice(0, 80),
      source: String(item?.source || "").trim().slice(0, 200),
      scanned_at: String(item?.scanned_at || item?.scannedAt || "").trim().slice(0, 80),
    });
    if (normalized.length >= 500) break;
  }
  return normalized;
}

export function normalizeBotConnectorItem(value) {
  const raw = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const platform = String(raw.platform || "")
    .trim()
    .toLowerCase();
  const id = normalizeBotConnectorId(raw.id || `${platform || "bot"}-connector`);
  return {
    id,
    enabled: raw.enabled !== false,
    platform,
    name: String(raw.name || "").trim().slice(0, 120),
    agent_name: "",
    description: String(raw.description || "").trim().slice(0, 280),
    system_prompt: String(raw.system_prompt || raw.systemPrompt || "").trim().slice(0, 4000),
    chat_mode: "desktop_local_agent",
    external_agent_type: ["codex_cli", "hermes", "claude_code"].includes(
      String(raw.external_agent_type || raw.externalAgentType || "").trim().toLowerCase(),
    )
      ? String(raw.external_agent_type || raw.externalAgentType || "").trim().toLowerCase()
      : "codex_cli",
    provider_id: String(raw.provider_id || raw.providerId || "").trim().slice(0, 120),
    model_name: String(raw.model_name || raw.modelName || "").trim().slice(0, 160),
    model_runtime:
      raw.model_runtime && typeof raw.model_runtime === "object"
        ? cloneJson(raw.model_runtime)
        : raw.modelRuntime && typeof raw.modelRuntime === "object"
          ? cloneJson(raw.modelRuntime)
          : null,
    app_id: String(raw.app_id || raw.appId || "").trim().slice(0, 160),
    app_secret: String(raw.app_secret || raw.appSecret || "").trim().slice(0, 200),
    verification_token: String(raw.verification_token || raw.verificationToken || "")
      .trim()
      .slice(0, 200),
    encrypt_key: String(raw.encrypt_key || raw.encryptKey || "").trim().slice(0, 200),
    event_receive_mode: String(raw.event_receive_mode || raw.eventReceiveMode || "manual")
      .trim()
      .toLowerCase(),
    auto_start_worker: raw.auto_start_worker ?? raw.autoStartWorker ?? false,
    reply_identity: ["bot", "user"].includes(
      String(raw.reply_identity || raw.replyIdentity || "").trim().toLowerCase(),
    )
      ? String(raw.reply_identity || raw.replyIdentity || "").trim().toLowerCase()
      : "bot",
    project_id: "",
    guide_url: String(raw.guide_url || raw.guideUrl || "").trim().slice(0, 500),
    sort_order: Math.min(999, Math.max(0, Number(raw.sort_order || raw.sortOrder || 0) || 0)),
    sandbox_mode: String(raw.sandbox_mode || raw.sandboxMode || "workspace-write")
      .trim()
      .toLowerCase(),
    high_risk_tool_confirm: raw.high_risk_tool_confirm ?? raw.highRiskToolConfirm ?? true,
    scanned_chats: normalizeBotConnectorScannedChats(raw.scanned_chats || raw.scannedChats),
  };
}

export function normalizeBotConnectorConfig(value, fallback = DEFAULT_BOT_CONNECTOR_CONFIG) {
  const raw = Array.isArray(value)
    ? { connectors: value }
    : value && typeof value === "object"
      ? value
      : fallback;
  const seen = new Set();
  const connectors = [];
  for (const item of Array.isArray(raw?.connectors) ? raw.connectors : []) {
    const normalized = normalizeBotConnectorItem(item);
    if (!normalized.id || !normalized.platform) continue;
    const uniqueKey = normalized.id.toLowerCase();
    if (seen.has(uniqueKey)) continue;
    seen.add(uniqueKey);
    connectors.push(normalized);
  }
  connectors.sort(
    (a, b) => a.sort_order - b.sort_order || a.platform.localeCompare(b.platform) || a.id.localeCompare(b.id),
  );
  return {
    version: Number(raw?.version || 1) || 1,
    connectors,
  };
}

export function formatBotConnectorConfig(value) {
  return JSON.stringify(normalizeBotConnectorConfig(value), null, 2);
}

export function globalWebToolsConfigPathLabel() {
  return "~/.ai-employee/desktop-agent-runtime/web-tools/config.json";
}

export function projectWebToolsConfigPathLabel() {
  return ".ai-employee/desktop-agent-runtime/web-tools/config.json";
}

export function globalBotConnectorConfigPathLabel() {
  return "~/.ai-employee/desktop-agent-runtime/bots/connectors.json";
}

const mcpConfigEditor = createJsonConfigEditor({
  label: "MCP 配置",
  globalPathLabel: globalMcpConfigPathLabel(),
  projectPathLabel: projectMcpConfigPathLabel(),
  globalDefaultConfig: DEFAULT_LOCAL_MCP_CONFIG,
  projectDefaultConfig: { mcpServers: {} },
  normalize: normalizeMcpConfig,
  hasNative: hasNativeDesktopBridge,
  readNativeGlobal: readNativeGlobalMcpConfigFile,
  writeNativeGlobal: writeNativeGlobalMcpConfigFile,
  readNativeProject: readNativeProjectMcpConfigFile,
  writeNativeProject: writeNativeProjectMcpConfigFile,
});

const webToolsConfigEditor = createJsonConfigEditor({
  label: "web-tools 配置",
  globalPathLabel: globalWebToolsConfigPathLabel(),
  projectPathLabel: projectWebToolsConfigPathLabel(),
  globalDefaultConfig: DEFAULT_WEB_TOOLS_CONFIG,
  projectDefaultConfig: {},
  normalize: (value, fallback = DEFAULT_WEB_TOOLS_CONFIG) =>
    normalizeWebToolsConfig(value, fallback),
  hasNative: hasNativeDesktopBridge,
  readNativeGlobal: readNativeGlobalWebToolsConfigFile,
  writeNativeGlobal: writeNativeGlobalWebToolsConfigFile,
  readNativeProject: readNativeProjectWebToolsConfigFile,
  writeNativeProject: writeNativeProjectWebToolsConfigFile,
});

const botConnectorConfigEditor = createJsonConfigEditor({
  label: "机器人连接器配置",
  globalPathLabel: globalBotConnectorConfigPathLabel(),
  globalDefaultConfig: DEFAULT_BOT_CONNECTOR_CONFIG,
  normalize: (value, fallback = DEFAULT_BOT_CONNECTOR_CONFIG) =>
    normalizeBotConnectorConfig(value, fallback),
  hasNative: hasNativeDesktopBridge,
  readNativeGlobal: readNativeGlobalBotConnectorConfigFile,
  writeNativeGlobal: writeNativeGlobalBotConnectorConfigFile,
});

export function parseMcpConfigText(text) {
  return mcpConfigEditor.parse(text);
}

export function parseWebToolsConfigText(text) {
  return webToolsConfigEditor.parse(text);
}

export function parseBotConnectorConfigText(text) {
  return botConnectorConfigEditor.parse(text);
}

export async function readGlobalMcpConfigFile() {
  return mcpConfigEditor.readGlobal();
}

export async function writeGlobalMcpConfigFile(config) {
  return mcpConfigEditor.writeGlobal(config);
}

export async function readProjectMcpConfigFile(workspacePath) {
  return mcpConfigEditor.readProject(workspacePath);
}

export async function writeProjectMcpConfigFile(workspacePath, config) {
  return mcpConfigEditor.writeProject(workspacePath, config);
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

export async function readGlobalWebToolsConfigFile() {
  return webToolsConfigEditor.readGlobal();
}

export async function writeGlobalWebToolsConfigFile(config) {
  return webToolsConfigEditor.writeGlobal(config);
}

export async function readGlobalBotConnectorConfigFile() {
  return botConnectorConfigEditor.readGlobal();
}

export async function writeGlobalBotConnectorConfigFile(config) {
  return botConnectorConfigEditor.writeGlobal(config);
}

export async function readProjectWebToolsConfigFile(workspacePath) {
  return webToolsConfigEditor.readProject(workspacePath);
}

export async function writeProjectWebToolsConfigFile(workspacePath, config) {
  return webToolsConfigEditor.writeProject(workspacePath, config);
}

function mergeWebToolConfigValues(globalValue, projectValue) {
  const globalIsObject =
    globalValue && typeof globalValue === "object" && !Array.isArray(globalValue);
  const projectIsObject =
    projectValue && typeof projectValue === "object" && !Array.isArray(projectValue);
  if (globalIsObject || projectIsObject) {
    const merged = {};
    for (const key of Object.keys(globalIsObject ? globalValue : {})) {
      merged[key] = cloneJson(globalValue[key]);
    }
    for (const key of Object.keys(projectIsObject ? projectValue : {})) {
      merged[key] = mergeWebToolConfigValues(merged[key], projectValue[key]);
    }
    return merged;
  }
  if (typeof projectValue === "string" && !projectValue.trim()) {
    return cloneJson(globalValue);
  }
  if (projectValue === undefined || projectValue === null) {
    return cloneJson(globalValue);
  }
  return cloneJson(projectValue);
}

export function mergeWebToolsConfigs(globalConfig, projectConfig) {
  const globalNormalized = normalizeWebToolsConfig(globalConfig, {});
  const projectNormalized = normalizeWebToolsConfig(projectConfig, {});
  const merged = normalizeWebToolsConfig(
    mergeWebToolConfigValues(
      globalNormalized,
      projectNormalized,
    ),
    {},
  );
  applyExplicitWebBackendOverride(merged, projectNormalized, ["backend"]);
  applyExplicitWebBackendOverride(merged, projectNormalized, ["search", "backend"]);
  applyExplicitWebBackendOverride(merged, projectNormalized, ["extract", "backend"]);
  return merged;
}

function hasOwnNestedValue(source, path) {
  let current = source;
  for (const [index, segment] of path.entries()) {
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      return false;
    }
    if (!Object.prototype.hasOwnProperty.call(current, segment)) {
      return false;
    }
    if (index === path.length - 1) return true;
    current = current[segment];
  }
  return false;
}

function nestedValue(source, path) {
  let current = source;
  for (const segment of path) {
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      return undefined;
    }
    current = current[segment];
  }
  return current;
}

function setNestedValue(target, path, value) {
  let current = target;
  for (const [index, segment] of path.entries()) {
    if (index === path.length - 1) {
      current[segment] = value;
      return;
    }
    if (!current[segment] || typeof current[segment] !== "object" || Array.isArray(current[segment])) {
      current[segment] = {};
    }
    current = current[segment];
  }
}

function applyExplicitWebBackendOverride(merged, projectConfig, path) {
  if (!hasOwnNestedValue(projectConfig, path)) return;
  setNestedValue(merged, path, String(nestedValue(projectConfig, path) || "").trim());
}

export async function readEffectiveWebToolsConfigFile(workspacePath) {
  const [globalFile, projectFile] = await Promise.all([
    readGlobalWebToolsConfigFile(),
    readProjectWebToolsConfigFile(workspacePath),
  ]);
  return {
    global: globalFile,
    project: projectFile,
    config: mergeWebToolsConfigs(globalFile.config, projectFile.config),
  };
}
