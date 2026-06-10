import { toWorkspaceRelativePath } from "@/utils/workspace-picker.js";

export function normalizeAiEntryFileForSave(value, workspacePath = "") {
  const rawValue = String(value || "").trim();
  if (!rawValue) return "";
  // AI 入口文件保存为相对工作区路径，无法归一时保留用户原始输入。
  const normalizedRelative = toWorkspaceRelativePath(rawValue, workspacePath);
  return String(normalizedRelative || rawValue).trim();
}
