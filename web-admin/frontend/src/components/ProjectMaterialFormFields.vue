<template>
  <div class="project-material-form">
    <div v-if="contextNote" class="project-material-form__note">
      {{ contextNote }}
    </div>

    <el-form :model="form" :label-width="labelWidth">
      <el-form-item v-if="showAssetType" required>
        <template #label>
          <div class="project-material-form__label">
            <span>素材类型</span>
            <el-tooltip
              content="决定素材进入图片、分镜或视频分组，也影响后续使用方式。"
              placement="top"
            >
              <el-icon class="project-material-form__label-icon">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </div>
        </template>
        <el-select v-model="form.asset_type" style="width: 100%">
          <el-option
            v-for="item in assetTypeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <div class="project-material-form__hint">
          先选对类型，后续素材卡片和生成链路会按这个类型组织。
        </div>
      </el-form-item>

      <el-form-item required>
        <template #label>
          <div class="project-material-form__label">
            <span>标题</span>
            <el-tooltip
              content="素材列表的主展示名称，建议写清用途、版本或画面主题。"
              placement="top"
            >
              <el-icon class="project-material-form__label-icon">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </div>
        </template>
        <el-input v-model="form.title" maxlength="120" show-word-limit />
        <div class="project-material-form__hint">
          例如：品牌主视觉 01、夏日饮品分镜草案、口播成片 v2。
        </div>
      </el-form-item>

      <el-form-item>
        <template #label>
          <div class="project-material-form__label">
            <span>摘要</span>
            <el-tooltip
              content="补充用途、风格、场景或版本差异，便于后续检索和团队协作。"
              placement="top"
            >
              <el-icon class="project-material-form__label-icon">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </div>
        </template>
        <el-input
          v-model="form.summary"
          type="textarea"
          :rows="3"
          maxlength="1000"
          show-word-limit
        />
        <div class="project-material-form__hint">
          可选。一句话说明这份素材能做什么，后续查找会更快。
        </div>
      </el-form-item>

      <el-form-item v-if="showLinkFields">
        <template #label>
          <div class="project-material-form__label">
            <span>预览链接</span>
            <el-tooltip :content="previewTooltip" placement="top">
              <el-icon class="project-material-form__label-icon">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </div>
        </template>
        <el-input v-model="form.preview_url" :placeholder="previewPlaceholder" />
        <div class="project-material-form__hint">
          {{ previewHint }}
        </div>
      </el-form-item>

      <el-form-item v-if="showLinkFields">
        <template #label>
          <div class="project-material-form__label">
            <span>内容链接</span>
            <el-tooltip :content="contentTooltip" placement="top">
              <el-icon class="project-material-form__label-icon">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </div>
        </template>
        <el-input v-model="form.content_url" :placeholder="contentPlaceholder" />
        <div class="project-material-form__hint">
          {{ contentHint }}
        </div>
      </el-form-item>

      <el-form-item>
        <template #label>
          <div class="project-material-form__label">
            <span>MIME 类型</span>
            <el-tooltip :content="mimeTooltip" placement="top">
              <el-icon class="project-material-form__label-icon">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </div>
        </template>
        <el-select
          v-model="form.mime_type"
          style="width: 100%"
          clearable
          filterable
          allow-create
          default-first-option
          placeholder="选择或输入 MIME 类型"
        >
          <el-option
            v-for="item in mimeTypeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <div class="project-material-form__hint">
          {{ mimeHint }}
        </div>
      </el-form-item>

      <el-form-item v-if="showStatus">
        <template #label>
          <div class="project-material-form__label">
            <span>状态</span>
            <el-tooltip
              content="用于内部管理。大多数可直接使用的素材保持“可用”即可。"
              placement="top"
            >
              <el-icon class="project-material-form__label-icon">
                <QuestionFilled />
              </el-icon>
            </el-tooltip>
          </div>
        </template>
        <el-select v-model="form.status" style="width: 100%">
          <el-option label="草稿" value="draft" />
          <el-option label="可用" value="ready" />
          <el-option label="归档" value="archived" />
        </el-select>
        <div class="project-material-form__hint">
          草稿适合暂存，归档适合停用历史素材。
        </div>
      </el-form-item>

      <div class="project-material-form__advanced" :style="advancedStyle">
        <button
          type="button"
          class="project-material-form__advanced-toggle"
          @click="advancedVisible = !advancedVisible"
        >
          {{ advancedVisible ? "收起高级信息" : "展开高级信息" }}
        </button>
        <div class="project-material-form__advanced-hint">
          结构化内容和元数据都是可选项，只有在后续还要驱动生成、检索或追踪来源时再填写。
        </div>
      </div>

      <el-collapse-transition>
        <div v-show="advancedVisible">
          <el-form-item>
            <template #label>
              <div class="project-material-form__label">
                <span>结构化内容</span>
                <el-tooltip
                  content="放业务正文 JSON，例如 shots、scene_count、prompt_blocks 这类可继续被系统消费的数据。"
                  placement="top"
                >
                  <el-icon class="project-material-form__label-icon">
                    <QuestionFilled />
                  </el-icon>
                </el-tooltip>
              </div>
            </template>
            <el-input
              v-model="form.structured_content_text"
              type="textarea"
              :rows="5"
              placeholder='例如 {"shots":[{"title":"开场","prompt":"..."}]}'
            />
            <div class="project-material-form__hint">
              分镜素材建议写这里；普通图片没有结构化信息时可留空。
            </div>
          </el-form-item>

          <el-form-item>
            <template #label>
              <div class="project-material-form__label">
                <span>元数据</span>
                <el-tooltip
                  content="放来源、模型、标签、批次号等辅助信息，不作为主展示内容。"
                  placement="top"
                >
                  <el-icon class="project-material-form__label-icon">
                    <QuestionFilled />
                  </el-icon>
                </el-tooltip>
              </div>
            </template>
            <el-input
              v-model="form.metadata_text"
              type="textarea"
              :rows="5"
              placeholder='例如 {"source":"manual","tag":"hero-banner"}'
            />
            <div class="project-material-form__hint">
              用于补充来源和检索标签；不需要时留空即可。
            </div>
          </el-form-item>
        </div>
      </el-collapse-transition>
    </el-form>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { QuestionFilled } from "@element-plus/icons-vue";

