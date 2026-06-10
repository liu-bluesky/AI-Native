import { computed } from "vue";
import { useTaskTreeHealth } from "@/modules/task-tree-feedback/useTaskTreeHealth";
import {
  isTaskTreeArchivedOrDone,
  resolveTaskTreeProgressPercent,
} from "@/modules/project-chat/mappers/taskTreeMappers.js";

export function useProjectChatTaskTreeState({
  chatTaskTree,
  selectedTaskTreeNodeId,
}) {
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
    Array.isArray(displayedChatTaskTree.value?.tree)
      ? displayedChatTaskTree.value.tree
      : [],
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
    if (!normalizedNodeId || !Array.isArray(displayedChatTaskTree.value?.nodes)) {
      return [];
    }
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
