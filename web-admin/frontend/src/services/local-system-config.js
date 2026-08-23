const STORAGE_KEY = "local_system_config";
const UPDATED_EVENT = "local-system-config-updated";

function canUseStorage() {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

function normalizeConfig(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? { ...value }
    : {};
}

export function readLocalSystemConfig() {
  if (!canUseStorage()) return {};
  try {
    return normalizeConfig(JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}"));
  } catch {
    return {};
  }
}

export function writeLocalSystemConfig(config) {
  const normalized = normalizeConfig(config);
  if (canUseStorage()) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    window.dispatchEvent(
      new CustomEvent(UPDATED_EVENT, {
        detail: { config: normalized, updatedAt: Date.now() },
      }),
    );
  }
  return normalized;
}

export function updateLocalSystemConfig(patch = {}) {
  return writeLocalSystemConfig({
    ...readLocalSystemConfig(),
    ...normalizeConfig(patch),
  });
}

export {
  STORAGE_KEY as LOCAL_SYSTEM_CONFIG_STORAGE_KEY,
  UPDATED_EVENT as LOCAL_SYSTEM_CONFIG_UPDATED_EVENT,
};
