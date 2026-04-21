<template>
  <section class="project-app-header">
    <div class="project-app-header__copy">
      <div v-if="badges.length" class="project-app-header__badges">
        <el-tag
          v-for="badge in badges"
          :key="badge.key || badge.label"
          size="small"
          effect="plain"
          :type="badge.type || 'info'"
        >
          {{ badge.label }}
        </el-tag>
      </div>

      <div class="project-app-header__heading">
        <div v-if="eyebrow" class="project-app-header__eyebrow">{{ eyebrow }}</div>
        <h3>{{ title }}</h3>
        <p v-if="description">{{ description }}</p>
      </div>

      <div v-if="stats.length" class="project-app-header__stats">
        <article
          v-for="item in stats"
          :key="item.key || item.label"
          class="project-app-header__stat"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small v-if="item.meta">{{ item.meta }}</small>
        </article>
      </div>
    </div>

    <div class="project-app-header__panel">
      <div v-if="panelTitle || panelDescription || panelEyebrow" class="project-app-header__panel-copy">
        <div v-if="panelEyebrow" class="project-app-header__eyebrow">{{ panelEyebrow }}</div>
        <h4 v-if="panelTitle">{{ panelTitle }}</h4>
        <p v-if="panelDescription">{{ panelDescription }}</p>
      </div>

      <div v-if="$slots.actions" class="project-app-header__actions">
        <slot name="actions" />
      </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  eyebrow: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    default: '',
  },
  panelEyebrow: {
    type: String,
    default: '',
  },
  panelTitle: {
    type: String,
    default: '',
  },
  panelDescription: {
    type: String,
    default: '',
  },
  badges: {
    type: Array,
    default: () => [],
  },
  stats: {
    type: Array,
    default: () => [],
  },
})
</script>

<style scoped>
.project-app-header {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.9fr);
  gap: 14px;
  padding: clamp(18px, 2vw, 24px);
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.project-app-header__copy,
.project-app-header__panel {
  min-width: 0;
}

.project-app-header__copy {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.project-app-header__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.project-app-header__heading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-app-header__eyebrow {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.project-app-header__heading h3 {
  margin: 0;
  max-width: 14ch;
  font-size: clamp(24px, 3vw, 34px);
  line-height: 1.04;
  letter-spacing: -0.03em;
  color: #0f172a;
}

.project-app-header__heading p,
.project-app-header__panel-copy p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #475569;
}

.project-app-header__stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 10px;
}

.project-app-header__stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  background: rgba(248, 250, 252, 0.78);
}

.project-app-header__stat span,
.project-app-header__stat small {
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.project-app-header__stat strong {
  color: #0f172a;
  font-size: 22px;
  line-height: 1.1;
}

.project-app-header__panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(125, 211, 252, 0.16), transparent 34%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.9), rgba(248, 250, 252, 0.84));
}

.project-app-header__panel-copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.project-app-header__panel-copy h4 {
  margin: 0;
  font-size: 18px;
  line-height: 1.15;
  color: #0f172a;
}

.project-app-header__actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-app-header__actions :deep(.el-button) {
  margin-left: 0;
}

@media (max-width: 900px) {
  .project-app-header {
    grid-template-columns: 1fr;
  }

  .project-app-header__heading h3 {
    max-width: none;
  }
}
</style>
