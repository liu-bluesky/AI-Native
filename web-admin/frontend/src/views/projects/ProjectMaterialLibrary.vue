<template>
  <div v-loading="loading" class="material-workbench">
    <section class="material-hero">
      <div class="material-hero__content">
        <div class="material-hero__eyebrow">Project Material Library</div>
        <h1 class="material-hero__title">项目素材库</h1>
        <p class="material-hero__desc">
          这里仅沉淀正式资产，不承载普通聊天文本。图片、分镜和视频都在同一个工作台里组织、回看和回跳来源。
        </p>
        <div class="material-hero__meta">
          <span>{{ project.name || projectId }}</span>
          <span>{{ getProjectTypeLabel(project.type) }}</span>
          <span>正式资产 {{ summary.total }}</span>
        </div>
      </div>
      <div class="material-hero__actions">
        <el-button class="material-hero__ghost" @click="goBackToProject">
          项目详情
        </el-button>
        <el-button
          class="material-hero__ghost"
          type="primary"
          plain
          @click="openProjectChat"
        >
          AI 对话
        </el-button>
        <el-button type="primary" @click="openCreateDialog">
          新增素材
        </el-button>
      </div>
      <div class="material-hero__stats">
        <article class="material-stat-card">
          <div class="material-stat-card__label">全部资产</div>
          <div class="material-stat-card__value">{{ summary.total }}</div>
          <div class="material-stat-card__hint">当前项目正式沉淀总量</div>
        </article>
        <article class="material-stat-card">
          <div class="material-stat-card__label">图片</div>
          <div class="material-stat-card__value">{{ summary.image_count }}</div>
          <div class="material-stat-card__hint">适合海报、KV、插画和参考图</div>
        </article>
        <article class="material-stat-card">
          <div class="material-stat-card__label">分镜</div>
          <div class="material-stat-card__value">
            {{ summary.storyboard_count }}
          </div>
          <div class="material-stat-card__hint">镜头规划和结构化 shot 方案</div>
        </article>
        <article class="material-stat-card">
          <div class="material-stat-card__label">视频</div>
          <div class="material-stat-card__value">{{ summary.video_count }}</div>
          <div class="material-stat-card__hint">最终可播放媒体与交付结果</div>
        </article>
      </div>
    </section>

    <section class="material-shell">
      <aside class="material-sidebar">
        <div class="material-panel material-panel--sidebar">
          <div class="material-panel__head">
            <div>
              <div class="material-panel__eyebrow">Navigator</div>
              <div class="material-panel__title">资产导航</div>
            </div>
          </div>

          <div class="material-search">
            <div class="material-search__label">检索</div>
            <el-input
              v-model="filters.query"
              clearable
              placeholder="按标题、来源消息、创建人搜索"
              @keyup.enter="fetchMaterials"
            />
            <div class="material-search__actions">
              <el-button type="primary" @click="fetchMaterials">搜索</el-button>
              <el-button @click="resetFilters">重置</el-button>
            </div>
          </div>

          <div class="material-sidebar__section">
            <div class="material-sidebar__section-title">一级分组</div>
            <button
              v-for="item in categoryOptions"
              :key="item.value"
              type="button"
              class="material-nav-item"
              :class="{ 'is-active': activeCategory === item.value }"
              @click="applyCategory(item.value)"
            >
              <span class="material-nav-item__label">{{ item.label }}</span>
              <span class="material-nav-item__count">{{ item.count }}</span>
            </button>
          </div>

          <div class="material-sidebar__section">
            <div class="material-sidebar__section-title">状态过滤</div>
            <div class="material-chip-group">
              <button
                v-for="item in statusOptions"
                :key="item.value"
                type="button"
                class="material-chip"
                :class="{ 'is-active': statusFilter === item.value }"
                @click="statusFilter = item.value"
              >
                {{ item.label }}
              </button>
            </div>
          </div>

          <div class="material-sidebar__section">
            <div class="material-sidebar__section-title">来源过滤</div>
            <div class="material-chip-group">
              <button
                v-for="item in sourceOptions"
                :key="item.value"
                type="button"
                class="material-chip"
                :class="{ 'is-active': sourceFilter === item.value }"
                @click="sourceFilter = item.value"
              >
                {{ item.label }}
              </button>
            </div>
          </div>

          <div class="material-sidebar__note">
            <div class="material-sidebar__note-title">当前设计原则</div>
            <p>
              聊天负责创作，素材库负责沉淀。所有资产都应能回到来源会话，不把临时讨论混进正式资产。
            </p>
          </div>
        </div>
      </aside>

      <div class="material-main">
        <div class="material-panel material-panel--content">
          <div class="material-toolbar">
            <div>
              <div class="material-toolbar__eyebrow">Workspace</div>
              <div class="material-toolbar__title">
                {{ currentCategoryLabel }}
              </div>
              <div class="material-toolbar__subtitle">
                当前展示 {{ displayMaterials.length }} 个资产
                <span v-if="statusFilter !== 'all'">
                  · 状态 {{ getStatusLabel(statusFilter) }}
                </span>
                <span v-if="sourceFilter !== 'all'">
                  · 来源 {{ getSourceFilterLabel(sourceFilter) }}
                </span>
              </div>
            </div>
            <div class="material-toolbar__actions">
              <el-radio-group v-model="viewMode" size="small">
                <el-radio-button label="board">看板</el-radio-button>
                <el-radio-button label="table">表格</el-radio-button>
              </el-radio-group>
              <el-button @click="refresh">刷新</el-button>
              <el-button type="primary" plain @click="openProjectChat">
                返回对话
              </el-button>
            </div>
          </div>

          <div v-if="viewMode === 'board'" class="material-board">
            <article
              v-for="row in displayMaterials"
              :key="row.id"
              class="material-card"
            >
              <div
                class="material-card__preview"
                :class="`is-${String(row.asset_type || 'image').trim() || 'image'}`"
                @click="row.preview_url ? openLink(row.preview_url) : undefined"
              >
                <img
                  v-if="row.asset_type === 'image' && row.preview_url"
                  :src="row.preview_url"
                  :alt="row.title || row.id"
                  class="material-card__image"
                />
                <div v-else class="material-card__placeholder">
                  <div class="material-card__placeholder-type">
                    {{
                      row.asset_type_label || getAssetTypeLabel(row.asset_type)
                    }}
                  </div>
                  <div class="material-card__placeholder-text">
                    {{ buildAssetPreviewText(row) }}
                  </div>
                </div>
                <div class="material-card__overlay">
                  <div class="material-card__tags">
                    <el-tag
                      size="small"
                      effect="dark"
                      :type="row.group_type === 'image' ? 'success' : 'warning'"
                    >
                      {{
                        row.group_type_label || getGroupTypeLabel(row.group_type)
                      }}
                    </el-tag>
                    <el-tag size="small" effect="dark">
                      {{
                        row.asset_type_label || getAssetTypeLabel(row.asset_type)
                      }}
                    </el-tag>
                    <el-tag
                      size="small"
                      effect="dark"
                      :type="getStatusTagType(row.status)"
                    >
                      {{ row.status_label || getStatusLabel(row.status) }}
                    </el-tag>
                  </div>
                  <div class="material-card__overlay-meta">
                    <span class="material-card__source-pill">
                      {{ formatSourceCompact(row) }}
                    </span>
                    <span class="material-card__updated-pill">
                      更新于 {{ formatDateTime(row.updated_at) }}
                    </span>
                  </div>
                </div>
              </div>

              <div class="material-card__body">
                <div class="material-card__title">
                  {{ row.title || row.id }}
                </div>
                <div class="material-card__summary">
                  {{ row.summary || buildAssetSummary(row) }}
                </div>

                <div class="material-card__facts">
                  <div class="material-card__fact">
                    <span class="material-card__fact-label">内容形态</span>
                    <span class="material-card__fact-value">
                      {{ buildAssetPreviewText(row) }}
                    </span>
                  </div>
                  <div class="material-card__fact">
                    <span class="material-card__fact-label">主内容</span>
                    <span class="material-card__fact-value">
                      {{ row.content_url ? "已提供" : "待补充" }}
                    </span>
                  </div>
                </div>
              </div>

              <div class="material-card__footer">
                <el-button
                  v-if="row.preview_url"
                  text
                  type="primary"
                  size="small"
                  @click="openLink(row.preview_url)"
                >
                  预览
                </el-button>
                <el-button
                  v-if="row.content_url"
                  text
                  type="success"
                  size="small"
                  @click="openLink(row.content_url)"
                >
                  内容
                </el-button>
                <el-button
                  v-if="hasSourceChat(row)"
                  text
                  type="primary"
                  size="small"
                  @click="openSourceChat(row)"
                >
                  查看来源
                </el-button>
                <el-button
                  text
                  type="warning"
                  size="small"
                  @click="openEditDialog(row)"
                >
                  编辑
                </el-button>
                <el-button
                  text
                  type="danger"
                  size="small"
                  @click="removeMaterial(row)"
                >
                  删除
                </el-button>
              </div>
            </article>
          </div>

          <div v-else class="material-table-shell">
            <el-table :data="displayMaterials" stripe>
              <el-table-column
                prop="title"
                label="标题"
                min-width="220"
                show-overflow-tooltip
              />
              <el-table-column label="分组" width="120">
                <template #default="{ row }">
                  <el-tag
                    :type="row.group_type === 'image' ? 'success' : 'warning'"
                  >
                    {{
                      row.group_type_label || getGroupTypeLabel(row.group_type)
                    }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="类型" width="110">
                <template #default="{ row }">
                  {{
                    row.asset_type_label || getAssetTypeLabel(row.asset_type)
                  }}
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="getStatusTagType(row.status)">
                    {{ row.status_label || getStatusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="created_by" label="创建人" width="120" />
              <el-table-column
                label="来源"
                min-width="220"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  <div class="source-cell">
                    <span>{{ formatSource(row) }}</span>
                    <el-button
                      v-if="hasSourceChat(row)"
                      text
                      type="primary"
                      size="small"
                      @click="openSourceChat(row)"
                    >
                      查看来源
                    </el-button>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="更新时间" width="180">
                <template #default="{ row }">
                  {{ formatDateTime(row.updated_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="260" fixed="right">
                <template #default="{ row }">
                  <el-button
                    v-if="row.preview_url"
                    text
                    type="primary"
                    size="small"
                    @click="openLink(row.preview_url)"
                  >
                    预览
                  </el-button>
                  <el-button
                    v-if="row.content_url"
                    text
                    type="success"
                    size="small"
                    @click="openLink(row.content_url)"
                  >
                    内容
                  </el-button>
                  <el-button
                    text
                    type="warning"
                    size="small"
                    @click="openEditDialog(row)"
                  >
                    编辑
                  </el-button>
                  <el-button
                    text
                    type="danger"
                    size="small"
                    @click="removeMaterial(row)"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <el-empty
            v-if="!displayMaterials.length && !loading"
            description="当前筛选条件下暂无素材"
          />
        </div>
      </div>
    </section>

    <el-dialog
      v-model="dialogVisible"
      :title="editingAssetId ? '编辑素材' : '新增素材'"
      width="720px"
      destroy-on-close
    >
      <ProjectMaterialFormFields
        :form="form"
        :label-width="120"
        :asset-type-options="assetTypeOptions"
        :mime-type-options="mimeTypeOptions"
        :show-asset-type="!editingAssetId"
        :show-status="Boolean(editingAssetId)"
        :context-note="
          editingAssetId
            ? '当前项目归属保持不变。来源关联由系统维护，这里只编辑素材内容本身。'
            : '当前页面已经锁定项目归属，无需再次选择项目。手动新增也不需要填写来源会话等系统字段。'
        "
      />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import ProjectMaterialFormFields from "@/components/ProjectMaterialFormFields.vue";
import api from "@/utils/api.js";
import { formatDateTime } from "@/utils/date.js";
import {
  MATERIAL_ASSET_TYPE_OPTIONS,
  MATERIAL_MIME_TYPE_OPTIONS,
} from "@/utils/project-materials.js";

const route = useRoute();
const router = useRouter();
const projectId = computed(() => String(route.query.project_id || "").trim());

const assetTypeOptions = MATERIAL_ASSET_TYPE_OPTIONS;
const mimeTypeOptions = MATERIAL_MIME_TYPE_OPTIONS;
const projectTypeOptions = [
  { value: "image", label: "图片项目" },
  { value: "storyboard_video", label: "分镜视频项目" },
  { value: "mixed", label: "综合项目" },
];

const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const editingAssetId = ref("");
const viewMode = ref("board");
const statusFilter = ref("all");
const sourceFilter = ref("all");
const project = ref({});
const materials = ref([]);
const summary = ref({
  total: 0,
  image_count: 0,
  storyboard_count: 0,
  video_count: 0,
});
const filters = ref({
  query: "",
  groupType: "",
  assetType: "",
});
const form = ref(buildEmptyForm());

function buildEmptyForm() {
  return {
    asset_type: "image",
    title: "",
    summary: "",
    preview_url: "",
    content_url: "",
    mime_type: "",
    status: "ready",
    structured_content_text: "",
    metadata_text: "",
  };
}

function normalizeProjectType(value) {
  const normalized = String(value || "").trim();
  return projectTypeOptions.some((item) => item.value === normalized)
    ? normalized
    : "mixed";
}

function getProjectTypeLabel(value) {
  return (
    projectTypeOptions.find(
      (item) => item.value === normalizeProjectType(value),
    )?.label || "综合项目"
  );
}

function getAssetTypeLabel(value) {
  return (
    assetTypeOptions.find((item) => item.value === String(value || "").trim())
      ?.label || "-"
  );
}

function getGroupTypeLabel(value) {
  return String(value || "").trim() === "image" ? "图片" : "分镜 / 视频";
}

function getStatusLabel(value) {
  const normalized = String(value || "").trim();
  if (normalized === "draft") return "草稿";
  if (normalized === "archived") return "归档";
  return "可用";
}

function getStatusTagType(value) {
  const normalized = String(value || "").trim();
  if (normalized === "draft") return "info";
  if (normalized === "archived") return "warning";
  return "success";
}

function getSourceFilterLabel(value) {
  if (value === "chat") return "聊天来源";
  if (value === "manual") return "手动录入";
  return "全部来源";
}

function openLink(url) {
  const normalized = String(url || "").trim();
  if (!normalized) return;
  window.open(normalized, "_blank", "noopener");
}

function formatSource(row) {
  const segments = [
    String(row.source_username || "").trim(),
    String(row.source_chat_session_id || "").trim(),
    String(row.source_message_id || "").trim(),
  ].filter(Boolean);
  return segments.join(" / ") || "-";
}

function formatSourceCompact(row) {
  const sourceUsername = String(row?.source_username || "").trim();
  if (hasSourceChat(row)) {
    return sourceUsername ? `${sourceUsername} · 对话来源` : "对话来源";
  }
  return sourceUsername ? `${sourceUsername} · 手动录入` : "手动录入";
}

function hasSourceChat(row) {
  return Boolean(String(row?.source_chat_session_id || "").trim());
}

function isManualAsset(row) {
  return !hasSourceChat(row);
}

function buildStructuredShotCount(row) {
  const structured = row?.structured_content;
  if (!structured || typeof structured !== "object") return 0;
  if (Array.isArray(structured.shots)) return structured.shots.length;
  const count = Number(
    structured.shot_count ?? structured.shotCount ?? structured.scene_count,
  );
  return Number.isFinite(count) && count > 0 ? count : 0;
}

function buildAssetPreviewText(row) {
  const assetType = String(row?.asset_type || "").trim();
  if (assetType === "storyboard") {
    const shotCount = buildStructuredShotCount(row);
    return shotCount ? `结构化分镜 · ${shotCount} 个镜头` : "结构化分镜方案";
  }
  if (assetType === "video") {
    return row?.mime_type ? `媒体文件 · ${row.mime_type}` : "视频交付结果";
  }
  return row?.mime_type ? `图片文件 · ${row.mime_type}` : "图片素材";
}

function buildAssetSummary(row) {
  const assetType = String(row?.asset_type || "").trim();
  if (assetType === "storyboard") {
    const shotCount = buildStructuredShotCount(row);
    return shotCount
      ? `已沉淀 ${shotCount} 个镜头节点，可继续驱动视频生成。`
      : "已沉淀结构化分镜内容，可继续用于镜头编排。";
  }
  if (assetType === "video") {
    return row?.content_url
      ? "已保存可播放媒体文件，适合复看、回交付和再次引用。"
      : "已沉淀视频资产信息，可继续补充媒体地址。";
  }
  return row?.preview_url
    ? "图片资产已进入项目素材库，可直接预览和回跳来源。"
    : "图片资产已沉淀，可继续补充预览地址和元数据。";
}

function safeParseObject(text, fieldLabel) {
  const source = String(text || "").trim();
  if (!source) return {};
  try {
    const parsed = JSON.parse(source);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
    throw new Error("not object");
  } catch {
    throw new Error(`${fieldLabel} 必须是合法 JSON 对象`);
  }
}

const activeCategory = computed(() => {
  const groupType = String(filters.value.groupType || "").trim();
  const assetType = String(filters.value.assetType || "").trim();
  if (groupType === "image" || assetType === "image") return "image";
  if (assetType === "storyboard") return "storyboard";
  if (assetType === "video") return "video";
  return "all";
});

const currentCategoryLabel = computed(() => {
  if (activeCategory.value === "image") return "图片资产";
  if (activeCategory.value === "storyboard") return "分镜资产";
  if (activeCategory.value === "video") return "视频资产";
  return "全部资产";
});

const categoryOptions = computed(() => [
  { value: "all", label: "全部资产", count: Number(summary.value.total || 0) },
  {
    value: "image",
    label: "图片",
    count: Number(summary.value.image_count || 0),
  },
  {
    value: "storyboard",
    label: "分镜",
    count: Number(summary.value.storyboard_count || 0),
  },
  {
    value: "video",
    label: "视频",
    count: Number(summary.value.video_count || 0),
  },
]);

const statusOptions = [
  { value: "all", label: "全部" },
  { value: "ready", label: "可用" },
  { value: "draft", label: "草稿" },
  { value: "archived", label: "归档" },
];

const sourceOptions = [
  { value: "all", label: "全部" },
  { value: "chat", label: "聊天来源" },
  { value: "manual", label: "手动录入" },
];

const displayMaterials = computed(() =>
  (materials.value || []).filter((row) => {
    const statusMatched =
      statusFilter.value === "all" || row?.status === statusFilter.value;
    const sourceMatched =
      sourceFilter.value === "all" ||
      (sourceFilter.value === "chat" && hasSourceChat(row)) ||
      (sourceFilter.value === "manual" && isManualAsset(row));
    return statusMatched && sourceMatched;
  }),
);

async function fetchProject() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    throw new Error("缺少项目 ID");
  }
  const data = await api.get(`/projects/${currentProjectId}`);
  project.value = {
    ...(data.project || {}),
    type: normalizeProjectType(data.project?.type),
  };
}

async function fetchMaterials() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    materials.value = [];
    summary.value = {
      total: 0,
      image_count: 0,
      storyboard_count: 0,
      video_count: 0,
    };
    return;
  }
  loading.value = true;
  try {
    const data = await api.get(`/projects/${currentProjectId}/materials`, {
      params: {
        query: filters.value.query,
        group_type: filters.value.groupType,
        asset_type: filters.value.assetType,
      },
    });
    materials.value = data.items || [];
    summary.value = data.summary || {
      total: 0,
      image_count: 0,
      storyboard_count: 0,
      video_count: 0,
    };
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载素材失败");
    materials.value = [];
  } finally {
    loading.value = false;
  }
}

async function refresh() {
  loading.value = true;
  try {
    await fetchProject();
    await fetchMaterials();
  } finally {
    loading.value = false;
  }
}

function applyCategory(category) {
  if (category === "image") {
    filters.value.groupType = "image";
    filters.value.assetType = "image";
  } else if (category === "storyboard") {
    filters.value.groupType = "storyboard_video";
    filters.value.assetType = "storyboard";
  } else if (category === "video") {
    filters.value.groupType = "storyboard_video";
    filters.value.assetType = "video";
  } else {
    filters.value.groupType = "";
    filters.value.assetType = "";
  }
  void fetchMaterials();
}

function resetFilters() {
  filters.value = { query: "", groupType: "", assetType: "" };
  statusFilter.value = "all";
  sourceFilter.value = "all";
  void fetchMaterials();
}

function goBackToProject() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  void router.push(`/projects/${currentProjectId}`);
}

function openProjectChat() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  void router.push({
    path: "/ai/chat",
    query: { project_id: currentProjectId },
  });
}

