const CHAT_RUNTIME_LOCAL_COMPACT_MESSAGE_LIMIT = 12;
const CHAT_RUNTIME_LOCAL_MINIMAL_MESSAGE_LIMIT = 4;
const CHAT_RUNTIME_LOCAL_COMPACT_CONTENT_LIMIT = 8000;
const CHAT_RUNTIME_LOCAL_MINIMAL_CONTENT_LIMIT = 2000;
const CHAT_RUNTIME_LOCAL_COMPACT_LOG_LIMIT = 80;
const CHAT_RUNTIME_LOCAL_COMPACT_OPERATION_LIMIT = 20;

export function chatRuntimeStorageKey(projectId, chatSessionId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return "";
  return `project_chat_runtime_${normalizedProjectId}_${normalizedChatSessionId}`;
}

export function chatRuntimeRemoteFingerprint(projectId, chatSessionId, payload) {
  const key = chatRuntimeStorageKey(projectId, chatSessionId);
  if (!key || !payload || typeof payload !== "object") return "";
  try {
    return `${key}:${JSON.stringify(payload)}`;
  } catch (_error) {
    return key;
  }
}

export function isStorageQuotaExceededError(error) {
  const name = String(error?.name || "");
  const message = String(error?.message || "");
  return (
    name === "QuotaExceededError" ||
    name === "NS_ERROR_DOM_QUOTA_REACHED" ||
    Number(error?.code) === 22 ||
    Number(error?.code) === 1014 ||
    /quota|exceeded/i.test(message)
  );
}

