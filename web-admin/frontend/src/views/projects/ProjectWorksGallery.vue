<template>
  <div v-loading="loadingWorks" class="project-works-page">
    <header class="project-works-page__header">
      <div>
        <div class="project-works-page__eyebrow">Works Gallery</div>
        <h2 class="project-works-page__title">我的作品</h2>
      </div>
      <div class="project-works-page__meta">
        <span>草稿 {{ draftWorks.length }}</span>
        <span>作品 {{ publishedWorks.length }}</span>
      </div>
    </header>

    <p class="project-works-page__desc">
      这里用于回看制作草稿和已完成作品。导出任务进度与失败信息统一在短片制作页查看。
    </p>

    <section class="project-works-page__section">
      <div class="project-works-page__section-head">
        <div class="project-works-page__section-title">制作草稿</div>
        <div class="project-works-page__section-desc">
          可直接回到短片制作继续编辑。
        </div>
      </div>

      <div v-if="draftWorks.length" class="project-works-page__grid">
        <article
          v-for="item in draftWorks"
          :key="item.id"
          class="project-work-card project-work-card--draft"
        >
          <div class="project-work-card__head">
            <div class="project-work-card__title">{{ item.title || "未命名草稿" }}</div>
            <span class="project-work-card__status">{{ item.status_label || "草稿" }}</span>
          </div>
          <div class="project-work-card__meta">
            <span>{{ resolveDraftStepLabel(item) }}</span>
            <span>{{ Number(item.clip_count || 0) }} 段</span>
            <span>{{ Number(item.timeline_duration_seconds || 0) }} 秒</span>
          </div>
          <div class="project-work-card__summary">
            保存于 {{ formatTime(item.updated_at || item.created_at) }}
          </div>
          <div class="project-work-card__actions">
            <el-button type="primary" size="small" @click="resumeDraft(item)">
              继续编辑
            </el-button>
          </div>
        </article>
      </div>

      <div v-else class="project-works-page__empty">
        <el-empty description="还没有保存到作品页的制作草稿" :image-size="56" />
      </div>
    </section>

    <section class="project-works-page__section">
      <div class="project-works-page__section-head">
        <div class="project-works-page__section-title">作品列表</div>
        <div class="project-works-page__section-desc">
          这里只展示已经完成并可回看的作品结果。
        </div>
      </div>

      <div v-if="publishedWorks.length" class="project-works-page__grid">
        <article
          v-for="item in publishedWorks"
          :key="item.id"
          class="project-work-card"
        >
          <div class="project-work-card__preview">
            <img
              v-if="item.result_poster_url"
              :src="item.result_poster_url"
              :alt="item.title || '导出结果封面'"
              class="project-work-card__preview-image"
            />
            <div v-else class="project-work-card__preview-fallback">
              <strong>{{ resolvePublishedPreviewBadge(item) }}</strong>
              <span>{{ resolvePublishedPreviewCopy(item) }}</span>
            </div>
          </div>
          <div class="project-work-card__head">
            <div class="project-work-card__title">{{ item.title || "未命名作品" }}</div>
            <span class="project-work-card__status">{{ item.status_label || "-" }}</span>
          </div>
          <div class="project-work-card__meta">
            <span>{{ item.export_format_label || item.export_format || "-" }}</span>
            <span>{{ item.export_resolution || "-" }}</span>
            <span>{{ Number(item.timeline_duration_seconds || 0) }} 秒</span>
          </div>
          <div
            class="project-work-card__summary"
            :class="{
              'project-work-card__summary--danger': isPublishedAssetMissing(item),
            }"
          >
            {{ resolvePublishedSummary(item) }}
          </div>
          <div class="project-work-card__actions">
            <el-button
              v-if="item.result_video_url"
              type="primary"
              size="small"
              @click="openPublishedWork(item)"
            >
              查看成片
            </el-button>
            <el-button
              v-else-if="hasPublishedResultAsset(item)"
              type="primary"
              plain
              size="small"
              @click="openPublishedMaterialLibrary(item)"
            >
              查看素材
            </el-button>
            <el-button
              v-if="hasPublishedResultAsset(item)"
              plain
              size="small"
              @click="openPublishedMaterialLibrary(item)"
            >
              去素材库
            </el-button>
            <el-button
              v-if="item.can_delete"
              type="danger"
              plain
              size="small"
              @click="removePublishedWork(item)"
            >
              删除
            </el-button>
          </div>
        </article>
      </div>

      <div v-else class="project-works-page__empty">
        <el-empty description="还没有可查看的作品" :image-size="56" />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import api from "@/utils/api.js";
