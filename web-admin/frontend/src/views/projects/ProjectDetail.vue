<template>
  <main v-loading="loading" class="folder-settings-page">
    <header class="folder-settings-page__header">
      <div class="folder-settings-page__heading">
        <div class="folder-settings-page__eyebrow">FOLDER</div>
        <h1>{{ pageTitle }}</h1>
        <p>管理这个文件夹的显示名称和本机路径</p>
      </div>
      <div class="folder-settings-page__header-actions">
        <el-button :disabled="!hasProject" @click="openProjectChat">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI 对话</span>
        </el-button>
        <el-button aria-label="返回文件夹列表" @click="openProjectList">
          <el-icon><ArrowLeft /></el-icon>
          <span>返回文件夹</span>
        </el-button>
      </div>
    </header>

    <section v-if="hasProject" class="folder-settings-page__content" aria-labelledby="folder-settings-title">
      <div class="folder-settings-form">
        <div class="folder-settings-form__heading">
          <h2 id="folder-settings-title">文件夹设置</h2>
        </div>

        <el-form label-position="top" @submit.prevent="saveProject">
          <el-form-item label="项目名称">
            <el-input
              v-model="form.name"
              maxlength="80"
              show-word-limit
              autocomplete="off"
              placeholder="输入显示名称"
              @keyup.enter="saveProject"
            />
          </el-form-item>

          <el-form-item label="文件夹">
            <div class="folder-settings-path">
              <el-input
                v-model="form.workspacePath"
                autocomplete="off"
                placeholder="选择本机文件夹"
              >
                <template #prefix>
                  <el-icon><FolderOpened /></el-icon>
                </template>
              </el-input>
              <el-button
                :loading="pickingWorkspace"
                :disabled="saving"
                @click="selectWorkspaceDirectory"
              >
                选择文件夹
              </el-button>
            </div>
          </el-form-item>

          <div class="folder-settings-form__actions">
            <el-button
              type="primary"
              :loading="saving"
              :disabled="pickingWorkspace"
              @click="saveProject"
            >
              <el-icon><Check /></el-icon>
              <span>保存</span>
            </el-button>
          </div>
        </el-form>
      </div>

      <div class="folder-settings-module">
        <ProjectGitRepositoriesPanel
          :project-id="projectId"
          :project="project"
          :can-manage-project="canManageProject"
          :manage-blocked-message="manageBlockedMessage"
        />
      </div>

      <div class="folder-settings-module">
        <ProjectDeploySettingsPanel
          :project-id="projectId"
          :project="project"
          :can-manage-project="canManageProject"
          :manage-blocked-message="manageBlockedMessage"
          @project-updated="handleProjectUpdated"
        />
      </div>
    </section>

    <section v-else-if="!loading" class="folder-settings-page__empty">
      <el-empty description="找不到这个文件夹项目" :image-size="88">
        <el-button type="primary" @click="openProjectList">返回文件夹列表</el-button>
      </el-empty>
    </section>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { ArrowLeft, ChatDotRound, Check, FolderOpened } from "@element-plus/icons-vue";
import { openRouteInDesktop } from "@/utils/desktop-app-bridge.js";
import { setStoredProjectContextId } from "@/utils/desktop-shell.js";
import { pickWorkspaceDirectory } from "@/utils/workspace-picker.js";
import {
  getLocalProject,
  getLocalWorkspaceProjectByPath,
  getWorkspaceFolderName,
  isProjectNamePlaceholder,
  updateLocalProjectRelations,
  upsertLocalProject,
} from "@/services/local-project-repository.js";
import ProjectGitRepositoriesPanel from "@/components/project-workspace/ProjectGitRepositoriesPanel.vue";
import ProjectDeploySettingsPanel from "@/components/project-workspace/ProjectDeploySettingsPanel.vue";

const route = useRoute();
const router = useRouter();
const projectId = computed(() => String(route.params.id || "").trim());
const loading = ref(false);
const saving = ref(false);
const pickingWorkspace = ref(false);
const project = ref(null);
const form = reactive({
  name: "",
  workspacePath: "",
});

const hasProject = computed(() => Boolean(project.value?.id));
const canManageProject = computed(() => project.value?.can_manage !== false);
const manageBlockedMessage = "当前账号无权修改项目";
const pageTitle = computed(() => {
  const name = String(form.name || "").trim();
  return name || getWorkspaceFolderName(form.workspacePath) || "文件夹设置";
});

function projectDisplayName(item = {}) {
  const id = String(item?.id || "").trim();
  const name = String(item?.name || "").trim();
  if (!isProjectNamePlaceholder(name, id)) return name;
  return getWorkspaceFolderName(item?.workspace_path) || "";
}

function loadProject() {
  loading.value = true;
  try {
    const currentProjectId = projectId.value;
    const current = currentProjectId ? getLocalProject(currentProjectId) : null;
    project.value = current;
    form.name = current ? projectDisplayName(current) : "";
    form.workspacePath = String(current?.workspace_path || "").trim();
    if (currentProjectId) {
      setStoredProjectContextId(currentProjectId);
    }
  } finally {
    loading.value = false;
  }
}

async function selectWorkspaceDirectory() {
  if (pickingWorkspace.value) return;
  pickingWorkspace.value = true;
  try {
    const picked = await pickWorkspaceDirectory(form.workspacePath, {
      title: "选择项目文件夹",
    });
    const workspacePath = String(picked || "").trim();
    if (!workspacePath) return;
    form.workspacePath = workspacePath;
    if (!String(form.name || "").trim()) {
      form.name = getWorkspaceFolderName(workspacePath);
    }
  } catch (error) {
    ElMessage.error(String(error?.message || error || "选择文件夹失败").trim());
  } finally {
    pickingWorkspace.value = false;
  }
}

