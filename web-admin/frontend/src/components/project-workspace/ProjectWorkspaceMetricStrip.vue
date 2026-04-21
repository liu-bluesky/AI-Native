<template>
  <div class="project-workspace-metric-strip" :class="[`is-${variant}`]">
    <article
      v-for="item in items"
      :key="item[keyField] || item[labelField]"
      class="project-workspace-metric-strip__card"
      :class="toneField && item[toneField] ? `is-${item[toneField]}` : ''"
    >
      <span>{{ item[labelField] }}</span>
      <strong>{{ item[valueField] }}</strong>
      <small v-if="item[metaField]">{{ item[metaField] }}</small>
    </article>
  </div>
</template>

<script setup>
defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  variant: {
    type: String,
    default: "default",
  },
  keyField: {
    type: String,
    default: "label",
  },
  labelField: {
    type: String,
    default: "label",
  },
  valueField: {
    type: String,
    default: "value",
  },
  metaField: {
    type: String,
    default: "meta",
  },
  toneField: {
    type: String,
    default: "tone",
  },
});
</script>

<style scoped>
.project-workspace-metric-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.project-workspace-metric-strip__card {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
  padding: 16px 18px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
}

.project-workspace-metric-strip.is-default .project-workspace-metric-strip__card {
  background: rgba(255, 255, 255, 0.78);
}

.project-workspace-metric-strip.is-accent .project-workspace-metric-strip__card {
  background: rgba(248, 250, 252, 0.92);
}

.project-workspace-metric-strip__card span {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.project-workspace-metric-strip__card strong {
  color: #0f172a;
  font-size: 22px;
  line-height: 1.1;
}

.project-workspace-metric-strip__card small {
  color: #64748b;
  line-height: 1.5;
}

.project-workspace-metric-strip__card.is-warning {
  border-color: rgba(245, 158, 11, 0.22);
}

.project-workspace-metric-strip__card.is-danger {
  border-color: rgba(248, 113, 113, 0.24);
}

.project-workspace-metric-strip__card.is-info {
  border-color: rgba(56, 189, 248, 0.24);
}

.project-workspace-metric-strip__card.is-success {
  border-color: rgba(34, 197, 94, 0.2);
}

@media (max-width: 640px) {
  .project-workspace-metric-strip {
    grid-template-columns: 1fr;
  }
}
</style>
