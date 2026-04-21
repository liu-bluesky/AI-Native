<template>
  <section class="project-app-section">
    <div v-if="eyebrow || title || description || $slots.actions" class="project-app-section__header">
      <div class="project-app-section__title">
        <div v-if="eyebrow" class="project-app-section__eyebrow">{{ eyebrow }}</div>
        <h4 v-if="title">{{ title }}</h4>
        <p v-if="description">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="project-app-section__actions">
        <slot name="actions" />
      </div>
    </div>

    <div class="project-app-section__content" :class="contentClass">
      <slot />
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
    default: '',
  },
  description: {
    type: String,
    default: '',
  },
  contentClass: {
    type: [String, Array, Object],
    default: '',
  },
})
</script>

<style scoped>
.project-app-section {
  min-width: 0;
  padding: clamp(16px, 1.8vw, 24px);
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.68);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.project-app-section__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.project-app-section__title,
.project-app-section__actions {
  min-width: 0;
}

.project-app-section__eyebrow {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.project-app-section__title h4 {
  margin: 6px 0 0;
  font-size: clamp(20px, 2.2vw, 24px);
  line-height: 1.15;
  color: #0f172a;
}

.project-app-section__title p {
  margin: 8px 0 0;
  max-width: 60ch;
  color: #64748b;
  line-height: 1.6;
}

.project-app-section__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.project-app-section__content {
  min-width: 0;
}

@media (max-width: 900px) {
  .project-app-section__header {
    flex-direction: column;
  }

  .project-app-section__actions {
    justify-content: flex-start;
  }
}
</style>
