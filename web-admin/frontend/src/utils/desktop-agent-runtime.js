import api from "@/utils/api.js";
import { getStoredToken } from "@/utils/auth-storage.js";
import {
  getNativeRuntimeInfo,
  hasNativeDesktopBridge,
  startNativeLiuAgentLocalChat,
} from "@/utils/native-desktop-bridge.js";
import { buildApiBaseUrl, resolveServerOrigin } from "@/utils/server-profile.js";

function desktopAgentRequestId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function desktopBackendApiBaseUrl() {
  const baseUrl = String(buildApiBaseUrl() || "").trim();
  if (/^https?:\/\//i.test(baseUrl)) return baseUrl;
  const origin = String(resolveServerOrigin() || "").trim();
  if (/^https?:\/\//i.test(origin)) {
    return `${origin.replace(/\/+$/, "")}/${baseUrl.replace(/^\/+/, "")}`;
  }
  return baseUrl;
}

export async function resolveDesktopAgentWorkspacePath(workspacePath = "") {
  const requested = String(workspacePath || "").trim();
  if (requested) return requested;
  const runtimeInfo = await getNativeRuntimeInfo();
  return String(
    runtimeInfo?.defaultWorkspacePath ||
      runtimeInfo?.default_workspace_path ||
      runtimeInfo?.installDir ||
      runtimeInfo?.install_dir ||
      "",
  ).trim();
}

export async function resolveDesktopAgentModelRuntime({
  providerId,
  modelName = "",
  temperature = 0.1,
} = {}) {
  const normalizedProviderId = String(providerId || "").trim();
  if (!normalizedProviderId) {
    throw new Error("请先选择桌面智能体使用的模型供应商");
  }
  const data = await api.get(
    `/llm/providers/${encodeURIComponent(normalizedProviderId)}/desktop-runtime`,
  );
  const runtime = data?.runtime && typeof data.runtime === "object" ? data.runtime : {};
  const baseUrl = String(runtime.base_url || runtime.baseUrl || "").trim();
  const apiKey = String(runtime.api_key || runtime.apiKey || "").trim();
  const resolvedModelName = String(
    modelName ||
      runtime.model_name ||
      runtime.modelName ||
      runtime.default_model ||
      runtime.defaultModel ||
      "",
  ).trim();
  if (!baseUrl || !apiKey || !resolvedModelName) {
    throw new Error("当前模型供应商缺少桌面端 Base URL、API Key 或模型名");
  }
  return {
    mode: "direct-openai-compatible",
    providerId: normalizedProviderId,
    modelName: resolvedModelName,
    baseUrl,
    apiKey,
    temperature: Number(temperature),
  };
}

export async function runDesktopAgentTextTask({
  projectId = "desktop-agent",
  chatSessionId = "",
  message,
  history = [],
  providerId,
  modelName = "",
  temperature = 0.1,
  systemPrompt = "",
  workspacePath = "",
} = {}) {
  if (!hasNativeDesktopBridge()) {
    throw new Error("当前功能仅支持桌面智能体");
  }
  const normalizedMessage = String(message || "").trim();
  if (!normalizedMessage) throw new Error("桌面智能体任务内容不能为空");
  const resolvedWorkspacePath = await resolveDesktopAgentWorkspacePath(workspacePath);
  if (!resolvedWorkspacePath) throw new Error("桌面端未返回默认工作区路径");
  const modelRuntime = await resolveDesktopAgentModelRuntime({
    providerId,
    modelName,
    temperature,
  });
  const resolvedChatSessionId =
    String(chatSessionId || "").trim() || desktopAgentRequestId("desktop-session");
  const result = await startNativeLiuAgentLocalChat({
    projectId: String(projectId || "desktop-agent").trim(),
    chatSessionId: resolvedChatSessionId,
    messageId: desktopAgentRequestId("user"),
    assistantMessageId: desktopAgentRequestId("assistant"),
    message: normalizedMessage,
    workspacePath: resolvedWorkspacePath,
    history: Array.isArray(history) ? history : [],
    providerId: modelRuntime.providerId,
    modelName: modelRuntime.modelName,
    systemPrompt: String(systemPrompt || "").trim(),
    systemPromptParts: String(systemPrompt || "").trim()
      ? [{ source: "desktop-task", priority: 100, content: systemPrompt }]
      : [],
    temperature: modelRuntime.temperature,
    modelRuntime,
    backendContext: {
      apiBaseUrl: desktopBackendApiBaseUrl(),
      token: getStoredToken(),
    },
  });
  if (!result?.ok) {
    throw new Error(
      String(
        result?.userVisibleErrorSummary ||
          result?.user_visible_error_summary ||
          result?.error ||
          result?.summary ||
          "桌面智能体执行失败",
      ).trim(),
    );
  }
  return String(
    result?.assistantContent ||
      result?.assistant_content ||
      result?.content ||
      result?.summary ||
      "",
  ).trim();
}
