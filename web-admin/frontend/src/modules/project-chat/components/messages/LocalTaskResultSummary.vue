<template>
  <section class="local-task-result-summary" aria-label="本次任务结果">
    <div class="local-task-result-summary__accent" aria-hidden="true"></div>
    <header class="local-task-result-summary__header">
      <div class="local-task-result-summary__heading">
        <span class="local-task-result-summary__icon" aria-hidden="true">
          <span class="local-task-result-summary__icon-dot"></span>
        </span>
        <div class="local-task-result-summary__heading-copy">
          <span class="local-task-result-summary__eyebrow">本次任务结果</span>
          <strong>{{ statusTitle(summary) }}</strong>
        </div>
      </div>
      <span :class="['local-task-result-summary__status', `is-${statusKey(summary)}`]">
        <span class="local-task-result-summary__status-dot" aria-hidden="true"></span>
        {{ statusLabel(summary) }}
      </span>
    </header>

    <div class="local-task-result-summary__divider"></div>

    <dl class="local-task-result-summary__facts">
      <div class="local-task-result-summary__fact">
        <dt><span class="local-task-result-summary__fact-mark">01</span>本次需求</dt>
        <dd>{{ summary.requestDescription || "未记录" }}</dd>
      </div>
      <div class="local-task-result-summary__fact">
        <dt><span class="local-task-result-summary__fact-mark">02</span>本地改动</dt>
        <dd>{{ summary.changeDescription || "未检测到本地文件改动" }}</dd>
      </div>
    </dl>

    <div v-if="summary.files?.length" class="local-task-result-summary__section">
      <div class="local-task-result-summary__section-heading">
        <div>
          <span class="local-task-result-summary__section-title">修改文件</span>
          <span class="local-task-result-summary__section-caption">{{ summary.files.length }} 个文件</span>
        </div>
      </div>
      <ul class="local-task-result-summary__files-list">
        <li v-for="file in summary.files" :key="`${file.changeType}:${file.path}`">
          <span :class="['local-task-result-summary__file-type', `is-${file.changeType}`]">
            {{ changeLabel(file.changeType) }}
          </span>
          <button
            type="button"
            class="local-task-result-summary__path"
            :title="`打开 ${file.path}`"
            @click="$emit('open-path', file.path)"
          >
            <code>{{ file.path }}</code>
          </button>
        </li>
      </ul>
    </div>

    <div v-if="summary.nextSteps?.length" class="local-task-result-summary__section">
      <div class="local-task-result-summary__section-heading">
        <div>
          <span class="local-task-result-summary__section-title">下一步计划</span>
          <span class="local-task-result-summary__section-caption">{{ summary.nextSteps.length }} 个步骤</span>
        </div>
      </div>
      <ol class="local-task-result-summary__step-nav" aria-label="下一步计划步骤">
        <li v-for="(step, index) in summary.nextSteps" :key="`${index}:${step}`">
          <span class="local-task-result-summary__step-rail" aria-hidden="true">
            <span class="local-task-result-summary__step-index">{{ String(index + 1).padStart(2, "0") }}</span>
          </span>
          <span class="local-task-result-summary__step-text">{{ step }}</span>
        </li>
      </ol>
    </div>

    <div v-if="summary.recordPath" class="local-task-result-summary__record">
      <span class="local-task-result-summary__record-label">记录已留存</span>
      <button
        type="button"
        class="local-task-result-summary__path local-task-result-summary__record-path"
        :title="`打开 ${summary.recordPath}`"
        @click="$emit('open-path', summary.recordPath)"
      >
        <code>{{ summary.recordPath }}</code>
      </button>
    </div>
  </section>
</template>

<script setup>
defineProps({
  summary: {
    type: Object,
    required: true,
  },
});

defineEmits(["open-path"]);

function changeLabel(changeType) {
  return {
    added: "新增",
    modified: "编辑",
    deleted: "删除",
  }[String(changeType || "modified")] || "编辑";
}

function statusKey(summary) {
  if (summary?.status) return String(summary.status).trim().toLowerCase();
  return summary?.completed ? "completed" : "paused";
}

function statusLabel(summary) {
  return {
    running: "执行中",
    paused: "待继续",
    waiting_user: "等待回答",
    waiting_approval: "等待授权",
    failed: "执行失败",
    completed: "已完成",
  }[statusKey(summary)] || "待处理";
}

function statusTitle(summary) {
  return {
    running: "任务执行中",
    paused: "任务已暂停",
    waiting_user: "等待补充信息",
    waiting_approval: "等待本机授权",
    failed: "任务执行失败",
    completed: "任务已完成",
  }[statusKey(summary)] || "任务尚未完成";
}
</script>

<style scoped>
.local-task-result-summary {
  position: relative;
  overflow: hidden;
  margin-top: 14px;
  padding: 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 14px;
  background: var(--el-fill-color-blank);
  box-shadow: 0 5px 18px rgba(15, 23, 42, 0.045);
}

.local-task-result-summary__accent {
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: linear-gradient(90deg, var(--el-color-primary), var(--el-color-primary-light-5));
}

