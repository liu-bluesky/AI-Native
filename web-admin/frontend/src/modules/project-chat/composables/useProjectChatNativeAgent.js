import { reactive, ref } from "vue";
import {
  normalizeNativeExternalAgentSessionId,
  isLiveNativeExternalAgentStatus,
} from "@/modules/project-chat/mappers/nativeAgentMappers.js";

/**
 * 管理 native external agent 的会话绑定、启动/后台标记和跨会话查找。
 * 页面层负责 UI 编排和终端交互，本 composable 只承担状态与缓存逻辑。
 */
export function useProjectChatNativeAgent() {
  const nativeExternalAgentLaunchingChatSessionIds = ref(new Set());
  const nativeExternalAgentBackgroundedChatSessionIds = ref(new Set());
  const nativeExternalAgentPersistedSessions = ref(new Set());
  const nativeExternalAgentFinalizedSessionIds = new Set();
  const nativeExternalAgentFastKilledSessionIds = new Set();
  const nativeExternalAgentCancelledSessionIds = new Set();
  const nativeExternalAgentDeferredCleanupTimers = new Map();

  // 当前主会话状态
  const nativeExternalAgentSession = ref(null);
  const nativeExternalAgentSessionLogs = ref([]);
  const nativeExternalAgentMessageId = ref("");
  const nativeExternalAgentChatSessionId = ref("");

  // 多会话映射
  const nativeExternalAgentSessionsById = reactive(new Map());
  const nativeExternalAgentSessionLogsById = reactive(new Map());
  const nativeExternalAgentRunnerSessionByChatSessionId = reactive(new Map());
  const nativeExternalAgentChatSessionByRunnerSessionId = reactive(new Map());
  const nativeExternalAgentMessageByRunnerSessionId = reactive(new Map());

  // ---- session 标记操作 ----

  /** 标记某个 chatSession 是否正在启动 external agent，并同步运行标记。 */
  function setNativeExternalAgentLaunching(chatSessionId, launching) {
    const normalizedChatSessionId = String(chatSessionId || "").trim();
    if (!normalizedChatSessionId) return;
    const next = new Set(nativeExternalAgentLaunchingChatSessionIds.value);
    if (launching) {
      next.add(normalizedChatSessionId);
    } else {
      next.delete(normalizedChatSessionId);
    }
    nativeExternalAgentLaunchingChatSessionIds.value = next;
  }

  /** 标记某个 chatSession 的 external agent 是否已退到后台。 */
  function setNativeExternalAgentBackgrounded(chatSessionId, backgrounded) {
    const normalizedChatSessionId = String(chatSessionId || "").trim();
    if (!normalizedChatSessionId) return;
    const next = new Set(nativeExternalAgentBackgroundedChatSessionIds.value);
    if (backgrounded) {
      next.add(normalizedChatSessionId);
    } else {
      next.delete(normalizedChatSessionId);
    }
    nativeExternalAgentBackgroundedChatSessionIds.value = next;
  }

  // ---- 跨会话映射 ----

  function rememberNativeExternalAgentSessionBinding({
    sessionId = "",
    chatSessionId = "",
    messageId = "",
  } = {}) {
    const normalizedSessionId = String(sessionId || "").trim();
    if (!normalizedSessionId) return;
    const normalizedChatSessionId = String(chatSessionId || "").trim();
    const normalizedMessageId = String(messageId || "").trim();
    if (normalizedChatSessionId) {
      nativeExternalAgentChatSessionByRunnerSessionId.set(
        normalizedSessionId,
        normalizedChatSessionId,
      );
      nativeExternalAgentRunnerSessionByChatSessionId.set(
        normalizedChatSessionId,
        normalizedSessionId,
      );
    }
    if (normalizedMessageId) {
      nativeExternalAgentMessageByRunnerSessionId.set(
        normalizedSessionId,
        normalizedMessageId,
      );
    }
  }

  function getNativeExternalAgentRunnerSessionIdForChatSession(chatSessionId) {
    const normalizedChatSessionId = String(chatSessionId || "").trim();
    if (!normalizedChatSessionId) return "";
    const mapped = String(
      nativeExternalAgentRunnerSessionByChatSessionId.get(
        normalizedChatSessionId,
      ) || "",
    ).trim();
    if (mapped) return mapped;
    if (
      String(nativeExternalAgentChatSessionId.value || "").trim() ===
      normalizedChatSessionId
    ) {
      return normalizeNativeExternalAgentSessionId(
        nativeExternalAgentSession.value,
      );
    }
    return "";
  }

  function getNativeExternalAgentChatSessionIdForRunnerSession(sessionId) {
    const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
    if (!normalizedSessionId) return "";
    const mapped = String(
      nativeExternalAgentChatSessionByRunnerSessionId.get(normalizedSessionId) ||
        "",
    ).trim();
    if (mapped) return mapped;
    if (
      normalizeNativeExternalAgentSessionId(nativeExternalAgentSession.value) ===
      normalizedSessionId
    ) {
      return String(nativeExternalAgentChatSessionId.value || "").trim();
    }
    return "";
  }

  function getNativeExternalAgentMessageIdForRunnerSession(sessionId) {
    const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
    if (!normalizedSessionId) return "";
    const mapped = String(
      nativeExternalAgentMessageByRunnerSessionId.get(normalizedSessionId) || "",
    ).trim();
    if (mapped) return mapped;
    if (
      normalizeNativeExternalAgentSessionId(nativeExternalAgentSession.value) ===
      normalizedSessionId
    ) {
      return String(nativeExternalAgentMessageId.value || "").trim();
    }
    return "";
  }

  function clearActiveNativeExternalAgentSessionBinding(
    sessionId = "",
    chatSessionId = "",
  ) {
    const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
    const normalizedChatSessionId = String(
      chatSessionId ||
        getNativeExternalAgentChatSessionIdForRunnerSession(
          normalizedSessionId,
        ) ||
        "",
    ).trim();
    if (!normalizedSessionId || !normalizedChatSessionId) return;
    const mappedSessionId = normalizeNativeExternalAgentSessionId(
      nativeExternalAgentRunnerSessionByChatSessionId.get(
        normalizedChatSessionId,
      ),
    );
    if (mappedSessionId === normalizedSessionId) {
      nativeExternalAgentRunnerSessionByChatSessionId.delete(
        normalizedChatSessionId,
      );
    }
    if (
      String(nativeExternalAgentChatSessionId.value || "").trim() ===
        normalizedChatSessionId &&
      normalizeNativeExternalAgentSessionId(nativeExternalAgentSession.value) ===
        normalizedSessionId
    ) {
      nativeExternalAgentChatSessionId.value = "";
      nativeExternalAgentMessageId.value = "";
    }
    nativeExternalAgentChatSessionByRunnerSessionId.delete(normalizedSessionId);
    nativeExternalAgentMessageByRunnerSessionId.delete(normalizedSessionId);
    nativeExternalAgentSessionsById.delete(normalizedSessionId);
    nativeExternalAgentSessionLogsById.delete(normalizedSessionId);
    nativeExternalAgentBackgroundedChatSessionIds.value = new Set(
      Array.from(
        nativeExternalAgentBackgroundedChatSessionIds.value,
      ).filter((id) => id !== normalizedChatSessionId),
    );
  }

  /**
   * 根据当前 chatSessionId 计算 nativeExternalAgentRunning 标记。
   * 页面负责将此结果赋值给 `nativeExternalAgentRunning.value`。
   */
  function computeRunningFlag(currentChatSessionIdValue) {
    const normalizedChatSessionId = String(currentChatSessionIdValue || "").trim();
    if (!normalizedChatSessionId) return false;
    const runnerSessionId =
      getNativeExternalAgentRunnerSessionIdForChatSession(normalizedChatSessionId);
    const snapshot = runnerSessionId
      ? nativeExternalAgentSessionsById.get(runnerSessionId)
      : null;
    const isBackgrounded =
      nativeExternalAgentBackgroundedChatSessionIds.value.has(normalizedChatSessionId);
    return (
      !isBackgrounded &&
      (isLiveNativeExternalAgentStatus(snapshot?.status) ||
        nativeExternalAgentLaunchingChatSessionIds.value.has(normalizedChatSessionId) ||
        (String(nativeExternalAgentChatSessionId.value || "").trim() ===
          normalizedChatSessionId &&
          isLiveNativeExternalAgentStatus(
            nativeExternalAgentSession.value?.status,
          )))
    );
  }

  /**
   * 同步 native external agent 会话面板：根据 currentChatSessionId + selectedRecordId
   * 选择当前活跃 session，回填 session/logs/messageId/chatSessionId。
   * 页面负责传入 selectedNativeExternalAgentRecordId 和调用后续 syncRunningFlag。
   */
  function syncSessionPanel(currentChatSessionIdValue, selectedRecordId = "", preferredSessionId = "") {
    const normalizedPreferredSessionId = normalizeNativeExternalAgentSessionId(preferredSessionId);
    const currentRunnerSessionId = getNativeExternalAgentRunnerSessionIdForChatSession(
      String(currentChatSessionIdValue || "").trim(),
    );
    const normalizedRecordId = String(selectedRecordId || "").trim();
    const sessionId =
      normalizedPreferredSessionId ||
      currentRunnerSessionId ||
      (normalizedRecordId && nativeExternalAgentSessionsById.has(normalizedRecordId)
        ? normalizedRecordId
        : "");
    if (!sessionId) {
      nativeExternalAgentSession.value = null;
      nativeExternalAgentSessionLogs.value = [];
      nativeExternalAgentMessageId.value = "";
      nativeExternalAgentChatSessionId.value = "";
      return;
    }
    const snapshot = nativeExternalAgentSessionsById.get(sessionId) || null;
    nativeExternalAgentSession.value = snapshot;
    nativeExternalAgentSessionLogs.value = Array.isArray(
      nativeExternalAgentSessionLogsById.get(sessionId),
    )
      ? nativeExternalAgentSessionLogsById.get(sessionId)
      : [];
    nativeExternalAgentMessageId.value =
      getNativeExternalAgentMessageIdForRunnerSession(sessionId);
    nativeExternalAgentChatSessionId.value =
      getNativeExternalAgentChatSessionIdForRunnerSession(sessionId);
  }

  return {
    // 状态
    nativeExternalAgentSession,
    nativeExternalAgentSessionLogs,
    nativeExternalAgentMessageId,
    nativeExternalAgentChatSessionId,
    nativeExternalAgentSessionsById,
    nativeExternalAgentSessionLogsById,
    nativeExternalAgentRunnerSessionByChatSessionId,
    nativeExternalAgentChatSessionByRunnerSessionId,
    nativeExternalAgentMessageByRunnerSessionId,
    nativeExternalAgentLaunchingChatSessionIds,
    nativeExternalAgentBackgroundedChatSessionIds,
    nativeExternalAgentPersistedSessions,
    nativeExternalAgentFinalizedSessionIds,
    nativeExternalAgentFastKilledSessionIds,
    nativeExternalAgentCancelledSessionIds,
    nativeExternalAgentDeferredCleanupTimers,
    // 操作
    computeRunningFlag,
    syncSessionPanel,
    setNativeExternalAgentLaunching,
    setNativeExternalAgentBackgrounded,
    rememberNativeExternalAgentSessionBinding,
    getNativeExternalAgentRunnerSessionIdForChatSession,
    getNativeExternalAgentChatSessionIdForRunnerSession,
    getNativeExternalAgentMessageIdForRunnerSession,
    clearAgentSessionBinding: clearActiveNativeExternalAgentSessionBinding,
  };
}