function openSourceChat(row) {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  const query = { project_id: currentProjectId };
  const chatSessionId = String(row?.source_chat_session_id || "").trim();
  const messageId = String(row?.source_message_id || "").trim();
  if (chatSessionId) {
    query.chat_session_id = chatSessionId;
  }
  if (messageId) {
    query.message_id = messageId;
  }
  void router.push({ path: "/ai/chat", query });
}

function openCreateDialog() {
  editingAssetId.value = "";
  form.value = buildEmptyForm();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingAssetId.value = String(row.id || "").trim();
  form.value = {
    asset_type: String(row.asset_type || "image").trim() || "image",
    title: String(row.title || ""),
    summary: String(row.summary || ""),
    preview_url: String(row.preview_url || ""),
    content_url: String(row.content_url || ""),
    mime_type: String(row.mime_type || ""),
    status: String(row.status || "ready") || "ready",
    structured_content_text: JSON.stringify(
      row.structured_content || {},
      null,
      2,
    ),
    metadata_text: JSON.stringify(row.metadata || {}, null, 2),
  };
  dialogVisible.value = true;
}

async function submitForm() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  const title = String(form.value.title || "").trim();
  if (!title) {
    ElMessage.warning("请输入素材标题");
    return;
  }
  let structuredContent;
  let metadata;
  try {
    structuredContent = safeParseObject(
      form.value.structured_content_text,
      "结构化内容",
    );
    metadata = safeParseObject(form.value.metadata_text, "元数据");
  } catch (err) {
    ElMessage.error(err.message || "JSON 格式错误");
    return;
  }
  const payload = {
    title,
    summary: form.value.summary,
    preview_url: form.value.preview_url,
    content_url: form.value.content_url,
    mime_type: form.value.mime_type,
    structured_content: structuredContent,
    metadata,
  };
  if (!editingAssetId.value) {
    payload.asset_type = form.value.asset_type;
  } else {
    payload.status = form.value.status;
  }
  saving.value = true;
  try {
    if (editingAssetId.value) {
      await api.patch(
        `/projects/${currentProjectId}/materials/${editingAssetId.value}`,
        payload,
      );
      ElMessage.success("素材已更新");
    } else {
      await api.post(`/projects/${currentProjectId}/materials`, payload);
      ElMessage.success("素材已创建");
    }
    dialogVisible.value = false;
    await fetchMaterials();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存素材失败");
  } finally {
    saving.value = false;
  }
}

