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
            <span class="expand-actions__label">测试模型</span>
            <div class="expand-actions__buttons">
              <el-button
                v-for="action in getProviderTestActions(row)"
                :key="`${row.id}-${action.modelName || 'auto'}`"
                :type="action.primary ? 'primary' : ''"
                plain
                size="small"
                :loading="isTestingAction(row.id, action.modelName)"
                @click="testConnection(row, action.modelName)"
              >
                {{ action.label }}
              </el-button>
            </div>
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
      <el-table-column label="模型列表" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">{{ formatProviderModels(row) }}</template>
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
          <el-button
            v-for="action in getPrimaryProviderActions(row)"
            :key="`${row.id}-${action.key}`"
            text
            :type="action.type"
            :loading="action.key === 'test' && testingProviderId === row.id"
            @click="handleProviderAction(row, action.key)"
          >
            {{ action.label }}
          </el-button>
          <el-dropdown
            v-if="getOverflowProviderActions(row).length"
            trigger="click"
            @command="(actionKey) => handleProviderAction(row, actionKey)"
          >
            <el-button text type="primary" size="small">更多</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="action in getOverflowProviderActions(row)"
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
    <el-empty v-if="!loading && !providers.length" description="暂无模型供应商" :image-size="60" />

    <el-dialog v-model="showDialog" :title="dialogTitle()" width="860px">
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
        <el-form-item label="模型配置">
          <div class="model-config-editor">
            <div
              v-for="(item, index) in form.model_configs"
              :key="item.key"
              class="model-config-row"
            >
              <el-input
                v-model="item.name"
                class="model-config-row__name"
                placeholder="模型名，例如：gpt-4.1"
              />
              <el-select
                v-model="item.model_type"
                class="model-config-row__type"
                placeholder="选择模型类型"
              >
                <el-option
                  v-for="option in modelTypeOptions"
                  :key="option.id"
                  :label="option.label"
                  :value="option.id"
                />
              </el-select>
              <el-button
                :type="form.default_model === String(item.name || '').trim() ? 'primary' : ''"
                plain
                @click="markDefaultModel(item)"
              >
                {{ form.default_model === String(item.name || '').trim() ? '默认模型' : '设为默认' }}
              </el-button>
              <el-button
                text
                type="danger"
                :disabled="form.model_configs.length <= 1"
                @click="removeModelConfig(index)"
              >
                删除
              </el-button>
            </div>
            <div class="model-config-editor__actions">
              <el-button @click="addModelConfig">添加模型</el-button>
              <span class="model-config-editor__hint">
                模型类型来自字典模块，后续可以继续扩展新的能力分类。
              </span>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="默认模型">
          <el-select
            v-model="form.default_model"
            :disabled="!normalizedFormModelConfigs.length"
            placeholder="请选择默认模型"
            style="width: 100%"
          >
            <el-option
              v-for="item in normalizedFormModelConfigs"
              :key="item.name"
              :label="item.name"
              :value="item.name"
            >
              <div class="model-option-line">
                <span>{{ item.name }}</span>
                <span class="model-option-line__meta">{{ formatModelTypeLabel(item.model_type) }}</span>
              </div>
            </el-option>
          </el-select>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'
import { fetchDictionary } from '@/utils/dictionaries.js'
import { canManageRecord, getOwnershipDeniedMessage } from '@/utils/ownership.js'
import {
  buildModelTypeMetaMap,
  FALLBACK_MODEL_TYPE_OPTIONS,
  normalizeProviderModelConfigs,
  normalizeProviderModelNames,
} from '@/utils/llm-models.js'

const loading = ref(false)
const saving = ref(false)
const providers = ref([])
const shareUserOptions = ref([])
const modelTypeOptions = ref(FALLBACK_MODEL_TYPE_OPTIONS)
const showDialog = ref(false)
const editingId = ref('')
const dialogMode = ref('create')
const testingProviderId = ref('')
const testingModelName = ref('')
const connectionResultByProvider = reactive({})
const form = reactive({
  name: '',
  provider_type: 'openai-compatible',
  base_url: '',
  api_key: '',
  model_configs: [],
  default_model: '',
  enabled: true,
  extra_headers_text: '',
  shared_usernames: [],
})

const modelTypeMetaMap = computed(() => buildModelTypeMetaMap(modelTypeOptions.value))
const normalizedFormModelConfigs = computed(() => normalizeProviderModelConfigs({ model_configs: form.model_configs }, modelTypeOptions.value))

let modelConfigSeed = 0

function createModelConfig(name = '', modelType = '') {
  modelConfigSeed += 1
  const fallbackType = modelTypeOptions.value[0]?.id || 'text_generation'
  return {
    key: `model-config-${modelConfigSeed}`,
    name: String(name || '').trim(),
    model_type: String(modelType || fallbackType).trim() || fallbackType,
  }
}

