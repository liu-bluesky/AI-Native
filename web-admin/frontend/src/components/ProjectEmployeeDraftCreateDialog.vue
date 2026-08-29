<template>
  <el-dialog
    :model-value="modelValue"
    title="确认更新 AI 智能体"
    width="min(880px, calc(100vw - 32px))"
    destroy-on-close
    class="employee-draft-create-dialog"
    @update:model-value="handleVisibleChange"
    @close="handleClose"
  >
    <div
      v-if="payload"
      class="employee-draft-dialog"
      v-loading="loading"
    >
      <div class="employee-draft-dialog__summary">
        <div class="employee-draft-dialog__title">
          {{ payload.name || "待补充名称" }}
        </div>
        <div
          v-if="payload.description"
          class="employee-draft-dialog__desc"
        >
          {{ payload.description }}
        </div>
        <div class="employee-draft-dialog__meta">
          <span>核心目标：{{ payload.goal || "-" }}</span>
          <span>
            风格：{{ payload.tone || "professional" }} /
            {{ payload.verbosity || "concise" }}
          </span>
        </div>
      </div>

      <div class="employee-draft-dialog__section">
        <div class="employee-draft-dialog__section-title">工具使用策略</div>
        <pre class="employee-draft-dialog__content-preview">{{ readableToolUsagePolicy || "未配置" }}</pre>
      </div>

      <div class="employee-draft-dialog__section">
        <div class="employee-draft-dialog__section-title">保存内容预览</div>
        <div class="employee-draft-dialog__section-hint">
          以下内容按可读文本展示，确认后才会写入智能体定义文件和本地项目数据。
        </div>
        <pre class="employee-draft-dialog__content-preview">{{ saveContentPreview }}</pre>
      </div>

      <div class="employee-draft-dialog__section">
        <div class="employee-draft-dialog__section-title">更新内容</div>
        <div class="employee-draft-dialog__section-hint">
          确认后只更新当前已存在的智能体定义。
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleVisibleChange(false)">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!payload"
        @click="handleConfirm"
      >
        确认更新
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  submitting: {
    type: Boolean,
    default: false,
  },
  payload: {
    type: Object,
    default: null,
  },
  mode: {
    type: String,
    default: "create",
  },
});

const emit = defineEmits(["update:modelValue", "confirm", "close"]);


function readableValue(value) {
  if (value == null) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(readableValue).filter(Boolean).join("\n");
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

const readableToolUsagePolicy = computed(() =>
  readableValue(props.payload?.tool_usage_policy),
);

const saveContentPreview = computed(() => {
  const payload = props.payload || {};
  return readableValue({
    name: payload.name || "",
    description: payload.description || "",
    goal: payload.goal || "",
    role: payload.role || "",
    instructions: payload.instructions || [],
    style_hints: payload.style_hints || [],
    default_workflow: payload.default_workflow || [],
    tool_usage_policy: readableToolUsagePolicy.value,
    skills: payload.skills || [],
    skill_drafts: payload.skill_drafts || [],
    rule_ids: payload.rule_ids || [],
    rule_titles: payload.rule_titles || [],
    rule_drafts: payload.rule_drafts || [],
  }) || "暂无可保存内容";
});

function handleVisibleChange(value) {
  emit("update:modelValue", Boolean(value));
}

function handleClose() {
  emit("close");
}

function handleConfirm() {
  emit("confirm");
}
</script>

<style scoped>
.employee-draft-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.employee-draft-dialog__summary {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(37, 99, 235, 0.12);
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.08),
      transparent 42%
    ),
    linear-gradient(180deg, rgba(248, 250, 252, 0.96), #ffffff);
}

.employee-draft-dialog__title {
  color: #0f172a;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.4;
}

.employee-draft-dialog__desc {
  margin-top: 8px;
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.employee-draft-dialog__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 12px;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.employee-draft-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.employee-draft-dialog__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.employee-draft-dialog__section-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

.employee-draft-dialog__section-hint {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.employee-draft-dialog__content-preview {
  max-height: 260px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 10px;
  background: #f8fafc;
  color: #334155;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.employee-draft-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.employee-draft-dialog__panel {
  min-height: 112px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #f8fafc;
}

.employee-draft-dialog__panel-title {
  margin-bottom: 10px;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.employee-draft-dialog__subsection {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed rgba(203, 213, 225, 0.92);
}

.employee-draft-dialog__subsection-title {
  margin-bottom: 10px;
  color: #92400e;
  font-size: 12px;
  font-weight: 600;
}

.employee-draft-dialog__tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.employee-draft-dialog__empty {
  color: #64748b;
  font-size: 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.employee-draft-dialog__switches {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  width: 100%;
  min-width: 0;
}

.employee-draft-dialog__option-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.employee-draft-dialog__option-list :deep(.el-checkbox) {
  align-items: flex-start;
  height: auto;
  margin-right: 0;
  white-space: normal;
}

.employee-draft-dialog__option-list :deep(.el-checkbox__label) {
  display: flex;
  flex-direction: column;
  gap: 3px;
  line-height: 1.45;
}

.employee-draft-dialog__option-list small {
  color: var(--el-text-color-secondary);
}

@media (max-width: 767px) {
  .employee-draft-dialog__grid {
    grid-template-columns: 1fr;
  }
}
</style>
