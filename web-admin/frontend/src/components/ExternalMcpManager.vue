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
    width="640px"
    append-to-body
    destroy-on-close
  >
    <div class="external-mcp-json">
      <div class="external-mcp-json__head">
        <span class="external-mcp-json__title">单个 MCP Server JSON</span>
        <div class="external-mcp-json__actions">
          <el-button size="small" text @click="fillSseExample">
            SSE 示例
          </el-button>
          <el-button size="small" text @click="formatJsonConfig">
            格式化
          </el-button>
        </div>
      </div>
      <div class="external-mcp-json__hint">
        每次只添加 1 个 server。支持完整对象或 <code>"server-name": { ... }</code> 片段；如有 <code>mcpServers</code>，请拆开逐个粘贴。
      </div>
      <el-input
        v-model="jsonConfigText"
        type="textarea"
        :rows="14"
        resize="vertical"
        spellcheck="false"
        placeholder='"query-center-project": {
  "description": "统一查询 MCP 入口",
  "type": "sse",
  "url": "http://127.0.0.1:8000/mcp/query/sse?key=..."
}'
      />
      <div v-if="jsonPreviewText" class="external-mcp-json__preview">
        {{ jsonPreviewText }}
      </div>
      <el-alert
        v-if="testResult"
        :title="testResult.summary"
        :type="testResult.ok ? 'success' : 'warning'"
        :description="testResult.details"
        :closable="false"
        show-icon
      />
    </div>
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
const jsonConfigText = ref('')

const normalizedProjectId = computed(() => String(props.projectId || '').trim())
const isEditing = computed(() => Boolean(String(editingModuleId.value || '').trim()))
const dialogTitle = computed(() => (isEditing.value ? '编辑外部 MCP 模块' : '新增外部 MCP 模块'))
const submitLabel = computed(() => (isEditing.value ? '保存修改' : '保存'))
const jsonPreviewText = computed(() => {
  const parsed = parseJsonConfigSilently()
  if (!parsed) return ''
  const parts = []
  if (parsed.name) parts.push(`名称: ${parsed.name}`)
  if (parsed.transport_type) parts.push(`类型: ${parsed.transport_type}`)
  if (parsed.endpoint_http || parsed.endpoint_sse) {
    parts.push(`入口: ${parsed.endpoint_http || parsed.endpoint_sse}`)
  } else if (parsed.command) {
    parts.push(`命令: ${parsed.command}`)
  }
  parts.push(parsed.project_id ? '范围: 当前项目' : '范围: 全局')
  parts.push(parsed.enabled ? '启用' : '停用')
  return parts.join(' | ')
})

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
  jsonConfigText.value = ''
}

function closeDialog() {
  showDialog.value = false
  resetForm()
}

function moduleMetaText(item) {
  const parts = []
  const endpoint = String(item?.endpoint_http || item?.endpoint_sse || '').trim()
  const command = String(item?.command || '').trim()
  const transportType = String(item?.transport_type || item?.type || '').trim()
  const projectScope = String(item?.project_id || '').trim()
  if (transportType) parts.push(`类型: ${transportType}`)
  if (endpoint) parts.push(`入口: ${endpoint}`)
  if (!endpoint && command) parts.push(`命令: ${command}`)
  if (projectScope) parts.push(`范围: 项目(${projectScope})`)
  if (!projectScope) parts.push('范围: 全局')
  return parts.join(' | ')
}

function parseJsonConfigSilently() {
  try {
    return normalizeJsonConfig(resolveSingleJsonConfig(JSON.parse(wrapNamedServerJson(jsonConfigText.value || '{}'))))
  } catch {
    return null
  }
}

function inferModuleName(config, transportType, endpointHttp, endpointSse, command, serverName = '') {
  const explicitName = String(config?.name || config?.module_name || config?.server_name || config?.id || '').trim()
  if (explicitName) return explicitName.slice(0, 80)
  if (serverName) return String(serverName).trim().slice(0, 80)
  if (command) return command.split('/').filter(Boolean).pop().slice(0, 80)
  const endpoint = String(endpointHttp || endpointSse || config?.url || '').trim()
  if (endpoint) {
    try {
      const url = new URL(endpoint)
      return (url.hostname || `${transportType || 'mcp'} 服务`).slice(0, 80)
    } catch {
      return endpoint.slice(0, 80)
    }
  }
  return '外部 MCP 模块'
}

