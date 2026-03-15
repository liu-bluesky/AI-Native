<template>
  <div v-loading="loading">
    <div class="toolbar">
      <div>
        <h3>行业智能体模板</h3>
        <div class="toolbar-subtitle">
          先导入外部 Agent 模板沉淀为模板库，再从模板创建员工。
        </div>
      </div>
      <div class="toolbar-actions">
        <el-input
          v-model="searchKeyword"
          class="template-search-input"
          clearable
          placeholder="搜索原名 / 中文名 / 来源 / 描述"
        />
        <div v-if="selectedTemplateIds.length" class="template-selection-summary">
          已选 {{ selectedTemplateIds.length }} 个
          <el-button link type="primary" @click="clearTemplateSelection">
            清空
          </el-button>
        </div>
        <el-button
          v-if="selectedTemplateIds.length"
          plain
          type="danger"
          :loading="batchDeletingTemplates"
          @click="batchDeleteTemplates"
        >
          批量删除
        </el-button>
        <el-button plain @click="goToEmployees">员工列表</el-button>
        <el-button
          plain
          :loading="translatingTemplateNames"
          :disabled="!templates.length"
          @click="fillMissingTemplateNames"
        >
          补全中文名
        </el-button>
        <el-button
          plain
          :loading="translatingTemplateNames"
          :disabled="!templates.length"
          @click="retranslateTemplateNames"
        >
          重译中文名
        </el-button>
        <el-button
          plain
          :loading="deduplicatingTemplates"
          :disabled="templates.length < 2"
          @click="runAiTemplateDeduplication"
        >
          同类去重
        </el-button>
        <el-button type="primary" @click="openImportDialog">导入模板</el-button>
      </div>
    </div>

    <el-alert
      class="usage-alert"
      type="info"
      :closable="false"
      show-icon
      title="模板库保存的是行业智能体/角色模板，不直接等同于平台里的员工实例。"
    />

    <el-table
      ref="templateTableRef"
      :data="filteredTemplates"
      row-key="id"
      stripe
      class="template-table"
      @selection-change="handleTemplateSelectionChange"
    >
      <el-table-column type="selection" width="52" reserve-selection />
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column label="中文名" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.name_zh || row.name || "-" }}
        </template>
      </el-table-column>
      <el-table-column label="来源" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.relative_path || row.source_name || "-" }}
        </template>
      </el-table-column>
      <el-table-column label="规则领域" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ (row.rule_domains || []).join(" / ") || "-" }}
        </template>
      </el-table-column>
      <el-table-column label="风格提示" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          {{ (row.style_hints || []).join(" / ") || "-" }}
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="220" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="openTemplateDetail(row)"
            >详情</el-button
          >
          <el-button text type="primary" @click="createEmployeeFromTemplate(row)"
            >创建员工</el-button
          >
          <el-button text type="danger" @click="deleteTemplate(row)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <el-empty
      v-if="!filteredTemplates.length && !loading"
      :description="templates.length ? '没有匹配的模板' : '暂无模板'"
    />

    <el-dialog
      v-model="showImportDialog"
      class="template-import-dialog"
      modal-class="template-import-overlay"
      fullscreen
      append-to-body
      :show-close="false"
      :z-index="4000"
      destroy-on-close
      @closed="resetImportDialog"
    >
      <div class="template-import-shell">
        <div class="template-import-hero">
          <div class="template-import-hero__copy">
            <div class="template-import-hero__eyebrow">Template Library</div>
            <div class="template-import-hero__title">导入行业智能体模板</div>
            <div class="template-import-hero__text">
              从 Git 仓库或本地目录读取 Markdown agent 文件，保存为可复用的模板库。
            </div>
          </div>
          <div class="template-import-hero__actions">
            <div class="template-import-hero__status">
              {{ importStatusText }}
            </div>
            <el-button @click="showImportDialog = false">关闭</el-button>
            <el-button
              type="primary"
              :disabled="!selectedImportedDraftEntries.length"
              :loading="savingTemplates"
              @click="saveSelectedTemplates"
            >
              保存到模板库（{{ selectedImportedTemplateCount }}）
            </el-button>
          </div>
        </div>

        <div class="template-import-layout">
          <div class="template-import-source">
            <div class="template-import-section__head">
              <div class="template-import-section__title">模板来源</div>
              <div class="template-import-section__hint">
                支持 Git 仓库 URL、本地目录，也支持 GitHub 的 `tree/...` 子目录链接。
              </div>
            </div>
            <el-form label-position="top" class="template-import-form">
              <el-form-item label="来源类型">
                <el-radio-group v-model="importForm.source_type">
                  <el-radio-button label="git">Git 仓库</el-radio-button>
                  <el-radio-button label="local">本地目录</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item
                :label="importForm.source_type === 'git' ? '仓库地址' : '目录路径'"
              >
                <el-input
                  v-model="importForm.source"
                  :placeholder="
                    importForm.source_type === 'git'
                      ? '例如：https://github.com/msitarzewski/agency-agents/tree/main/engineering'
                      : '例如：./agents 或 /abs/path/to/templates'
                  "
                />
              </el-form-item>
              <div class="template-import-source__row">
                <el-form-item label="子目录">
                  <el-input
                    v-model="importForm.subdirectory"
                    placeholder="可选，例如：engineering"
                  />
                </el-form-item>
                <el-form-item
                  v-if="importForm.source_type === 'git'"
                  label="分支"
                >
                  <el-input v-model="importForm.branch" placeholder="可选" />
                </el-form-item>
                <el-form-item v-else label="读取上限">
                  <el-input-number v-model="importForm.limit" :min="1" :max="80" />
                </el-form-item>
              </div>
              <el-form-item
                v-if="importForm.source_type === 'git'"
                label="读取上限"
              >
                <el-input-number v-model="importForm.limit" :min="1" :max="80" />
              </el-form-item>
            </el-form>
            <div class="template-import-source__actions">
              <el-button
                type="primary"
                :loading="importLoading"
                @click="loadTemplateCandidates"
                >读取模板</el-button
              >
              <span class="template-import-source__status">
                读取后在右侧勾选要保存到模板库的项。
              </span>
            </div>
          </div>

          <div class="template-import-main">
            <div class="template-import-candidates">
              <div class="template-import-section__head">
                <div class="template-import-section__title">模板列表</div>
                <div class="template-import-section__hint">
                  共 {{ importedTemplates.length }} 个候选模板。勾选后会进入右侧待保存区。
                </div>
              </div>
              <div
                v-if="importedTemplates.length"
                class="template-import-candidates__toolbar"
              >
                <div class="template-import-candidates__selection">
                  待保存 {{ selectedImportedTemplateCount }} 个
                </div>
                <div class="template-import-candidates__actions">
                  <el-button link type="primary" @click="selectAllImportedTemplates"
                    >全选</el-button
                  >
                  <el-button link @click="clearImportedTemplateSelection"
                    >清空</el-button
                  >
                </div>
              </div>
              <div v-loading="importLoading" class="template-import-candidates__list">
                <el-empty
                  v-if="!importedTemplates.length"
                  description="尚未读取到模板"
                  :image-size="56"
                />
                <div
                  v-for="item in importedTemplates"
                  :key="item.id"
                  class="template-candidate-card"
                  :class="{
                    'is-active': selectedImportedTemplateId === item.id,
                    'is-selected': isImportedTemplateSelected(item.id),
                  }"
                  @click="selectedImportedTemplateId = item.id"
                >
                  <div class="template-candidate-card__select" @click.stop>
                    <el-checkbox
                      :model-value="isImportedTemplateSelected(item.id)"
                      @change="(checked) => setImportedTemplateSelection(item.id, checked)"
                    />
                  </div>
                  <div class="template-candidate-card__body">
                    <div class="template-candidate-card__head">
                      <span class="template-candidate-card__name">{{ item.name }}</span>
                      <span class="template-candidate-card__path">{{
                        item.relative_path
                      }}</span>
                    </div>
                    <div class="template-candidate-card__desc">
                      {{ item.description || "暂无描述" }}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="template-import-preview">
              <div class="template-import-section__head">
                <div class="template-import-section__title">待保存模板</div>
                <div class="template-import-section__hint">
                  先确认保存范围，再点击详情查看模板原文。
                </div>
              </div>

              <div
                v-if="selectedImportedDraftEntries.length"
                class="template-import-preview__body"
              >
                <div class="template-import-preview__selected">
                  <div class="template-import-preview__selected-head">
                    <div class="template-import-preview__selected-title">
                      已勾选 {{ selectedImportedTemplateCount }} 个模板
                    </div>
                    <div class="template-import-preview__selected-hint">
                      点击“详情”查看模板内容。
                    </div>
                  </div>
                  <div class="template-import-preview__selected-list">
                    <div
                      v-for="entry in selectedImportedDraftEntries"
                      :key="entry.id"
                      class="template-import-preview__selected-card"
                      :class="{ 'is-active': selectedImportedPreviewId === entry.id }"
                    >
                      <div class="template-import-preview__selected-main">
                        <div class="template-import-preview__selected-name">
                          {{ entry.draft.name || entry.name || "未命名模板" }}
                        </div>
                        <div class="template-import-preview__selected-meta">
                          <span>{{ entry.draft.template_relative_path || "-" }}</span>
                          <span>{{ entry.draft.template_source_name || "-" }}</span>
                        </div>
                      </div>
                      <div class="template-import-preview__selected-actions">
                        <el-button
                          link
                          type="primary"
                          @click="showImportedTemplateDetail(entry.id)"
                          >详情</el-button
                        >
                        <el-button
                          link
                          @click="setImportedTemplateSelection(entry.id, false)"
                          >移除</el-button
                        >
                      </div>
                    </div>
                  </div>
                </div>

                <div
                  v-if="selectedImportedDraft"
                  class="template-import-preview__detail"
                >
                  <div class="template-import-preview__summary">
                    <div class="template-import-preview__summary-main">
                      <div class="template-import-preview__title">
                        {{ selectedImportedDraft.name || "未命名模板" }}
                      </div>
                      <div class="template-import-preview__meta">
                        <span>来源：{{ selectedImportedDraft.template_source_name || "-" }}</span>
                        <span>路径：{{ selectedImportedDraft.template_relative_path || "-" }}</span>
                      </div>
                    </div>
                  </div>
                  <pre class="template-import-preview__content">{{
                    selectedImportedContent || "模板内容为空"
                  }}</pre>
                </div>
              </div>
              <div v-else class="template-import-preview__empty-state">
                <div class="template-import-preview__empty-title">等待勾选模板</div>
                <div class="template-import-preview__empty-text">
                  先读取模板，再勾选要保存到模板库的项。
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <el-drawer
      v-model="showDetailDrawer"
      title="模板详情"
      size="min(720px, 92vw)"
    >
      <div v-if="activeTemplate" class="detail">
        <div class="detail-title">{{ activeTemplate.name || "未命名模板" }}</div>
        <div class="detail-meta">
          <span>中文名：{{ activeTemplate.name_zh || activeTemplate.name || "-" }}</span>
          <span>来源：{{ activeTemplate.source_name || "-" }}</span>
          <span>路径：{{ activeTemplate.relative_path || "-" }}</span>
        </div>
        <div class="detail-section">
          <div class="detail-section__label">模板内容</div>
          <pre class="detail-policy">{{ activeTemplate.content || "模板内容为空" }}</pre>
        </div>
      </div>

      <template #footer>
        <div class="detail-footer">
          <el-button @click="showDetailDrawer = false">关闭</el-button>
          <el-button
            v-if="activeTemplate"
            type="primary"
            :loading="creatingEmployee"
            @click="createEmployeeFromTemplate(activeTemplate)"
          >
            从模板创建员工
          </el-button>
        </div>
      </template>
    </el-drawer>

    <ModelProviderPickerDialog
      :model-value="showModelPickerDialog"
      :title="modelPickerDialogTitle"
      :description="modelPickerDialogDescription"
      :confirm-text="modelPickerDialogConfirmText"
      :internal-providers="internalAiProviders"
      :external-connectors="externalAiConnectors"
      :loading="aiSourcesLoading"
      :source-type="selectedAiSourceType"
      :provider-id="selectedTranslationProviderId"
      :model-name="selectedTranslationModelName"
      :local-connector-id="selectedExternalConnectorId"
      :external-agent-type="selectedExternalAgentType"
      @update:model-value="handleModelPickerDialogVisibilityChange"
      @update:source-type="selectedAiSourceType = $event"
      @update:provider-id="selectedTranslationProviderId = $event"
      @update:model-name="selectedTranslationModelName = $event"
      @update:local-connector-id="selectedExternalConnectorId = $event"
      @update:external-agent-type="selectedExternalAgentType = $event"
      @confirm="handleModelPickerConfirm"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import api from "@/utils/api.js";
