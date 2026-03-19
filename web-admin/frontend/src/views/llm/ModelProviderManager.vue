<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>模型供应商管理</h3>
      <el-button type="primary" @click="openCreate">新增供应商</el-button>
    </div>

    <el-table :data="providers" stripe>
      <el-table-column type="expand">
        <template #default="{ row }">
          <el-descriptions :column="2" border size="small" class="expand-desc">
            <el-descriptions-item label="连接状态">
              <el-tag :type="connectionTagType(row.id)" size="small">{{ connectionTagText(row.id) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="最近测试时间">{{ formatDateTime(getConnectionMeta(row.id, 'tested_at')) }}</el-descriptions-item>
            <el-descriptions-item label="测试模型">{{ getConnectionMeta(row.id, 'model_tested') || '-' }}</el-descriptions-item>
            <el-descriptions-item label="延迟(ms)">{{ getConnectionMeta(row.id, 'latency_ms') || '-' }}</el-descriptions-item>
            <el-descriptions-item label="返回信息" :span="2">
              {{ getConnectionMeta(row.id, 'message') || '-' }}
            </el-descriptions-item>
          </el-descriptions>
          <div class="expand-actions">
            <el-input
              v-model="testModelByProvider[row.id]"
              placeholder="可选：指定测试模型，不填用默认模型"
              style="width: 300px"
            />
            <el-button
              type="primary"
              plain
              :loading="testingProviderId === row.id"
              @click="testConnection(row)"
            >
              测试模型接口连接
            </el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="owner_username" label="创建人" width="140">
        <template #default="{ row }">{{ row.owner_username || '-' }}</template>
      </el-table-column>
      <el-table-column prop="provider_type" label="类型" width="150" />
      <el-table-column prop="base_url" label="Base URL" min-width="220" show-overflow-tooltip />
      <el-table-column label="共享用户" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatSharedUsers(row.shared_usernames) }}
        </template>
      </el-table-column>
      <el-table-column label="模型列表" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ (row.models || []).join(', ') || '-' }}</template>
      </el-table-column>
      <el-table-column prop="default_model" label="默认模型" width="170" show-overflow-tooltip />
      <el-table-column label="API Key" width="150">
        <template #default="{ row }">{{ row.api_key_masked || '-' }}</template>
      </el-table-column>
      <el-table-column label="启用" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="220">
        <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="320" fixed="right">
        <template #default="{ row }">
          <el-button text type="success" :loading="testingProviderId === row.id" @click="testConnection(row)">测试连接</el-button>
          <el-button text type="warning" @click="openDuplicate(row)">复制</el-button>
          <el-button text type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button text type="danger" @click="removeProvider(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && !providers.length" description="暂无模型供应商" :image-size="60" />

    <el-dialog v-model="showDialog" :title="dialogTitle()" width="720px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="供应商名称" required>
          <el-input v-model="form.name" placeholder="例如：OpenAI 主账号" />
        </el-form-item>
        <el-form-item label="供应商类型">
          <el-select v-model="form.provider_type" style="width: 220px">
            <el-option label="openai-compatible" value="openai-compatible" />
            <el-option label="responses" value="responses" />
            <el-option label="custom" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL" required>
          <el-input v-model="form.base_url" placeholder="例如：https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="apiKeyPlaceholder()"
          />
        </el-form-item>
        <el-form-item label="模型列表">
          <el-input
            v-model="form.models_text"
            type="textarea"
            :rows="3"
            placeholder="多个模型用逗号或换行分隔"
          />
        </el-form-item>
        <el-form-item label="默认模型">
          <el-input v-model="form.default_model" placeholder="例如：gpt-4.1" />
        </el-form-item>
        <el-form-item label="额外请求头(JSON)">
          <el-input
            v-model="form.extra_headers_text"
            type="textarea"
            :rows="3"
            placeholder='例如：{"X-Provider":"demo"}'
          />
        </el-form-item>
        <el-form-item label="共享给用户">
          <el-select
            v-model="form.shared_usernames"
            multiple
            collapse-tags
            collapse-tags-tooltip
            filterable
            clearable
            placeholder="选择可使用该模型的用户"
            style="width: 100%"
          >
            <el-option
              v-for="item in shareUserOptions"
              :key="item.username"
              :label="item.label"
              :value="item.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'

