<template>
<div class="chat-tool-row" :data-state="state" :data-variant="variant" :data-open="expanded || undefined">
    <button
      type="button"
      class="chat-tool-row__head"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <span class="chat-tool-row__leading" aria-hidden="true">
        <span class="chat-tool-row__icon">
        <svg viewBox="0 0 24 24" focusable="false">
          <path :d="variantIconPath" />
        </svg>
        </span>
        <span class="chat-tool-row__leading-chevron">
          <svg viewBox="0 0 16 16" width="14" height="14">
            <path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" />
          </svg>
        </span>
      </span>
      <span class="chat-tool-row__copy">
        <span class="chat-tool-row__title">{{ title }}</span>
        <span
          v-if="collapsedSummary && collapsedSummary !== title"
          class="chat-tool-row__summary"
          :class="{ 'is-error': state === 'error' }"
        >
          {{ collapsedSummary }}
        </span>
      </span>
      <span v-if="state === 'error'" class="chat-tool-row__state-dot" aria-hidden="true"></span>
      <span class="chat-tool-row__a11y">{{ stateLabel }}</span>
    </button>

    <div v-if="expanded" class="chat-tool-row__body">
      <div v-if="variant === 'terminal'" class="chat-tool-card chat-tool-card--terminal">
        <div v-if="command" class="chat-tool-card__terminal-head">
          <span>$</span><code>{{ command }}</code>
        </div>
        <div v-if="cwd || exitCode" class="chat-tool-card__meta">
          <span v-if="cwd">{{ cwd }}</span>
          <span v-if="exitCode">exit {{ exitCode }}</span>
        </div>
        <pre v-if="output" class="chat-tool-card__terminal-output">{{ output }}</pre>
      </div>

      <div v-else-if="variant === 'edit'" class="chat-tool-card chat-tool-card--diff">
        <div
          v-for="line in outputLines"
          :key="line.id"
          class="chat-tool-card__diff-line"
          :class="`is-${diffLineTone(line.text)}`"
        >{{ line.text }}</div>
      </div>

      <div v-else-if="variant === 'read'" class="chat-tool-card chat-tool-card--read">
        <div v-for="line in outputLines" :key="line.id" class="chat-tool-card__read-line">
          <span>{{ line.number }}</span><code>{{ line.text }}</code>
        </div>
      </div>

      <div v-else-if="variant === 'search' || variant === 'web'" class="chat-tool-card chat-tool-card--results">
        <div v-for="line in outputLines" :key="line.id" class="chat-tool-card__result-line">
          <span aria-hidden="true">{{ variant === 'web' ? '↗' : '⌕' }}</span>
          <code>{{ line.text }}</code>
        </div>
      </div>

      <div v-else class="chat-tool-card chat-tool-card--io">
        <div v-if="inputText" class="chat-tool-card__io-section">
          <span>IN</span><pre>{{ inputText }}</pre>
        </div>
        <div v-if="inputText && output" class="chat-tool-card__divider"></div>
        <div v-if="output" class="chat-tool-card__io-section">
          <span>OUT</span><pre :class="{ 'is-error': state === 'error' }">{{ output }}</pre>
        </div>
      </div>

      <p v-if="detail && !output" class="chat-tool-row__detail">{{ detail }}</p>
      <div v-if="actions.length" class="chat-tool-row__actions">
        <el-button
          v-for="action in actions"
          :key="action.key"
          size="small"
          :type="action.type === 'danger' ? 'danger' : 'primary'"
          :plain="action.type !== 'danger'"
          @click.stop="$emit('action', action.key)"
        >{{ action.label }}</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import {
  chatToolStateLabel,
  classifyChatTool,
  diffLineTone,
  normalizeChatToolState,
  splitToolOutputLines,
} from "./chatToolPresentation.js";

const props = defineProps({
  operation: { type: Object, required: true },
  title: { type: String, default: "工具调用" },
  preview: { type: String, default: "" },
  detail: { type: String, default: "" },
  command: { type: String, default: "" },
  cwd: { type: String, default: "" },
  argumentsText: { type: String, default: "" },
  output: { type: String, default: "" },
  exitCode: { type: String, default: "" },
  actions: { type: Array, default: () => [] },
});

