<template>
  <div v-loading="loading" class="project-list-page">
    <ProjectAppHeader
      eyebrow="Project Space"
      title="项目桌面"
      :description="projectListDescription"
      panel-eyebrow="Quick Actions"
      panel-title="项目入口"
      panel-description="新建、筛选和进入详情都集中在这个桌面应用窗口中处理。"
      :badges="projectListBadges"
      :stats="projectListStats"
    >
      <template #actions>
        <div class="project-list-hero-actions">
          <el-button
            v-if="showProjectCreateEntry"
            type="primary"
            @click="openCreate"
          >
            新建项目
          </el-button>
          <el-button plain @click="handleSearch">刷新列表</el-button>
        </div>
      </template>
    </ProjectAppHeader>

    <ProjectAppSection
      eyebrow="Workspace Browser"
      title="项目列表"
      description="把项目视作桌面里的独立应用条目，先快速筛选，再进入详情工作区。"
      class="project-list-page__section"
    >
      <div class="filter-panel">
        <div class="filter-panel__fields">
          <el-input
            v-model="filters.name"
            clearable
            placeholder="筛选项目名称"
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          />
          <el-input
            v-model="filters.createdBy"
            clearable
            placeholder="筛选创建人"
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          />
        </div>
        <div class="filter-panel__actions">
          <el-button type="primary" plain @click="handleSearch">筛选</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </div>

      <div class="project-list-grid-metrics">
        <article
          v-for="item in projectListStats"
          :key="item.key"
          class="project-list-grid-metrics__item"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.meta }}</small>
        </article>
      </div>

      <div class="project-list-table-shell">
        <el-table :data="projects" stripe>
      <el-table-column prop="id" label="项目 ID" width="150" />
      <el-table-column prop="name" label="项目名称" min-width="200" show-overflow-tooltip />
      <el-table-column label="项目类型" width="140" align="center">
        <template #default="{ row }">
          <el-tag :type="getProjectTypeTagType(row.type)">
            {{ getProjectTypeLabel(row.type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        v-if="showProjectLocationFields"
        prop="workspace_path"
        label="工作区路径"
        width="220"
        show-overflow-tooltip
      >
        <template #default="{ row }">{{ row.workspace_path || '-' }}</template>
      </el-table-column>
      <el-table-column
        v-if="showProjectLocationFields"
        prop="ai_entry_file"
        label="AI 入口文件"
        width="220"
        show-overflow-tooltip
      >
        <template #default="{ row }">{{ row.ai_entry_file || '-' }}</template>
      </el-table-column>
      <el-table-column prop="description" label="描述" show-overflow-tooltip />
      <el-table-column label="创建人" width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.created_by || '-' }}</template>
      </el-table-column>
      <el-table-column label="成员数" width="90" align="center">
        <template #default="{ row }">{{ row.member_count || 0 }}</template>
      </el-table-column>
      <el-table-column label="MCP" width="100" align="center">
        <template #default="{ row }">
          <el-switch
            :model-value="!!row.mcp_enabled"
            :disabled="!canManageProject(row)"
            @change="(val) => patchProjectFlags(row, { mcp_enabled: !!val }, val ? '已开启项目 MCP' : '已关闭项目 MCP')"
          />
        </template>
      </el-table-column>
      <el-table-column label="反馈升级" width="120" align="center">
        <template #default="{ row }">
          <el-switch
            :model-value="!!row.feedback_upgrade_enabled"
            :disabled="!canManageProject(row)"
            @change="(val) => patchProjectFlags(row, { feedback_upgrade_enabled: !!val }, val ? '已开启反馈升级' : '已关闭反馈升级')"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="280" fixed="right" class-name="table-action-column">
        <template #default="{ row }">
          <el-button
            v-for="action in getPrimaryProjectActions(row)"
            :key="`${row.id}-${action.key}`"
            text
            :type="action.type"
            size="small"
            @click="handleProjectAction(row, action.key)"
          >
            {{ action.label }}
          </el-button>
          <el-dropdown
            v-if="getOverflowProjectActions(row).length"
            trigger="click"
            @command="(actionKey) => handleProjectAction(row, actionKey)"
          >
            <el-button text type="primary" size="small">更多</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="action in getOverflowProjectActions(row)"
                  :key="`${row.id}-${action.key}`"
                  :command="action.key"
                >
                  {{ action.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
        </el-table>
      </div>

      <div v-if="paginationTotal > 0" class="pagination-wrap">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, jumper, sizes"
          :page-sizes="[10, 20, 50]"
          :total="paginationTotal"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>

      <el-empty v-if="!projects.length && !loading" :description="emptyDescription" />
    </ProjectAppSection>

    <el-dialog v-if="showProjectCreateEntry" v-model="showCreateDialog" title="新建项目" width="520px">
      <el-form :model="createForm" label-width="110px">
        <el-form-item label="项目名称" required>
          <el-input v-model="createForm.name" placeholder="例如：web-admin" />
        </el-form-item>
        <el-form-item label="项目描述">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="3"
            placeholder="项目说明（可选）"
          />
        </el-form-item>
        <el-form-item label="项目类型">
          <el-select v-model="createForm.type" style="width: 100%">
            <el-option
              v-for="item in projectTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            >
              <div class="project-type-option">
                <div class="project-type-option__label">{{ item.label }}</div>
                <div class="project-type-option__desc">{{ item.description }}</div>
              </div>
            </el-option>
          </el-select>
          <div class="project-type-help">{{ getProjectTypeDescription(createForm.type) }}</div>
        </el-form-item>
        <el-form-item label="MCP 使用说明">
          <el-input
            v-model="createForm.mcp_instruction"
            type="textarea"
            :rows="4"
            placeholder="给外部模型看的接入说明，例如先读 usage guide，再看项目成员和工具"
          />
        </el-form-item>
        <el-form-item v-if="showProjectLocationFields" label="工作区路径">
          <el-input v-model="createForm.workspace_path" placeholder="可手动输入或点击选择目录">
            <template #append>
              <el-button @click="selectWorkspaceDirectory">选择目录</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item v-if="showProjectLocationFields" label="AI 入口文件">
          <el-input v-model="createForm.ai_entry_file" placeholder="如 .ai/ENTRY.md 或 /abs/path/to/ENTRY.md">
            <template #append>
              <el-button @click="selectCreateAiEntryFile">选择文件</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="启用 MCP">
          <el-switch v-model="createForm.mcp_enabled" />
        </el-form-item>
        <el-form-item label="反馈升级">
          <el-switch v-model="createForm.feedback_upgrade_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createProject">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑项目" width="520px">
      <el-form :model="editForm" label-width="110px">
        <el-form-item label="项目名称" required>
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="项目描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="项目类型">
          <el-select v-model="editForm.type" style="width: 100%">
            <el-option
              v-for="item in projectTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            >
              <div class="project-type-option">
                <div class="project-type-option__label">{{ item.label }}</div>
                <div class="project-type-option__desc">{{ item.description }}</div>
              </div>
            </el-option>
          </el-select>
          <div class="project-type-help">{{ getProjectTypeDescription(editForm.type) }}</div>
        </el-form-item>
        <el-form-item label="MCP 使用说明">
          <el-input
            v-model="editForm.mcp_instruction"
            type="textarea"
            :rows="4"
            placeholder="给外部模型看的接入说明，例如先读 usage guide，再看项目成员和工具"
          />
        </el-form-item>
        <el-form-item v-if="showProjectLocationFields" label="工作区路径">
          <el-input v-model="editForm.workspace_path" placeholder="可手动输入或点击选择目录">
            <template #append>
              <el-button @click="selectEditWorkspaceDirectory">选择目录</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item v-if="showProjectLocationFields" label="AI 入口文件">
          <el-input v-model="editForm.ai_entry_file" placeholder="如 .ai/ENTRY.md 或 /abs/path/to/ENTRY.md">
            <template #append>
              <el-button @click="selectEditAiEntryFile">选择文件</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="启用 MCP">
          <el-switch v-model="editForm.mcp_enabled" />
        </el-form-item>
        <el-form-item label="反馈升级">
          <el-switch v-model="editForm.feedback_upgrade_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="updateProject">保存</el-button>
      </template>
    </el-dialog>

    <UnifiedMcpAccessDialog
      v-model="showMcpDialog"
      :title="`统一 MCP 接入: ${currentProject?.name || ''}`"
      :project-id="currentProject?.id || ''"
      :project-label="currentProject?.name || currentProject?.id || ''"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import ProjectAppHeader from '@/components/project-workspace/ProjectAppHeader.vue'
import ProjectAppSection from '@/components/project-workspace/ProjectAppSection.vue'
import UnifiedMcpAccessDialog from '@/components/UnifiedMcpAccessDialog.vue'
import api from '@/utils/api.js'
import { openRouteInDesktop } from '@/utils/desktop-app-bridge.js'
import { hasPermission } from '@/utils/permissions.js'
import {
  pickWorkspaceDirectory as openWorkspaceDirectoryPicker,
  pickWorkspaceFile as openWorkspaceFilePicker,
  toWorkspaceRelativePath,
} from '@/utils/workspace-picker.js'

const PROJECT_CREATED_EVENT = 'project-created'
const router = useRouter()
const loading = ref(false)
const creating = ref(false)
const updating = ref(false)
const projects = ref([])
const filters = ref({
  name: '',
  createdBy: '',
})
const currentPage = ref(1)
const pageSize = ref(10)
const paginationTotal = ref(0)
const showProjectCreateEntry = computed(() => hasPermission('menu.projects'))
const showProjectLocationFields = false
const projectTypeOptions = [
  {
    value: 'image',
    label: '图片项目',
    description: '适合海报、KV、插画、商品图等以图片产出为主的项目。',
  },
  {
    value: 'storyboard_video',
    label: '分镜视频项目',
    description: '适合镜头脚本、分镜规划、视频生成等以视频产出为主的项目。',
  },
  {
    value: 'mixed',
    label: '综合项目',
    description: '适合图文混合或方向未定的项目，默认工作流更中性。',
  },
]

const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const createForm = ref({
  name: '',
  description: '',
  type: 'mixed',
  mcp_instruction: '',
  workspace_path: '',
  ai_entry_file: '',
  mcp_enabled: true,
  feedback_upgrade_enabled: true,
})

const editForm = ref({
  id: '',
  name: '',
  description: '',
  type: 'mixed',
  mcp_instruction: '',
  workspace_path: '',
  ai_entry_file: '',
  mcp_enabled: true,
  feedback_upgrade_enabled: true,
})

const showMcpDialog = ref(false)
const currentProject = ref(null)
const PROJECT_ACTIONS = [
  { key: 'detail', label: '详情', type: 'primary', requiresManage: false },
  { key: 'edit', label: '编辑', type: 'warning', requiresManage: true },
  { key: 'access', label: '接入', type: 'success', requiresManage: true },
  { key: 'delete', label: '删除', type: 'danger', requiresManage: true },
]

const emptyDescription = computed(() => {
  if (filters.value.name || filters.value.createdBy) {
    return '暂无匹配项目'
  }
  return '暂无项目'
})
const projectListDescription = computed(() => {
  if (filters.value.name || filters.value.createdBy) {
    return '当前已切换到聚焦浏览模式，适合快速筛掉无关项目后进入对应工作区。'
  }
  return '这里统一承载项目创建、筛选、状态切换和进入详情的桌面工作流。'
})
const projectListBadges = computed(() => [
  {
    key: 'scope',
    label: filters.value.name || filters.value.createdBy ? '筛选中' : '全部项目',
    type: filters.value.name || filters.value.createdBy ? 'warning' : 'info',
  },
  {
    key: 'create',
    label: showProjectCreateEntry.value ? '可新建项目' : '只读浏览',
    type: showProjectCreateEntry.value ? 'success' : 'info',
  },
])
const projectListStats = computed(() => [
  {
    key: 'total',
    label: '项目总数',
    value: paginationTotal.value,
    meta: '当前列表结果',
  },
  {
    key: 'mcp',
    label: 'MCP 已开',
    value: projects.value.filter((item) => item.mcp_enabled).length,
    meta: '便于直接接入桌面工作流',
  },
  {
    key: 'manageable',
    label: '可管理',
    value: projects.value.filter((item) => canManageProject(item)).length,
    meta: '当前账号可直接编辑',
  },
])

function canManageProject(project) {
  return !!project?.can_manage
}

function manageBlockedMessage(project) {
  const creator = String(project?.created_by || '').trim()
  if (creator) {
    return `仅项目创建者可编辑，当前创建者为 ${creator}`
  }
  return '仅项目创建者可编辑'
}

function getProjectActions(project) {
  return PROJECT_ACTIONS.filter((item) => !item.requiresManage || canManageProject(project))
}

function getPrimaryProjectActions(project) {
  return getProjectActions(project).slice(0, 3)
}

function getOverflowProjectActions(project) {
  return getProjectActions(project).slice(3)
}

function buildProjectQueryParams() {
  return {
    page: currentPage.value,
    page_size: pageSize.value,
    name: String(filters.value.name || '').trim(),
    created_by: String(filters.value.createdBy || '').trim(),
  }
}

function normalizeProjectList(items) {
  return (items || []).map((item) => ({
    ...item,
    type: normalizeProjectType(item.type),
  }))
}

function handleSearch() {
  currentPage.value = 1
  void fetchProjects()
}

function resetFilters() {
  filters.value = {
    name: '',
    createdBy: '',
  }
  currentPage.value = 1
  void fetchProjects()
}

function handlePageChange(page) {
  currentPage.value = page
  void fetchProjects()
}

function handlePageSizeChange(size) {
  pageSize.value = size
  currentPage.value = 1
  void fetchProjects()
}

function openCreate() {
  createForm.value = {
    name: '',
    description: '',
    type: 'mixed',
    mcp_instruction: '',
    workspace_path: '',
    ai_entry_file: '',
    mcp_enabled: true,
    feedback_upgrade_enabled: true,
  }
  showCreateDialog.value = true
}

async function selectWorkspaceDirectory() {
  const picked = await pickWorkspaceDirectory(createForm.value.workspace_path)
  if (picked === null) return
  createForm.value.workspace_path = picked
}

async function selectCreateAiEntryFile() {
  const picked = await pickAiEntryFile(
    createForm.value.ai_entry_file,
    createForm.value.workspace_path,
  )
  if (picked === null) return
  createForm.value.ai_entry_file = picked
}

function openEdit(project) {
  if (!canManageProject(project)) {
    ElMessage.warning(manageBlockedMessage(project))
    return
  }
  editForm.value = {
    id: project.id,
    name: project.name || '',
    description: project.description || '',
    type: normalizeProjectType(project.type),
    mcp_instruction: project.mcp_instruction || '',
    workspace_path: project.workspace_path || '',
    ai_entry_file: project.ai_entry_file || '',
    mcp_enabled: project.mcp_enabled ?? true,
    feedback_upgrade_enabled: project.feedback_upgrade_enabled ?? true,
  }
  showEditDialog.value = true
}

function handleProjectAction(project, actionKey) {
  switch (String(actionKey || '').trim()) {
    case 'detail':
      void openRouteInDesktop(router, `/projects/${project.id}`, {
        mode: 'new-window',
        appId: 'projects',
        title: project.name || '项目详情',
        eyebrow: 'Project Workspace',
        summary: '项目详情作为桌面中的独立应用窗口打开，可与列表、对话和素材库并行工作。',
      })
      return
    case 'edit':
      openEdit(project)
      return
    case 'access':
      showMcpConfig(project)
      return
    case 'delete':
      void removeProject(project)
      return
    default:
      return
  }
}

function normalizeProjectType(value) {
  const normalized = String(value || '').trim()
  return projectTypeOptions.some((item) => item.value === normalized) ? normalized : 'mixed'
}

function getProjectTypeLabel(value) {
  const matched = projectTypeOptions.find((item) => item.value === normalizeProjectType(value))
  return matched?.label || '综合项目'
}

function getProjectTypeDescription(value) {
  const matched = projectTypeOptions.find((item) => item.value === normalizeProjectType(value))
  return matched?.description || '适合图文混合或方向未定的项目，默认工作流更中性。'
}

function getProjectTypeTagType(value) {
  const normalized = normalizeProjectType(value)
  if (normalized === 'image') return 'success'
  if (normalized === 'storyboard_video') return 'warning'
  return 'info'
}

async function selectEditWorkspaceDirectory() {
  const picked = await pickWorkspaceDirectory(editForm.value.workspace_path)
  if (picked === null) return
  editForm.value.workspace_path = picked
}

async function selectEditAiEntryFile() {
  const picked = await pickAiEntryFile(
    editForm.value.ai_entry_file,
    editForm.value.workspace_path,
  )
  if (picked === null) return
  editForm.value.ai_entry_file = picked
}

async function pickWorkspaceDirectory(currentPath = '') {
  return await openWorkspaceDirectoryPicker(currentPath, {
    title: '选择项目工作区目录',
  })
}

async function pickAiEntryFile(currentPath = '', workspacePath = '') {
  const picked = await openWorkspaceFilePicker(currentPath, {
    title: '选择 AI 入口文件',
    placeholder: '.ai/ENTRY.md',
    basePath: workspacePath,
  })
  if (picked === null) return null
  return toWorkspaceRelativePath(picked, workspacePath) || String(picked || '').trim()
}

async function updateProject() {
  const currentProject = projects.value.find((item) => item.id === editForm.value.id)
  if (!canManageProject(currentProject)) {
    ElMessage.warning(manageBlockedMessage(currentProject))
    showEditDialog.value = false
    return
  }
  const name = String(editForm.value.name || '').trim()
  if (!name) {
    ElMessage.warning('请输入项目名称')
    return
  }
  updating.value = true
  try {
    await api.put(`/projects/${editForm.value.id}`, {
      name: editForm.value.name,
      description: editForm.value.description,
      type: normalizeProjectType(editForm.value.type),
      mcp_instruction: editForm.value.mcp_instruction,
      workspace_path: editForm.value.workspace_path,
      ai_entry_file: editForm.value.ai_entry_file,
      mcp_enabled: editForm.value.mcp_enabled,
      feedback_upgrade_enabled: editForm.value.feedback_upgrade_enabled,
    })
    ElMessage.success('项目已更新')
    showEditDialog.value = false
    await fetchProjects()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '更新失败')
  } finally {
    updating.value = false
  }
}

function showMcpConfig(project) {
  if (!canManageProject(project)) {
    ElMessage.warning(manageBlockedMessage(project))
    return
  }
  currentProject.value = project
  showMcpDialog.value = true
}

async function fetchProjects(options = {}) {
  const allowPageAdjust = options.allowPageAdjust !== false
  loading.value = true
  try {
    const data = await api.get('/projects', {
      params: buildProjectQueryParams(),
    })
    const nextProjects = normalizeProjectList(data.projects || [])
    const nextTotal = Math.max(
      0,
      Number(data?.pagination?.total ?? data?.total ?? nextProjects.length),
    )
    paginationTotal.value = nextTotal
    if (allowPageAdjust && nextTotal > 0 && !nextProjects.length && currentPage.value > 1) {
      currentPage.value = Math.max(1, Math.ceil(nextTotal / pageSize.value))
      await fetchProjects({ allowPageAdjust: false })
      return
    }
    projects.value = nextProjects
  } catch {
    projects.value = []
    paginationTotal.value = 0
    ElMessage.error('加载项目失败')
  } finally {
    loading.value = false
  }
}

async function createProject() {
  const name = String(createForm.value.name || '').trim()
  if (!name) {
    ElMessage.warning('请输入项目名称')
    return
  }
  creating.value = true
  try {
    const data = await api.post('/projects', {
      name,
      description: createForm.value.description,
      type: normalizeProjectType(createForm.value.type),
      mcp_instruction: createForm.value.mcp_instruction,
      workspace_path: createForm.value.workspace_path,
      ai_entry_file: createForm.value.ai_entry_file,
      mcp_enabled: !!createForm.value.mcp_enabled,
      feedback_upgrade_enabled: !!createForm.value.feedback_upgrade_enabled,
    })
    const createdProjectId = String(data?.project?.id || '').trim()
    if (createdProjectId) {
      localStorage.setItem('project_id', createdProjectId)
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
        window.dispatchEvent(
          new CustomEvent(PROJECT_CREATED_EVENT, {
            detail: { projectId: createdProjectId },
          }),
        )
      }
    }
    ElMessage.success('项目创建成功')
    showCreateDialog.value = false
    currentPage.value = 1
    await fetchProjects()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

async function patchProjectFlags(row, payload, successMessage) {
  if (!canManageProject(row)) {
    ElMessage.warning(manageBlockedMessage(row))
    return
  }
  try {
    await api.patch(`/projects/${row.id}`, payload)
    ElMessage.success(successMessage)
    await fetchProjects()
  } catch {
    ElMessage.error('更新失败')
  }
}

async function removeProject(row) {
  if (!canManageProject(row)) {
    ElMessage.warning(manageBlockedMessage(row))
    return
  }
  await ElMessageBox.confirm(`确定删除项目「${row.name}」？`, '确认', { type: 'warning' })
  try {
    await api.delete(`/projects/${row.id}`)
    ElMessage.success('已删除项目')
    await fetchProjects()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(fetchProjects)
</script>

<style scoped>
.project-list-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px 0 32px;
}

.project-list-page__section {
  margin-top: 0;
}

.project-list-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.filter-panel__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 240px));
  gap: 12px;
  flex: 1;
}

.filter-panel__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.project-list-grid-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.project-list-grid-metrics__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  background: rgba(248, 250, 252, 0.82);
}

.project-list-grid-metrics__item span,
.project-list-grid-metrics__item small {
  font-size: 12px;
  color: #64748b;
}

.project-list-grid-metrics__item strong {
  font-size: 24px;
  line-height: 1.1;
  color: #0f172a;
}

.project-list-table-shell {
  padding: 8px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.68);
}

.project-list-table-shell :deep(.el-table),
.project-list-table-shell :deep(.el-table__inner-wrapper) {
  border-radius: 20px;
  overflow: hidden;
}

.project-list-table-shell :deep(.el-table th.el-table__cell) {
  height: 54px;
  background: rgba(248, 250, 252, 0.9);
  color: #475569;
}

.project-list-table-shell :deep(.el-table td.el-table__cell) {
  padding-top: 14px;
  padding-bottom: 14px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.project-type-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.project-type-option__label {
  font-weight: 600;
  color: #111827;
}

.project-type-option__desc {
  font-size: 12px;
  line-height: 1.4;
  color: #6b7280;
}

.project-type-help {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: #6b7280;
}

@media (max-width: 900px) {
  .filter-panel {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-panel__fields {
    grid-template-columns: 1fr;
  }

  .filter-panel__actions {
    justify-content: flex-end;
  }
}

</style>
