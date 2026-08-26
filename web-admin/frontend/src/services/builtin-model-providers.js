import { DEFAULT_BACKEND_API_ORIGIN } from "@/utils/backend-endpoints.js";

function normalizeText(value) {
  return String(value || "").trim();
}

function normalizeProvider(provider = {}) {
  const models = Array.isArray(provider.models) ? provider.models : [];
  const modelConfigs = models
    .map((model) => {
      const modelCode = normalizeText(model?.model_code || model?.name);
      if (!modelCode) return null;
      return {
        name: modelCode,
        model_type: normalizeText(model?.capability_type) || "text_generation",
        display_name: normalizeText(model?.name) || modelCode,
      };
    })
    .filter(Boolean);
  const providerId = normalizeText(provider?.id);
  if (!providerId || !modelConfigs.length) return null;
  return {
    id: `server-builtin-${providerId}`,
    source_provider_id: providerId,
    source: "server-builtin",
    is_builtin_provider: true,
    name: normalizeText(provider?.name) || "内置模型供应商",
    provider_type: normalizeText(provider?.provider_type) || "openai-compatible",
    model_configs: modelConfigs,
    default_model:
      normalizeText(provider?.default_model) || modelConfigs[0]?.name || "",
    enabled: provider?.enabled !== false && Number(provider?.enabled) !== 0,
    updated_at: provider?.updated_at || "",
  };
}

export async function fetchBuiltinModelProviders() {
  const response = await fetch(
    `${DEFAULT_BACKEND_API_ORIGIN}/api/llm/builtin-providers`,
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.error || "获取内置模型供应商失败");
  }
  const source = Array.isArray(payload?.providers)
    ? payload.providers
    : payload?.provider
      ? [{ ...payload.provider, models: payload.models || [] }]
      : [];
  return source.map(normalizeProvider).filter(Boolean);
}
