<template>
  <main v-loading="loading" class="workspace-list-page">
    <header class="workspace-list-page__header">
      <div class="workspace-list-page__heading">
        <div class="workspace-list-page__eyebrow">WORKSPACES</div>
        <h1>文件夹</h1>
        <p>最近打开的工作区</p>
      </div>
      <div class="workspace-list-page__actions">
        <el-button
          type="primary"
          :loading="openingWorkspace"
          @click="selectWorkspace"
        >
          <el-icon><FolderOpened /></el-icon>
          <span>打开文件夹</span>
        </el-button>
        <el-tooltip content="刷新列表" placement="bottom">
          <el-button circle aria-label="刷新列表" @click="fetchWorkspaces">
            <el-icon><Refresh /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
    </header>

    <section class="workspace-list-page__content" aria-labelledby="recent-workspaces-title">
      <div class="workspace-list-page__toolbar">
        <h2 id="recent-workspaces-title">最近文件夹</h2>
        <el-input
          v-model="searchQuery"
          class="workspace-list-page__search"
          clearable
          placeholder="搜索文件夹或路径"
          aria-label="搜索文件夹或路径"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>

      <div v-if="filteredWorkspaces.length" class="workspace-list" role="list">
        <article
          v-for="workspace in filteredWorkspaces"
          :key="workspace.id"
          class="workspace-list__item"
          role="listitem"
        >
          <div class="workspace-list__icon" aria-hidden="true">
            <el-icon><FolderOpened /></el-icon>
          </div>
          <div class="workspace-list__main">
            <button
              class="workspace-list__open"
              type="button"
              @click="openWorkspace(workspace)"
            >
              {{ workspaceName(workspace) }}
            </button>
            <p :title="workspace.workspace_path">{{ workspace.workspace_path }}</p>
          </div>
          <div class="workspace-list__actions">
            <el-tooltip content="在对话中打开" placement="bottom">
              <el-button
                circle
                text
                aria-label="在对话中打开"
                @click="openWorkspace(workspace)"
              >
                <el-icon><ChatDotRound /></el-icon>
              </el-button>
            </el-tooltip>
            <el-dropdown
              trigger="click"
              @command="(command) => handleWorkspaceCommand(workspace, command)"
            >
              <el-button circle text aria-label="更多操作" title="更多操作">
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">
                    <el-icon><EditPen /></el-icon>
                    <span>重命名</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="settings">
                    <el-icon><Setting /></el-icon>
                    <span>文件夹设置</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="remove" divided>
                    <el-icon><Delete /></el-icon>
                    <span>从列表移除</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </article>
      </div>

      <el-empty
        v-else-if="!loading"
        :description="emptyDescription"
        :image-size="92"
      >
        <el-button type="primary" :loading="openingWorkspace" @click="selectWorkspace">
          打开文件夹
        </el-button>
      </el-empty>
    </section>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  ChatDotRound,
  Delete,
  EditPen,
  FolderOpened,
  MoreFilled,
  Refresh,
  Setting,
  Search,
} from "@element-plus/icons-vue";
import {
  getWorkspaceFolderName,
  getLocalWorkspaceProjectByPath,
  isProjectNamePlaceholder,
  openLocalWorkspaceProject,
  readLocalWorkspaceProjects,
  renameLocalWorkspaceProject,
  removeLocalWorkspaceProject,
  upsertLocalProject,
} from "@/services/local-project-repository.js";
import { readLocalSystemConfig } from "@/services/local-system-config.js";
import { DEFAULT_DESKTOP_AGENT_GLOBAL_PROMPT } from "@/config/desktopAgentPrompts.js";
import {
  hasNativeDesktopBridge,
  readNativeWorkspaceFile,
  writeNativeWorkspaceFile,
} from "@/utils/native-desktop-bridge.js";
import { pickWorkspaceDirectory } from "@/utils/workspace-picker.js";

const DEFAULT_AI_ENTRY_FILE = "AIENTRY.md";

const router = useRouter();
const loading = ref(false);
const openingWorkspace = ref(false);
const searchQuery = ref("");
const workspaces = ref([]);

