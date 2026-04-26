<template>
  <div v-loading="loading" class="settings-page">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__eyebrow">Model Access</div>
        <h1 class="settings-hero__title">模型供应商管理</h1>
        <p class="settings-hero__summary">
          管理可用模型入口、共享范围和连通性配置，列表默认按最新创建优先展示。
        </p>
        <div class="settings-hero__meta">
          <span>总供应商 {{ providers.length }}</span>
          <span>当前筛选 {{ filteredProviders.length }}</span>
        </div>
      </div>
      <div class="settings-hero__actions">
        <el-button :loading="importingPresets" @click="importMainstreamPresets">导入主流模板</el-button>
        <el-button @click="fetchProviders">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增供应商</el-button>
      </div>
    </section>

    <section class="filter-panel">
      <div class="filter-panel__grid">
        <el-input
          v-model="filters.query"
          clearable
          placeholder="搜索名称、地址、创建人或模型"
        />
        <el-select v-model="filters.providerType" clearable placeholder="供应商类型">
          <el-option label="全部类型" value="" />
          <el-option
            v-for="item in providerTypeOptions"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
        <el-select v-model="filters.sort" placeholder="排序方式">
          <el-option label="最新创建" value="created_desc" />
          <el-option label="最早创建" value="created_asc" />
          <el-option label="名称 A-Z" value="name_asc" />
        </el-select>
        <el-select v-model="pageSize" placeholder="每页条数">
          <el-option :value="10" label="10 条/页" />
          <el-option :value="20" label="20 条/页" />
          <el-option :value="50" label="50 条/页" />
        </el-select>
      </div>
    </section>

    <section class="table-panel">
      <div class="table-panel__head">
        <div>
          <div class="table-panel__eyebrow">Provider Matrix</div>
          <div class="table-panel__title">供应商列表</div>
        </div>
        <div class="table-panel__meta">共 {{ filteredProviders.length }} 条</div>
      </div>

      <el-table :data="pagedProviders" stripe class="responsive-provider-table">
      <el-table-column type="expand">
        <template #default="{ row }">
          <el-descriptions :column="2" border size="small" class="expand-desc">
            <el-descriptions-item label="连接状态">
              <el-tag :type="connectionTagType(row.id)" size="small">{{ connectionTagText(row.id) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="最近测试时间">{{ formatDateTime(getConnectionMeta(row.id, 'tested_at'), { withSeconds: true }) }}</el-descriptions-item>
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
      <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
      <el-table-column prop="owner_username" label="创建人" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.owner_username || '-' }}</template>
      </el-table-column>
      <el-table-column prop="provider_type" label="类型" min-width="140" show-overflow-tooltip />
      <el-table-column prop="base_url" label="Base URL" min-width="200" show-overflow-tooltip />
      <el-table-column label="共享用户" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatSharedUsers(row.shared_usernames) }}
        </template>
      </el-table-column>
      <el-table-column label="模型列表" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ formatProviderModels(row) }}</template>
      </el-table-column>
      <el-table-column prop="default_model" label="默认模型" min-width="150" show-overflow-tooltip />
      <el-table-column label="API Key" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">{{ row.api_key_masked || '-' }}</template>
      </el-table-column>
      <el-table-column label="启用" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="180">
        <template #default="{ row }">{{ formatDateTime(row.created_at, { withSeconds: true }) }}</template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="180">
        <template #default="{ row }">{{ formatDateTime(row.updated_at, { withSeconds: true }) }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="320" fixed="right" class-name="table-action-column">
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

      <div v-if="filteredProviders.length" class="table-panel__pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, jumper, sizes"
          :total="filteredProviders.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>

      <el-empty v-if="!loading && !filteredProviders.length" description="暂无模型供应商" :image-size="60" />
    </section>

    <el-dialog v-model="showDialog" :title="dialogTitle()" width="min(860px, calc(100vw - 24px))">
      <el-form :model="form" label-width="120px">
        <el-form-item label="主流模板">
          <div class="provider-preset-panel">
            <div class="provider-preset-row">
              <el-tag
                v-for="preset in PROVIDER_PRESETS"
                :key="preset.key"
                class="provider-preset-tag"
                :type="appliedPresetKey === preset.key ? 'success' : 'info'"
                effect="plain"
                @click="applyProviderPreset(preset)"
              >
                {{ preset.label }}
              </el-tag>
            </div>
            <div v-if="activePresetMeta" class="provider-preset-note">
              <div>{{ activePresetMeta.note }}</div>
              <div>Base URL：{{ activePresetMeta.base_url }}</div>
              <div>示例模型：{{ activePresetMeta.model_configs.map((item) => item.name).join('、') }}</div>
            </div>
            <div v-else class="provider-preset-note">
              点击上方模板可自动填充主流供应商的类型、Base URL 和示例模型；模型名可按实际账号权限调整。
            </div>
          </div>
        </el-form-item>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime, parseDateTime } from '@/utils/date.js'
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
const importingPresets = ref(false)
const providers = ref([])
const shareUserOptions = ref([])
const modelTypeOptions = ref(FALLBACK_MODEL_TYPE_OPTIONS)
const showDialog = ref(false)
const editingId = ref('')
const dialogMode = ref('create')
const testingProviderId = ref('')
const testingModelName = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const appliedPresetKey = ref('')
const connectionResultByProvider = reactive({})
const filters = reactive({
  query: '',
  providerType: '',
  sort: 'created_desc',
})
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
const providerTypeOptions = computed(() =>
  Array.from(
    new Set(
      (providers.value || [])
        .map((item) => String(item?.provider_type || '').trim())
        .filter(Boolean),
    ),
  ),
)

