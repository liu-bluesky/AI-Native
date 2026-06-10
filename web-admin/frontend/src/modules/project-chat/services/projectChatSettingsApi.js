import api from "@/utils/api.js";

function projectChatSettingsUrl(projectId, suffix = "") {
  return `/projects/${encodeURIComponent(projectId)}/chat${suffix}`;
}

export function fetchProjectChatProviders(projectId) {
  return api.get(projectChatSettingsUrl(projectId, "/providers"));
}

export function saveProjectChatSettings(projectId, settings = {}) {
  // 设置保存由 service 统一维护接口形状，页面仍负责表单清洗和自动保存状态。
  return api.put(projectChatSettingsUrl(projectId, "/settings"), { settings });
}
