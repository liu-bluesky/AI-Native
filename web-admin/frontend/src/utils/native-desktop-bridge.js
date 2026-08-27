import {
  convertFileSrc,
  invoke as invokeTauriCommand,
  isTauri as isTauriRuntime,
} from "@tauri-apps/api/core";
import { listen as listenTauriEvent } from "@tauri-apps/api/event";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import { getCurrentWindow } from "@tauri-apps/api/window";

const NATIVE_BRIDGE_NAMES = [
  "__AI_EMPLOYEE_DESKTOP__",
  "aiEmployeeDesktop",
];

const TAURI_COMMAND_NAMES = {
  pickWorkspaceDirectory: "pick_workspace_directory",
  detectExecutors: "detect_executors",
  getRuntimeInfo: "get_runtime_info",
  listWorkspaceFiles: "list_workspace_files",
  readWorkspaceFile: "read_workspace_file",
  readLocalFile: "read_local_file",
  openDesktopDevtools: "open_desktop_devtools",
  previewWorkspaceDiff: "preview_workspace_diff",
  prepareWorkspaceFileWrite: "prepare_workspace_file_write",
  writeWorkspaceFile: "write_workspace_file",
  listWorkspaceFileChanges: "list_workspace_file_changes",
  acceptWorkspaceFileChange: "accept_workspace_file_change",
  revertWorkspaceFileChange: "revert_workspace_file_change",
  readGlobalMcpConfigFile: "read_global_mcp_config_file",
  writeGlobalMcpConfigFile: "write_global_mcp_config_file",
  readProjectMcpConfigFile: "read_project_mcp_config_file",
  writeProjectMcpConfigFile: "write_project_mcp_config_file",
  readGlobalWebToolsConfigFile: "read_global_web_tools_config_file",
  writeGlobalWebToolsConfigFile: "write_global_web_tools_config_file",
  readProjectWebToolsConfigFile: "read_project_web_tools_config_file",
  writeProjectWebToolsConfigFile: "write_project_web_tools_config_file",
  readGlobalBotConnectorConfigFile: "read_global_bot_connector_config_file",
  writeGlobalBotConnectorConfigFile: "write_global_bot_connector_config_file",
  readGlobalProjectCatalogFile: "read_global_project_catalog_file",
  writeGlobalProjectCatalogFile: "write_global_project_catalog_file",
  readGlobalFtpCredentialsFile: "read_global_ftp_credentials_file",
  writeGlobalFtpCredentialsFile: "write_global_ftp_credentials_file",
  openExternalUrl: "open_external_url",
  copyResourceFileToClipboard: "copy_resource_file_to_clipboard",
  saveResourceFile: "save_resource_file",
  persistProjectChatAsset: "persist_project_chat_asset",
  classifyRunnerCommand: "classify_runner_command",
  runRunnerCommand: "run_runner_command",
  recordRunnerPermissionDecision: "record_runner_permission_decision",
  listRunnerPermissionDecisions: "list_runner_permission_decisions",
  checkDesktopUpdate: "check_desktop_update",
  getDesktopVersion: "get_desktop_version",
  installDesktopUpdate: "install_desktop_update",
  discoverProviderModels: "discover_provider_models",
  testProviderModel: "test_provider_model",
  liuagentBuiltinToolDefinitions: "liuagent_builtin_tool_definitions",
  liuagentExecuteTool: "liuagent_execute_tool",
  liuagentUploadProviderFile: "liuagent_upload_provider_file",
  liuagentStartLocalChat: "liuagent_start_local_chat",
  liuagentPauseLocalChat: "liuagent_pause_local_chat",
  liuagentClassifyPermissionReply: "liuagent_classify_permission_reply",
  botStartFeishuLocalListener: "bot_start_feishu_local_listener",
  botStopFeishuLocalListener: "bot_stop_feishu_local_listener",
  botListFeishuLocalListeners: "bot_list_feishu_local_listeners",
  botScanFeishuChats: "bot_scan_feishu_chats",
  liuagentPrepareAgentInvocation: "liuagent_prepare_agent_invocation",
  liuagentRecoverRuntimeState: "liuagent_recover_runtime_state",
  liuagentRefreshRuntimeJob: "liuagent_refresh_runtime_job",
  liuagentCancelRuntimeJob: "liuagent_cancel_runtime_job",
  liuagentListRuntimeEvents: "liuagent_list_runtime_events",
  liuagentListRuntimeOutbox: "liuagent_list_runtime_outbox",
  liuagentAckRuntimeOutbox: "liuagent_ack_runtime_outbox",
  liuagentSaveOfflineCache: "liuagent_save_offline_cache",
  liuagentLoadOfflineCache: "liuagent_load_offline_cache",
  liuagentCleanupOfflineCache: "liuagent_cleanup_offline_cache",
  projectChatListSessions: "project_chat_list_sessions",
  projectChatListAllSessions: "project_chat_list_all_sessions",
  projectChatUpsertSession: "project_chat_upsert_session",
  projectChatReplaceSessions: "project_chat_replace_sessions",
  projectChatReadRuntime: "project_chat_read_runtime",
  projectChatWriteRuntime: "project_chat_write_runtime",
  projectChatDeleteSession: "project_chat_delete_session",
  agentSupervisionSearchAnswers: "agent_supervision_search_answers",
  agentSupervisionGetAnswer: "agent_supervision_get_answer",
  agentSupervisionFindAnswer: "agent_supervision_find_answer",
};

function canUseWindow() {
  return typeof window !== "undefined";
}

function resolveNativeGlobals() {
  const candidates = [];
  const appendCandidate = (candidate) => {
    if (!candidate || candidates.includes(candidate)) return;
    candidates.push(candidate);
  };

  if (typeof globalThis !== "undefined") appendCandidate(globalThis);
  if (!canUseWindow()) return candidates;

  appendCandidate(window);
  try {
    appendCandidate(window.parent);
  } catch {
    // Cross-origin parent windows cannot expose the native bridge.
  }
  try {
    appendCandidate(window.top);
  } catch {
    // Cross-origin top windows cannot expose the native bridge.
  }
  return candidates;
}

function resolveTauriInvoke() {
  for (const nativeGlobal of resolveNativeGlobals()) {
    try {
      const tauriCore = nativeGlobal.__TAURI__?.core;
      if (typeof tauriCore?.invoke === "function") {
        return tauriCore.invoke.bind(tauriCore);
      }
      if (typeof nativeGlobal.__TAURI__?.invoke === "function") {
        return nativeGlobal.__TAURI__.invoke.bind(nativeGlobal.__TAURI__);
      }
      if (typeof nativeGlobal.__TAURI_INTERNALS__?.invoke === "function") {
        return nativeGlobal.__TAURI_INTERNALS__.invoke.bind(
          nativeGlobal.__TAURI_INTERNALS__,
        );
      }
    } catch {
      // Ignore inaccessible cross-origin window globals.
    }
  }
  return null;
}

function resolveTauriEventListen() {
  for (const nativeGlobal of resolveNativeGlobals()) {
    try {
      const eventApi = nativeGlobal.__TAURI__?.event;
      if (typeof eventApi?.listen === "function") {
        return eventApi.listen.bind(eventApi);
      }
      if (typeof nativeGlobal.__TAURI__?.listen === "function") {
        return nativeGlobal.__TAURI__.listen.bind(nativeGlobal.__TAURI__);
      }
    } catch {
      // Ignore inaccessible cross-origin window globals.
    }
  }
  return null;
}

function canUseTauriApi() {
  for (const nativeGlobal of resolveNativeGlobals()) {
    try {
      if (
        nativeGlobal?.isTauri === true ||
        nativeGlobal?.__TAURI__ ||
        nativeGlobal?.__TAURI_INTERNALS__
      ) {
        return true;
      }
    } catch {
      // Ignore inaccessible cross-origin window globals.
    }
  }
  try {
    return Boolean(isTauriRuntime());
  } catch {
    return false;
  }
}

function resolveBridge() {
  for (const nativeGlobal of resolveNativeGlobals()) {
    for (const key of NATIVE_BRIDGE_NAMES) {
      try {
        const candidate = nativeGlobal[key];
        if (candidate && typeof candidate === "object") return candidate;
      } catch {
        // Ignore inaccessible cross-origin window globals.
      }
    }
  }
  return null;
}

export function hasNativeDesktopBridge() {
  return Boolean(resolveBridge() || canUseTauriApi() || resolveTauriInvoke());
}

function requireNativeProjectChatStore() {
  if (!hasNativeDesktopBridge()) {
    throw new Error("桌面聊天本地 SQLite 存储不可用");
  }
}

export async function listNativeProjectChatSessions(projectId, username) {
  requireNativeProjectChatStore();
  const result = await invokeNativeDesktopBridge("projectChatListSessions", {
    projectId: String(projectId || "").trim(),
    username: String(username || "").trim(),
  });
  return Array.isArray(result) ? result : [];
}

