<template>
  <section class="work-log-page">
    <header class="work-log-page__head">
      <div>
        <p class="work-log-page__eyebrow">Project Work Log</p>
        <h1>项目工作日志</h1>
        <p>
          独立的项目工作日志模块。这里直接读取项目需求记录和工作会话生成日志，不再依赖全局助手表单。
        </p>
      </div>
      <button
        type="button"
        class="work-log-page__button work-log-page__button--primary"
        :disabled="generating || !canGenerate"
        @click="generateWorkLog"
      >
        {{ generating ? "生成中" : "生成日志" }}
      </button>
    </header>

    <section class="work-log-layout">
      <aside class="work-log-panel work-log-panel--settings">
        <div class="work-log-panel__title">
          <span>生成参数</span>
          <button type="button" class="work-log-link" :disabled="loadingProjects" @click="loadProjects(true)">
            刷新项目
          </button>
        </div>

        <div class="work-log-field">
          <div class="work-log-field__head">
            <span>项目</span>
            <span class="work-log-field__count">{{ selectedProjectIds.length }} 个</span>
          </div>
          <button
            type="button"
            class="work-log-project-select"
            :disabled="loadingProjects"
            @click="openProjectPicker"
          >
            <span :class="{ 'is-placeholder': !selectedProjectIds.length }">
              {{ selectedProjectSummary }}
            </span>
            <span class="work-log-project-select__icon">⌄</span>
          </button>
          <p v-if="!selectedProjectIds.length" class="work-log-field__hint">
            默认不选择项目，请手动选择需要生成日志的项目。
          </p>
        </div>

        <teleport to="body">
          <div
            v-if="projectPickerOpen"
            class="work-log-modal-backdrop"
            role="presentation"
            @click.self="closeProjectPicker"
          >
            <section
              class="work-log-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="work-log-project-picker-title"
            >
              <header class="work-log-modal__head">
                <div>
                  <h2 id="work-log-project-picker-title">选择项目</h2>
                  <p>已选择 {{ projectPickerDraftIds.length }} 个项目，可选 {{ projectPickerOptions.length }} 个</p>
                </div>
                <button type="button" class="work-log-modal__close" aria-label="关闭" @click="closeProjectPicker">
                  ×
                </button>
              </header>
              <div class="work-log-modal__toolbar">
                <button type="button" class="work-log-link" :disabled="loadingProjectPickerOptions || !projectPickerOptions.length" @click="selectAllProjectDrafts">
                  全选
                </button>
                <button type="button" class="work-log-link" :disabled="!projectPickerDraftIds.length" @click="clearProjectDrafts">
                  清空
                </button>
              </div>
              <div class="work-log-modal__body">
                <div v-if="loadingProjects || loadingProjectPickerOptions" class="work-log-project-empty">
                  {{ loadingProjects ? "加载项目中" : "正在按时间范围筛选项目" }}
                </div>
                <div v-else-if="!projectPickerOptions.length" class="work-log-project-empty">
                  当前时间范围内暂无有工作记录的项目
                </div>
                <div v-else class="work-log-project-picker-list">
                  <label
                    v-for="project in projectPickerOptions"
                    :key="project.id"
                    class="work-log-project-option"
                    :class="{ 'is-selected': projectPickerDraftIds.includes(project.id) }"
                  >
                    <input v-model="projectPickerDraftIds" type="checkbox" :value="project.id" />
                    <span>{{ project.name || project.id }}</span>
                  </label>
                </div>
              </div>
              <footer class="work-log-modal__foot">
                <button type="button" class="work-log-page__button work-log-page__button--ghost" @click="closeProjectPicker">
                  取消
                </button>
                <button type="button" class="work-log-page__button work-log-page__button--primary" @click="applyProjectPicker">
                  确定
                </button>
              </footer>
            </section>
          </div>
        </teleport>

        <div class="work-log-field-grid">
          <label class="work-log-field">
            <span>日志类型</span>
            <select v-model="form.reportType" @change="resetDateRange">
              <option v-for="item in reportTypes" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <label class="work-log-field">
            <span>模板</span>
            <select v-model="form.template" :disabled="loadingTemplates">
              <option v-for="item in templates" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
        </div>

        <div class="work-log-field-grid">
          <label class="work-log-field">
            <span>开始日期</span>
            <input v-model="form.startDate" type="date" />
          </label>
          <label class="work-log-field">
            <span>结束日期</span>
            <input v-model="form.endDate" type="date" />
          </label>
        </div>

        <label class="work-log-check">
          <input v-model="form.includeDetails" type="checkbox" />
          <span>保留验证和轨迹明细</span>
        </label>

        <label class="work-log-check">
          <input v-model="form.useAiSummary" type="checkbox" />
          <span>使用模型生成领导口径总结</span>
        </label>

        <label v-if="form.useAiSummary" class="work-log-field">
          <span>生成模型</span>
          <select v-model="selectedModelOptionValue" :disabled="loadingModelOptions || !modelOptions.length">
            <option v-if="!modelOptions.length" value="">
              {{ loadingModelOptions ? "模型加载中" : "暂无可用模型" }}
            </option>
            <option v-for="option in modelOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>

        <label class="work-log-field">
          <span>补充说明</span>
          <textarea
            v-model="form.extraNotes"
            rows="4"
            maxlength="500"
            placeholder="可选：补充汇报对象、输出口径或本次日志重点"
          />
        </label>

        <p v-if="errorText" class="work-log-error">{{ errorText }}</p>
      </aside>

      <main class="work-log-main">
        <nav class="work-log-tabs" aria-label="项目工作日志视图">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            class="work-log-tabs__item"
            :class="{ 'is-active': activeTab === tab.id }"
            @click="activeTab = tab.id"
          >
            <span>{{ tab.label }}</span>
            <small>{{ tab.count }}</small>
          </button>
        </nav>

        <section v-if="activeTab === 'templates'" class="work-log-panel">
          <div class="work-log-panel__title work-log-panel__title--table">
            <div>
              <span>日志模板</span>
              <p>模板为全局通用配置，所有项目生成日志时共用这一套模板。</p>
            </div>
            <button type="button" class="work-log-link" :disabled="loadingTemplates" @click="loadTemplates">
              {{ loadingTemplates ? "刷新中" : "刷新模板" }}
            </button>
          </div>
          <div v-if="loadingTemplates" class="work-log-empty">
            正在加载日志模板。
          </div>
          <div v-else class="work-log-template-list">
            <article v-for="template in templates" :key="template.value" class="work-log-template">
              <div v-if="editingTemplateValue === template.value" class="work-log-template__editor">
                <label class="work-log-field work-log-field--inline">
                  <span>模板名称</span>
                  <input v-model="templateDrafts[template.value].label" maxlength="80" />
                </label>
                <label class="work-log-field work-log-field--inline">
                  <span>生成提示词</span>
                  <textarea
                    v-model="templateDrafts[template.value].description"
                    rows="8"
                    maxlength="4000"
                    placeholder="填写模型生成时必须遵守的输出格式、标题层级和内容组织要求"
                  />
                </label>
              </div>
              <div v-else class="work-log-template__content">
                <h2>{{ template.label }}</h2>
                <p>{{ template.description }}</p>
              </div>
              <div class="work-log-template__actions">
                <template v-if="editingTemplateValue === template.value">
                  <button
                    type="button"
                    class="work-log-link"
                    :disabled="savingTemplateValue === template.value"
                    @click="saveTemplate(template)"
                  >
                    {{ savingTemplateValue === template.value ? "保存中" : "保存" }}
                  </button>
                  <button type="button" class="work-log-link" :disabled="savingTemplateValue === template.value" @click="cancelEditTemplate">
                    取消
                  </button>
                </template>
                <button v-else type="button" class="work-log-link" @click="startEditTemplate(template)">
                  编辑
                </button>
              </div>
            </article>
          </div>
        </section>

        <section v-else class="work-log-panel">
          <div class="work-log-panel__title work-log-panel__title--table">
            <div>
              <span>日志记录</span>
              <p>这里只显示本模块写入后端的真实生成记录，内容来自项目需求记录和工作会话。</p>
            </div>
            <button type="button" class="work-log-link" :disabled="loadingRecords" @click="loadRecords">
              {{ loadingRecords ? "刷新中" : "刷新记录" }}
            </button>
          </div>

          <div v-if="loadingRecords" class="work-log-empty">
            正在加载日志记录。
          </div>
          <div v-else-if="!records.length" class="work-log-empty">
            还没有日志记录。每点击一次生成日志都会在这里新增一条记录。
          </div>
          <div v-else class="work-log-record-table">
            <div class="work-log-record-table__head">
              <span>标题</span>
              <span>项目</span>
              <span>模板</span>
              <span>生成时间</span>
              <span>操作</span>
            </div>
            <article v-for="record in records" :key="record.id" class="work-log-record-row">
              <div class="work-log-record-row__title">
                <strong>{{ record.title || "未命名日志" }}</strong>
                <small>{{ resolveLabel(reportTypes, record.reportType || record.report_type, "日志") }}</small>
              </div>
              <span>{{ record.projectLabel || record.projectName || record.project_id || "-" }}</span>
              <span>{{ record.templateLabel || record.template_label || "-" }}</span>
              <span>{{ displayRecordTime(record.createdAt || record.created_at) }}</span>
              <div class="work-log-record-row__actions">
                <button type="button" class="work-log-link" @click="copyRecord(record)">
                  {{ copiedRecordId === record.id ? "已复制" : "复制" }}
                </button>
                <button
                  type="button"
                  class="work-log-link work-log-link--danger"
                  :disabled="deletingRecordId === record.id"
                  @click="deleteRecord(record)"
                >
                  {{ deletingRecordId === record.id ? "删除中" : "删除" }}
                </button>
              </div>
            </article>
          </div>
        </section>

        <section v-if="previewText" class="work-log-panel work-log-preview">
          <div class="work-log-panel__title">
            <span>本次生成结果</span>
            <button type="button" class="work-log-link" @click="copyText(previewText)">复制</button>
          </div>
          <pre>{{ previewText }}</pre>
        </section>
      </main>
    </section>
  </section>
