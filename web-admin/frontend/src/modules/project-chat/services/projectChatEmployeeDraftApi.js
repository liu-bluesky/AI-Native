import { readLocalEntities } from "@/services/local-project-repository.js";

export async function fetchEmployeeDraftCatalog() {
  return {
    skills: readLocalEntities("skills"),
    rules: readLocalEntities("rules"),
  };
}

export function generateEmployeeDraft(payload = {}) {
  void payload;
  throw new Error("本地模式未安装智能体草稿生成器，请在项目对话中使用本机 AI Runtime 生成草稿");
}
