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
  const reconnectAttempt = ref(0);

  let reconnectTimer = null;
  let connectingPromise = null;
  let manualClose = false;

  const wsStatusText = computed(() => (wsConnected.value ? "已连接" : "未连接"));
  const wsStatusType = computed(() => (wsConnected.value ? "success" : "info"));

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function scheduleReconnect(projectId, reason = "") {
    const normalizedProjectId = String(projectId || wsProjectId.value || "").trim();
    if (!normalizedProjectId || manualClose) return;
    if (reconnectTimer !== null) return;
    const attempt = Math.min(Number(reconnectAttempt.value || 0) + 1, 5);
    reconnectAttempt.value = attempt;
    const delayMs = Math.min(30000, 1000 * 2 ** Math.max(0, attempt - 1));
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      void ensureWsClient(normalizedProjectId, { reconnect: true }).catch((err) => {
        if (attempt >= 5) {
          onUnexpectedClose?.(err?.message || reason || "WebSocket 重连失败");
          return;
        }
        scheduleReconnect(normalizedProjectId, err?.message || reason);
      });
    }, delayMs);
  }

  function disconnectWs(reason = "") {
    manualClose = true;
    clearReconnectTimer();
    if (wsClient.value) {
      wsClient.value.close(1000, reason || "client close");
    }
    wsClient.value = null;
    wsConnected.value = false;
    wsProjectId.value = "";
    reconnectAttempt.value = 0;
    connectingPromise = null;
    onDisconnect?.(reason || "连接已断开");
  }

  async function ensureWsClient(projectId, options = {}) {
    const normalizedProjectId = String(projectId || "").trim();
    if (!normalizedProjectId) {
      throw new Error("缺少项目 ID");
    }
    if (
      wsClient.value &&
      wsProjectId.value === normalizedProjectId &&
      wsClient.value.isOpen()
    ) {
      return wsClient.value;
    }
    if (connectingPromise && wsProjectId.value === normalizedProjectId) {
      return connectingPromise;
    }
    if (wsClient.value && wsProjectId.value !== normalizedProjectId) {
      disconnectWs("switch project");
    } else if (wsClient.value) {
      wsClient.value.close(1000, "replace connection");
      wsClient.value = null;
      wsConnected.value = false;
    }

    const token = getToken?.();
    if (!token) {
      throw new Error("登录状态失效，请重新登录");
    }
    manualClose = false;
    clearReconnectTimer();
    wsProjectId.value = normalizedProjectId;
    // WebSocket 的协议事件仍由页面编排层处理，这里只负责连接生命周期。
    const client = createProjectChatWsClient({
      projectId: normalizedProjectId,
      token,
      onOpen: () => {
        wsConnected.value = true;
        reconnectAttempt.value = 0;
      },
      onMessage,
      onError: () => {
        wsConnected.value = false;
      },
      onStale: (reason) => {
        wsConnected.value = false;
        onUnexpectedClose?.(reason);
      },
      onClose: (event) => {
        wsConnected.value = false;
        if (wsClient.value === client) {
          wsClient.value = null;
        }
        const code = Number(event?.code || 1000);
        if (manualClose || code === 1000) return;
        const reason = String(event?.reason || "").trim() || `连接关闭(${code})`;
        onUnexpectedClose?.(reason);
        scheduleReconnect(normalizedProjectId, reason);
      },
    });
    wsClient.value = client;
    connectingPromise = client.ready
      .then(() => {
        if (wsClient.value !== client) {
          throw new Error("WebSocket 连接已被替换");
        }
        wsConnected.value = true;
        return client;
      })
      .finally(() => {
        if (wsClient.value === client) {
          connectingPromise = null;
        }
      });
    return connectingPromise;
  }

  return {
    wsConnected,
    wsClient,
    wsProjectId,
    wsStatusText,
    wsStatusType,
    disconnectWs,
    ensureWsClient,
    scheduleReconnect,
  };
}