async function saveProject() {
  if (saving.value || !hasProject.value) return;
  const id = projectId.value;
  const name = String(form.name || "").trim();
  const workspacePath = String(form.workspacePath || "").trim();
  if (isProjectNamePlaceholder(name, id)) {
    ElMessage.warning("请输入项目名称，不能使用内部项目 ID");
    return;
  }
  if (!workspacePath) {
    ElMessage.warning("请选择文件夹");
    return;
  }

  const existingWorkspace = getLocalWorkspaceProjectByPath(workspacePath);
  if (existingWorkspace && existingWorkspace.id !== id) {
    ElMessage.warning("该文件夹已在列表中，请从文件夹列表打开它");
    return;
  }

  saving.value = true;
  try {
    const current = getLocalProject(id);
    if (!current) {
      throw new Error("文件夹项目不存在");
    }
    upsertLocalProject({
      ...current,
      id,
      name,
      workspace_path: workspacePath,
      created_by: current.created_by || "local",
      can_manage: current.can_manage ?? true,
      updated_at: new Date().toISOString(),
    });
    updateLocalProjectRelations(id, { workspace_path: workspacePath });
    project.value = getLocalProject(id);
    form.name = projectDisplayName(project.value || {});
    form.workspacePath = String(project.value?.workspace_path || "").trim();
    setStoredProjectContextId(id);
    ElMessage.success("文件夹设置已保存");
  } catch (error) {
    ElMessage.error(String(error?.message || error || "保存失败").trim());
  } finally {
    saving.value = false;
  }
}

function openProjectChat() {
  const id = String(project.value?.id || projectId.value || "").trim();
  if (!id) return;
  setStoredProjectContextId(id);
  void openRouteInDesktop(
    router,
    { path: "/ai/chat", query: { project_id: id } },
    {
      mode: "new-window",
      appId: "chat",
      title: pageTitle.value || "AI 对话",
      eyebrow: "AI Workspace",
    },
  );
}

function openProjectList() {
  void openRouteInDesktop(router, "/projects", {
    mode: "focus-or-open",
    appId: "projects",
    title: "文件夹",
    eyebrow: "Folders",
  });
}

function handleProjectUpdated() {
  loadProject();
}

function handleProjectStorage(event) {
  if (event?.key !== "local_projects_cache") return;
  const latest = getLocalProject(projectId.value);
  if (
    !latest ||
    latest.name !== project.value?.name ||
    latest.workspace_path !== project.value?.workspace_path
  ) {
    loadProject();
  }
}

watch(projectId, loadProject, { immediate: true });

onMounted(() => {
  window.addEventListener("local-projects-updated", handleProjectUpdated);
  window.addEventListener("storage", handleProjectStorage);
});

onBeforeUnmount(() => {
  window.removeEventListener("local-projects-updated", handleProjectUpdated);
  window.removeEventListener("storage", handleProjectStorage);
});
</script>

<style scoped>
.folder-settings-page {
  width: min(100%, 1120px);
  margin: 0 auto;
  padding: 24px 20px 40px;
  color: #1f2937;
}

 .folder-settings-page__header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid #dfe5ec;
}

 .folder-settings-page__heading {
  min-width: 0;
}

 .folder-settings-page__eyebrow {
  margin-bottom: 8px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
}

 .folder-settings-page__heading h1 {
  overflow: hidden;
  margin: 0;
  color: #111827;
  font-size: 28px;
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

 .folder-settings-page__heading p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 14px;
  line-height: 1.5;
}

 .folder-settings-page__header-actions,
.folder-settings-form__actions,
.folder-settings-path {
  display: flex;
  align-items: center;
  gap: 8px;
}

 .folder-settings-page__header-actions {
  flex-shrink: 0;
}

 .folder-settings-page__header-actions :deep(.el-icon),
.folder-settings-form__actions :deep(.el-icon) {
  margin-right: 5px;
}

 .folder-settings-page__content {
  padding-top: 28px;
  display: flex;
  flex-direction: column;
  gap: 32px;
}

 .folder-settings-form {
  max-width: 680px;
}

.folder-settings-module {
  padding-top: 24px;
  border-top: 1px solid #dfe5ec;
}

 .folder-settings-form__heading {
  margin-bottom: 20px;
}

 .folder-settings-form__heading h2 {
  margin: 0;
  color: #334155;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.35;
}

 .folder-settings-path :deep(.el-input) {
  min-width: 0;
  flex: 1 1 auto;
}

 .folder-settings-path > .el-button {
  flex: 0 0 auto;
}

 .folder-settings-form__actions {
  justify-content: flex-end;
  padding-top: 8px;
}

 .folder-settings-page__empty {
  padding: 40px 0;
}

@media (max-width: 640px) {
  .folder-settings-page {
    padding: 18px 14px 32px;
  }

  .folder-settings-page__header {
    align-items: stretch;
    flex-direction: column;
  }

  .folder-settings-page__header-actions {
    flex-wrap: wrap;
  }

  .folder-settings-page__header-actions > .el-button {
    flex: 1 1 auto;
  }

  .folder-settings-path {
    align-items: stretch;
    flex-direction: column;
  }

  .folder-settings-path > .el-button {
    width: 100%;
  }

  .folder-settings-form__actions > .el-button {
    width: 100%;
  }
}
</style>