defineEmits(["action"]);

const expanded = ref(false);
const variant = computed(() => classifyChatTool(props.operation));
const state = computed(() => normalizeChatToolState(props.operation?.phase || props.operation?.status));
const stateLabel = computed(() => chatToolStateLabel(state.value));
const outputLines = computed(() => splitToolOutputLines(props.output || props.detail));
const inputText = computed(() => [props.command, props.cwd, props.argumentsText].filter(Boolean).join("\n"));
const collapsedSummary = computed(() => {
  if (state.value === "error" && props.output) return props.output.split(/\r?\n/)[0];
  return props.preview || props.command || props.detail || stateLabel.value;
});
const variantIconPath = computed(() => {
  if (variant.value === "terminal") {
    return "M5 7.5 9.5 12 5 16.5M12.5 16.5H19";
  }
  if (variant.value === "edit") {
    return "m14.5 5.5 4 4M6 18l3.2-.7L19.2 7.3a1.7 1.7 0 0 0-2.4-2.4L6.8 14.9 6 18Z";
  }
  if (variant.value === "read") {
    return "M6 4.5h12v15H6zM9 8h6M9 12h6M9 16h4";
  }
  if (variant.value === "search") {
    return "m20 20-4.2-4.2M10.8 17a6.2 6.2 0 1 1 0-12.4 6.2 6.2 0 0 1 0 12.4Z";
  }
  if (variant.value === "web") {
    return "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM3.5 12h17M12 3c2.2 2.4 3.3 5.4 3.3 9S14.2 18.6 12 21c-2.2-2.4-3.3-5.4-3.3-9S9.8 5.4 12 3Z";
  }
  return "M12 4.5v15M4.5 12h15";
});

watch(
  state,
  (nextState) => {
    if (nextState === "waiting") expanded.value = true;
  },
  { immediate: true },
);
</script>

<style scoped>
.chat-tool-row {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
}

.chat-tool-row__head {
  position: relative;
  display: flex;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  min-height: 24px;
  align-items: flex-start;
  padding: 0;
  overflow: hidden;
  border: 0;
  border-radius: 4px;
  color: #64748b;
  background: transparent;
  cursor: pointer;
  font: 400 13px/24px var(--el-font-family);
  text-align: left;
}

.chat-tool-row__head:hover,
.chat-tool-row__head:focus-visible {
  color: #334155;
  background: transparent;
}

.chat-tool-row__head:focus-visible {
  outline: 1px solid rgba(59, 130, 246, 0.62);
  outline-offset: 1px;
}

.chat-tool-row[data-state="running"] .chat-tool-row__head::after {
  content: "";
  position: absolute;
  inset-block: 0;
  left: -300px;
  width: 300px;
  background: linear-gradient(90deg, transparent 0%, rgba(248, 250, 252, 0.82) 55%, transparent 100%);
  animation: chat-tool-row-sweep 2.6s ease-out infinite;
  pointer-events: none;
}

.chat-tool-row__leading,
.chat-tool-row__icon,
.chat-tool-row__leading-chevron,
.chat-tool-row__copy,
.chat-tool-row__title,
.chat-tool-row__summary,
.chat-tool-row__state-dot,
.chat-tool-row__chevron {
  position: relative;
  z-index: 1;
}

.chat-tool-row__leading {
  position: relative;
  display: inline-flex;
  width: 16px;
  height: 16px;
  flex: none;
  align-items: center;
  justify-content: center;
  margin: 4px 8px 0 0;
  color: #94a3b8;
}

.chat-tool-row__icon,
.chat-tool-row__leading-chevron {
  display: inline-flex;
  width: 14px;
  height: 14px;
  align-items: center;
  justify-content: center;
  transition: opacity 100ms ease, transform 100ms ease;
}

.chat-tool-row__icon svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.55;
}

.chat-tool-row__leading-chevron {
  position: absolute;
  inset: 1px;
  opacity: 0;
  transform: rotate(-90deg);
}

.chat-tool-row[data-open="true"] .chat-tool-row__leading-chevron {
  opacity: 1;
}

.chat-tool-row[data-open="true"] .chat-tool-row__leading-chevron {
  transform: rotate(0deg);
}

