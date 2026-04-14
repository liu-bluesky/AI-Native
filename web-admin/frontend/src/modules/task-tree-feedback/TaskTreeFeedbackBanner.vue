<template>
  <div
    v-if="health"
    class="task-tree-feedback-banner"
    :class="`is-${tone}`"
  >
    <div class="task-tree-feedback-banner__head">
      <div>
        <div class="task-tree-feedback-banner__eyebrow">Task Health</div>
        <div class="task-tree-feedback-banner__title">
          {{ label }}
        </div>
      </div>
      <el-tag size="small" effect="plain" :type="tagType">
        {{ health.health_score }} 分
      </el-tag>
    </div>
    <div class="task-tree-feedback-banner__summary">
      {{ summary }}
    </div>
    <div class="task-tree-feedback-banner__meta">
      <span v-if="health.detected_intent">意图 {{ health.detected_intent }}</span>
      <span>问题 {{ health.issue_count || 0 }} 条</span>
      <span v-if="health.rebuild_recommended">建议先重建再继续</span>
    </div>
    <TaskTreeIssueList :issues="health.issues" :max="maxIssues" />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import TaskTreeIssueList from "./TaskTreeIssueList.vue";
import {
  getTaskTreeHealthLabel,
  getTaskTreeHealthSummary,
  getTaskTreeHealthTagType,
  getTaskTreeHealthTone,
  type TaskTreeHealth,
} from "./taskTreeFeedback";

const props = withDefaults(
  defineProps<{
    health?: TaskTreeHealth | null;
    maxIssues?: number;
  }>(),
  {
    health: null,
    maxIssues: 3,
  },
);

const tone = computed(() => getTaskTreeHealthTone(props.health));
const tagType = computed(() => getTaskTreeHealthTagType(props.health));
const label = computed(() => getTaskTreeHealthLabel(props.health));
const summary = computed(() => getTaskTreeHealthSummary(props.health));
</script>

<style scoped>
.task-tree-feedback-banner {
  display: grid;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.78);
}

.task-tree-feedback-banner.is-danger {
  border-color: rgba(239, 68, 68, 0.24);
  background: rgba(254, 242, 242, 0.9);
}

.task-tree-feedback-banner.is-warning {
  border-color: rgba(245, 158, 11, 0.22);
  background: rgba(255, 251, 235, 0.92);
}

.task-tree-feedback-banner.is-info {
  border-color: rgba(59, 130, 246, 0.2);
  background: rgba(239, 246, 255, 0.92);
}

.task-tree-feedback-banner.is-success {
  border-color: rgba(34, 197, 94, 0.18);
  background: rgba(240, 253, 244, 0.88);
}

.task-tree-feedback-banner__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.task-tree-feedback-banner__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(71, 85, 105, 0.66);
}

.task-tree-feedback-banner__title {
  margin-top: 4px;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.task-tree-feedback-banner__summary,
.task-tree-feedback-banner__meta {
  font-size: 13px;
  line-height: 1.7;
  color: rgba(31, 41, 55, 0.78);
}

.task-tree-feedback-banner__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
}
</style>
