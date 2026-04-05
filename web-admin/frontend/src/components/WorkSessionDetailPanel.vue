<template>
  <div class="work-session-detail-shell">
    <section class="work-session-detail-hero">
      <div class="work-session-detail-hero__content">
        <div class="work-session-detail-eyebrow">Session Summary</div>
        <h4>{{ session.goal || session.session_id || "未命名工作轨迹" }}</h4>
        <p>
          {{
            (session.steps || []).join(" / ")
              || (session.verification || []).join(" / ")
              || "这条轨迹保留了阶段推进、验证结果和后续动作。"
          }}
        </p>
      </div>
      <div class="work-session-detail-hero__status">
        <div class="work-session-detail-card">
          <span>状态</span>
          <strong>{{ session.latest_status || "-" }}</strong>
        </div>
        <div class="work-session-detail-card">
          <span>事件数</span>
          <strong>{{ Number(session.event_count || 0) }}</strong>
        </div>
        <div class="work-session-detail-card">
          <span>更新时间</span>
          <strong>{{ formatDateTime(session.updated_at) }}</strong>
        </div>
      </div>
    </section>

    <section class="work-session-detail-meta-grid">
      <div class="work-session-detail-card">
        <span>Session</span>
        <strong>{{ session.session_id || "-" }}</strong>
      </div>
      <div class="work-session-detail-card">
        <span>员工</span>
        <strong>{{ session.employee_name || session.employee_id || "-" }}</strong>
      </div>
      <div class="work-session-detail-card">
        <span>阶段</span>
        <strong>{{ (session.phases || []).join(" / ") || "-" }}</strong>
      </div>
      <div class="work-session-detail-card">
        <span>步骤</span>
        <strong>{{ (session.steps || []).join(" / ") || "-" }}</strong>
      </div>
      <div class="work-session-detail-card">
        <span>任务树</span>
        <strong>{{ session.task_tree_session_id || session.task_tree_chat_session_id || "-" }}</strong>
      </div>
      <div class="work-session-detail-card">
        <span>节点</span>
        <strong>{{ session.task_node_title || (session.task_node_titles || []).join(" / ") || "-" }}</strong>
      </div>
    </section>

    <section class="work-session-detail-content-grid">
      <article class="work-session-detail-section">
        <div class="work-session-detail-section__header">
          <div>
            <div class="work-session-detail-eyebrow">Verification</div>
            <h4>验证</h4>
          </div>
        </div>
        <div class="work-session-detail-block">
          {{ (session.verification || []).join("\n") || "-" }}
        </div>
      </article>

      <article class="work-session-detail-section">
        <div class="work-session-detail-section__header">
          <div>
            <div class="work-session-detail-eyebrow">Files</div>
            <h4>变更文件</h4>
          </div>
        </div>
        <div class="work-session-detail-block">
          {{ (session.changed_files || []).join("\n") || "-" }}
        </div>
      </article>

      <article class="work-session-detail-section">
        <div class="work-session-detail-section__header">
          <div>
            <div class="work-session-detail-eyebrow">Risks</div>
            <h4>风险</h4>
          </div>
        </div>
        <div class="work-session-detail-block">
          {{ (session.risks || []).join("\n") || "-" }}
        </div>
      </article>

      <article class="work-session-detail-section">
        <div class="work-session-detail-section__header">
          <div>
            <div class="work-session-detail-eyebrow">Next</div>
            <h4>下一步</h4>
          </div>
        </div>
        <div class="work-session-detail-block">
          {{ (session.next_steps || []).join("\n") || "-" }}
        </div>
      </article>

      <article class="work-session-detail-section work-session-detail-section--full">
        <div class="work-session-detail-section__header">
          <div>
            <div class="work-session-detail-eyebrow">Timeline</div>
            <h4>事件时间线</h4>
          </div>
        </div>
        <div class="work-session-detail-plan">
          <article
            v-for="item in events"
            :key="item.id || `${item.created_at}-${item.event_type}`"
            class="work-session-detail-plan__item"
          >
            <div class="work-session-detail-plan__row">
              <div class="work-session-detail-plan__title-group">
                <span class="work-session-detail-plan__index">{{ item.event_type || item.source_kind || "-" }}</span>
                <strong>{{ item.phase || "未标注阶段" }}<template v-if="item.step"> / {{ item.step }}</template></strong>
              </div>
              <el-tag class="work-session-detail-status" size="small" :type="statusTagType(resolveEventStatus(item))">
                {{ resolveEventStatusLabel(item) }}
              </el-tag>
            </div>
            <div class="work-session-detail-plan__desc">
              {{ item.goal || item.content || (item.facts || []).join("\n") || "-" }}
            </div>
            <div v-if="eventStatusHint(item)" class="work-session-detail-subtext">
              {{ eventStatusHint(item) }}
            </div>
            <div
              v-if="item.task_tree_session_id || item.task_node_title || item.task_tree_chat_session_id"
              class="work-session-detail-subtext"
            >
              任务树:
              {{ item.task_tree_session_id || item.task_tree_chat_session_id || "-" }}
              <template v-if="item.task_node_title">
                · 节点: {{ item.task_node_title }}
              </template>
            </div>
            <div v-if="item.verification?.length" class="work-session-detail-plan__verification">
              <span>验证</span>
              <p>{{ item.verification.join("\n") }}</p>
            </div>
            <div class="work-session-detail-subtext">{{ formatDateTime(item.created_at) }}</div>
          </article>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";

