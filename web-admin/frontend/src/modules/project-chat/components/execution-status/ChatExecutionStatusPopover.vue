<template>
  <el-popover
    v-if="visible"
    trigger="click"
    placement="top-start"
    :width="360"
    popper-class="execution-status-popover"
    :popper-style="{ padding: '0' }"
    :offset="10"
    :teleported="false"
  >
    <template #reference>
      <ChatExecutionStatusChip :chip-label="chipLabel" :tone-class="toneClass" />
    </template>
    <ChatExecutionStatusPopoverPanel
      :action-label="actionLabel"
      :description="description"
      :detail-available="detailAvailable"
      :external-agent-warmup-loading="externalAgentWarmupLoading"
      :native-executor-detecting="nativeExecutorDetecting"
      :native-runner-self-checking="nativeRunnerSelfChecking"
      :status-label="statusLabel"
      :status-tag-type="statusTagType"
      :summary-items="summaryItems"
      :title="title"
      :tone-class="toneClass"
      @execute-primary="$emit('execute-primary')"
      @open-execution-detail="$emit('open-execution-detail')"
      @open-settings="$emit('open-settings')"
    />
  </el-popover>
</template>

<script setup>
import ChatExecutionStatusChip from "./ChatExecutionStatusChip.vue";
import ChatExecutionStatusPopoverPanel from "./ChatExecutionStatusPopoverPanel.vue";

defineProps({
  actionLabel: {
    type: String,
    default: "",
  },
  chipLabel: {
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
  visible: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["execute-primary", "open-execution-detail", "open-settings"]);
</script>