const filteredWorkspaces = computed(() => {
  const query = String(searchQuery.value || "").trim().toLowerCase();
  if (!query) return workspaces.value;
  return workspaces.value.filter((workspace) =>
    [workspaceName(workspace), workspace.workspace_path]
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
});

const emptyDescription = computed(() =>
  String(searchQuery.value || "").trim()
    ? "没有匹配的文件夹"
    : "还没有打开过文件夹",
);

function workspaceName(workspace) {
  const name = String(workspace?.name || "").trim();
  if (!isProjectNamePlaceholder(name, workspace?.id)) return name;
  return getWorkspaceFolderName(workspace?.workspace_path) || "未命名文件夹";
}

function isWorkspaceFileMissing(error) {
  return /not found|no such file|os error 2|系统找不到指定的文件|找不到指定的文件|不存在/i.test(
    String(error?.message || error?.detail || error || ""),
  );
}

async function initializeProjectAiEntryFile(project) {
  const projectId = String(project?.id || "").trim();
  const workspacePath = String(project?.workspace_path || "").trim();
  if (!projectId || !workspacePath) {
    return;
  }
  if (!hasNativeDesktopBridge()) return;

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
      return;
    }
  } catch (error) {
    if (!isWorkspaceFileMissing(error)) {
      throw error;
    }
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
}

async function fetchWorkspaces() {
  loading.value = true;
  try {
    workspaces.value = readLocalWorkspaceProjects();
  } finally {
    loading.value = false;
  }
}

async function selectWorkspace() {
  if (openingWorkspace.value) return;
  openingWorkspace.value = true;
  try {
    const workspacePath = await pickWorkspaceDirectory("", {
      title: "打开文件夹",
    });
    if (!workspacePath) return;
    const existingWorkspace = getLocalWorkspaceProjectByPath(workspacePath);
    const workspace = openLocalWorkspaceProject(workspacePath);
    if (!workspace?.id) {
      throw new Error("无法保存文件夹工作区");
    }
    await initializeProjectAiEntryFile(workspace);
    await openWorkspaceSettings(workspace);
  } catch (error) {
    ElMessage.error(String(error?.message || error || "打开文件夹失败").trim());
  } finally {
    openingWorkspace.value = false;
  }
}

async function openWorkspace(workspace) {
  const workspacePath = String(workspace?.workspace_path || "").trim();
  if (!workspacePath) {
    ElMessage.warning("该文件夹缺少工作区路径");
    return;
  }
  try {
    const currentWorkspace = openLocalWorkspaceProject(workspacePath);
    if (!currentWorkspace?.id) {
      throw new Error("无法打开文件夹工作区");
    }
    await initializeProjectAiEntryFile(currentWorkspace);
    await openProjectChat(currentWorkspace);
  } catch (error) {
    ElMessage.error(String(error?.message || error || "打开文件夹失败").trim());
  }
}

async function openProjectChat(workspace) {
  const projectId = String(workspace?.id || "").trim();
  if (!projectId) return;
  try {
    window.localStorage?.setItem("project_id", projectId);
  } catch {
    // The route query remains sufficient when local storage is unavailable.
  }
  await router.push({
    path: "/ai/chat",
    query: { project_id: projectId },
  });
}

function handleWorkspaceCommand(workspace, command) {
  if (command === "rename") {
    void renameWorkspace(workspace);
    return;
  }
  if (command === "settings") {
    void openWorkspaceSettings(workspace);
    return;
  }
  if (command === "remove") {
    void removeWorkspace(workspace);
  }
}

async function renameWorkspace(workspace) {
  const projectId = String(workspace?.id || "").trim();
  if (!projectId) {
    ElMessage.warning("该文件夹无法重命名");
    return;
  }
  let value = "";
  try {
    ({ value } = await ElMessageBox.prompt("", "重命名文件夹", {
      inputValue: workspaceName(workspace),
      inputPlaceholder: "输入显示名称",
      confirmButtonText: "保存",
      cancelButtonText: "取消",
      inputValidator: (input) =>
        String(input || "").trim() ? true : "请输入名称",
    }));
  } catch {
    return;
  }
  const name = String(value || "").trim();
  if (isProjectNamePlaceholder(name, projectId)) {
    ElMessage.warning("请输入有效的文件夹名称");
    return;
  }
  if (!renameLocalWorkspaceProject(projectId, name)) {
    ElMessage.error("重命名失败");
    return;
  }
  await fetchWorkspaces();
  ElMessage.success("名称已保存");
}

async function openWorkspaceSettings(workspace) {
  const projectId = String(workspace?.id || "").trim();
  if (!projectId) return;
  await router.push(`/projects/${encodeURIComponent(projectId)}`);
}

