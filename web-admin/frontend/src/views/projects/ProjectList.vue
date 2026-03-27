<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>项目管理</h3>
      <el-button v-if="showProjectCreateEntry" type="primary" size="small" @click="openCreate">
        新建项目
      </el-button>
    </div>

    <el-table :data="projects" stripe>
      <el-table-column prop="id" label="项目 ID" width="150" />
      <el-table-column prop="name" label="项目名称" width="180" show-overflow-tooltip />
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
      <el-table-column label="操作" width="280" fixed="right">
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

    <el-empty v-if="!projects.length && !loading" description="暂无项目" />

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
import UnifiedMcpAccessDialog from '@/components/UnifiedMcpAccessDialog.vue'
import api from '@/utils/api.js'
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
      void router.push(`/projects/${project.id}`)
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

async function fetchProjects() {
  loading.value = true
  try {
    const data = await api.get('/projects')
    projects.value = (data.projects || []).map((item) => ({
      ...item,
      type: normalizeProjectType(item.type),
    }))
  } catch {
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
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar h3 {
  margin: 0;
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

</style>
