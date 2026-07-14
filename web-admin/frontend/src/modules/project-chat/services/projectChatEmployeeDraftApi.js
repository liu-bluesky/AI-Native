import api from "@/utils/api.js";

export async function fetchEmployeeDraftCatalog() {
  const [skillsRes, rulesRes] = await Promise.all([
    api.get("/skills"),
    api.get("/rules"),
  ]);
  return {
    skills: Array.isArray(skillsRes?.skills) ? skillsRes.skills : [],
    rules: Array.isArray(rulesRes?.rules) ? rulesRes.rules : [],
  };
}

export function createEmployeeFromDraft(payload = {}) {
  // 智能体草稿创建会触发技能/规则补齐，页面负责提交前的表单和匹配状态。
  return api.post("/employees/create-from-draft", payload);
}

export function generateEmployeeDraft(payload = {}) {
  return api.post("/employees/generate-draft", payload);
}