.local-task-result-summary__header,
.local-task-result-summary__heading,
.local-task-result-summary__facts > div,
.local-task-result-summary__record {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.local-task-result-summary__heading {
  justify-content: flex-start;
  align-items: center;
  gap: 11px;
}

.local-task-result-summary__header > div,
.local-task-result-summary__facts > div,
.local-task-result-summary__record,
.local-task-result-summary__step-text {
  min-width: 0;
}

.local-task-result-summary__icon {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-radius: 9px;
  background: var(--el-color-primary-light-9);
}

.local-task-result-summary__icon-dot,
.local-task-result-summary__status-dot {
  display: block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--el-color-primary);
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--el-color-primary) 12%, transparent);
}

.local-task-result-summary__heading-copy {
  min-width: 0;
}

.local-task-result-summary__eyebrow,
.local-task-result-summary dt {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.local-task-result-summary__header strong {
  display: block;
  margin-top: 4px;
  color: var(--el-text-color-primary);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.local-task-result-summary__status,
.local-task-result-summary__file-type {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.local-task-result-summary__status-dot {
  width: 6px;
  height: 6px;
  box-shadow: none;
  background: currentColor;
}

.local-task-result-summary__status.is-completed { color: var(--el-color-success); background: var(--el-color-success-light-9); }
.local-task-result-summary__status.is-running { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.local-task-result-summary__status.is-paused,
.local-task-result-summary__status.is-waiting_user,
.local-task-result-summary__status.is-waiting_approval { color: var(--el-color-warning); background: var(--el-color-warning-light-9); }
.local-task-result-summary__status.is-failed { color: var(--el-color-danger); background: var(--el-color-danger-light-9); }

.local-task-result-summary__divider {
  height: 1px;
  margin: 14px 0;
  background: var(--el-border-color-lighter);
}

.local-task-result-summary__facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.local-task-result-summary__fact {
  display: block !important;
  padding: 0 12px;
  border-left: 2px solid var(--el-color-primary-light-7);
}

.local-task-result-summary dt {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
  font-weight: 600;
}

.local-task-result-summary__fact-mark {
  color: var(--el-color-primary);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
}

.local-task-result-summary dd {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 13px;
  line-height: 1.55;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.local-task-result-summary__section {
  margin-top: 18px;
}

.local-task-result-summary__section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 20px;
}

.local-task-result-summary__section-heading > div {
  display: flex;
  align-items: baseline;
  gap: 9px;
}

.local-task-result-summary__section-title {
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 700;
}

.local-task-result-summary__section-caption {
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.local-task-result-summary__files-list {
  display: grid;
  gap: 6px;
  margin: 9px 0 0;
  padding: 0;
  list-style: none;
}

.local-task-result-summary__files-list li {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 9px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.local-task-result-summary__path {
  display: block;
  min-width: 0;
  padding: 0;
  overflow: hidden;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.local-task-result-summary__path code {
  min-width: 0;
  overflow: hidden;
  color: var(--el-color-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.local-task-result-summary__path:hover code {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.local-task-result-summary__file-type {
  padding: 3px 7px;
  font-size: 11px;
}
.local-task-result-summary__file-type.is-added { color: var(--el-color-success); background: var(--el-color-success-light-9); }
.local-task-result-summary__file-type.is-modified { color: var(--el-color-warning); background: var(--el-color-warning-light-9); }
.local-task-result-summary__file-type.is-deleted { color: var(--el-color-danger); background: var(--el-color-danger-light-9); }

.local-task-result-summary__step-nav {
  display: grid;
  gap: 8px;
  margin: 9px 0 0;
  padding: 0;
  list-style: none;
}

.local-task-result-summary__step-nav li {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  min-width: 0;
  position: relative;
  padding: 3px 0 3px 0;
}

.local-task-result-summary__step-rail {
  position: relative;
  display: grid;
  min-height: 28px;
  place-items: center;
}

.local-task-result-summary__step-nav li:not(:last-child) .local-task-result-summary__step-rail::after {
  position: absolute;
  top: 28px;
  bottom: -11px;
  left: 13px;
  width: 1px;
  content: "";
  background: var(--el-border-color-lighter);
}

.local-task-result-summary__step-index {
  display: inline-grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 8px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--el-color-primary) 10%, transparent);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}
.local-task-result-summary__step-text {
  align-self: center;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.55;
  overflow-wrap: anywhere;
  word-break: break-word;
  white-space: normal;
}
.local-task-result-summary__record {
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.local-task-result-summary__record-label {
  flex: 0 0 auto;
  font-weight: 600;
}

.local-task-result-summary__record code {
  display: block;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
  white-space: normal;
  color: var(--el-color-primary);
}

.local-task-result-summary__record-path {
  flex: 1 1 100%;
}

@media (max-width: 560px) {
  .local-task-result-summary {
    padding: 12px;
  }

  .local-task-result-summary__header {
    display: grid;
    gap: 12px;
  }

  .local-task-result-summary__status {
    justify-self: start;
  }

  .local-task-result-summary__facts {
    grid-template-columns: minmax(0, 1fr);
  }

  .local-task-result-summary__files-list li {
    align-items: flex-start;
  }

  .local-task-result-summary__files-list code,
  .local-task-result-summary__record code {
    white-space: normal;
    overflow-wrap: anywhere;
    word-break: break-word;
  }
}
</style>