import { resolveMaterialResourceUrl } from "@/utils/project-materials.js";
import {
  getStoredProjectContextId,
  setStoredProjectContextId,
} from "@/utils/desktop-shell.js";

const route = useRoute();
const router = useRouter();

const projectId = computed(() =>
  String(route.query.project_id || "").trim() || getStoredProjectContextId(),
);
const works = ref([]);
const loadingWorks = ref(false);
const resultAssets = ref([]);

watch(projectId, (value) => {
  const normalizedProjectId = String(value || "").trim();
  if (!normalizedProjectId) return;
  setStoredProjectContextId(normalizedProjectId);
});

const draftWorks = computed(() =>
  works.value.filter(
    (item) =>
      String(item.source_type || "").trim() === "studio_draft" ||
      String(item.status || "").trim() === "draft",
  ),
);

const resultAssetMap = computed(() =>
  new Map(
    resultAssets.value.map((item) => [String(item.id || "").trim(), item]),
  ),
);

const publishedWorks = computed(() =>
  works.value
    .filter(
      (item) =>
        String(item.source_type || "").trim() !== "studio_draft" &&
        String(item.status || "").trim() !== "draft" &&
        (
          String(item.status || "").trim() === "succeeded" ||
          Boolean(String(item.result_asset_id || "").trim())
        ),
    )
    .map((item) => {
      const resultAssetId = String(item.result_asset_id || "").trim();
      const resultAsset = resultAssetMap.value.get(resultAssetId) || null;
      return {
        ...item,
        has_result_asset: Boolean(resultAsset),
        result_asset: resultAsset,
        result_poster_url: resolvePublishedPosterUrl(resultAsset),
        result_video_url: resolvePublishedVideoUrl(resultAsset),
      };
    }),
);

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(
    date.getMinutes(),
  ).padStart(2, "0")}`;
}

function resolveDraftStepLabel(item) {
  const step =
    String(item?.audio_payload?.active_step || "").trim() ||
    String(item?.timeline_payload?.summary?.activeStep || "").trim();
  if (step === "art") return "美术设定";
  if (step === "storyboard") return "分镜制作";
  if (step === "export") return "导出视频";
  return "剧本创作";
}

function resolvePublishedPosterUrl(asset) {
  return resolveMaterialResourceUrl(asset?.preview_url || asset?.content_url || "");
}

function resolvePublishedVideoUrl(asset) {
  return resolveMaterialResourceUrl(asset?.content_url || asset?.preview_url || "");
}

function resolvePublishedPreviewBadge(item) {
  const status = String(item?.status || "").trim();
  if (status === "succeeded") return "READY";
  if (status === "failed") return "FAILED";
  if (status === "processing") return "RENDER";
  if (status === "queued") return "QUEUE";
  if (status === "canceled") return "STOP";
  return "WORK";
}

function resolvePublishedPreviewCopy(item) {
  const status = String(item?.status || "").trim();
  if (status === "succeeded" && isPublishedAssetMissing(item)) {
    return "素材已从素材库删除，作品记录仍保留";
  }
  if (status === "succeeded") return "作品已生成，可直接查看结果";
  return "作品结果已沉淀，可回看或进入素材库";
}

function resolvePublishedSummary(item) {
  const time = formatTime(item.updated_at || item.created_at);
  const asset = item?.result_asset;
  const assetName =
    String(asset?.original_filename || "").trim() ||
    String(asset?.title || "").trim();
  if (assetName) {
    return `结果已入素材库：${assetName} · 更新时间 ${time}`;
  }
  if (isPublishedAssetMissing(item)) {
    return `关联素材已从素材库删除，作品记录仍保留 · 更新时间 ${time}`;
  }
  return `作品已生成 · 更新时间 ${time}`;
}

function hasPublishedResultAsset(item) {
  return Boolean(item?.has_result_asset);
}

function isPublishedAssetMissing(item) {
  return (
    Boolean(String(item?.result_asset_id || "").trim()) &&
    !hasPublishedResultAsset(item)
  );
}

async function fetchWorks() {
  const currentProjectId = projectId.value;
  if (!currentProjectId) {
    works.value = [];
    resultAssets.value = [];
    return;
  }
  loadingWorks.value = true;
  try {
    const [workData, materialData] = await Promise.all([
      api.get(`/projects/${currentProjectId}/studio/exports`, {
        params: { limit: 100 },
      }),
      api.get(`/projects/${currentProjectId}/materials`, {
        params: { asset_type: "video" },
      }),
    ]);
    works.value = Array.isArray(workData?.items) ? workData.items : [];
    resultAssets.value = Array.isArray(materialData?.items) ? materialData.items : [];
  } catch (err) {
    works.value = [];
    resultAssets.value = [];
    ElMessage.error(err?.detail || err?.message || "加载作品列表失败");
  } finally {
    loadingWorks.value = false;
  }
}

function resumeDraft(item) {
  const currentProjectId = projectId.value;
  const workId = String(item?.id || "").trim();
  if (!currentProjectId || !workId) {
    ElMessage.warning("缺少草稿信息");
    return;
  }
  void router.push({
    path: "/materials/studio",
    query: {
      project_id: currentProjectId,
      draft_job_id: workId,
    },
  });
}

function openPublishedWork(item) {
  const targetUrl = String(item?.result_video_url || "").trim();
  if (!targetUrl) {
    ElMessage.warning("导出结果文件暂不可用");
    return;
  }
  if (typeof window !== "undefined") {
    window.open(targetUrl, "_blank", "noopener");
  }
}

function openPublishedMaterialLibrary(item) {
  const currentProjectId = projectId.value;
  if (!currentProjectId) return;
  const query = String(
    item?.result_asset?.title ||
      item?.result_asset?.original_filename ||
      item?.title ||
      "",
  ).trim();
  void router.push({
    path: "/materials",
    query: {
      project_id: currentProjectId,
      asset_type: "video",
      query,
    },
  });
}

async function removePublishedWork(item) {
  const currentProjectId = projectId.value;
  const workId = String(item?.id || "").trim();
  const workTitle = String(item?.title || "").trim() || workId;
  if (!currentProjectId || !workId) return;
  try {
    await ElMessageBox.confirm(
      `确认删除作品「${workTitle}」？删除后将无法恢复该作品记录。`,
      "删除作品",
      { type: "warning" },
    );
  } catch {
    return;
  }
  try {
    await api.delete(`/projects/${currentProjectId}/studio/exports/${workId}`);
    works.value = works.value.filter(
      (existingItem) => String(existingItem?.id || "").trim() !== workId,
    );
    ElMessage.success("作品已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除作品失败");
  }
}

watch(projectId, () => {
  void fetchWorks();
});

onMounted(() => {
  void fetchWorks();
});
</script>

<style scoped>
.project-works-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.project-works-page__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 6px 0;
}

.project-works-page__eyebrow {
  color: #9ca3af;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.project-works-page__title {
  margin: 6px 0 0;
  color: #111827;
  font-size: 22px;
  line-height: 1.2;
}

.project-works-page__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #64748b;
  font-size: 12px;
}

.project-works-page__desc {
  margin: 0;
  max-width: 920px;
  padding: 0 6px;
  color: #334155;
  font-size: 14px;
  line-height: 1.8;
}

.project-works-page__section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.project-works-page__section-head {
  padding: 0 6px;
}

.project-works-page__section-title {
  color: #0f172a;
  font-size: 16px;
  font-weight: 600;
}

.project-works-page__section-desc {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.project-works-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.project-work-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.05);
}

.project-work-card__preview {
  position: relative;
  overflow: hidden;
  border-radius: 14px;
  aspect-ratio: 16 / 9;
  background:
    linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(37, 99, 235, 0.68)),
    #0f172a;
}

.project-work-card__preview-image {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.project-work-card__preview-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 6px;
  padding: 16px;
  color: rgba(255, 255, 255, 0.92);
}

.project-work-card__preview-fallback strong {
  font-size: 20px;
  line-height: 1;
  letter-spacing: 0.08em;
}

.project-work-card__preview-fallback span {
  max-width: 20em;
  font-size: 12px;
  line-height: 1.6;
}

.project-work-card--draft {
  border-color: rgba(14, 165, 233, 0.16);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.94),
    rgba(240, 249, 255, 0.9)
  );
}

.project-work-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.project-work-card__title {
  color: #0f172a;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
}

.project-work-card__status {
  flex: none;
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
  font-size: 12px;
}

.project-work-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #64748b;
  font-size: 12px;
}

.project-work-card__summary {
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}

.project-work-card__summary--danger {
  color: #b91c1c;
}

.project-work-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.project-works-page__empty {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(17, 24, 39, 0.06);
}
</style>