export async function listAllNativeProjectChatSessions(username) {
  requireNativeProjectChatStore();
  const result = await invokeNativeDesktopBridge("projectChatListAllSessions", {
    username: String(username || "").trim(),
  });
  return Array.isArray(result) ? result : [];
}

export async function upsertNativeProjectChatSession(
  projectId,
  username,
  session,
) {
  requireNativeProjectChatStore();
  return invokeNativeDesktopBridge("projectChatUpsertSession", {
    projectId: String(projectId || "").trim(),
    username: String(username || "").trim(),
    session: session && typeof session === "object" ? session : {},
  });
}

export async function replaceNativeProjectChatSessions(
  projectId,
  username,
  sessions,
) {
  requireNativeProjectChatStore();
  return invokeNativeDesktopBridge("projectChatReplaceSessions", {
    projectId: String(projectId || "").trim(),
    username: String(username || "").trim(),
    sessions: Array.isArray(sessions) ? sessions : [],
  });
}

export async function readNativeProjectChatRuntime(
  projectId,
  chatSessionId,
  username,
) {
  requireNativeProjectChatStore();
  return invokeNativeDesktopBridge("projectChatReadRuntime", {
    projectId: String(projectId || "").trim(),
    chatSessionId: String(chatSessionId || "").trim(),
    username: String(username || "").trim(),
  });
}

export async function writeNativeProjectChatRuntime(
  projectId,
  chatSessionId,
  username,
  payload,
) {
  requireNativeProjectChatStore();
  return invokeNativeDesktopBridge("projectChatWriteRuntime", {
    projectId: String(projectId || "").trim(),
    chatSessionId: String(chatSessionId || "").trim(),
    username: String(username || "").trim(),
    payload: payload && typeof payload === "object" ? payload : {},
  });
}

export async function deleteNativeProjectChatSession(
  projectId,
  chatSessionId,
  username,
) {
  requireNativeProjectChatStore();
  return invokeNativeDesktopBridge("projectChatDeleteSession", {
    projectId: String(projectId || "").trim(),
    chatSessionId: String(chatSessionId || "").trim(),
    username: String(username || "").trim(),
  });
}

export async function searchNativeAgentSupervisionAnswers(
  projectId,
  username,
  query = "",
  limit = 50,
) {
  requireNativeProjectChatStore();
  const result = await invokeNativeDesktopBridge(
    "agentSupervisionSearchAnswers",
    {
      projectId: String(projectId || "").trim(),
      username: String(username || "").trim(),
      query: String(query || "").trim(),
      limit: Math.max(1, Math.min(200, Number(limit || 50))),
    },
  );
  return Array.isArray(result) ? result : [];
}

export async function getNativeAgentSupervisionAnswer(
  projectId,
  username,
  answerId,
) {
  requireNativeProjectChatStore();
  return invokeNativeDesktopBridge("agentSupervisionGetAnswer", {
    projectId: String(projectId || "").trim(),
    username: String(username || "").trim(),
    answerId: String(answerId || "").trim(),
  });
}

export async function findNativeAgentSupervisionAnswer(
  username,
  answerId,
  projectId = "",
) {
  requireNativeProjectChatStore();
  return invokeNativeDesktopBridge("agentSupervisionFindAnswer", {
    username: String(username || "").trim(),
    answerId: String(answerId || "").trim(),
    projectId: String(projectId || "").trim(),
  });
}

export async function invokeNativeDesktopBridge(method, payload = {}) {
  const normalizedMethod = String(method || "").trim();
  if (!normalizedMethod) return null;
  const bridge = resolveBridge();
  if (bridge) {
    const handler = bridge[normalizedMethod];
    if (typeof handler === "function") {
      return handler(payload && typeof payload === "object" ? payload : {});
    }
    if (typeof bridge.invoke === "function") {
      return bridge.invoke(
        normalizedMethod,
        payload && typeof payload === "object" ? payload : {},
      );
    }
  }
  const tauriInvoke = resolveTauriInvoke();
  const tauriCommand = TAURI_COMMAND_NAMES[normalizedMethod] || normalizedMethod;
  if (tauriInvoke && tauriCommand) {
    return tauriInvoke(
      tauriCommand,
      payload && typeof payload === "object" ? payload : {},
    );
  }
  if (canUseTauriApi() && tauriCommand) {
    return invokeTauriCommand(
      tauriCommand,
      payload && typeof payload === "object" ? payload : {},
    );
  }
  return null;
}

export async function pickNativeWorkspaceDirectory(options = {}) {
  const result = await invokeNativeDesktopBridge("pickWorkspaceDirectory", {
    title: String(options?.title || "选择工作区目录").trim(),
    initialPath: String(options?.initialPath || "").trim(),
  });
  if (!result) return null;
  if (typeof result === "string") return result.trim() || null;
  if (result.cancelled) return null;
  return String(result.path || result.workspacePath || "").trim() || null;
}

export async function detectNativeExecutors(options = {}) {
  const result = await invokeNativeDesktopBridge("detectExecutors", {
    workspacePath: String(options?.workspacePath || "").trim(),
  });
  if (!result || typeof result !== "object") return null;
  return {
    codex: normalizeExecutorStatus(result.codex),
    hermes: normalizeExecutorStatus(result.hermes),
    claudeCode: normalizeExecutorStatus(result.claudeCode || result.claude_code),
    workspace: normalizeWorkspaceStatus(result.workspace),
  };
}

export async function getNativeRuntimeInfo() {
  const result = await invokeNativeDesktopBridge("getRuntimeInfo");
  if (!result || typeof result !== "object") return null;
  return {
    platform: String(result.platform || "").trim(),
    arch: String(result.arch || "").trim(),
    desktopBridgeVersion: String(
      result.desktopBridgeVersion || result.desktop_bridge_version || "",
    ).trim(),
    installDir: String(result.installDir || result.install_dir || "").trim(),
    defaultWorkspacePath: String(
      result.defaultWorkspacePath || result.default_workspace_path || "",
    ).trim(),
  };
}

export async function getNativeDesktopVersion() {
  const result = await invokeNativeDesktopBridge("getDesktopVersion");
  const version = typeof result === "string" ? result : result?.version;
  return String(version || "").trim() || null;
}

export async function checkNativeDesktopUpdate(endpoint) {
  const normalizedEndpoint = String(endpoint || "").trim();
  if (!normalizedEndpoint) return null;
  const result = await invokeNativeDesktopBridge("checkDesktopUpdate", {
    endpoint: normalizedEndpoint,
  });
  if (!result || typeof result !== "object") return null;
  return {
    version: String(result.version || "").trim(),
    currentVersion: String(result.currentVersion || result.current_version || "").trim(),
    notes: String(result.notes || ""),
    pubDate: String(result.pubDate || result.pub_date || "").trim(),
  };
}

export async function installNativeDesktopUpdate(endpoint) {
  const normalizedEndpoint = String(endpoint || "").trim();
  if (!normalizedEndpoint) throw new Error("版本更新地址未配置");
  const result = await invokeNativeDesktopBridge("installDesktopUpdate", {
    endpoint: normalizedEndpoint,
  });
  if (result === null || result === undefined) {
    throw new Error("桌面端版本更新命令不可用，请完全退出并重新启动桌面端");
  }
  return result;
}

export async function subscribeNativeDesktopUpdateProgress(handler) {
  if (typeof handler !== "function" || !hasNativeDesktopBridge()) return () => {};
  const handleEvent = (event) => {
    const payload = event?.payload && typeof event.payload === "object" ? event.payload : event;
    handler({
      downloaded: Number(payload?.downloaded || 0),
      contentLength: Number(payload?.contentLength || payload?.content_length || 0) || null,
      finished: Boolean(payload?.finished),
    });
  };
  const unlisteners = [];
  try {
    unlisteners.push(await listenTauriEvent("desktop-update-progress", handleEvent));
  } catch (_error) {
    // iframe/legacy bridge fallback below
  }
  if (!unlisteners.length) {
    const fallbackListen = resolveTauriEventListen();
    if (fallbackListen) {
      try {
        unlisteners.push(await fallbackListen("desktop-update-progress", handleEvent));
      } catch (_error) {
        // ignore unavailable event bridge
      }
    }
  }
  if (!unlisteners.length) return () => {};
  return () => {
    for (const unlisten of unlisteners) {
      try {
        unlisten?.();
      } catch (_error) {
        // ignore cleanup errors
      }
    }
  };
}