import ModelProviderPickerDialog from "@/components/ModelProviderPickerDialog.vue";
import { resolveSettingsAwarePanelPath } from "@/utils/chat-settings-route.js";

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const templates = ref([]);
const searchKeyword = ref("");
const selectedTemplateIds = ref([]);
const templateTableRef = ref(null);
const internalAiProviders = ref([]);
const externalAiConnectors = ref([]);
const aiSourcesLoading = ref(false);
const selectedAiSourceType = ref("internal");
const selectedTranslationProviderId = ref("");
const selectedTranslationModelName = ref("");
const selectedExternalConnectorId = ref("");
const selectedExternalAgentType = ref("codex_cli");
const showModelPickerDialog = ref(false);
const pendingModelAction = ref(null);
const activeTemplate = ref(null);
const showDetailDrawer = ref(false);
const creatingEmployee = ref(false);
const deduplicatingTemplates = ref(false);
const translatingTemplateNames = ref(false);
const batchDeletingTemplates = ref(false);

const showImportDialog = ref(false);
const importLoading = ref(false);
const savingTemplates = ref(false);
const importedTemplates = ref([]);
const selectedImportedTemplateId = ref("");
const selectedImportedTemplateIds = ref([]);
const importForm = ref({
  source_type: "git",
  source: "",
  subdirectory: "",
  branch: "",
  limit: 40,
});

