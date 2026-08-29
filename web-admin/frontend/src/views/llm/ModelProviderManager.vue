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
        <el-button :loading="importingPresets" @click="importMainstreamPresets"
          >导入主流模板</el-button
        >
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
        <el-select
          v-model="filters.providerType"
          clearable
          placeholder="供应商类型"
        >
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
        <div class="table-panel__meta">
          共 {{ filteredProviders.length }} 条
        </div>
      </div>

      <el-table
        ref="providerTableRef"
        :data="pagedProviders"
        stripe
        class="responsive-provider-table"
        :style="providerTableStyle"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="provider-expanded-content">
              <el-descriptions
                :column="2"
                border
                size="small"
                class="expand-desc"
              >
                <el-descriptions-item label="连接状态">
                  <el-tag :type="connectionTagType(row.id)" size="small">{{
                    connectionTagText(row.id)
                  }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="最近测试时间">{{
                  formatDateTime(getConnectionMeta(row.id, "tested_at"), {
                    withSeconds: true,
                  })
                }}</el-descriptions-item>
                <el-descriptions-item label="测试模型">{{
                  getConnectionMeta(row.id, "model_tested") || "-"
                }}</el-descriptions-item>
                <el-descriptions-item label="延迟(ms)">{{
                  getConnectionMeta(row.id, "latency_ms") || "-"
                }}</el-descriptions-item>
                <el-descriptions-item label="请求地址" :span="2">
                  {{ formatConnectionRequestAddresses(row.id) || "-" }}
                </el-descriptions-item>
                <el-descriptions-item label="返回信息" :span="2">
                  {{ getConnectionMeta(row.id, "message") || "-" }}
                </el-descriptions-item>
              </el-descriptions>
              <ProviderCapabilityTestResults
                :results="getConnectionResults(row.id)"
                :format-model-type-label="formatModelTypeLabel"
              />
              <div class="expand-actions">
                <div class="expand-actions__copy">
                  <span class="expand-actions__label">测试模型</span>
                  <span class="expand-actions__hint"
                    >图片、视频和音频测试会真实生成内容，可能产生供应商费用。</span
                  >
                </div>
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
            </div>
          </template>
        </el-table-column>
        <el-table-column
          prop="name"
          label="名称"
          min-width="140"
          show-overflow-tooltip
        />
        <el-table-column
          prop="owner_username"
          label="创建人"
          min-width="120"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{
            row.owner_username || "-"
          }}</template>
        </el-table-column>
        <el-table-column
          prop="provider_type"
          label="类型"
          min-width="140"
          show-overflow-tooltip
        />
        <el-table-column
          prop="base_url"
          label="Base URL"
          min-width="200"
          show-overflow-tooltip
        />

        <el-table-column label="模型列表" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{
            formatProviderModels(row)
          }}</template>
        </el-table-column>
        <el-table-column
          prop="default_model"
          label="默认模型"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column label="API Key" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{
            row.api_key_masked || maskApiKey(row.api_key) || "-"
          }}</template>
        </el-table-column>
        <el-table-column label="启用" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{
              row.enabled ? "是" : "否"
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180">
          <template #default="{ row }">{{
            formatDateTime(row.created_at, { withSeconds: true })
          }}</template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="180">
          <template #default="{ row }">{{
            formatDateTime(row.updated_at, { withSeconds: true })
          }}</template>
        </el-table-column>
        <el-table-column
          label="操作"
          min-width="320"
          fixed="right"
          class-name="table-action-column"
        >
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

      <el-empty
        v-if="!loading && !filteredProviders.length"
        description="暂无模型供应商"
        :image-size="60"
      />
    </section>

    <ModelProviderCreateDialog
      v-model="createDialogVisible"
      @saved="fetchProviders"
    />

    <el-dialog
      v-if="dialogMode !== 'create'"
      v-model="showDialog"
      :title="dialogTitle()"
      width="min(860px, calc(100vw - 24px))"
    >
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
              <div>
                接口规范：{{
                  formatProviderInterfaceLabel(activePresetMeta.provider_type)
                }}（已自动选择）
              </div>
              <div>
                示例模型：{{
                  activePresetMeta.model_configs
                    .map((item) => item.name)
                    .join("、")
                }}
              </div>
            </div>
            <div v-else class="provider-preset-note">
              点击上方模板可自动填充主流供应商的接口规范、Base URL
              和示例模型；模型名可按实际账号权限调整。
            </div>
            <div class="provider-standard-note">
              OpenAI 官方最新模型优先使用
              Responses；Ollama、DeepSeek、智谱、Gemini 优先使用
              OpenAI-compatible；Claude 需通过兼容网关或后续 Anthropic
              适配；Codex 属于外部执行器，不建议作为普通模型供应商。
            </div>
          </div>
        </el-form-item>
        <el-form-item label="供应商名称" required>
          <el-input v-model="form.name" placeholder="例如：OpenAI 主账号" />
        </el-form-item>
        <el-form-item label="接口规范">
          <div class="provider-interface-panel">
            <el-radio-group
              v-model="form.provider_type"
              class="provider-interface-options"
            >
              <el-radio-button
                v-for="option in PROVIDER_INTERFACE_OPTIONS"
                :key="option.value"
                :label="option.value"
              >
                {{ option.label }}
              </el-radio-button>
            </el-radio-group>
            <div class="provider-interface-help">
              <div class="provider-interface-help__head">
                <strong>{{ activeProviderTypeMeta.label }}</strong>
                <el-tag
                  size="small"
                  :type="providerInterfaceAssistTagType"
                  effect="plain"
                >
                  {{ providerInterfaceAssistText }}
                </el-tag>
              </div>
              <span>{{ activeProviderTypeMeta.description }}</span>
              <span
                v-if="activePresetMeta && !isUsingPresetProviderType"
                class="provider-interface-help__warning"
              >
                {{ activePresetMeta.label }} 模板推荐
                {{
                  formatProviderInterfaceLabel(activePresetMeta.provider_type)
                }}。
              </span>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="Base URL" required>
          <el-input
            v-model="form.base_url"
            placeholder="例如：https://api.openai.com/v1"
          />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" :placeholder="apiKeyPlaceholder()" />
        </el-form-item>
        <el-form-item label="模型配置">
          <div class="model-config-editor">
            <div class="model-config-header">
              <span>模型名称</span>
              <span>能力类型</span>
              <span>默认</span>
              <span>操作</span>
            </div>
            <div
              v-for="(item, index) in form.model_configs"
              :key="item.key"
              class="model-config-row"
            >
              <el-input
                v-model="item.name"
                class="model-config-row__name"
                placeholder="模型名，例如：gpt-5.5"
              />
              <div class="model-config-row__type-cell">
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
                  >
                    <div class="model-type-option">
                      <span>{{ option.label }}</span>
                      <span>{{ option.id }}</span>
                    </div>
                  </el-option>
                </el-select>
                <div class="model-config-row__type-help">
                  {{ getModelTypeDescription(item.model_type) }}
                </div>
              </div>
              <el-button
                :type="
                  form.default_model === String(item.name || '').trim()
                    ? 'primary'
                    : ''
                "
                plain
                @click="markDefaultModel(item)"
              >
                {{
                  form.default_model === String(item.name || "").trim()
                    ? "默认模型"
                    : "设为默认"
                }}
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
              <el-button
                :loading="discoveringModels"
                :disabled="!form.base_url.trim()"
                @click="discoverModels"
              >
                获取模型
              </el-button>
              <span class="model-config-editor__hint">
                模型能力来自字典模块；接口规范由上方供应商配置决定。
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
                <span class="model-option-line__meta">{{
                  formatModelTypeLabel(item.model_type)
                }}</span>
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
        <!-- <el-form-item label="共享给用户">
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
        </el-form-item> -->
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import {
  computed,
  h,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  discoverNativeProviderModels,
  hasNativeDesktopBridge,
  testNativeProviderModel,
} from "@/utils/native-desktop-bridge.js";
import {
  readAllLocalProjectRelations,
  readLocalEntities,
  removeLocalEntity,
  hydrateLocalProjectRepository,
  writeLocalEntities,
  upsertLocalEntity,
} from "@/services/local-project-repository.js";
import { formatDateTime, parseDateTime } from "@/utils/date.js";
import ProviderCapabilityTestResults from "@/components/llm/ProviderCapabilityTestResults.vue";
import ModelProviderCreateDialog from "@/components/llm/ModelProviderCreateDialog.vue";
import {
  fetchBuiltinModelProviders,
  isServerBuiltinModelProvider,
  mergeBuiltinModelProviders,
  testBuiltinModelProvider,
} from "@/services/builtin-model-providers.js";
import {
  buildModelTypeMetaMap,
  FALLBACK_MODEL_TYPE_OPTIONS,
  normalizeProviderModelConfigs,
  normalizeProviderModelNames,
} from "@/utils/llm-models.js";