export async function discoverNativeProviderModels(options = {}) {
  let result;
  try {
    result = await invokeNativeDesktopBridge("discoverProviderModels", {
      request: {
        providerType: String(
          options?.providerType || options?.provider_type || "openai-compatible",
        ).trim(),
        baseUrl: String(options?.baseUrl || options?.base_url || "").trim(),
        apiKey: String(options?.apiKey || options?.api_key || "").trim(),
        extraHeaders:
          options?.extraHeaders && typeof options.extraHeaders === "object"
            ? options.extraHeaders
            : options?.extra_headers && typeof options.extra_headers === "object"
              ? options.extra_headers
              : {},
      },
    });
  } catch (error) {
    const detail =
      typeof error === "string"
        ? error.trim()
        : String(error?.detail || error?.message || error?.error || "").trim();
    throw new Error(detail || "桌面端模型发现命令执行失败");
  }
  if (!result || typeof result !== "object") {
    throw new Error(
      "桌面端模型发现命令不可用，请完全退出并重新启动桌面端",
    );
  }
  const normalizeModelItem = (item) =>
    typeof item === "object"
      ? String(item?.id || item?.name || item?.model || "").trim()
      : String(item || "").trim();
  return {
    models: Array.isArray(result?.models)
      ? result.models.map(normalizeModelItem).filter(Boolean)
      : Array.isArray(result?.data)
        ? result.data.map(normalizeModelItem).filter(Boolean)
        : [],
  };
}

export async function testNativeProviderModel(options = {}) {
  return invokeNativeDesktopBridge("testProviderModel", {
    request: {
      providerType: String(options?.providerType || options?.provider_type || "openai-compatible").trim(),
      baseUrl: String(options?.baseUrl || options?.base_url || "").trim(),
      apiKey: String(options?.apiKey || options?.api_key || "").trim(),
      modelName: String(options?.modelName || options?.model_name || "").trim(),
      modelType: String(options?.modelType || options?.model_type || "text_generation").trim(),
      extraHeaders: options?.extraHeaders && typeof options.extraHeaders === "object" ? options.extraHeaders : {},
    },
  });
}

function normalizeConfigFileContent(value) {
  const content = String(value ?? "");
  return content.trim().toLowerCase() === "undefined" ? "" : content;
}

function normalizeConfigFileResult(result) {
  if (!result || typeof result !== "object") return null;
  return {
    scope: String(result.scope || "").trim(),
    path: String(result.path || "").trim(),
    exists: Boolean(result.exists),
    content: normalizeConfigFileContent(result.content),
  };
}

export async function readNativeGlobalMcpConfigFile() {
  const result = await invokeNativeDesktopBridge("readGlobalMcpConfigFile");
  return normalizeConfigFileResult(result);
}

export async function writeNativeGlobalMcpConfigFile(content = "") {
  const result = await invokeNativeDesktopBridge("writeGlobalMcpConfigFile", {
    content: String(content || ""),
  });
  return normalizeConfigFileResult(result);
}

export async function readNativeProjectMcpConfigFile(workspacePath = "") {
  const normalizedWorkspacePath = String(workspacePath || "").trim();
  if (!normalizedWorkspacePath) return null;
  const result = await invokeNativeDesktopBridge("readProjectMcpConfigFile", {
    workspacePath: normalizedWorkspacePath,
  });
  return normalizeConfigFileResult(result);
}

export async function writeNativeProjectMcpConfigFile(workspacePath = "", content = "") {
  const normalizedWorkspacePath = String(workspacePath || "").trim();
  if (!normalizedWorkspacePath) return null;
  const result = await invokeNativeDesktopBridge("writeProjectMcpConfigFile", {
    workspacePath: normalizedWorkspacePath,
    content: String(content || ""),
  });
  return normalizeConfigFileResult(result);
}

export async function readNativeGlobalWebToolsConfigFile() {
  const result = await invokeNativeDesktopBridge("readGlobalWebToolsConfigFile");
  return normalizeConfigFileResult(result);
}

export async function writeNativeGlobalWebToolsConfigFile(content = "") {
  const result = await invokeNativeDesktopBridge("writeGlobalWebToolsConfigFile", {
    content: String(content || ""),
  });
  return normalizeConfigFileResult(result);
}

export async function readNativeProjectWebToolsConfigFile(workspacePath = "") {
  const normalizedWorkspacePath = String(workspacePath || "").trim();
  if (!normalizedWorkspacePath) return null;
  const result = await invokeNativeDesktopBridge("readProjectWebToolsConfigFile", {
    workspacePath: normalizedWorkspacePath,
  });
  return normalizeConfigFileResult(result);
}

export async function writeNativeProjectWebToolsConfigFile(workspacePath = "", content = "") {
  const normalizedWorkspacePath = String(workspacePath || "").trim();
  if (!normalizedWorkspacePath) return null;
  const result = await invokeNativeDesktopBridge("writeProjectWebToolsConfigFile", {
    workspacePath: normalizedWorkspacePath,
    content: String(content || ""),
  });
  return normalizeConfigFileResult(result);
}

export async function readNativeGlobalBotConnectorConfigFile() {
  const result = await invokeNativeDesktopBridge("readGlobalBotConnectorConfigFile");
  return normalizeConfigFileResult(result);
}

export async function writeNativeGlobalBotConnectorConfigFile(content = "") {
  const result = await invokeNativeDesktopBridge("writeGlobalBotConnectorConfigFile", {
    content: String(content || ""),
  });
  return normalizeConfigFileResult(result);
}

export async function readNativeGlobalProjectCatalogFile() {
  const result = await invokeNativeDesktopBridge("readGlobalProjectCatalogFile");
  return normalizeConfigFileResult(result);
}

export async function writeNativeGlobalProjectCatalogFile(content = "") {
  const result = await invokeNativeDesktopBridge("writeGlobalProjectCatalogFile", {
    content: String(content || ""),
  });
  return normalizeConfigFileResult(result);
}

export async function readNativeGlobalFtpCredentialsFile() {
  const result = await invokeNativeDesktopBridge("readGlobalFtpCredentialsFile");
  return normalizeConfigFileResult(result);
}

export async function writeNativeGlobalFtpCredentialsFile(content = "") {
  const result = await invokeNativeDesktopBridge("writeGlobalFtpCredentialsFile", {
    content: String(content || ""),
  });
  return normalizeConfigFileResult(result);
}

export async function openNativeExternalUrl(url = "") {
  const normalizedUrl = String(url || "").trim();
  if (!normalizedUrl) return false;
  const result = await invokeNativeDesktopBridge("openExternalUrl", {
    url: normalizedUrl,
  });
  return result === true || result?.opened === true;
}

export async function copyNativeResourceFileToClipboard(options = {}) {
  const url = String(options?.url || "").trim();
  if (!url) throw new Error("缺少要复制的文件地址");
  return invokeNativeDesktopBridge("copyResourceFileToClipboard", {
    url,
    fileName: String(options?.fileName || "").trim(),
    mimeType: String(options?.mimeType || "").trim(),
    authorizationToken: String(options?.authorizationToken || "").trim(),
  });
}

export async function saveNativeResourceFile(options = {}) {
  const url = String(options?.url || "").trim();
  if (!url) throw new Error("缺少要保存的文件地址");
  return invokeNativeDesktopBridge("saveResourceFile", {
    url,
    fileName: String(options?.fileName || "").trim(),
    mimeType: String(options?.mimeType || "").trim(),
    authorizationToken: String(options?.authorizationToken || "").trim(),
  });
}

export async function persistNativeProjectChatAsset(options = {}) {
  const url = String(options?.url || "").trim();
  const username = String(options?.username || "").trim();
  const projectId = String(options?.projectId || "").trim();
  const chatSessionId = String(options?.chatSessionId || "").trim();
  const messageId = String(options?.messageId || "").trim();
  if (!url || !username || !projectId || !chatSessionId || !messageId) {
    throw new Error("持久化会话资产缺少必要参数");
  }
  const result = await invokeNativeDesktopBridge("persistProjectChatAsset", {
    username,
    projectId,
    chatSessionId,
    messageId,
    url,
    fileName: String(options?.fileName || "").trim(),
    mimeType: String(options?.mimeType || "").trim(),
    assetType: String(options?.assetType || "").trim(),
    authorizationToken: String(options?.authorizationToken || "").trim(),
    sourceTool: String(options?.sourceTool || "").trim(),
  });
  const localPath = String(result?.localPath || "").trim();
  return {
    ...(result && typeof result === "object" ? result : {}),
    localPath,
    displayUrl: localPath ? convertFileSrc(localPath) : url,
  };
}

export async function listNativeLiuAgentBuiltinTools() {
  const result = await invokeNativeDesktopBridge("liuagentBuiltinToolDefinitions");
  return Array.isArray(result) ? result : [];
}