function normalizeImportedDraftPayload(draft) {
  if (!draft || typeof draft !== "object") return null;
  return {
    ...draft,
    style_hints: Array.isArray(draft.style_hints) ? draft.style_hints : [],
    default_workflow: Array.isArray(draft.default_workflow)
      ? draft.default_workflow
      : [],
    rule_domains: Array.isArray(draft.rule_domains) ? draft.rule_domains : [],
    rule_drafts: Array.isArray(draft.rule_drafts) ? draft.rule_drafts : [],
  };
}

const selectedImportedDraftEntries = computed(() =>
  importedTemplates.value
    .filter((item) => selectedImportedTemplateIds.value.includes(item.id))
    .map((item) => ({
      id: item.id,
      name: item.name || item.id,
      draft: normalizeImportedDraftPayload(item.draft),
      content: String(item.content || ""),
      source_name: item.source_name || "",
      source_url: item.source_url || "",
      relative_path: item.relative_path || "",
      description: item.description || "",
    }))
    .filter((item) => item.draft),
);
const selectedImportedPreviewId = computed(() => {
  if (!selectedImportedDraftEntries.value.length) return "";
  const matched = selectedImportedDraftEntries.value.find(
    (item) => item.id === selectedImportedTemplateId.value,
  );
  return matched?.id || selectedImportedDraftEntries.value[0]?.id || "";
});
const selectedImportedDraft = computed(() => {
  const matched = selectedImportedDraftEntries.value.find(
    (item) => item.id === selectedImportedPreviewId.value,
  );
  return matched?.draft || null;
});
const selectedImportedContent = computed(() => {
  const matched = selectedImportedDraftEntries.value.find(
    (item) => item.id === selectedImportedPreviewId.value,
  );
  return String(matched?.content || "");
});
const selectedImportedTemplateCount = computed(
  () => selectedImportedDraftEntries.value.length,
);
const importStatusText = computed(() => {
  if (importLoading.value) return "正在扫描模板...";
  if (!importedTemplates.value.length) return "输入来源后读取模板";
  return `已读取 ${importedTemplates.value.length} 个模板，待保存 ${selectedImportedTemplateCount.value} 个`;
});
const filteredTemplates = computed(() => {
  const keyword = String(searchKeyword.value || "").trim().toLowerCase();
  if (!keyword) return templates.value;
  return templates.value.filter((item) => {
    const haystacks = [
      item?.name,
      item?.name_zh,
      item?.description,
      item?.source_name,
      item?.relative_path,
      ...(Array.isArray(item?.rule_domains) ? item.rule_domains : []),
      ...(Array.isArray(item?.style_hints) ? item.style_hints : []),
    ]
      .map((value) => String(value || "").toLowerCase())
      .filter(Boolean);
    return haystacks.some((value) => value.includes(keyword));
  });
});
const modelPickerDialogTitle = computed(
  () => pendingModelAction.value?.pickerTitle || "选择 AI 来源",
);
const modelPickerDialogDescription = computed(
  () =>
    pendingModelAction.value?.pickerDescription ||
    "先选择本次操作要使用的内部模型或外部智能体 CLI，再继续执行。",
);
const modelPickerDialogConfirmText = computed(
  () => pendingModelAction.value?.pickerConfirmText || "确认",
);

