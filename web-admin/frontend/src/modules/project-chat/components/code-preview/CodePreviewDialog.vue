<template>
  <el-dialog
    v-model="visibleModel"
    :title="title"
    width="min(1200px, calc(100vw - 32px))"
    destroy-on-close
    class="code-preview-dialog"
  >
    <div class="code-preview-shell">
      <div v-if="error" class="code-preview-error">
        {{ error }}
      </div>
      <iframe
        v-else
        class="code-preview-frame"
        :srcdoc="srcdoc"
        sandbox="allow-scripts allow-forms allow-modals"
        referrerpolicy="no-referrer"
      />
    </div>
  </el-dialog>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: "代码预览" },
  srcdoc: { type: String, default: "" },
  error: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue"]);

const visibleModel = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});
</script>

<style scoped>
.code-preview-shell {
  min-height: 72vh;
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92), #ffffff);
}

.code-preview-frame {
  width: 100%;
  min-height: 72vh;
  border: 0;
  background: #ffffff;
}

.code-preview-error {
  padding: 18px 20px;
  color: #9f1239;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
}
</style>