export async function executeNativeLiuAgentTool(request = {}) {
  const toolName = String(request?.name || request?.toolName || "").trim();
  const workspacePath = String(request?.workspacePath || "").trim();
  if (!toolName) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "tool name is required",
    };
  }
  if (!workspacePath) {
    return {
      ok: false,
      errorCode: "workspace.not_configured",
      error: "workspacePath is required",
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentExecuteTool", {
    request: {
      toolCallId: String(request?.toolCallId || "").trim(),
      name: toolName,
      arguments:
        request?.arguments && typeof request.arguments === "object"
          ? request.arguments
          : {},
      workspacePath,
      permissionDecision:
        request?.permissionDecision &&
        typeof request.permissionDecision === "object"
          ? request.permissionDecision
          : null,
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent runtime is unavailable",
      };
}

export async function startNativeLiuAgentLocalChat(request = {}) {
  const projectId = String(request?.projectId || request?.project_id || "").trim();
  const chatSessionId = String(
    request?.chatSessionId || request?.chat_session_id || "",
  ).trim();
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  const message = String(request?.message || "").trim();
  if (!projectId || !chatSessionId || !workspacePath || !message) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "projectId, chatSessionId, workspacePath and message are required",
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentStartLocalChat", {
    request: {
      projectId,
      chatSessionId,
      messageId: String(request?.messageId || request?.message_id || "").trim(),
      assistantMessageId: String(
        request?.assistantMessageId || request?.assistant_message_id || "",
      ).trim(),
      message,
      workspacePath,
      history: Array.isArray(request?.history) ? request.history : [],
      providerId: String(request?.providerId || request?.provider_id || "").trim(),
      modelName: String(request?.modelName || request?.model_name || "").trim(),
      systemPrompt: String(
        request?.systemPrompt || request?.system_prompt || "",
      ).trim(),
      systemPromptParts: (
        Array.isArray(request?.systemPromptParts)
          ? request.systemPromptParts
          : Array.isArray(request?.system_prompt_parts)
            ? request.system_prompt_parts
            : []
      )
        .map((part) => ({
          source: String(part?.source || "").trim(),
          priority:
            Number.isFinite(Number(part?.priority)) && part?.priority !== ""
              ? Number(part.priority)
              : null,
          content: String(part?.content || "").trim(),
        }))
        .filter((part) => part.content),
      temperature:
        Number.isFinite(Number(request?.temperature)) &&
        request?.temperature !== ""
          ? Number(request.temperature)
          : null,
      modelRuntime:
        request?.modelRuntime && typeof request.modelRuntime === "object"
          ? request.modelRuntime
          : request?.model_runtime && typeof request.model_runtime === "object"
            ? request.model_runtime
            : null,
      aiEntryFile: String(request?.aiEntryFile || request?.ai_entry_file || "").trim(),
      localResourceDirectories:
        request?.localResourceDirectories && typeof request.localResourceDirectories === "object"
          ? request.localResourceDirectories
          : request?.local_resource_directories && typeof request.local_resource_directories === "object"
            ? request.local_resource_directories
            : null,
      mcpConfig:
        request?.mcpConfig && typeof request.mcpConfig === "object"
          ? request.mcpConfig
          : request?.mcp_config && typeof request.mcp_config === "object"
            ? request.mcp_config
            : null,
      attachments: Array.isArray(request?.attachments)
        ? request.attachments
        : Array.isArray(request?.localAttachments)
          ? request.localAttachments
          : [],
      mediaTools: Array.isArray(request?.mediaTools)
        ? request.mediaTools
        : Array.isArray(request?.media_tools)
          ? request.media_tools
          : [],
      backendContext:
        request?.backendContext && typeof request.backendContext === "object"
          ? request.backendContext
          : request?.backend_context && typeof request.backend_context === "object"
            ? request.backend_context
            : null,
      permissionDecision:
        request?.permissionDecision && typeof request.permissionDecision === "object"
          ? request.permissionDecision
          : request?.permission_decision &&
              typeof request.permission_decision === "object"
            ? request.permission_decision
            : null,
      userQuestionAnswer:
        request?.userQuestionAnswer && typeof request.userQuestionAnswer === "object"
          ? request.userQuestionAnswer
          : request?.user_question_answer &&
              typeof request.user_question_answer === "object"
            ? request.user_question_answer
            : null,
      resumeFromCheckpoint: Boolean(
        request?.resumeFromCheckpoint || request?.resume_from_checkpoint,
      ),
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent local chat runtime is unavailable",
      };
}

export async function pauseNativeLiuAgentLocalChat(request = {}) {
  const normalizedRequest =
    request && typeof request === "object" ? request : { chatSessionId: request };
  const normalizedChatSessionId = String(
    normalizedRequest?.chatSessionId || normalizedRequest?.chat_session_id || "",
  ).trim();
  if (!normalizedChatSessionId) return false;
  return Boolean(
    await invokeNativeDesktopBridge("liuagentPauseLocalChat", {
      request: {
        projectId: String(
          normalizedRequest?.projectId || normalizedRequest?.project_id || "",
        ).trim(),
        chatSessionId: normalizedChatSessionId,
        workspacePath: String(
          normalizedRequest?.workspacePath || normalizedRequest?.workspace_path || "",
        ).trim(),
        reason: String(normalizedRequest?.reason || "manual_pause").trim(),
      },
    }),
  );
}

export async function classifyNativeLiuAgentPermissionReply(request = {}) {
  const projectId = String(request?.projectId || request?.project_id || "").trim();
  const chatSessionId = String(
    request?.chatSessionId || request?.chat_session_id || "",
  ).trim();
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  const message = String(request?.message || "").trim();
  if (!projectId || !chatSessionId || !workspacePath || !message) {
    return {
      ok: false,
      decision: "not_an_approval",
      errorCode: "tool.schema_invalid",
      error: "projectId, chatSessionId, workspacePath and message are required",
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentClassifyPermissionReply", {
    request: {
      ...request,
      projectId,
      chatSessionId,
      workspacePath,
      message,
      permissionDecision: null,
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        decision: "not_an_approval",
        errorCode: "native_bridge.unavailable",
        error: "native permission reply classifier is unavailable",
      };
}

export async function startNativeFeishuLocalBotListener(options = {}) {
  const connectorId = String(options?.connectorId || options?.connector_id || "").trim();
  if (!connectorId) {
    throw new Error("缺少机器人连接器 ID");
  }
  return invokeNativeDesktopBridge("botStartFeishuLocalListener", {
    request: {
      connectorId,
      modelRuntime: options?.modelRuntime || options?.model_runtime || null,
      mcpConfig: options?.mcpConfig || options?.mcp_config || {},
      permissionDecision:
        options?.permissionDecision || options?.permission_decision || null,
    },
  });
}

export async function stopNativeFeishuLocalBotListener(connectorId) {
  return invokeNativeDesktopBridge("botStopFeishuLocalListener", {
    connectorId: String(connectorId || "").trim(),
  });
}

export async function listNativeFeishuLocalBotListeners() {
  const result = await invokeNativeDesktopBridge("botListFeishuLocalListeners");
  return Array.isArray(result) ? result : [];
}

export async function scanNativeFeishuBotChats(options = {}) {
  return invokeNativeDesktopBridge("botScanFeishuChats", {
    request: {
      pageSize: Number(options?.pageSize || options?.page_size || 100) || 100,
      pageLimit: Number(options?.pageLimit || options?.page_limit || 10) || 10,
    },
  });
}

export async function uploadNativeLiuAgentProviderFile(request = {}) {
  const baseUrl = String(request?.baseUrl || request?.base_url || "").trim();
  const apiKey = String(request?.apiKey || request?.api_key || "").trim();
  const filename = String(request?.filename || request?.name || "").trim();
  const fileBytes = Array.isArray(request?.fileBytes)
    ? request.fileBytes
    : Array.isArray(request?.file_bytes)
      ? request.file_bytes
      : [];
  if (!baseUrl || !apiKey || !filename || !fileBytes.length) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "baseUrl, apiKey, filename and fileBytes are required",
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentUploadProviderFile", {
    request: {
      providerId: String(request?.providerId || request?.provider_id || "").trim(),
      baseUrl,
      apiKey,
      filename,
      mimeType: String(request?.mimeType || request?.mime_type || "").trim(),
      purpose: String(request?.purpose || "").trim(),
      fileBytes,
      timeoutMs:
        Number.isFinite(Number(request?.timeoutMs || request?.timeout_ms)) &&
        (request?.timeoutMs || request?.timeout_ms) !== ""
          ? Number(request?.timeoutMs || request?.timeout_ms)
          : null,
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent provider file upload is unavailable",
      };
}

export async function prepareNativeLiuAgentInvocation(request = {}) {
  const projectId = String(request?.projectId || request?.project_id || "").trim();
  const chatSessionId = String(
    request?.chatSessionId || request?.chat_session_id || "",
  ).trim();
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  const userMessage = String(
    request?.userMessage || request?.user_message || request?.message || "",
  ).trim();
  if (!projectId || !chatSessionId || !workspacePath || !userMessage) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "projectId, chatSessionId, workspacePath and userMessage are required",
    };
  }
  const capabilities = Array.isArray(request?.capabilities)
    ? request.capabilities.map((item) => String(item || "").trim()).filter(Boolean)
    : ["local_runner", "mcp_recording", "desktop_tools"];
  const result = await invokeNativeDesktopBridge("liuagentPrepareAgentInvocation", {
    request: {
      invocationId: String(
        request?.invocationId || request?.invocation_id || "",
      ).trim(),
      source: String(request?.source || "project_chat").trim(),
      adapterKind: String(
        request?.adapterKind || request?.adapter_kind || "desktop",
      ).trim(),
      projectId,
      chatSessionId,
      userMessage,
      workspacePath,
      agentId: String(request?.agentId || request?.agent_id || "").trim(),
      promptBundleId: String(
        request?.promptBundleId || request?.prompt_bundle_id || "",
      ).trim(),
      toolBundleId: String(
        request?.toolBundleId || request?.tool_bundle_id || "",
      ).trim(),
      capabilities,
      recordRequirement:
        request?.recordRequirement ?? request?.record_requirement ?? true,
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent agent gateway is unavailable",
      };
}

export async function recoverNativeLiuAgentRuntimeState(request = {}) {
  const projectId = String(request?.projectId || request?.project_id || "").trim();
  const chatSessionId = String(
    request?.chatSessionId || request?.chat_session_id || "",
  ).trim();
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  if (!projectId || !chatSessionId || !workspacePath) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "projectId, chatSessionId and workspacePath are required",
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentRecoverRuntimeState", {
    request: {
      projectId,
      chatSessionId,
      workspacePath,
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent runtime recovery is unavailable",
      };
}

function normalizeNativeLiuAgentRuntimeJobRequest(request = {}) {
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  const statePath = String(request?.statePath || request?.state_path || "").trim();
  if (!workspacePath || !statePath) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "workspacePath and statePath are required",
    };
  }
  return {
    request: {
      workspacePath,
      statePath,
    },
  };
}

export async function refreshNativeLiuAgentRuntimeJob(request = {}) {
  const payload = normalizeNativeLiuAgentRuntimeJobRequest(request);
  if (payload?.ok === false) return payload;
  const result = await invokeNativeDesktopBridge("liuagentRefreshRuntimeJob", payload);
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent runtime job refresh is unavailable",
      };
}