async function removeMaterial(row) {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  await ElMessageBox.confirm(
    `确认删除素材「${row.title || row.id}」？`,
    "删除素材",
    { type: "warning" },
  );
  try {
    await api.delete(`/projects/${currentProjectId}/materials/${row.id}`);
    ElMessage.success("素材已删除");
    await fetchMaterials();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除素材失败");
  }
}

onMounted(() => {
  void refresh();
});
</script>

<style scoped>
.material-workbench {
  --material-ink: #18212f;
  --material-muted: #5d6b7f;
  --material-line: rgba(30, 41, 59, 0.1);
  --material-panel: rgba(255, 255, 255, 0.84);
  --material-shadow: 0 24px 60px rgba(15, 23, 42, 0.08);
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 8px 0 24px;
  background:
    radial-gradient(
      circle at top left,
      rgba(255, 250, 240, 0.95),
      transparent 26%
    ),
    radial-gradient(
      circle at top right,
      rgba(222, 242, 255, 0.72),
      transparent 28%
    ),
    linear-gradient(180deg, #f4f7fb 0%, #edf2f7 100%);
}

.material-hero {
  position: relative;
  overflow: hidden;
  padding: 28px;
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  background:
    linear-gradient(
      135deg,
      rgba(255, 248, 234, 0.96),
      rgba(239, 247, 255, 0.9)
    ),
    #ffffff;
  box-shadow: var(--material-shadow);
}

.material-hero::after {
  content: "";
  position: absolute;
  right: -40px;
  top: -56px;
  width: 220px;
  height: 220px;
  border-radius: 999px;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.86),
    rgba(255, 255, 255, 0)
  );
  pointer-events: none;
}

