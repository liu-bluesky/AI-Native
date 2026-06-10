import api from "@/utils/api.js";

function projectAgentRuntimeUrl(projectId, suffix = "") {
  return `/projects/${encodeURIComponent(projectId)}/agent-runtime-v2${suffix}`;
}

export function submitAgentRuntimePermissionActionRequest(
  projectId,
  payload = {},
) {
  // Agent Runtime 权限动作保持 service 窄入口，页面继续负责 operation 乐观更新与结果回填。
  return api.post(projectAgentRuntimeUrl(projectId, "/permission-actions"), {
    action: String(payload.action || "").trim(),
    run_id: String(payload.run_id || "").trim(),
    call_id: String(payload.call_id || "").trim(),
    tool_name: String(payload.tool_name || "").trim(),
    args:
      payload.args && typeof payload.args === "object" && !Array.isArray(payload.args)
        ? payload.args
        : {},
    chat_session_id: String(payload.chat_session_id || "").trim(),
    assistant_message_id: String(payload.assistant_message_id || "").trim(),
  });
}

export function trustAgentRuntimeWorkspaceRequest(projectId, payload = {}) {
  return api.post(projectAgentRuntimeUrl(projectId, "/workspace-trust"), {
    workspace_path: String(payload.workspace_path || "").trim(),
    trusted: payload.trusted !== false,
    metadata:
      payload.metadata &&
      typeof payload.metadata === "object" &&
      !Array.isArray(payload.metadata)
        ? payload.metadata
        : {},
  });
}
