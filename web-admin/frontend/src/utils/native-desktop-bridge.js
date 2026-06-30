import {
  invoke as invokeTauriCommand,
  isTauri as isTauriRuntime,
} from "@tauri-apps/api/core";
import { listen as listenTauriEvent } from "@tauri-apps/api/event";

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
  previewWorkspaceDiff: "preview_workspace_diff",
  prepareWorkspaceFileWrite: "prepare_workspace_file_write",
  classifyRunnerCommand: "classify_runner_command",
  runRunnerCommand: "run_runner_command",
  recordRunnerPermissionDecision: "record_runner_permission_decision",
  listRunnerPermissionDecisions: "list_runner_permission_decisions",
  liuagentBuiltinToolDefinitions: "liuagent_builtin_tool_definitions",
  liuagentExecuteTool: "liuagent_execute_tool",
  liuagentUploadProviderFile: "liuagent_upload_provider_file",
  liuagentStartLocalChat: "liuagent_start_local_chat",
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
      permissionDecision:
        request?.permissionDecision && typeof request.permissionDecision === "object"
          ? request.permissionDecision
          : request?.permission_decision &&
              typeof request.permission_decision === "object"
            ? request.permission_decision
            : null,
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
