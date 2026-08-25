import { DEFAULT_DESKTOP_AGENT_GLOBAL_PROMPT } from "@/config/desktopAgentPrompts.js";
import {
  openLocalWorkspaceProject,
  upsertLocalProject,
} from "@/services/local-project-repository.js";
import { readLocalSystemConfig } from "@/services/local-system-config.js";
import {
  hasNativeDesktopBridge,
  readNativeWorkspaceFile,
  writeNativeWorkspaceFile,
} from "@/utils/native-desktop-bridge.js";
import { pickWorkspaceDirectory } from "@/utils/workspace-picker.js";

const DEFAULT_AI_ENTRY_FILE = "AIENTRY.md";

function isWorkspaceFileMissing(error) {
  return /not found|no such file|os error 2|系统找不到指定的文件|找不到指定的文件|不存在/i.test(
    String(error?.message || error?.detail || error || ""),
  );
}

export async function initializeLocalWorkspaceProjectAiEntryFile(project) {
  const projectId = String(project?.id || "").trim();
  const workspacePath = String(project?.workspace_path || "").trim();
  if (!projectId || !workspacePath || !hasNativeDesktopBridge()) return project;

  try {
    const existingFile = await readNativeWorkspaceFile({
      workspacePath,
      path: DEFAULT_AI_ENTRY_FILE,
    });
    if (Number(existingFile?.size || 0) > 0) {
      upsertLocalProject({
        ...project,
        id: projectId,
        ai_entry_file: DEFAULT_AI_ENTRY_FILE,
      });
      return project;
    }
  } catch (error) {
    if (!isWorkspaceFileMissing(error)) throw error;
    await writeNativeWorkspaceFile({
      workspacePath,
      path: DEFAULT_AI_ENTRY_FILE,
      content:
        String(readLocalSystemConfig().desktop_agent_global_prompt || "").trim() ||
        DEFAULT_DESKTOP_AGENT_GLOBAL_PROMPT,
    });
  }

  upsertLocalProject({
    ...project,
    id: projectId,
    ai_entry_file: DEFAULT_AI_ENTRY_FILE,
  });
  return project;
}

export async function openLocalWorkspaceProjectFromPicker(options = {}) {
  const workspacePath = await pickWorkspaceDirectory(
    String(options?.initialPath || "").trim(),
    {
      title: String(options?.title || "打开文件夹").trim() || "打开文件夹",
    },
  );
  if (!workspacePath) return null;

  const project = openLocalWorkspaceProject(workspacePath);
  if (!project?.id) {
    throw new Error("无法保存文件夹工作区");
  }

  await initializeLocalWorkspaceProjectAiEntryFile(project);
  return { project, workspacePath };
}
