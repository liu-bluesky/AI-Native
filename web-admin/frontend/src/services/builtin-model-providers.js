import {
  getStoredAuthProfile,
  getStoredToken,
  isExternalAuthSession,
} from "@/utils/auth-storage.js";
import { DEFAULT_BACKEND_API_ORIGIN } from "@/utils/backend-endpoints.js";
import { buildNativeBackendApiBaseUrl } from "@/utils/server-profile.js";

function normalizeText(value) {
  return String(value || "").trim();
}

export function isServerBuiltinModelProvider(provider = {}) {
  const id = normalizeText(provider?.id);
  return (
    provider?.is_builtin_provider === true ||
    provider?.source === "server-builtin" ||
    id.startsWith("server-builtin-") ||
    id.startsWith("builtin-")
  );
}

export function mergeBuiltinModelProviders(localProviders = [], builtinProviders = []) {
  const localOnly = (Array.isArray(localProviders) ? localProviders : []).filter(
    (provider) => !isServerBuiltinModelProvider(provider),
  );
  return [...builtinProviders, ...localOnly];
}

function providerIdentity(provider = {}) {
  return normalizeText(provider?.id || provider?.provider_id);
}

function hasProviderValue(provider, ...keys) {
  return keys.some((key) => normalizeText(provider?.[key]));
}

export function mergeProjectModelProviders(
  projectProviders = [],
  localProviders = [],
) {
  const localById = new Map(
    (Array.isArray(localProviders) ? localProviders : [])
      .map((provider) => [providerIdentity(provider), provider])
      .filter(([id]) => id),
  );
  const usedIds = new Set();
  const mergedProjectProviders = (Array.isArray(projectProviders)
    ? projectProviders
    : []
  )
    .map((projectProvider) => {
      const providerId = providerIdentity(projectProvider);
      if (!providerId) return null;
      const localProvider = localById.get(providerId) || {};
      usedIds.add(providerId);
      const merged = { ...localProvider, ...projectProvider, id: providerId };
      if (!hasProviderValue(projectProvider, "base_url", "baseUrl")) {
        merged.base_url = normalizeText(
          localProvider.base_url || localProvider.baseUrl,
        );
      }
      if (!hasProviderValue(projectProvider, "api_key", "apiKey")) {
        merged.api_key = normalizeText(
          localProvider.api_key || localProvider.apiKey,
        );
      }
      if (!hasProviderValue(projectProvider, "provider_type", "providerType")) {
        merged.provider_type = normalizeText(
          localProvider.provider_type || localProvider.providerType,
        );
      }
      if (
        !Array.isArray(projectProvider.model_configs) &&
        !Array.isArray(projectProvider.models)
      ) {
        merged.model_configs = Array.isArray(localProvider.model_configs)
          ? localProvider.model_configs
          : localProvider.models;
      }
      return merged;
    })
    .filter(Boolean);
  const remainingLocalProviders = (Array.isArray(localProviders)
    ? localProviders
    : []
  ).filter((provider) => !usedIds.has(providerIdentity(provider)));
  return [...mergedProjectProviders, ...remainingLocalProviders];
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
    ...provider,
    id: `server-builtin-${providerId}`,
    source_provider_id: providerId,
    source: "server-builtin",
    is_builtin_provider: true,
    name: normalizeText(provider?.name) || "内置模型供应商",
    provider_type: normalizeText(provider?.provider_type) || "openai-compatible",
    base_url: normalizeText(provider?.base_url || provider?.baseUrl),
    api_key: normalizeText(provider?.api_key || provider?.apiKey),
    api_key_env: normalizeText(provider?.api_key_env || provider?.apiKeyEnv),
    extra_headers:
      provider?.extra_headers && typeof provider.extra_headers === "object"
        ? provider.extra_headers
        : provider?.extraHeaders && typeof provider.extraHeaders === "object"
          ? provider.extraHeaders
          : {},
    model_configs: modelConfigs,
    default_model:
      normalizeText(provider?.default_model) || modelConfigs[0]?.name || "",
    enabled: provider?.enabled !== false && Number(provider?.enabled) !== 0,
    temperature: provider?.temperature,
    timeout_ms: provider?.timeout_ms || provider?.timeoutMs,
    updated_at: provider?.updated_at || "",
  };
}

export async function fetchBuiltinModelProviders() {
  const response = await requestBuiltinProviderApi("/api/llm/builtin-providers");
  const source = Array.isArray(response?.providers)
    ? response.providers
    : response?.provider
      ? [{ ...response.provider, models: response.models || [] }]
      : [];
  return source.map(normalizeProvider).filter(Boolean);
}

async function requestBuiltinProviderApi(pathname, init = {}) {
  const token = getStoredToken();
  const profile = getStoredAuthProfile();
  const headers = {};
  const externalSession = isExternalAuthSession();
  const username = String(profile?.username || "").trim();
  if (externalSession && username) {
    headers.Authorization = `Bearer ${encodeURIComponent(username)}`;
  } else if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const apiBaseUrl = externalSession
    ? `${DEFAULT_BACKEND_API_ORIGIN}/api`
    : buildNativeBackendApiBaseUrl().replace(/\/+$/, "");
  const response = await fetch(`${apiBaseUrl}${pathname.replace(/^\/api/, "")}`, {
    ...init,
    headers: { ...headers, ...(init.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.error || "获取内置模型供应商失败");
  }
  return payload;
}

export async function testBuiltinModelProvider(providerId) {
  const id = encodeURIComponent(normalizeText(providerId));
  if (!id) throw new Error("缺少内置供应商 ID");
  return requestBuiltinProviderApi(`/api/llm/builtin-providers/${id}/test`, {
    method: "POST",
  });
}
