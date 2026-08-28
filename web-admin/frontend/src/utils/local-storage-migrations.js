const LEGACY_LOCAL_RUNTIME_KEY_PREFIX = "project_chat_runtime_";

export function removeLegacyLocalRuntimeSnapshots() {
  if (typeof window === "undefined" || !window.localStorage) return 0;
  const legacyKeys = [];
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index) || "";
    if (key.startsWith(LEGACY_LOCAL_RUNTIME_KEY_PREFIX)) {
      legacyKeys.push(key);
    }
  }
  let removed = 0;
  for (const key of legacyKeys) {
    try {
      window.localStorage.removeItem(key);
      removed += 1;
    } catch {}
  }
  return removed;
}
