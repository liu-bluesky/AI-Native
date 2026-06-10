import api from "@/utils/api.js";

function projectWorkspaceUrl(projectId, suffix = "") {
  return `/projects/${encodeURIComponent(projectId)}/workspace${suffix}`;
}

export function listProjectWorkspaceFiles(projectId, path = "") {
  return api.get(projectWorkspaceUrl(projectId, "/files"), {
    params: { path: String(path || "").trim() },
  });
}

export function readProjectWorkspaceFile(projectId, path = "") {
  return api.get(projectWorkspaceUrl(projectId, "/file"), {
    params: { path: String(path || "").trim() },
  });
}

export function saveProjectWorkspaceFile(projectId, { path = "", content = "" } = {}) {
  // 工作区文件写入接口保持窄入口，调用方仍负责权限、确认和只读分支判断。
  return api.put(projectWorkspaceUrl(projectId, "/file"), {
    path: String(path || "").trim(),
    content,
  });
}