function normalizeTimestamp(value) {
  return parseDateTime(value)?.getTime() || 0
}

const filteredProviders = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  const providerType = String(filters.providerType || '').trim()
  const list = (providers.value || []).filter((item) => {
    const matchesKeyword =
      !keyword ||
      String(item?.name || '').toLowerCase().includes(keyword) ||
      String(item?.base_url || '').toLowerCase().includes(keyword) ||
      String(item?.owner_username || '').toLowerCase().includes(keyword) ||
      formatProviderModels(item).toLowerCase().includes(keyword)
    const matchesProviderType = !providerType || String(item?.provider_type || '').trim() === providerType
    return matchesKeyword && matchesProviderType
  })
  return list.sort((left, right) => {
    if (filters.sort === 'created_asc') {
      return normalizeTimestamp(left?.created_at) - normalizeTimestamp(right?.created_at)
    }
    if (filters.sort === 'name_asc') {
      return String(left?.name || '').localeCompare(String(right?.name || ''), 'zh-CN')
    }
    return normalizeTimestamp(right?.created_at) - normalizeTimestamp(left?.created_at)
  })
})

const pagedProviders = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredProviders.value.slice(start, start + pageSize.value)
})

watch(
  () => [filters.query, filters.providerType, filters.sort, pageSize.value],
  () => {
    currentPage.value = 1
  },
)