</template>

<script setup>
import { ElMessage } from "element-plus";
import { computed, onMounted, reactive, ref, watch } from "vue";

import api from "@/utils/api.js";
import { formatRelativeDateTime } from "@/utils/date.js";
import { fetchAllVisibleProjects } from "@/utils/projects.js";

const activeTab = ref("templates");
const loadingProjects = ref(false);
const loadingProjectPickerOptions = ref(false);
const loadingRecords = ref(false);
const loadingTemplates = ref(false);
const loadingModelOptions = ref(false);
const generating = ref(false);
const errorText = ref("");
const previewText = ref("");
const projectOptions = ref([]);
const projectPickerOptions = ref([]);
const modelOptions = ref([]);
const selectedModelOptionValue = ref("");
const records = ref([]);
const copiedRecordId = ref("");
const deletingRecordId = ref("");
const editingTemplateValue = ref("");
const savingTemplateValue = ref("");
const projectPickerOpen = ref(false);
const projectPickerDraftIds = ref([]);
const templateDrafts = reactive({});

const reportTypes = [
  { value: "daily", label: "日报" },
  { value: "weekly", label: "周报" },
  { value: "monthly", label: "月报" },
];

const defaultTemplates = [
  {
    value: "leadership_work_plan",
    label: "领导周报（解决内容）",
    description: "把技术执行轨迹转换成领导可读的解决事项、风险阻塞和下周计划。",
  },
  {
    value: "engineering_summary",
    label: "研发执行摘要",
    description: "保留实现、验证、风险和后续项，适合研发内部同步。",
  },
  {
    value: "delivery_review",
    label: "交付复盘",
    description: "围绕交付结果、验证证据、遗留风险和后续动作形成记录。",
  },
];
const templates = ref(defaultTemplates.map((item) => ({ ...item })));

const form = reactive({
  projectIds: [],
  reportType: "weekly",
  template: "leadership_work_plan",
  startDate: "",
  endDate: "",
  includeDetails: false,
  useAiSummary: true,
  extraNotes: "",
});

const tabs = computed(() => [
  { id: "templates", label: "日志模板", count: templates.value.length },
  { id: "records", label: "日志记录", count: records.value.length },
]);

