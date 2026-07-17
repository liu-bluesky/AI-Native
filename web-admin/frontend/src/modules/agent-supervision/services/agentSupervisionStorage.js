import {
  getNativeAgentSupervisionAnswer,
  searchNativeAgentSupervisionAnswers,
} from "@/utils/native-desktop-bridge.js";
import { resolveCurrentUsername } from "@/modules/project-chat/services/projectChatStorage.js";

export function normalizeAgentSupervisionAnswerId(value) {
  return String(value || "").trim();
}

export async function searchAgentSupervisionAnswers(
  projectId,
  query = "",
  limit = 50,
) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) return [];
  return searchNativeAgentSupervisionAnswers(
    normalizedProjectId,
    resolveCurrentUsername(),
    normalizeAgentSupervisionAnswerId(query),
    limit,
  );
}

export async function getAgentSupervisionAnswer(projectId, answerId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedAnswerId = normalizeAgentSupervisionAnswerId(answerId);
  if (!normalizedProjectId || !normalizedAnswerId) return null;
  return getNativeAgentSupervisionAnswer(
    normalizedProjectId,
    resolveCurrentUsername(),
    normalizedAnswerId,
  );
}
