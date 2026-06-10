import { normalizeTaskTreeHealth } from "@/modules/task-tree-feedback/taskTreeFeedback";

export function isTaskTreeArchivedOrDone(payload) {
  if (!payload || typeof payload !== "object") return false;
  const lifecycle = String(payload.lifecycle_status || "").trim().toLowerCase();
  const status = String(payload.status || "").trim().toLowerCase();
  return Boolean(
    payload.is_archived || lifecycle === "archived" || status === "done",
  );
}

function isTaskTreeFinalized(taskTree) {
  if (!taskTree || typeof taskTree !== "object") {
    return false;
  }
  const status = String(taskTree.status || "").trim().toLowerCase();
  const progressPercent = Number(taskTree.progress_percent || 0);
  const stats =
    taskTree.stats && typeof taskTree.stats === "object" ? taskTree.stats : {};
  const leafTotal = Number(taskTree.leaf_total ?? stats.leaf_total ?? 0);
  const doneLeafTotal = Number(
    taskTree.done_leaf_total ?? stats.done_leaf_total ?? 0,
  );
  // 任务树归档链路可能只回填 done 状态，进度需要从叶子节点统计兜正。
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
  const stats =
    taskTree.stats && typeof taskTree.stats === "object" ? taskTree.stats : {};
  const leafTotal = Number(taskTree.leaf_total ?? stats.leaf_total ?? 0);
  const doneLeafTotal = Number(
    taskTree.done_leaf_total ?? stats.done_leaf_total ?? 0,
  );
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

export function normalizeWorkSessionSummary(raw) {
  if (!raw || typeof raw !== "object") return null;
  const sessionId = String(raw.session_id || "").trim();
  if (!sessionId) return null;
  return {
    session_id: sessionId,
    latest_status: String(raw.latest_status || "")
      .trim()
      .toLowerCase(),
    goal: String(raw.goal || "").trim(),
    task_tree_session_id: String(raw.task_tree_session_id || "").trim(),
    task_tree_chat_session_id: String(
      raw.task_tree_chat_session_id || "",
    ).trim(),
    task_node_title: String(raw.task_node_title || "").trim(),
    updated_at: String(raw.updated_at || "").trim(),
    created_at: String(raw.created_at || "").trim(),
    phases: Array.isArray(raw.phases)
      ? raw.phases.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    steps: Array.isArray(raw.steps)
      ? raw.steps.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
  };
}

export function buildOngoingTaskRestoreNotice(taskTree, workSession) {
  const chatSessionId = String(taskTree?.chat_session_id || "").trim();
  if (!chatSessionId) return null;
  // 恢复提示只依赖任务树和工作轨迹快照，避免页面重复拼字段。
  return {
    chat_session_id: chatSessionId,
    task_tree_session_id: String(taskTree?.id || "").trim(),
    work_session_id: String(workSession?.session_id || "").trim(),
    title:
      String(taskTree?.title || taskTree?.root_goal || "").trim() ||
      "已恢复进行中的任务",
    current_node_title: String(
      taskTree?.current_node?.title || taskTree?.root_goal || "",
    ).trim(),
    updated_at: String(
      workSession?.updated_at ||
        taskTree?.updated_at ||
        taskTree?.created_at ||
        "",
    ).trim(),
    latest_status: String(workSession?.latest_status || "").trim(),
  };
}

export function normalizeTaskTreeNodeDraft(node) {
  const targetNode = node && typeof node === "object" ? node : null;
  return {
    selected_node_id: String(targetNode?.id || "").trim(),
    status: String(targetNode?.status || "pending").trim(),
    verification_result: String(targetNode?.verification_result || "").trim(),
    summary_for_model: String(targetNode?.summary_for_model || "").trim(),
  };
}

export function resolveTaskTreeNodeDraft(taskTree, preferredNodeId = "") {
  const source = taskTree && typeof taskTree === "object" ? taskTree : null;
  if (!source) return normalizeTaskTreeNodeDraft(null);
  const nodes = Array.isArray(source.nodes) ? source.nodes : [];
  const nextNodeId =
    String(preferredNodeId || "").trim() ||
    String(source.current_node_id || "").trim() ||
    String(nodes?.[0]?.id || "").trim();
  const targetNode =
    nodes.find((item) => String(item?.id || "").trim() === nextNodeId) ||
    source.current_node ||
    nodes?.[0] ||
    null;
  return normalizeTaskTreeNodeDraft(targetNode);
}

export function validateTaskTreeNodeSave({
  setCurrentOnly = false,
  nextStatus = "pending",
  verificationResult = "",
  childNodes = [],
} = {}) {
  if (setCurrentOnly || String(nextStatus || "").trim() !== "done") {
    return "";
  }
  const children = Array.isArray(childNodes) ? childNodes : [];
  if (
    children.length &&
    children.some((item) => String(item?.status || "").trim() !== "done")
  ) {
    return "父节点下还有未完成的子任务，不能直接标记完成";
  }
  if (!String(verificationResult || "").trim()) {
    return children.length
      ? "父节点完成前必须填写整体验证结果"
      : "叶子节点完成前必须填写验证结果";
  }
  return "";
}

export function buildTaskTreeNodeUpdatePayload({
  chatSessionId = "",
  setCurrentOnly = false,
  status = "pending",
  verificationResult = "",
  summaryForModel = "",
} = {}) {
  const payload = {
    chat_session_id: String(chatSessionId || "").trim(),
    is_current: true,
  };
  if (!setCurrentOnly) {
    // 节点保存 payload 在 mapper 层统一清洗，页面只负责调用 API。
    payload.status = String(status || "pending").trim();
    payload.verification_result = String(verificationResult || "").trim();
    payload.summary_for_model = String(summaryForModel || "").trim();
  }
  return payload;
}

export function resolveTaskTreeEventPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return payload ?? null;
  }
  if (payload.task_tree && typeof payload.task_tree === "object") {
    return payload.task_tree;
  }
  if (
    payload.history_task_tree &&
    typeof payload.history_task_tree === "object"
  ) {
    return payload.history_task_tree;
  }
  // 后端显式返回空 task_tree/history_task_tree 时，页面要清掉当前任务树状态。
  if (
    Object.prototype.hasOwnProperty.call(payload, "task_tree") ||
    Object.prototype.hasOwnProperty.call(payload, "history_task_tree")
  ) {
    return null;
  }
  return payload;
}
