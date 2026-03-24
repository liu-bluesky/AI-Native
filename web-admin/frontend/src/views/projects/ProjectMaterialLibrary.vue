<template>
  <div v-loading="loading" class="material-workbench">
    <section class="material-context-bar">
      <div class="material-context-bar__main">
        <div class="material-context-bar__eyebrow">AI Operating System</div>
        <h1 class="material-context-bar__title">素材库</h1>
        <p class="material-context-bar__summary">
          在同一项目里继续整理图片、分镜、视频和音频资产。
        </p>
        <div class="material-context-bar__meta">
          <span>{{ project.name || projectId || "未选择项目" }}</span>
          <span>{{ getProjectTypeLabel(project.type) }}</span>
          <span>正式资产 {{ summary.total }}</span>
        </div>
        <div class="material-context-bar__signals" aria-label="素材概览">
          <span>图片 {{ summary.image_count }}</span>
          <span>分镜 {{ summary.storyboard_count }}</span>
          <span>视频 {{ summary.video_count }}</span>
          <span>音频 {{ summary.audio_count }}</span>
        </div>
      </div>

      <div class="material-context-bar__actions">
        <el-button
          size="small"
          plain
          class="material-context-bar__action-button"
          @click="goBackToProject"
        >
          项目详情
        </el-button>
        <el-button
          size="small"
          plain
          class="material-context-bar__action-button"
          @click="openProjectChat"
        >
          AI 对话
        </el-button>
        <el-button
          type="primary"
          class="material-context-bar__primary"
          @click="openCreateDialog"
        >
          新增素材
        </el-button>
      </div>
    </section>

    <section class="material-filter-bar">
      <div class="material-filter-bar__top">
        <div class="material-filter-bar__search">
          <el-input
            v-model="filters.query"
            clearable
            placeholder="按标题、来源消息、创建人搜索"
            @keyup.enter="fetchMaterials"
          />
        </div>

        <div class="material-filter-bar__actions">
          <el-radio-group v-model="viewMode" size="small">
            <el-radio-button label="board">看板</el-radio-button>
            <el-radio-button label="table">表格</el-radio-button>
          </el-radio-group>
          <el-button @click="fetchMaterials">搜索</el-button>
          <el-button @click="resetFilters">重置</el-button>
          <el-button @click="refresh">刷新</el-button>
        </div>
      </div>

      <div class="material-filter-bar__groups">
        <div class="material-filter-group">
          <span class="material-filter-group__label">分类</span>
          <div class="material-chip-group">
            <button
              v-for="item in categoryOptions"
              :key="item.value"
              type="button"
              class="material-chip"
              :class="{ 'is-active': activeCategory === item.value }"
              @click="applyCategory(item.value)"
            >
              {{ item.label }}
              <span class="material-chip__count">{{ item.count }}</span>
            </button>
          </div>
        </div>

        <div class="material-filter-group">
          <span class="material-filter-group__label">状态</span>
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

        <div class="material-filter-group">
          <span class="material-filter-group__label">来源</span>
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
      </div>
    </section>

    <section class="material-content-surface">
      <header class="material-content-head">
        <div>
          <div class="material-content-head__eyebrow">Current View</div>
          <div class="material-content-head__title">
            {{ currentCategoryLabel }}
          </div>
          <div class="material-content-head__subtitle">
            当前展示 {{ displayMaterials.length }} 个资产
            <span v-if="statusFilter !== 'all'">
              · 状态 {{ getStatusLabel(statusFilter) }}
            </span>
            <span v-if="sourceFilter !== 'all'">
              · 来源 {{ getSourceFilterLabel(sourceFilter) }}
            </span>
          </div>
        </div>

        <div class="material-content-head__toolbar">
          <span class="material-content-head__mode">
            {{ viewMode === "board" ? "看板浏览" : "表格浏览" }}
          </span>
        </div>
      </header>

      <section
        v-if="focusAssetNotice"
        class="material-focus-banner"
        :class="`is-${focusAssetNotice.tone}`"
      >
        <div class="material-focus-banner__body">
          <div class="material-focus-banner__title">
            {{ focusAssetNotice.title }}
          </div>
          <div class="material-focus-banner__message">
            {{ focusAssetNotice.message }}
          </div>
        </div>
        <div class="material-focus-banner__actions">
          <el-button
            v-if="focusAssetNotice.action === 'reset-filters'"
            size="small"
            @click="resetFiltersForFocusedAsset"
          >
            清空筛选
          </el-button>
          <el-button
            v-else-if="focusAssetNotice.action === 'reveal'"
            size="small"
            @click="revealFocusedAsset"
          >
            显示素材
          </el-button>
          <el-button
            v-else-if="focusAssetNotice.action === 'create-material'"
            size="small"
            type="primary"
            @click="openCreateDialog"
          >
            新增素材
          </el-button>
          <el-button size="small" text @click="clearFocusedAssetRoute">
            清除定位
          </el-button>
        </div>
      </section>

      <div v-if="viewMode === 'board'" class="material-board">
        <article
          v-for="row in displayMaterials"
          :key="row.id"
          class="material-card"
          :data-material-asset-id="row.id"
          :class="{ 'is-highlighted': row.id === highlightedAssetId }"
        >
          <div
            class="material-card__preview"
            :class="[
              `is-${normalizeAssetType(row.asset_type, row)}`,
              { 'is-clickable': canOpenMediaPreview(row) },
            ]"
            @click="handleMaterialPreviewClick(row)"
          >
            <template v-if="normalizeAssetType(row.asset_type, row) === 'video'">
              <img
                v-if="resolveBoardVideoPosterUrl(row)"
                :src="resolveBoardVideoPosterUrl(row)"
                :alt="row.title || row.id"
                class="material-card__image"
              />
            </template>
            <div
              v-else-if="normalizeAssetType(row.asset_type, row) === 'audio'"
              class="material-card__audio-preview"
              @click.stop
              @mousedown.stop
              @pointerdown.stop
            >
              <div class="material-card__audio-icon">♪</div>
              <div class="material-card__audio-copy">
                <strong>{{ row.title || row.id }}</strong>
                <span>{{ row.mime_type || "音频素材" }}</span>
              </div>
              <audio
                v-if="resolveAudioUrl(row)"
                class="material-card__audio-player"
                :src="resolveAudioUrl(row)"
                controls
                preload="metadata"
                @click.stop
                @mousedown.stop
                @pointerdown.stop
              />
            </div>
            <img
              v-else-if="resolveImagePreviewUrl(row)"
              :src="resolveImagePreviewUrl(row)"
              :alt="row.title || row.id"
              class="material-card__image"
            />
            <div v-else class="material-card__placeholder">
              <div class="material-card__placeholder-type">
                {{
                  row.asset_type_label ||
                  getAssetTypeLabel(normalizeAssetType(row.asset_type, row))
                }}
              </div>
              <div class="material-card__placeholder-text">
                {{ buildAssetPreviewText(row) }}
              </div>
            </div>
          </div>

          <div class="material-card__body">
            <div class="material-card__head">
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
                    row.asset_type_label ||
                    getAssetTypeLabel(normalizeAssetType(row.asset_type, row))
                  }}
                </el-tag>
                <el-tag
                  size="small"
                  effect="dark"
                  :type="getStatusTagType(row.status)"
                >
                  {{ row.status_label || getStatusLabel(row.status) }}
                </el-tag>
                <el-tag
                  v-if="isStudioExportAsset(row)"
                  size="small"
                  effect="plain"
                  :type="isStudioExportFinal(row) ? 'success' : 'danger'"
                >
                  {{ isStudioExportFinal(row) ? "短片正式导出" : "短片导出预览" }}
                </el-tag>
                <el-tag
                  v-if="resolveRequestedExportResolution(row)"
                  size="small"
                  effect="plain"
                >
                  {{ resolveRequestedExportResolution(row) }}
                </el-tag>
              </div>
              <div class="material-card__meta">
                <span class="material-card__source-pill">
                  {{ formatSourceCompact(row) }}
                </span>
                <span class="material-card__updated-pill">
                  更新于 {{ formatDateTime(row.updated_at) }}
                </span>
              </div>
            </div>

            <div class="material-card__title">{{ row.title || row.id }}</div>
            <div class="material-card__summary">
              {{ buildMaterialCardSummary(row) }}
            </div>
          </div>

          <div class="material-card__footer">
            <el-button
              v-if="canOpenMediaPreview(row)"
              text
              type="primary"
              size="small"
              @click="openMaterialPreview(row)"
            >
              预览
            </el-button>
            <el-button
              v-else-if="resolvePreviewActionUrl(row)"
              text
              type="success"
              size="small"
              @click="openLink(resolvePreviewActionUrl(row))"
            >
              查看内容
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
                {{ row.group_type_label || getGroupTypeLabel(row.group_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="110">
            <template #default="{ row }">
              {{ row.asset_type_label || getAssetTypeLabel(row.asset_type) }}
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
          <el-table-column label="来源" min-width="220" show-overflow-tooltip>
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
                v-if="canOpenMediaPreview(row)"
                text
                type="primary"
                size="small"
                @click="openMaterialPreview(row)"
              >
                预览
              </el-button>
              <el-button
                v-else-if="resolvePreviewActionUrl(row)"
                text
                type="success"
                size="small"
                @click="openLink(resolvePreviewActionUrl(row))"
              >
                查看内容
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

      <div
        v-if="!displayMaterials.length && !loading"
        class="material-empty-state"
      >
        <el-empty description="当前筛选条件下暂无素材" />
      </div>
    </section>

    <el-dialog
      v-model="previewDialogVisible"
      class="material-preview-dialog"
      width="min(1080px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div class="material-preview-dialog__head">
          <div class="material-preview-dialog__title">
            {{ previewDialogTitle }}
          </div>
          <div class="material-preview-dialog__meta">
            {{ previewDialogMeta }}
          </div>
        </div>
      </template>
      <div class="material-preview-dialog__body">
        <video
          v-if="previewDialogType === 'video' && previewDialogUrl"
          class="material-preview-dialog__video"
          :src="previewDialogUrl"
          :poster="previewDialogPosterUrl"
          controls
          autoplay
          preload="metadata"
          playsinline
        />
        <audio
          v-else-if="previewDialogType === 'audio' && previewDialogUrl"
          class="material-preview-dialog__audio"
          :src="previewDialogUrl"
          controls
          autoplay
          preload="metadata"
        />
        <img
          v-else-if="previewDialogType === 'image' && previewDialogUrl"
          :src="previewDialogUrl"
          :alt="previewDialogTitle"
          class="material-preview-dialog__image"
        />
        <el-empty
          v-else
          description="当前素材暂不支持页内预览"
          :image-size="64"
        />
      </div>
      <template #footer>
        <el-button @click="previewDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="dialogVisible"
      :title="editingAssetId ? '编辑素材' : '新增素材'"
      width="720px"
      destroy-on-close
    >
      <input
        ref="coverUploadInputRef"
        class="material-upload-panel__input"
        type="file"
        accept="image/*"
        @change="handleCoverFileChange"
      />
      <div v-if="!editingAssetId" class="material-upload-panel">
        <input
          ref="uploadInputRef"
          class="material-upload-panel__input"
          type="file"
          :accept="uploadAccept"
          @change="handleUploadFileChange"
        />
        <div class="material-upload-panel__surface">
          <div class="material-upload-panel__copy">
            <div class="material-upload-panel__title">上传文件</div>
            <div class="material-upload-panel__text">
              新增素材请直接上传文件，不再手动填写素材地址。
            </div>
            <div class="material-upload-panel__meta">
              <span>{{ selectedUploadFileName || "未选择文件" }}</span>
              <span>{{ uploadAcceptLabel }}</span>
            </div>
          </div>
          <div class="material-upload-panel__actions">
            <el-button plain @click="triggerUploadPicker">
              {{ selectedUploadFileName ? "重新选择" : "选择文件" }}
            </el-button>
            <el-button
              v-if="selectedUploadFileName"
              text
              type="warning"
              @click="clearSelectedUploadFile"
            >
              清空
            </el-button>
          </div>
          <div v-if="uploadPreviewUrl" class="material-upload-panel__preview">
            <video
              v-if="uploadPreviewKind === 'video'"
              :src="uploadPreviewUrl"
              class="material-upload-panel__preview-video"
              controls
              preload="metadata"
              playsinline
              muted
            />
            <audio
              v-else-if="uploadPreviewKind === 'audio'"
              :src="uploadPreviewUrl"
              class="material-upload-panel__preview-audio"
              controls
              preload="metadata"
            />
            <img
              v-else
              :src="uploadPreviewUrl"
              :alt="form.title || selectedUploadFileName || '上传预览图'"
              class="material-upload-panel__preview-image"
            />
          </div>
        </div>
      </div>
      <div v-if="showVideoCoverPanel" class="material-video-cover-panel">
        <div class="material-video-cover-panel__copy">
          <div class="material-upload-panel__title">视频封面</div>
          <div class="material-upload-panel__text">
            {{
              editingAssetId
                ? "可上传新封面替换当前封面；不上传则继续保留已保存封面。"
                : "系统会自动抽取默认封面；你也可以在这里手动上传封面，优先覆盖自动结果。"
            }}
          </div>
          <div class="material-upload-panel__meta">
            <span>{{ coverSelectionLabel }}</span>
            <span>{{ coverSelectionSourceLabel }}</span>
          </div>
        </div>
        <div class="material-upload-panel__actions">
          <el-button plain @click="triggerCoverPicker">
            {{ activeCoverPreviewUrl ? "更换封面" : "上传封面" }}
          </el-button>
          <el-button
            v-if="canClearCoverSelection"
            text
            type="warning"
            @click="clearCoverSelection"
          >
            {{ manualCoverFile ? "移除手动封面" : "清空默认封面" }}
          </el-button>
          <span v-if="!editingAssetId" class="material-video-cover-panel__hint">
            创建时可直接上传封面，未上传时默认使用自动抽帧。
          </span>
        </div>
        <div
          v-if="activeCoverPreviewUrl"
          class="material-upload-panel__preview material-upload-panel__preview--cover"
        >
          <img
            :src="activeCoverPreviewUrl"
            :alt="form.title || '视频封面预览'"
            class="material-upload-panel__preview-image"
          />
        </div>
      </div>
      <ProjectMaterialFormFields
        :form="form"
        :label-width="120"
        :asset-type-options="assetTypeOptions"
        :mime-type-options="mimeTypeOptions"
        :show-asset-type="!editingAssetId"
        :show-link-fields="false"
        :show-status="Boolean(editingAssetId)"
        :context-note="
          editingAssetId
            ? '当前项目归属保持不变。来源关联由系统维护，这里只编辑素材内容本身。'
            : '当前页面已经锁定项目归属。新增素材会先上传文件，再补标题、摘要和结构化信息。'
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import ProjectMaterialFormFields from "@/components/ProjectMaterialFormFields.vue";
import api from "@/utils/api.js";
import { buildChatSettingsRoute } from "@/utils/chat-settings-route.js";
import { formatDateTime } from "@/utils/date.js";
import {
  inferMaterialAssetTypeFromFile,
  MATERIAL_ASSET_TYPE_OPTIONS,
  MATERIAL_MIME_TYPE_OPTIONS,
  readVideoDurationFromFile,
  readVideoDurationFromUrl,
  resolveMaterialResourceUrl,
} from "@/utils/project-materials.js";

const route = useRoute();
const router = useRouter();
const projectId = computed(() => String(route.query.project_id || "").trim());
const focusAssetId = computed(() => String(route.query.focus_asset_id || "").trim());

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
const previewDialogVisible = ref(false);
const previewTarget = ref(null);
const highlightedAssetId = ref("");
const lastAutoFocusedAssetId = ref("");
const editingAssetId = ref("");
const uploadInputRef = ref(null);
const coverUploadInputRef = ref(null);
const selectedUploadFile = ref(null);
const selectedUploadFileName = ref("");
const uploadPreviewUrl = ref("");
const uploadPreviewKind = ref("");
const manualCoverFile = ref(null);
const manualCoverFileName = ref("");
const manualCoverPreviewUrl = ref("");
const autoCoverFile = ref(null);
const autoCoverFileName = ref("");
const autoCoverPreviewUrl = ref("");
const persistedCoverPreviewUrl = ref("");
const generatingVideoCover = ref(false);
const videoCoverGenerationToken = ref(0);
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
  audio_count: 0,
});
const filters = ref({
  query: "",
  groupType: "",
  assetType: "",
});
const form = ref(buildEmptyForm());
const resolvingVideoDurationIds = new Set();

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

const uploadAccept = computed(() => {
  const assetType = String(form.value?.asset_type || "image").trim();
  if (assetType === "video") return "video/*";
  if (assetType === "audio") return "audio/*,.mp3,.wav,.m4a,.aac,.ogg,.flac";
  if (assetType === "storyboard") {
    return ".json,.txt,.pdf,.doc,.docx,image/*";
  }
  return "image/*";
});

const uploadAcceptLabel = computed(() => {
  const assetType = String(form.value?.asset_type || "image").trim();
  if (assetType === "video") return "支持视频文件";
  if (assetType === "audio") return "支持音频文件";
  if (assetType === "storyboard") return "支持文档、JSON 或参考图片";
  return "支持图片文件";
});

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
  const normalized = normalizeRenderableUrl(url);
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
  if (isStudioExportAsset(row)) {
    const label = isStudioExportFinal(row) ? "正式导出" : "短片导出";
    return sourceUsername ? `${sourceUsername} · ${label}` : label;
  }
  if (hasSourceChat(row)) {
    return sourceUsername ? `${sourceUsername} · 对话来源` : "对话来源";
  }
  return sourceUsername ? `${sourceUsername} · 手动录入` : "手动录入";
}

