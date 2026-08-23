import { ElMessage, ElMessageBox } from "element-plus";
import {
  clearTaskTreeSessionMemory,
  clearWorkSessionMemory,
  rememberTaskTreeSession,
  rememberWorkSession,
  restoreChatSession,
  readLocalTaskTreeSnapshot,
  writeLocalTaskTreeSnapshot,
  readLocalWorkSessionSnapshot,
  writeLocalWorkSessionSnapshot,
} from "@/modules/project-chat/services/projectChatStorage.js";
import {
  buildOngoingTaskRestoreNotice,
  isTaskTreeArchivedOrDone,
  normalizeTaskTreeNodeDraft,
  normalizeTaskTreePayload,
  normalizeWorkSessionSummary,
  resolveTaskTreeNodeDraft,
  validateTaskTreeNodeSave,
} from "@/modules/project-chat/mappers/taskTreeMappers.js";

export function useProjectChatTaskTreeActions({
  chatTaskTree,
  selectedTaskTreeNodeId,
  taskTreeStatusDraft,
  taskTreeVerificationDraft,
  taskTreeSummaryDraft,
  taskTreeLoading,
  taskTreeSaving,
  taskTreePanelVisible,
  currentWorkSessionId,
  ongoingTaskRestoreNotice,
  selectedProjectId,
  currentChatSessionId,
  displayedChatTaskTree,
  taskTreeIsReadonly,
  taskTreeSelectedNode,
  getTaskTreeChildNodes,
  chatLoading,
  fetchChatHistory,
}) {
  function clearOngoingTaskRestoreNotice() {
    ongoingTaskRestoreNotice.value = null;
  }

  function setOngoingTaskRestoreNotice(taskTree, workSession) {
    const notice = buildOngoingTaskRestoreNotice(taskTree, workSession);
    if (!notice) {
      clearOngoingTaskRestoreNotice();
      return;
    }
    ongoingTaskRestoreNotice.value = notice;
  }

  function applyTaskTreePayload(payload) {
    const normalized = normalizeTaskTreePayload(payload);
    chatTaskTree.value = normalized;
    const projectId = String(selectedProjectId.value || "").trim();
    const chatSessionId = String(payload?.chat_session_id || currentChatSessionId.value || "").trim();
    if (projectId && chatSessionId) {
      writeLocalTaskTreeSnapshot(projectId, chatSessionId, payload);
    }
    if (projectId) {
      if (normalized?.id && !isTaskTreeArchivedOrDone(normalized)) {
        rememberTaskTreeSession(projectId, normalized.id);
      } else if (normalized?.id && isTaskTreeArchivedOrDone(normalized)) {
        clearTaskTreeSessionMemory(projectId);
        clearWorkSessionMemory(projectId);
        currentWorkSessionId.value = "";
        clearOngoingTaskRestoreNotice();
      }
    }
    if (!normalized) {
      selectedTaskTreeNodeId.value = "";
      taskTreeStatusDraft.value = "pending";
      taskTreeVerificationDraft.value = "";
      taskTreeSummaryDraft.value = "";
      return;
    }
    const draft = resolveTaskTreeNodeDraft(
      normalized,
      selectedTaskTreeNodeId.value,
    );
    selectedTaskTreeNodeId.value = draft.selected_node_id;
    taskTreeStatusDraft.value = draft.status;
    taskTreeVerificationDraft.value = draft.verification_result;
    taskTreeSummaryDraft.value = draft.summary_for_model;
  }

  function applyWorkSessionPayload(raw, options = {}) {
    const normalized = normalizeWorkSessionSummary(raw);
    const projectId = String(
      options.projectId || selectedProjectId.value || "",
    ).trim();
    if (!projectId || !normalized?.session_id) {
      return null;
    }
    const taskTree =
      options.taskTree && typeof options.taskTree === "object"
        ? options.taskTree
        : displayedChatTaskTree.value;
    const taskTreeChatSessionId = String(
      normalized.task_tree_chat_session_id ||
        raw?.task_tree_chat_session_id ||
        raw?.chat_session_id ||
        taskTree?.chat_session_id ||
        currentChatSessionId.value ||
        "",
    ).trim();
    const localSession = {
      ...normalized,
      task_tree_chat_session_id: taskTreeChatSessionId,
      task_tree_session_id: String(
        normalized.task_tree_session_id || taskTree?.id || "",
      ).trim(),
      goal: String(
        normalized.goal || taskTree?.root_goal || taskTree?.title || "",
      ).trim(),
    };
    currentWorkSessionId.value = normalized.session_id;
    writeLocalWorkSessionSnapshot(
      projectId,
      taskTreeChatSessionId,
      localSession,
    );
    rememberWorkSession(projectId, normalized.session_id);
    const noticeSessionId = String(
      ongoingTaskRestoreNotice.value?.chat_session_id || "",
    ).trim();
    const taskChatSessionId = String(taskTree?.chat_session_id || "").trim();
    if (
      noticeSessionId &&
      taskChatSessionId &&
      noticeSessionId === taskChatSessionId
    ) {
      setOngoingTaskRestoreNotice(taskTree, localSession);
    }
    return localSession;
  }

  async function syncOngoingWorkSessionFromTaskTree(
    projectId,
    taskTree,
    options = {},
  ) {
    const normalizedProjectId = String(projectId || "").trim();
    const taskTreeChatSessionId = String(taskTree?.chat_session_id || "").trim();
    if (!normalizedProjectId || !String(taskTree?.id || "").trim()) {
      if (options.clearIfMissing !== false) {
        currentWorkSessionId.value = "";
        clearWorkSessionMemory(normalizedProjectId);
      }
      return null;
    }
    try {
      const localSession = normalizeWorkSessionSummary(
        readLocalWorkSessionSnapshot(
          normalizedProjectId,
          taskTreeChatSessionId,
        ),
      );
      if (localSession?.session_id) {
        currentWorkSessionId.value = localSession.session_id;
        rememberWorkSession(normalizedProjectId, localSession.session_id);
        return localSession;
      }
      if (options.clearIfMissing !== false) {
        currentWorkSessionId.value = "";
        clearWorkSessionMemory(normalizedProjectId);
      }
      return null;
    } catch (err) {
      if (!options.silent) {
        ElMessage.error(err?.detail || err?.message || "恢复工作轨迹失败");
      }
      return null;
    }
  }

  function syncTaskTreeDrafts(node) {
    const draft = normalizeTaskTreeNodeDraft(node || taskTreeSelectedNode.value);
    selectedTaskTreeNodeId.value = draft.selected_node_id;
    taskTreeStatusDraft.value = draft.status;
    taskTreeVerificationDraft.value = draft.verification_result;
    taskTreeSummaryDraft.value = draft.summary_for_model;
  }

  async function fetchChatTaskTree(
    projectId,
    chatSessionId = currentChatSessionId.value,
    options = {},
  ) {
    const normalizedProjectId = String(projectId || "").trim();
    const normalizedChatSessionId = String(chatSessionId || "").trim();
    if (!normalizedProjectId) {
      applyTaskTreePayload(null);
      return null;
    }
    taskTreeLoading.value = true;
    try {
      const payload = normalizeTaskTreePayload(
        readLocalTaskTreeSnapshot(
          normalizedProjectId,
          normalizedChatSessionId,
        ),
      );
      applyTaskTreePayload(payload);
      if (payload?.id && !isTaskTreeArchivedOrDone(payload)) {
        await syncOngoingWorkSessionFromTaskTree(normalizedProjectId, payload, {
          silent: true,
        });
      }
      return payload;
    } catch (err) {
      applyTaskTreePayload(null);
      if (!options.silent) {
        ElMessage.error(err?.detail || err?.message || "加载任务树失败");
      }
      return null;
    } finally {
      taskTreeLoading.value = false;
    }
  }

  async function restoreOngoingTaskFromServer(projectId, options = {}) {
    const normalizedProjectId = String(projectId || "").trim();
    currentWorkSessionId.value = "";
    if (!normalizedProjectId) {
      return null;
    }
    taskTreeLoading.value = true;
    try {
      const chatSessionId = restoreChatSession(normalizedProjectId);
      const payload = normalizeTaskTreePayload(
        readLocalTaskTreeSnapshot(normalizedProjectId, chatSessionId),
      );
      if (!payload || isTaskTreeArchivedOrDone(payload)) {
        clearOngoingTaskRestoreNotice();
        return null;
      }
      const workSession = normalizeWorkSessionSummary(
        readLocalWorkSessionSnapshot(normalizedProjectId, chatSessionId),
      );
      setOngoingTaskRestoreNotice(payload, workSession);
      return { chatSessionId, taskTree: payload, workSession };
    } catch (err) {
      if (!options.silent) {
        ElMessage.error(err?.detail || err?.message || "恢复进行中任务失败");
      }
      return null;
    } finally {
      taskTreeLoading.value = false;
    }
  }

  async function resumeOngoingTaskFromNotice() {
    const projectId = String(selectedProjectId.value || "").trim();
    const chatSessionId = String(
      ongoingTaskRestoreNotice.value?.chat_session_id || "",
    ).trim();
    if (!projectId || !chatSessionId) return;
    if (chatLoading.value) {
      ElMessage.warning("当前回答进行中，暂时不能恢复其他任务");
      return;
    }
    if (typeof fetchChatHistory === "function") {
      await fetchChatHistory(projectId, chatSessionId);
    }
    await fetchChatTaskTree(projectId, chatSessionId, { silent: true });
  }

  async function openTaskTreePanel() {
    taskTreePanelVisible.value = true;
    const projectId = String(selectedProjectId.value || "").trim();
    const chatSessionId = String(currentChatSessionId.value || "").trim();
    if (!projectId || !chatSessionId) {
      applyTaskTreePayload(null);
      return;
    }
    await fetchChatTaskTree(projectId, chatSessionId, { silent: true });
  }

  async function deleteCurrentTaskTree() {
    const projectId = String(selectedProjectId.value || "").trim();
    const chatSessionId = String(currentChatSessionId.value || "").trim();
    if (!projectId || !chatSessionId) {
      ElMessage.warning("当前没有可删除的任务推进");
      return;
    }
    try {
      await ElMessageBox.confirm(
        "删除后只会清空当前会话的任务推进，不会删除聊天记录。是否继续？",
        "删除任务推进",
        {
          confirmButtonText: "删除",
          cancelButtonText: "取消",
          type: "warning",
        },
      );
    } catch {
      return;
    }
    taskTreeSaving.value = true;
    try {
      writeLocalTaskTreeSnapshot(projectId, chatSessionId, null);
      writeLocalWorkSessionSnapshot(projectId, chatSessionId, null);
      clearTaskTreeSessionMemory(projectId);
      clearWorkSessionMemory(projectId);
      applyTaskTreePayload(null);
      ElMessage.success("当前会话的本地任务推进已删除");
    } catch (err) {
      ElMessage.error(err?.detail || err?.message || "删除任务推进失败");
    } finally {
      taskTreeSaving.value = false;
    }
  }

  async function saveTaskTreeNode({ setCurrentOnly = false } = {}) {
    if (taskTreeIsReadonly.value) {
      ElMessage.info("已归档任务树仅支持查看，不支持继续修改");
      return;
    }
    const projectId = String(selectedProjectId.value || "").trim();
    const chatSessionId = String(currentChatSessionId.value || "").trim();
    const nodeId = String(selectedTaskTreeNodeId.value || "").trim();
    if (!projectId || !chatSessionId || !nodeId) {
      ElMessage.warning("请先选择一个任务节点");
      return;
    }
    const nextStatus = String(taskTreeStatusDraft.value || "pending").trim();
    const verificationResult = String(
      taskTreeVerificationDraft.value || "",
    ).trim();
    const validationMessage = validateTaskTreeNodeSave({
      setCurrentOnly,
      nextStatus,
      verificationResult,
      childNodes: getTaskTreeChildNodes(nodeId),
    });
    if (validationMessage) {
      ElMessage.warning(validationMessage);
      return;
    }
    taskTreeSaving.value = true;
    try {
      const currentTree = chatTaskTree.value;
      const nextTree = currentTree
        ? {
            ...currentTree,
            status: nextStatus,
            current_node_id: setCurrentOnly
              ? nodeId
              : currentTree.current_node_id,
            nodes: (currentTree.nodes || []).map((node) =>
              String(node?.id || "") === nodeId
                ? {
                    ...node,
                    status: nextStatus,
                    verification_result: verificationResult,
                    summary_for_model: String(
                      taskTreeSummaryDraft.value || "",
                    ).trim(),
                  }
                : node,
            ),
          }
        : null;
      if (nextTree) {
        writeLocalTaskTreeSnapshot(projectId, chatSessionId, nextTree);
        applyTaskTreePayload(nextTree);
      }
      ElMessage.success(setCurrentOnly ? "已切换本地执行节点" : "本地任务节点已更新");
    } catch (err) {
      ElMessage.error(err?.detail || err?.message || "更新任务节点失败");
    } finally {
      taskTreeSaving.value = false;
    }
  }

  function handleTaskTreeNodeClick(node) {
    syncTaskTreeDrafts(node);
  }

  return {
    applyTaskTreePayload,
    applyWorkSessionPayload,
    clearOngoingTaskRestoreNotice,
    deleteCurrentTaskTree,
    fetchChatTaskTree,
    handleTaskTreeNodeClick,
    openTaskTreePanel,
    restoreOngoingTaskFromServer,
    resumeOngoingTaskFromNotice,
    saveTaskTreeNode,
    setOngoingTaskRestoreNotice,
    syncOngoingWorkSessionFromTaskTree,
    syncTaskTreeDrafts,
  };
}