.material-hero__content {
  position: relative;
  z-index: 1;
  max-width: 760px;
}

.material-hero__eyebrow,
.material-panel__eyebrow,
.material-toolbar__eyebrow {
  color: #8a5c1f;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.material-hero__title {
  margin: 10px 0 0;
  color: var(--material-ink);
  font-size: 34px;
  line-height: 1.05;
}

.material-hero__desc {
  margin: 12px 0 0;
  max-width: 680px;
  color: var(--material-muted);
  font-size: 14px;
  line-height: 1.7;
}

.material-hero__meta {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.material-hero__meta span {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: #314055;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.material-hero__actions {
  position: relative;
  z-index: 1;
  margin-top: 22px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.material-hero__ghost {
  border-radius: 999px;
}

.material-hero__stats {
  position: relative;
  z-index: 1;
  margin-top: 24px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.material-stat-card {
  padding: 16px 18px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(148, 163, 184, 0.14);
  backdrop-filter: blur(12px);
}

.material-stat-card__label {
  color: #75829a;
  font-size: 12px;
}

.material-stat-card__value {
  margin-top: 8px;
  color: var(--material-ink);
  font-size: 28px;
  font-weight: 700;
}

.material-stat-card__hint {
  margin-top: 8px;
  color: var(--material-muted);
  font-size: 12px;
  line-height: 1.6;
}

.material-shell {
  display: grid;
  grid-template-columns: 292px minmax(0, 1fr);
  gap: 18px;
  min-height: 0;
}

.material-sidebar,
.material-main {
  min-width: 0;
}

.material-panel {
  border-radius: 26px;
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: var(--material-panel);
  box-shadow: var(--material-shadow);
  backdrop-filter: blur(14px);
}

.material-panel--sidebar {
  padding: 22px 18px 18px;
  position: sticky;
  top: 18px;
}

.material-panel--content {
  padding: 20px;
}

.material-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.material-panel__title,
.material-toolbar__title {
  margin-top: 6px;
  color: var(--material-ink);
  font-size: 22px;
  font-weight: 700;
}

.material-search {
  margin-top: 18px;
  padding: 14px;
  border-radius: 18px;
  background: rgba(246, 248, 252, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.12);
}

.material-search__label,
.material-sidebar__section-title,
.material-sidebar__note-title {
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.material-search__actions {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}

.material-sidebar__section {
  margin-top: 18px;
}

.material-nav-item {
  width: 100%;
  margin-top: 8px;
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.material-nav-item:hover,
.material-nav-item.is-active {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.24);
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.08);
}

.material-nav-item.is-active {
  background: linear-gradient(
    135deg,
    rgba(255, 247, 237, 0.96),
    rgba(239, 246, 255, 0.92)
  );
}

.material-nav-item__label {
  color: var(--material-ink);
  font-size: 13px;
  font-weight: 600;
}

.material-nav-item__count {
  color: #6b7280;
  font-size: 12px;
}

.material-chip-group {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.material-chip {
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.72);
  color: #475569;
  font-size: 12px;
  cursor: pointer;
}

.material-chip.is-active {
  background: #18212f;
  border-color: #18212f;
  color: #ffffff;
}

.material-sidebar__note {
  margin-top: 18px;
  padding: 14px;
  border-radius: 18px;
  background: linear-gradient(
    180deg,
    rgba(255, 250, 240, 0.92),
    rgba(255, 255, 255, 0.86)
  );
  border: 1px solid rgba(250, 204, 21, 0.16);
}

.material-sidebar__note p {
  margin: 8px 0 0;
  color: var(--material-muted);
  font-size: 12px;
  line-height: 1.7;
}

.material-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 18px;
}

.material-toolbar__subtitle {
  margin-top: 8px;
  color: var(--material-muted);
  font-size: 13px;
}

.material-toolbar__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.material-board {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 18px;
}

.material-card {
  overflow: hidden;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(148, 163, 184, 0.14);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.material-card:hover {
  transform: translateY(-3px);
  border-color: rgba(59, 130, 246, 0.22);
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.1);
}

.material-card__preview {
  min-height: 214px;
  aspect-ratio: 16 / 10;
  position: relative;
  overflow: hidden;
  background:
    linear-gradient(
      135deg,
      rgba(230, 244, 255, 0.96),
      rgba(255, 247, 237, 0.98)
    ),
    #f8fafc;
}

.material-card__preview.is-image {
  cursor: zoom-in;
}

.material-card__preview::after {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.08), transparent 28%),
    linear-gradient(0deg, rgba(15, 23, 42, 0.54), transparent 42%);
  pointer-events: none;
}