const loading = ref(false);
const saving = ref(false);
const importingPresets = ref(false);
const discoveringModels = ref(false);
const providers = ref([]);
const shareUserOptions = ref([]);
const modelTypeOptions = ref(FALLBACK_MODEL_TYPE_OPTIONS);
const showDialog = ref(false);
const createDialogVisible = ref(false);
const editingId = ref("");
const dialogMode = ref("create");
const testingProviderId = ref("");
const testingModelName = ref("");
const currentPage = ref(1);
const pageSize = ref(10);
const appliedPresetKey = ref("");
const providerTableRef = ref(null);
const providerTableVisibleWidth = ref(0);
let providerTableResizeObserver = null;

const providerTableStyle = computed(() =>
  providerTableVisibleWidth.value
    ? {
        "--provider-table-visible-width": `${providerTableVisibleWidth.value}px`,
      }
    : {},
);

function syncProviderTableVisibleWidth() {
  const tableElement = providerTableRef.value?.$el;
  if (!(tableElement instanceof HTMLElement)) return;
  providerTableVisibleWidth.value = tableElement.clientWidth;
}
const connectionResultByProvider = reactive({});
const connectionResultsByProvider = reactive({});
const filters = reactive({
  query: "",
  providerType: "",
  sort: "created_desc",
});
const form = reactive({
  name: "",
  provider_type: "openai-compatible",
  base_url: "",
  api_key: "",
  model_configs: [],
  default_model: "",
  enabled: true,
  extra_headers_text: "",
  shared_usernames: [],
});
const LOCAL_PROVIDER_ENTITY = "llm_providers";
const LEGACY_PROVIDER_MODEL_SNAPSHOTS_KEY = "liuagent:cached-provider-models";
const DELETED_PROVIDER_IDS_KEY = "llm_providers_deleted_ids";

function createLocalProviderId() {
  const suffix =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `local-provider-${suffix}`;
}

function readLocalProviders() {
  return readLocalEntities(LOCAL_PROVIDER_ENTITY).sort(
    (left, right) =>
      normalizeTimestamp(right?.updated_at || right?.created_at) -
      normalizeTimestamp(left?.updated_at || left?.created_at),
  );
}

function normalizeLegacyProvider(provider = {}) {
  const id = String(provider?.id || provider?.provider_id || "").trim();
  if (!id) return null;
  const models = Array.isArray(provider?.models)
    ? provider.models.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const modelConfigs = Array.isArray(provider?.model_configs)
    ? provider.model_configs
        .map((item) => ({
          name: String(
            item?.name || item?.model_name || item?.model || "",
          ).trim(),
          model_type: String(item?.model_type || "text_generation").trim(),
        }))
        .filter((item) => item.name)
    : models.map((name) => ({ name, model_type: "text_generation" }));
  return {
    ...provider,
    id,
    name: String(provider?.name || provider?.label || id).trim(),
    provider_type: String(
      provider?.provider_type || "openai-compatible",
    ).trim(),
    base_url: String(provider?.base_url || provider?.baseUrl || "").trim(),
    model_configs: modelConfigs,
    default_model: String(
      provider?.default_model || modelConfigs[0]?.name || "",
    ).trim(),
    enabled: provider?.enabled !== false,
  };
}

function collectLegacyLocalProviders() {
  const candidates = [];
  const relations = readAllLocalProjectRelations();
  Object.values(relations || {}).forEach((relation) => {
    if (Array.isArray(relation?.providers))
      candidates.push(...relation.providers);
  });
  try {
    const snapshots = JSON.parse(
      window.localStorage?.getItem(LEGACY_PROVIDER_MODEL_SNAPSHOTS_KEY) || "{}",
    );
    Object.values(snapshots?.scopes || {}).forEach((scope) => {
      if (Array.isArray(scope?.providers)) candidates.push(...scope.providers);
    });
  } catch (error) {
    console.warn("read legacy local provider snapshots failed", error);
  }
  return candidates.map(normalizeLegacyProvider).filter(Boolean);
}