function goToEmployees() {
  void router.push(
    resolveSettingsAwarePanelPath(route.path, "employees", "/employees"),
  );
}

function handleTemplateSelectionChange(rows) {
  selectedTemplateIds.value = (Array.isArray(rows) ? rows : [])
    .map((item) => String(item?.id || "").trim())
    .filter(Boolean);
}

function clearTemplateSelection() {
  selectedTemplateIds.value = [];
  templateTableRef.value?.clearSelection?.();
}

function getTemplateActionTargetIds() {
  const selected = selectedTemplateIds.value
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  return selected;
}

async function fetchTemplates() {
  loading.value = true;
  try {
    const data = await api.get("/agent-templates");
    templates.value = data.templates || [];
  } catch {
    ElMessage.error("加载模板库失败");
  } finally {
    loading.value = false;
  }
}

async function fetchAiSources() {
  aiSourcesLoading.value = true;
  try {
    const data = await api.get("/agent-templates/ai-sources");
    const providers = Array.isArray(data?.internal_providers)
      ? data.internal_providers
      : [];
    const connectors = Array.isArray(data?.external_connectors)
      ? data.external_connectors
      : [];
    internalAiProviders.value = providers;
    externalAiConnectors.value = connectors;
    const currentProvider = providers.find(
      (item) => String(item?.id || "").trim() === selectedTranslationProviderId.value,
    );
    const currentModels = Array.isArray(currentProvider?.models)
      ? currentProvider.models
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      : [];
    if (
      currentProvider &&
      currentModels.includes(String(selectedTranslationModelName.value || "").trim())
    ) {
      // keep current internal selection
    } else {
      const defaultProvider =
        providers.find((item) => Boolean(item?.is_default)) || providers[0] || null;
      selectedTranslationProviderId.value = String(defaultProvider?.id || "").trim();
      selectedTranslationModelName.value = String(
        defaultProvider?.default_model ||
          (Array.isArray(defaultProvider?.models) ? defaultProvider.models[0] : "") ||
          "",
      ).trim();
    }
    const currentConnector = connectors.find(
      (item) => String(item?.id || "").trim() === selectedExternalConnectorId.value,
    );
    const currentAgentAvailable = Array.isArray(currentConnector?.agent_types)
      ? currentConnector.agent_types.some(
          (item) =>
            String(item?.agent_type || "").trim() === selectedExternalAgentType.value &&
            Boolean(item?.available),
        )
      : false;
    if (currentConnector && currentAgentAvailable) {
      // keep current external selection
    } else {
      const defaultConnector = connectors[0] || null;
      const defaultAgent = Array.isArray(defaultConnector?.agent_types)
        ? defaultConnector.agent_types.find((item) => Boolean(item?.available)) ||
          defaultConnector.agent_types[0]
        : null;
      selectedExternalConnectorId.value = String(defaultConnector?.id || "").trim();
      selectedExternalAgentType.value = String(
        defaultAgent?.agent_type || "codex_cli",
      ).trim();
    }
    if (selectedAiSourceType.value === "external" && !connectors.length && providers.length) {
      selectedAiSourceType.value = "internal";
    } else if (selectedAiSourceType.value === "internal" && !providers.length && connectors.length) {
      selectedAiSourceType.value = "external";
    }
  } catch (e) {
    internalAiProviders.value = [];
    externalAiConnectors.value = [];
    selectedTranslationProviderId.value = "";
    selectedTranslationModelName.value = "";
    selectedExternalConnectorId.value = "";
    selectedExternalAgentType.value = "codex_cli";
    ElMessage.error(e?.detail || "加载 AI 来源失败");
  } finally {
    aiSourcesLoading.value = false;
  }
}

async function ensureAiSourcesReady() {
  if (aiSourcesLoading.value) return false;
  if (!internalAiProviders.value.length && !externalAiConnectors.value.length) {
    await fetchAiSources();
  }
  if (!internalAiProviders.value.length && !externalAiConnectors.value.length) {
    ElMessage.warning("当前没有可用 AI 来源，请先配置内部模型或外部智能体连接器");
    return false;
  }
  return true;
}

function handleModelPickerDialogVisibilityChange(value) {
  const visible = Boolean(value);
  showModelPickerDialog.value = visible;
  if (!visible) {
    pendingModelAction.value = null;
  }
}

async function openModelPickerForAction(action) {
  pendingModelAction.value = action;
  const ready = await ensureAiSourcesReady();
  if (!ready) {
    pendingModelAction.value = null;
    return;
  }
  showModelPickerDialog.value = true;
}

