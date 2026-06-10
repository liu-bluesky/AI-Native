import api from "@/utils/api.js";

function projectChatTaskTreeUrl(projectId) {
  return `/projects/${encodeURIComponent(projectId)}/chat/task-tree`;
}

export function fetchProjectChatTaskTree(projectId, params = {}) {
  return api.get(projectChatTaskTreeUrl(projectId), { params });
}

export function fetchProjectChatOngoingTaskTree(projectId) {
  return api.get(`${projectChatTaskTreeUrl(projectId)}/ongoing`);
}

export function fetchProjectChatWorkSessionsByTaskTree(
  projectId,
  {
    taskTreeSessionId = "",
    taskTreeChatSessionId = "",
    limit = 1,
  } = {},
) {
  // 工作轨迹查询和任务树恢复强绑定，统一在 service 层维护 API 参数。
  return api.get(`/projects/${encodeURIComponent(projectId)}/work-sessions`, {
    params: {
      task_tree_session_id: String(taskTreeSessionId || "").trim(),
      task_tree_chat_session_id: String(taskTreeChatSessionId || "").trim(),
      limit,
    },
  });
}

export function deleteProjectChatTaskTree(projectId, chatSessionId) {
  return api.delete(projectChatTaskTreeUrl(projectId), {
    params: { chat_session_id: chatSessionId },
  });
}

export function updateProjectChatTaskTreeNode(projectId, nodeId, payload) {
  // 任务树节点更新是 MCP 任务闭环入口，调用方必须先完成验证结果校验。
  return api.patch(
    `${projectChatTaskTreeUrl(projectId)}/nodes/${encodeURIComponent(nodeId)}`,
    payload,
  );
}
