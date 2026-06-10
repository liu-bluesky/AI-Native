<template>
  <div class="execution-status-popover__body">
    <div class="execution-status-popover__head">
      <div class="execution-status-popover__status-mark" :class="toneClass">
        <span></span>
      </div>
      <div class="execution-status-popover__title">
        <strong>{{ title }}</strong>
        <span>{{ description }}</span>
      </div>
      <el-tag size="small" effect="plain" :type="statusTagType">
        {{ statusLabel }}
      </el-tag>
    </div>
    <div class="execution-status-popover__grid" aria-label="执行状态摘要">
      <div v-for="item in summaryItems" :key="item.label">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>
    <div class="execution-status-popover__actions">
      <el-button
        class="execution-status-popover__secondary-action"
        size="small"
        @click="$emit('open-settings')"
      >
        <el-icon><Setting /></el-icon>
        打开设置
      </el-button>
      <el-button
        class="execution-status-popover__secondary-action"
        size="small"
        :disabled="!detailAvailable"
        @click="$emit('open-execution-detail')"
      >
        <el-icon><View /></el-icon>
        查看详情
      </el-button>
      <el-button
        class="execution-status-popover__primary-action"
        size="small"
        type="primary"
        plain
        :loading="primaryActionLoading"
        @click="$emit('execute-primary')"
      >
        {{ actionLabel }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { Setting, View } from "@element-plus/icons-vue";

const props = defineProps({
  actionLabel: {
    type: String,
    default: "",
  },
  description: {
    type: String,
    default: "",
  },
  detailAvailable: {
    type: Boolean,
    default: false,
  },
  externalAgentWarmupLoading: {
    type: Boolean,
    default: false,
  },
  nativeExecutorDetecting: {
    type: Boolean,
    default: false,
  },
  nativeRunnerSelfChecking: {
    type: Boolean,
    default: false,
  },
  statusLabel: {
    type: String,
    default: "",
  },
  statusTagType: {
    type: String,
    default: "",
  },
  summaryItems: {
    type: Array,
    default: () => [],
  },
  title: {
    type: String,
    default: "",
  },
  toneClass: {
    type: String,
    default: "",
  },
});

defineEmits(["execute-primary", "open-execution-detail", "open-settings"]);

// 多个执行入口共用主按钮 loading，避免自检、预热期间重复触发执行。
const primaryActionLoading = computed(
  () =>
    props.nativeExecutorDetecting ||
    props.nativeRunnerSelfChecking ||
    props.externalAgentWarmupLoading,
);
</script>

<style scoped>
:global(.execution-status-popover) {
  overflow: hidden;
  padding: 0 !important;
  border: 1px solid rgba(203, 213, 225, 0.8) !important;
  border-radius: 12px !important;
  background: #fff !important;
  box-shadow:
    0 20px 46px rgba(15, 23, 42, 0.13),
    0 6px 16px rgba(15, 23, 42, 0.08) !important;
}

:global(.execution-status-popover .el-popper__arrow::before) {
  border-color: rgba(203, 213, 225, 0.8) !important;
  background: #fff !important;
}

.execution-status-popover__body {
  min-width: 0;
  display: grid;
  gap: 0;
  box-sizing: border-box;
  width: 100%;
  background: #fff;
}

.execution-status-popover__head {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 14px 12px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.82);
  background: #fff;
}

.execution-status-popover__status-mark {
  width: 30px;
  height: 30px;
  box-sizing: border-box;
  display: grid;
  place-items: center;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  background: #f8fafc;
}

.execution-status-popover__status-mark span {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #94a3b8;
  box-shadow: 0 0 0 4px rgba(148, 163, 184, 0.13);
}

.execution-status-popover__status-mark.is-muted span {
  background: #94a3b8;
  box-shadow: 0 0 0 4px rgba(148, 163, 184, 0.13);
}

.execution-status-popover__status-mark.is-ready span {
  background: #22c55e;
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.14);
}

.execution-status-popover__status-mark.is-warning span {
  background: #f59e0b;
  box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.14);
}

.execution-status-popover__status-mark.is-pending span {
  background: #a855f7;
  box-shadow: 0 0 0 4px rgba(168, 85, 247, 0.14);
}

.execution-status-popover__status-mark.is-running span {
  background: #0ea5e9;
  box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.14);
}

.execution-status-popover__status-mark.is-system span {
  background: #6366f1;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.14);
}

.execution-status-popover__status-mark.is-danger span {
  background: #ef4444;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.14);
}

.execution-status-popover__title {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.execution-status-popover__head strong {
  min-width: 0;
  color: #0f172a;
  font-size: 13.5px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.execution-status-popover__head span {
  min-width: 0;
  color: #667085;
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.execution-status-popover__head :deep(.el-tag) {
  flex: 0 0 auto;
  max-width: 96px;
  border-radius: 999px;
  font-weight: 650;
}

.execution-status-popover__head :deep(.el-tag__content) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.execution-status-popover__grid {
  display: grid;
  gap: 0;
  padding: 4px 14px;
  background: #fff;
}

.execution-status-popover__grid > div {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(72px, auto) minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  box-sizing: border-box;
  min-height: 36px;
  padding: 7px 0;
}

.execution-status-popover__grid > div + div {
  border-top: 1px solid rgba(226, 232, 240, 0.72);
}

.execution-status-popover__grid span {
  min-width: 0;
  color: #667085;
  font-size: 11px;
  line-height: 1.3;
}

.execution-status-popover__grid strong {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  color: #1e293b;
  font-size: 12px;
  line-height: 1.35;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.execution-status-popover__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid rgba(226, 232, 240, 0.82);
  background: #f8fafc;
}

.execution-status-popover__actions :deep(.el-button) {
  flex: 1 1 calc(50% - 4px);
  min-width: 0;
  height: 34px;
  justify-content: center;
  box-sizing: border-box;
  margin-left: 0;
  padding: 0 10px;
  border-radius: 8px;
  font-weight: 600;
  white-space: nowrap;
}

.execution-status-popover__actions :deep(.el-button .el-icon) {
  flex: 0 0 auto;
  margin-right: 0;
  font-size: 14px;
}

.execution-status-popover__actions :deep(.el-button > span) {
  min-width: 0;
  max-width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.execution-status-popover__actions
  :deep(.execution-status-popover__secondary-action) {
  border: 1px solid rgba(203, 213, 225, 0.78);
  background: #fff;
  color: #475569;
}

.execution-status-popover__actions
  :deep(.execution-status-popover__secondary-action:hover) {
  background: rgba(226, 232, 240, 0.72);
  color: #1e293b;
}

.execution-status-popover__actions
  :deep(.execution-status-popover__secondary-action.is-disabled),
.execution-status-popover__actions
  :deep(.execution-status-popover__secondary-action.is-disabled:hover) {
  border-color: rgba(226, 232, 240, 0.82);
  background: rgba(255, 255, 255, 0.58);
  color: #94a3b8;
  cursor: not-allowed;
}

.execution-status-popover__actions
  :deep(.execution-status-popover__primary-action.el-button--primary.is-plain) {
  flex-basis: 100%;
  height: 36px;
  border-color: #2563eb;
  background: #2563eb;
  color: #fff;
  box-shadow: 0 5px 12px rgba(37, 99, 235, 0.22);
}

.execution-status-popover__actions
  :deep(.execution-status-popover__primary-action.el-button--primary.is-plain:hover) {
  border-color: #1d4ed8;
  background: #1d4ed8;
  color: #fff;
}
</style>