async function handleModelPickerConfirm(selection) {
  const action = pendingModelAction.value;
  pendingModelAction.value = null;
  if (!action) return;
  if (action.kind === "deduplicate") {
    await executeAiTemplateDeduplication(selection);
    return;
  }
  if (action.kind === "fill-name") {
    await translateTemplateNames(
      {
        force: false,
        title: "补全中文名",
        confirmText:
          "系统会用 AI 只为缺少中文名的非中文模板补全中文翻译，已有中文翻译不会覆盖。确定继续？",
        confirmButtonText: "开始补全",
        successText: "个模板补全了中文名",
        errorText: "中文名补全失败",
      },
      selection,
    );
    return;
  }
  if (action.kind === "retranslate-name") {
    await translateTemplateNames(
      {
        force: true,
        title: "重译中文名",
        confirmText:
          "系统会用 AI 为非中文模板名称重新生成中文名，并直接覆盖现有中文翻译。原始名称本身是中文的模板不会改动。确定继续？",
        confirmButtonText: "开始重译",
        successText: "个模板的中文名",
        errorText: "中文名重译失败",
      },
      selection,
    );
  }
}

async function runAiTemplateDeduplication() {
  await openModelPickerForAction({
    kind: "deduplicate",
    pickerTitle: "选择同类去重使用的 AI 来源",
    pickerDescription: "先选择内部或外部；内部使用系统模型，外部使用共享的外部智能体 CLI。",
    pickerConfirmText: "下一步",
  });
}

async function executeAiTemplateDeduplication(selection) {
  const targetIds = getTemplateActionTargetIds();
  const targetCount = targetIds.length || templates.value.length;
  if (targetCount < 2) {
    ElMessage.warning("至少需要 2 个模板才能执行同类去重");
    return;
  }
  const sourceType = String(selection?.sourceType || "").trim() || "internal";
  const providerId = String(selection?.providerId || "").trim();
  const modelName = String(selection?.modelName || "").trim();
  const localConnectorId = String(selection?.localConnectorId || "").trim();
  const externalAgentType = String(selection?.externalAgentType || "").trim();
  if (
    (sourceType === "internal" && (!providerId || !modelName)) ||
    (sourceType === "external" && (!localConnectorId || !externalAgentType))
  ) {
    ElMessage.warning("请选择用于同类去重的 AI 来源");
    return;
  }
  await ElMessageBox.confirm(
    targetIds.length
      ? `系统会仅对选中的 ${targetIds.length} 个模板执行同类去重，调用大模型保留最佳版本并删除其余重复项。确定继续？`
      : "系统会先筛选同类型模板，再调用大模型为每组保留最佳版本，并删除其余模板。确定继续？",
    "同类去重",
    {
      type: "warning",
      confirmButtonText: "开始去重",
      cancelButtonText: "取消",
    },
  );
  deduplicatingTemplates.value = true;
  try {
    const data = await api.post("/agent-templates/deduplicate", {
      template_ids: targetIds,
      source_type: sourceType,
      provider_id: providerId,
      model_name: modelName,
      local_connector_id: localConnectorId,
      external_agent_type: externalAgentType,
      apply: true,
    });
    const groups = Array.isArray(data?.groups) ? data.groups : [];
    if (!groups.length) {
      ElMessage.success(targetIds.length ? "选中模板里没有发现需要去重的同类型项" : "没有发现需要去重的同类型模板");
      return;
    }
    const lines = groups.map((group) => {
      const keepName = group?.keep?.name || "未命名模板";
      const removeNames = (group?.remove || [])
        .map((item) => item?.name || item?.id || "未命名模板")
        .join("、");
      const reason = String(group?.reason || "").trim();
      const dedupeSource =
        String(group?.dedupe_source || "").trim() === "exact"
          ? "完全重复"
          : "语义同类";
      return [
        `方式：${dedupeSource}`,
        `类型：${group?.type_label || "同类型模板"}`,
        `保留：${keepName}`,
        `删除：${removeNames || "-"}`,
        reason ? `原因：${reason}` : "",
      ]
        .filter(Boolean)
        .join("\n");
    });
    const exactRemoved = Number(data?.exact_remove_count || 0);
    const semanticRemoved = Number(data?.semantic_remove_count || 0);
    const summaryLines = [
      `完全重复删除：${exactRemoved} 个`,
      `语义同类删除：${semanticRemoved} 个`,
    ];
    await ElMessageBox.alert(
      `${summaryLines.join("\n")}\n\n${lines.join("\n\n")}`,
      "同类去重结果",
      {
      confirmButtonText: "知道了",
      },
    );
    ElMessage.success(
      `已完成同类去重，删除 ${Number(data?.deleted_count || 0)} 个模板（完全重复 ${exactRemoved}，语义同类 ${semanticRemoved}）`,
    );
    if (showDetailDrawer.value && activeTemplate.value) {
      const removedIds = new Set(
        groups.flatMap((group) =>
          (group?.remove || []).map((item) => String(item?.id || "").trim()),
        ),
      );
      if (removedIds.has(String(activeTemplate.value.id || "").trim())) {
        showDetailDrawer.value = false;
        activeTemplate.value = null;
      }
    }
    clearTemplateSelection();
    await fetchTemplates();
  } catch (e) {
    if (String(e || "").includes("cancel")) return;
    ElMessage.error(e?.detail || e?.message || "同类去重失败");
  } finally {
    deduplicatingTemplates.value = false;
  }
}

async function retranslateTemplateNames() {
  await openModelPickerForAction({
    kind: "retranslate-name",
    pickerTitle: "选择重译中文名使用的 AI 来源",
    pickerDescription: "先选择内部或外部；内部使用系统模型，外部使用共享的外部智能体 CLI。",
    pickerConfirmText: "下一步",
  });
}

