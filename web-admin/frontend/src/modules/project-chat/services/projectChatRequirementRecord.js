import api from "@/utils/api.js";
import { clipText } from "@/modules/project-chat/mappers/mediaMappers.js";

export function upsertProjectChatRequirementRecord(projectId, payload = {}) {
  const normalizedProjectId = String(projectId || "").trim();
  const activeChatSessionId = String(payload.chatSessionId || "").trim();
  const normalizedRootGoal = String(payload.rootGoal || payload.title || "").trim();
  if (!normalizedProjectId || !activeChatSessionId || !normalizedRootGoal) {
    return Promise.resolve(null);
  }
  // requirement record 只保存需求内容；执行轨迹、任务树和上下文走各自链路。
  return api.post(
    `/projects/${encodeURIComponent(normalizedProjectId)}/chat/requirement-record`,
    {
      chat_session_id: activeChatSessionId,
      message_id: String(payload.messageId || "").trim(),
      assistant_message_id: String(payload.assistantMessageId || "").trim(),
      root_goal: clipText(normalizedRootGoal, 1000),
      title: clipText(payload.title || normalizedRootGoal, 160),
    },
  );
}
