import { reactive, ref } from "vue";

export function useProjectChatPendingRequests({ currentChatSessionId }) {
  const pendingRequests = reactive(new Map());
  const activeGenerationRequestId = ref("");

  function hasPendingRequestForChatSession(chatSessionId) {
    const normalizedSessionId = String(chatSessionId || "").trim();
    if (!normalizedSessionId) return false;
    for (const pending of pendingRequests.values()) {
      if (String(pending?.chatSessionId || "").trim() === normalizedSessionId) {
        return true;
      }
    }
    return false;
  }

  function getActiveRequestId() {
    const currentSessionId = String(currentChatSessionId?.value || "").trim();
    // 当前会话优先，避免后台会话的请求状态抢占前台停止/续写操作。
    if (currentSessionId) {
      const currentEntries = Array.from(pendingRequests.entries()).filter(
        ([, pending]) =>
          String(pending?.chatSessionId || "").trim() === currentSessionId,
      );
      if (currentEntries.length > 0) {
        return currentEntries[currentEntries.length - 1][0];
      }
    }
    const activeRequestId = String(activeGenerationRequestId.value || "").trim();
    if (
      activeRequestId &&
      pendingRequests.has(activeRequestId) &&
      !currentSessionId
    ) {
      return activeRequestId;
    }
    if (currentSessionId) return null;
    const entries = Array.from(pendingRequests.entries());
    if (entries.length > 0) {
      return entries[entries.length - 1][0];
    }
    return null;
  }

  function trackPendingRequest(requestId) {
    const normalizedRequestId = String(requestId || "").trim();
    if (normalizedRequestId) {
      activeGenerationRequestId.value = normalizedRequestId;
    }
  }

  function clearTrackedPendingRequest(requestId) {
    const normalizedRequestId = String(requestId || "").trim();
    const activeRequestId = String(activeGenerationRequestId.value || "").trim();
    if (
      normalizedRequestId &&
      activeRequestId &&
      activeRequestId !== normalizedRequestId &&
      pendingRequests.has(activeRequestId)
    ) {
      return;
    }
    activeGenerationRequestId.value = getActiveRequestId() || "";
  }

  return {
    pendingRequests,
    activeGenerationRequestId,
    hasPendingRequestForChatSession,
    getActiveRequestId,
    trackPendingRequest,
    clearTrackedPendingRequest,
  };
}