function migrateLegacyLocalProviders() {
  const existing = readLocalEntities(LOCAL_PROVIDER_ENTITY);
  const deletedIds = readDeletedProviderIds();
  const existingIds = new Set(
    existing.map((item) => String(item?.id || "").trim()).filter(Boolean),
  );
  const now = new Date().toISOString();
  collectLegacyLocalProviders().forEach((provider) => {
    if (existingIds.has(provider.id) || deletedIds.has(provider.id)) return;
    upsertLocalEntity(LOCAL_PROVIDER_ENTITY, {
      ...provider,
      created_at: String(provider.created_at || now),
      updated_at: String(provider.updated_at || now),
    });
    existingIds.add(provider.id);
  });
}

function readDeletedProviderIds() {
  try {
    const stored = JSON.parse(
      window.localStorage?.getItem(DELETED_PROVIDER_IDS_KEY) || "[]",
    );
    return new Set(
      Array.isArray(stored)
        ? stored.map((item) => String(item || "").trim()).filter(Boolean)
        : [],
    );
  } catch {
    return new Set();
  }
}

function rememberDeletedProviderId(providerId) {
  const id = String(providerId || "").trim();
  if (!id) return;
  const deletedIds = readDeletedProviderIds();
  deletedIds.add(id);
  window.localStorage?.setItem(
    DELETED_PROVIDER_IDS_KEY,
    JSON.stringify([...deletedIds]),
  );
}

const PROVIDER_INTERFACE_OPTIONS = [
  {
    value: "openai-compatible",
    label: "OpenAI-compatible",
    description:
      "统一走 /chat/completions，适合 DeepSeek、智谱、Gemini、OpenRouter 和多数兼容网关。",
  },
  {
    value: "responses",
    label: "OpenAI Responses",
    description:
      "统一走 /responses，适合明确支持 Responses API 的 OpenAI 系模型。",
  },
  {
    value: "custom",
    label: "Custom",
    description:
      "仅用于保留非标准接入配置；保存前请确认后端调用层已适配该接口。",
  },
];

const modelTypeMetaMap = computed(() =>
  buildModelTypeMetaMap(modelTypeOptions.value),
);
const normalizedFormModelConfigs = computed(() =>
  normalizeProviderModelConfigs(
    { model_configs: form.model_configs },
    modelTypeOptions.value,
  ),
);
const activeProviderTypeMeta = computed(() =>
  resolveProviderInterfaceOption(form.provider_type),
);
const providerTypeOptions = computed(() =>
  Array.from(
    new Set(
      (providers.value || [])
        .map((item) => String(item?.provider_type || "").trim())
        .filter(Boolean),
    ),
  ),
);

function normalizeTimestamp(value) {
  return parseDateTime(value)?.getTime() || 0;
}

const filteredProviders = computed(() => {
  const keyword = String(filters.query || "")
    .trim()
    .toLowerCase();
  const providerType = String(filters.providerType || "").trim();
  const list = (providers.value || []).filter((item) => {
    const matchesKeyword =
      !keyword ||
      String(item?.name || "")
        .toLowerCase()
        .includes(keyword) ||
      String(item?.base_url || "")
        .toLowerCase()
        .includes(keyword) ||
      String(item?.owner_username || "")
        .toLowerCase()
        .includes(keyword) ||
      formatProviderModels(item).toLowerCase().includes(keyword);
    const matchesProviderType =
      !providerType ||
      String(item?.provider_type || "").trim() === providerType;
    return matchesKeyword && matchesProviderType;
  });
  return list.sort((left, right) => {
    if (filters.sort === "created_asc") {
      return (
        normalizeTimestamp(left?.created_at) -
        normalizeTimestamp(right?.created_at)
      );
    }
    if (filters.sort === "name_asc") {
      return String(left?.name || "").localeCompare(
        String(right?.name || ""),
        "zh-CN",
      );
    }
    return (
      normalizeTimestamp(right?.created_at) -
      normalizeTimestamp(left?.created_at)
    );
  });
});

const pagedProviders = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredProviders.value.slice(start, start + pageSize.value);
});

watch(
  () => [filters.query, filters.providerType, filters.sort, pageSize.value],
  () => {
    currentPage.value = 1;
  },
);