const loading = ref(false)
const saving = ref(false)
const providers = ref([])
const shareUserOptions = ref([])
const showDialog = ref(false)
const editingId = ref('')
const dialogMode = ref('create')
const testingProviderId = ref('')
const connectionResultByProvider = reactive({})
const testModelByProvider = reactive({})
const form = reactive({
  name: '',
  provider_type: 'openai-compatible',
  base_url: '',
  api_key: '',
  models_text: '',
  default_model: '',
  enabled: true,
  extra_headers_text: '',
  shared_usernames: [],
})

function splitModels(text) {
  return String(text || '')
    .replace(/\n/g, ',')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function resetForm() {
  form.name = ''
  form.provider_type = 'openai-compatible'
  form.base_url = ''
  form.api_key = ''
  form.models_text = ''
  form.default_model = ''
  form.enabled = true
  form.extra_headers_text = ''
  form.shared_usernames = []
}

function buildDuplicateName(name) {
  const base = String(name || '').trim()
  return base ? `${base} 副本` : '供应商副本'
}

function populateForm(row, { duplicate = false } = {}) {
  form.name = duplicate ? buildDuplicateName(row?.name) : String(row?.name || '')
  form.provider_type = String(row?.provider_type || 'openai-compatible')
  form.base_url = String(row?.base_url || '')
  form.api_key = ''
  form.models_text = Array.isArray(row?.models) ? row.models.join(', ') : ''
  form.default_model = String(row?.default_model || '')
  form.enabled = row?.enabled !== false
  const headers = row?.extra_headers && typeof row.extra_headers === 'object' ? row.extra_headers : {}
  form.extra_headers_text = Object.keys(headers).length ? JSON.stringify(headers, null, 2) : ''
  form.shared_usernames = Array.isArray(row?.shared_usernames) ? row.shared_usernames.map((item) => String(item || '').trim()).filter(Boolean) : []
}

function openCreate() {
  dialogMode.value = 'create'
  editingId.value = ''
  resetForm()
  showDialog.value = true
}

function openEdit(row) {
  dialogMode.value = 'edit'
  editingId.value = String(row.id || '')
  populateForm(row)
  showDialog.value = true
}

function openDuplicate(row) {
  dialogMode.value = 'duplicate'
  editingId.value = ''
  populateForm(row, { duplicate: true })
  showDialog.value = true
}

function dialogTitle() {
  if (dialogMode.value === 'edit') return '编辑模型供应商'
  if (dialogMode.value === 'duplicate') return '复制模型供应商'
  return '新增模型供应商'
}

function apiKeyPlaceholder() {
  if (dialogMode.value === 'edit') return '编辑时留空表示不修改'
  if (dialogMode.value === 'duplicate') return '出于安全原因不会复制 API Key，请按需填写'
  return '例如：sk-...'
}

function parseHeaders() {
  const raw = String(form.extra_headers_text || '').trim()
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed
    }
    throw new Error('invalid')
  } catch {
    throw new Error('额外请求头必须是 JSON 对象')
  }
}

async function fetchProviders() {
  loading.value = true
  try {
    const data = await api.get('/llm/providers')
    providers.value = data.providers || []
    for (const item of providers.value) {
      const id = String(item.id || '')
      if (!id) continue
      if (!(id in testModelByProvider)) {
        testModelByProvider[id] = String(item.default_model || '')
      }
    }
  } catch (e) {
    ElMessage.error(e.detail || '加载模型供应商失败')
  } finally {
    loading.value = false
  }
}