function isStudioExportPreview(row) {
  return String(row?.metadata?.artifact_source || "").trim() === "studio-export-preview";
}

function isStudioExportFinal(row) {
  return String(row?.metadata?.artifact_source || "").trim() === "studio-export-final";
}

function isStudioExportAsset(row) {
  return isStudioExportPreview(row) || isStudioExportFinal(row);
}

function resolveRequestedExportResolution(row) {
  const metadata = row?.metadata;
  const candidates = [
    metadata?.requested_export_resolution,
    metadata?.export_resolution,
    metadata?.resolution,
  ];
  for (const candidate of candidates) {
    const normalized = String(candidate || "").trim();
    if (normalized) return normalized;
  }
  return "";
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
  if (
    isUnsupportedLocalFileUrl(row?.preview_url) ||
    isUnsupportedLocalFileUrl(row?.content_url)
  ) {
    return "本地文件路径需先上传或转成 http(s) 地址";
  }
  const assetType = normalizeAssetType(row?.asset_type, row);
  if (assetType === "storyboard") {
    const shotCount = buildStructuredShotCount(row);
    return shotCount ? `结构化分镜 · ${shotCount} 个镜头` : "结构化分镜方案";
  }
  if (assetType === "video") {
    if (isStudioExportAsset(row)) {
      const resolution = resolveRequestedExportResolution(row);
      const segments = [isStudioExportFinal(row) ? "短片正式导出" : "短片导出预览"];
      if (resolution) segments.push(resolution);
      if (row?.mime_type) segments.push(row.mime_type);
      return segments.join(" · ");
    }
    return row?.mime_type ? `媒体文件 · ${row.mime_type}` : "视频交付结果";
  }
  if (assetType === "audio") {
    return row?.mime_type ? `音频文件 · ${row.mime_type}` : "音频素材";
  }
  return row?.mime_type ? `图片文件 · ${row.mime_type}` : "图片素材";
}

