import { computed } from "vue";
import { normalizeTaskTreeHealth } from "@/modules/task-tree-feedback/taskTreeFeedback";
import { useTaskTreeHealth } from "@/modules/task-tree-feedback/useTaskTreeHealth";

export function isTaskTreeArchivedOrDone(payload) {
  if (!payload || typeof payload !== "object") return false;
  const lifecycle = String(payload.lifecycle_status || "").trim().toLowerCase();
  const status = String(payload.status || "").trim().toLowerCase();
  return Boolean(payload.is_archived || lifecycle === "archived" || status === "done");
}

function isTaskTreeFinalized(taskTree) {
  if (!taskTree || typeof taskTree !== "object") {
    return false;
  }
  const status = String(taskTree.status || "").trim().toLowerCase();
  const progressPercent = Number(taskTree.progress_percent || 0);
  const stats = taskTree.stats && typeof taskTree.stats === "object" ? taskTree.stats : {};
  const leafTotal = Number(taskTree.leaf_total ?? stats.leaf_total ?? 0);
  const doneLeafTotal = Number(taskTree.done_leaf_total ?? stats.done_leaf_total ?? 0);
  if (Boolean(taskTree.is_archived) && status === "done") {
    return true;
  }
  if (status !== "done") {
    return false;
  }
  if (progressPercent >= 100) {
    return true;
  }
  return leafTotal > 0 && doneLeafTotal >= leafTotal;
}

export function resolveTaskTreeProgressPercent(taskTree) {
  if (!taskTree || typeof taskTree !== "object") {
    return 0;
  }
  const explicitProgress = Number(taskTree.progress_percent || 0);
  if (explicitProgress > 0) {
    return explicitProgress;
  }
  if (isTaskTreeFinalized(taskTree)) {
    return 100;
  }
  const stats = taskTree.stats && typeof taskTree.stats === "object" ? taskTree.stats : {};
  const leafTotal = Number(taskTree.leaf_total ?? stats.leaf_total ?? 0);
  const doneLeafTotal = Number(taskTree.done_leaf_total ?? stats.done_leaf_total ?? 0);
  if (leafTotal > 0 && doneLeafTotal > 0) {
    return Math.round((doneLeafTotal / leafTotal) * 100);
  }
  return 0;
}

export function normalizeTaskTreePayload(raw) {
  if (!raw || typeof raw !== "object") return null;
  const nodes = Array.isArray(raw.nodes) ? raw.nodes : [];
  const tree = Array.isArray(raw.tree) ? raw.tree : [];
  const currentNodeId = String(raw.current_node_id || "").trim();
  return {
    ...raw,
    id: String(raw.id || "").trim(),
    chat_session_id: String(raw.chat_session_id || "").trim(),
    title: String(raw.title || "").trim(),
    root_goal: String(raw.root_goal || "").trim(),
    status:
      String(raw.status || "pending")
        .trim()
        .toLowerCase() || "pending",
    current_node_id: currentNodeId,
    progress_percent: resolveTaskTreeProgressPercent(raw),
    nodes,
    tree,
    task_tree_health: normalizeTaskTreeHealth(raw.task_tree_health),
    current_node:
      raw.current_node && typeof raw.current_node === "object"
        ? raw.current_node
        : nodes.find(
            (item) => String(item?.id || "").trim() === currentNodeId,
          ) || null,
  };
}

export function useProjectChatTaskTreeState({ chatTaskTree, selectedTaskTreeNodeId }) {
  const displayedChatTaskTree = computed(() => {
    const payload =
      chatTaskTree.value && typeof chatTaskTree.value === "object"
        ? chatTaskTree.value
        : null;
    return payload;
  });

  const hasChatTaskTree = computed(() =>
    Boolean(String(displayedChatTaskTree.value?.id || "").trim()),
  );

  const taskTreeIsReadonly = computed(() => {
    return isTaskTreeArchivedOrDone(displayedChatTaskTree.value);
  });

  const taskTreeTreeData = computed(() =>
    Array.isArray(displayedChatTaskTree.value?.tree) ? displayedChatTaskTree.value.tree : [],
  );

  const taskTreeProgressLabel = computed(() => {
    if (!hasChatTaskTree.value) return "未拆解";
    return `${resolveTaskTreeProgressPercent(displayedChatTaskTree.value)}%`;
  });

  const displayedChatTaskTreeHealth = useTaskTreeHealth(
    () => displayedChatTaskTree.value?.task_tree_health || null,
  );

  const taskTreeSelectedNode = computed(() => {
    const nodeId = String(selectedTaskTreeNodeId.value || "").trim();
    if (!nodeId) return null;
    return (
      (Array.isArray(displayedChatTaskTree.value?.nodes)
        ? displayedChatTaskTree.value.nodes.find(
            (item) => String(item?.id || "").trim() === nodeId,
          )
        : null) || null
    );
  });

  function getTaskTreeChildNodes(nodeId) {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId || !Array.isArray(displayedChatTaskTree.value?.nodes)) return [];
    return displayedChatTaskTree.value.nodes.filter(
      (item) => String(item?.parent_id || "").trim() === normalizedNodeId,
    );
  }

  const taskTreeSelectedNodeChildCount = computed(
    () =>
      getTaskTreeChildNodes(String(taskTreeSelectedNode.value?.id || "").trim())
        .length,
  );

  const taskTreeVerificationPlaceholder = computed(() =>
    taskTreeSelectedNodeChildCount.value
      ? "填写父节点的整体验证结论。只有全部子任务完成后，父节点才能标记完成。"
      : "填写叶子节点的验证结果，例如测试、截图、日志或人工确认结论。",
  );

  const taskTreeSaveHint = computed(() => {
    const node = taskTreeSelectedNode.value;
    if (!node) return "请先选择一个任务节点。";
    if (taskTreeSelectedNodeChildCount.value) {
      return `当前选中的是父节点「${node.title}」。请先完成全部子任务，再补充整体验证结论。`;
    }
    return `当前选中的是叶子节点「${node.title}」。标记完成前必须填写验证结果。`;
  });

  return {
    displayedChatTaskTree,
    hasChatTaskTree,
    taskTreeIsReadonly,
    taskTreeTreeData,
    taskTreeProgressLabel,
    displayedChatTaskTreeHealth,
    taskTreeSelectedNode,
    taskTreeSelectedNodeChildCount,
    taskTreeVerificationPlaceholder,
    taskTreeSaveHint,
    getTaskTreeChildNodes,
  };
}
