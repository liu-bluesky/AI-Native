<template>
  <ProjectWorkspaceBlock eyebrow="Git" title="代码仓库">
    <template #actions>
      <el-button
        type="primary"
        size="small"
        :disabled="!canManageProject"
        @click="openRepositoryDialog()"
      >
        添加仓库
      </el-button>
    </template>

    <el-alert
      class="git-panel__alert"
      title="这里维护项目关联的代码仓库元数据；凭据只保存引用标识，后续自动提交会基于仓库、分支和凭据引用做独立确认。"
      type="info"
      :closable="false"
      show-icon
    />

    <el-table
      v-loading="repositoryLoading"
      :data="codeRepositories"
      stripe
      class="git-panel__table"
    >
      <el-table-column label="仓库" min-width="220">
        <template #default="{ row }">
          <div class="git-panel__repo-main">
            <div class="git-panel__repo-head">
              <strong>{{ row.name || row.id }}</strong>
              <el-tag size="small" effect="plain" :type="row.enabled ? 'success' : 'info'">
                {{ row.enabled ? "启用" : "停用" }}
              </el-tag>
            </div>
            <span>{{ row.description || "未填写说明" }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Git 地址" min-width="280">
        <template #default="{ row }">
          <div class="git-panel__url">
            <code>{{ row.repo_url || "-" }}</code>
            <el-button text size="small" :disabled="!row.repo_url" @click="copyRepositoryUrl(row)">
              复制
            </el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="默认分支" width="120">
        <template #default="{ row }">
          <el-tag effect="plain" type="info">{{ row.default_branch || "main" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="本地路径" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.local_path || "-" }}</template>
      </el-table-column>
      <el-table-column label="凭据引用" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.credential_ref || "-" }}</template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="140">
        <template #default="{ row }">{{ formatRelativeTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="150" fixed="right">
        <template #default="{ row }">
          <el-button
            text
            type="primary"
            size="small"
            :disabled="!canManageProject"
            @click="openRepositoryDialog(row)"
          >
            编辑
          </el-button>
          <el-button
            text
            type="danger"
            size="small"
            :disabled="!canManageProject"
            @click="deleteCodeRepository(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty
      v-if="!repositoryLoading && !codeRepositories.length"
      description="当前项目还没有维护代码仓库"
      :image-size="60"
    />

    <el-dialog
      v-model="showRepositoryDialog"
      :title="editingRepositoryId ? '编辑代码仓库' : '添加代码仓库'"
      width="640px"
    >
      <el-form :model="repositoryForm" label-width="104px">
        <el-form-item label="仓库名称" required>
          <el-input v-model="repositoryForm.name" placeholder="例如 PC 后台 / 移动端 / API 服务" />
        </el-form-item>
        <el-form-item label="Git 地址" required>
          <el-input
            v-model="repositoryForm.repo_url"
            placeholder="https://github.com/org/repo.git 或 git@host:org/repo.git"
          />
        </el-form-item>
        <el-form-item label="默认分支">
          <el-input v-model="repositoryForm.default_branch" placeholder="main / master / develop" />
        </el-form-item>
        <el-form-item label="本地路径">
          <el-input
            v-model="repositoryForm.local_path"
            readonly
            placeholder="可选，用于后续自动提交定位工作区"
            @click="selectRepositoryLocalPath"
          >
            <template #append>
              <el-button @click.stop="selectRepositoryLocalPath">选择</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="凭据引用">
          <el-input v-model="repositoryForm.credential_ref" placeholder="可选，例如 github-main-token" />
          <div class="git-panel__help">这里只保存凭据引用，不保存真实 token 或密码。</div>
        </el-form-item>
        <el-form-item label="仓库说明">
          <el-input
            v-model="repositoryForm.description"
            type="textarea"
            :rows="3"
            placeholder="补充仓库用途、端类型或提交注意事项"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="repositoryForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRepositoryDialog = false">取消</el-button>
        <el-button type="primary" :loading="repositorySaving" @click="saveCodeRepository">
          保存
        </el-button>
      </template>
    </el-dialog>
  </ProjectWorkspaceBlock>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import ProjectWorkspaceBlock from "@/components/project-workspace/ProjectWorkspaceBlock.vue";
