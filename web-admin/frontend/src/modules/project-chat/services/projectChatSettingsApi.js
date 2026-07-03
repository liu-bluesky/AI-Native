import api from "@/utils/api.js";

function projectChatSettingsUrl(projectId, suffix = "") {
  return `/projects/${encodeURIComponent(projectId)}/chat${suffix}`;
}

export function fetchProjectChatProviders(projectId, options = {}) {
  const includeRuntimeExternalTools =
    options.includeRuntimeExternalTools !== false;
  return api.get(projectChatSettingsUrl(projectId, "/providers"), {
    params: {
      include_runtime_external_tools: includeRuntimeExternalTools,
    },
  });
}

export function saveProjectChatSettings(projectId, settings = {}) {
  // 设置保存由 service 统一维护接口形状，页面仍负责表单清洗和自动保存状态。
  return api.put(projectChatSettingsUrl(projectId, "/settings"), { settings });
}