const selectedProjectIds = computed(() =>
  Array.from(
    new Set(
      (Array.isArray(form.projectIds) ? form.projectIds : [])
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  ),
);

const selectedProjects = computed(() =>
  selectedProjectIds.value.map((projectId) =>
    projectOptions.value.find((item) => item.id === projectId) || {
      id: projectId,
      name: projectId,
    },
  ),
);

const selectedProjectSummary = computed(() => {
  if (!selectedProjects.value.length) return "请选择项目";
  const names = selectedProjects.value.map((item) => item.name || item.id).filter(Boolean);
  if (names.length <= 2) return names.join("、");
  return `已选择 ${names.length} 个项目`;
});

const selectedTemplate = computed(() =>
  templates.value.find((item) => item.value === form.template) || null,
);

const canGenerate = computed(() =>
  Boolean(selectedProjectIds.value.length && form.startDate && form.endDate),
);

onMounted(() => {
  resetDateRange();
  void loadTemplates();
  void loadProjects();
  void loadRecords();
  void loadModelOptions();
});

watch(
  () => selectedProjectIds.value.join("\n"),
  () => {
    previewText.value = "";
    ensureSelectedTemplate();
  },
);

watch(
  () => `${form.startDate}\n${form.endDate}`,
  () => {
    if (projectPickerOpen.value) {
      void refreshProjectPickerOptions();
    }
  },
);

function formatDateValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function resolveDefaultDateRange(type = "weekly") {
  const end = new Date();
  const start = new Date(end);
  if (type === "daily") {
    return [formatDateValue(end), formatDateValue(end)];
  }
  if (type === "monthly") {
    start.setMonth(end.getMonth() - 1);
    start.setDate(start.getDate() + 1);
  } else {
    start.setDate(end.getDate() - 6);
  }
  return [formatDateValue(start), formatDateValue(end)];
}

function resetDateRange() {
  const [startDate, endDate] = resolveDefaultDateRange(form.reportType);
  form.startDate = startDate;
  form.endDate = endDate;
}

function resolveProjectItems(payload) {
  if (Array.isArray(payload?.projects)) return payload.projects;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload)) return payload;
  return [];
}

function hasDateRange() {
  return Boolean(String(form.startDate || "").trim() && String(form.endDate || "").trim());
}

async function loadProjects(force = false) {
  if ((!force && projectOptions.value.length) || loadingProjects.value) return;
  loadingProjects.value = true;
  errorText.value = "";
  try {
    let items = await fetchAllVisibleProjects();
    if (!items.length) {
      const metaPayload = await api.get("/work-sessions/meta");
      items = resolveProjectItems(metaPayload);
    }
    projectOptions.value = items
      .map((item) => ({
        id: String(item?.id || "").trim(),
        name: String(item?.name || item?.title || item?.id || "").trim(),
      }))
      .filter((item) => item.id);
    const availableIds = new Set(projectOptions.value.map((item) => item.id));
    form.projectIds = selectedProjectIds.value.filter((item) =>
      availableIds.has(item),
    );
  } catch (err) {
    errorText.value = err?.detail || err?.message || "加载项目列表失败";
  } finally {
    loadingProjects.value = false;
  }
}

async function projectHasWorkInDateRange(projectId) {
  if (!hasDateRange()) return true;
  const [sessions, requirementRecords] = await Promise.all([
    fetchWorkSessions(projectId, form.startDate, form.endDate).catch(() => []),
    fetchRequirementRecords(projectId, form.startDate, form.endDate).catch(() => []),
  ]);
  return Boolean(sessions.length || requirementRecords.length);
}

async function refreshProjectPickerOptions() {
  if (!projectOptions.value.length) {
    projectPickerOptions.value = [];
    return;
  }
  if (!hasDateRange()) {
    projectPickerOptions.value = [...projectOptions.value];
    return;
  }
  loadingProjectPickerOptions.value = true;
  errorText.value = "";
  try {
    const availability = await Promise.all(
      projectOptions.value.map(async (project) => ({
        project,
        hasWork: await projectHasWorkInDateRange(project.id),
      })),
    );
    projectPickerOptions.value = availability
      .filter((item) => item.hasWork)
      .map((item) => item.project);
    const availableIds = new Set(projectPickerOptions.value.map((item) => item.id));
    projectPickerDraftIds.value = projectPickerDraftIds.value.filter((item) =>
      availableIds.has(item),
    );
  } catch (err) {
    errorText.value = err?.detail || err?.message || "筛选项目列表失败";
    projectPickerOptions.value = [];
  } finally {
    loadingProjectPickerOptions.value = false;
  }
}

async function openProjectPicker() {
  projectPickerDraftIds.value = [...selectedProjectIds.value];
  projectPickerOpen.value = true;
  if (!projectOptions.value.length && !loadingProjects.value) {
    await loadProjects(true);
  }
  await refreshProjectPickerOptions();
}

function closeProjectPicker() {
  projectPickerOpen.value = false;
}

function applyProjectPicker() {
  const availableIds = new Set(projectPickerOptions.value.map((item) => item.id));
  form.projectIds = Array.from(
    new Set(
      projectPickerDraftIds.value
        .map((item) => String(item || "").trim())
        .filter((item) => item && availableIds.has(item)),
    ),
  );
  projectPickerOpen.value = false;
}

function selectAllProjectDrafts() {
  projectPickerDraftIds.value = projectPickerOptions.value.map((item) => item.id).filter(Boolean);
}

function clearProjectDrafts() {
  projectPickerDraftIds.value = [];
}

function normalizeModelConfigs(provider) {
  const configs = Array.isArray(provider?.model_configs) ? provider.model_configs : [];
  if (configs.length) {
    return configs
      .map((item) => ({
        name: String(item?.name || item?.model_name || "").trim(),
        type: String(item?.model_type || "").trim(),
      }))
      .filter((item) => item.name);
  }
  return (Array.isArray(provider?.models) ? provider.models : [])
    .map((name) => ({
      name: String(name || "").trim(),
      type: "",
    }))
    .filter((item) => item.name);
}

