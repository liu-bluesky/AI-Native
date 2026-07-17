<template>
  <article
    :class="[
      'execution-flow-node',
      `kind-${data.nodeKind || 'stage'}`,
      `is-${data.visualType || 'observation'}`,
      `status-${data.status || 'completed'}`,
      selected ? 'is-selected' : '',
    ]"
  >
    <Handle type="target" :position="Position.Top" class="execution-flow-handle" />
    <header>
      <span class="execution-flow-node__index">{{ data.order }}</span>
      <span class="execution-flow-node__type">{{ data.typeLabel }}</span>
      <span class="execution-flow-node__status">{{ data.statusLabel }}</span>
    </header>
    <strong>{{ data.title }}</strong>
    <p>{{ data.summary }}</p>
    <footer>
      <span v-if="data.eventCount > 1">{{ data.eventCount }} 个原始事件</span>
      <span v-if="data.modelStepIndex">第 {{ data.modelStepIndex }} 轮</span>
      <span v-if="data.contextMessageCount">上下文 {{ data.contextMessageCount }} 条</span>
      <span v-if="data.modelTotalTokens">实际 {{ data.modelTotalTokens }} Token</span>
      <span v-else-if="data.contextInputTokens">预估 ≈ {{ data.contextInputTokens }} Token</span>
      <span v-if="data.durationLabel !== '—'">{{ data.durationLabel }}</span>
      <span v-if="data.toolName">{{ data.toolName }}</span>
    </footer>
    <Handle type="source" :position="Position.Bottom" class="execution-flow-handle" />
  </article>
</template>

<script setup>
import { Handle, Position } from "@vue-flow/core";

defineProps({
  data: {
    type: Object,
    required: true,
  },
  selected: {
    type: Boolean,
    default: false,
  },
});
</script>

<style scoped>
.execution-flow-node {
  --node-accent: #64748b;
  position: relative;
  width: 320px;
  min-height: 150px;
  padding: 16px;
  border: 1px solid color-mix(in srgb, var(--node-accent) 26%, #dbe3ee);
  border-left: 5px solid var(--node-accent);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.1);
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}

.execution-flow-node:hover,
.execution-flow-node.is-selected {
  border-color: var(--node-accent);
  box-shadow: 0 16px 34px color-mix(in srgb, var(--node-accent) 18%, transparent);
  transform: translateY(-2px);
}

.execution-flow-node.kind-stage {
  border-left-width: 7px;
  background: linear-gradient(135deg, #fff, color-mix(in srgb, var(--node-accent) 7%, #fff));
}

.execution-flow-node.kind-cycle {
  margin-left: 18px;
  border-radius: 12px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
}

.execution-flow-node.is-request,
.execution-flow-node.is-observation {
  --node-accent: #64748b;
}

.execution-flow-node.is-context_build,
.execution-flow-node.is-plan {
  --node-accent: #7c3aed;
}

.execution-flow-node.is-model_call {
  --node-accent: #2563eb;
}

.execution-flow-node.is-tool_call {
  --node-accent: #0891b2;
}

.execution-flow-node.is-operation,
.execution-flow-node.is-resume {
  --node-accent: #0f766e;
}

.execution-flow-node.is-permission,
.execution-flow-node.is-retry {
  --node-accent: #d97706;
}

.execution-flow-node.is-final_answer {
  --node-accent: #16a34a;
}

.execution-flow-node.is-error,
.execution-flow-node.status-failed,
.execution-flow-node.status-blocked {
  --node-accent: #dc2626;
}

.execution-flow-node header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.execution-flow-node__index {
  display: inline-grid;
  width: 24px;
  height: 24px;
  border-radius: 8px;
  place-items: center;
  color: #fff;
  background: var(--node-accent);
  font-size: 12px;
  font-weight: 800;
}

.execution-flow-node__type {
  color: var(--node-accent);
  font-size: 12px;
  font-weight: 800;
}

.execution-flow-node__status {
  margin-left: auto;
  padding: 3px 7px;
  border-radius: 999px;
  color: #475569;
  background: #f1f5f9;
  font-size: 11px;
  font-weight: 700;
}

.execution-flow-node strong {
  display: block;
  color: #0f172a;
  font-size: 16px;
  line-height: 1.4;
}

.execution-flow-node p {
  display: -webkit-box;
  margin: 8px 0 12px;
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.execution-flow-node footer {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.execution-flow-node footer span {
  padding: 4px 7px;
  border-radius: 7px;
  color: #475569;
  background: #f8fafc;
  font-size: 11px;
  font-weight: 600;
}

:deep(.execution-flow-handle) {
  width: 10px;
  height: 10px;
  border: 2px solid #fff;
  background: var(--node-accent);
}
</style>