function buildAssetSummary(row) {
  const assetType = normalizeAssetType(row?.asset_type, row);
  if (assetType === "storyboard") {
    const shotCount = buildStructuredShotCount(row);
    return shotCount
      ? `已沉淀 ${shotCount} 个镜头节点，可继续驱动视频生成。`
      : "已沉淀结构化分镜内容，可继续用于镜头编排。";
  }
  if (assetType === "video") {
    if (isStudioExportAsset(row)) {
      const resolution = resolveRequestedExportResolution(row);
      const subject = isStudioExportFinal(row) ? "短片正式导出结果" : "短片工作台导出预览";
      return resolution
        ? `${subject}已入库，可按 ${resolution} 配置继续回看和复用。`
        : `${subject}已入库，可继续回看和复用。`;
    }
    return row?.content_url
      ? "已保存可播放媒体文件，适合复看、回交付和再次引用。"
      : "已沉淀视频资产信息，可继续补充媒体地址。";
  }
  if (assetType === "audio") {
    return row?.content_url
      ? "已保存可播放音频文件，适合试听、配音和导出复用。"
      : "已沉淀音频资产信息，可继续补充音频地址。";
  }
  return row?.preview_url
    ? "图片资产已进入项目素材库，可直接预览和回跳来源。"
    : "图片资产已沉淀，可继续补充预览地址和元数据。";
}

function buildMaterialCardSummary(row) {
  const assetType = normalizeAssetType(row?.asset_type, row);
  if (assetType === "video" && isStudioExportAsset(row)) {
    const resolution = resolveRequestedExportResolution(row);
    const subject = isStudioExportFinal(row) ? "正式导出结果" : "导出预览";
    return resolution
      ? `${resolution} ${subject}，可重新加入时间线继续编排`
      : `短片${subject}，可重新加入时间线继续编排`;
  }
  const source = String(row?.summary || "")
    .replace(/\s+/g, " ")
    .trim();
  if (source) {
    return source.slice(0, 46) + (source.length > 46 ? "..." : "");
  }
  if (assetType === "storyboard") {
    const shotCount = buildStructuredShotCount(row);
    return shotCount ? `${shotCount} 个镜头节点` : "结构化分镜内容";
  }
  if (assetType === "video") {
    return row?.content_url ? "可直接预览的视频资产" : "待补充视频地址";
  }
  if (assetType === "audio") {
    return row?.content_url ? "可直接试听的音频素材" : "待补充音频地址";
  }
  return resolveImagePreviewUrl(row) ? "可直接预览的图片素材" : "待补充预览图";
}

