<template>
  <div class="chat-reasoning-row" :data-state="running ? 'running' : 'ok'">
    <button
      type="button"
      class="chat-reasoning-row__head"
      :disabled="!expandable"
      :aria-expanded="expandable ? expanded : undefined"
      @click="toggleExpanded"
    >
      <span class="chat-reasoning-row__icon" aria-hidden="true">✦</span>
      <span class="chat-reasoning-row__title">思考</span>
      <span class="chat-reasoning-row__separator" aria-hidden="true"></span>
      <span class="chat-reasoning-row__summary">{{ summary }}</span>
      <span v-if="duration" class="chat-reasoning-row__duration">{{ duration }}</span>
      <span v-if="expandable" class="chat-reasoning-row__chevron" aria-hidden="true">
        <svg viewBox="0 0 16 16" width="12" height="12">
          <path d="m6 3 5 5-5 5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" />
        </svg>
      </span>
    </button>
    <span v-if="running" class="chat-reasoning-row__a11y">思考中</span>
    <div v-if="expanded && expandable" class="chat-reasoning-row__body">
      <div
        v-for="block in blocks"
        :key="block.id"
        class="chat-reasoning-row__block"
        v-html="renderBlock(block.text)"
      ></div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  blocks: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
  placeholder: { type: String, default: "正在理解你的需求…" },
  duration: { type: String, default: "" },
  renderHtml: { type: Function, default: null },
});

const expanded = ref(false);
const reasoningText = computed(() =>
  props.blocks
    .map((block) => String(block?.text || "").trim())
    .filter(Boolean)
    .join("\n\n"),
);
const expandable = computed(() => Boolean(reasoningText.value));
function compactSummaryLine(value) {
  return String(value || "")
    .replace(/\*{4,}/g, " · ")
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1")
    .replace(/(^|\s)[#>*_`~]+/g, "$1")
    .replace(/[*_`~]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
function localizeReasoningText(value) {
  const text = String(value || "").trim();
  const replacements = [
    [/^listing local resource agents$/i, "正在列出本地智能体资源"],
    [/^planning parallel authorized file deletions$/i, "正在规划并行删除已授权文件"],
    [/^reading (.+)$/i, "正在读取 $1"],
    [/^deleting (.+)$/i, "正在删除 $1"],
    [/^checking (.+)$/i, "正在检查 $1"],
    [/^searching (.+)$/i, "正在搜索 $1"],
    [/^writing (.+)$/i, "正在写入 $1"],
    [/^running (.+)$/i, "正在执行 $1"],
  ];
  return replacements.reduce((result, [pattern, replacement]) =>
    pattern.test(result) ? result.replace(pattern, replacement) : result,
  text);
}
const summary = computed(() => {
  if (!reasoningText.value) return props.placeholder;
  const lines = reasoningText.value
    .split(/\r?\n|\*{4,}/)
    .map((line) => localizeReasoningText(compactSummaryLine(line)))
    .filter(Boolean);
  return props.running ? lines[lines.length - 1] || props.placeholder : lines[0] || props.placeholder;
});

function renderBlock(text) {
  const localized = String(text || "")
    .split(/\r?\n/)
    .map(localizeReasoningText)
    .join("\n");
  return props.renderHtml ? props.renderHtml(localized) : localized;
}

function toggleExpanded() {
  if (!expandable.value) return;
  expanded.value = !expanded.value;
}

</script>

<style scoped>
.chat-reasoning-row {
  display: flex;
  flex-direction: column;
  margin: 6px 14px 2px 12px;
}

.chat-reasoning-row__head {
  position: relative;
  display: flex;
  width: 100%;
  min-height: 28px;
  align-items: center;
  padding: 2px 8px;
  overflow: hidden;
  border: 0;
  border-radius: 6px;
  color: #64748b;
  background: transparent;
  cursor: pointer;
  font: 400 13px/24px var(--el-font-family);
  text-align: left;
}

.chat-reasoning-row__head:hover,
.chat-reasoning-row__head:focus-visible {
  color: #334155;
  background: rgba(241, 245, 249, 0.9);
}

.chat-reasoning-row__head:focus-visible {
  outline: 1px solid rgba(59, 130, 246, 0.62);
  outline-offset: 1px;
}

.chat-reasoning-row__head:disabled {
  cursor: default;
  opacity: 1;
}

.chat-reasoning-row__head:disabled:hover {
  background: transparent;
}

.chat-reasoning-row[data-state="running"] .chat-reasoning-row__head::after {
  content: "";
  position: absolute;
  inset-block: 0;
  left: -300px;
  width: 300px;
  background: linear-gradient(90deg, transparent 0%, rgba(248, 250, 252, 0.82) 55%, transparent 100%);
  animation: chat-reasoning-sweep 2.6s ease-out infinite;
  pointer-events: none;
}

.chat-reasoning-row__icon,
.chat-reasoning-row__title,
.chat-reasoning-row__separator,
.chat-reasoning-row__summary,
.chat-reasoning-row__duration,
.chat-reasoning-row__chevron {
  position: relative;
  z-index: 1;
}

.chat-reasoning-row__icon {
  width: 18px;
  flex: none;
  color: #64748b;
  font-size: 14px;
  text-align: center;
}

.chat-reasoning-row__title {
  flex: none;
  color: #475569;
}

.chat-reasoning-row__separator {
  width: 3px;
  height: 3px;
  flex: none;
  margin: 0 8px;
  border-radius: 50%;
  background: #cbd5e1;
}

.chat-reasoning-row__summary {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: #94a3b8;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-reasoning-row__duration {
  flex: none;
  margin-left: 8px;
  color: #94a3b8;
  font-size: 11px;
}

.chat-reasoning-row__chevron {
  display: inline-flex;
  width: 12px;
  height: 12px;
  flex: none;
  margin-left: 8px;
  color: #94a3b8;
  transition: transform 160ms ease-out;
}

.chat-reasoning-row__head[aria-expanded="true"] .chat-reasoning-row__chevron {
  transform: rotate(90deg);
}

.chat-reasoning-row__body {
  max-height: 360px;
  margin: 2px 8px 8px 30px;
  padding: 4px 10px;
  overflow: auto;
  border-left: 1px solid rgba(148, 163, 184, 0.36);
  color: #64748b;
  font-size: 13px;
  line-height: 1.62;
  overflow-wrap: anywhere;
}

.chat-reasoning-row__block + .chat-reasoning-row__block {
  margin-top: 10px;
}

.chat-reasoning-row__block :deep(p:first-child) {
  margin-top: 0;
}

.chat-reasoning-row__block :deep(p:last-child) {
  margin-bottom: 0;
}

.chat-reasoning-row__a11y {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

@keyframes chat-reasoning-sweep {
  0% { left: -300px; }
  90%, 100% { left: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .chat-reasoning-row[data-state="running"] .chat-reasoning-row__head::after {
    animation: none;
  }

  .chat-reasoning-row__chevron {
    transition: none;
  }
}
</style>