const PROVIDER_PRESETS = [
  {
    key: "ollama",
    label: "Ollama",
    name: "Ollama 本地模型",
    provider_type: "openai-compatible",
    base_url: "http://127.0.0.1:11434/v1",
    note: "Ollama 本地 OpenAI 兼容入口，适合接入 Gemma、Llama、Qwen、DeepSeek 等本机模型；API Key 可留空。",
    model_configs: [
      { name: "gemma4", model_type: "text_generation" },
      { name: "gemma3", model_type: "text_generation" },
      { name: "llama3.3", model_type: "text_generation" },
      { name: "qwen3", model_type: "text_generation" },
    ],
    default_model: "gemma4",
  },
  {
    key: "openai",
    label: "OpenAI",
    name: "OpenAI",
    provider_type: "responses",
    base_url: "https://api.openai.com/v1",
    note: "OpenAI 官方 Responses 入口，适合作为最新旗舰模型的通用基准供应商。",
    model_configs: [
      { name: "gpt-5.5", model_type: "multimodal_chat" },
      { name: "gpt-5.4", model_type: "multimodal_chat" },
    ],
    default_model: "gpt-5.5",
  },
  {
    key: "deepseek",
    label: "DeepSeek",
    name: "DeepSeek",
    provider_type: "openai-compatible",
    base_url: "https://api.deepseek.com",
    note: "DeepSeek 官方 OpenAI 兼容入口，适合通用对话与推理模型；旧别名 deepseek-chat/deepseek-reasoner 已不再作为默认模板。",
    model_configs: [
      { name: "deepseek-v4-flash", model_type: "text_generation" },
      { name: "deepseek-v4-pro", model_type: "text_generation" },
    ],
    default_model: "deepseek-v4-flash",
  },
  {
    key: "gemini",
    label: "Gemini",
    name: "Google Gemini",
    provider_type: "openai-compatible",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
    note: "Google Gemini 的 OpenAI 兼容入口，适合图文理解、推理与通用对话。",
    model_configs: [
      { name: "gemini-3.5-flash", model_type: "multimodal_chat" },
      { name: "gemini-3.1-pro", model_type: "multimodal_chat" },
    ],
    default_model: "gemini-3.5-flash",
  },
  {
    key: "zhipu",
    label: "智谱 GLM",
    name: "智谱 GLM",
    provider_type: "openai-compatible",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    note: "智谱 OpenAI 兼容入口，已适配 /api/paas/v4，并可用于文本、视觉、TTS、音色复刻和 ASR 场景。",
    model_configs: [
      { name: "glm-5.2", model_type: "text_generation" },
      { name: "glm-5v-turbo", model_type: "multimodal_chat" },
      { name: "glm-4.5-air", model_type: "text_generation" },
      { name: "glm-tts", model_type: "audio_generation" },
      { name: "glm-tts-clone", model_type: "audio_generation" },
      { name: "glm-asr-2512", model_type: "audio_transcription" },
    ],
    default_model: "glm-5.2",
  },
  {
    key: "dashscope",
    label: "阿里百炼",
    name: "阿里云百炼",
    provider_type: "openai-compatible",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    note: "DashScope OpenAI 兼容入口，适合 Qwen 系列模型接入；官方推荐工作空间专属域名，通用域名仍可作为模板起点。",
    model_configs: [
      { name: "qwen-plus", model_type: "text_generation" },
      { name: "qwen-max", model_type: "text_generation" },
    ],
    default_model: "qwen-plus",
  },
  {
    key: "openrouter",
    label: "OpenRouter",
    name: "OpenRouter",
    provider_type: "openai-compatible",
    base_url: "https://openrouter.ai/api/v1",
    note: "聚合路由入口，适合统一接入多家模型；如需归因统计可额外补请求头。",
    model_configs: [
      { name: "openai/gpt-5.5", model_type: "multimodal_chat" },
      { name: "deepseek/deepseek-v4-flash", model_type: "text_generation" },
    ],
    default_model: "openai/gpt-5.5",
  },
  {
    key: "moonshot",
    label: "Moonshot",
    name: "Moonshot AI",
    provider_type: "openai-compatible",
    base_url: "https://api.moonshot.ai/v1",
    note: "Moonshot/Kimi 官方 OpenAI 兼容入口，适合中文长文本、多模态、工具调用和通用对话。",
    model_configs: [
      { name: "kimi-k2.7-code", model_type: "multimodal_chat" },
      { name: "kimi-k2.6", model_type: "multimodal_chat" },
    ],
    default_model: "kimi-k2.7-code",
  },
  {
    key: "siliconflow",
    label: "SiliconFlow",
    name: "SiliconFlow",
    provider_type: "openai-compatible",
    base_url: "https://api.siliconflow.cn/v1",
    note: "SiliconFlow 聚合入口，适合快速试用开源与商用模型。",
    model_configs: [
      { name: "Qwen/Qwen3-32B", model_type: "text_generation" },
      { name: "deepseek-ai/DeepSeek-V4-Flash", model_type: "text_generation" },
    ],
    default_model: "Qwen/Qwen3-32B",
  },
];

const activePresetMeta = computed(
  () =>
    PROVIDER_PRESETS.find((item) => item.key === appliedPresetKey.value) ||
    null,
);
const isUsingPresetProviderType = computed(() => {
  if (!activePresetMeta.value) return false;
  return (
    String(form.provider_type || "").trim() ===
    String(activePresetMeta.value.provider_type || "").trim()
  );
});
const providerInterfaceAssistTagType = computed(() => {
  if (!activePresetMeta.value) return "info";
  return isUsingPresetProviderType.value ? "success" : "warning";
});
const providerInterfaceAssistText = computed(() => {
  if (!activePresetMeta.value) {
    return String(form.provider_type || "").trim() === "openai-compatible"
      ? "默认推荐"
      : "已手动选择";
  }
  if (isUsingPresetProviderType.value)
    return `${activePresetMeta.value.label} 模板已选择`;
  return "已手动调整";
});

let modelConfigSeed = 0;

function resolveProviderInterfaceOption(value) {
  const normalized = String(value || "").trim();
  return (
    PROVIDER_INTERFACE_OPTIONS.find((item) => item.value === normalized) ||
    PROVIDER_INTERFACE_OPTIONS[0]
  );
}

function formatProviderInterfaceLabel(value) {
  return resolveProviderInterfaceOption(value).label;
}

function createModelConfig(name = "", modelType = "") {
  modelConfigSeed += 1;
  const fallbackType = modelTypeOptions.value[0]?.id || "text_generation";
  return {
    key: `model-config-${modelConfigSeed}`,
    name: String(name || "").trim(),
    model_type: String(modelType || fallbackType).trim() || fallbackType,
  };
}

function resetForm() {
  form.name = "";
  form.provider_type = "openai-compatible";
  form.base_url = "";
  form.api_key = "";
  form.model_configs = [createModelConfig()];
  form.default_model = "";
  form.enabled = true;
  form.extra_headers_text = "";
  form.shared_usernames = [];
  appliedPresetKey.value = "";
}

function buildDuplicateName(name) {
  const base = String(name || "").trim();
  return base ? `${base} 副本` : "供应商副本";
}

function populateForm(row, { duplicate = false } = {}) {
  form.name = duplicate
    ? buildDuplicateName(row?.name)
    : String(row?.name || "");
  form.provider_type = String(row?.provider_type || "openai-compatible");
  form.base_url = String(row?.base_url || "");
  form.api_key = String(row?.api_key || "");
  const modelConfigs = normalizeProviderModelConfigs(
    row,
    modelTypeOptions.value,
  );
  form.model_configs = modelConfigs.length
    ? modelConfigs.map((item) => createModelConfig(item.name, item.model_type))
    : [createModelConfig()];
  form.default_model = String(row?.default_model || "");
  form.enabled = row?.enabled !== false;
  const headers =
    row?.extra_headers && typeof row.extra_headers === "object"
      ? row.extra_headers
      : {};
  form.extra_headers_text = Object.keys(headers).length
    ? JSON.stringify(headers, null, 2)
    : "";
  form.shared_usernames = Array.isArray(row?.shared_usernames)
    ? row.shared_usernames
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  appliedPresetKey.value = matchPresetKey({
    name: form.name,
    provider_type: form.provider_type,
    base_url: form.base_url,
  });
  syncDefaultModelSelection();
}

function matchPresetKey(row) {
  const normalizedBaseUrl = String(row?.base_url || "")
    .trim()
    .replace(/\/+$/, "");
  const normalizedType = String(row?.provider_type || "").trim();
  return (
    PROVIDER_PRESETS.find(
      (item) =>
        item.provider_type === normalizedType &&
        item.base_url === normalizedBaseUrl,
    )?.key || ""
  );
}