function normalizeAssetType(value, row = null) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (
    normalized === "video" ||
    (row &&
      (hasVideoMime(row) ||
        isLikelyVideoUrl(row?.content_url) ||
        isLikelyVideoUrl(row?.preview_url)))
  ) {
    return "video";
  }
  if (
    normalized === "audio" ||
    (row &&
      (hasAudioMime(row) ||
        isLikelyAudioUrl(row?.content_url) ||
        isLikelyAudioUrl(row?.preview_url)))
  ) {
    return "audio";
  }
  if (normalized === "storyboard") return "storyboard";
  return "image";
}

function handleMaterialPreviewClick(row) {
  if (normalizeAssetType(row?.asset_type, row) === "audio") return;
  openMaterialPreview(row);
}

function isUnsupportedLocalFileUrl(url) {
  return String(url || "")
    .trim()
    .toLowerCase()
    .startsWith("file://");
}

function normalizeRenderableUrl(url) {
  const normalized = resolveMaterialResourceUrl(url);
  if (!normalized || isUnsupportedLocalFileUrl(normalized)) {
    return "";
  }
  return normalized;
}

function revokeObjectUrl(url) {
  if (url && url.startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}

function revokeUploadPreviewUrl() {
  revokeObjectUrl(uploadPreviewUrl.value);
  uploadPreviewUrl.value = "";
  uploadPreviewKind.value = "";
}

function clearSelectedUploadFile() {
  selectedUploadFile.value = null;
  selectedUploadFileName.value = "";
  revokeUploadPreviewUrl();
}

function clearManualCoverSelection() {
  manualCoverFile.value = null;
  manualCoverFileName.value = "";
  revokeObjectUrl(manualCoverPreviewUrl.value);
  manualCoverPreviewUrl.value = "";
}

function clearAutoCoverSelection() {
  autoCoverFile.value = null;
  autoCoverFileName.value = "";
  revokeObjectUrl(autoCoverPreviewUrl.value);
  autoCoverPreviewUrl.value = "";
  generatingVideoCover.value = false;
}

function resetCoverSelection({ preservePersisted = false } = {}) {
  videoCoverGenerationToken.value += 1;
  clearManualCoverSelection();
  clearAutoCoverSelection();
  if (!preservePersisted) {
    persistedCoverPreviewUrl.value = "";
  }
}

function triggerUploadPicker() {
  uploadInputRef.value?.click?.();
}

function triggerCoverPicker() {
  coverUploadInputRef.value?.click?.();
}

function extractVideoFrameBlob(file) {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "auto";
    video.muted = true;
    video.playsInline = true;
    video.src = objectUrl;

    let settled = false;
    const finalize = (callback) => {
      if (settled) return;
      settled = true;
      video.pause?.();
      video.removeAttribute("src");
      video.load?.();
      URL.revokeObjectURL(objectUrl);
      callback();
    };
    const fail = () => finalize(() => reject(new Error("视频封面抽帧失败")));
    const capture = () => {
      const width = Number(video.videoWidth || 0);
      const height = Number(video.videoHeight || 0);
      if (!width || !height) {
        fail();
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) {
        fail();
        return;
      }
      context.drawImage(video, 0, 0, width, height);
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            fail();
            return;
          }
          finalize(() => resolve(blob));
        },
        "image/jpeg",
        0.9,
      );
    };
    const captureAfterSeek = () => {
      video.removeEventListener("seeked", captureAfterSeek);
      capture();
    };
    video.addEventListener("error", fail, { once: true });
    video.addEventListener(
      "loadeddata",
      () => {
        const duration = Number(video.duration || 0);
        const targetTime =
          Number.isFinite(duration) && duration > 0.3
            ? Math.min(0.2, Math.max(duration / 3, 0.1))
            : 0;
        if (targetTime > 0) {
          video.addEventListener("seeked", captureAfterSeek, { once: true });
          try {
            video.currentTime = targetTime;
          } catch {
            video.removeEventListener("seeked", captureAfterSeek);
            capture();
          }
          return;
        }
        capture();
      },
      { once: true },
    );
  });
}

async function generateAutoCoverFromVideo(file) {
  const currentToken = videoCoverGenerationToken.value + 1;
  videoCoverGenerationToken.value = currentToken;
  clearAutoCoverSelection();
  generatingVideoCover.value = true;
  try {
    const coverBlob = await extractVideoFrameBlob(file);
    if (videoCoverGenerationToken.value !== currentToken) return;
    const baseName =
      String(file.name || "video").replace(/\.[^.]+$/, "") || "video";
    const coverFile = new File([coverBlob], `${baseName}-cover.jpg`, {
      type: "image/jpeg",
    });
    autoCoverFile.value = coverFile;
    autoCoverFileName.value = coverFile.name;
    autoCoverPreviewUrl.value = URL.createObjectURL(coverFile);
  } catch {
    if (videoCoverGenerationToken.value === currentToken) {
      clearAutoCoverSelection();
    }
  } finally {
    if (videoCoverGenerationToken.value === currentToken) {
      generatingVideoCover.value = false;
    }
  }
}

async function handleUploadFileChange(event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  clearSelectedUploadFile();
  resetCoverSelection();
  const fileType = String(file.type || "")
    .trim()
    .toLowerCase();
  const inferredAssetType = inferMaterialAssetTypeFromFile(file);
  if (inferredAssetType === "video" && fileType.startsWith("video/")) {
    try {
      const durationSeconds = await readVideoDurationFromFile(file);
      updateFormVideoDurationMetadata(durationSeconds);
    } catch (err) {
      ElMessage.error(
        err?.message || "无法读取视频时长，请更换可解析的视频文件后再上传",
      );
      if (event?.target) {
        event.target.value = "";
      }
      return;
    }
  }
  selectedUploadFile.value = file;
  selectedUploadFileName.value = String(file.name || "").trim();
  if (fileType.startsWith("image/")) {
    uploadPreviewUrl.value = URL.createObjectURL(file);
    uploadPreviewKind.value = "image";
  } else if (fileType.startsWith("video/")) {
    uploadPreviewUrl.value = URL.createObjectURL(file);
    uploadPreviewKind.value = "video";
  } else if (fileType.startsWith("audio/")) {
    uploadPreviewUrl.value = URL.createObjectURL(file);
    uploadPreviewKind.value = "audio";
  }
  form.value.asset_type = inferredAssetType;
  form.value.mime_type = String(file.type || "").trim() || form.value.mime_type;
  if (!String(form.value.title || "").trim()) {
    form.value.title = String(file.name || "").replace(/\.[^.]+$/, "");
  }
  if (inferredAssetType === "video" && fileType.startsWith("video/")) {
    await generateAutoCoverFromVideo(file);
  }
  if (event?.target) {
    event.target.value = "";
  }
}

function handleCoverFileChange(event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  clearManualCoverSelection();
  manualCoverFile.value = file;
  manualCoverFileName.value = String(file.name || "").trim();
  manualCoverPreviewUrl.value = URL.createObjectURL(file);
  if (event?.target) {
    event.target.value = "";
  }
}

function clearCoverSelection() {
  if (manualCoverFile.value) {
    clearManualCoverSelection();
    return;
  }
  if (autoCoverFile.value) {
    clearAutoCoverSelection();
  }
}