async function fillMissingTemplateNames() {
  await openModelPickerForAction({
    kind: "fill-name",
    pickerTitle: "选择补全中文名使用的 AI 来源",
    pickerDescription: "先选择内部或外部；内部使用系统模型，外部使用共享的外部智能体 CLI。",
    pickerConfirmText: "下一步",
  });
}

async function translateTemplateNames(options, selection) {
  const targetIds = getTemplateActionTargetIds();
  const targetCount = targetIds.length || templates.value.length;
  if (!targetCount) {
    ElMessage.warning("暂无模板可翻译");
    return;
  }
  const sourceType = String(selection?.sourceType || "").trim() || "internal";
  const providerId = String(selection?.providerId || "").trim();
  const modelName = String(selection?.modelName || "").trim();
  const localConnectorId = String(selection?.localConnectorId || "").trim();
  const externalAgentType = String(selection?.externalAgentType || "").trim();
  if (
    (sourceType === "internal" && (!providerId || !modelName)) ||
    (sourceType === "external" && (!localConnectorId || !externalAgentType))
  ) {
    ElMessage.warning("请选择用于中文翻译的 AI 来源");
    return;
  }
  try {
    await ElMessageBox.confirm(
      targetIds.length
        ? `${options.confirmText}\n\n当前仅处理已选中的 ${targetIds.length} 个模板。`
        : options.confirmText,
      options.title,
      {
        type: "warning",
        confirmButtonText: options.confirmButtonText,
        cancelButtonText: "取消",
      },
    );
  } catch {
    return;
  }
  translatingTemplateNames.value = true;
  try {
    const data = await api.post("/agent-templates/translate-names", {
      template_ids: targetIds,
      source_type: sourceType,
      provider_id: providerId,
      model_name: modelName,
      local_connector_id: localConnectorId,
      external_agent_type: externalAgentType,
      force: Boolean(options.force),
    });
    const updatedCount = Number(data?.updated_count || 0);
    const processedCount = Number(data?.count || targetCount || 0);
    if (!updatedCount) {
      ElMessage.warning(
        targetIds.length
          ? `已处理 ${processedCount} 个选中模板，但没有检测到需要更新的中文名`
          : `已处理 ${processedCount} 个模板，但没有检测到需要更新的中文名`,
      );
    } else {
      ElMessage.success(`已更新 ${updatedCount} ${options.successText}`);
    }
    clearTemplateSelection();
    await fetchTemplates();
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || options.errorText);
  } finally {
    translatingTemplateNames.value = false;
  }
}

function resetImportDialog() {
  importLoading.value = false;
  savingTemplates.value = false;
  importedTemplates.value = [];
  selectedImportedTemplateId.value = "";
  selectedImportedTemplateIds.value = [];
}

function openImportDialog() {
  resetImportDialog();
  importForm.value = {
    source_type: "git",
    source: "",
    subdirectory: "",
    branch: "",
    limit: 40,
  };
  showImportDialog.value = true;
}

function isImportedTemplateSelected(templateId) {
  return selectedImportedTemplateIds.value.includes(templateId);
}

function setImportedTemplateSelection(templateId, checked) {
  const normalizedId = String(templateId || "").trim();
  if (!normalizedId) return;
  if (checked) {
    if (!selectedImportedTemplateIds.value.includes(normalizedId)) {
      selectedImportedTemplateIds.value = [
        ...selectedImportedTemplateIds.value,
        normalizedId,
      ];
    }
    if (!selectedImportedTemplateId.value) {
      selectedImportedTemplateId.value = normalizedId;
    }
    return;
  }
  selectedImportedTemplateIds.value = selectedImportedTemplateIds.value.filter(
    (item) => item !== normalizedId,
  );
  if (selectedImportedTemplateId.value === normalizedId) {
    selectedImportedTemplateId.value = selectedImportedTemplateIds.value[0] || "";
  }
}

function selectAllImportedTemplates() {
  selectedImportedTemplateIds.value = importedTemplates.value.map((item) => item.id);
  if (!selectedImportedTemplateId.value && importedTemplates.value.length) {
    selectedImportedTemplateId.value = importedTemplates.value[0].id;
  }
}

function clearImportedTemplateSelection() {
  selectedImportedTemplateIds.value = [];
  selectedImportedTemplateId.value = "";
}

function showImportedTemplateDetail(templateId) {
  selectedImportedTemplateId.value = String(templateId || "").trim();
}

async function loadTemplateCandidates() {
  const payload = {
    source_type: String(importForm.value.source_type || "git").trim(),
    source: String(importForm.value.source || "").trim(),
    subdirectory: String(importForm.value.subdirectory || "").trim(),
    branch: String(importForm.value.branch || "").trim(),
    limit: Number(importForm.value.limit || 40),
  };
  if (!payload.source) {
    ElMessage.warning(
      payload.source_type === "git" ? "请先输入仓库地址" : "请先输入目录路径",
    );
    return;
  }
  importLoading.value = true;
  try {
    const data = await api.post("/agent-templates/import-preview", payload);
    importedTemplates.value = Array.isArray(data?.templates) ? data.templates : [];
    selectedImportedTemplateId.value = importedTemplates.value[0]?.id || "";
    selectedImportedTemplateIds.value = [];
    if (!importedTemplates.value.length) {
      ElMessage.warning("没有找到可导入的 Markdown agent 模板");
      return;
    }
    ElMessage.success(`已读取 ${importedTemplates.value.length} 个模板`);
  } catch (e) {
    importedTemplates.value = [];
    selectedImportedTemplateId.value = "";
    selectedImportedTemplateIds.value = [];
    ElMessage.error(e.detail || "模板读取失败");
  } finally {
    importLoading.value = false;
  }
}