import { pickWorkspaceDirectory } from "@/utils/workspace-picker.js";
import {
  getLocalProjectRelations,
  updateLocalProjectRelations,
} from "@/services/local-project-repository.js";

const props = defineProps({
  projectId: { type: String, required: true },
  project: { type: Object, default: null },
  canManageProject: { type: Boolean, default: false },
  manageBlockedMessage: { type: String, default: "当前账号无权修改项目" },
});

const emit = defineEmits(["repositories-updated"]);

const repositoryLoading = ref(false);
const repositorySaving = ref(false);
const showRepositoryDialog = ref(false);
const editingRepositoryId = ref("");
const codeRepositories = ref([]);
const repositoryForm = ref(createEmptyRepositoryForm());

function createEmptyRepositoryForm(localPath = "") {
  return {
    name: "",
    repo_url: "",
    default_branch: "main",
    description: "",
    local_path: String(localPath || "").trim(),
    credential_ref: "",
    enabled: true,
  };
}

function defaultRepositoryLocalPath() {
  return String(props.project?.workspace_path || "").trim();
}

function formatRelativeTime(isoString) {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "";
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function normalizeCodeRepository(item) {
  return {
    id: String(item?.id || "").trim(),
    project_id: String(item?.project_id || "").trim(),
    name: String(item?.name || "").trim(),
    repo_url: String(item?.repo_url || "").trim(),
    repo_type: String(item?.repo_type || "git").trim() || "git",
    default_branch: String(item?.default_branch || "").trim() || "main",
    description: String(item?.description || "").trim(),
    local_path: String(item?.local_path || "").trim(),
    credential_ref: String(item?.credential_ref || "").trim(),
    enabled: item?.enabled !== false,
    created_by: String(item?.created_by || "").trim(),
    created_at: String(item?.created_at || "").trim(),
    updated_at: String(item?.updated_at || "").trim(),
  };
}

function fetchCodeRepositories() {
  const effectiveProjectId = String(props.projectId || "").trim();
  if (!effectiveProjectId) {
    codeRepositories.value = [];
    return;
  }
  repositoryLoading.value = true;
  try {
    const relations = getLocalProjectRelations(effectiveProjectId);
    codeRepositories.value = Array.isArray(relations.code_repositories)
      ? relations.code_repositories.map(normalizeCodeRepository).filter((item) => item.id)
      : [];
  } finally {
    repositoryLoading.value = false;
  }
}

function resetRepositoryForm() {
  editingRepositoryId.value = "";
  repositoryForm.value = createEmptyRepositoryForm(defaultRepositoryLocalPath());
}

function openRepositoryDialog(repository = null) {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  if (repository?.id) {
    const normalized = normalizeCodeRepository(repository);
    editingRepositoryId.value = normalized.id;
    repositoryForm.value = {
      name: normalized.name,
      repo_url: normalized.repo_url,
      default_branch: normalized.default_branch || "main",
      description: normalized.description,
      local_path: normalized.local_path,
      credential_ref: normalized.credential_ref,
      enabled: normalized.enabled,
    };
  } else {
    resetRepositoryForm();
  }
  showRepositoryDialog.value = true;
}

async function selectRepositoryLocalPath() {
  const picked = await pickWorkspaceDirectory(repositoryForm.value.local_path, {
    title: "选择代码仓库本地路径",
    manualFallback: false,
  });
  if (picked === null) return;
  repositoryForm.value.local_path = picked;
}

function buildRepositoryPayload() {
  return {
    name: String(repositoryForm.value.name || "").trim(),
    repo_url: String(repositoryForm.value.repo_url || "").trim(),
    repo_type: "git",
    default_branch: String(repositoryForm.value.default_branch || "").trim() || "main",
    description: String(repositoryForm.value.description || "").trim(),
    local_path: String(repositoryForm.value.local_path || "").trim(),
    credential_ref: String(repositoryForm.value.credential_ref || "").trim(),
    enabled: repositoryForm.value.enabled !== false,
  };
}

async function saveCodeRepository() {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    showRepositoryDialog.value = false;
    return;
  }
  const payload = buildRepositoryPayload();
  if (!payload.name) {
    ElMessage.warning("请输入仓库名称");
    return;
  }
  if (!payload.repo_url) {
    ElMessage.warning("请输入 Git 地址");
    return;
  }
  const effectiveProjectId = String(props.projectId || "").trim();
  if (!effectiveProjectId) return;

  repositorySaving.value = true;
  try {
    const relations = getLocalProjectRelations(effectiveProjectId);
    const now = new Date().toISOString();
    const existing = Array.isArray(relations.code_repositories)
      ? relations.code_repositories.find((item) => item.id === editingRepositoryId.value)
      : null;
    const repository = normalizeCodeRepository({
      ...payload,
      id: editingRepositoryId.value || `local-repository-${Date.now()}`,
      project_id: effectiveProjectId,
      created_at: existing?.created_at || now,
      updated_at: now,
    });
    const repositories = Array.isArray(relations.code_repositories)
      ? relations.code_repositories.filter((item) => item.id !== repository.id)
      : [];
    updateLocalProjectRelations(effectiveProjectId, {
      code_repositories: [...repositories, repository],
    });
    ElMessage.success(editingRepositoryId.value ? "代码仓库已更新" : "代码仓库已添加");
    showRepositoryDialog.value = false;
    resetRepositoryForm();
    fetchCodeRepositories();
    emit("repositories-updated");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存代码仓库失败");
  } finally {
    repositorySaving.value = false;
  }
}