function isLikelyVideoUrl(url) {
  const normalized = normalizeRenderableUrl(url).toLowerCase();
  if (!normalized) return false;
  return [".mp4", ".mov", ".m4v", ".webm", ".ogg"].some((ext) =>
    normalized.includes(ext),
  );
}

function hasVideoMime(row) {
  return String(row?.mime_type || "")
    .trim()
    .toLowerCase()
    .startsWith("video/");
}

function resolveImagePreviewUrl(row) {
  if (canRenderVideoPreview(row)) {
    return normalizeRenderableUrl(row?.preview_url);
  }
  return normalizeRenderableUrl(row?.preview_url || row?.content_url);
}

function resolvePosterUrl(row) {
  return normalizeRenderableUrl(row?.preview_url);
}

function resolveBoardVideoPosterUrl(row) {
  return resolveStoredCoverPreviewUrl(row);
}

function resolveStoredCoverPreviewUrl(row) {
  const previewUrl = normalizeRenderableUrl(row?.preview_url);
  if (!previewUrl) return "";
  if (
    normalizeAssetType(row?.asset_type, row) === "video" &&
    previewUrl === normalizeRenderableUrl(row?.content_url)
  ) {
    return "";
  }
  return previewUrl;
}

function resolveVideoUrl(row) {
  const contentUrl = normalizeRenderableUrl(row?.content_url);
  if (contentUrl && (hasVideoMime(row) || isLikelyVideoUrl(contentUrl))) {
    return contentUrl;
  }
  const previewUrl = normalizeRenderableUrl(row?.preview_url);
  if (previewUrl && (hasVideoMime(row) || isLikelyVideoUrl(previewUrl))) {
    return previewUrl;
  }
  return "";
}

function hasAudioMime(row) {
  return String(row?.mime_type || "")
    .trim()
    .toLowerCase()
    .startsWith("audio/");
}

function isLikelyAudioUrl(url) {
  const normalized = normalizeRenderableUrl(url).toLowerCase();
  if (!normalized) return false;
  return [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"].some((ext) =>
    normalized.includes(ext),
  );
}

function resolveAudioUrl(row) {
  const contentUrl = normalizeRenderableUrl(row?.content_url);
  if (contentUrl && (hasAudioMime(row) || isLikelyAudioUrl(contentUrl))) {
    return contentUrl;
  }
  const previewUrl = normalizeRenderableUrl(row?.preview_url);
  if (previewUrl && (hasAudioMime(row) || isLikelyAudioUrl(previewUrl))) {
    return previewUrl;
  }
  return "";
}

function normalizeDetectedVideoDuration(value) {
  const duration = Number(value || 0);
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  return Math.max(1, Math.round(duration));
}

function extractVideoDurationSeconds(row) {
  const metadata = row?.metadata;
  const candidates = [
    metadata?.duration_seconds,
    metadata?.durationSeconds,
    metadata?.video_duration_seconds,
    metadata?.videoDurationSeconds,
  ];
  for (const candidate of candidates) {
    const normalized = normalizeDetectedVideoDuration(candidate);
    if (normalized > 0) return normalized;
  }
  return 0;
}

function mergeVideoDurationMetadata(metadata, durationSeconds) {
  const normalizedDuration = normalizeDetectedVideoDuration(durationSeconds);
  if (!normalizedDuration) {
    return typeof metadata === "object" && metadata ? { ...metadata } : {};
  }
  return {
    ...(typeof metadata === "object" && metadata ? metadata : {}),
    duration_seconds: normalizedDuration,
    durationSeconds: normalizedDuration,
    video_duration_seconds: normalizedDuration,
    videoDurationSeconds: normalizedDuration,
  };
}

function updateFormVideoDurationMetadata(durationSeconds) {
  const metadata = safeParseObject(form.value.metadata_text || "{}", "元数据");
  form.value.metadata_text = JSON.stringify(
    mergeVideoDurationMetadata(metadata, durationSeconds),
    null,
    2,
  );
}

async function hydrateVideoDurationForMaterial(row, currentProjectId) {
  const materialId = String(row?.id || "").trim();
  if (
    !currentProjectId ||
    !materialId ||
    normalizeAssetType(row?.asset_type, row) !== "video" ||
    extractVideoDurationSeconds(row) > 0 ||
    resolvingVideoDurationIds.has(materialId)
  ) {
    return row;
  }
  const videoUrl = resolveVideoUrl(row);
  if (!videoUrl) return row;
  resolvingVideoDurationIds.add(materialId);
  try {
    const durationSeconds = normalizeDetectedVideoDuration(
      await readVideoDurationFromUrl(videoUrl),
    );
    if (!durationSeconds) return row;
    const metadata = mergeVideoDurationMetadata(row?.metadata, durationSeconds);
    try {
      await api.patch(`/projects/${currentProjectId}/materials/${materialId}`, {
        metadata,
      });
    } catch {
      // Ignore persistence failure and keep local fallback.
    }
    return {
      ...row,
      metadata,
    };
  } catch {
    return row;
  } finally {
    resolvingVideoDurationIds.delete(materialId);
  }
}

async function hydrateMissingVideoDurations(rows) {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId || !Array.isArray(rows) || !rows.length) {
    return rows;
  }
  return Promise.all(
    rows.map((row) => hydrateVideoDurationForMaterial(row, currentProjectId)),
  );
}

function canRenderVideoPreview(row) {
  return (
    normalizeAssetType(row?.asset_type, row) === "video" &&
    Boolean(resolveVideoUrl(row))
  );
}

function resolvePreviewActionUrl(row) {
  if (normalizeAssetType(row?.asset_type, row) === "video") {
    return normalizeRenderableUrl(row?.content_url || row?.preview_url);
  }
  if (normalizeAssetType(row?.asset_type, row) === "audio") {
    return resolveAudioUrl(row);
  }
  return normalizeRenderableUrl(row?.preview_url || row?.content_url);
}

function canOpenMediaPreview(row) {
  const assetType = normalizeAssetType(row?.asset_type, row);
  if (assetType === "video") return Boolean(resolveVideoUrl(row));
  if (assetType === "audio") return Boolean(resolveAudioUrl(row));
  if (assetType === "image") return Boolean(resolveImagePreviewUrl(row));
  return false;
}

function resolveMediaPreviewType(row) {
  const assetType = normalizeAssetType(row?.asset_type, row);
  if (assetType === "video") return "video";
  if (assetType === "audio") return "audio";
  return "image";
}

function openMaterialPreview(row) {
  if (!canOpenMediaPreview(row)) return;
  previewTarget.value = row;
  previewDialogVisible.value = true;
}

function hasActiveMaterialFilters() {
  return Boolean(
    String(filters.value.query || "").trim() ||
      String(filters.value.groupType || "").trim() ||
      String(filters.value.assetType || "").trim() ||
      statusFilter.value !== "all" ||
      sourceFilter.value !== "all",
  );
}

