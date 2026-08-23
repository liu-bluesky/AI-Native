import {
  buildLocalModelRuntime,
  normalizeLocalModelRuntime,
  readLocalModelProviders,
} from "./local-model-runtime.js";
import {
  readLocalSystemConfig,
  updateLocalSystemConfig,
} from "./local-system-config.js";

const MAIN_PROVIDER_KEY = "default_ai_provider_id";
const MAIN_MODEL_KEY = "default_ai_model_name";
const MAIN_MODEL_UPDATED_EVENT = "local-main-model-updated";

function normalizeText(value) {
  return String(value || "").trim();
}

export function readLocalMainModelSelection() {
  const config = readLocalSystemConfig();
  return {
    providerId: normalizeText(
      config[MAIN_PROVIDER_KEY] ||
        config.main_chat_provider_id ||
        config.mainChatProviderId,
    ),
    modelName: normalizeText(
      config[MAIN_MODEL_KEY] ||
        config.main_chat_model_name ||
        config.mainChatModelName,
    ),
  };
}

export function writeLocalMainModelSelection(providerId = "", modelName = "") {
  const normalizedProviderId = normalizeText(providerId);
  const normalizedModelName = normalizeText(modelName);
  const config = updateLocalSystemConfig({
    [MAIN_PROVIDER_KEY]: normalizedProviderId,
    [MAIN_MODEL_KEY]: normalizedModelName,
    main_chat_provider_id: normalizedProviderId,
    main_chat_model_name: normalizedModelName,
  });
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent(MAIN_MODEL_UPDATED_EVENT, {
        detail: {
          providerId: normalizedProviderId,
          modelName: normalizedModelName,
        },
      }),
    );
  }
  return config;
}

export function resolveLocalMainModelRuntime() {
  const selection = readLocalMainModelSelection();
  const providers = readLocalModelProviders();
  const preferredProvider = selection.providerId
    ? providers.find((item) => item.id === selection.providerId)
    : null;
  const provider = preferredProvider || providers[0] || null;
  if (!provider) return null;

  const runtime = buildLocalModelRuntime(
    provider.id,
    selection.modelName || provider.default_model,
  );
  const normalized = normalizeLocalModelRuntime(
    runtime,
    provider.id,
    selection.modelName || provider.default_model,
  );
  if (!normalized) {
    throw new Error("系统主对话模型运行时配置无效");
  }
  return normalized;
}

export { MAIN_MODEL_UPDATED_EVENT };