function resolveModelOptionValue(providerId, modelName) {
  const normalizedProviderId = String(providerId || "").trim();
  const normalizedModelName = String(modelName || "").trim();
  if (!normalizedProviderId || !normalizedModelName) return "";
  return `${encodeURIComponent(normalizedProviderId)}::${encodeURIComponent(normalizedModelName)}`;
}

function parseModelOptionValue(value) {
  const raw = String(value || "").trim();
  const separatorIndex = raw.indexOf("::");
  if (separatorIndex <= 0) return { providerId: "", modelName: "" };
  return {
    providerId: decodeURIComponent(raw.slice(0, separatorIndex)),
    modelName: decodeURIComponent(raw.slice(separatorIndex + 2)),
  };
}

async function loadModelOptions() {
  if (loadingModelOptions.value) return;
  loadingModelOptions.value = true;
  try {
    const projectId = selectedProjectIds.value[0] || "proj-d16591a6";
    const data = await api.get(
      `/projects/${encodeURIComponent(projectId)}/chat/providers`,
      { params: { include_runtime_external_tools: false } },
    );
    const options = [];
    for (const provider of Array.isArray(data?.providers) ? data.providers : []) {
      const providerId = String(provider?.id || "").trim();
      if (!providerId) continue;
      const providerName = String(provider?.name || providerId).trim();
      for (const model of normalizeModelConfigs(provider)) {
        options.push({
          value: resolveModelOptionValue(providerId, model.name),
          label: `${providerName} / ${model.name}`,
          providerId,
          modelName: model.name,
          modelType: model.type,
        });
      }
    }
    modelOptions.value = options;
    const defaultValue = resolveModelOptionValue(data?.default_provider_id, data?.default_model_name);
    selectedModelOptionValue.value = options.some((item) => item.value === defaultValue)
      ? defaultValue
      : options[0]?.value || "";
  } catch (err) {
    modelOptions.value = [];
    if (form.useAiSummary) {
      errorText.value = err?.detail || err?.message || "加载模型列表失败";
    }
  } finally {
    loadingModelOptions.value = false;
  }
}

function mergeTemplates(savedItems) {
  const savedByValue = new Map(
    (Array.isArray(savedItems) ? savedItems : [])
      .map((item) => ({
        value: String(item?.value || "").trim(),
        label: String(item?.label || "").trim(),
        description: String(item?.description || "").trim(),
      }))
      .filter((item) => item.value)
      .map((item) => [item.value, item]),
  );
  const merged = defaultTemplates.map((item) => ({
    ...item,
    ...(savedByValue.get(item.value) || {}),
  }));
  for (const item of savedByValue.values()) {
    if (!merged.some((template) => template.value === item.value)) {
      merged.push({
        value: item.value,
        label: item.label || item.value,
        description: item.description || "自定义日志模板",
      });
    }
  }
  templates.value = merged;
  ensureSelectedTemplate();
}

async function loadTemplates() {
  if (loadingTemplates.value) return;
  loadingTemplates.value = true;
  errorText.value = "";
  try {
    const data = await api.get("/projects/_global/work-log-templates");
    mergeTemplates(data?.items || []);
  } catch (err) {
    if (Number(err?.status || 0) === 404) {
      mergeTemplates([]);
      return;
    }
    errorText.value = err?.detail || err?.message || "加载日志模板失败";
  } finally {
    loadingTemplates.value = false;
  }
}

function ensureSelectedTemplate() {
  if (!templates.value.some((item) => item.value === form.template)) {
    form.template = templates.value[0]?.value || "";
  }
}

function startEditTemplate(template) {
  const value = String(template?.value || "").trim();
  if (!value) return;
  templateDrafts[value] = {
    label: String(template?.label || "").trim(),
    description: String(template?.description || "").trim(),
  };
  editingTemplateValue.value = value;
}

function cancelEditTemplate() {
  editingTemplateValue.value = "";
  savingTemplateValue.value = "";
}

async function saveTemplate(template) {
  const value = String(template?.value || "").trim();
  const draft = templateDrafts[value] || {};
  if (!value || savingTemplateValue.value) return;
  const label = String(draft.label || "").trim();
  if (!label) {
    errorText.value = "模板名称不能为空";
    return;
  }
  savingTemplateValue.value = value;
  errorText.value = "";
  try {
    const payload = {
      label,
      description: String(draft.description || "").trim(),
    };
    const saved = await api.put(
      `/projects/_global/work-log-templates/${encodeURIComponent(value)}`,
      payload,
    );
    const nextTemplate = {
      ...template,
      ...(saved?.item || payload),
      value,
    };
    templates.value = templates.value.map((item) =>
      item.value === value ? nextTemplate : item,
    );
    editingTemplateValue.value = "";
  } catch (err) {
    errorText.value = err?.detail || err?.message || "保存日志模板失败";
  } finally {
    savingTemplateValue.value = "";
  }
}

async function loadRecords() {
  if (loadingRecords.value) return;
  loadingRecords.value = true;
  errorText.value = "";
  try {
    const data = await api.get("/projects/_global/work-logs", {
      params: { limit: 50 },
    });
    const deduped = new Map();
    for (const item of Array.isArray(data?.items) ? data.items : []) {
      const id = String(item?.id || "").trim();
      if (!id || deduped.has(id)) continue;
      deduped.set(id, normalizeRecord(item));
    }
    records.value = Array.from(deduped.values())
      .sort((a, b) =>
        String(b?.createdAt || b?.created_at || "").localeCompare(
          String(a?.createdAt || a?.created_at || ""),
        ),
      )
      .slice(0, 50);
  } catch (err) {
    errorText.value = err?.detail || err?.message || "加载日志记录失败";
  } finally {
    loadingRecords.value = false;
  }
}

function normalizeRecord(record) {
  const projectNames = Array.isArray(record?.projectNames)
    ? record.projectNames.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const projectLabel = String(record?.projectLabel || "").trim()
    || projectNames.join("、")
    || String(record?.projectName || record?.project_id || "").trim();
  return {
    ...record,
    projectLabel,
  };
}

function inDateRange(value, startDate, endDate) {
  const raw = String(value || "").trim();
  if (!raw) return false;
  const datePart = raw.slice(0, 10);
  return datePart >= startDate && datePart <= endDate;
}