async function autoFocusMaterialFromRoute() {
  const assetId = focusAssetId.value;
  if (!assetId || assetId === lastAutoFocusedAssetId.value) return;
  const target = displayMaterials.value.find(
    (item) => String(item?.id || "").trim() === assetId,
  );
  if (!target) {
    highlightedAssetId.value = materials.value.some(
      (item) => String(item?.id || "").trim() === assetId,
    )
      ? assetId
      : "";
    return;
  }
  highlightedAssetId.value = assetId;
  lastAutoFocusedAssetId.value = assetId;
  await nextTick();
  if (typeof document !== "undefined") {
    const card = Array.from(
      document.querySelectorAll("[data-material-asset-id]"),
    ).find((node) => node.dataset.materialAssetId === assetId);
    if (typeof card?.scrollIntoView === "function") {
      card.scrollIntoView({
        behavior: "smooth",
        block: "center",
        inline: "nearest",
      });
    }
  }
  if (canOpenMediaPreview(target)) {
    openMaterialPreview(target);
  }
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
  if (assetType === "audio") return "audio";
  return "all";
});

const currentCategoryLabel = computed(() => {
  if (activeCategory.value === "image") return "图片资产";
  if (activeCategory.value === "storyboard") return "分镜资产";
  if (activeCategory.value === "video") return "视频资产";
  if (activeCategory.value === "audio") return "音频资产";
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
  {
    value: "audio",
    label: "音频",
    count: Number(summary.value.audio_count || 0),
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
const focusedMaterial = computed(() => {
  const assetId = focusAssetId.value;
  if (!assetId) return null;
  return (
    materials.value.find((row) => String(row?.id || "").trim() === assetId) ||
    null
  );
});
const isFocusedMaterialVisible = computed(() => {
  const assetId = focusAssetId.value;
  if (!assetId) return false;
  return displayMaterials.value.some(
    (row) => String(row?.id || "").trim() === assetId,
  );
});
const focusAssetNotice = computed(() => {
  const assetId = focusAssetId.value;
  if (!assetId) return null;
  const title = String(
    focusedMaterial.value?.title || focusedMaterial.value?.id || assetId,
  ).trim();
  if (focusedMaterial.value && isFocusedMaterialVisible.value) {
    return {
      tone: "success",
      title: "已定位导出关联素材",
      message: `当前已定位到素材「${title}」，可直接预览、编辑或重新加入时间线。`,
      action: "",
    };
  }
  if (focusedMaterial.value) {
    return {
      tone: "warning",
      title: "目标素材已找到，但当前未显示",
      message: `素材「${title}」已存在于当前项目中，但被当前筛选条件隐藏。清空筛选后会自动滚动到该素材。`,
      action: "reveal",
    };
  }
  if (hasActiveMaterialFilters()) {
    return {
      tone: "warning",
      title: "目标素材未出现在当前筛选结果里",
      message: `正在查找素材 ID「${assetId}」。当前存在筛选条件，建议先清空筛选后再确认素材是否仍在项目中。`,
      action: "reset-filters",
    };
  }
  return {
    tone: "danger",
    title: "当前项目里找不到这个素材",
    message: `素材 ID「${assetId}」未出现在当前项目资产记录中，导出失败时引用的素材可能已被删除、替换，或来自错误的项目上下文。`,
    action: "create-material",
  };
});
const previewDialogType = computed(() =>
  previewTarget.value ? resolveMediaPreviewType(previewTarget.value) : "",
);
const previewDialogUrl = computed(() => {
  if (!previewTarget.value) return "";
  return previewDialogType.value === "video"
    ? resolveVideoUrl(previewTarget.value)
    : previewDialogType.value === "audio"
      ? resolveAudioUrl(previewTarget.value)
    : resolveImagePreviewUrl(previewTarget.value);
});
const previewDialogPosterUrl = computed(() =>
  previewTarget.value ? resolvePosterUrl(previewTarget.value) : "",
);
const previewDialogTitle = computed(
  () =>
    String(
      previewTarget.value?.title || previewTarget.value?.id || "素材预览",
    ).trim() || "素材预览",
);
const previewDialogMeta = computed(() => {
  if (!previewTarget.value) return "";
  return [
    previewTarget.value.asset_type_label ||
      getAssetTypeLabel(
        normalizeAssetType(previewTarget.value.asset_type, previewTarget.value),
      ),
    buildAssetPreviewText(previewTarget.value),
  ]
    .filter(Boolean)
    .join(" · ");
});
const showVideoCoverPanel = computed(
  () => String(form.value?.asset_type || "").trim() === "video",
);
const activeCoverPreviewUrl = computed(
  () =>
    manualCoverPreviewUrl.value ||
    autoCoverPreviewUrl.value ||
    persistedCoverPreviewUrl.value ||
    "",
);
const activeCoverFile = computed(
  () => manualCoverFile.value || autoCoverFile.value || null,
);
const coverSelectionLabel = computed(() => {
  if (manualCoverFileName.value) return manualCoverFileName.value;
  if (autoCoverFileName.value) return autoCoverFileName.value;
  if (persistedCoverPreviewUrl.value) return "当前已保存封面";
  return generatingVideoCover.value ? "正在抽取默认封面" : "未设置封面";
});
const coverSelectionSourceLabel = computed(() => {
  if (manualCoverFile.value) return "手动上传";
  if (autoCoverFile.value) return "自动抽帧";
  if (persistedCoverPreviewUrl.value) return "已保存封面";
  return "可选";
});
const canClearCoverSelection = computed(() =>
  Boolean(manualCoverFile.value || autoCoverFile.value),
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
      audio_count: 0,
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
    materials.value = await hydrateMissingVideoDurations(data.items || []);
    summary.value = data.summary || {
      total: 0,
      image_count: 0,
      storyboard_count: 0,
      video_count: 0,
      audio_count: 0,
    };
    await autoFocusMaterialFromRoute();
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
  } else if (category === "audio") {
    filters.value.groupType = "storyboard_video";
    filters.value.assetType = "audio";
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

async function resetFiltersForFocusedAsset() {
  filters.value = { query: "", groupType: "", assetType: "" };
  statusFilter.value = "all";
  sourceFilter.value = "all";
  await fetchMaterials();
}

async function revealFocusedAsset() {
  if (!focusAssetId.value) return;
  if (hasActiveMaterialFilters()) {
    await resetFiltersForFocusedAsset();
    return;
  }
  await autoFocusMaterialFromRoute();
}

function clearFocusedAssetRoute() {
  lastAutoFocusedAssetId.value = "";
  highlightedAssetId.value = "";
  const nextQuery = { ...route.query };
  delete nextQuery.focus_asset_id;
  void router.replace({
    path: route.path,
    query: nextQuery,
  });
}

function goBackToProject() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  void router.push(buildChatSettingsRoute(`/projects/${currentProjectId}`));
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
  clearSelectedUploadFile();
  resetCoverSelection();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingAssetId.value = String(row.id || "").trim();
  clearSelectedUploadFile();
  resetCoverSelection();
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
  persistedCoverPreviewUrl.value = resolveStoredCoverPreviewUrl(row);
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
  if (!editingAssetId.value && !selectedUploadFile.value) {
    ElMessage.warning("请先上传文件");
    return;
  }
  if (
    !editingAssetId.value &&
    form.value.asset_type === "video" &&
    generatingVideoCover.value
  ) {
    ElMessage.warning("正在处理视频默认封面，请稍后再保存");
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
  if (
    !editingAssetId.value &&
    form.value.asset_type === "video" &&
    extractVideoDurationSeconds({ metadata }) <= 0
  ) {
    ElMessage.error("无法确认视频时长，请重新选择可解析的视频文件后再上传");
    return;
  }
  const payload = {
    title,
    summary: form.value.summary,
    mime_type: form.value.mime_type,
    structured_content: structuredContent,
    metadata,
  };
  if (!editingAssetId.value) {
    const formData = new FormData();
    formData.append("file", selectedUploadFile.value);
    formData.append("asset_type", form.value.asset_type);
    formData.append("title", title);
    formData.append("summary", String(form.value.summary || ""));
    formData.append("mime_type", String(form.value.mime_type || ""));
    formData.append(
      "structured_content",
      JSON.stringify(structuredContent || {}),
    );
    formData.append("metadata", JSON.stringify(metadata || {}));
    if (form.value.asset_type === "video" && activeCoverFile.value) {
      formData.append("cover_file", activeCoverFile.value);
      formData.append(
        "cover_mime_type",
        String(activeCoverFile.value.type || "").trim(),
      );
      formData.append(
        "cover_source",
        manualCoverFile.value ? "manual_upload" : "auto_generated",
      );
    }
    saving.value = true;
    try {
      await api.post(
        `/projects/${currentProjectId}/materials/upload`,
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        },
      );
      ElMessage.success("素材已上传");
      dialogVisible.value = false;
      clearSelectedUploadFile();
      await fetchMaterials();
    } catch (err) {
      ElMessage.error(err?.detail || err?.message || "上传素材失败");
    } finally {
      saving.value = false;
    }
    return;
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
      if (form.value.asset_type === "video" && manualCoverFile.value) {
        const coverFormData = new FormData();
        coverFormData.append("cover_file", manualCoverFile.value);
        coverFormData.append(
          "cover_mime_type",
          String(manualCoverFile.value.type || "").trim(),
        );
        coverFormData.append("cover_source", "manual_upload");
        await api.post(
          `/projects/${currentProjectId}/materials/${editingAssetId.value}/cover`,
          coverFormData,
          {
            headers: {
              "Content-Type": "multipart/form-data",
            },
          },
        );
      }
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

watch(projectId, () => {
  void refresh();
});

watch(focusAssetId, (assetId, previousAssetId) => {
  if (assetId && assetId !== previousAssetId) {
    lastAutoFocusedAssetId.value = "";
    highlightedAssetId.value = assetId;
    void autoFocusMaterialFromRoute();
    return;
  }
  if (!assetId) {
    lastAutoFocusedAssetId.value = "";
    highlightedAssetId.value = "";
  }
});

watch(
  () => String(form.value?.asset_type || "").trim(),
  (assetType, previousAssetType) => {
    if (assetType !== "video" && previousAssetType === "video") {
      resetCoverSelection();
    }
  },
);

watch(dialogVisible, (visible) => {
  if (!visible) {
    clearSelectedUploadFile();
    resetCoverSelection();
  }
});

watch(previewDialogVisible, (visible) => {
  if (!visible) {
    previewTarget.value = null;
  }
});

onMounted(() => {
  void refresh();
});

onBeforeUnmount(() => {
  highlightedAssetId.value = "";
});
</script>

<style scoped>
.material-workbench {
  --material-ink: #0f172a;
  --material-muted: #475569;
  width: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 18px 22px;
  box-sizing: border-box;
  background: transparent;
}

.material-context-bar,
.material-filter-bar,
.material-content-surface {
  border: 1px solid rgba(255, 255, 255, 0.92);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.94)
  );
  box-shadow:
    0 18px 40px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(16px);
}

.material-context-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 20px;
  border-radius: 28px;
}

.material-context-bar__main {
  min-width: 0;
}

.material-context-bar__eyebrow,
.material-content-head__eyebrow,
.material-filter-group__label {
  color: #7c8aa0;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.material-context-bar__title {
  margin: 6px 0 0;
  color: #0f172a;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.15;
}

.material-context-bar__summary {
  margin: 8px 0 0;
  max-width: 540px;
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.material-context-bar__meta {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.material-context-bar__meta span {
  color: #5b6678;
  font-size: 12px;
  line-height: 1.6;
}

.material-context-bar__meta span:not(:last-child)::after {
  content: "·";
  margin-left: 10px;
  color: #9aa7b8;
}

.material-context-bar__signals {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.material-context-bar__signals span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border-radius: 0;
  background: transparent;
  border: 0;
  color: #6b7a8e;
  font-size: 12px;
  font-weight: 600;
}

.material-context-bar__signals span::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.45);
}

.material-context-bar__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.material-context-bar__action-button {
  border-radius: 999px;
  border-color: rgba(191, 219, 254, 0.76);
  color: #334155;
  background: rgba(255, 255, 255, 0.76);
}

.material-context-bar__primary {
  border-radius: 999px;
}

.material-filter-bar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 18px 18px;
  border-radius: 26px;
}

.material-filter-bar__top {
  display: grid;
  grid-template-columns: minmax(280px, 440px) minmax(0, 1fr);
  gap: 14px 18px;
  align-items: center;
}

.material-filter-bar__search {
  min-width: 0;
}

.material-filter-bar__groups {
  display: grid;
  gap: 12px;
}

.material-filter-group {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 10px 14px;
}

.material-chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  min-width: 0;
}