export async function cancelNativeLiuAgentRuntimeJob(request = {}) {
  const payload = normalizeNativeLiuAgentRuntimeJobRequest(request);
  if (payload?.ok === false) return payload;
  const result = await invokeNativeDesktopBridge("liuagentCancelRuntimeJob", payload);
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent runtime job cancel is unavailable",
      };
}

export async function listNativeLiuAgentRuntimeEvents(request = {}) {
  const projectId = String(request?.projectId || request?.project_id || "").trim();
  const chatSessionId = String(
    request?.chatSessionId || request?.chat_session_id || "",
  ).trim();
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  if (!projectId || !chatSessionId || !workspacePath) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "projectId, chatSessionId and workspacePath are required",
      events: [],
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentListRuntimeEvents", {
    request: {
      projectId,
      chatSessionId,
      workspacePath,
      afterEventId: String(
        request?.afterEventId || request?.after_event_id || "",
      ).trim(),
      limit: Number.isFinite(Number(request?.limit)) ? Number(request.limit) : null,
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent runtime event stream is unavailable",
        events: [],
      };
}

export async function listNativeLiuAgentRuntimeOutbox(request = {}) {
  const projectId = String(request?.projectId || request?.project_id || "").trim();
  const chatSessionId = String(
    request?.chatSessionId || request?.chat_session_id || "",
  ).trim();
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  if (!projectId || !workspacePath) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "projectId and workspacePath are required",
      entries: [],
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentListRuntimeOutbox", {
    request: {
      projectId,
      chatSessionId: chatSessionId || null,
      workspacePath,
      limit: Number.isFinite(Number(request?.limit)) ? Number(request.limit) : null,
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent runtime outbox is unavailable",
        entries: [],
      };
}

export async function ackNativeLiuAgentRuntimeOutbox(request = {}) {
  const projectId = String(request?.projectId || request?.project_id || "").trim();
  const chatSessionId = String(
    request?.chatSessionId || request?.chat_session_id || "",
  ).trim();
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  const eventIds = Array.isArray(request?.eventIds || request?.event_ids)
    ? (request.eventIds || request.event_ids)
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  if (!projectId || !chatSessionId || !workspacePath) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "projectId, chatSessionId and workspacePath are required",
      deletedCount: 0,
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentAckRuntimeOutbox", {
    request: {
      projectId,
      chatSessionId,
      workspacePath,
      eventIds,
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent runtime outbox ack is unavailable",
        deletedCount: 0,
      };
}

export async function saveNativeLiuAgentOfflineCache(request = {}) {
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  const cacheKind = String(
    request?.cacheKind || request?.cache_kind || "",
  ).trim();
  if (!workspacePath || !cacheKind) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "workspacePath and cacheKind are required",
      result: {},
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentSaveOfflineCache", {
    request: {
      workspacePath,
      cacheKind,
      projectId: String(request?.projectId || request?.project_id || "").trim() || null,
      chatSessionId:
        String(request?.chatSessionId || request?.chat_session_id || "").trim() ||
        null,
      providerId: String(request?.providerId || request?.provider_id || "").trim() || null,
      payload:
        request?.payload && typeof request.payload === "object"
          ? request.payload
          : {},
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent offline cache save is unavailable",
        result: {},
      };
}

export async function loadNativeLiuAgentOfflineCache(request = {}) {
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  const cacheKind = String(
    request?.cacheKind || request?.cache_kind || "",
  ).trim();
  if (!workspacePath || !cacheKind) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "workspacePath and cacheKind are required",
      result: {},
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentLoadOfflineCache", {
    request: {
      workspacePath,
      cacheKind,
      projectId: String(request?.projectId || request?.project_id || "").trim() || null,
      chatSessionId:
        String(request?.chatSessionId || request?.chat_session_id || "").trim() ||
        null,
      providerId: String(request?.providerId || request?.provider_id || "").trim() || null,
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent offline cache load is unavailable",
        result: {},
      };
}

export async function cleanupNativeLiuAgentOfflineCache(request = {}) {
  const workspacePath = String(
    request?.workspacePath || request?.workspace_path || "",
  ).trim();
  const projectId = String(request?.projectId || request?.project_id || "").trim();
  const chatSessionId = String(
    request?.chatSessionId || request?.chat_session_id || "",
  ).trim();
  const eventIds = Array.isArray(request?.eventIds || request?.event_ids)
    ? (request.eventIds || request.event_ids)
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  if (!workspacePath || !projectId || !chatSessionId) {
    return {
      ok: false,
      errorCode: "tool.schema_invalid",
      error: "workspacePath, projectId and chatSessionId are required",
      result: {},
    };
  }
  const result = await invokeNativeDesktopBridge("liuagentCleanupOfflineCache", {
    request: {
      workspacePath,
      projectId,
      chatSessionId,
      eventIds,
      serverRefs:
        request?.serverRefs && typeof request.serverRefs === "object"
          ? request.serverRefs
          : request?.server_refs && typeof request.server_refs === "object"
            ? request.server_refs
            : {},
    },
  });
  return result && typeof result === "object"
    ? result
    : {
        ok: false,
        errorCode: "native_bridge.unavailable",
        error: "native liuAgent offline cache cleanup is unavailable",
        result: {},
      };
}

export async function listNativeWorkspaceFiles(options = {}) {
  const workspacePath = String(
    options?.workspacePath || options?.workspace_path || "",
  ).trim();
  const path = String(options?.path || "").trim();
  const result = await invokeNativeDesktopBridge("listWorkspaceFiles", {
    workspacePath,
    path,
  });
  return normalizeWorkspaceFileList(result, { workspacePath, path });
}

export async function readNativeWorkspaceFile(options = {}) {
  const workspacePath = String(
    options?.workspacePath || options?.workspace_path || "",
  ).trim();
  const path = String(options?.path || "").trim();
  const result = await invokeNativeDesktopBridge("readWorkspaceFile", {
    workspacePath,
    path,
  });
  return normalizeWorkspaceFileReadResult(result, { workspacePath, path });
}

export async function readNativeLocalFile(path = "") {
  const normalizedPath = String(path || "").trim();
  if (!normalizedPath) {
    throw new Error("缺少本地文件路径");
  }
  const result = await invokeNativeDesktopBridge("readLocalFile", {
    path: normalizedPath,
  });
  if (!result || typeof result !== "object") {
    throw new Error(`桌面端未返回文件内容：${normalizedPath}`);
  }
  return {
    name: String(result?.name || "").trim(),
    mimeType: String(result?.mimeType || result?.mime_type || "").trim(),
    size: Number(result?.size || 0) || 0,
    bytes: Array.isArray(result?.bytes) ? result.bytes : [],
  };
}

export async function openNativeDesktopDevtools() {
  return invokeNativeDesktopBridge("openDesktopDevtools");
}