async function saveSelectedTemplates() {
  if (!selectedImportedDraftEntries.value.length) {
    ElMessage.warning("请先勾选要保存的模板");
    return;
  }
  savingTemplates.value = true;
  try {
    const payload = {
      templates: selectedImportedDraftEntries.value.map((item) => ({
        name: item.draft.name || item.name,
        description: item.description || item.draft.description || "",
        content: item.content || "",
        source_name: item.source_name,
        source_url: item.source_url,
        relative_path: item.relative_path,
        draft: item.draft,
      })),
    };
    const data = await api.post("/agent-templates/batch", payload);
    ElMessage.success(`已保存 ${data?.count || 0} 个模板`);
    showImportDialog.value = false;
    await fetchTemplates();
  } catch (e) {
    ElMessage.error(e.detail || "保存模板失败");
  } finally {
    savingTemplates.value = false;
  }
}

function openTemplateDetail(template) {
  activeTemplate.value = template;
  showDetailDrawer.value = true;
}

async function createEmployeeFromTemplate(template) {
  if (!template?.draft) return;
  creatingEmployee.value = true;
  try {
    const payload = {
      ...template.draft,
      auto_create_missing_skills: true,
      auto_create_missing_rules: true,
    };
    const data = await api.post("/employees/create-from-draft", payload);
    ElMessage.success(`已创建员工：${data?.employee?.name || template.name || "员工"}`);
    await fetchTemplates();
  } catch (e) {
    ElMessage.error(e.detail || "创建员工失败");
  } finally {
    creatingEmployee.value = false;
  }
}

async function deleteTemplate(row) {
  await ElMessageBox.confirm(`确定删除模板「${row.name}」？`, "确认");
  try {
    await api.delete(`/agent-templates/${row.id}`);
    ElMessage.success("已删除");
    if (activeTemplate.value?.id === row.id) {
      showDetailDrawer.value = false;
      activeTemplate.value = null;
    }
    await fetchTemplates();
  } catch {
    ElMessage.error("删除失败");
  }
}