async function fetchWorkSessions(projectId, startDate, endDate) {
  const data = await api.get(`/projects/${encodeURIComponent(projectId)}/work-sessions`, {
    params: { limit: 200 },
  });
  return Array.isArray(data?.items)
    ? data.items.filter((item) =>
        inDateRange(item?.updated_at || item?.created_at, startDate, endDate),
      )
    : [];
}

function resolveRequirementRound(record) {
  if (record?.currentRound && typeof record.currentRound === "object") return record.currentRound;
  if (record?.latestRound && typeof record.latestRound === "object") return record.latestRound;
  if (record?.detailRound && typeof record.detailRound === "object") return record.detailRound;
  const rounds = Array.isArray(record?.rounds) ? record.rounds : [];
  return rounds[rounds.length - 1] || {};
}

function resolveRequirementTime(record) {
  const round = resolveRequirementRound(record);
  return String(record?.updatedAt || record?.createdAt || round?.updatedAt || round?.createdAt || "").trim();
}

async function fetchRequirementRecords(projectId, startDate, endDate) {
  const data = await api.get(`/projects/${encodeURIComponent(projectId)}/requirement-records`, {
    params: { limit: 300 },
  });
  return Array.isArray(data?.items)
    ? data.items.filter((item) => inDateRange(resolveRequirementTime(item), startDate, endDate))
    : [];
}

function normalizePlainText(value, fallback = "") {
  return (
    String(value || "")
      .replace(/`[^`]+`/g, "")
      .replace(/[A-Za-z0-9_.-]+\/[A-Za-z0-9_./-]+/g, "")
      .replace(/\b(?:ws|tts|ttn|chat-session|proj)-[A-Za-z0-9_-]+\b/g, "")
      .replace(/\s+/g, " ")
      .trim() || fallback
  );
}

function dedupeItems(values, limit = 8) {
  const seen = new Set();
  return (Array.isArray(values) ? values : [])
    .map((item) => normalizePlainText(item))
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    })
    .slice(0, limit);
}

function formatList(values, emptyText = "暂无") {
  const items = Array.isArray(values) ? values.map((item) => String(item || "").trim()).filter(Boolean) : [];
  if (!items.length) return `- ${emptyText}`;
  return items.slice(0, 8).map((item) => `- ${item}`).join("\n");
}

function isCompletedStatus(value) {
  return ["done", "completed", "success", "closed", "archived"].includes(
    String(value || "").trim().toLowerCase(),
  );
}

function summarizeRequirement(record) {
  const round = resolveRequirementRound(record);
  const workSessions = Array.isArray(round?.workSessions) ? round.workSessions : [];
  const status = String(round?.status || record?.status || "pending").trim();
  const rootGoal = normalizePlainText(record?.rootGoal || round?.rootGoal || record?.title, "未命名需求");
  const summary = normalizePlainText(record?.summaryText || round?.summaryText || record?.currentFocus || round?.currentNodeTitle);
  const outcome = summary && summary !== rootGoal ? `${rootGoal}：${summary}` : rootGoal;
  return {
    outcome,
    isFinalized: Boolean(round?.isFinalized) || isCompletedStatus(status),
    risks: dedupeItems(workSessions.flatMap((item) => (Array.isArray(item?.risks) ? item.risks : [])), 4),
    verification: dedupeItems(workSessions.flatMap((item) => (Array.isArray(item?.verification) ? item.verification : [])), 4),
    nextSteps: dedupeItems(workSessions.flatMap((item) => (Array.isArray(item?.next_steps) ? item.next_steps : [])), 4),
  };
}

function summarizeSession(session) {
  const goal = normalizePlainText(session?.goal || session?.title || session?.session_id, "未命名工作");
  const status = String(session?.latest_status || session?.status || "").trim();
  return status ? `${goal}（${status}）` : goal;
}

function resolveLabel(options, value, fallback = "") {
  const items = Array.isArray(options) ? options : options?.value || [];
  return items.find((item) => item.value === value)?.label || fallback || value;
}

function resolveProjectLabel(project) {
  return String(project?.name || project?.id || "").trim() || "未命名项目";
}

function buildProjectDraftText(project, sessions, requirementRecords) {
  const projectLabel = resolveProjectLabel(project);
  const requirements = requirementRecords.map((item) => summarizeRequirement(item));
  const completedRequirements = requirements.filter((item) => item.isFinalized);
  const activeRequirements = requirements.filter((item) => !item.isFinalized);
  const completedSessions = sessions.filter((item) => isCompletedStatus(item?.latest_status || item?.status));
  const activeSessions = sessions.filter((item) => !completedSessions.includes(item));
  const solvedItems = completedRequirements.length
    ? completedRequirements.map((item) => item.outcome)
    : completedSessions.map((item) => summarizeSession(item));
  const activeItems = activeRequirements.length
    ? activeRequirements.map((item) => item.outcome)
    : activeSessions.map((item) => summarizeSession(item));
  const summaryItems = solvedItems.length ? solvedItems : activeItems;
  const risks = dedupeItems([
    ...requirements.flatMap((item) => item.risks),
    ...sessions.flatMap((item) => (Array.isArray(item?.risks) ? item.risks : [])),
  ]);
  const verification = dedupeItems([
    ...requirements.flatMap((item) => item.verification),
    ...sessions.flatMap((item) => (Array.isArray(item?.verification) ? item.verification : [])),
  ]);
  const nextSteps = dedupeItems([
    ...requirements.flatMap((item) => item.nextSteps),
    ...sessions.flatMap((item) => (Array.isArray(item?.next_steps) ? item.next_steps : [])),
    ...activeItems.map((item) => `继续推进：${item}`),
  ]);
  const detailLines = form.includeDetails
    ? `\n验证/交付依据：\n${formatList(verification, "暂无验证记录")}\n工作会话明细：\n${formatList(sessions.map((item) => summarizeSession(item)), "当前范围内暂无工作会话")}`
    : "";
  return [
    `## 项目：${projectLabel}`,
    `记录数量：需求记录 ${requirementRecords.length} 条，工作会话 ${sessions.length} 条。`,
    `本期项目工作计划（由需求记录反推）：围绕 ${solvedItems.length + activeItems.length} 项需求推进，其中已解决/交付 ${solvedItems.length} 项，持续推进 ${activeItems.length} 项。`,
    `本期可写入总结的工作事项：\n${formatList(summaryItems, "本期暂无可写入总结的工作事项")}`,
    `本期解决了什么：\n${formatList(solvedItems, "本期暂无已闭环问题")}`,
    `本期仍在推进：\n${formatList(activeItems, "暂无进行中事项")}`,
    `风险与阻塞：\n${formatList(risks, "暂无需要协调的阻塞")}`,
    `下一步计划：\n${formatList(nextSteps, "延续未完成事项并按业务反馈收口")}`,
    detailLines,
  ]
    .filter(Boolean)
    .join("\n\n");
}