function normalizeStringList(value) {
  return Array.isArray(value)
    ? value.map((item) => String(item || '').trim()).filter(Boolean)
    : []
}

function normalizeStringMap(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, item]) => [String(key || '').trim(), String(item ?? '')])
      .filter(([key]) => key),
  )
}

function normalizeTransportType(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (['stdio', 'sse', 'http'].includes(normalized)) return normalized
  return ''
}

function normalizeJsonConfig(input) {
  const { config, serverName } = input && input.config ? input : { config: input, serverName: '' }
  if (!config || typeof config !== 'object' || Array.isArray(config)) {
    throw new Error('JSON 配置必须是对象')
  }
  const transportType = normalizeTransportType(config.type || config.transport || config.transport_type)
  const url = String(config.url || '').trim()
  const endpointHttp = String(config.endpoint_http || config.http_endpoint || (transportType === 'http' ? url : '') || '').trim()
  const endpointSse = String(config.endpoint_sse || config.sse_endpoint || (transportType === 'sse' ? url : '') || '').trim()
  const command = String(config.command || '').trim()
  const scope = String(config.scope || '').trim().toLowerCase()
  const projectId = String(config.project_id || '').trim()
  const resolvedProjectId = projectId || buildScopeProjectId(scope || 'project')
  const resolvedType = transportType || (command ? 'stdio' : endpointSse ? 'sse' : endpointHttp || url ? 'http' : '')
  const resolvedEndpointHttp = endpointHttp || (resolvedType === 'http' ? url : '')
  const resolvedEndpointSse = endpointSse || (resolvedType === 'sse' ? url : '')
  return {
    name: inferModuleName(config, resolvedType, resolvedEndpointHttp, resolvedEndpointSse, command, serverName),
    description: String(config.description || '').trim().slice(0, 300),
    transport_type: resolvedType,
    endpoint_http: resolvedEndpointHttp,
    endpoint_sse: resolvedEndpointSse,
    command,
    args: normalizeStringList(config.args),
    env: normalizeStringMap(config.env),
    headers: normalizeStringMap(config.headers),
    config,
    auth_type: String(config.auth_type || 'none').trim() || 'none',
    project_id: resolvedProjectId,
    enabled: config.enabled !== false,
  }
}

function resolveSingleJsonConfig(config) {
  if (!config || typeof config !== 'object' || Array.isArray(config)) {
    throw new Error('JSON 配置必须是对象')
  }
  if (config.mcpServers && typeof config.mcpServers === 'object' && !Array.isArray(config.mcpServers)) {
    throw new Error('请一次只粘贴一个 server 配置，不要粘贴 mcpServers 批量配置')
  }
  const directKeys = ['type', 'transport', 'transport_type', 'url', 'endpoint_http', 'endpoint_sse', 'command', 'args', 'headers']
  if (directKeys.some((key) => Object.prototype.hasOwnProperty.call(config, key))) {
    return { config, serverName: String(config.name || '').trim() }
  }
  const entries = Object.entries(config).filter(([, value]) => value && typeof value === 'object' && !Array.isArray(value))
  if (entries.length === 1) {
    const [serverName, serverConfig] = entries[0]
    return { config: serverConfig, serverName }
  }
  throw new Error('请粘贴单个 MCP server 配置')
}

function wrapNamedServerJson(value) {
  const text = String(value || '').trim()
  if (!text) return '{}'
  if (text.startsWith('{')) return text
  return `{${text}}`
}

