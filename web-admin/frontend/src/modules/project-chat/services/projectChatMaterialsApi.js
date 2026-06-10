import api from "@/utils/api.js";

export function createProjectMaterial(projectId, payload = {}) {
  // 素材保存 payload 来自弹窗表单，service 只维护项目素材接口入口。
  return api.post(`/projects/${encodeURIComponent(projectId)}/materials`, payload);
}
