import { computed, ref } from "vue";

export function useProjectChatTransport({
  onDisconnect,
} = {}) {
  const wsConnected = ref(false);
  const wsClient = ref(null);
  const wsProjectId = ref("");

  const wsStatusText = computed(() => "本地 Runtime");
  const wsStatusType = computed(() => (wsConnected.value ? "success" : "info"));

  function selectWsProject(projectId = "") {
    wsProjectId.value = String(projectId || "").trim();
    return null;
  }

  function getWsClient(projectId = wsProjectId.value) {
    return null;
  }

  function closeProjectConnection(projectId, reason = "") {
    if (wsProjectId.value !== String(projectId || "").trim()) return false;
    wsClient.value = null;
    wsConnected.value = false;
    return true;
  }

  function disconnectWs(reason = "", options = {}) {
    const projectId = String(options?.projectId || "").trim();
    if (projectId) {
      closeProjectConnection(projectId, reason);
      onDisconnect?.(reason || "本地 Runtime 已断开", projectId);
      return;
    }
    wsClient.value = null;
    wsConnected.value = false;
    wsProjectId.value = "";
    onDisconnect?.(reason || "本地 Runtime 已断开", "");
  }

  async function ensureWsClient(projectId, options = {}) {
    throw new Error("本地项目聊天不使用远程实时接口，请使用桌面端本地 Runtime");
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
    scheduleReconnect() {},
  };
}
