import { normalizeProviderModelConfigs } from "@/utils/llm-models.js";

import { readLocalEntities } from "./local-project-repository.js";

const LOCAL_PROVIDER_ENTITY = "llm_providers";

function normalizeText(value) {
  return String(value || "").trim();
}

function normalizeFiniteNumber(value) {
  return Number.isFinite(Number(value)) && value !== "" ? Number(value) : null;
}

export function normalizeLocalModelRuntime(
  runtime,
  fallbackProviderId = "",
  fallbackModelName = "",
) {
  const source =
    runtime && typeof runtime === "object" && !Array.isArray(runtime) ? runtime : {};
  const mode = normalizeText(source.mode || "direct-openai-compatible").toLowerCase();
  if (mode !== "direct-openai-compatible") return null;

  const providerId = normalizeText(
    source.providerId || source.provider_id || fallbackProviderId,
  );
  const modelName = normalizeText(
    source.modelName ||
      source.model_name ||
      source.defaultModel ||
      source.default_model ||
      fallbackModelName,
  );
  const baseUrl = normalizeText(source.baseUrl || source.base_url);
  if (!baseUrl || !modelName) return null;

  const apiKey = normalizeText(source.apiKey || source.api_key);
  const apiKeyEnv = normalizeText(source.apiKeyEnv || source.api_key_env);
  const gatewayUrl = normalizeText(source.gatewayUrl || source.gateway_url);
  const normalized = {
    mode: "direct-openai-compatible",
    providerId,
    modelName,
    baseUrl,
  };
  if (apiKey) normalized.apiKey = apiKey;
  if (apiKeyEnv) normalized.apiKeyEnv = apiKeyEnv;
  if (gatewayUrl) normalized.gatewayUrl = gatewayUrl;

  const temperature = normalizeFiniteNumber(source.temperature);
  if (temperature !== null) normalized.temperature = temperature;
  const timeoutMs = normalizeFiniteNumber(source.timeoutMs || source.timeout_ms);
  if (timeoutMs !== null) normalized.timeoutMs = timeoutMs;
  return normalized;
}

export function readLocalModelProviders() {
  return readLocalEntities(LOCAL_PROVIDER_ENTITY)
    .map((provider) => {
      const id = normalizeText(provider?.id || provider?.provider_id);
      if (!id) return null;
      const modelConfigs = normalizeProviderModelConfigs(provider);
      return {
        ...provider,
        id,
        name: normalizeText(provider?.name || id) || id,
        base_url: normalizeText(provider?.base_url || provider?.baseUrl),
        api_key: normalizeText(provider?.api_key || provider?.apiKey),
        default_model: normalizeText(
          provider?.default_model || provider?.defaultModel || modelConfigs[0]?.name,
        ),
        model_configs: modelConfigs,
        enabled: provider?.enabled !== false,
      };
    })
    .filter((provider) => provider && provider.enabled !== false);
}

export function findLocalModelProvider(providerId) {
  const normalizedProviderId = normalizeText(providerId);
  if (!normalizedProviderId) return null;
  return (
    readLocalModelProviders().find((provider) => provider.id === normalizedProviderId) || null
  );
}

export function buildLocalModelRuntime(providerId, modelName = "") {
  const provider = findLocalModelProvider(providerId);
  if (!provider) {
    throw new Error(`本地未找到已启用的模型供应商：${normalizeText(providerId)}`);
  }
  if (!provider.base_url) {
    throw new Error(`本地模型供应商缺少 Base URL：${provider.name}`);
  }
  const resolvedModelName =
    normalizeText(modelName) ||
    provider.default_model ||
    provider.model_configs[0]?.name ||
    "";
  if (!resolvedModelName) {
    throw new Error(`本地模型供应商未配置可用模型：${provider.name}`);
  }
  const runtime = normalizeLocalModelRuntime(
    {
      mode: "direct-openai-compatible",
      providerId: provider.id,
      modelName: resolvedModelName,
      baseUrl: provider.base_url,
      apiKey: provider.api_key,
      apiKeyEnv: provider.api_key_env,
      temperature: provider.temperature,
      timeoutMs: provider.timeout_ms || provider.timeoutMs,
    },
    provider.id,
    resolvedModelName,
  );
  if (!runtime) {
    throw new Error(`本地模型供应商运行时配置无效：${provider.name}`);
  }
  return runtime;
}