async function removeWorkspace(workspace) {
  const name = workspaceName(workspace);
  try {
    await ElMessageBox.confirm(
      `确认从最近文件夹列表移除「${name}」？磁盘文件夹和已有对话不会被删除。`,
      "移除文件夹",
      {
        type: "warning",
        confirmButtonText: "移除",
        cancelButtonText: "取消",
      },
    );
  } catch {
    return;
  }

  const projectId = String(workspace?.id || "").trim();
  removeLocalWorkspaceProject(projectId);
  try {
    if (window.localStorage?.getItem("project_id") === projectId) {
      window.localStorage.removeItem("project_id");
    }
  } catch {
    // Removing the recent-folder association still succeeds without storage access.
  }
  await fetchWorkspaces();
  ElMessage.success("已从最近文件夹移除");
}

function handleWorkspaceListUpdated() {
  void fetchWorkspaces();
}

function handleWorkspaceStorage(event) {
  if (
    event?.key !== null &&
    event?.key !== "local_projects_cache" &&
    event?.key !== "local_hidden_workspace_project_ids"
  ) {
    return;
  }
  void fetchWorkspaces();
}

onMounted(() => {
  void fetchWorkspaces();
  window.addEventListener("local-projects-updated", handleWorkspaceListUpdated);
  window.addEventListener(
    "local-workspace-projects-updated",
    handleWorkspaceListUpdated,
  );
  window.addEventListener("storage", handleWorkspaceStorage);
});

onBeforeUnmount(() => {
  window.removeEventListener(
    "local-projects-updated",
    handleWorkspaceListUpdated,
  );
  window.removeEventListener(
    "local-workspace-projects-updated",
    handleWorkspaceListUpdated,
  );
  window.removeEventListener("storage", handleWorkspaceStorage);
});
</script>

<style scoped>
.workspace-list-page {
  width: 100%;
  min-height: 100dvh;
  box-sizing: border-box;
  margin: 0 auto;
  padding: 24px max(20px, calc((100% - 1080px) / 2 + 20px)) 40px;
  color: #1f2937;
  background: var(
    --page-bg,
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%)
  );
}

 .workspace-list-page__header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid #dfe5ec;
}

 .workspace-list-page__heading {
  min-width: 0;
}

 .workspace-list-page__eyebrow {
  margin-bottom: 8px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
}

 .workspace-list-page__heading h1 {
  margin: 0;
  color: #111827;
  font-size: 28px;
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1.2;
}

 .workspace-list-page__heading p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 14px;
  line-height: 1.5;
}

 .workspace-list-page__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

 .workspace-list-page__actions :deep(.el-icon) {
  margin-right: 6px;
}

 .workspace-list-page__actions :deep(.el-button.is-circle .el-icon) {
  margin-right: 0;
}

 .workspace-list-page__content {
  padding-top: 24px;
}

 .workspace-list-page__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
}

 .workspace-list-page__toolbar h2 {
  margin: 0;
  color: #334155;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0;
}

 .workspace-list-page__search {
  width: min(100%, 320px);
}

 .workspace-list {
  border-top: 1px solid #e2e8f0;
}

 .workspace-list__item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 76px;
  border-bottom: 1px solid #e2e8f0;
  transition: background-color 160ms ease;
}

 .workspace-list__item:hover {
  background: #f8fafc;
}

 .workspace-list__icon {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 6px;
  background: #e0f2fe;
  color: #0369a1;
  font-size: 18px;
}

 .workspace-list__main {
  min-width: 0;
  padding: 12px 0;
}

 .workspace-list__open {
  display: block;
  max-width: 100%;
  overflow: hidden;
  padding: 0;
  border: 0;
  background: transparent;
  color: #1e293b;
  cursor: pointer;
  font: inherit;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

 .workspace-list__open:hover,
 .workspace-list__open:focus-visible {
  color: #2563eb;
  outline: none;
}

 .workspace-list__main p {
  overflow: hidden;
  margin: 4px 0 0;
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

 .workspace-list__actions {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-right: 4px;
}

 .workspace-list__actions :deep(.el-icon) {
  margin-right: 0;
}

@media (max-width: 640px) {
  .workspace-list-page {
    padding: 18px 14px 32px;
  }

  .workspace-list-page__header,
  .workspace-list-page__toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .workspace-list-page__actions {
    justify-content: flex-start;
  }

  .workspace-list-page__search {
    width: 100%;
  }

  .workspace-list__item {
    grid-template-columns: 32px minmax(0, 1fr) auto;
    gap: 8px;
  }

  .workspace-list__main p {
    max-width: 100%;
  }
}
</style>
