<template>
  <ul v-if="items.length" class="task-tree-issue-list">
    <li v-for="(issue, index) in items" :key="`${issue.code}-${index}`">
      {{ issue.message }}
    </li>
  </ul>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { TaskTreeHealthIssue } from "./taskTreeFeedback";

const props = withDefaults(
  defineProps<{
    issues?: TaskTreeHealthIssue[] | null;
    max?: number;
  }>(),
  {
    issues: () => [],
    max: 3,
  },
);

const items = computed(() => {
  const safeIssues = Array.isArray(props.issues) ? props.issues : [];
  return safeIssues.slice(0, Math.max(0, Number(props.max || 0)));
});
</script>

<style scoped>
.task-tree-issue-list {
  margin: 0;
  padding-left: 18px;
  color: rgba(31, 41, 55, 0.78);
  font-size: 13px;
  line-height: 1.7;
}
</style>
