import {
  readNativeProjectChatRuntime,
  readNativeProjectChatMessageSnapshot,
  writeNativeProjectChatRuntime,
} from "@/utils/native-desktop-bridge.js";
import {
  deleteLocalChatSession,
  isChatSessionDeleted,
  resolveCurrentUsername,
} from "@/modules/project-chat/services/projectChatStorage.js";

export async function readPersistedChatRuntime(projectId, chatSessionId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return null;
  if (isChatSessionDeleted(normalizedProjectId, normalizedChatSessionId)) {
    return null;
  }
  return readNativeProjectChatRuntime(
    normalizedProjectId,
    normalizedChatSessionId,
    resolveCurrentUsername(),
  );
}

export async function readPersistedChatMessageSnapshot(projectId, chatSessionId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return [];
  if (isChatSessionDeleted(normalizedProjectId, normalizedChatSessionId)) {
    return [];
  }
  return readNativeProjectChatMessageSnapshot(
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
    console.error("writePersistedChatRuntime: invalid payload, refusing to save", {
      projectId: normalizedProjectId,
      chatSessionId: normalizedChatSessionId,
      payloadType: typeof payload,
      payload,
    });
    return false;
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
      const saved = await writeNativeProjectChatRuntime(
        normalizedProjectId,
        normalizedChatSessionId,
        resolveCurrentUsername(),
        payload,
      );
      if (saved !== true) {
        console.error("project chat runtime write returned non-success", {
          projectId: normalizedProjectId,
          chatSessionId: normalizedChatSessionId,
          username: resolveCurrentUsername(),
          payloadKeys: Object.keys(payload),
          deletedMessageIds: Array.isArray(payload.deleted_message_ids)
            ? payload.deleted_message_ids
            : [],
          hasMessages: Array.isArray(payload.messages),
          result: saved,
        });
      }
      return saved;
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
