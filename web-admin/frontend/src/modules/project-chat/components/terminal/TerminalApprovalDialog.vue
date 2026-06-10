<template>
  <el-dialog
    :model-value="modelValue"
    title="等待操作确认"
    width="min(560px, calc(100vw - 32px))"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    class="terminal-approval-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="prompt" class="terminal-approval-card">
      <div class="terminal-approval-card__title">
        {{ prompt.title }}
      </div>
      <div v-if="prompt.description" class="terminal-approval-card__desc">
        {{ prompt.description }}
      </div>
      <pre v-if="prompt.message" class="terminal-approval-card__message">{{
        prompt.message
      }}</pre>
    </div>
    <template #footer>
      <div class="terminal-approval-dialog__footer">
        <el-button type="danger" plain @click="emit('choose', '3')">
          取消
        </el-button>
        <el-button @click="emit('choose', '2')"> 本会话批准 </el-button>
        <el-button type="primary" @click="emit('choose', '1')">
          批准一次
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, default: false },
  prompt: { type: Object, default: null },
});

const emit = defineEmits(["update:modelValue", "choose"]);
</script>

<style scoped>
.terminal-approval-card {
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(251, 191, 36, 0.3);
  background: rgba(120, 53, 15, 0.35);
}

.terminal-approval-card__title {
  font-size: 13px;
  font-weight: 700;
  color: #fde68a;
}

.terminal-approval-card__desc {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.55;
  color: #fef3c7;
}

.terminal-approval-card__message {
  margin: 10px 0 0;
  padding: 10px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.28);
  color: #f8fafc;
  white-space: pre-wrap;
  word-break: break-word;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 12px;
  line-height: 1.55;
}

.terminal-approval-dialog__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
