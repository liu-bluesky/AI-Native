import {
  readNativeProjectChatRuntime,
  writeNativeProjectChatRuntime,
} from "@/utils/native-desktop-bridge.js";
import {
  deleteLocalChatSession,
  isChatSessionDeleted,
  resolveCurrentUsername,
  enqueueChatSessionStorageOperation,
} from "@/modules/project-chat/services/projectChatStorage.js";

export async function readPersistedChatRuntime(projectId, chatSessionId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return null;
  await enqueueChatSessionStorageOperation(
    normalizedProjectId,
    async () => undefined,
  );
  if (isChatSessionDeleted(normalizedProjectId, normalizedChatSessionId)) {
    return null;
  }
  return readNativeProjectChatRuntime(
    normalizedProjectId,
    normalizedChatSessionId,
    resolveCurrentUsername(),
  );
}

export async function writePersistedChatRuntime(
  projectId,
  chatSessionId,
  payload,
) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return false;
  if (!payload || typeof payload !== "object") {
    await clearPersistedChatRuntime(normalizedProjectId, normalizedChatSessionId);
    return true;
  }
  if (isChatSessionDeleted(normalizedProjectId, normalizedChatSessionId)) {
    return false;
  }
  return enqueueChatSessionStorageOperation(
    normalizedProjectId,
    async () => {
      if (isChatSessionDeleted(normalizedProjectId, normalizedChatSessionId)) {
        return false;
      }
      return writeNativeProjectChatRuntime(
        normalizedProjectId,
        normalizedChatSessionId,
        resolveCurrentUsername(),
        payload,
      );
    },
  );
}

export async function clearPersistedChatRuntime(projectId, chatSessionId = "") {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return false;
  return deleteLocalChatSession(
    normalizedProjectId,
    normalizedChatSessionId,
  );
}
