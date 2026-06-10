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

  const wsStatusText = computed(() => (wsConnected.value ? "已连接" : "未连接"));
  const wsStatusType = computed(() => (wsConnected.value ? "success" : "info"));

  function disconnectWs(reason = "") {
    if (wsClient.value) {
      wsClient.value.close(1000, reason || "client close");
    }
    wsClient.value = null;
    wsConnected.value = false;
    wsProjectId.value = "";
    onDisconnect?.(reason || "连接已断开");
  }

  async function ensureWsClient(projectId) {
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
    disconnectWs("switch project");

    const token = getToken?.();
    if (!token) {
      throw new Error("登录状态失效，请重新登录");
    }
    wsProjectId.value = normalizedProjectId;
    // WebSocket 的协议事件仍由页面编排层处理，这里只负责连接生命周期。
    const client = createProjectChatWsClient({
      projectId: normalizedProjectId,
      token,
      onOpen: () => {
        wsConnected.value = true;
      },
      onMessage,
      onError: () => {
        wsConnected.value = false;
      },
      onClose: (event) => {
        wsConnected.value = false;
        wsClient.value = null;
        const code = Number(event?.code || 1000);
        if (code === 1000) return;
        const reason = String(event?.reason || "").trim() || `连接关闭(${code})`;
        onUnexpectedClose?.(reason);
      },
    });
    wsClient.value = client;
    await client.ready;
    wsConnected.value = true;
    return client;
  }

  return {
    wsConnected,
    wsClient,
    wsProjectId,
    wsStatusText,
    wsStatusType,
    disconnectWs,
    ensureWsClient,
  };
}