function applyProviderPreset(preset) {
  if (!preset || typeof preset !== "object") return;
  form.name = String(preset.name || "");
  form.provider_type = String(preset.provider_type || "openai-compatible");
  form.base_url = String(preset.base_url || "");
  form.model_configs =
    Array.isArray(preset.model_configs) && preset.model_configs.length
      ? preset.model_configs.map((item) =>
          createModelConfig(item.name, item.model_type),
        )
      : [createModelConfig()];
  form.default_model = String(
    preset.default_model || preset.model_configs?.[0]?.name || "",
  );
  form.extra_headers_text = preset.extra_headers
    ? JSON.stringify(preset.extra_headers, null, 2)
    : "";
  appliedPresetKey.value = String(preset.key || "");
  syncDefaultModelSelection();
}

function openCreate() {
  createDialogVisible.value = true;
}

function openEdit(row) {
  dialogMode.value = "edit";
  editingId.value = String(row.id || "");
  populateForm(row);
  showDialog.value = true;
}

function openDuplicate(row) {
  dialogMode.value = "duplicate";
  editingId.value = "";
  populateForm(row, { duplicate: true });
  showDialog.value = true;
}

function dialogTitle() {
  if (dialogMode.value === "edit") return "编辑模型供应商";
  if (dialogMode.value === "duplicate") return "复制模型供应商";
  return "新增模型供应商";
}

function apiKeyPlaceholder() {
  if (dialogMode.value === "edit") return "编辑时留空表示不修改";
  if (dialogMode.value === "duplicate")
    return "出于安全原因不会复制 API Key，请按需填写";
  return "例如：sk-...";
}

function addModelConfig() {
  form.model_configs.push(createModelConfig());
}

function mergeDiscoveredModelNames(modelNames) {
  const latestNames = Array.from(
    new Set(
      (Array.isArray(modelNames) ? modelNames : [])
        .map((item) =>
          typeof item === "object"
            ? item?.id || item?.name || item?.model
            : item,
        )
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  );
  if (!latestNames.length) return 0;
  const existingByName = new Map(
    form.model_configs
      .map((item) => [String(item?.name || "").trim(), item])
      .filter(([name]) => name),
  );
  const previousNames = new Set(existingByName.keys());
  form.model_configs = latestNames.map(
    (name) => existingByName.get(name) || createModelConfig(name),
  );
  syncDefaultModelSelection();
  return latestNames.filter((name) => !previousNames.has(name)).length;
}

function removeModelConfig(index) {
  form.model_configs.splice(index, 1);
  if (!form.model_configs.length) {
    form.model_configs.push(createModelConfig());
  }
  syncDefaultModelSelection();
}

function markDefaultModel(item) {
  const modelName = String(item?.name || "").trim();
  if (!modelName) {
    ElMessage.warning("请先填写模型名称");
    return;
  }
  form.default_model = modelName;
}

function syncDefaultModelSelection() {
  const values = normalizedFormModelConfigs.value;
  if (values.some((item) => item.name === form.default_model)) return;
  form.default_model = values[0]?.name || "";
}

function formatModelTypeLabel(modelType) {
  const meta = modelTypeMetaMap.value.get(String(modelType || "").trim());
  return meta?.label || "文本生成";
}

function getModelTypeDescription(modelType) {
  const meta = modelTypeMetaMap.value.get(String(modelType || "").trim());
  return meta?.description || "选择该模型在系统中的能力分类。";
}

function formatProviderModels(row) {
  const values = normalizeProviderModelConfigs(row, modelTypeOptions.value);
  if (!values.length) return "-";
  return values
    .map((item) => `${item.name} [${formatModelTypeLabel(item.model_type)}]`)
    .join(", ");
}

function parseHeaders() {
  const raw = String(form.extra_headers_text || "").trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
    throw new Error("invalid");
  } catch {
    throw new Error("额外请求头必须是 JSON 对象");
  }
}

function formatProviderDiscoveryError(error) {
  if (typeof error === "string") return error.trim() || "获取模型失败";
  const directMessage = String(
    error?.detail || error?.message || error?.error || "",
  ).trim();
  if (directMessage) return directMessage;
  try {
    const serialized = JSON.stringify(error);
    if (serialized && serialized !== "{}") return serialized;
  } catch {}
  return "获取模型失败：桌面端没有返回可识别的错误信息";
}

async function discoverModels() {
  if (!form.base_url.trim()) {
    ElMessage.warning("请先填写 Base URL");
    return;
  }

  let extraHeaders = {};
  try {
    extraHeaders = parseHeaders();
  } catch (e) {
    ElMessage.error(e.message || "额外请求头格式错误");
    return;
  }

  discoveringModels.value = true;
  try {
    if (!hasNativeDesktopBridge()) {
      throw new Error("当前环境不支持本地模型发现，请在桌面应用中操作");
    }
    const data = await discoverNativeProviderModels({
      providerType: form.provider_type,
      baseUrl: form.base_url,
      apiKey: form.api_key,
      extraHeaders,
    });
    if (!data || typeof data !== "object") {
      throw new Error(
        "桌面端模型发现命令没有返回结果，请完全退出并重新启动桌面端后重试",
      );
    }
    const models = Array.isArray(data?.models)
      ? data.models
      : Array.isArray(data?.data)
        ? data.data
        : [];
    if (!models.length) {
      throw new Error(
        "供应商返回成功，但没有可用模型；请检查 API Key 和接口地址",
      );
    }
    const added = mergeDiscoveredModelNames(models);
    ElMessage.success(
      `已获取 ${models.length} 个最新模型${added ? `，新增 ${added} 个` : "，已更新当前模型列表"}，请点击保存`,
    );
  } catch (e) {
    const message = formatProviderDiscoveryError(e);
    console.error("discover provider models failed", e);
    ElMessage({
      type: "error",
      message,
      duration: 12000,
      showClose: true,
    });
  } finally {
    discoveringModels.value = false;
  }
}