.chat-tool-row__copy {
  width: 0;
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 18px;
}

.chat-tool-row__title {
  max-width: 100%;
  min-width: 0;
  overflow-wrap: anywhere;
  color: #334155;
  font-weight: 600;
  line-height: 18px;
  word-break: break-word;
  white-space: normal;
}

.chat-tool-row__summary {
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
  color: #94a3b8;
  font-size: 12px;
  line-height: 18px;
  word-break: break-word;
  white-space: normal;
}

.chat-tool-row__summary.is-error {
  color: #dc2626;
}

.chat-tool-row__state-dot {
  width: 6px;
  height: 6px;
  flex: none;
  margin: 9px 2px 0 6px;
  border-radius: 50%;
  background: #94a3b8;
}

.chat-tool-row[data-state="error"] .chat-tool-row__state-dot { background: #ef4444; }

.chat-tool-row__chevron {
  display: inline-flex;
  width: 12px;
  height: 12px;
  flex: none;
  margin-left: 6px;
  color: #94a3b8;
  transition: transform 160ms ease-out;
}

.chat-tool-row__head[aria-expanded="true"] .chat-tool-row__chevron {
  transform: rotate(90deg);
}

.chat-tool-row__a11y {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.chat-tool-row__body {
  min-width: 0;
  margin: 4px 0 8px 22px;
}

.chat-tool-card {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  border: 1px solid rgba(203, 213, 225, 0.72);
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.92);
  color: #475569;
  font: 12px/1.55 ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
}

.chat-tool-card__terminal-head {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 6px;
  padding: 9px 11px;
  background: #111827;
  color: #e5e7eb;
}

.chat-tool-card__terminal-head code,
.chat-tool-card__result-line code,
.chat-tool-card__read-line code {
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.chat-tool-card__meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  padding: 5px 11px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.6);
  color: #64748b;
  background: rgba(226, 232, 240, 0.58);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.chat-tool-card__terminal-output {
  max-height: 260px;
  margin: 0;
  padding: 10px 11px;
  overflow: auto;
  background: #0f172a;
  color: #e5e7eb;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-tool-card--diff,
.chat-tool-card--read,
.chat-tool-card--results {
  max-height: 280px;
  overflow: auto;
}

.chat-tool-card__diff-line {
  min-width: 0;
  padding: 1px 11px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.chat-tool-card__diff-line.is-add { background: rgba(22, 101, 52, 0.13); color: #166534; }
.chat-tool-card__diff-line.is-remove { background: rgba(185, 28, 28, 0.12); color: #b91c1c; }
.chat-tool-card__diff-line.is-hunk { background: rgba(37, 99, 235, 0.1); color: #1d4ed8; font-weight: 600; }
.chat-tool-card__diff-line.is-meta { color: #64748b; font-weight: 600; }

.chat-tool-card__read-line {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
}

.chat-tool-card__read-line > span {
  padding: 1px 9px;
  border-right: 1px solid rgba(203, 213, 225, 0.58);
  color: #94a3b8;
  text-align: right;
  user-select: none;
}

.chat-tool-card__read-line > code {
  padding: 1px 10px;
}

.chat-tool-card__result-line {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 6px;
  padding: 5px 10px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.76);
}

.chat-tool-card__result-line:last-child { border-bottom: 0; }
.chat-tool-card__result-line > span { color: #94a3b8; }

.chat-tool-card__io-section {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  max-height: 180px;
  padding: 10px 12px;
  overflow: auto;
}

.chat-tool-card__io-section > span { color: #94a3b8; font-size: 10px; }
.chat-tool-card__io-section pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
.chat-tool-card__io-section pre.is-error { color: #dc2626; }
.chat-tool-card__divider { height: 1px; background: rgba(203, 213, 225, 0.66); }

.chat-tool-row__detail {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}

.chat-tool-row__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

@keyframes chat-tool-row-sweep {
  0% { left: -300px; }
  90%, 100% { left: 100%; }
}

@media (max-width: 720px) {
  .chat-tool-row__body { margin-left: 18px; margin-right: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .chat-tool-row[data-state="running"] .chat-tool-row__head::after { animation: none; }
  .chat-tool-row__chevron { transition: none; }
}
</style>
