<template>
  <el-dialog
    :model-value="modelValue"
    title="加入素材库"
    width="min(760px, calc(100vw - 32px))"
    destroy-on-close
    class="material-save-dialog"
    @update:model-value="handleVisibleChange"
    @close="handleClose"
  >
    <div class="material-save-dialog__body">
      <div class="material-save-dialog__summary">
        <div class="material-save-dialog__title">当前项目：{{ projectLabel }}</div>
        <div class="material-save-dialog__meta">
          <span>消息角色：{{ messageRoleLabel || "-" }}</span>
          <span>来源会话：{{ sourceChatSessionId || "-" }}</span>
          <span>图片数：{{ imageCount }}</span>
        </div>
      </div>

      <ProjectMaterialFormFields
        :form="form"
        :label-width="108"
        :asset-type-options="normalizedAssetTypeOptions"
        :mime-type-options="normalizedMimeTypeOptions"
        context-note="来源会话、消息关联和项目归属会自动写入，这里只需要确认素材本身的信息。"
      />
    </div>

    <template #footer>
      <el-button @click="handleVisibleChange(false)">取消</el-button>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!modelValue"
        @click="handleSubmit"
      >
        保存到素材库
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import ProjectMaterialFormFields from "@/components/ProjectMaterialFormFields.vue";

const DEFAULT_ASSET_TYPE_OPTIONS = [
  { value: "image", label: "图片" },
  { value: "storyboard", label: "分镜" },
  { value: "video", label: "视频" },
];
const DEFAULT_MIME_TYPE_OPTIONS = [
  { value: "image/png", label: "PNG 图片" },
  { value: "image/jpeg", label: "JPEG 图片" },
  { value: "image/webp", label: "WebP 图片" },
  { value: "image/gif", label: "GIF 图片" },
  { value: "image/svg+xml", label: "SVG 图片" },
  { value: "image/bmp", label: "BMP 图片" },
  { value: "video/mp4", label: "MP4 视频" },
  { value: "video/quicktime", label: "MOV / QuickTime 视频" },
  { value: "application/json", label: "JSON 结构化结果" },
  { value: "text/plain", label: "纯文本" },
];

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  projectLabel: {
    type: String,
    default: "",
  },
  messageRoleLabel: {
    type: String,
    default: "",
  },
  imageCount: {
    type: Number,
    default: 0,
  },
  sourceChatSessionId: {
    type: String,
    default: "",
  },
  initialForm: {
    type: Object,
    default: () => ({}),
  },
  assetTypeOptions: {
    type: Array,
    default: () => [],
  },
  mimeTypeOptions: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["update:modelValue", "submit", "close"]);

const form = ref(buildDefaultForm());

const normalizedAssetTypeOptions = computed(() =>
  Array.isArray(props.assetTypeOptions) && props.assetTypeOptions.length
    ? props.assetTypeOptions
    : DEFAULT_ASSET_TYPE_OPTIONS,
);
const normalizedMimeTypeOptions = computed(() =>
  Array.isArray(props.mimeTypeOptions) && props.mimeTypeOptions.length
    ? props.mimeTypeOptions
    : DEFAULT_MIME_TYPE_OPTIONS,
);

watch(
  () => [props.modelValue, props.initialForm],
  ([visible]) => {
    if (!visible) return;
    form.value = cloneForm(props.initialForm);
  },
  { deep: true, immediate: true },
);

function buildDefaultForm() {
  return {
    asset_type: "image",
    title: "",
    summary: "",
    preview_url: "",
    content_url: "",
    mime_type: "",
    structured_content_text: "",
    metadata_text: "",
  };
}

function cloneForm(source) {
  return {
    ...buildDefaultForm(),
    ...(source && typeof source === "object" ? source : {}),
  };
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

function handleVisibleChange(value) {
  emit("update:modelValue", Boolean(value));
}

function handleClose() {
  emit("close");
}

function handleSubmit() {
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
    ElMessage.error(err?.message || "JSON 格式错误");
    return;
  }
  emit("submit", {
    asset_type: String(form.value.asset_type || "image").trim() || "image",
    title,
    summary: form.value.summary,
    preview_url: form.value.preview_url,
    content_url: form.value.content_url,
    mime_type: form.value.mime_type,
    structured_content: structuredContent,
    metadata,
  });
}
</script>

<style scoped>
.material-save-dialog__body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.material-save-dialog__summary {
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: linear-gradient(180deg, #f8fafc, #ffffff);
}

.material-save-dialog__title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.material-save-dialog__meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  font-size: 12px;
  color: #64748b;
}
</style>
