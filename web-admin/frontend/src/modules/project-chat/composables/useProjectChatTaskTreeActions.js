import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteProjectChatTaskTree,
  fetchProjectChatOngoingTaskTree,
  fetchProjectChatTaskTree,
  fetchProjectChatWorkSessionsByTaskTree,
  updateProjectChatTaskTreeNode,
} from "@/modules/project-chat/services/projectChatTaskTreeApi.js";
import {
  clearTaskTreeSessionMemory,
  clearWorkSessionMemory,
  rememberTaskTreeSession,
  rememberWorkSession,
  restoreTaskTreeSession,
  restoreWorkSession,
} from "@/modules/project-chat/services/projectChatStorage.js";
import {
  buildOngoingTaskRestoreNotice,
  buildTaskTreeNodeUpdatePayload,
  isTaskTreeArchivedOrDone,
  normalizeTaskTreeNodeDraft,
  normalizeTaskTreePayload,
  normalizeWorkSessionSummary,
  resolveTaskTreeEventPayload,
  resolveTaskTreeNodeDraft,
  validateTaskTreeNodeSave,
} from "@/modules/project-chat/mappers/taskTreeMappers.js";

function createFallbackWorkSessionSummary(taskTree, chatSessionId, sessionId) {
  const normalizedSessionId = String(sessionId || "").trim();
  if (!normalizedSessionId) {
    return null;
  }
  return {
    session_id: normalizedSessionId,
    latest_status: "",
    goal: "",
    task_tree_session_id: String(taskTree?.id || "").trim(),
    task_tree_chat_session_id: String(chatSessionId || "").trim(),
    task_node_title: String(taskTree?.current_node?.title || "").trim(),
    updated_at: String(taskTree?.updated_at || taskTree?.created_at || "").trim(),
    created_at: String(taskTree?.created_at || "").trim(),
    phases: [],
    steps: [],
  };
}

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
    currentWorkSessionId.value = normalized.session_id;
    rememberWorkSession(projectId, normalized.session_id);
    const taskTree =
      options.taskTree && typeof options.taskTree === "object"
        ? options.taskTree
        : displayedChatTaskTree.value;
    const noticeSessionId = String(
      ongoingTaskRestoreNotice.value?.chat_session_id || "",
    ).trim();
    const taskChatSessionId = String(taskTree?.chat_session_id || "").trim();
    if (
      noticeSessionId &&
      taskChatSessionId &&
      noticeSessionId === taskChatSessionId
    ) {
      setOngoingTaskRestoreNotice(taskTree, normalized);
    }
    return normalized;
  }

  async function syncOngoingWorkSessionFromTaskTree(
    projectId,
    taskTree,
    options = {},
  ) {
    const normalizedProjectId = String(projectId || "").trim();
    const taskTreeSessionId = String(taskTree?.id || "").trim();
    const taskTreeChatSessionId = String(taskTree?.chat_session_id || "").trim();
    if (!normalizedProjectId || !taskTreeSessionId) {
      if (options.clearIfMissing !== false) {
        currentWorkSessionId.value = "";
        clearWorkSessionMemory(normalizedProjectId);
      }
      return null;
    }
    try {
      const data = await fetchProjectChatWorkSessionsByTaskTree(
        normalizedProjectId,
        {
          taskTreeSessionId,
          taskTreeChatSessionId,
          limit: 1,
        },
      );
      const workSession = normalizeWorkSessionSummary(data?.items?.[0]);
      if (workSession?.session_id) {
        currentWorkSessionId.value = workSession.session_id;
        rememberWorkSession(normalizedProjectId, workSession.session_id);
        return workSession;
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
      const params = {};
      if (normalizedChatSessionId) {
        params.chat_session_id = normalizedChatSessionId;
      }
      const data = await fetchProjectChatTaskTree(normalizedProjectId, params);
      const payload = normalizeTaskTreePayload(data?.task_tree);
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
      const ongoing = await fetchProjectChatOngoingTaskTree(normalizedProjectId);
      const ongoingTaskTree = normalizeTaskTreePayload(ongoing?.task_tree);
      const ongoingChatSessionId = String(
        ongoing?.chat_session_id || ongoingTaskTree?.chat_session_id || "",
      ).trim();
      if (
        ongoing?.can_continue &&
        ongoingTaskTree?.id &&
        ongoingChatSessionId &&
        !isTaskTreeArchivedOrDone(ongoingTaskTree)
      ) {
        const ongoingSessionId = String(
          ongoing?.session_id || ongoing?.work_session?.session_id || "",
        ).trim();
        const workSession =
          normalizeWorkSessionSummary(ongoing?.work_session) ||
          createFallbackWorkSessionSummary(
            ongoingTaskTree,
            ongoingChatSessionId,
            ongoingSessionId,
          );
        setOngoingTaskRestoreNotice(ongoingTaskTree, workSession);
        return {
          chatSessionId: ongoingChatSessionId,
          taskTree: ongoingTaskTree,
          workSession,
        };
      }

      // 远端没有 ongoing 记录时，只使用本项目记住的 task_tree_session_id 兜回当前任务。
      const taskSessionId = restoreTaskTreeSession(normalizedProjectId);
      if (!taskSessionId) {
        return null;
      }
      const data = await fetchProjectChatTaskTree(normalizedProjectId, {
        session_id: taskSessionId,
      });
      const payload = normalizeTaskTreePayload(data?.task_tree);
      if (!payload?.id || isTaskTreeArchivedOrDone(payload)) {
        clearTaskTreeSessionMemory(normalizedProjectId);
        clearWorkSessionMemory(normalizedProjectId);
        currentWorkSessionId.value = "";
        return null;
      }
      const chatSessionId = String(payload.chat_session_id || "").trim();
      if (!chatSessionId) {
        clearTaskTreeSessionMemory(normalizedProjectId);
        clearWorkSessionMemory(normalizedProjectId);
        currentWorkSessionId.value = "";
        return null;
      }
      const workSession = createFallbackWorkSessionSummary(
        payload,
        chatSessionId,
        restoreWorkSession(normalizedProjectId),
      );
      setOngoingTaskRestoreNotice(payload, workSession);
      return {
        chatSessionId,
        taskTree: payload,
        workSession,
      };
    } catch (err) {
      if (Number(err?.status || 0) === 404) {
        clearTaskTreeSessionMemory(normalizedProjectId);
        clearWorkSessionMemory(normalizedProjectId);
        currentWorkSessionId.value = "";
      }
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
      await deleteProjectChatTaskTree(projectId, chatSessionId);
      applyTaskTreePayload(null);
      ElMessage.success("当前会话的任务推进已删除");
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
      const payload = buildTaskTreeNodeUpdatePayload({
        chatSessionId,
        setCurrentOnly,
        status: nextStatus,
        verificationResult,
        summaryForModel: taskTreeSummaryDraft.value,
      });
      const data = await updateProjectChatTaskTreeNode(
        projectId,
        nodeId,
        payload,
      );
      applyTaskTreePayload(resolveTaskTreeEventPayload(data));
      ElMessage.success(setCurrentOnly ? "已切换当前执行节点" : "任务节点已更新");
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