function buildDraftText(projectPayloads) {
  const payloads = Array.isArray(projectPayloads) ? projectPayloads : [];
  const projectLabel = payloads
    .map((item) => resolveProjectLabel(item?.project))
    .filter(Boolean)
    .join("、");
  const totalRequirementCount = payloads.reduce(
    (sum, item) => sum + (Array.isArray(item?.requirementRecords) ? item.requirementRecords.length : 0),
    0,
  );
  const totalSessionCount = payloads.reduce(
    (sum, item) => sum + (Array.isArray(item?.sessions) ? item.sessions.length : 0),
    0,
  );
  const reportTitle = `${resolveLabel(reportTypes, form.reportType)}｜${form.startDate} 至 ${form.endDate}`;
  return [
    `# ${reportTitle}`,
    `生成时间：${formatRelativeDateTime(new Date().toISOString())}`,
    `项目：${projectLabel || "未选择项目"}`,
    `模板：${resolveLabel(templates, form.template)}`,
    form.extraNotes ? `补充说明：${form.extraNotes}` : "",
    `总记录数量：需求记录 ${totalRequirementCount} 条，工作会话 ${totalSessionCount} 条。`,
    "以下原始数据已按项目分组；生成时必须把每个项目下的事项归入对应项目，不能跨项目合并或挪用。",
    payloads
      .map((item) => buildProjectDraftText(item.project, item.sessions || [], item.requirementRecords || []))
      .join("\n\n"),
  ]
    .filter(Boolean)
    .join("\n\n");
}

function buildAiPrompt(draftText, projects = []) {
  const projectItems = Array.isArray(projects) ? projects : [];
  const projectNames = projectItems
    .map((project) => String(project?.name || project?.id || "").trim())
    .filter(Boolean);
  return [
    `请基于以下项目需求记录和工作轨迹，生成一份${resolveLabel(reportTypes, form.reportType)}。`,
    `输出模板：${resolveLabel(templates, form.template)}。`,
    selectedTemplate.value?.description
      ? [
          "【生成提示词，最高优先级】",
          "必须严格按照下面提示词的标题、层级、顺序、编号和段落结构输出。",
          "不得新增提示词以外的一级标题或总结段，不得改写提示词中指定的标题名称。",
          "提示词中的“项目一 / 项目二”等占位项目名必须替换为当前选择的真实项目名称。",
          selectedTemplate.value.description,
        ].join("\n")
      : "",
    projectNames.length ? `允许出现的项目范围：${projectNames.join("、")}。` : "",
    "范围约束：只能使用下方原始结构化草稿中已经出现的项目、事项、风险和计划；不得补充、联想或引用草稿以外的项目和工作内容。",
    "项目归属约束：原始草稿已经按项目分组，必须把每个项目分组下的事项写回同名项目；不得把一个项目的事项挪到另一个项目，也不得因为某项目不是第一个项目就写暂无。",
    "如果草稿没有某类内容，请写暂无或省略该类内容，不要从历史上下文、全局助手记忆、其他项目记录中补齐。",
    "内容筛选：可以按领导口径精简具体代码、文件、命令、工具、会话 ID 或执行过程，但最终输出结构必须服从【生成提示词】。",
    "输出要求：不要输出项目 ID 或类似 proj-xxx 的内部标识；不要输出文件路径、接口路径、测试命令、MCP 工具名、session_id、task_node_id。",
    form.extraNotes ? `额外口径：${form.extraNotes}` : "",
    "原始结构化草稿如下：",
    draftText,
  ]
    .filter(Boolean)
    .join("\n\n");
}

async function summarizeWithAi(draftText, projects = []) {
  const selectedModel = parseModelOptionValue(selectedModelOptionValue.value);
  const projectNames = (Array.isArray(projects) ? projects : [])
    .map((project) => String(project?.name || project?.id || "").trim())
    .filter(Boolean);
  const payload = await api.post("/projects/chat/global", {
    message: buildAiPrompt(draftText, projects),
    chat_session_id: `work-log-${Date.now()}`,
    chat_mode: "system",
    chat_surface: "project-work-log",
    source_context: {
      source_type: "project_work_log_generation",
      allowed_project_names: projectNames,
      strict_source_only: true,
      disable_runtime_snapshot: true,
    },
    route_path: "/work-logs",
    route_title: "项目工作日志",
    history: [],
    temperature: 0.2,
    auto_use_tools: false,
    enabled_project_tool_names: [],
    answer_style: "concise",
    prefer_conclusion_first: true,
    provider_id: selectedModel.providerId || undefined,
    model_name: selectedModel.modelName || undefined,
  });
  return String(payload?.content || "").trim();
}

