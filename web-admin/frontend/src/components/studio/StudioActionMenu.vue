<template>
  <el-popover
    v-model:visible="visible"
    :placement="placement"
    :width="width"
    trigger="click"
    popper-class="studio-action-menu-popper"
  >
    <template #reference>
      <button
        type="button"
        class="studio-action-menu__trigger"
        :class="[
          `is-${variant}`,
          { 'is-icon-only': iconOnly },
        ]"
        @click.stop
      >
        <span v-if="!iconOnly && triggerText" class="studio-action-menu__trigger-text">
          {{ triggerText }}
        </span>
        <span class="studio-action-menu__trigger-mark">•••</span>
      </button>
    </template>

    <div class="studio-action-menu">
      <button
        v-for="action in actions"
        :key="action.id"
        type="button"
        class="studio-action-menu__item"
        :class="{
          'is-danger': action.danger,
        }"
        :disabled="action.disabled"
        @click.stop="handleSelect(action)"
      >
        <span class="studio-action-menu__item-label">{{ action.label }}</span>
        <span
          v-if="action.description"
          class="studio-action-menu__item-description"
        >
          {{ action.description }}
        </span>
      </button>
    </div>
  </el-popover>
</template>

<script setup>
import { ref } from "vue";

const props = defineProps({
  actions: {
    type: Array,
    default: () => [],
  },
  triggerText: {
    type: String,
    default: "",
  },
  placement: {
    type: String,
    default: "bottom-end",
  },
  width: {
    type: Number,
    default: 220,
  },
  iconOnly: {
    type: Boolean,
    default: false,
  },
  variant: {
    type: String,
    default: "ghost",
  },
});

const emit = defineEmits(["select"]);
const visible = ref(false);

function handleSelect(action) {
  if (!action || action.disabled) return;
  visible.value = false;
  emit("select", action.id, action);
}
</script>

<style scoped>
.studio-action-menu__trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.studio-action-menu__trigger.is-ghost {
  background: rgba(255, 255, 255, 0.92);
  color: #0f172a;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.26);
}

.studio-action-menu__trigger.is-dark {
  background: rgba(15, 23, 42, 0.42);
  color: rgba(255, 255, 255, 0.94);
}

.studio-action-menu__trigger.is-icon-only {
  min-width: 28px;
  padding: 0;
}

.studio-action-menu__trigger:hover {
  background: rgba(15, 23, 42, 0.12);
}

.studio-action-menu__trigger.is-dark:hover {
  background: rgba(15, 23, 42, 0.68);
}

.studio-action-menu__trigger-text {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.studio-action-menu__trigger-mark {
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: 0.08em;
}

.studio-action-menu {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 0;
}

.studio-action-menu__item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  padding: 10px 12px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.18s ease;
}

.studio-action-menu__item:hover {
  background: rgba(15, 23, 42, 0.05);
}

.studio-action-menu__item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.studio-action-menu__item.is-danger .studio-action-menu__item-label {
  color: #dc2626;
}

.studio-action-menu__item-label {
  color: #111827;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
}

.studio-action-menu__item-description {
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
  line-height: 1.45;
}

:deep(.studio-action-menu-popper) {
  padding: 8px;
  border-radius: 16px;
  border: 1px solid rgba(226, 232, 240, 0.96);
  box-shadow:
    0 22px 44px rgba(15, 23, 42, 0.12),
    0 8px 20px rgba(15, 23, 42, 0.06);
}
</style>