const PROVIDER_PRESETS = [
  {
    key: 'openai',
    label: 'OpenAI',
    name: 'OpenAI',
    provider_type: 'openai-compatible',
    base_url: 'https://api.openai.com/v1',
    note: '官方标准 OpenAI 兼容入口，适合作为通用基准供应商。',
    model_configs: [
      { name: 'gpt-4.1', model_type: 'multimodal_chat' },
      { name: 'gpt-4o-mini', model_type: 'multimodal_chat' },
    ],
    default_model: 'gpt-4.1',
  },
  {
    key: 'deepseek',
    label: 'DeepSeek',
    name: 'DeepSeek',
    provider_type: 'openai-compatible',
    base_url: 'https://api.deepseek.com',
    note: 'DeepSeek 官方 OpenAI 兼容入口，适合通用对话与推理模型。',
    model_configs: [
      { name: 'deepseek-chat', model_type: 'text_generation' },
      { name: 'deepseek-reasoner', model_type: 'text_generation' },
    ],
    default_model: 'deepseek-chat',
  },
  {
    key: 'gemini',
    label: 'Gemini',
    name: 'Google Gemini',
    provider_type: 'openai-compatible',
    base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
    note: 'Google Gemini 的 OpenAI 兼容入口，适合图文理解与通用对话。',
    model_configs: [
      { name: 'gemini-2.5-flash', model_type: 'multimodal_chat' },
      { name: 'gemini-2.5-pro', model_type: 'multimodal_chat' },
    ],
    default_model: 'gemini-2.5-flash',
  },
  {
    key: 'zhipu',
    label: '智谱 GLM',
    name: '智谱 GLM',
    provider_type: 'openai-compatible',
    base_url: 'https://open.bigmodel.cn/api/paas/v4',
    note: '智谱 OpenAI 兼容入口，已适配 /api/paas/v4，并可用于 TTS 与音色复刻场景。',
    model_configs: [
      { name: 'glm-5', model_type: 'text_generation' },
      { name: 'glm-4.5-air', model_type: 'text_generation' },
      { name: 'glm-tts', model_type: 'audio_generation' },
      { name: 'glm-tts-clone', model_type: 'audio_generation' },
      { name: 'glm-asr-2512', model_type: 'audio_transcription' },
    ],
    default_model: 'glm-5',
  },
  {
    key: 'dashscope',
    label: '阿里百炼',
    name: '阿里云百炼',
    provider_type: 'openai-compatible',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    note: 'DashScope OpenAI 兼容入口，适合 Qwen 系列模型接入。',
    model_configs: [
      { name: 'qwen-plus', model_type: 'text_generation' },
      { name: 'qwen-max', model_type: 'text_generation' },
    ],
    default_model: 'qwen-plus',
  },
  {
    key: 'openrouter',
    label: 'OpenRouter',
    name: 'OpenRouter',
    provider_type: 'openai-compatible',
    base_url: 'https://openrouter.ai/api/v1',
    note: '聚合路由入口，适合统一接入多家模型；如需归因统计可额外补请求头。',
    model_configs: [
      { name: 'openai/gpt-4o-mini', model_type: 'multimodal_chat' },
      { name: 'deepseek/deepseek-chat', model_type: 'text_generation' },
    ],
    default_model: 'openai/gpt-4o-mini',
  },
  {
    key: 'moonshot',
    label: 'Moonshot',
    name: 'Moonshot AI',
    provider_type: 'openai-compatible',
    base_url: 'https://api.moonshot.cn/v1',
    note: 'Moonshot/Kimi 官方兼容入口，适合中文长文本与通用对话。',
    model_configs: [
      { name: 'kimi-latest', model_type: 'text_generation' },
      { name: 'moonshot-v1-8k', model_type: 'text_generation' },
    ],
    default_model: 'kimi-latest',
  },
  {
    key: 'siliconflow',
    label: 'SiliconFlow',
    name: 'SiliconFlow',
    provider_type: 'openai-compatible',
    base_url: 'https://api.siliconflow.cn/v1',
    note: 'SiliconFlow 聚合入口，适合快速试用开源与商用模型。',
    model_configs: [
      { name: 'Qwen/Qwen3-32B', model_type: 'text_generation' },
      { name: 'deepseek-ai/DeepSeek-V3', model_type: 'text_generation' },
    ],
    default_model: 'Qwen/Qwen3-32B',
  },
]

const activePresetMeta = computed(() => PROVIDER_PRESETS.find((item) => item.key === appliedPresetKey.value) || null)

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
  appliedPresetKey.value = ''
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
  appliedPresetKey.value = matchPresetKey({
    name: form.name,
    provider_type: form.provider_type,
    base_url: form.base_url,
  })
  syncDefaultModelSelection()
}

function matchPresetKey(row) {
  const normalizedBaseUrl = String(row?.base_url || '').trim().replace(/\/+$/, '')
  const normalizedType = String(row?.provider_type || '').trim()
  return PROVIDER_PRESETS.find(
    (item) => item.provider_type === normalizedType && item.base_url === normalizedBaseUrl,
  )?.key || ''
}