function withEditableMetadata(config, item) {
  const next = config && typeof config === 'object' && !Array.isArray(config)
    ? { ...config }
    : {}
  if (!String(next.name || '').trim()) {
    next.name = String(item?.name || '').trim()
  }
  if (!String(next.description || '').trim()) {
    next.description = String(item?.description || '').trim()
  }
  if (next.enabled === undefined) {
    next.enabled = Boolean(item?.enabled ?? true)
  }
  if (!String(next.project_id || '').trim() && !String(next.scope || '').trim()) {
    next.scope = String(item?.project_id || '').trim() ? 'project' : 'global'
  }
  return next
}

function formatJsonConfig() {
  try {
    const parsed = JSON.parse(wrapNamedServerJson(jsonConfigText.value || '{}'))
    jsonConfigText.value = JSON.stringify(parsed, null, 2)
  } catch (err) {
    ElMessage.warning(`JSON 格式错误：${err.message || err}`)
  }
}

function fillSseExample() {
  jsonConfigText.value = JSON.stringify({
    'query-center-project': {
      description: '统一查询 MCP 入口。推荐先调用 query://usage-guide，再使用 search_ids、get_content、get_manual_content；项目手册可直接通过 MCP 获取，无需写入项目文件',
      type: 'sse',
      url: 'http://192.168.1.126:3000/mcp/query/sse?key=YOUR_API_KEY',
    },
  }, null, 2)
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
  const sourceConfig = item?.config && typeof item.config === 'object'
    ? withEditableMetadata(item.config, item)
    : {
        type: String(item?.transport_type || '').trim() || (item?.command ? 'stdio' : item?.endpoint_sse ? 'sse' : 'http'),
        name: String(item?.name || '').trim(),
        description: String(item?.description || '').trim(),
        endpoint_http: String(item?.endpoint_http || '').trim(),
        endpoint_sse: String(item?.endpoint_sse || '').trim(),
        command: String(item?.command || '').trim(),
        args: Array.isArray(item?.args) ? item.args : [],
        env: item?.env && typeof item.env === 'object' ? item.env : {},
        project_id: String(item?.project_id || '').trim(),
        enabled: Boolean(item?.enabled ?? true),
      }
  jsonConfigText.value = JSON.stringify(sourceConfig, null, 2)
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
  let payload
  try {
    payload = normalizeJsonConfig(resolveSingleJsonConfig(JSON.parse(wrapNamedServerJson(jsonConfigText.value || '{}'))))
  } catch (err) {
    ElMessage.warning(`JSON 配置无效：${err.message || err}`)
    return
  }
  if (payload.transport_type === 'stdio') {
    ElMessage.warning('stdio MCP 暂不支持在服务端测试连接')
    return
  }
  if (!payload.endpoint_http && !payload.endpoint_sse) {
    ElMessage.warning('JSON 配置中缺少 url、endpoint_http 或 endpoint_sse')
    return
  }

  testing.value = true
  testResult.value = null
  try {
    const result = await api.post('/mcp/modules/test', {
      endpoint_http: payload.endpoint_http,
      endpoint_sse: payload.endpoint_sse,
      headers: payload.headers,
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
  let payload
  try {
    payload = normalizeJsonConfig(resolveSingleJsonConfig(JSON.parse(wrapNamedServerJson(jsonConfigText.value || '{}'))))
  } catch (err) {
    ElMessage.warning(`JSON 配置无效：${err.message || err}`)
    return
  }
  if (payload.transport_type === 'stdio' && !payload.command) {
    ElMessage.warning(`stdio 配置“${payload.name}”缺少 command`)
    return
  }
  if (payload.transport_type !== 'stdio' && !payload.endpoint_http && !payload.endpoint_sse) {
    ElMessage.warning(`配置“${payload.name}”缺少 url、endpoint_http 或 endpoint_sse`)
    return
  }
  if (!normalizedProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
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

.external-mcp-json {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.external-mcp-json__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.external-mcp-json__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.external-mcp-json__hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 18px;
}

.external-mcp-json__hint code {
  color: var(--el-text-color-regular);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}

.external-mcp-json__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.external-mcp-json :deep(.el-textarea__inner) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.5;
}

.external-mcp-json__preview {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  background: var(--el-fill-color-extra-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 18px;
  word-break: break-word;
}
</style>
