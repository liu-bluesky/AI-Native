export function useProjectChatComposer(options = {}) {
  const {
    selectedProjectId,
    currentChatSessionId,
    draftText,
    uploadFiles,
    activeComposerAssist,
    singleRoundAnswerOnly,
    slashCommandHighlightIndex,
    getCacheKey,
  } = options;

  const composerCache = new Map();

  function cacheKey(projectId, chatSessionId) {
    return typeof getCacheKey === "function"
      ? getCacheKey(projectId, chatSessionId)
      : "";
  }

  function normalizeComposerUploadItem(item) {
    if (!item || typeof item !== "object") return null;
    return {
      ...item,
      name: String(item.name || item.raw?.name || "").trim(),
      kind: String(item.kind || "").trim(),
      url: String(item.url || "").trim(),
      raw: item.raw || null,
    };
  }

  function rememberChatSessionComposerState(projectId, chatSessionId, state) {
    const key = cacheKey(projectId, chatSessionId);
    if (!key || !state || typeof state !== "object") return;
    // 按会话隔离输入草稿，避免切换会话时把未发送内容串到其他对话。
    composerCache.set(key, {
      draftText: String(state.draftText || ""),
      uploadFiles: Array.isArray(state.uploadFiles)
        ? state.uploadFiles.map(normalizeComposerUploadItem).filter(Boolean)
        : [],
      activeComposerAssist: String(state.activeComposerAssist || "").trim(),
      singleRoundAnswerOnly: Boolean(state.singleRoundAnswerOnly),
    });
  }

  function rememberCurrentChatSessionComposerState() {
    const projectId = String(selectedProjectId?.value || "").trim();
    const chatSessionId = String(currentChatSessionId?.value || "").trim();
    if (!projectId || !chatSessionId) return;
    rememberChatSessionComposerState(projectId, chatSessionId, {
      draftText: draftText?.value,
      uploadFiles: uploadFiles?.value,
      activeComposerAssist: activeComposerAssist?.value,
      singleRoundAnswerOnly: singleRoundAnswerOnly?.value,
    });
  }

  function applyChatSessionComposerState(projectId, chatSessionId) {
    const key = cacheKey(projectId, chatSessionId);
    const state = key ? composerCache.get(key) : null;
    draftText.value = String(state?.draftText || "");
    uploadFiles.value = Array.isArray(state?.uploadFiles)
      ? state.uploadFiles.map(normalizeComposerUploadItem).filter(Boolean)
      : [];
    activeComposerAssist.value = String(
      state?.activeComposerAssist || "",
    ).trim();
    singleRoundAnswerOnly.value = Boolean(state?.singleRoundAnswerOnly);
    slashCommandHighlightIndex.value = 0;
  }

  function clearCurrentChatSessionComposerState() {
    const projectId = String(selectedProjectId?.value || "").trim();
    const chatSessionId = String(currentChatSessionId?.value || "").trim();
    if (!projectId || !chatSessionId) return;
    rememberChatSessionComposerState(projectId, chatSessionId, {
      draftText: "",
      uploadFiles: [],
      activeComposerAssist: activeComposerAssist?.value,
      singleRoundAnswerOnly: singleRoundAnswerOnly?.value,
    });
  }

  return {
    rememberChatSessionComposerState,
    rememberCurrentChatSessionComposerState,
    applyChatSessionComposerState,
    clearCurrentChatSessionComposerState,
  };
}
