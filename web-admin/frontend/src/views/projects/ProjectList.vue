<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>项目管理</h3>
      <el-button type="primary" size="small" @click="openCreate">新建项目</el-button>
    </div>

    <el-table :data="projects" stripe>
      <el-table-column prop="id" label="项目 ID" width="150" />
      <el-table-column prop="name" label="项目名称" width="220" show-overflow-tooltip />
      <el-table-column prop="description" label="描述" show-overflow-tooltip />
      <el-table-column label="成员数" width="90" align="center">
        <template #default="{ row }">{{ row.member_count || 0 }}</template>
      </el-table-column>
      <el-table-column label="MCP" width="100" align="center">
        <template #default="{ row }">
          <el-switch
            :model-value="!!row.mcp_enabled"
            @change="(val) => updateProject(row, { mcp_enabled: !!val }, val ? '已开启项目 MCP' : '已关闭项目 MCP')"
          />
        </template>
      </el-table-column>
      <el-table-column label="反馈升级" width="120" align="center">
        <template #default="{ row }">
          <el-switch
            :model-value="!!row.feedback_upgrade_enabled"
            @change="(val) => updateProject(row, { feedback_upgrade_enabled: !!val }, val ? '已开启反馈升级' : '已关闭反馈升级')"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="$router.push(`/projects/${row.id}`)">详情</el-button>
          <el-button text type="success" size="small" @click="showMcpConfig(row)">接入</el-button>
          <el-button text type="danger" size="small" @click="removeProject(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!projects.length && !loading" description="暂无项目" />

    <el-dialog v-model="showCreateDialog" title="新建项目" width="520px">
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

    <el-dialog v-model="showMcpDialog" :title="`项目 MCP 接入: ${currentProject?.name || ''}`" width="620px">
      <el-tabs v-model="mcpTab">
        <el-tab-pane label="SSE" name="sse">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpSseConfig }}</code></pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="HTTP" name="http">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpHttpConfig }}</code></pre>
          </div>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button type="primary" @click="copyMcpConfig">复制当前配置</el-button>
        <el-button @click="showMcpDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const loading = ref(false)
const creating = ref(false)
const projects = ref([])

const showCreateDialog = ref(false)
const createForm = ref({
  name: '',
  description: '',
  mcp_enabled: true,
  feedback_upgrade_enabled: true,
})

const showMcpDialog = ref(false)
const mcpTab = ref('sse')
const currentProject = ref(null)

const mcpSseConfig = computed(() => {
  if (!currentProject.value) return ''
  const serviceName = `project-${currentProject.value.id}`
  return JSON.stringify(
    {
      mcpServers: {
        [serviceName]: {
          type: 'sse',
          url: `http://localhost:8000/mcp/projects/${currentProject.value.id}/sse?key=YOUR_API_KEY`,
        },
      },
    },
    null,
    2,
  )
})

const mcpHttpConfig = computed(() => {
  if (!currentProject.value) return ''
  const serviceName = `project-${currentProject.value.id}`
  return JSON.stringify(
    {
      mcpServers: {
        [serviceName]: {
          command: 'npx',
          args: [
            '-y',
            '@modelcontextprotocol/inspector',
            `http://localhost:8000/mcp/projects/${currentProject.value.id}/mcp?key=YOUR_API_KEY`,
          ],
        },
      },
    },
    null,
    2,
  )
})

function openCreate() {
  createForm.value = {
    name: '',
    description: '',
    mcp_enabled: true,
    feedback_upgrade_enabled: true,
  }
  showCreateDialog.value = true
}

function showMcpConfig(project) {
  currentProject.value = project
  mcpTab.value = 'sse'
  showMcpDialog.value = true
}

async function copyMcpConfig() {
  const text = mcpTab.value === 'sse' ? mcpSseConfig.value : mcpHttpConfig.value
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('配置已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function fetchProjects() {
  loading.value = true
  try {
    const data = await api.get('/projects')
    projects.value = data.projects || []
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
    await api.post('/projects', {
      name,
      description: createForm.value.description,
      mcp_enabled: !!createForm.value.mcp_enabled,
      feedback_upgrade_enabled: !!createForm.value.feedback_upgrade_enabled,
    })
    ElMessage.success('项目创建成功')
    showCreateDialog.value = false
    await fetchProjects()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

async function updateProject(row, payload, successMessage) {
  try {
    await api.patch(`/projects/${row.id}`, payload)
    ElMessage.success(successMessage)
    await fetchProjects()
  } catch {
    ElMessage.error('更新失败')
  }
}

async function removeProject(row) {
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

.mcp-code-wrap {
  background: #1e1e1e;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}

.mcp-code {
  margin: 0;
  color: #d4d4d4;
  font-size: 13px;
  line-height: 1.5;
}
</style>
