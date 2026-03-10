<template>
  <div class="external-mcp-manager">
    <div class="external-mcp-actions">
      <span v-if="tip" class="external-mcp-tip">{{ tip }}</span>
      <el-button size="small" type="primary" plain @click="openCreateDialog">
        新增外部模块
      </el-button>
    </div>

    <div class="external-mcp-list" v-loading="loading">
      <el-empty
        v-if="!modules.length && !loading"
        :description="emptyDescription"
        :image-size="48"
      />
      <template v-else>
        <div
          v-for="item in modules.slice(0, visibleLimit)"
          :key="item.id || item.name"
          class="external-mcp-item"
        >
          <div class="external-mcp-row">
            <div class="external-mcp-head">
              <span class="external-mcp-name">{{ item.name || item.id || '-' }}</span>
              <el-tag size="small" type="info">外部服务</el-tag>
            </div>
            <div class="external-mcp-item-actions">
              <el-button text size="small" @click="editModule(item)">编辑</el-button>
              <el-button text size="small" type="danger" @click="deleteModule(item)">删除</el-button>
            </div>
          </div>
          <div v-if="item.description" class="external-mcp-desc">{{ item.description }}</div>
          <div v-if="moduleMetaText(item)" class="external-mcp-meta">{{ moduleMetaText(item) }}</div>
        </div>
        <div v-if="modules.length > visibleLimit" class="external-mcp-more">
          其余 {{ modules.length - visibleLimit }} 个模块未展示
        </div>
      </template>
    </div>
  </div>

  <el-dialog
    v-model="showDialog"
    :title="dialogTitle"
    width="520px"
    destroy-on-close
  >
    <el-form label-position="top" size="default">
      <el-form-item label="模块名称" required>
        <el-input
          v-model="form.name"
          maxlength="80"
          placeholder="例如：企业知识库服务"
        />
      </el-form-item>
      <el-form-item label="描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="2"
          maxlength="300"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label="HTTP Endpoint">
        <el-input
          v-model="form.endpoint_http"
          placeholder="https://example.com/mcp"
        />
      </el-form-item>
      <el-form-item label="SSE Endpoint">
        <el-input
          v-model="form.endpoint_sse"
          placeholder="https://example.com/sse"
        />
      </el-form-item>
      <el-form-item label="作用范围">
        <el-radio-group v-model="form.scope">
          <el-radio label="project">仅当前项目</el-radio>
          <el-radio label="global">全局</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="form.enabled" />
      </el-form-item>
      <el-alert
        v-if="testResult"
        :title="testResult.summary"
        :type="testResult.ok ? 'success' : 'warning'"
        :description="testResult.details"
        :closable="false"
        show-icon
      />
    </el-form>
    <template #footer>
      <el-button @click="closeDialog">取消</el-button>
      <el-button :loading="testing" @click="testModule">测试连接</el-button>
      <el-button type="primary" :loading="submitting" @click="submitModule">
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const props = defineProps({
  projectId: {
    type: String,
    default: '',
  },
  tip: {
    type: String,
    default: '外部 MCP 可新增、编辑、删除。',
  },
  emptyDescription: {
    type: String,
    default: '暂无外部 MCP 模块',
  },
  visibleLimit: {
    type: Number,
    default: 12,
  },
})

const emit = defineEmits(['changed', 'count-change'])

const loading = ref(false)
const submitting = ref(false)
const testing = ref(false)
const showDialog = ref(false)
const editingModuleId = ref('')
const testResult = ref(null)
const modules = ref([])
const form = ref({
  name: '',
  description: '',
  endpoint_http: '',
  endpoint_sse: '',
  scope: 'project',
  enabled: true,
})

const normalizedProjectId = computed(() => String(props.projectId || '').trim())
const isEditing = computed(() => Boolean(String(editingModuleId.value || '').trim()))
const dialogTitle = computed(() => (isEditing.value ? '编辑外部 MCP 模块' : '新增外部 MCP 模块'))
const submitLabel = computed(() => (isEditing.value ? '保存修改' : '保存'))

watch(normalizedProjectId, async (value) => {
  if (!value) {
    modules.value = []
    emit('count-change', 0)
    return
  }
  await fetchModules()
}, { immediate: true })

function buildScopeProjectId(scope) {
  return String(scope || '').trim() === 'global' ? '' : normalizedProjectId.value
}

function resetForm() {
  editingModuleId.value = ''
  testResult.value = null
  form.value = {
    name: '',
    description: '',
    endpoint_http: '',
    endpoint_sse: '',
    scope: 'project',
    enabled: true,
  }
}

function closeDialog() {
  showDialog.value = false
  resetForm()
}

function moduleMetaText(item) {
  const parts = []
  const endpoint = String(item?.endpoint_http || item?.endpoint_sse || '').trim()
  const projectScope = String(item?.project_id || '').trim()
  if (endpoint) parts.push(`入口: ${endpoint}`)
  if (projectScope) parts.push(`范围: 项目(${projectScope})`)
  if (!projectScope) parts.push('范围: 全局')
  return parts.join(' | ')
}

