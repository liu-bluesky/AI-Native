import {
  deleteNativeProjectChatSession,
  readNativeProjectChatRuntime,
  writeNativeProjectChatRuntime,
} from "@/utils/native-desktop-bridge.js";
import { resolveCurrentUsername } from "@/modules/project-chat/services/projectChatStorage.js";

const runtimeWriteQueues = new Map();

function runtimeStorageQueueKey(projectId, chatSessionId) {
  return `${String(projectId || "").trim()}::${String(chatSessionId || "").trim()}`;
}

function enqueueRuntimeStorageOperation(projectId, chatSessionId, operation) {
  const key = runtimeStorageQueueKey(projectId, chatSessionId);
  const previous = runtimeWriteQueues.get(key) || Promise.resolve();
  const next = previous.catch(() => undefined).then(operation);
  runtimeWriteQueues.set(key, next);
  return next.finally(() => {
    if (runtimeWriteQueues.get(key) === next) {
      runtimeWriteQueues.delete(key);
    }
  });
}

export async function readPersistedChatRuntime(projectId, chatSessionId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return null;
  await (runtimeWriteQueues.get(
    runtimeStorageQueueKey(normalizedProjectId, normalizedChatSessionId),
  ) || Promise.resolve());
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
  return enqueueRuntimeStorageOperation(
    normalizedProjectId,
    normalizedChatSessionId,
    () =>
      writeNativeProjectChatRuntime(
        normalizedProjectId,
        normalizedChatSessionId,
        resolveCurrentUsername(),
        payload,
      ),
  );
}

export async function clearPersistedChatRuntime(projectId, chatSessionId = "") {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return false;
  return enqueueRuntimeStorageOperation(
    normalizedProjectId,
    normalizedChatSessionId,
    () =>
      deleteNativeProjectChatSession(
        normalizedProjectId,
        normalizedChatSessionId,
        resolveCurrentUsername(),
      ),
  );
}
