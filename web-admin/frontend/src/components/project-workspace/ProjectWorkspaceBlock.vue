<template>
  <div class="block" :class="blockClass">
    <div v-if="eyebrow || title || $slots.actions" class="block-header" :class="headerClass">
      <div>
        <div v-if="eyebrow" class="block-eyebrow">{{ eyebrow }}</div>
        <h4 v-if="title">{{ title }}</h4>
        <p v-if="description" class="project-workspace-block__description">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="project-workspace-block__actions">
        <slot name="actions" />
      </div>
    </div>

    <slot />
  </div>
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
  blockClass: {
    type: [String, Array, Object],
    default: '',
  },
  headerClass: {
    type: [String, Array, Object],
    default: '',
  },
})
</script>

<style scoped>
.block {
  min-width: 0;
}

.block-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.block-header > * {
  min-width: 0;
}

.block-eyebrow {
  margin-bottom: 8px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.block-header h4 {
  margin: 0;
  color: #334155;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.35;
}

.project-workspace-block__description {
  margin: 8px 0 0;
  max-width: 60ch;
  color: #64748b;
  line-height: 1.6;
}

.project-workspace-block__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