function truncateRuntimeStorageText(value, limit) {
  const text = String(value || "");
  const maxLength = Number(limit || 0);
  if (!maxLength || text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}\n\n[本地缓存已截断，完整内容请以服务端历史为准]`;
}

function compactRuntimeStorageRecord(value, stringLimit = 800) {
  if (!value || typeof value !== "object") {
    return truncateRuntimeStorageText(value, stringLimit);
  }
  const result = Array.isArray(value) ? [] : {};
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === "string") {
      result[key] = truncateRuntimeStorageText(item, stringLimit);
    } else if (
      typeof item === "number" ||
      typeof item === "boolean" ||
      item === null
    ) {
      result[key] = item;
    }
  }
  return result;
}

function compactRuntimeStorageRecords(rows, limit, stringLimit = 800) {
  if (!Array.isArray(rows)) return [];
  return rows
    .slice(-Number(limit || CHAT_RUNTIME_LOCAL_COMPACT_LOG_LIMIT))
    .map((item) => compactRuntimeStorageRecord(item, stringLimit));
}

function compactRuntimeMessageForLocalStorage(row, contentLimit) {
  if (!row || typeof row !== "object") return null;
  const id = String(row.id || "").trim();
  if (!id) return null;
  return {
    id,
    role: String(row.role || "assistant"),
    content: truncateRuntimeStorageText(row.content, contentLimit),
    time: String(row.time || ""),
    displayMode: String(row.displayMode || ""),
    effectiveToolTotal: Number(row.effectiveToolTotal || 0),
    processExpanded: Boolean(row.processExpanded),
    messageExecutionStartedAtEpochMs:
      Number(row.messageExecutionStartedAtEpochMs || 0) || 0,
    messageExecutionEndedAtEpochMs:
      Number(row.messageExecutionEndedAtEpochMs || 0) || 0,
    messageExecutionDurationMs:
      Number(row.messageExecutionDurationMs || 0) || 0,
    messageExecutionDurationLabel: String(
      row.messageExecutionDurationLabel || "",
    ),
    agentRuntimeStartedAtEpochMs:
      Number(row.agentRuntimeStartedAtEpochMs || 0) || 0,
    agentRuntimeLatestEventAtEpochMs:
      Number(row.agentRuntimeLatestEventAtEpochMs || 0) || 0,
    agentRuntimeEndedAtEpochMs:
      Number(row.agentRuntimeEndedAtEpochMs || 0) || 0,
    agentRuntimeDurationMs: Number(row.agentRuntimeDurationMs || 0) || 0,
    agentRuntimeDurationLabel: String(row.agentRuntimeDurationLabel || ""),
    terminalLog: compactRuntimeStorageRecords(
      row.terminalLog,
      CHAT_RUNTIME_LOCAL_COMPACT_LOG_LIMIT,
    ),
    processLog: compactRuntimeStorageRecords(
      row.processLog,
      CHAT_RUNTIME_LOCAL_COMPACT_LOG_LIMIT,
    ),
    statusNotes: compactRuntimeStorageRecords(
      row.statusNotes,
      CHAT_RUNTIME_LOCAL_COMPACT_LOG_LIMIT,
    ),
    operations: compactRuntimeStorageRecords(
      row.operations,
      CHAT_RUNTIME_LOCAL_COMPACT_OPERATION_LIMIT,
    ),
  };
}

function compactTerminalRuntimeForLocalStorage(terminal) {
  if (!terminal || typeof terminal !== "object") return null;
  return {
    panel_status: String(terminal.panel_status || "idle"),
    panel_expanded: Boolean(terminal.panel_expanded),
    panel_lines: Array.isArray(terminal.panel_lines)
      ? terminal.panel_lines
          .slice(-CHAT_RUNTIME_LOCAL_COMPACT_LOG_LIMIT)
          .map((item) => truncateRuntimeStorageText(item, 500))
      : [],
    mirror_connected: Boolean(terminal.mirror_connected),
    host_terminal_session_id: String(
      terminal.host_terminal_session_id || "",
    ).trim(),
    host_terminal_workspace_path: String(
      terminal.host_terminal_workspace_path || "",
    ).trim(),
    active_assistant_index: Number(terminal.active_assistant_index ?? -1),
    active_assistant_message_id: String(
      terminal.active_assistant_message_id || "",
    ).trim(),
  };
}

function compactNativeExternalAgentRuntimeForLocalStorage(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  return {
    session_id: String(snapshot.session_id || "").trim(),
    chat_session_id: String(snapshot.chat_session_id || "").trim(),
    message_id: String(snapshot.message_id || "").trim(),
    running: Boolean(snapshot.running),
    logs: compactRuntimeStorageRecords(
      snapshot.logs,
      CHAT_RUNTIME_LOCAL_COMPACT_LOG_LIMIT,
      500,
    ),
  };
}

function buildCompactChatRuntimePayloadForLocalStorage(
  payload,
  { messageLimit, contentLimit },
) {
  const messages = Array.isArray(payload?.messages) ? payload.messages : [];
  return {
    version: Number(payload?.version || 1),
    updated_at: String(payload?.updated_at || new Date().toISOString()),
    storage_mode: "compact_local_cache",
    // localStorage 配额很小；降级缓存只保留恢复运行态所需字段，完整消息以服务端历史为准。
    messages: messages
      .slice(-Number(messageLimit || CHAT_RUNTIME_LOCAL_COMPACT_MESSAGE_LIMIT))
      .map((row) => compactRuntimeMessageForLocalStorage(row, contentLimit))
      .filter(Boolean),
    terminal: compactTerminalRuntimeForLocalStorage(payload?.terminal),
    native_external_agent: compactNativeExternalAgentRuntimeForLocalStorage(
      payload?.native_external_agent,
    ),
    native_external_agents: Array.isArray(payload?.native_external_agents)
      ? payload.native_external_agents
          .slice(-3)
          .map(compactNativeExternalAgentRuntimeForLocalStorage)
          .filter(Boolean)
      : [],
  };
}

function pruneOtherChatRuntimeStorage(projectId, keepKey) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedKeepKey = String(keepKey || "").trim();
  if (!normalizedProjectId || typeof window === "undefined") return 0;
  const prefix = `project_chat_runtime_${normalizedProjectId}_`;
  const keys = [];
  try {
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = String(localStorage.key(index) || "").trim();
      if (key.startsWith(prefix) && key !== normalizedKeepKey) {
        keys.push(key);
      }
    }
    for (const key of keys) {
      localStorage.removeItem(key);
    }
  } catch (error) {
    console.warn("prune chat runtime storage failed", error);
  }
  return keys.length;
}

export function readPersistedChatRuntime(projectId, chatSessionId) {
  if (typeof window === "undefined") return null;
  const key = chatRuntimeStorageKey(projectId, chatSessionId);
  if (!key) return null;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

export function writePersistedChatRuntime(projectId, chatSessionId, payload) {
  if (typeof window === "undefined") return;
  const key = chatRuntimeStorageKey(projectId, chatSessionId);
  if (!key) return;
  if (!payload || typeof payload !== "object") {
    localStorage.removeItem(key);
    return;
  }
  try {
    localStorage.setItem(key, JSON.stringify(payload));
    return;
  } catch (error) {
    if (!isStorageQuotaExceededError(error)) {
      console.warn("persist chat runtime failed", error);
      return;
    }
  }

  const normalizedProjectId = String(projectId || "").trim();
  pruneOtherChatRuntimeStorage(normalizedProjectId, key);
  const compactPayloads = [
    buildCompactChatRuntimePayloadForLocalStorage(payload, {
      messageLimit: CHAT_RUNTIME_LOCAL_COMPACT_MESSAGE_LIMIT,
      contentLimit: CHAT_RUNTIME_LOCAL_COMPACT_CONTENT_LIMIT,
    }),
    buildCompactChatRuntimePayloadForLocalStorage(payload, {
      messageLimit: CHAT_RUNTIME_LOCAL_MINIMAL_MESSAGE_LIMIT,
      contentLimit: CHAT_RUNTIME_LOCAL_MINIMAL_CONTENT_LIMIT,
    }),
  ];
  for (const compactPayload of compactPayloads) {
    try {
      localStorage.setItem(key, JSON.stringify(compactPayload));
      return;
    } catch (retryError) {
      if (!isStorageQuotaExceededError(retryError)) {
        console.warn("persist compact chat runtime failed", retryError);
        return;
      }
    }
  }
  try {
    localStorage.removeItem(key);
  } catch (_error) {
    // 移除失败时只能放弃本地快照，避免把浏览器存储异常继续抛到页面。
  }
}

export function clearPersistedChatRuntime(projectId, chatSessionId = "") {
  if (typeof window === "undefined") return;
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId) return;
  if (normalizedChatSessionId) {
    const key = chatRuntimeStorageKey(
      normalizedProjectId,
      normalizedChatSessionId,
    );
    if (key) {
      localStorage.removeItem(key);
    }
    return;
  }
  const prefix = `project_chat_runtime_${normalizedProjectId}_`;
  const keys = [];
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = String(localStorage.key(index) || "").trim();
    if (key.startsWith(prefix)) {
      keys.push(key);
    }
  }
  for (const key of keys) {
    localStorage.removeItem(key);
  }
}
