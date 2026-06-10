import api from "@/utils/api.js";
import { clipText } from "@/modules/project-chat/mappers/mediaMappers.js";

export function upsertProjectChatRequirementRecord(projectId, payload = {}) {
  const normalizedProjectId = String(projectId || "").trim();
  const activeChatSessionId = String(payload.chatSessionId || "").trim();
  const normalizedRootGoal = String(payload.rootGoal || payload.title || "").trim();
  if (!normalizedProjectId || !activeChatSessionId || !normalizedRootGoal) {
    return Promise.resolve(null);
  }
  // requirement record 是 ProjectChat 与任务恢复列表的 API 边界，页面只传业务状态。
  return api.post(
    `/projects/${encodeURIComponent(normalizedProjectId)}/chat/requirement-record`,
    {
      chat_session_id: activeChatSessionId,
      message_id: String(payload.messageId || "").trim(),
      assistant_message_id: String(payload.assistantMessageId || "").trim(),
      root_goal: clipText(normalizedRootGoal, 1000),
      title: clipText(payload.title || normalizedRootGoal, 160),
      status: String(payload.status || "in_progress").trim(),
      result_summary: clipText(payload.resultSummary, 1800),
      verification_result: clipText(payload.verificationResult, 1800),
      runner_session_id: String(payload.runnerSessionId || "").trim(),
      runner_agent_type: String(payload.runnerAgentType || "").trim(),
      source: String(payload.source || "project_chat").trim(),
      source_context:
        payload.sourceContext && typeof payload.sourceContext === "object"
          ? payload.sourceContext
          : {},
    },
  );
}