function stripProjectIds(text) {
  return String(text || "")
    .replace(/\n?项目ID[:：]?\s*\b\S+\b\s*\n?/g, "\n")
    .replace(/\bproj-[A-Za-z0-9_-]+\b/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function generateWorkLog() {
  if (!canGenerate.value || generating.value) return;
  generating.value = true;
  errorText.value = "";
  previewText.value = "";
  try {
    const projects = selectedProjects.value;
    const projectIds = selectedProjectIds.value;
    const projectPayloads = await Promise.all(
      projectIds.map(async (projectId) => {
        const project = projects.find((item) => item.id === projectId) || {
          id: projectId,
          name: projectId,
        };
        const [sessions, requirementRecords] = await Promise.all([
          fetchWorkSessions(projectId, form.startDate, form.endDate),
          fetchRequirementRecords(projectId, form.startDate, form.endDate).catch(() => []),
        ]);
        return { project, sessions, requirementRecords };
      }),
    );
    const draftText = buildDraftText(projectPayloads);
    const content = stripProjectIds(form.useAiSummary ? (await summarizeWithAi(draftText, projects)) || draftText : draftText);
    const projectNames = projects.map((project) => project?.name || project?.id).filter(Boolean);
    const selectedModel = parseModelOptionValue(selectedModelOptionValue.value);
    const recordPayload = {
      title: `${projectNames.length > 1 ? "多项目" : projectNames[0] || "项目"} ${resolveLabel(reportTypes, form.reportType)}`,
      report_type: form.reportType,
      template_key: form.template,
      template_label: resolveLabel(templates, form.template),
      start_date: form.startDate,
      end_date: form.endDate,
      project_ids: projectIds,
      project_names: projectNames,
      provider_id: selectedModel.providerId,
      model_name: selectedModel.modelName,
      content,
    };
    const saved = await api.post(
      `/projects/${encodeURIComponent(projectIds[0])}/work-logs`,
      recordPayload,
    );
    const savedRecord = normalizeRecord(saved?.item || {
      id: `work-log-${projectIds.join("-")}-${Date.now()}`,
      ...recordPayload,
      projectId: projectIds[0],
      projectName: projectNames.join("、"),
      projectLabel: projectNames.join("、"),
      templateLabel: recordPayload.template_label,
      createdAt: new Date().toISOString(),
    });
    records.value = [
      savedRecord,
      ...records.value.filter((item) => item.id !== savedRecord.id),
    ]
      .sort((a, b) =>
        String(b?.createdAt || b?.created_at || "").localeCompare(
          String(a?.createdAt || a?.created_at || ""),
        ),
      )
      .slice(0, 50);
    previewText.value = content;
    activeTab.value = "records";
  } catch (err) {
    errorText.value = err?.detail || err?.message || "生成工作日志失败";
  } finally {
    generating.value = false;
  }
}

function displayRecordTime(value) {
  return formatRelativeDateTime(value || new Date().toISOString());
}

async function copyText(text, successMessage = "内容已复制到剪贴板") {
  const content = String(text || "");
  if (!content.trim()) {
    ElMessage.warning("暂无可复制内容");
    return false;
  }
  try {
    await navigator.clipboard.writeText(content);
    ElMessage.success(successMessage);
    return true;
  } catch (err) {
    ElMessage.error(err?.message || "复制失败");
    return false;
  }
}

async function copyRecord(record) {
  const copied = await copyText(record?.content || "", "日志内容已复制到剪贴板");
  if (!copied) return;
  copiedRecordId.value = String(record?.id || "");
  window.setTimeout(() => {
    if (copiedRecordId.value === String(record?.id || "")) {
      copiedRecordId.value = "";
    }
  }, 1200);
}

async function deleteRecord(record) {
  const recordId = String(record?.id || "").trim();
  if (!recordId || deletingRecordId.value) return;
  deletingRecordId.value = recordId;
  errorText.value = "";
  try {
    await api.delete(`/projects/_global/work-logs/${encodeURIComponent(recordId)}`);
    records.value = records.value.filter((item) => item.id !== recordId);
  } catch (err) {
    errorText.value = err?.detail || err?.message || "删除日志记录失败";
  } finally {
    deletingRecordId.value = "";
  }
}
</script>

<style scoped>
.work-log-page {
  min-height: 100vh;
  padding: 22px;
  box-sizing: border-box;
  background: #f4f7fb;
  color: #0f172a;
}

.work-log-page__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 14px;
  padding: 18px 20px;
  border: 1px solid #d9e2ee;
  border-radius: 10px;
  background: #fff;
}

.work-log-page__eyebrow {
  margin: 0 0 6px;
  color: #0f766e;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.work-log-page h1 {
  margin: 0;
  font-size: 26px;
  line-height: 1.2;
}

.work-log-page p {
  max-width: 68ch;
  margin: 6px 0 0;
  color: #526071;
  font-size: 14px;
  line-height: 1.6;
}

.work-log-page__button,
.work-log-tabs__item,
.work-log-link {
  border: 0;
  cursor: pointer;
  font: inherit;
}

.work-log-page__button {
  min-height: 40px;
  padding: 0 18px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 800;
  white-space: nowrap;
}

.work-log-page__button--primary {
  background: #0f766e;
  color: #fff;
}

.work-log-page__button:disabled,
.work-log-link:disabled {
  cursor: not-allowed;
  opacity: 0.48;
}

.work-log-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.work-log-panel {
  border: 1px solid #dbe3ee;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.04);
}

.work-log-panel--settings {
  align-self: start;
  padding-bottom: 14px;
}

.work-log-panel__title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid #edf2f7;
  font-size: 14px;
  font-weight: 900;
}

.work-log-panel__title p {
  margin-top: 4px;
  font-weight: 500;
}

.work-log-link {
  background: transparent;
  color: #0f766e;
  font-size: 13px;
  font-weight: 800;
}

.work-log-link--danger {
  color: #b91c1c;
}

.work-log-field,
.work-log-check {
  display: grid;
  gap: 7px;
  margin: 12px 16px 0;
  color: #334155;
  font-size: 13px;
  font-weight: 800;
}

.work-log-field-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
  margin: 0 16px;
}

.work-log-field-grid .work-log-field {
  margin-right: 0;
  margin-left: 0;
}

.work-log-field__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.work-log-field__count {
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.work-log-field__hint {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
}

.work-log-field select,
.work-log-field input,
.work-log-field textarea {
  width: 100%;
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  box-sizing: border-box;
  background: #fff;
  color: #0f172a;
  font: inherit;
  font-weight: 500;
}

.work-log-field textarea {
  padding-top: 10px;
  resize: vertical;
}

.work-log-project-select {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 18px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  color: #0f172a;
  cursor: pointer;
  font: inherit;
  font-weight: 600;
  text-align: left;
}

.work-log-project-select:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.work-log-project-select span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-log-project-select .is-placeholder {
  color: #94a3b8;
}

.work-log-project-select__icon {
  color: #64748b;
  font-size: 16px;
  line-height: 1;
  text-align: center;
}

.work-log-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.38);
  box-sizing: border-box;
}