async function fetchShareUserOptions() {
  try {
    const data = await api.get('/llm/providers/share-options')
    const users = Array.isArray(data?.users) ? data.users : []
    shareUserOptions.value = users
      .map((item) => {
        const username = String(item?.username || '').trim()
        if (!username) return null
        const role = String(item?.role || '').trim()
        return {
          username,
          label: role ? `${username} (${role})` : username,
        }
      })
      .filter(Boolean)
  } catch (e) {
    shareUserOptions.value = []
    ElMessage.error(e.detail || '加载共享用户失败')
  }
}

async function submitForm() {
  if (!form.name.trim() || !form.base_url.trim()) {
    ElMessage.warning('请填写供应商名称和 Base URL')
    return
  }

  let extraHeaders = {}
  try {
    extraHeaders = parseHeaders()
  } catch (e) {
    ElMessage.error(e.message || '额外请求头格式错误')
    return
  }

  const payload = {
    name: form.name.trim(),
    provider_type: form.provider_type,
    base_url: form.base_url.trim(),
    models: splitModels(form.models_text),
    default_model: form.default_model.trim(),
    enabled: Boolean(form.enabled),
    extra_headers: extraHeaders,
    shared_usernames: Array.isArray(form.shared_usernames)
      ? form.shared_usernames.map((item) => String(item || '').trim()).filter(Boolean)
      : [],
  }

  if (!editingId.value || form.api_key.trim()) {
    payload.api_key = form.api_key.trim()
  }

  saving.value = true
  try {
    if (editingId.value) {
      await api.patch(`/llm/providers/${encodeURIComponent(editingId.value)}`, payload)
      ElMessage.success('更新成功')
    } else {
      await api.post('/llm/providers', payload)
      ElMessage.success(dialogMode.value === 'duplicate' ? '复制创建成功' : '创建成功')
    }
    showDialog.value = false
    fetchProviders()
  } catch (e) {
    ElMessage.error(e.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function formatSharedUsers(usernames) {
  const values = Array.isArray(usernames)
    ? usernames.map((item) => String(item || '').trim()).filter(Boolean)
    : []
  return values.join(', ') || '-'
}

async function removeProvider(row) {
  const id = String(row.id || '')
  if (!id) return
  await ElMessageBox.confirm(`确定删除供应商 ${row.name || id}？`, '删除确认', { type: 'warning' })
  try {
    await api.delete(`/llm/providers/${encodeURIComponent(id)}`)
    ElMessage.success('删除成功')
    fetchProviders()
  } catch (e) {
    ElMessage.error(e.detail || '删除失败')
  }
}

function getConnectionMeta(providerId, key) {
  const state = connectionResultByProvider[String(providerId || '')]
  if (!state || typeof state !== 'object') return ''
  return state[key] || ''
}

function connectionTagType(providerId) {
  const state = connectionResultByProvider[String(providerId || '')]
  if (!state) return 'info'
  return state.reachable ? 'success' : 'danger'
}

function connectionTagText(providerId) {
  const state = connectionResultByProvider[String(providerId || '')]
  if (!state) return '未测试'
  return state.reachable ? '已连通' : '连接失败'
}

async function testConnection(row) {
  const providerId = String(row?.id || '').trim()
  if (!providerId) return
  testingProviderId.value = providerId
  try {
    const response = await api.post(`/llm/providers/${encodeURIComponent(providerId)}/test`, {
      model_name: String(testModelByProvider[providerId] || '').trim(),
    })
    const result = response.result || {}
    connectionResultByProvider[providerId] = result
    if (response.status === 'ok' && result.reachable) {
      ElMessage.success('模型接口连接测试成功')
    } else {
      ElMessage.error(result.message || '模型接口连接测试失败')
    }
  } catch (e) {
    connectionResultByProvider[providerId] = {
      reachable: false,
      message: e.detail || '连接失败',
      tested_at: new Date().toISOString(),
    }
    ElMessage.error(e.detail || '模型接口连接测试失败')
  } finally {
    testingProviderId.value = ''
  }
}

onMounted(async () => {
  await Promise.all([fetchProviders(), fetchShareUserOptions()])
})
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

.expand-desc {
  margin-bottom: 12px;
}

.expand-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