function toNativeDragDropPoint(value) {
  if (Array.isArray(value)) {
    const x = Number(value[0]);
    const y = Number(value[1]);
    return {
      x: Number.isFinite(x) ? x : Number.NaN,
      y: Number.isFinite(y) ? y : Number.NaN,
    };
  }
  if (!value || typeof value !== "object") {
    return { x: Number.NaN, y: Number.NaN };
  }
  const nested =
    value.Physical ||
    value.Logical ||
    value.physical ||
    value.logical ||
    null;
  const source = nested && typeof nested === "object" ? nested : value;
  const x = Number(source.x);
  const y = Number(source.y);
  return {
    x: Number.isFinite(x) ? x : Number.NaN,
    y: Number.isFinite(y) ? y : Number.NaN,
  };
}

function unwrapNativeDragDropSource(payload = {}, fallbackType = "") {
  if (payload == null || typeof payload !== "object") {
    return { type: String(fallbackType || "").trim() };
  }
  if (payload.enter && typeof payload.enter === "object") {
    return { type: "enter", ...payload.enter };
  }
  if (payload.over && typeof payload.over === "object") {
    return { type: "over", ...payload.over };
  }
  if (payload.drop && typeof payload.drop === "object") {
    return { type: "drop", ...payload.drop };
  }
  if (payload.leave && typeof payload.leave === "object") {
    return { type: "leave", ...payload.leave };
  }
  if (
    Object.prototype.hasOwnProperty.call(payload, "leave") &&
    payload.leave == null
  ) {
    return { type: "leave" };
  }
  return payload;
}

export function normalizeNativeDragDropPayload(payload = {}, fallbackType = "") {
  const source = unwrapNativeDragDropSource(payload, fallbackType);
  const paths = Array.isArray(source.paths)
    ? source.paths.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  let type = String(source.type || fallbackType || "").trim();
  if (!type) {
    type = paths.length ? "drop" : "over";
  }
  return {
    type,
    paths,
    position: toNativeDragDropPoint(source.position),
  };
}

export function nativeDragDropCssPoints(position = {}) {
  if (typeof window === "undefined") return [];
  const point = toNativeDragDropPoint(position);
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return [];
  if (Math.abs(point.x) < 0.5 && Math.abs(point.y) < 0.5) return [];
  const devicePixelRatio = Number(window.devicePixelRatio || 1) || 1;
  const cssPoint = {
    x: point.x / devicePixelRatio,
    y: point.y / devicePixelRatio,
  };
  const points = [cssPoint];
  if (
    Math.abs(cssPoint.x - point.x) > 0.5 ||
    Math.abs(cssPoint.y - point.y) > 0.5
  ) {
    points.push(point);
  }
  return points;
}

function currentNativeWindowLabel() {
  try {
    const label = String(getCurrentWebviewWindow()?.label || "").trim();
    if (label) return label;
  } catch (_error) {
    // Ignore missing webview window handles outside Tauri.
  }
  try {
    const label = String(getCurrentWindow()?.label || "").trim();
    if (label) return label;
  } catch (_error) {
    // Ignore missing window handles outside Tauri.
  }
  return "main";
}

function currentNativeDragDropListenTargets() {
  const label = currentNativeWindowLabel();
  return [
    { kind: "Any" },
    { kind: "AnyLabel", label },
    { kind: "WebviewWindow", label },
    { kind: "Webview", label },
    { kind: "Window", label },
  ];
}

async function subscribeNativeDragDropSource(label, subscribe) {
  try {
    const unlisten = await subscribe();
    return typeof unlisten === "function" ? unlisten : null;
  } catch (error) {
    console.warn(`订阅 ${label} 失败`, error);
    return null;
  }
}

const NATIVE_DRAG_LEAVE_GRACE_MS = 600;
export const NATIVE_FILE_DRAG_DROP_DOM_EVENT =
  "ai-employee-native-file-drag-drop";

export async function subscribeNativeDesktopDragDrop(handler) {
  if (typeof handler !== "function") {
    return null;
  }
  const unlisteners = [];
  const recentEvents = new Map();
  let leaveTimer = null;
  const cancelNativeDragLeaveTimer = () => {
    if (leaveTimer == null) return;
    clearTimeout(leaveTimer);
    leaveTimer = null;
  };
  const forwardPayload = (payload, fallbackType = "") => {
    try {
      const normalizedPayload = normalizeNativeDragDropPayload(
        payload,
        fallbackType,
      );
      const type = String(normalizedPayload.type || "").trim();
      const position = normalizedPayload.position || {};
      const paths = Array.isArray(normalizedPayload.paths)
        ? normalizedPayload.paths
        : [];
      if (type !== "leave") {
        const signature = [
          type,
          paths.join("\0"),
          Math.round(Number(position.x || 0)),
          Math.round(Number(position.y || 0)),
        ].join(":");
        const now = Date.now();
        const previous = recentEvents.get(signature) || 0;
        const isDuplicate = now - previous < 250;
        if (!isDuplicate) {
          recentEvents.set(signature, now);
          if (recentEvents.size > 32) {
            for (const [key, timestamp] of recentEvents) {
              if (now - timestamp > 1000) recentEvents.delete(key);
            }
          }
        }
        cancelNativeDragLeaveTimer();
        if (isDuplicate) return;
        handler(normalizedPayload);
        return;
      }
      if (leaveTimer != null) return;
      leaveTimer = setTimeout(() => {
        leaveTimer = null;
        handler(normalizedPayload);
      }, NATIVE_DRAG_LEAVE_GRACE_MS);
    } catch (error) {
      console.warn("处理原生文件拖放事件失败", error);
    }
  };

  const addUnlistener = (unlisten) => {
    if (typeof unlisten === "function") unlisteners.push(unlisten);
  };

  if (typeof window !== "undefined") {
    const onNativeDomDragDrop = (event) => {
      forwardPayload(event?.detail);
    };
    window.addEventListener(
      NATIVE_FILE_DRAG_DROP_DOM_EVENT,
      onNativeDomDragDrop,
    );
    document.addEventListener(
      NATIVE_FILE_DRAG_DROP_DOM_EVENT,
      onNativeDomDragDrop,
    );
    addUnlistener(() => {
      window.removeEventListener(
        NATIVE_FILE_DRAG_DROP_DOM_EVENT,
        onNativeDomDragDrop,
      );
      document.removeEventListener(
        NATIVE_FILE_DRAG_DROP_DOM_EVENT,
        onNativeDomDragDrop,
      );
    });
  }

  addUnlistener(
    await subscribeNativeDragDropSource(
      "WebviewWindow.onDragDropEvent",
      async () =>
        getCurrentWebviewWindow().onDragDropEvent((event) => {
          try {
            forwardPayload(event?.payload);
          } catch (error) {
            console.warn("处理 WebviewWindow.onDragDropEvent 失败", error);
          }
        }),
    ),
  );
  addUnlistener(
    await subscribeNativeDragDropSource("Webview.onDragDropEvent", async () =>
      getCurrentWebview().onDragDropEvent((event) => {
        try {
          forwardPayload(event?.payload);
        } catch (error) {
          console.warn("处理 Webview.onDragDropEvent 失败", error);
        }
      }),
    ),
  );
  addUnlistener(
    await subscribeNativeDragDropSource("Window.onDragDropEvent", async () =>
      getCurrentWindow().onDragDropEvent((event) => {
        try {
          forwardPayload(event?.payload);
        } catch (error) {
          console.warn("处理 Window.onDragDropEvent 失败", error);
        }
      }),
    ),
  );
  addUnlistener(
    await subscribeNativeDragDropSource(
      "WebviewWindow.desktop-file-drag-drop",
      async () =>
        getCurrentWebviewWindow().listen("desktop-file-drag-drop", (event) => {
          forwardPayload(event?.payload);
        }),
    ),
  );
  addUnlistener(
    await subscribeNativeDragDropSource("desktop-file-drag-drop", async () =>
      listenTauriEvent("desktop-file-drag-drop", (event) => {
        forwardPayload(event?.payload);
      }),
    ),
  );
  for (const target of currentNativeDragDropListenTargets()) {
    addUnlistener(
      await subscribeNativeDragDropSource(
        `desktop-file-drag-drop:${target.kind}`,
        async () =>
          listenTauriEvent(
            "desktop-file-drag-drop",
            (event) => {
              forwardPayload(event?.payload);
            },
            { target },
          ),
      ),
    );
  }
  const rawDragEvents = [
    ["tauri://drag-enter", "enter"],
    ["tauri://drag-over", "over"],
    ["tauri://drag-drop", "drop"],
    ["tauri://drag-leave", "leave"],
  ];
  for (const [eventName, fallbackType] of rawDragEvents) {
    for (const target of currentNativeDragDropListenTargets()) {
      addUnlistener(
        await subscribeNativeDragDropSource(
          `${eventName}:${target.kind}`,
          async () =>
            listenTauriEvent(
              eventName,
              (event) => {
                forwardPayload(event?.payload, fallbackType);
              },
              { target },
            ),
        ),
      );
    }
  }

  if (!unlisteners.length) return null;
  return () => {
    cancelNativeDragLeaveTimer();
    for (const unlisten of unlisteners) {
      try {
        unlisten();
      } catch (_error) {
        // Ignore cleanup failures from a window that has already closed.
      }
    }
  };
}