.material-card__preview.is-storyboard {
  background:
    linear-gradient(
      135deg,
      rgba(255, 248, 235, 0.98),
      rgba(255, 241, 242, 0.94)
    ),
    #fffaf5;
}

.material-card__preview.is-video {
  background:
    linear-gradient(
      135deg,
      rgba(226, 232, 240, 0.98),
      rgba(219, 234, 254, 0.92)
    ),
    #f8fafc;
}

.material-card__image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.material-card__placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 20px;
  color: var(--material-ink);
}

.material-card__placeholder-type {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #64748b;
}

.material-card__placeholder-text {
  margin-top: 10px;
  max-width: 240px;
  font-size: 20px;
  line-height: 1.35;
  font-weight: 700;
}

.material-card__overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 14px;
}

.material-card__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px 18px 14px;
}

.material-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
}

.material-card__overlay-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.material-card__source-pill,
.material-card__updated-pill {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.52);
  color: #f8fafc;
  font-size: 12px;
  line-height: 1.4;
  backdrop-filter: blur(12px);
}

.material-card__source-pill {
  font-weight: 600;
}

.material-card__title {
  color: var(--material-ink);
  font-size: 17px;
  font-weight: 700;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.material-card__summary {
  color: var(--material-muted);
  font-size: 13px;
  line-height: 1.7;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  overflow: hidden;
}

.material-card__facts {
  margin-top: auto;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.material-card__fact {
  min-width: 0;
  padding: 11px 12px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), #ffffff);
  border: 1px solid rgba(226, 232, 240, 0.92);
}

.material-card__fact-label {
  display: block;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
}

.material-card__fact-value {
  display: block;
  margin-top: 5px;
  color: #1e293b;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
  word-break: break-word;
}

.material-card__footer {
  padding: 12px 14px 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  border-top: 1px solid rgba(226, 232, 240, 0.84);
  background: rgba(248, 250, 252, 0.84);
}

.material-card__footer :deep(.el-button + .el-button) {
  margin-left: 0;
}

.material-table-shell {
  overflow: hidden;
  border-radius: 18px;
}

.source-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

@media (max-width: 1100px) {
  .material-hero__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .material-shell {
    grid-template-columns: 1fr;
  }

  .material-panel--sidebar {
    position: static;
  }
}

@media (max-width: 760px) {
  .material-workbench {
    gap: 14px;
    padding-bottom: 18px;
  }

  .material-hero {
    padding: 20px;
    border-radius: 22px;
  }

  .material-hero__title {
    font-size: 28px;
  }

  .material-hero__stats {
    grid-template-columns: 1fr;
  }

  .material-toolbar {
    flex-direction: column;
  }

  .material-toolbar__actions {
    width: 100%;
    justify-content: flex-start;
  }

  .material-board {
    grid-template-columns: 1fr;
  }

  .material-card__facts {
    grid-template-columns: 1fr;
  }
}
</style>
