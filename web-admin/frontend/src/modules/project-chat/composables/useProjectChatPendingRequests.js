import { reactive, ref } from "vue";

export function useProjectChatPendingRequests({ currentChatSessionId }) {
  const pendingRequests = reactive(new Map());
  const activeGenerationRequestId = ref("");
  const DEFAULT_PENDING_TIMEOUT_MS = 120000;

  function clearPendingTimer(pending) {
    const timer = pending?.timeoutTimer ?? pending?.timeout_timer;
    if (timer !== null && timer !== undefined) {
      window.clearTimeout(timer);
    }
    if (pending && typeof pending === "object") {
      pending.timeoutTimer = null;
    }
  }

  function settlePending(pending, type, value) {
    if (!pending || pending.settled) return false;
    pending.settled = true;
    clearPendingTimer(pending);
    if (type === "resolve") {
      pending.resolve(value);
    } else {
      pending.reject(
        value instanceof Error ? value : new Error(String(value || "未知错误")),
      );
    }
    return true;
  }

  function createPendingRequest(requestId, pending, options = {}) {
    const normalizedRequestId = String(requestId || "").trim();
    if (!normalizedRequestId || !pending || typeof pending !== "object") {
      return null;
    }
    const timeoutMs = Math.max(
      0,
      Number(options.timeoutMs ?? pending.timeoutMs ?? DEFAULT_PENDING_TIMEOUT_MS),
    );
    pending.requestId = normalizedRequestId;
    pending.settled = false;
    if (timeoutMs > 0) {
      pending.timeoutTimer = window.setTimeout(() => {
        const current = pendingRequests.get(normalizedRequestId);
        if (current !== pending || pending.settled) return;
        rejectAndCleanupRequest(
          normalizedRequestId,
          pending,
          `请求超时（${Math.round(timeoutMs / 1000)}s 未收到完成事件）`,
        );
      }, timeoutMs);
    }
    pendingRequests.set(normalizedRequestId, pending);
    trackPendingRequest(normalizedRequestId);
    return pending;
  }

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

  /**
   * 清理单个 pending request 的 Map 条目和追踪状态，不处理页面 UI 副作用。
   * 返回 { chatSessionId } 供调用方自行执行会话级清理（如 clearWorkingStatus、persist 消息）。
   * @param {string} requestId
   * @param {object} pending
   * @returns {{ chatSessionId: string }}
   */
  function cleanupRequest(requestId, pending) {
    clearPendingTimer(pending);
    pendingRequests.delete(requestId);
    clearTrackedPendingRequest(requestId);
    return {
      chatSessionId: String(pending?.chatSessionId || "").trim(),
    };
  }

  /**
   * 清理单个 pending request 并 reject，不处理页面 UI 副作用。
   * @param {string} requestId
   * @param {object} pending
   * @param {Error|string} error
   * @returns {{ chatSessionId: string }}
   */
  function rejectAndCleanupRequest(requestId, pending, error) {
    const settled = settlePending(
      pending,
      "reject",
      error instanceof Error ? error : new Error(String(error || "未知错误")),
    );
    pendingRequests.delete(requestId);
    clearTrackedPendingRequest(requestId);
    return {
      chatSessionId: String(pending?.chatSessionId || "").trim(),
      settled,
    };
  }

  /**
   * 批量清理所有 pending request（reject + 删除 Map 条目 + 清除追踪），不处理页面 UI 副作用。
   * @param {string} reason
   * @returns {Array<{ requestId: string, pending: object }>} 原 pending 条目列表，供页面做消息行更新等副作用
   */
  function rejectAndCleanupAllRequests(reason) {
    const message = String(reason || "连接已断开").trim();
    const items = Array.from(pendingRequests.entries()).map(
      ([requestId, pending]) => ({ requestId, pending }),
    );
    for (const { requestId, pending } of items) {
      settlePending(pending, "reject", new Error(message));
      pendingRequests.delete(requestId);
      clearTrackedPendingRequest(requestId);
    }
    return items;
  }

  return {
    pendingRequests,
    activeGenerationRequestId,
    createPendingRequest,
    settlePending,
    hasPendingRequestForChatSession,
    getActiveRequestId,
    trackPendingRequest,
    clearTrackedPendingRequest,
    cleanupRequest,
    rejectAndCleanupRequest,
    rejectAndCleanupAllRequests,
  };
}