export async function previewNativeWorkspaceDiff(options = {}) {
  const workspacePath = String(
    options?.workspacePath || options?.workspace_path || "",
  ).trim();
  const path = String(options?.path || "").trim();
  const result = await invokeNativeDesktopBridge("previewWorkspaceDiff", {
    workspacePath,
    path,
  });
  return normalizeWorkspaceDiffPreview(result, { workspacePath, path });
}

export async function prepareNativeWorkspaceFileWrite(options = {}) {
  const workspacePath = String(
    options?.workspacePath || options?.workspace_path || "",
  ).trim();
  const path = String(options?.path || "").trim();
  const content = String(options?.content || "");
  const result = await invokeNativeDesktopBridge("prepareWorkspaceFileWrite", {
    workspacePath,
    path,
    content,
  });
  return normalizeWorkspaceFileWritePreparation(result, {
    workspacePath,
    path,
  });
}

export async function writeNativeWorkspaceFile(options = {}) {
  const workspacePath = String(options?.workspacePath || options?.workspace_path || "").trim();
  const path = String(options?.path || "").trim();
  const content = String(options?.content || "");
  const expectedCurrentHash = String(options?.expectedCurrentHash || options?.expected_current_hash || "").trim();
  return invokeNativeDesktopBridge("writeWorkspaceFile", {
    workspacePath,
    path,
    content,
    expectedCurrentHash,
  });
}

export async function listNativeWorkspaceFileChanges(options = {}) {
  const workspacePath = String(options?.workspacePath || options?.workspace_path || "").trim();
  const result = await invokeNativeDesktopBridge("listWorkspaceFileChanges", { workspacePath });
  return (Array.isArray(result) ? result : []).map((item) => ({
    path: String(item?.path || "").trim(),
    changeType: String(item?.changeType || item?.change_type || "modified").trim(),
    baselineHash: String(item?.baselineHash || item?.baseline_hash || "").trim(),
    currentHash: String(item?.currentHash || item?.current_hash || "").trim(),
    createdAtEpochMs: Number(item?.createdAtEpochMs || item?.created_at_epoch_ms || 0),
    reviewStatus: String(item?.reviewStatus || item?.review_status || "pending").trim(),
  }));
}

export function acceptNativeWorkspaceFileChange(options = {}) {
  return invokeNativeDesktopBridge("acceptWorkspaceFileChange", {
    workspacePath: String(options?.workspacePath || "").trim(),
    path: String(options?.path || "").trim(),
    expectedCurrentHash: String(options?.expectedCurrentHash || "").trim(),
  });
}

export function revertNativeWorkspaceFileChange(options = {}) {
  return invokeNativeDesktopBridge("revertWorkspaceFileChange", {
    workspacePath: String(options?.workspacePath || "").trim(),
    path: String(options?.path || "").trim(),
    expectedCurrentHash: String(options?.expectedCurrentHash || "").trim(),
  });
}

export async function classifyNativeRunnerCommand(options = {}) {
  const payload = normalizeRunnerCommandPayload(options);
  const result = await invokeNativeDesktopBridge("classifyRunnerCommand", payload);
  return normalizeRunnerCommandClassification(result, payload);
}

export async function runNativeRunnerCommand(options = {}) {
  const payload = normalizeRunnerCommandPayload(options);
  const result = await invokeNativeDesktopBridge("runRunnerCommand", {
    ...payload,
    timeoutMs: Number(options?.timeoutMs || options?.timeout_ms || 5000),
    dryRun: Boolean(options?.dryRun || options?.dry_run),
  });
  return normalizeRunnerCommandResult(result, payload);
}

function removedNativeExternalAgentError() {
  return new Error("代理会话功能已下线，请使用系统对话或桌面端 Runner 命令。");
}

export async function prepareNativeExternalAgentLaunch(options = {}) {
  throw removedNativeExternalAgentError();
}

export async function startNativeExternalAgentSession(options = {}) {
  throw removedNativeExternalAgentError();
}

/// 复用常驻会话发送新一轮 prompt（多轮上下文由 CLI 自身维护）。
/// 找不到可复用会话时 Rust 端返回 Err，调用方据此回退到 startNativeExternalAgentSession。
export async function sendNativeExternalAgentPrompt(options = {}) {
  throw removedNativeExternalAgentError();
}

/// 预热常驻会话：提前启动进程并完成握手，首条消息直接复用、免冷启动。
/// 当前仅 hermes 支持；其它 agent 或环境不可用时 Rust 端返回 Err。
export async function warmupNativeExternalAgentSession(options = {}) {
  throw removedNativeExternalAgentError();
}

export async function getNativeExternalAgentSession(options = {}) {
  throw removedNativeExternalAgentError();
}

export async function listNativeExternalAgentSessions(options = {}) {
  return [];
}

export async function cancelNativeExternalAgentSession(options = {}) {
  throw removedNativeExternalAgentError();
}

export async function hardKillNativeExternalAgentSession(options = {}) {
  throw removedNativeExternalAgentError();
}

export async function writeNativeExternalAgentSessionInput(options = {}) {
  throw removedNativeExternalAgentError();
}

export async function resolveNativeExternalAgentPermission(options = {}) {
  throw removedNativeExternalAgentError();
}

export async function subscribeNativeExternalAgentSessionEvents(handler) {
  return () => {};
}

export async function subscribeNativeLiuAgentRuntimeEvents(handler) {
  if (typeof handler !== "function") return () => {};
  if (!hasNativeDesktopBridge()) return () => {};
  const handleEvent = (event) => {
    handler(event?.payload && typeof event.payload === "object" ? event.payload : {});
  };
  const unlisteners = [];
  try {
    unlisteners.push(await listenTauriEvent("liuagent-runtime-event", handleEvent));
  } catch (_error) {
    // keep legacy fallback below
  }
  try {
    unlisteners.push(await listenTauriEvent("liuagent://runtime-event", handleEvent));
  } catch (_error) {
    // keep primary listener if available
  }
  if (!unlisteners.length) {
    const fallbackListen = resolveTauriEventListen();
    if (fallbackListen) {
      try {
        unlisteners.push(await fallbackListen("liuagent-runtime-event", handleEvent));
      } catch (_error) {
        // keep legacy fallback below
      }
      try {
        unlisteners.push(await fallbackListen("liuagent://runtime-event", handleEvent));
      } catch (_error) {
        // keep primary listener if available
      }
    }
  }
  if (!unlisteners.length) {
    return () => {};
  }
  return () => {
    for (const unlisten of unlisteners) {
      try {
        unlisten?.();
      } catch (_error) {
        // ignore cleanup errors
      }
    }
  };
}

export async function subscribeNativeFeishuLocalBotStatus(handler) {
  if (typeof handler !== "function") return () => {};
  if (!hasNativeDesktopBridge()) return () => {};
  const handleEvent = (event) => {
    handler(event?.payload && typeof event.payload === "object" ? event.payload : {});
  };
  const unlisteners = [];
  try {
    unlisteners.push(await listenTauriEvent("bot-feishu-local-status", handleEvent));
  } catch (_error) {
    // keep fallback below
  }
  try {
    unlisteners.push(await listenTauriEvent("bot://feishu-local-status", handleEvent));
  } catch (_error) {
    // keep primary listener if available
  }
  if (!unlisteners.length) {
    const fallbackListen = resolveTauriEventListen();
    if (fallbackListen) {
      try {
        unlisteners.push(await fallbackListen("bot-feishu-local-status", handleEvent));
      } catch (_error) {
        // ignore
      }
      try {
        unlisteners.push(await fallbackListen("bot://feishu-local-status", handleEvent));
      } catch (_error) {
        // ignore
      }
    }
  }
  if (!unlisteners.length) return () => {};
  return () => {
    for (const unlisten of unlisteners) {
      try {
        unlisten?.();
      } catch (_error) {
        // ignore cleanup errors
      }
    }
  };
}

export async function recordNativeRunnerPermissionDecision(options = {}) {
  const payload = normalizeRunnerPermissionDecisionPayload(options);
  const result = await invokeNativeDesktopBridge(
    "recordRunnerPermissionDecision",
    { input: payload },
  );
  return normalizeRunnerPermissionDecisionRecord(result, payload);
}