async function deleteCodeRepository(repository) {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  const repositoryId = String(repository?.id || "").trim();
  if (!repositoryId) return;
  try {
    await ElMessageBox.confirm(
      `确定删除代码仓库「${repository?.name || repositoryId}」吗？这只会删除项目里的仓库元数据，不会删除真实 Git 仓库。`,
      "删除代码仓库",
      {
        type: "warning",
        confirmButtonText: "删除",
      },
    );
  } catch {
    return;
  }
  const effectiveProjectId = String(props.projectId || "").trim();
  if (!effectiveProjectId) return;
  repositorySaving.value = true;
  try {
    const relations = getLocalProjectRelations(effectiveProjectId);
    updateLocalProjectRelations(effectiveProjectId, {
      code_repositories: (relations.code_repositories || []).filter(
        (item) => String(item?.id || "") !== repositoryId,
      ),
    });
    ElMessage.success("代码仓库已删除");
    fetchCodeRepositories();
    emit("repositories-updated");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除代码仓库失败");
  } finally {
    repositorySaving.value = false;
  }
}

async function copyRepositoryUrl(repository) {
  const repoUrl = String(repository?.repo_url || "").trim();
  if (!repoUrl) return;
  try {
    await navigator.clipboard.writeText(repoUrl);
    ElMessage.success("Git 地址已复制");
  } catch {
    ElMessage.error("复制失败");
  }
}

function handleRelationsUpdated() {
  fetchCodeRepositories();
}

watch(
  () => [props.projectId, props.project?.workspace_path],
  () => fetchCodeRepositories(),
  { immediate: true },
);

onMounted(() => {
  window.addEventListener("local-project-relations-updated", handleRelationsUpdated);
});

onBeforeUnmount(() => {
  window.removeEventListener("local-project-relations-updated", handleRelationsUpdated);
});
</script>

<style scoped>
.git-panel__alert {
  margin-bottom: 16px;
}

.git-panel__table {
  margin-top: 8px;
  width: 100%;
}

.git-panel__repo-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.git-panel__repo-head,
.git-panel__url {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.git-panel__repo-head strong,
.git-panel__url code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.git-panel__repo-head strong {
  color: #0f172a;
  font-weight: 600;
}

.git-panel__repo-main span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.git-panel__url code {
  color: #334155;
  font-size: 12px;
}

.git-panel__help {
  margin-top: 10px;
  color: #6b7280;
  font-size: 12px;
  line-height: 1.5;
}
</style>