async function batchDeleteTemplates() {
  const targetIds = getTemplateActionTargetIds();
  if (!targetIds.length) {
    ElMessage.warning("请先勾选要删除的模板");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定批量删除已选中的 ${targetIds.length} 个模板？此操作不可恢复。`,
      "批量删除确认",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
      },
    );
  } catch {
    return;
  }
  batchDeletingTemplates.value = true;
  try {
    const data = await api.post("/agent-templates/batch-delete", {
      template_ids: targetIds,
    });
    const deletedIds = new Set(
      (Array.isArray(data?.deleted_ids) ? data.deleted_ids : [])
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    );
    if (showDetailDrawer.value && activeTemplate.value) {
      if (deletedIds.has(String(activeTemplate.value.id || "").trim())) {
        showDetailDrawer.value = false;
        activeTemplate.value = null;
      }
    }
    ElMessage.success(
      `已删除 ${Number(data?.deleted_count || 0)} 个模板`,
    );
    clearTemplateSelection();
    await fetchTemplates();
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || "批量删除失败");
  } finally {
    batchDeletingTemplates.value = false;
  }
}

onMounted(async () => {
  await fetchTemplates();
  await fetchAiSources();
});
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.toolbar h3 {
  margin: 0;
}

.toolbar-subtitle {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.6;
  color: #6b7280;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.template-search-input {
  width: min(280px, 42vw);
}

.template-selection-summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  height: 32px;
  border-radius: 999px;
  background: rgba(139, 115, 85, 0.12);
  color: #8b7355;
  font-size: 12px;
  line-height: 1;
}

.usage-alert {
  margin-bottom: 12px;
}

.detail {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.detail-title {
  font-size: 28px;
  line-height: 1.1;
  font-weight: 600;
  color: #161616;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #6b7280;
}

.detail-section {
  display: grid;
  gap: 8px;
}

.detail-section__label,
.detail-card__label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #8b7355;
}

.detail-section__text,
.detail-card__text {
  font-size: 14px;
  line-height: 1.8;
  color: #374151;
}

.detail-policy {
  margin: 0;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.8;
  color: #374151;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

.detail-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

:global(.template-import-overlay) {
  z-index: 4000 !important;
  background:
    radial-gradient(circle at top left, rgba(255, 244, 214, 0.5), transparent 24%),
    linear-gradient(180deg, #f6f3ee 0%, #f7f7f8 32%, #f5f5f6 100%);
}

:global(.template-import-overlay .el-overlay-dialog) {
  padding: 0;
}

:global(.template-import-dialog) {
  margin: 0;
  width: 100vw;
  height: 100dvh;
  max-width: none;
  max-height: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

:global(.template-import-dialog .el-dialog__header) {
  display: none;
}

:global(.template-import-dialog .el-dialog__body) {
  padding: 0;
  height: 100%;
}

.template-import-shell {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  padding: 14px 16px 16px;
  box-sizing: border-box;
  gap: 18px;
}

.template-import-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 8px 24px 6px;
}

.template-import-hero__copy {
  min-width: 0;
  max-width: 760px;
}

.template-import-hero__eyebrow {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #8b7355;
}

.template-import-hero__title {
  margin-top: 10px;
  font-size: clamp(28px, 3vw, 38px);
  line-height: 1.08;
  font-weight: 600;
  color: #161616;
}

.template-import-hero__text {
  margin-top: 10px;
  font-size: 14px;
  line-height: 1.7;
  color: #5f6368;
}

.template-import-hero__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.template-import-hero__status {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}

.template-import-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 18px;
}

.template-import-main {
  min-width: 0;
  min-height: 0;
  max-height: calc(100dvh - 176px);
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 18px;
}

.template-import-source,
.template-import-candidates,
.template-import-preview {
  min-width: 0;
  border: 1px solid rgba(229, 231, 235, 0.88);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(14px);
}

.template-import-source,
.template-import-candidates {
  padding: 18px;
}

.template-import-preview {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 176px);
  padding: 18px max(20px, calc((100% - 920px) / 2)) 22px;
  overflow: hidden;
}

.template-import-section__head {
  margin-bottom: 12px;
}

.template-import-section__title {
  font-size: 15px;
  font-weight: 600;
  color: #161616;
}

.template-import-section__hint {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.6;
  color: #6b7280;
}

.template-import-form {
  margin-top: 14px;
}

.template-import-source__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.template-import-source__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.template-import-source__status {
  font-size: 12px;
  line-height: 1.5;
  color: #6b7280;
}

.template-import-candidates {
  min-height: 0;
  max-height: calc(100dvh - 176px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.template-import-candidates__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.template-import-candidates__selection {
  font-size: 12px;
  color: #6b7280;
}

.template-import-candidates__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.template-import-candidates__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.template-candidate-card {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid transparent;
  border-radius: 20px;
  background: transparent;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    transform 0.2s ease;
}

.template-candidate-card:hover {
  background: rgba(17, 24, 39, 0.04);
}

.template-candidate-card.is-selected {
  border-color: rgba(59, 130, 246, 0.24);
  background: rgba(219, 234, 254, 0.42);
}

.template-candidate-card.is-active {
  background: rgba(17, 24, 39, 0.08);
  transform: translateY(-1px);
}

.template-candidate-card__select {
  flex-shrink: 0;
  padding-top: 2px;
}

.template-candidate-card__body {
  min-width: 0;
  flex: 1;
}

.template-candidate-card__head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.template-candidate-card__name {
  font-size: 14px;
  font-weight: 600;
  color: #161616;
}

.template-candidate-card__path {
  font-size: 12px;
  color: #7a7f87;
}

.template-candidate-card__desc {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.55;
  color: #4b5563;
}

.template-import-preview__body {
  width: min(100%, 920px);
  margin: 0 auto;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
}

.template-import-preview__selected {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: min(36dvh, 320px);
  padding: 14px 16px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.56);
  border: 1px solid rgba(229, 231, 235, 0.84);
  overflow: hidden;
}

.template-import-preview__selected-head {
  display: grid;
  gap: 4px;
}

.template-import-preview__selected-title {
  font-size: 14px;
  font-weight: 600;
  color: #161616;
}

.template-import-preview__selected-hint {
  font-size: 12px;
  line-height: 1.6;
  color: #6b7280;
}

.template-import-preview__selected-list {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  padding-right: 4px;
}

.template-import-preview__selected-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(229, 231, 235, 0.9);
  background: rgba(255, 255, 255, 0.72);
}

.template-import-preview__selected-card.is-active {
  border-color: rgba(59, 130, 246, 0.28);
  background: rgba(219, 234, 254, 0.42);
}

.template-import-preview__selected-main {
  min-width: 0;
  flex: 1;
}

.template-import-preview__selected-name {
  font-size: 14px;
  font-weight: 600;
  color: #161616;
}

.template-import-preview__selected-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: #7a7f87;
}

.template-import-preview__selected-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.template-import-preview__detail {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.template-import-preview__summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 0 10px;
  border-bottom: 1px solid rgba(229, 231, 235, 0.88);
}

.template-import-preview__summary-main {
  min-width: 0;
}

.template-import-preview__summary-side {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.template-import-preview__title {
  font-size: 28px;
  line-height: 1.14;
  font-weight: 600;
  color: #161616;
}

.template-import-preview__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  font-size: 12px;
  color: #6b7280;
}

.template-import-preview__content {
  margin: 0;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.8;
  color: #374151;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  padding: 14px 16px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(229, 231, 235, 0.84);
}

.template-import-preview__empty {
  font-size: 13px;
  color: #9ca3af;
}

.template-import-preview__empty-state {
  width: min(100%, 780px);
  margin: auto;
  text-align: center;
  padding: 64px 24px;
}

.template-import-preview__empty-title {
  font-size: 30px;
  line-height: 1.12;
  font-weight: 600;
  color: #161616;
}

.template-import-preview__empty-text {
  margin-top: 12px;
  font-size: 15px;
  line-height: 1.8;
  color: #6b7280;
}

@media (max-width: 1180px) {
  .template-import-shell {
    padding: 12px 14px 14px;
  }

  .template-import-hero {
    padding: 6px 12px 4px;
    flex-direction: column;
  }

  .template-import-hero__actions {
    width: 100%;
    justify-content: space-between;
  }

  .template-import-layout {
    grid-template-columns: 1fr;
  }

  .template-import-main {
    grid-template-columns: 1fr;
    max-height: none;
  }

  .template-import-preview {
    max-height: none;
    padding: 18px;
  }

  .template-import-candidates {
    max-height: min(44dvh, 420px);
  }
}

@media (max-width: 720px) {
  .toolbar {
    flex-direction: column;
  }

  .template-import-source__row {
    grid-template-columns: 1fr;
  }

  .template-import-hero__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .template-import-hero__status {
    white-space: normal;
  }

  .template-import-candidates__toolbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .template-import-preview__summary {
    flex-direction: column;
  }

  .template-import-preview__title {
    font-size: 24px;
  }

  .template-import-preview__selected-card {
    flex-direction: column;
  }

  .template-import-preview__selected-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