.material-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 13px;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  background: rgba(255, 255, 255, 0.82);
  color: #516071;
  font-size: 12px;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background 0.18s ease,
    color 0.18s ease;
}

.material-chip:hover,
.material-chip.is-active {
  border-color: rgba(15, 23, 42, 0.12);
  background: rgba(248, 250, 252, 0.96);
  color: #0f172a;
}

.material-chip__count {
  color: #7c8aa0;
}

.material-filter-bar__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.material-filter-bar__search :deep(.el-input__wrapper) {
  min-height: 42px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow:
    0 0 0 1px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.5);
}

.material-filter-bar__actions :deep(.el-radio-group) {
  flex-wrap: wrap;
}

.material-filter-bar__actions :deep(.el-radio-button__inner) {
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.64);
  box-shadow: none;
}

.material-filter-bar__actions :deep(.el-button) {
  border-radius: 999px;
}

.material-content-surface {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 18px;
  border-radius: 28px;
}

.material-content-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px 18px;
}

.material-focus-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: -4px;
  padding: 14px 16px;
  border-radius: 22px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.94),
    rgba(248, 250, 252, 0.92)
  );
}

.material-focus-banner.is-success {
  border-color: rgba(14, 116, 144, 0.22);
  background:
    radial-gradient(circle at left top, rgba(103, 232, 249, 0.16), transparent 34%),
    linear-gradient(135deg, rgba(240, 253, 250, 0.94), rgba(236, 254, 255, 0.9));
}

.material-focus-banner.is-warning {
  border-color: rgba(217, 119, 6, 0.22);
  background:
    radial-gradient(circle at left top, rgba(251, 191, 36, 0.16), transparent 34%),
    linear-gradient(135deg, rgba(255, 251, 235, 0.96), rgba(255, 247, 237, 0.92));
}

.material-focus-banner.is-danger {
  border-color: rgba(220, 38, 38, 0.2);
  background:
    radial-gradient(circle at left top, rgba(252, 165, 165, 0.16), transparent 34%),
    linear-gradient(135deg, rgba(254, 242, 242, 0.96), rgba(255, 241, 242, 0.92));
}

.material-focus-banner__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.material-focus-banner__title {
  color: var(--material-ink);
  font-size: 14px;
  font-weight: 700;
}

.material-focus-banner__message {
  color: var(--material-muted);
  font-size: 13px;
  line-height: 1.7;
}