function formatTestResult(result) {
  const items = Array.isArray(result?.results) ? result.results : []
  const details = items
    .map((item) => {
      const transport = String(item?.transport || '').toUpperCase() || 'MCP'
      const url = String(item?.url || '').trim()
      const status = item?.status_code ? ` (${item.status_code})` : ''
      const message = String(item?.message || '').trim()
      return `${transport}${status} ${message}${url ? `：${url}` : ''}`
    })
    .join('；')
  return {
    ok: Boolean(result?.ok),
    summary: String(result?.summary || '测试完成'),
    details,
  }
}

async function fetchModules() {
  if (!normalizedProjectId.value) {
    modules.value = []
    emit('count-change', 0)
    return
  }
  loading.value = true
  try {
    const data = await api.get(`/mcp/modules?project_id=${encodeURIComponent(normalizedProjectId.value)}`)
    modules.value = Array.isArray(data?.modules) ? data.modules : []
    emit('count-change', modules.value.length)
    emit('changed', modules.value)
  } catch (err) {
    modules.value = []
    emit('count-change', 0)
    ElMessage.error(err?.detail || err?.message || '加载外部 MCP 模块失败')
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  if (!normalizedProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  resetForm()
  showDialog.value = true
}

function editModule(item) {
  if (!normalizedProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  editingModuleId.value = String(item?.id || '').trim()
  testResult.value = null
  form.value = {
    name: String(item?.name || '').trim(),
    description: String(item?.description || '').trim(),
    endpoint_http: String(item?.endpoint_http || '').trim(),
    endpoint_sse: String(item?.endpoint_sse || '').trim(),
    scope: String(item?.project_id || '').trim() ? 'project' : 'global',
    enabled: Boolean(item?.enabled ?? true),
  }
  showDialog.value = true
}

async function deleteModule(item) {
  const moduleId = String(item?.id || '').trim()
  const moduleName = String(item?.name || item?.id || '').trim() || '该模块'
  if (!moduleId) {
    ElMessage.error('缺少模块 ID，无法删除')
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除外部 MCP 模块“${moduleName}”吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger',
    })
  } catch {
    return
  }

  try {
    await api.delete(`/mcp/modules/${encodeURIComponent(moduleId)}`)
    await fetchModules()
    ElMessage.success('外部 MCP 模块已删除')
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '删除外部模块失败')
  }
}

async function testModule() {
  const endpointHttp = String(form.value.endpoint_http || '').trim()
  const endpointSse = String(form.value.endpoint_sse || '').trim()
  if (!endpointHttp && !endpointSse) {
    ElMessage.warning('至少填写一个 Endpoint')
    return
  }

  testing.value = true
  testResult.value = null
  try {
    const result = await api.post('/mcp/modules/test', {
      endpoint_http: endpointHttp,
      endpoint_sse: endpointSse,
      timeout_sec: 8,
    })
    const formatted = formatTestResult(result)
    testResult.value = formatted
    if (formatted.ok) {
      ElMessage.success(formatted.summary)
    } else {
      ElMessage.warning(formatted.summary)
    }
  } catch (err) {
    testResult.value = {
      ok: false,
      summary: '连接测试失败',
      details: String(err?.detail || err?.message || '未知错误'),
    }
    ElMessage.error(err?.detail || err?.message || '连接测试失败')
  } finally {
    testing.value = false
  }
}

async function submitModule() {
  const isEditingValue = isEditing.value
  const name = String(form.value.name || '').trim()
  const endpointHttp = String(form.value.endpoint_http || '').trim()
  const endpointSse = String(form.value.endpoint_sse || '').trim()
  if (!name) {
    ElMessage.warning('请输入模块名称')
    return
  }
  if (!endpointHttp && !endpointSse) {
    ElMessage.warning('至少填写一个 Endpoint')
    return
  }
  if (!normalizedProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }

  const payload = {
    name,
    description: String(form.value.description || '').trim(),
    endpoint_http: endpointHttp,
    endpoint_sse: endpointSse,
    auth_type: 'none',
    project_id: buildScopeProjectId(form.value.scope),
    enabled: Boolean(form.value.enabled),
  }

  submitting.value = true
  try {
    if (isEditingValue) {
      await api.patch(`/mcp/modules/${encodeURIComponent(editingModuleId.value)}`, payload)
    } else {
      await api.post('/mcp/modules', payload)
    }
    closeDialog()
    await fetchModules()
    ElMessage.success(isEditingValue ? '外部 MCP 模块已更新' : '外部 MCP 模块已添加')
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || (isEditingValue ? '更新外部模块失败' : '新增外部模块失败'))
  } finally {
    submitting.value = false
  }
}

defineExpose({
  fetchModules,
})
</script>

<style scoped>
.external-mcp-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.external-mcp-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 18px;
}

.external-mcp-list {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 8px;
  max-height: 220px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.external-mcp-item {
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 6px;
  padding: 8px;
  background: var(--el-fill-color-extra-light);
}

.external-mcp-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.external-mcp-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.external-mcp-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.external-mcp-item-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.external-mcp-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 18px;
  word-break: break-word;
}

.external-mcp-meta {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  line-height: 16px;
  word-break: break-word;
}

.external-mcp-more {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 4px 0;
}
</style>
