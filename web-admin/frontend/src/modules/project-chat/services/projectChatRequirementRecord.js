import api from "@/utils/api.js";

export function upsertProjectChatRequirementRecord(projectId, payload = {}) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) return Promise.resolve(null);
  return api.post(
    `/projects/${encodeURIComponent(normalizedProjectId)}/chat/requirement-record`,
    payload,
  );
}