.material-focus-banner__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.material-content-head__title {
  margin-top: 6px;
  color: #0f172a;
  font-size: 22px;
  font-weight: 600;
  line-height: 1.3;
}

.material-content-head__subtitle {
  margin-top: 8px;
  color: #5b6678;
  font-size: 13px;
  line-height: 1.7;
}

.material-content-head__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.material-content-head__mode {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(15, 23, 42, 0.06);
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.material-board {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.material-card {
  overflow: hidden;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 28px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.94)
  );
  border: 1px solid rgba(226, 232, 240, 0.96);
  box-shadow:
    0 18px 42px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.material-card:hover {
  transform: translateY(-4px);
  border-color: rgba(15, 23, 42, 0.12);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
}

.material-card.is-highlighted {
  border-color: rgba(14, 165, 233, 0.42);
  box-shadow:
    0 22px 52px rgba(14, 165, 233, 0.16),
    0 0 0 2px rgba(125, 211, 252, 0.42);
}

.material-card__preview {
  min-height: 248px;
  aspect-ratio: 16 / 10;
  position: relative;
  overflow: hidden;
  background:
    linear-gradient(
      135deg,
      rgba(244, 244, 245, 0.96),
      rgba(250, 250, 250, 0.98)
    ),
    #f8fafc;
}

.material-card__preview.is-clickable {
  cursor: zoom-in;
}

.material-card__preview::after {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.03), transparent 24%),
    linear-gradient(0deg, rgba(15, 23, 42, 0.18), transparent 42%);
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

.material-card__preview.is-audio {
  background:
    radial-gradient(circle at top right, rgba(16, 185, 129, 0.18), transparent 30%),
    linear-gradient(
      135deg,
      rgba(236, 253, 245, 0.98),
      rgba(239, 246, 255, 0.92)
    ),
    #f8fafc;
}

.material-card__image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.material-card__audio-preview {
  position: relative;
  z-index: 1;
  display: flex;
  height: 100%;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
  padding: 22px;
  box-sizing: border-box;
}

.material-card__audio-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 18px;
  background: linear-gradient(135deg, #059669, #10b981);
  color: #ecfdf5;
  font-size: 26px;
  font-weight: 700;
  box-shadow: 0 14px 28px rgba(5, 150, 105, 0.2);
}

.material-card__audio-copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.material-card__audio-copy strong {
  color: #0f172a;
  font-size: 18px;
  line-height: 1.35;
  font-weight: 700;
  word-break: break-all;
}

.material-card__audio-copy span {
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.material-card__audio-player {
  width: 100%;
}

.material-card__play-badge {
  position: absolute;
  right: 16px;
  bottom: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 64px;
  height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.24);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  pointer-events: none;
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.22);
}

.material-card__placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 22px;
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

.material-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
}

.material-card__head {
  display: grid;
  gap: 10px;
}

.material-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.material-card__source-pill,
.material-card__updated-pill {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(241, 245, 249, 0.94);
  color: #334155;
  font-size: 11px;
  line-height: 1.4;
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.material-card__source-pill {
  font-weight: 600;
}

.material-card__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px 18px 12px;
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
  line-height: 1.6;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.material-card__footer {
  padding: 0 18px 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: transparent;
  border-top: 1px solid rgba(226, 232, 240, 0.78);
  margin-top: 4px;
  padding-top: 14px;
}

.material-card__footer :deep(.el-button + .el-button) {
  margin-left: 0;
}

.material-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.46);
  border: 1px dashed rgba(15, 23, 42, 0.08);
}

.material-table-shell {
  overflow: hidden;
  border-radius: 22px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.86);
}

.material-table-shell :deep(.el-table) {
  --el-table-border-color: rgba(15, 23, 42, 0.06);
  --el-table-header-bg-color: rgba(248, 250, 252, 0.86);
  --el-table-row-hover-bg-color: rgba(248, 250, 252, 0.8);
  background: transparent;
}

.material-table-shell :deep(.el-table th.el-table__cell) {
  background: rgba(248, 250, 252, 0.78);
}

.material-table-shell :deep(.el-table tr) {
  background: transparent;
}

.source-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.material-upload-panel {
  margin-bottom: 18px;
}

.material-upload-panel__input {
  display: none;
}

.material-upload-panel__surface {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 18px;
  border-radius: 22px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background:
    radial-gradient(
      circle at top right,
      rgba(56, 189, 248, 0.14),
      transparent 34%
    ),
    rgba(248, 250, 252, 0.9);
}

.material-upload-panel__copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.material-upload-panel__title {
  color: #0f172a;
  font-size: 15px;
  font-weight: 700;
}

.material-upload-panel__text {
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}

.material-upload-panel__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #64748b;
  font-size: 12px;
}

.material-upload-panel__meta span {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.material-upload-panel__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.material-upload-panel__preview {
  width: 100%;
  max-width: 240px;
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.82);
}

.material-upload-panel__preview--cover {
  max-width: 220px;
}

.material-upload-panel__preview-image {
  display: block;
  width: 100%;
  height: 180px;
  object-fit: cover;
}

.material-upload-panel__preview-video {
  display: block;
  width: 100%;
  height: 180px;
  object-fit: cover;
  background: #0f172a;
}

.material-upload-panel__preview-audio {
  display: block;
  width: 100%;
  min-height: 72px;
  padding: 14px;
  box-sizing: border-box;
}

.material-video-cover-panel {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 16px;
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: linear-gradient(
    135deg,
    rgba(239, 246, 255, 0.92),
    rgba(248, 250, 252, 0.94)
  );
}

.material-video-cover-panel__copy {
  display: flex;
  min-width: 0;
  flex: 1 1 220px;
  flex-direction: column;
  gap: 6px;
}

.material-video-cover-panel__hint {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.material-preview-dialog__head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.material-preview-dialog__title {
  color: #0f172a;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.4;
}

.material-preview-dialog__meta {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.material-preview-dialog__body {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: min(70vh, 720px);
  border-radius: 22px;
  background:
    radial-gradient(circle at top, rgba(186, 230, 253, 0.12), transparent 28%),
    rgba(248, 250, 252, 0.88);
  overflow: hidden;
}

.material-preview-dialog__image,
.material-preview-dialog__video {
  display: block;
  width: 100%;
  max-height: min(70vh, 720px);
  object-fit: contain;
  background: #0f172a;
}

.material-preview-dialog__audio {
  width: min(100%, 720px);
}

@media (max-width: 1100px) {
  .material-context-bar,
  .material-filter-bar,
  .material-content-surface {
    padding-left: 16px;
    padding-right: 16px;
  }

  .material-context-bar {
    flex-direction: column;
  }

  .material-context-bar__summary {
    max-width: none;
  }

  .material-filter-bar__top {
    grid-template-columns: 1fr;
  }

  .material-filter-bar__actions {
    justify-content: flex-start;
  }
}

@media (max-width: 720px) {
  .material-workbench {
    gap: 12px;
    padding: 12px 12px 16px;
  }

  .material-context-bar,
  .material-filter-bar,
  .material-content-surface {
    border-radius: 24px;
    padding: 16px;
  }

  .material-context-bar__title {
    font-size: 22px;
  }

  .material-context-bar__summary {
    font-size: 13px;
  }

  .material-content-head__title {
    font-size: 18px;
  }

  .source-cell {
    align-items: flex-start;
    flex-direction: column;
  }

  .material-upload-panel__actions {
    flex-wrap: wrap;
  }
}
</style>
