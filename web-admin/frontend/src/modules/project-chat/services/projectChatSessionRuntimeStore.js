const sessionMessageCache = new Map();
const sessionRuntimeCache = new Map();
const dirtySessionKeys = new Set();

function sessionKey(projectId, chatSessionId) {
  const project = String(projectId || "").trim();
  const session = String(chatSessionId || "").trim();
  return project && session ? `${project}:${session}` : "";
}

export function getProjectChatSessionMessageCache() {
  return sessionMessageCache;
}

export function getProjectChatSessionRuntimeCache() {
  return sessionRuntimeCache;
}

export function getProjectChatSessionDirtyKeys() {
  return dirtySessionKeys;
}

export function clearProjectChatSessionRuntime(projectId, chatSessionId) {
  const key = sessionKey(projectId, chatSessionId);
  if (!key) return;
  sessionMessageCache.delete(key);
  sessionRuntimeCache.delete(key);
  dirtySessionKeys.delete(key);
}

export function clearProjectChatSessionProjectRuntime(projectId) {
  const project = String(projectId || "").trim();
  if (!project) return;
  const prefix = `${project}:`;
  for (const key of sessionMessageCache.keys()) {
    if (key.startsWith(prefix)) sessionMessageCache.delete(key);
  }
  for (const key of sessionRuntimeCache.keys()) {
    if (key.startsWith(prefix)) sessionRuntimeCache.delete(key);
  }
  for (const key of dirtySessionKeys) {
    if (key.startsWith(prefix)) dirtySessionKeys.delete(key);
  }
}
