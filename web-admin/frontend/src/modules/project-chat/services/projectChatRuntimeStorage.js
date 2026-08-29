import {
  readNativeProjectChatRuntime,
  readNativeProjectChatMessageSnapshot,
  writeNativeProjectChatRuntime,
} from "@/utils/native-desktop-bridge.js";
import {
  deleteLocalChatSession,
  isChatSessionDeleted,
  resolveCurrentUsername,
  enqueueChatSessionStorageOperation,
} from "@/modules/project-chat/services/projectChatStorage.js";

const persistedRuntimeSignatures = new Map();

function runtimeStorageKey(projectId, chatSessionId) {
  return `${String(projectId || "").trim()}::${String(chatSessionId || "").trim()}`;
}

function runtimePayloadSignature(payload) {
  if (!payload || typeof payload !== "object") return "";
  const { updated_at: _updatedAt, ...content } = payload;
  try {
    return JSON.stringify(content);
  } catch {
    return "";
  }
}

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

export async function readPersistedChatMessageSnapshot(projectId, chatSessionId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return [];
  await enqueueChatSessionStorageOperation(
    normalizedProjectId,
    async () => undefined,
  );
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
    await clearPersistedChatRuntime(normalizedProjectId, normalizedChatSessionId);
    return true;
  }
  if (isChatSessionDeleted(normalizedProjectId, normalizedChatSessionId)) {
    return false;
  }
  const storageKey = runtimeStorageKey(
    normalizedProjectId,
    normalizedChatSessionId,
  );
  const signature = runtimePayloadSignature(payload);
  if (signature && persistedRuntimeSignatures.get(storageKey) === signature) {
    return true;
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
      if (saved === true && signature) {
        persistedRuntimeSignatures.set(storageKey, signature);
      }
      return saved;
    },
  );
}

export async function clearPersistedChatRuntime(projectId, chatSessionId = "") {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return false;
  persistedRuntimeSignatures.delete(
    runtimeStorageKey(normalizedProjectId, normalizedChatSessionId),
  );
  return deleteLocalChatSession(
    normalizedProjectId,
    normalizedChatSessionId,
  );
}
