import { computed, ref } from "vue";

import { createProjectChatWsClient } from "@/utils/ws-chat.js";

export function useProjectChatTransport({
  getToken,
  onMessage,
  onDisconnect,
  onUnexpectedClose,
} = {}) {
  const wsConnected = ref(false);
  const wsClient = ref(null);
  const wsProjectId = ref("");
  const connections = new Map();

  const wsStatusText = computed(() => (wsConnected.value ? "已连接" : "未连接"));
  const wsStatusType = computed(() => (wsConnected.value ? "success" : "info"));

  function syncActiveConnection(projectId = wsProjectId.value) {
    const normalizedProjectId = String(projectId || "").trim();
    wsProjectId.value = normalizedProjectId;
    const entry = normalizedProjectId ? connections.get(normalizedProjectId) : null;
    wsClient.value = entry?.client || null;
    wsConnected.value = Boolean(entry?.connected && entry?.client?.isOpen?.());
    return entry || null;
  }

  function selectWsProject(projectId = "") {
    return syncActiveConnection(projectId);
  }

  function getWsClient(projectId = wsProjectId.value) {
    const normalizedProjectId = String(projectId || "").trim();
    return normalizedProjectId ? connections.get(normalizedProjectId)?.client || null : null;
  }

  function clearReconnectTimer(entry) {
    if (!entry || entry.reconnectTimer === null) return;
    window.clearTimeout(entry.reconnectTimer);
    entry.reconnectTimer = null;
  }

  function scheduleReconnect(projectId, reason = "") {
    const normalizedProjectId = String(projectId || "").trim();
    const entry = connections.get(normalizedProjectId);
    if (!normalizedProjectId || !entry || entry.manualClose) return;
    if (entry.reconnectTimer !== null) return;
    const attempt = Math.min(Number(entry.reconnectAttempt || 0) + 1, 5);
    entry.reconnectAttempt = attempt;
    const delayMs = Math.min(30000, 1000 * 2 ** Math.max(0, attempt - 1));
    entry.reconnectTimer = window.setTimeout(() => {
      entry.reconnectTimer = null;
      void ensureWsClient(normalizedProjectId, { reconnect: true }).catch((err) => {
        if (attempt >= 5) {
          onUnexpectedClose?.(
            err?.message || reason || "项目聊天实时连接重连失败",
            normalizedProjectId,
          );
          return;
        }
        scheduleReconnect(normalizedProjectId, err?.message || reason);
      });
    }, delayMs);
  }

  function closeProjectConnection(projectId, reason = "") {
    const normalizedProjectId = String(projectId || "").trim();
    const entry = connections.get(normalizedProjectId);
    if (!entry) return false;
    entry.manualClose = true;
    entry.generation += 1;
    clearReconnectTimer(entry);
    entry.client?.close(1000, reason || "client close");
    connections.delete(normalizedProjectId);
    if (wsProjectId.value === normalizedProjectId) {
      syncActiveConnection(normalizedProjectId);
    }
    return true;
  }

  function disconnectWs(reason = "", options = {}) {
    const projectId = String(options?.projectId || "").trim();
    if (projectId) {
      closeProjectConnection(projectId, reason);
      onDisconnect?.(reason || "连接已断开", projectId);
      return;
    }
    const projectIds = Array.from(connections.keys());
    for (const activeProjectId of projectIds) {
      closeProjectConnection(activeProjectId, reason);
    }
    wsClient.value = null;
    wsConnected.value = false;
    wsProjectId.value = "";
    onDisconnect?.(reason || "连接已断开", "");
  }

  async function ensureWsClient(projectId, options = {}) {
    const normalizedProjectId = String(projectId || "").trim();
    if (!normalizedProjectId) {
      throw new Error("缺少项目 ID");
    }
    const shouldForceReconnect = Boolean(options?.forceReconnect);
    let entry = connections.get(normalizedProjectId);
    if (shouldForceReconnect && entry) {
      closeProjectConnection(normalizedProjectId, "replace connection");
      entry = null;
    }
    if (entry?.client?.isOpen?.()) {
      syncActiveConnection(normalizedProjectId);
      return entry.client;
    }
    if (entry?.connectingPromise) {
      syncActiveConnection(normalizedProjectId);
      return entry.connectingPromise;
    }

    const token = getToken?.();
    if (!token) {
      throw new Error("登录状态失效，请重新登录");
    }
    if (!entry) {
      entry = {
        client: null,
        connected: false,
        reconnectAttempt: 0,
        reconnectTimer: null,
        connectingPromise: null,
        generation: 0,
        manualClose: false,
      };
      connections.set(normalizedProjectId, entry);
    }
    entry.manualClose = false;
    clearReconnectTimer(entry);
    const generation = entry.generation + 1;
    entry.generation = generation;
    const client = createProjectChatWsClient({
      projectId: normalizedProjectId,
      token,
      onOpen: () => {
        if (entry.generation !== generation) return;
        entry.connected = true;
        entry.reconnectAttempt = 0;
        if (wsProjectId.value === normalizedProjectId) {
          syncActiveConnection(normalizedProjectId);
        }
      },
      onMessage: (eventData) => onMessage?.(eventData, normalizedProjectId),
      onError: () => {
        if (entry.generation !== generation) return;
        entry.connected = false;
        if (wsProjectId.value === normalizedProjectId) {
          syncActiveConnection(normalizedProjectId);
        }
      },
      onStale: (reason) => {
        if (entry.generation !== generation) return;
        entry.connected = false;
        if (wsProjectId.value === normalizedProjectId) {
          syncActiveConnection(normalizedProjectId);
        }
        onUnexpectedClose?.(reason, normalizedProjectId);
      },
      onClose: (event) => {
        if (entry.generation !== generation) return;
        entry.connected = false;
        if (entry.client === client) {
          entry.client = null;
        }
        if (wsProjectId.value === normalizedProjectId) {
          syncActiveConnection(normalizedProjectId);
        }
        const code = Number(event?.code || 1000);
        if (entry.manualClose || code === 1000) return;
        const closeReason =
          String(event?.reason || "").trim() ||
          `项目聊天实时连接关闭(${code})`;
        onUnexpectedClose?.(closeReason, normalizedProjectId);
        scheduleReconnect(normalizedProjectId, closeReason);
      },
    });
    entry.client = client;
    syncActiveConnection(normalizedProjectId);
    entry.connectingPromise = client.ready
      .then(() => {
        if (entry.generation !== generation || entry.client !== client) {
          throw new Error("WebSocket 连接已被替换");
        }
        entry.connected = true;
        if (wsProjectId.value === normalizedProjectId) {
          syncActiveConnection(normalizedProjectId);
        }
        return client;
      })
      .finally(() => {
        if (entry.client === client) {
          entry.connectingPromise = null;
        }
      });
    return entry.connectingPromise;
  }

  return {
    wsConnected,
    wsClient,
    wsProjectId,
    wsStatusText,
    wsStatusType,
    selectWsProject,
    getWsClient,
    disconnectWs,
    ensureWsClient,
    scheduleReconnect,
  };
}