async function fetchProviders() {
  loading.value = true;
  try {
    migrateLegacyLocalProviders();
    const localProviders = readLocalProviders();
    localProviders
      .filter((provider) => isServerBuiltinModelProvider(provider))
      .forEach((provider) => {
        const providerId = String(provider?.id || "").trim();
        if (!providerId) return;
        removeLocalEntity(LOCAL_PROVIDER_ENTITY, providerId);
        rememberDeletedProviderId(providerId);
      });
    const nonBuiltinLocalProviders = localProviders.filter(
      (provider) => !isServerBuiltinModelProvider(provider),
    );
    const [builtinProviders] = await Promise.all([
      fetchBuiltinModelProviders().catch((error) => {
        console.warn("load server builtin model providers failed", error);
        return [];
      }),
    ]);
    providers.value = mergeBuiltinModelProviders(
      nonBuiltinLocalProviders,
      builtinProviders,
    );
  } catch (error) {
    console.error("load local model providers failed", error);
    providers.value = [];
  } finally {
    loading.value = false;
  }
}

async function fetchShareUserOptions() {
  shareUserOptions.value = [];
}

async function fetchModelTypeOptions() {
  modelTypeOptions.value = FALLBACK_MODEL_TYPE_OPTIONS;
}

async function submitForm() {
  if (!form.name.trim() || !form.base_url.trim()) {
    ElMessage.warning("请填写供应商名称和 Base URL");
    return;
  }

  let extraHeaders = {};
  try {
    extraHeaders = parseHeaders();
  } catch (e) {
    ElMessage.error(e.message || "额外请求头格式错误");
    return;
  }

  const modelConfigs = normalizedFormModelConfigs.value;
  if (!modelConfigs.length) {
    ElMessage.warning("请至少添加一个模型");
    return;
  }
  const preferredDefaultModel = String(form.default_model || "").trim();
  const defaultModel = modelConfigs.some(
    (item) => item.name === preferredDefaultModel,
  )
    ? preferredDefaultModel
    : modelConfigs[0].name;
  form.default_model = defaultModel;

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
      ? form.shared_usernames
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      : [],
  };

  if (!editingId.value || form.api_key.trim()) {
    payload.api_key = form.api_key.trim();
  }

  saving.value = true;
  try {
    const existing = (providers.value || []).find(
      (item) => String(item?.id || "").trim() === editingId.value,
    );
    const now = new Date().toISOString();
    const providerId = editingId.value || createLocalProviderId();
    const nextProvider = {
      ...(existing || {}),
      ...payload,
      id: providerId,
      created_at: String(existing?.created_at || now),
      updated_at: now,
    };
    delete nextProvider.models;
    delete nextProvider.api_key_masked;
    const savedProviders = writeLocalEntities(
      LOCAL_PROVIDER_ENTITY,
      readLocalEntities(LOCAL_PROVIDER_ENTITY)
        .filter((item) => String(item?.id || "").trim() !== providerId)
        .concat(nextProvider),
    );
    const savedProvider = savedProviders.find(
      (item) => String(item?.id || "").trim() === providerId,
    );
    const savedModelNames = normalizeProviderModelConfigs(
      savedProvider,
      modelTypeOptions.value,
    ).map((item) => item.name);
    const expectedModelNames = modelConfigs.map((item) => item.name);
    if (
      savedModelNames.length !== expectedModelNames.length ||
      savedModelNames.some((name, index) => name !== expectedModelNames[index])
    ) {
      throw new Error("模型配置写入失败，请重试");
    }
    ElMessage.success(
      editingId.value
        ? "本地供应商已更新"
        : dialogMode.value === "duplicate"
          ? "本地供应商已复制创建"
          : "本地供应商已创建",
    );
    showDialog.value = false;
    await fetchProviders();
  } catch (e) {
    ElMessage.error(e.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

function buildPresetPayload(preset) {
  const modelConfigs = Array.isArray(preset?.model_configs)
    ? preset.model_configs
    : [];
  return {
    name: String(preset?.name || "").trim(),
    provider_type: String(preset?.provider_type || "openai-compatible").trim(),
    base_url: String(preset?.base_url || "").trim(),
    model_configs: modelConfigs.map((item) => ({
      name: String(item?.name || "").trim(),
      model_type: String(
        item?.model_type || modelTypeOptions.value[0]?.id || "text_generation",
      ).trim(),
    })),
    default_model: String(
      preset?.default_model || modelConfigs[0]?.name || "",
    ).trim(),
    enabled: false,
    extra_headers:
      preset?.extra_headers && typeof preset.extra_headers === "object"
        ? preset.extra_headers
        : {},
    shared_usernames: [],
    api_key: "",
  };
}

async function importMainstreamPresets() {
  try {
    await ElMessageBox.confirm(
      "将批量创建主流供应商模板，默认处于禁用状态。导入后请补充 API Key、按需调整模型并手动启用。",
      "导入主流模板",
      { type: "info" },
    );
  } catch {
    return;
  }

  importingPresets.value = true;
  try {
    const existingKeys = new Set(
      (Array.isArray(providers.value) ? providers.value : []).map(
        (item) =>
          `${String(item?.name || "").trim()}@@${String(item?.base_url || "")
            .trim()
            .replace(/\/+$/, "")}`,
      ),
    );
    let createdCount = 0;
    let skippedCount = 0;
    for (const preset of PROVIDER_PRESETS) {
      const dedupeKey = `${preset.name}@@${preset.base_url}`;
      if (existingKeys.has(dedupeKey)) {
        skippedCount += 1;
        continue;
      }
      const now = new Date().toISOString();
      upsertLocalEntity(LOCAL_PROVIDER_ENTITY, {
        ...buildPresetPayload(preset),
        id: createLocalProviderId(),
        created_at: now,
        updated_at: now,
      });
      existingKeys.add(dedupeKey);
      createdCount += 1;
    }
    await fetchProviders();
    if (!createdCount) {
      ElMessage.info(`主流模板已存在，已跳过 ${skippedCount} 条`);
      return;
    }
    ElMessage.success(
      `已导入 ${createdCount} 条主流模板${skippedCount ? `，跳过 ${skippedCount} 条重复项` : ""}`,
    );
  } catch (e) {
    ElMessage.error(e?.detail || "导入主流模板失败");
  } finally {
    importingPresets.value = false;
  }
}

function formatSharedUsers(usernames) {
  const values = Array.isArray(usernames)
    ? usernames.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  return values.join(", ") || "-";
}

function maskApiKey(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return "";
  if (normalized.length <= 8) return "••••••••";
  return `${normalized.slice(0, 4)}••••${normalized.slice(-4)}`;
}

function getProviderActions(row) {
  if (row?.is_builtin_provider) {
    return [{ key: "test", label: "测试连接", type: "success" }];
  }
  return [
    { key: "test", label: "测试连接", type: "success" },
    { key: "duplicate", label: "复制", type: "warning" },
    { key: "edit", label: "编辑", type: "primary" },
    { key: "delete", label: "删除", type: "danger" },
  ];
}

function getPrimaryProviderActions(row) {
  return getProviderActions(row).slice(0, 3);
}

function getOverflowProviderActions(row) {
  return getProviderActions(row).slice(3);
}

function handleProviderAction(row, actionKey) {
  switch (actionKey) {
    case "test":
      if (row?.is_builtin_provider) {
        void testBuiltinConnection(row);
        break;
      }
      void testConnection(row, getPrimaryTestModel(row));
      break;
    case "duplicate":
      openDuplicate(row);
      break;
    case "edit":
      openEdit(row);
      break;
    case "delete":
      void removeProvider(row);
      break;
    default:
      break;
  }
}

async function testBuiltinConnection(row) {
  const providerId = String(row?.source_provider_id || "").trim();
  if (!providerId) return;
  testingProviderId.value = String(row?.id || providerId);
  try {
    const result = await testBuiltinModelProvider(providerId);
    const normalizedResult = {
      reachable: result?.reachable === true,
      model_tested: result?.model_tested || row?.default_model || "",
      latency_ms: result?.latency_ms || "",
      message: result?.message || "连接测试完成",
      tested_at: new Date().toISOString(),
    };
    storeConnectionResult(String(row?.id || providerId), normalizedResult);
    if (normalizedResult.reachable) ElMessage.success("内置供应商连接测试成功");
    else showConnectionTestFailure(normalizedResult, normalizedResult.message);
  } catch (error) {
    const failedResult = {
      reachable: false,
      message: error?.message || "内置供应商连接测试失败",
      tested_at: new Date().toISOString(),
    };
    storeConnectionResult(String(row?.id || providerId), failedResult);
    showConnectionTestFailure(failedResult, failedResult.message);
  } finally {
    testingProviderId.value = "";
  }
}

async function removeProvider(row) {
  const id = String(row.id || "");
  if (!id) return;
  try {
    await ElMessageBox.confirm(
      `确定删除供应商 ${row.name || id}？`,
      "删除确认",
      {
        type: "warning",
      },
    );
    const remainingProviders = removeLocalEntity(LOCAL_PROVIDER_ENTITY, id);
    if (remainingProviders.some((item) => String(item?.id || "") === id)) {
      throw new Error("供应商删除未完成，请刷新后重试");
    }
    delete connectionResultByProvider[id];
    delete connectionResultsByProvider[id];
    rememberDeletedProviderId(id);
    ElMessage.success("本地供应商已删除");
    await fetchProviders();
  } catch (e) {
    if (e === "cancel" || e?.action === "cancel" || e?.action === "close") {
      return;
    }
    ElMessage.error(e?.detail || e?.message || "删除失败");
  }
}

function getConnectionMeta(providerId, key) {
  const state = connectionResultByProvider[String(providerId || "")];
  if (!state || typeof state !== "object") return "";
  return state[key] || "";
}

function storeConnectionResult(providerId, result, fallbackModelName = "") {
  const normalizedProviderId = String(providerId || "").trim();
  if (!normalizedProviderId || !result || typeof result !== "object") return;
  const normalizedModelName =
    String(result.model_tested || fallbackModelName || "default").trim() ||
    "default";
  connectionResultByProvider[normalizedProviderId] = result;
  if (!connectionResultsByProvider[normalizedProviderId]) {
    connectionResultsByProvider[normalizedProviderId] = {};
  }
  connectionResultsByProvider[normalizedProviderId][normalizedModelName] =
    result;
}

function getConnectionResults(providerId) {
  const states = connectionResultsByProvider[String(providerId || "")];
  if (!states || typeof states !== "object") return [];
  return Object.values(states).sort((left, right) => {
    const leftTime = parseDateTime(left?.tested_at)?.getTime?.() || 0;
    const rightTime = parseDateTime(right?.tested_at)?.getTime?.() || 0;
    return rightTime - leftTime;
  });
}

function formatConnectionRequestAddresses(providerId) {
  const state = connectionResultByProvider[String(providerId || "")];
  if (!state || typeof state !== "object") return "";
  const urls = Array.isArray(state.request_urls)
    ? state.request_urls
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  const fallbackUrls = [
    String(state.models_url || "").trim(),
    String(state.completion_url || "").trim(),
  ].filter(Boolean);
  return (urls.length ? urls : fallbackUrls).join("；");
}

function connectionTagType(providerId) {
  const state = connectionResultByProvider[String(providerId || "")];
  if (!state) return "info";
  return state.reachable ? "success" : "danger";
}

function connectionTagText(providerId) {
  const state = connectionResultByProvider[String(providerId || "")];
  if (!state) return "未测试";
  return state.reachable ? "已连通" : "连接失败";
}

function normalizeProviderModels(row) {
  return normalizeProviderModelNames(row, modelTypeOptions.value);
}

function getPrimaryTestModel(row) {
  const models = normalizeProviderModels(row);
  const defaultModel = String(row?.default_model || "").trim();
  return models.includes(defaultModel) ? defaultModel : models[0] || "";
}

function getProviderTestActions(row) {
  const models = normalizeProviderModels(row);
  if (!models.length) {
    return [{ modelName: "", label: "按默认配置测试", primary: true }];
  }
  const defaultModel = String(row?.default_model || "").trim();
  return models.map((modelName, index) => ({
    modelName,
    label:
      index === 0 && defaultModel === modelName
        ? `默认模型 · ${modelName}`
        : modelName,
    primary: index === 0,
  }));
}

function getProviderTestModelType(row, modelName = "") {
  const normalizedModelName = String(
    modelName || row?.default_model || "",
  ).trim();
  const configs = normalizeProviderModelConfigs(row, modelTypeOptions.value);
  return String(
    configs.find(
      (item) => String(item?.name || "").trim() === normalizedModelName,
    )?.model_type || "text_generation",
  ).trim();
}

async function confirmBillableCapabilityTest(row, modelName = "") {
  const modelType = getProviderTestModelType(row, modelName);
  if (
    !["image_generation", "video_generation", "audio_generation"].includes(
      modelType,
    )
  )
    return true;
  const modelLabel = String(
    modelName || row?.default_model || "默认模型",
  ).trim();
  try {
    await ElMessageBox.confirm(
      `将调用 ${modelLabel} 执行真实${formatModelTypeLabel(modelType)}测试，可能产生供应商费用。是否继续？`,
      "确认真实能力测试",
      {
        type: "warning",
        confirmButtonText: "继续测试",
        cancelButtonText: "取消",
      },
    );
    return true;
  } catch {
    return false;
  }
}

function isTestingAction(providerId, modelName = "") {
  return (
    testingProviderId.value === String(providerId || "") &&
    testingModelName.value === String(modelName || "").trim()
  );
}

function buildConnectionFailureMessage(result, fallbackMessage = "") {
  const message = String(
    result?.message || fallbackMessage || "模型接口连接测试失败",
  ).trim();
  const addresses = Array.isArray(result?.request_urls)
    ? result.request_urls
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [
        String(result?.models_url || "").trim(),
        String(result?.completion_url || "").trim(),
      ].filter(Boolean);
  const modelName = String(result?.model_tested || "").trim();
  return h("div", { class: "connection-failure-detail" }, [
    h("p", message),
    modelName
      ? h("p", `测试模型：${modelName}`)
      : h("p", "测试模型：未解析到可用模型"),
    addresses.length
      ? h("div", [
          h("p", "请求地址："),
          h(
            "ul",
            addresses.map((item) => h("li", item)),
          ),
        ])
      : h("p", "请求地址：-"),
  ]);
}

function showConnectionTestFailure(result, fallbackMessage = "") {
  void ElMessageBox.alert(
    buildConnectionFailureMessage(result, fallbackMessage),
    "模型接口连接测试失败",
    {
      type: "error",
      confirmButtonText: "关闭",
    },
  );
}

async function testConnection(row, modelName = "") {
  const providerId = String(row?.id || "").trim();
  if (!providerId) return;
  const normalizedModelName = String(modelName || "").trim();
  if (!(await confirmBillableCapabilityTest(row, normalizedModelName))) return;
  testingProviderId.value = providerId;
  testingModelName.value = normalizedModelName;
  try {
    if (!hasNativeDesktopBridge()) {
      throw new Error("当前环境不支持本地供应商测试，请在桌面应用中操作");
    }
    const result = await testNativeProviderModel({
      providerType: row?.provider_type,
      baseUrl: row?.base_url,
      apiKey: row?.api_key,
      modelName: normalizedModelName || getPrimaryTestModel(row),
      modelType: getProviderTestModelType(row, normalizedModelName),
      extraHeaders: row?.extra_headers || {},
    });
    const normalizedResult = {
      ...result,
      model_type:
        result?.modelType || getProviderTestModelType(row, normalizedModelName),
      request_urls: result?.requestUrl ? [result.requestUrl] : [],
      message: result?.httpStatus
        ? `${result.message || "模型接口连接测试失败"}（HTTP ${result.httpStatus}）`
        : result?.message,
      tested_at: new Date().toISOString(),
    };
    storeConnectionResult(providerId, normalizedResult, normalizedModelName);
    if (normalizedResult.reachable) {
      ElMessage.success("模型真实能力测试成功，结果已展示");
    } else {
      showConnectionTestFailure(normalizedResult, normalizedResult.message);
    }
  } catch (e) {
    const failedResult = {
      reachable: false,
      model_tested: normalizedModelName,
      request_urls: e.requestUrl ? [e.requestUrl] : [],
      message: e.detail || e.message || "连接失败",
      tested_at: new Date().toISOString(),
    };
    storeConnectionResult(providerId, failedResult, normalizedModelName);
    showConnectionTestFailure(
      failedResult,
      e.detail || e.message || "模型接口连接测试失败",
    );
  } finally {
    testingProviderId.value = "";
    testingModelName.value = "";
  }
}

onMounted(async () => {
  await hydrateLocalProjectRepository();
  await Promise.all([
    fetchProviders(),
    fetchShareUserOptions(),
    fetchModelTypeOptions(),
  ]);
  await nextTick();
  syncProviderTableVisibleWidth();
  const tableElement = providerTableRef.value?.$el;
  if (tableElement instanceof HTMLElement) {
    providerTableResizeObserver = new ResizeObserver(
      syncProviderTableVisibleWidth,
    );
    providerTableResizeObserver.observe(tableElement);
  }
});

onBeforeUnmount(() => {
  providerTableResizeObserver?.disconnect();
});
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

.responsive-provider-table :deep(.el-table__expanded-cell) {
  position: relative;
}

.provider-expanded-content {
  position: sticky;
  left: 50px;
  box-sizing: border-box;
  width: max(0px, calc(var(--provider-table-visible-width, 100vw) - 100px));
  max-width: max(0px, calc(var(--provider-table-visible-width, 100vw) - 100px));
}

.expand-actions__hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.expand-actions {
  display: grid;
  gap: 8px;
  min-width: 0;
  width: 100%;
}

.expand-actions__copy {
  display: grid;
  gap: 2px;
  min-width: 0;
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
  min-width: 0;
  width: 100%;
}

.expand-actions__buttons :deep(.el-button) {
  max-width: 100%;
  margin-left: 0;
}

.expand-actions__buttons :deep(.el-button > span) {
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: normal;
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

.provider-standard-note {
  border-left: 3px solid #2563eb;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(37, 99, 235, 0.07);
  color: #334155;
  font-size: 12px;
  line-height: 1.6;
}

.provider-interface-panel {
  display: grid;
  gap: 10px;
  width: 100%;
}

.provider-interface-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.provider-interface-help {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.32);
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.86);
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.provider-interface-help__head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.provider-interface-help strong {
  color: #0f172a;
  font-size: 13px;
}

.provider-interface-help__warning {
  color: #b45309;
}

.api-key-help {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.model-config-header {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(160px, 220px) auto auto;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
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

.model-config-row__type-cell {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.model-config-row__type-help {
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-type-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.model-type-option span:last-child {
  color: var(--el-text-color-secondary);
  font-size: 12px;
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

  .model-config-header {
    display: none;
  }
}

@media (max-width: 640px) {
  .filter-panel__grid {
    grid-template-columns: 1fr;
  }

  .responsive-provider-table :deep(.el-table__expanded-cell) {
    padding-right: 16px;
    padding-left: 16px;
  }

  .provider-expanded-content {
    left: 16px;
    width: max(0px, calc(var(--provider-table-visible-width, 100vw) - 32px));
    max-width: max(
      0px,
      calc(var(--provider-table-visible-width, 100vw) - 32px)
    );
  }
}
</style>
