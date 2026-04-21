<template>
  <div class="project-workspace-toolbar" :class="[`is-${variant}`]">
    <div v-if="description || $slots.summary" class="project-workspace-toolbar__summary">
      <slot name="summary">
        <p>{{ description }}</p>
      </slot>
    </div>

    <div v-if="$slots.controls" class="project-workspace-toolbar__controls">
      <slot name="controls" />
    </div>

    <div v-if="hint || $slots.hint" class="project-workspace-toolbar__hint">
      <slot name="hint">{{ hint }}</slot>
    </div>
  </div>
</template>

<script setup>
defineProps({
  description: {
    type: String,
    default: "",
  },
  hint: {
    type: String,
    default: "",
  },
  variant: {
    type: String,
    default: "panel",
  },
});
</script>

<style scoped>
.project-workspace-toolbar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 18px;
  padding: 16px 18px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 24px;
}

.project-workspace-toolbar.is-panel {
  background: rgba(248, 250, 252, 0.82);
}

.project-workspace-toolbar.is-compact {
  background: rgba(255, 255, 255, 0.82);
}

.project-workspace-toolbar__summary,
.project-workspace-toolbar__controls {
  min-width: 0;
}

.project-workspace-toolbar__summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.project-workspace-toolbar__summary p {
  max-width: 60ch;
  margin: 0;
  color: #475569;
  line-height: 1.65;
}

.project-workspace-toolbar__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.project-workspace-toolbar__hint {
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .project-workspace-toolbar__summary,
  .project-workspace-toolbar__controls {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