function resetForm() {
  form.name = ''
  form.provider_type = 'openai-compatible'
  form.base_url = ''
  form.api_key = ''
  form.model_configs = [createModelConfig()]
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
  const modelConfigs = normalizeProviderModelConfigs(row, modelTypeOptions.value)
  form.model_configs = modelConfigs.length
    ? modelConfigs.map((item) => createModelConfig(item.name, item.model_type))
    : [createModelConfig()]
  form.default_model = String(row?.default_model || '')
  form.enabled = row?.enabled !== false
  const headers = row?.extra_headers && typeof row.extra_headers === 'object' ? row.extra_headers : {}
  form.extra_headers_text = Object.keys(headers).length ? JSON.stringify(headers, null, 2) : ''
  form.shared_usernames = Array.isArray(row?.shared_usernames) ? row.shared_usernames.map((item) => String(item || '').trim()).filter(Boolean) : []
  syncDefaultModelSelection()
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

function addModelConfig() {
  form.model_configs.push(createModelConfig())
}

function removeModelConfig(index) {
  form.model_configs.splice(index, 1)
  if (!form.model_configs.length) {
    form.model_configs.push(createModelConfig())
  }
  syncDefaultModelSelection()
}

function markDefaultModel(item) {
  const modelName = String(item?.name || '').trim()
  if (!modelName) {
    ElMessage.warning('请先填写模型名称')
    return
  }
  form.default_model = modelName
}

function syncDefaultModelSelection() {
  const values = normalizedFormModelConfigs.value
  if (values.some((item) => item.name === form.default_model)) return
  form.default_model = values[0]?.name || ''
}

function formatModelTypeLabel(modelType) {
  const meta = modelTypeMetaMap.value.get(String(modelType || '').trim())
  return meta?.label || '文本生成'
}

function formatProviderModels(row) {
  const values = normalizeProviderModelConfigs(row, modelTypeOptions.value)
  if (!values.length) return '-'
  return values
    .map((item) => `${item.name} [${formatModelTypeLabel(item.model_type)}]`)
    .join(', ')
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

async function fetchModelTypeOptions() {
  try {
    const data = await fetchDictionary('llm_model_types')
    const options = Array.isArray(data?.options) ? data.options : []
    if (options.length) {
      modelTypeOptions.value = options
    }
  } catch (e) {
    modelTypeOptions.value = FALLBACK_MODEL_TYPE_OPTIONS
    ElMessage.error(e.detail || '加载模型类型失败')
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

  const modelConfigs = normalizedFormModelConfigs.value
  if (!modelConfigs.length) {
    ElMessage.warning('请至少添加一个模型')
    return
  }
  const preferredDefaultModel = String(form.default_model || '').trim()
  const defaultModel = modelConfigs.some((item) => item.name === preferredDefaultModel)
    ? preferredDefaultModel
    : modelConfigs[0].name
  form.default_model = defaultModel

  const payload = {
    name: form.name.trim(),
    provider_type: form.provider_type,
    base_url: form.base_url.trim(),
    model_configs: modelConfigs.map((item) => ({
      name: item.name,
      model_type: item.model_type,
    })),
    default_model: defaultModel,
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

function canManageProvider(row) {
  return canManageRecord(row)
}

function getProviderActions() {
  return [
    { key: 'test', label: '测试连接', type: 'success' },
    { key: 'duplicate', label: '复制', type: 'warning' },
    { key: 'edit', label: '编辑', type: 'primary', requiresManage: true },
    { key: 'delete', label: '删除', type: 'danger', requiresManage: true },
  ]
}

function getPrimaryProviderActions(row) {
  return getProviderActions(row).map((item) => ({
    ...item,
    disabled: item.requiresManage ? !canManageProvider(row) : false,
  })).slice(0, 3)
}

function getOverflowProviderActions(row) {
  return getProviderActions(row).map((item) => ({
    ...item,
    disabled: item.requiresManage ? !canManageProvider(row) : false,
  })).slice(3)
}

function handleProviderAction(row, actionKey) {
  switch (actionKey) {
    case 'test':
      void testConnection(row, getPrimaryTestModel(row))
      break
    case 'duplicate':
      openDuplicate(row)
      break
    case 'edit':
      if (!canManageProvider(row)) {
        ElMessage.warning(getOwnershipDeniedMessage(row, '编辑'))
        return
      }
      openEdit(row)
      break
    case 'delete':
      if (!canManageProvider(row)) {
        ElMessage.warning(getOwnershipDeniedMessage(row, '删除'))
        return
      }
      void removeProvider(row)
      break
    default:
      break
  }
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

function normalizeProviderModels(row) {
  return normalizeProviderModelNames(row, modelTypeOptions.value)
}

function getPrimaryTestModel(row) {
  return normalizeProviderModels(row)[0] || ''
}

function getProviderTestActions(row) {
  const models = normalizeProviderModels(row)
  if (!models.length) {
    return [{ modelName: '', label: '按默认配置测试', primary: true }]
  }
  const defaultModel = String(row?.default_model || '').trim()
  return models.map((modelName, index) => ({
    modelName,
    label: index === 0 && defaultModel === modelName ? `默认模型 · ${modelName}` : modelName,
    primary: index === 0,
  }))
}

function isTestingAction(providerId, modelName = '') {
  return testingProviderId.value === String(providerId || '') && testingModelName.value === String(modelName || '').trim()
}

async function testConnection(row, modelName = '') {
  const providerId = String(row?.id || '').trim()
  if (!providerId) return
  const normalizedModelName = String(modelName || '').trim()
  testingProviderId.value = providerId
  testingModelName.value = normalizedModelName
  try {
    const response = await api.post(`/llm/providers/${encodeURIComponent(providerId)}/test`, {
      model_name: normalizedModelName,
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
    testingModelName.value = ''
  }
}

onMounted(async () => {
  await Promise.all([fetchProviders(), fetchShareUserOptions(), fetchModelTypeOptions()])
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
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
}

.expand-actions__label {
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 32px;
}

.expand-actions__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.model-config-editor {
  display: grid;
  gap: 10px;
  width: 100%;
}

.model-config-row {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(180px, 220px) auto auto;
  gap: 8px;
  align-items: center;
}

.model-config-row__name,
.model-config-row__type {
  width: 100%;
}

.model-config-editor__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.model-config-editor__hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.model-option-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.model-option-line__meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