.work-log-modal {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  width: min(520px, 100%);
  max-height: min(680px, calc(100vh - 40px));
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 22px 70px rgba(15, 23, 42, 0.28);
  overflow: hidden;
}

.work-log-modal__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid #edf2f7;
}

.work-log-modal__head h2 {
  margin: 0;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.35;
}

.work-log-modal__head p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.work-log-modal__close {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 8px;
  background: #f1f5f9;
  color: #334155;
  cursor: pointer;
  font: inherit;
  font-size: 20px;
  line-height: 1;
}

.work-log-modal__toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 10px 20px;
  border-bottom: 1px solid #edf2f7;
}

.work-log-modal__body {
  min-height: 0;
  padding: 12px 20px;
  overflow: hidden;
}

.work-log-project-picker-list {
  display: grid;
  gap: 6px;
  max-height: 380px;
  overflow: auto;
  padding-right: 4px;
}

.work-log-modal__foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px 18px;
  border-top: 1px solid #edf2f7;
}

.work-log-page__button--ghost {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #334155;
}

.work-log-project-option {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 5px 7px;
  border-radius: 6px;
  color: #334155;
  font-weight: 700;
  cursor: pointer;
}

.work-log-project-option.is-selected {
  background: #ecfdf5;
  color: #0f766e;
}

.work-log-project-option input {
  width: 16px;
  height: 16px;
  margin: 0;
}

.work-log-project-option span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-log-project-empty {
  padding: 14px 8px;
  color: #64748b;
  font-weight: 700;
  text-align: center;
}

.work-log-field--inline {
  margin: 0;
}

.work-log-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
}

.work-log-error {
  margin: 12px 16px 0;
  padding: 9px 10px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  background: #fff1f2;
  color: #b91c1c;
  font-weight: 700;
}

.work-log-main {
  display: grid;
  grid-auto-rows: max-content;
  align-items: start;
  align-content: start;
  gap: 14px;
  min-width: 0;
}

.work-log-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  justify-self: start;
  align-self: start;
  width: 304px;
  height: 44px;
  gap: 4px;
  padding: 4px;
  border: 1px solid #dbe3ee;
  border-radius: 8px;
  background: #fff;
  box-sizing: border-box;
}

.work-log-tabs__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34px;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 34px;
  min-height: 0;
  padding: 0 12px;
  border-radius: 6px;
  background: transparent;
  color: #526071;
  font-size: 13px;
  font-weight: 800;
  box-sizing: border-box;
}

.work-log-tabs__item span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-log-tabs__item small {
  width: 34px;
  padding: 2px 7px;
  border-radius: 999px;
  box-sizing: border-box;
  background: #e2e8f0;
  color: #334155;
  font-size: 12px;
  text-align: center;
}

.work-log-tabs__item.is-active {
  background: #0f172a;
  color: #fff;
}

.work-log-template-list {
  display: grid;
  gap: 10px;
  padding: 16px;
}

.work-log-template {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fbfdff;
}

.work-log-template {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px;
  gap: 14px;
  padding: 14px 16px;
}

.work-log-template__content,
.work-log-template__editor {
  min-width: 0;
}

.work-log-template__editor {
  display: grid;
  gap: 12px;
}

.work-log-template__actions {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.work-log-template h2 {
  margin: 0;
  color: #0f172a;
  font-size: 16px;
  line-height: 1.35;
}

.work-log-template span {
  color: #0f766e;
  font-size: 13px;
  font-weight: 900;
  white-space: nowrap;
}

.work-log-empty {
  min-height: 180px;
  display: grid;
  place-items: center;
  padding: 36px 16px;
  color: #64748b;
  text-align: center;
}

.work-log-record-table {
  display: grid;
  padding: 16px;
  overflow-x: auto;
}

.work-log-record-table__head,
.work-log-record-row {
  min-width: 820px;
  display: grid;
  grid-template-columns: minmax(240px, 1.8fr) minmax(170px, 1.2fr) minmax(150px, 1fr) 150px 120px;
  align-items: center;
  gap: 14px;
}

.work-log-record-table__head {
  padding: 0 14px 10px;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.work-log-record-row {
  min-height: 56px;
  padding: 12px 14px;
  border-top: 1px solid #e2e8f0;
  color: #334155;
  font-size: 13px;
}

.work-log-record-row:first-of-type {
  border-top-color: #cbd5e1;
}

.work-log-record-row__title {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.work-log-record-row__title strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 14px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-log-record-row__title small {
  color: #64748b;
  font-size: 12px;
  line-height: 1.3;
}

.work-log-record-row > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-log-record-row__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  white-space: nowrap;
}

.work-log-preview pre {
  max-height: 520px;
  margin: 0;
  padding: 16px;
  overflow: auto;
  white-space: pre-wrap;
  color: #1e293b;
  font: 13px/1.7 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}

@media (max-width: 980px) {
  .work-log-page__head,
  .work-log-layout {
    display: grid;
    grid-template-columns: 1fr;
  }

  .work-log-page__head {
    padding: 16px;
  }

  .work-log-field-grid {
    grid-template-columns: 1fr;
  }

  .work-log-tabs {
    width: 100%;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .work-log-tabs__item {
    width: 100%;
  }

  .work-log-template {
    grid-template-columns: 1fr;
  }

  .work-log-template__actions {
    justify-content: flex-start;
  }

  .work-log-record-table {
    gap: 10px;
  }

  .work-log-record-table__head {
    display: none;
  }

  .work-log-record-row {
    min-width: 0;
    grid-template-columns: 1fr;
    gap: 8px;
    align-items: flex-start;
    padding: 14px;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background: #fbfdff;
  }

  .work-log-record-row:first-of-type {
    border-top-color: #e2e8f0;
  }

  .work-log-record-row > span {
    max-width: 100%;
  }

  .work-log-modal-backdrop {
    padding: 12px;
  }

  .work-log-modal {
    max-height: calc(100vh - 24px);
  }
}
</style>
