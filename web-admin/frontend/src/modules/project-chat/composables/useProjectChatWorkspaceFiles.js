import { computed, ref } from "vue";

/**
 * 管理工作区文件树、文件内容、diff 预览和路径配置的状态。
 * API 调用已迁入 `services/projectChatWorkspaceApi.js`，本 composable 只持有状态。
 */
export function useProjectChatWorkspaceFiles() {
  // --- 工作区文件树 ---
  const workspaceFileTreeLoading = ref(false);
  const workspaceFileTreePath = ref("");
  const workspaceFileItems = ref([]);

  // --- 文件内容 ---
  const workspaceFileLoading = ref(false);
  const workspaceFileSaving = ref(false);
  const activeWorkspaceFilePath = ref("");
  const workspaceFileDraft = ref("");
  const workspaceFileOriginal = ref("");

  // --- diff 预览 ---
  const workspaceDiffLoading = ref(false);
  const workspaceDiffPreview = ref(null);

  // --- 工作区路径配置 ---
  const workspacePathDraft = ref("");
  const workspacePathPicking = ref(false);
  const workspacePathSaving = ref(false);
  const workspacePathTesting = ref(false);

  // --- 简单计算属性 ---
  const workspacePathDraftNormalized = computed(() =>
    String(workspacePathDraft.value || "").trim(),
  );

  function resetWorkspaceFilePanel() {
    workspaceFileTreePath.value = "";
    workspaceFileItems.value = [];
    activeWorkspaceFilePath.value = "";
    workspaceFileDraft.value = "";
    workspaceFileOriginal.value = "";
    workspaceDiffPreview.value = null;
  }

  return {
    // 文件树
    workspaceFileTreeLoading,
    workspaceFileTreePath,
    workspaceFileItems,
    // 文件内容
    workspaceFileLoading,
    workspaceFileSaving,
    activeWorkspaceFilePath,
    workspaceFileDraft,
    workspaceFileOriginal,
    // diff
    workspaceDiffLoading,
    workspaceDiffPreview,
    // 路径配置
    workspacePathDraft,
    workspacePathPicking,
    workspacePathSaving,
    workspacePathTesting,
    workspacePathDraftNormalized,
    resetWorkspaceFilePanel,
  };
}