export async function listNativeRunnerPermissionDecisions(options = {}) {
  const limit = Number(options?.limit || 20);
  const result = await invokeNativeDesktopBridge(
    "listRunnerPermissionDecisions",
    { limit },
  );
  if (!Array.isArray(result)) return [];
  return result
    .map((item) => normalizeRunnerPermissionDecisionRecord(item))
    .filter((item) => item.decisionId);
}

function normalizeExecutorStatus(value) {
  if (value === true) return { installed: true, path: "", version: "" };
  if (!value || typeof value !== "object") {
    return { installed: false, path: "", version: "" };
  }
  return {
    installed: Boolean(value.installed || value.available),
    path: String(value.path || value.executablePath || "").trim(),
    version: String(value.version || "").trim(),
    reason: String(value.reason || "").trim(),
  };
}

function normalizeRunnerCommandPayload(options = {}) {
  return {
    command: String(options?.command || "").trim(),
    args: Array.isArray(options?.args)
      ? options.args.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    workspacePath: String(
      options?.workspacePath || options?.workspace_path || "",
    ).trim(),
  };
}

function normalizeRunnerPermissionDecisionPayload(options = {}) {
  return {
    decisionId: String(options?.decisionId || options?.decision_id || "").trim(),
    command: String(options?.command || "").trim(),
    args: Array.isArray(options?.args)
      ? options.args.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    workspacePath: String(
      options?.workspacePath || options?.workspace_path || "",
    ).trim(),
    decision: String(options?.decision || "").trim(),
    reason: String(options?.reason || "").trim(),
    scope: String(options?.scope || "").trim(),
    source: String(options?.source || "").trim(),
    riskLevel: String(options?.riskLevel || options?.risk_level || "").trim(),
  };
}

function normalizeRunnerCommandClassification(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      allowed: false,
      riskLevel: "unavailable",
      requiresApproval: false,
      command: fallback.command || "",
      args: fallback.args || [],
      workspacePath: fallback.workspacePath || "",
      blockedReason: "桌面端原生 Runner 不可用",
      summary: "",
    };
  }
  return {
    allowed: Boolean(value.allowed),
    riskLevel: String(value.riskLevel || value.risk_level || "").trim(),
    requiresApproval: Boolean(value.requiresApproval || value.requires_approval),
    command: String(value.command || fallback.command || "").trim(),
    args: Array.isArray(value.args) ? value.args.map((item) => String(item)) : [],
    workspacePath: String(
      value.workspacePath || value.workspace_path || fallback.workspacePath || "",
    ).trim(),
    blockedReason: String(
      value.blockedReason || value.blocked_reason || "",
    ).trim(),
    summary: String(value.summary || "").trim(),
  };
}

function normalizeRunnerCommandResult(value, fallback = {}) {
  const classification = normalizeRunnerCommandClassification(value, fallback);
  if (!value || typeof value !== "object") {
    return {
      ...classification,
      stdout: "",
      stderr: "",
      exitCode: -1,
      durationMs: 0,
      timedOut: false,
    };
  }
  return {
    ...classification,
    stdout: String(value.stdout || ""),
    stderr: String(value.stderr || ""),
    exitCode: Number(value.exitCode ?? value.exit_code ?? -1),
    durationMs: Number(value.durationMs ?? value.duration_ms ?? 0),
    timedOut: Boolean(value.timedOut || value.timed_out),
  };
}

function normalizeRunnerPermissionDecisionRecord(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      decisionId: fallback.decisionId || "",
      command: fallback.command || "",
      args: fallback.args || [],
      workspacePath: fallback.workspacePath || "",
      decision: fallback.decision || "",
      reason: fallback.reason || "",
      scope: fallback.scope || "",
      source: fallback.source || "",
      riskLevel: fallback.riskLevel || "",
      createdAtEpochMs: 0,
    };
  }
  return {
    decisionId: String(
      value.decisionId || value.decision_id || fallback.decisionId || "",
    ).trim(),
    command: String(value.command || fallback.command || "").trim(),
    args: Array.isArray(value.args)
      ? value.args.map((item) => String(item || "").trim()).filter(Boolean)
      : fallback.args || [],
    workspacePath: String(
      value.workspacePath || value.workspace_path || fallback.workspacePath || "",
    ).trim(),
    decision: String(value.decision || fallback.decision || "").trim(),
    reason: String(value.reason || fallback.reason || "").trim(),
    scope: String(value.scope || fallback.scope || "").trim(),
    source: String(value.source || fallback.source || "").trim(),
    riskLevel: String(
      value.riskLevel || value.risk_level || fallback.riskLevel || "",
    ).trim(),
    createdAtEpochMs: Number(
      value.createdAtEpochMs || value.created_at_epoch_ms || 0,
    ),
  };
}

function normalizeWorkspaceStatus(value) {
  if (!value || typeof value !== "object") {
    return {
      configured: false,
      exists: false,
      isDirectory: false,
      path: "",
      reason: "",
    };
  }
  const path = String(value.path || "").trim();
  const configured = Boolean(value.configured || path);
  const exists = Boolean(value.exists);
  const isDirectory = Boolean(value.isDirectory || value.is_directory);
  return {
    configured,
    exists,
    isDirectory,
    path,
    reason: String(value.reason || "").trim(),
  };
}

function normalizeWorkspaceFileList(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      root: fallback.workspacePath || "",
      path: fallback.path || "",
      items: [],
    };
  }
  return {
    root: String(value.root || fallback.workspacePath || "").trim(),
    path: String(value.path || fallback.path || "").trim(),
    items: Array.isArray(value.items)
      ? value.items.map(normalizeWorkspaceFileItem).filter((item) => item.name)
      : [],
  };
}

function normalizeWorkspaceFileItem(value) {
  const kind = String(value?.kind || "").trim();
  return {
    name: String(value?.name || "").trim(),
    path: String(value?.path || "").trim(),
    kind: kind === "directory" ? "directory" : "file",
    size: Number(value?.size || 0),
    modifiedAtEpochMs: Number(
      value?.modifiedAtEpochMs || value?.modified_at_epoch_ms || 0,
    ),
  };
}

function normalizeWorkspaceFileReadResult(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      root: fallback.workspacePath || "",
      path: fallback.path || "",
      name: "",
      size: 0,
      modifiedAtEpochMs: 0,
      encoding: "",
      content: "",
    };
  }
  return {
    root: String(value.root || fallback.workspacePath || "").trim(),
    path: String(value.path || fallback.path || "").trim(),
    name: String(value.name || "").trim(),
    size: Number(value.size || 0),
    modifiedAtEpochMs: Number(
      value.modifiedAtEpochMs || value.modified_at_epoch_ms || 0,
    ),
    encoding: String(value.encoding || "").trim(),
    content: String(value.content || ""),
    contentHash: String(value.contentHash || value.content_hash || "").trim(),
  };
}

function normalizeWorkspaceDiffPreview(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      root: fallback.workspacePath || "",
      path: fallback.path || "",
      available: false,
      summary: "",
      diff: "",
      status: "",
      exitCode: -1,
      truncated: false,
      reason: "桌面端原生 diff 预览不可用",
    };
  }
  return {
    root: String(value.root || fallback.workspacePath || "").trim(),
    path: String(value.path || fallback.path || "").trim(),
    available: Boolean(value.available),
    summary: String(value.summary || ""),
    diff: String(value.diff || ""),
    status: String(value.status || ""),
    exitCode: Number(value.exitCode ?? value.exit_code ?? -1),
    truncated: Boolean(value.truncated),
    reason: String(value.reason || "").trim(),
    currentHash: String(value.currentHash || value.current_hash || "").trim(),
    nextHash: String(value.nextHash || value.next_hash || "").trim(),
    modifiedAtEpochMs: Number(value.modifiedAtEpochMs || value.modified_at_epoch_ms || 0),
  };
}

function normalizeWorkspaceFileWritePreparation(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      root: fallback.workspacePath || "",
      path: fallback.path || "",
      exists: false,
      currentSize: 0,
      nextSize: 0,
      currentLineCount: 0,
      nextLineCount: 0,
      changed: false,
      riskLevel: "unavailable",
      requiresApproval: false,
      summary: "桌面端原生写入准备不可用",
      reason: "",
    };
  }
  return {
    root: String(value.root || fallback.workspacePath || "").trim(),
    path: String(value.path || fallback.path || "").trim(),
    exists: Boolean(value.exists),
    currentSize: Number(value.currentSize ?? value.current_size ?? 0),
    nextSize: Number(value.nextSize ?? value.next_size ?? 0),
    currentLineCount: Number(
      value.currentLineCount ?? value.current_line_count ?? 0,
    ),
    nextLineCount: Number(value.nextLineCount ?? value.next_line_count ?? 0),
    changed: Boolean(value.changed),
    riskLevel: String(value.riskLevel || value.risk_level || "").trim(),
    requiresApproval: Boolean(
      value.requiresApproval || value.requires_approval,
    ),
    summary: String(value.summary || "").trim(),
    reason: String(value.reason || "").trim(),
  };
}