import { formatDateTime } from "@/utils/date.js";

const props = defineProps({
  session: {
    type: Object,
    default: null,
  },
  events: {
    type: Array,
    default: () => [],
  },
});

const session = computed(() => (props.session && typeof props.session === "object" ? props.session : {}));
const events = computed(() => (Array.isArray(props.events) ? props.events : []));

function normalizeStatus(value) {
  return String(value || "").trim().toLowerCase();
}

function isTerminalStatus(value) {
  return ["completed", "done", "failed", "blocked"].includes(normalizeStatus(value));
}

function resolveEventStatus(item) {
  const eventStatus = normalizeStatus(item?.status);
  const latestStatus = normalizeStatus(session.value?.latest_status);
  const eventType = String(item?.event_type || "").trim().toLowerCase();
  if (eventType === "start" && latestStatus && latestStatus !== eventStatus && isTerminalStatus(latestStatus)) {
    return latestStatus;
  }
  return eventStatus || latestStatus || "";
}

function resolveEventStatusLabel(item) {
  const value = resolveEventStatus(item);
  return value || "-";
}

function eventStatusHint(item) {
  const eventType = String(item?.event_type || "").trim().toLowerCase();
  const rawStatus = normalizeStatus(item?.status);
  const displayStatus = resolveEventStatus(item);
  if (eventType === "start" && rawStatus && displayStatus && rawStatus !== displayStatus) {
    return `起始事件原始状态为 ${rawStatus}，当前会话已更新为 ${displayStatus}。`;
  }
  return "";
}

function statusTagType(value) {
  const normalized = normalizeStatus(value);
  if (normalized === "completed" || normalized === "done") return "success";
  if (normalized === "blocked" || normalized === "failed") return "danger";
  if (normalized === "in_progress" || normalized === "verifying") return "warning";
  return "info";
}
</script>

<style scoped>
.work-session-detail-shell {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.work-session-detail-hero,
.work-session-detail-section {
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.work-session-detail-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.9fr);
  gap: 14px;
  padding: 20px;
}

.work-session-detail-eyebrow {
  font-size: 11px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: #0f766e;
}

.work-session-detail-hero__content h4,
.work-session-detail-section__header h4 {
  margin: 8px 0 0;
  color: #0f172a;
}

.work-session-detail-hero__content h4 {
  font-size: clamp(22px, 2.8vw, 30px);
  line-height: 1.1;
}

.work-session-detail-hero__content p,
.work-session-detail-block,
.work-session-detail-plan__desc,
.work-session-detail-plan__verification p {
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.work-session-detail-hero__content p {
  margin: 10px 0 0;
  max-width: 56ch;
}

.work-session-detail-hero__status,
.work-session-detail-meta-grid {
  display: grid;
  gap: 10px;
}

.work-session-detail-hero__status {
  grid-template-columns: 1fr;
}

.work-session-detail-meta-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.work-session-detail-card {
  padding: 11px 13px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.86);
}

.work-session-detail-card span,
.work-session-detail-plan__verification span {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.work-session-detail-card strong {
  display: block;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.4;
  word-break: break-word;
}

.work-session-detail-section {
  padding: 18px 20px;
}

.work-session-detail-section__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.work-session-detail-content-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.work-session-detail-section--full {
  grid-column: 1 / -1;
}

.work-session-detail-plan {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.work-session-detail-plan__item {
  position: relative;
  padding: 14px 14px 14px 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.88);
}

.work-session-detail-plan__item::before {
  content: "";
  position: absolute;
  left: 8px;
  top: 14px;
  bottom: 14px;
  width: 3px;
  border-radius: 999px;
  background: linear-gradient(180deg, rgba(15, 118, 110, 0.72), rgba(125, 211, 252, 0.36));
}

.work-session-detail-plan__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.work-session-detail-plan__title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.work-session-detail-plan__title-group strong {
  color: #0f172a;
  font-size: 13px;
  line-height: 1.4;
}

.work-session-detail-plan__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 30px;
  height: 30px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.1);
  color: #115e59;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.work-session-detail-status {
  --el-tag-border-radius: 999px;
  min-width: 64px;
  height: 22px;
  justify-content: center;
  padding: 0 8px;
  font-size: 11px;
}

.work-session-detail-plan__verification {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.78);
}

.work-session-detail-plan__verification p {
  margin: 0;
}

.work-session-detail-subtext {
  margin-top: 8px;
  font-size: 11px;
  line-height: 1.5;
  color: #7c8aa0;
}

@media (max-width: 980px) {
  .work-session-detail-hero {
    grid-template-columns: 1fr;
  }

  .work-session-detail-meta-grid,
  .work-session-detail-content-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .work-session-detail-hero,
  .work-session-detail-section {
    padding: 16px;
    border-radius: 20px;
  }

  .work-session-detail-meta-grid,
  .work-session-detail-content-grid {
    grid-template-columns: 1fr;
  }

  .work-session-detail-plan__row,
  .work-session-detail-plan__title-group {
    align-items: flex-start;
  }

  .work-session-detail-plan__row {
    flex-direction: column;
  }

  .work-session-detail-plan__item {
    padding: 13px 13px 13px 17px;
  }
}
</style>