const props = defineProps({
  form: {
    type: Object,
    required: true,
  },
  assetTypeOptions: {
    type: Array,
    default: () => [],
  },
  mimeTypeOptions: {
    type: Array,
    default: () => [],
  },
  showAssetType: {
    type: Boolean,
    default: true,
  },
  showStatus: {
    type: Boolean,
    default: false,
  },
  showLinkFields: {
    type: Boolean,
    default: true,
  },
  contextNote: {
    type: String,
    default: "",
  },
  labelWidth: {
    type: [String, Number],
    default: 120,
  },
});

const advancedVisible = ref(false);

const assetType = computed(
  () => String(props.form?.asset_type || "image").trim() || "image",
);

const previewPlaceholder = computed(() =>
  assetType.value === "video"
    ? "https://.../cover.jpg"
    : assetType.value === "audio"
      ? "https://.../audio-cover.jpg"
    : assetType.value === "storyboard"
      ? "https://.../storyboard-cover.jpg"
      : "https://.../preview.png",
);

const contentPlaceholder = computed(() =>
  assetType.value === "video"
    ? "https://.../video.mp4"
    : assetType.value === "audio"
      ? "https://.../audio.mp3"
    : assetType.value === "storyboard"
      ? "https://.../storyboard.json"
      : "https://.../original.png",
);

const previewTooltip = computed(() =>
  assetType.value === "video"
    ? "视频素材通常放封面图地址，方便在列表中快速识别。"
    : assetType.value === "audio"
      ? "音频素材可放封面图或节目图，方便在列表中快速识别。"
    : assetType.value === "storyboard"
      ? "分镜素材可放封面、关键帧草图或总览图。"
      : "图片素材会优先用这个地址做卡片预览。",
);

const contentTooltip = computed(() =>
  assetType.value === "video"
    ? "填写可播放的视频地址或主交付文件地址。"
    : assetType.value === "audio"
      ? "填写可播放的音频地址或主音频文件地址。"
    : assetType.value === "storyboard"
      ? "填写分镜 JSON、文档或详情页地址。"
      : "填写原图、高清图或主文件地址。",
);

const mimeTooltip = computed(() =>
  assetType.value === "storyboard"
    ? "分镜常用 application/json 或 text/plain。"
    : assetType.value === "video"
      ? "视频常用 video/mp4、video/quicktime。"
      : assetType.value === "audio"
        ? "音频常用 audio/mpeg、audio/wav、audio/mp4。"
      : "图片常用 image/png、image/jpeg、image/webp。",
);

const previewHint = computed(() =>
  assetType.value === "video"
    ? "可选。建议填封面图，素材墙浏览会更直观。"
    : assetType.value === "audio"
      ? "可选。建议填一张封面图，方便快速识别音频素材。"
    : assetType.value === "storyboard"
      ? "可选。建议填一张分镜概览图，方便快速识别。"
      : "可选。用于素材卡片展示，建议填可直接访问的图片地址。",
);

const contentHint = computed(() =>
  assetType.value === "video"
    ? "建议填写视频主文件或播放地址，后续可直接打开复看。"
    : assetType.value === "audio"
      ? "建议填写音频主文件或播放地址，后续可直接试听和复用。"
    : assetType.value === "storyboard"
      ? "建议填写分镜 JSON、文档或外部说明页地址。"
      : "建议填写原图或主素材地址，便于下载和复用。",
);

const mimeHint = computed(() =>
  assetType.value === "storyboard"
    ? "不确定时可先留空；结构化分镜通常选 JSON。"
    : "不确定时可先留空，也可以从下拉里快速选择。",
);

const advancedStyle = computed(() => ({
  paddingLeft:
    typeof props.labelWidth === "number"
      ? `${props.labelWidth}px`
      : String(props.labelWidth || "120px"),
}));

watch(
  () => props.form,
  (nextForm) => {
    const hasAdvancedData = Boolean(
      String(nextForm?.structured_content_text || "").trim() ||
        String(nextForm?.metadata_text || "").trim(),
    );
    advancedVisible.value = hasAdvancedData;
  },
  { immediate: true },
);
</script>

<style scoped>
.project-material-form__note {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(248, 250, 252, 0.94);
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}

.project-material-form__label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.project-material-form__label-icon {
  color: #94a3b8;
  cursor: help;
}

.project-material-form__hint {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.project-material-form__advanced {
  margin-top: 2px;
  margin-bottom: 14px;
}

.project-material-form__advanced-toggle {
  padding: 0;
  border: none;
  background: transparent;
  color: #2563eb;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.project-material-form__advanced-hint {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .project-material-form__advanced {
    padding-left: 0;
  }
}
</style>