function applyProviderPreset(preset) {
  if (!preset || typeof preset !== 'object') return
  form.name = String(preset.name || '')
  form.provider_type = String(preset.provider_type || 'openai-compatible')
  form.base_url = String(preset.base_url || '')
  form.model_configs = Array.isArray(preset.model_configs) && preset.model_configs.length
    ? preset.model_configs.map((item) => createModelConfig(item.name, item.model_type))
    : [createModelConfig()]
  form.default_model = String(preset.default_model || preset.model_configs?.[0]?.name || '')
  form.extra_headers_text = preset.extra_headers ? JSON.stringify(preset.extra_headers, null, 2) : ''
  appliedPresetKey.value = String(preset.key || '')
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
    providers.value = Array.isArray(data?.providers) ? data.providers : []
  } catch (e) {
    ElMessage.error(e.detail || '加载模型供应商失败')
    providers.value = []
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

function buildPresetPayload(preset) {
  const modelConfigs = Array.isArray(preset?.model_configs) ? preset.model_configs : []
  return {
    name: String(preset?.name || '').trim(),
    provider_type: String(preset?.provider_type || 'openai-compatible').trim(),
    base_url: String(preset?.base_url || '').trim(),
    model_configs: modelConfigs.map((item) => ({
      name: String(item?.name || '').trim(),
      model_type: String(item?.model_type || modelTypeOptions.value[0]?.id || 'text_generation').trim(),
    })),
    default_model: String(preset?.default_model || modelConfigs[0]?.name || '').trim(),
    enabled: false,
    extra_headers: preset?.extra_headers && typeof preset.extra_headers === 'object' ? preset.extra_headers : {},
    shared_usernames: [],
    api_key: '',
  }
}

async function importMainstreamPresets() {
  try {
    await ElMessageBox.confirm(
      '将批量创建主流供应商模板，默认处于禁用状态。导入后请补充 API Key、按需调整模型并手动启用。',
      '导入主流模板',
      { type: 'info' },
    )
  } catch {
    return
  }

  importingPresets.value = true
  try {
    const existingKeys = new Set(
      (Array.isArray(providers.value) ? providers.value : []).map(
        (item) => `${String(item?.name || '').trim()}@@${String(item?.base_url || '').trim().replace(/\/+$/, '')}`,
      ),
    )
    let createdCount = 0
    let skippedCount = 0
    for (const preset of PROVIDER_PRESETS) {
      const dedupeKey = `${preset.name}@@${preset.base_url}`
      if (existingKeys.has(dedupeKey)) {
        skippedCount += 1
        continue
      }
      await api.post('/llm/providers', buildPresetPayload(preset))
      existingKeys.add(dedupeKey)
      createdCount += 1
    }
    await fetchProviders()
    if (!createdCount) {
      ElMessage.info(`主流模板已存在，已跳过 ${skippedCount} 条`)
      return
    }
    ElMessage.success(`已导入 ${createdCount} 条主流模板${skippedCount ? `，跳过 ${skippedCount} 条重复项` : ''}`)
  } catch (e) {
    ElMessage.error(e?.detail || '导入主流模板失败')
  } finally {
    importingPresets.value = false
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
.settings-page {
  display: grid;
  gap: 18px;
}

.settings-hero,
.filter-panel,
.table-panel {
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.74);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(18px);
}

.settings-hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 26px;
}

.settings-hero__copy {
  display: grid;
  gap: 10px;
}

.settings-hero__eyebrow,
.table-panel__eyebrow {
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #64748b;
}

.settings-hero__title,
.table-panel__title {
  margin: 0;
  font-size: 28px;
  color: #0f172a;
}

.settings-hero__summary {
  margin: 0;
  max-width: 620px;
  color: #475569;
  line-height: 1.7;
}

.settings-hero__meta,
.table-panel__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #64748b;
  font-size: 13px;
}

.settings-hero__actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-panel {
  padding: 18px 20px;
}

.filter-panel__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.table-panel {
  padding: 20px;
  overflow: hidden;
}

.table-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.table-panel__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
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

.provider-preset-panel {
  display: grid;
  gap: 10px;
  width: 100%;
}

.provider-preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.provider-preset-tag {
  cursor: pointer;
}

.provider-preset-note {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.7;
}

.model-config-row {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(160px, 220px) auto auto;
  gap: 8px;
  align-items: center;
}

.responsive-provider-table :deep(.table-action-column .cell) {
  justify-content: flex-start;
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

@media (max-width: 960px) {
  .settings-hero,
  .table-panel__head {
    flex-direction: column;
    align-items: flex-start;
  }

  .filter-panel__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .model-config-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .filter-panel__grid {
    grid-template-columns: 1fr;
  }
}
</style>
