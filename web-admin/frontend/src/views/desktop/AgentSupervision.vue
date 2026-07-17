<template>
  <div class="agent-supervision">
    <header class="supervision-hero">
      <div>
        <div class="supervision-eyebrow">Local Agent Observability</div>
        <h1>智能体监管</h1>
        <p>通过回答 ID 复盘模型、工具、权限与最终回答的本地执行链路。</p>
      </div>
      <div class="local-only-badge">
        <span class="local-only-badge__dot" />
        仅查询桌面本地 SQLite
      </div>
    </header>

    <section class="supervision-search-card">
      <el-select
        v-model="projectId"
        class="project-input"
        placeholder="选择项目"
        filterable
        clearable
        :loading="projectsLoading"
        @change="handleProjectChange"
      >
        <el-option
          v-for="project in projectOptions"
          :key="project.id"
          :label="project.name"
          :value="project.id"
        >
          <div class="project-option">
            <span>{{ project.name }}</span>
            <small>{{ project.id }}</small>
          </div>
        </el-option>
      </el-select>
      <el-input
        v-model="searchQuery"
        class="answer-input"
        placeholder="粘贴回答 ID，例如 ans_xxx"
        clearable
        @keyup.enter="runSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button type="primary" :loading="searching" @click="runSearch">
        搜索
      </el-button>
      <el-button :icon="Refresh" :disabled="searching" @click="loadRecent">
        最近回答
      </el-button>
    </section>

    <el-alert
      v-if="errorMessage"
      class="supervision-alert"
      type="error"
      :closable="false"
      show-icon
      :title="errorMessage"
    />

    <main class="supervision-workspace">
      <aside class="answer-list-panel">
        <div class="panel-heading">
          <div>
            <span>回答记录</span>
            <small>{{ answers.length }} 条</small>
          </div>
        </div>
        <div v-if="searching" class="panel-loading">
          <el-skeleton :rows="6" animated />
        </div>
        <el-empty
          v-else-if="!answers.length"
          description="本机监管库中暂无匹配回答"
        />
        <button
          v-for="answer in answers"
          v-else
          :key="answer.answer_id"
          type="button"
          :class="[
            'answer-list-item',
            selectedAnswerId === answer.answer_id ? 'is-active' : '',
          ]"
          @click="selectAnswer(answer.answer_id)"
        >
          <span class="answer-list-item__topline">
            <el-tag size="small" :type="statusTagType(answer.status)">
              {{ statusLabel(answer.status) }}
            </el-tag>
            <time>{{ formatTimestamp(answer.started_at_epoch_ms, answer.updated_at) }}</time>
          </span>
          <strong>{{ answer.question_preview || "未记录用户问题" }}</strong>
          <span>{{ answer.answer_preview || "暂无回答摘要" }}</span>
          <code>{{ answer.answer_id }}</code>
        </button>
      </aside>

      <section class="answer-detail-panel">
        <div v-if="detailLoading" class="detail-loading">
          <el-skeleton :rows="12" animated />
        </div>
        <el-empty
          v-else-if="!detail"
          description="选择回答后查看完整执行链路"
        />
        <template v-else>
          <section class="answer-summary-card">
            <div class="answer-summary-card__head">
              <div>
                <div class="answer-summary-card__label">回答 ID</div>
                <h2>{{ detail.answer.answer_id }}</h2>
              </div>
              <div class="answer-summary-actions">
                <el-button text :icon="CopyDocument" @click="copyAnswerId">
                  复制 ID
                </el-button>
                <el-button
                  text
                  :icon="ChatLineSquare"
                  @click="openOriginalChat"
                >
                  返回原对话
                </el-button>
              </div>
            </div>
            <div class="answer-metrics">
              <article>
                <span>状态</span>
                <strong>{{ statusLabel(detail.answer.status) }}</strong>
              </article>
              <article>
                <span>总耗时</span>
                <strong>{{ formatDuration(detail.answer.duration_ms) }}</strong>
              </article>
              <article>
                <span>模型步骤</span>
                <strong>{{ detail.run?.model_round_count || modelStepCount }}</strong>
              </article>
              <article>
                <span>工具步骤</span>
                <strong>{{ detail.run?.tool_call_count || toolStepCount }}</strong>
              </article>
              <article>
                <span>执行节点</span>
                <strong>{{ detail.steps.length }}</strong>
              </article>
            </div>
            <div class="answer-text-grid">
              <article>
                <span>用户问题</span>
                <p>{{ detail.answer.question_preview || "未记录" }}</p>
              </article>
              <article>
                <span>最终回答</span>
                <p>{{ detail.answer.answer_preview || "暂无回答内容" }}</p>
              </article>
            </div>
          </section>

          <section class="execution-card">
            <div class="panel-heading panel-heading--graph">
              <div>
                <span>执行链路</span>
                <small>点击节点查看输入、输出、耗时与状态</small>
              </div>
              <div class="graph-legend">
                <span v-for="item in graphLegend" :key="item.type">
                  <i :style="{ background: item.color }" />{{ item.label }}
                </span>
              </div>
            </div>
            <div v-if="detail.steps.length" class="execution-grid">
              <div class="execution-flow-shell">
                <VueFlow
                  id="agent-supervision-flow"
                  v-model:nodes="flowNodes"
                  v-model:edges="flowEdges"
                  class="execution-flow"
                  :min-zoom="0.25"
                  :max-zoom="1.4"
                  :nodes-draggable="false"
                  :nodes-connectable="false"
                  :zoom-on-double-click="false"
                  :default-edge-options="defaultEdgeOptions"
                  @node-click="handleFlowNodeClick"
                  @pane-ready="handleFlowReady"
                >
                  <Background pattern-color="#cbd5e1" :gap="24" />
                  <Controls position="bottom-left" :show-interactive="false" />
                  <MiniMap
                    position="bottom-right"
                    pannable
                    zoomable
                    :node-color="miniMapNodeColor"
                  />
                  <template #node-execution="nodeProps">
                    <ExecutionFlowNode v-bind="nodeProps" />
                  </template>
                </VueFlow>
              </div>
              <aside class="step-detail">
                <template v-if="selectedStep">
                  <div class="step-detail__head">
                    <el-tag size="small" :type="statusTagType(selectedStep.status)">
                      {{ statusLabel(selectedStep.status) }}
                    </el-tag>
                    <span>{{ stepTypeLabel(selectedStep.step_type) }}</span>
                  </div>
                  <h3>{{ selectedStep.title }}</h3>
                  <div v-if="selectedGroupSteps.length > 1" class="step-event-list">
                    <span>阶段内原始事件</span>
                    <button
                      v-for="(step, index) in selectedGroupSteps"
                      :key="step.step_id"
                      type="button"
                      :class="selectedStep.step_id === step.step_id ? 'is-active' : ''"
                      @click="selectedStep = step"
                    >
                      <b>{{ index + 1 }}</b>
                      <span>{{ step.title || stepTypeLabel(step.step_type) }}</span>
                    </button>
                  </div>
                  <dl>
                    <div>
                      <dt>步骤 ID</dt>
                      <dd>{{ selectedStep.step_id }}</dd>
                    </div>
                    <div v-if="selectedStep.tool_name">
                      <dt>工具</dt>
                      <dd>{{ selectedStep.tool_name }}</dd>
                    </div>
                    <div v-if="selectedStep.call_id">
                      <dt>调用 ID</dt>
                      <dd>{{ selectedStep.call_id }}</dd>
                    </div>
                    <div>
                      <dt>耗时</dt>
                      <dd>{{ formatDuration(selectedStep.duration_ms) }}</dd>
                    </div>
                  </dl>
                  <div v-if="selectedStep.summary" class="step-detail__section">
                    <span>摘要</span>
                    <p>{{ selectedStep.summary }}</p>
                  </div>
                  <div
                    v-if="selectedStep.detail_preview"
                    class="step-detail__section"
                  >
                    <span>执行详情</span>
                    <pre>{{ selectedStep.detail_preview }}</pre>
                  </div>
                </template>
                <el-empty v-else description="点击流程节点查看详情" />
              </aside>
            </div>
            <el-empty
              v-else
              class="execution-empty"
              description="该回答的本地运行快照尚未采集到执行步骤"
            />
          </section>
        </template>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
  ChatLineSquare,
  CopyDocument,
  Refresh,
  Search,
} from "@element-plus/icons-vue";
import { MarkerType, VueFlow } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import { MiniMap } from "@vue-flow/minimap";

import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";
import "@vue-flow/minimap/dist/style.css";

import ExecutionFlowNode from "@/components/agent-supervision/ExecutionFlowNode.vue";
import {
  getAgentSupervisionAnswer,
  searchAgentSupervisionAnswers,
} from "@/modules/agent-supervision/services/agentSupervisionStorage.js";
import { buildExecutionFlow } from "@/modules/agent-supervision/utils/executionFlowLayout.js";
import { getStoredProjectContextId } from "@/utils/desktop-shell.js";
import { openRouteInDesktop } from "@/utils/desktop-app-bridge.js";
import { fetchAllVisibleProjects } from "@/utils/projects.js";

const route = useRoute();
const router = useRouter();
const projectId = ref(
  String(route.query.project_id || getStoredProjectContextId() || "").trim(),
);
const searchQuery = ref(String(route.query.answer_id || "").trim());
const projectOptions = ref([]);
const projectsLoading = ref(false);
const searching = ref(false);
const detailLoading = ref(false);
const answers = ref([]);
const detail = ref(null);
const selectedAnswerId = ref("");
const selectedStep = ref(null);
const selectedStageStepIds = ref([]);
const flowNodes = ref([]);
const flowEdges = ref([]);
const errorMessage = ref("");
let flowInstance = null;

const GRAPH_TYPES = {
  request: { label: "用户请求", color: "#64748b", symbol: "roundRect" },
  context_build: { label: "上下文", color: "#8b5cf6", symbol: "diamond" },
  model_call: { label: "模型", color: "#2563eb", symbol: "circle" },
  tool_call: { label: "工具", color: "#0891b2", symbol: "roundRect" },
  permission: { label: "权限", color: "#d97706", symbol: "diamond" },
  plan: { label: "计划", color: "#7c3aed", symbol: "roundRect" },
  retry: { label: "重试", color: "#ea580c", symbol: "diamond" },
  pause: { label: "暂停", color: "#475569", symbol: "rect" },
  resume: { label: "恢复", color: "#0f766e", symbol: "rect" },
  final_answer: { label: "最终回答", color: "#16a34a", symbol: "roundRect" },
  error: { label: "错误", color: "#dc2626", symbol: "diamond" },
  operation: { label: "执行步骤", color: "#0f766e", symbol: "roundRect" },
  observation: { label: "观察", color: "#64748b", symbol: "circle" },
};

const graphLegend = computed(() =>
  ["request", "model_call", "tool_call", "permission", "final_answer"].map(
    (type) => ({ type, ...GRAPH_TYPES[type] }),
  ),
);
const modelStepCount = computed(
  () => detail.value?.steps?.filter((item) => item.step_type === "model_call").length || 0,
);
const toolStepCount = computed(
  () => detail.value?.steps?.filter((item) => item.step_type === "tool_call").length || 0,
);
const selectedGroupSteps = computed(() => {
  if (!selectedStageStepIds.value.length) return selectedStep.value ? [selectedStep.value] : [];
  const stepIds = new Set(selectedStageStepIds.value);
  return (detail.value?.steps || []).filter((step) => stepIds.has(step.step_id));
});
const defaultEdgeOptions = {
  type: "smoothstep",
  markerEnd: MarkerType.ArrowClosed,
  style: { stroke: "#94a3b8", strokeWidth: 2 },
};

function statusLabel(status) {
  const normalized = String(status || "").trim().toLowerCase();
  return {
    pending: "等待中",
    running: "执行中",
    completed: "已完成",
    failed: "失败",
    blocked: "已阻塞",
    cancelled: "已取消",
  }[normalized] || normalized || "未知";
}

function statusTagType(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "completed") return "success";
  if (normalized === "failed" || normalized === "cancelled") return "danger";
  if (normalized === "blocked") return "warning";
  if (normalized === "running") return "primary";
  return "info";
}

function stepTypeLabel(type) {
  return GRAPH_TYPES[String(type || "").trim()]?.label || "执行步骤";
}

function formatDuration(value) {
  const duration = Number(value || 0);
  if (!duration) return "—";
  if (duration < 1000) return `${Math.round(duration)} ms`;
  if (duration < 60_000) return `${(duration / 1000).toFixed(1)} 秒`;
  return `${Math.floor(duration / 60_000)} 分 ${Math.round((duration % 60_000) / 1000)} 秒`;
}

function formatTimestamp(epochMs, fallback = "") {
  const timestamp = Number(epochMs || 0);
  if (timestamp > 0) return new Date(timestamp).toLocaleString();
  const parsed = Date.parse(String(fallback || ""));
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : "—";
}

function normalizeError(error, fallback) {
  return String(error?.message || error?.detail || fallback || "操作失败").trim();
}

function normalizeProjectOption(item = {}) {
  const id = String(item?.id || item?.project_id || "").trim();
  if (!id) return null;
  return {
    id,
    name: String(item?.name || item?.project_label || id).trim() || id,
  };
}

async function loadProjectOptions() {
  projectsLoading.value = true;
  try {
    projectOptions.value = (await fetchAllVisibleProjects())
      .map(normalizeProjectOption)
      .filter(Boolean);
  } catch (error) {
    projectOptions.value = [];
    errorMessage.value = normalizeError(error, "加载项目列表失败");
  } finally {
    projectsLoading.value = false;
  }
}

async function handleProjectChange(nextProjectId) {
  resetExecutionFlow();
  projectId.value = String(nextProjectId || "").trim();
  searchQuery.value = "";
  answers.value = [];
  detail.value = null;
  selectedAnswerId.value = "";
  selectedStep.value = null;
  errorMessage.value = "";
  await router.replace({
    path: "/ai/supervision",
    query: projectId.value ? { project_id: projectId.value } : {},
  });
  if (projectId.value) await loadRecent();
}

async function runSearch() {
  const normalizedProjectId = String(projectId.value || "").trim();
  if (!normalizedProjectId) {
    errorMessage.value = "请先填写项目 ID";
    return;
  }
  searching.value = true;
  errorMessage.value = "";
  try {
    answers.value = await searchAgentSupervisionAnswers(
      normalizedProjectId,
      searchQuery.value,
      100,
    );
    const exact = answers.value.find(
      (item) =>
        item.answer_id === searchQuery.value ||
        item.assistant_message_id === searchQuery.value,
    );
    if (exact) {
      await selectAnswer(exact.answer_id);
    } else if (searchQuery.value && !answers.value.length) {
      detail.value = null;
      selectedAnswerId.value = "";
      resetExecutionFlow();
    }
  } catch (error) {
    answers.value = [];
    detail.value = null;
    resetExecutionFlow();
    errorMessage.value = normalizeError(error, "读取桌面监管库失败");
  } finally {
    searching.value = false;
  }
}

async function loadRecent() {
  searchQuery.value = "";
  await runSearch();
}

async function selectAnswer(answerId) {
  const normalizedProjectId = String(projectId.value || "").trim();
  const normalizedAnswerId = String(answerId || "").trim();
  if (!normalizedProjectId || !normalizedAnswerId) return;
  resetExecutionFlow();
  detailLoading.value = true;
  errorMessage.value = "";
  selectedAnswerId.value = normalizedAnswerId;
  try {
    detail.value = await getAgentSupervisionAnswer(
      normalizedProjectId,
      normalizedAnswerId,
    );
    selectedStep.value = detail.value?.steps?.[0] || null;
    await prepareExecutionFlow();
    if (!detail.value) {
      errorMessage.value = "本机监管库中没有找到该回答";
    }
    await router.replace({
      path: "/ai/supervision",
      query: {
        project_id: normalizedProjectId,
        answer_id: normalizedAnswerId,
      },
    });
  } catch (error) {
    detail.value = null;
    resetExecutionFlow();
    errorMessage.value = normalizeError(error, "读取回答执行详情失败");
  } finally {
    detailLoading.value = false;
    await nextTick();
    await focusInitialFlow();
  }
}

function resetExecutionFlow() {
  flowNodes.value = [];
  flowEdges.value = [];
  selectedStageStepIds.value = [];
  selectedStep.value = null;
  flowInstance = null;
}

async function prepareExecutionFlow() {
  const result = await buildExecutionFlow(detail.value?.steps, detail.value?.edges);
  flowNodes.value = result.nodes.map((node) => ({
    ...node,
    data: {
      ...node.data,
      typeLabel: stepTypeLabel(node.data.visualType),
      statusLabel: statusLabel(node.data.status),
      durationLabel: formatDuration(node.data.durationMs),
    },
  }));
  flowEdges.value = result.edges.map((edge) => ({
    ...edge,
    ...defaultEdgeOptions,
  }));
  const firstNode = flowNodes.value[0];
  selectedStageStepIds.value = firstNode?.data?.stepIds || [];
  selectedStep.value = firstNode?.data?.primaryStep || detail.value?.steps?.[0] || null;
}

function handleFlowNodeClick({ node }) {
  selectedStageStepIds.value = node?.data?.stepIds || [];
  selectedStep.value = node?.data?.primaryStep || null;
}

function handleFlowReady(instance) {
  flowInstance = instance;
  void focusInitialFlow();
}

async function focusInitialFlow() {
  if (!flowInstance || !flowNodes.value.length) return;
  await nextTick();
  await flowInstance.fitView({
    nodes: flowNodes.value.slice(0, 3).map((node) => node.id),
    padding: 0.16,
    minZoom: 0.62,
    maxZoom: 0.92,
    duration: 260,
  });
}

function miniMapNodeColor(node) {
  const type = node?.data?.visualType || "observation";
  if (["failed", "blocked"].includes(node?.data?.status)) return "#dc2626";
  return GRAPH_TYPES[type]?.color || GRAPH_TYPES.observation.color;
}

async function copyAnswerId() {
  const answerId = String(detail.value?.answer?.answer_id || "").trim();
  if (!answerId) return;
  await navigator.clipboard.writeText(answerId);
  ElMessage.success("回答 ID 已复制");
}

function openOriginalChat() {
  const answer = detail.value?.answer || {};
  void openRouteInDesktop(
    router,
    {
      path: "/ai/chat",
      query: {
        project_id: projectId.value,
        chat_session_id: answer.chat_session_id,
        message_id: answer.assistant_message_id,
      },
    },
    { mode: "new-window", appId: "chat", title: "AI 对话" },
  );
}

onMounted(async () => {
  await loadProjectOptions();
  if (searchQuery.value) {
    await runSearch();
  } else if (projectId.value) {
    await loadRecent();
  }
});

</script>

<style scoped>
.agent-supervision {
  min-height: 100vh;
  padding: 28px;
  color: #0f172a;
  background:
    radial-gradient(circle at 10% 0%, rgba(37, 99, 235, 0.12), transparent 34%),
    radial-gradient(circle at 92% 8%, rgba(124, 58, 237, 0.1), transparent 30%),
    #f4f7fb;
}

.supervision-hero,
.supervision-search-card,
.supervision-workspace,
.answer-summary-card,
.execution-card {
  max-width: 1680px;
  margin-inline: auto;
}

.supervision-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
}

.supervision-eyebrow {
  margin-bottom: 8px;
  color: #2563eb;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.supervision-hero h1 {
  margin: 0;
  font-size: clamp(28px, 3vw, 42px);
  line-height: 1.15;
}

.supervision-hero p {
  margin: 10px 0 0;
  color: #64748b;
  font-size: 15px;
}

.local-only-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid rgba(22, 163, 74, 0.18);
  border-radius: 999px;
  color: #166534;
  background: rgba(240, 253, 244, 0.92);
  font-size: 13px;
  font-weight: 700;
}

.local-only-badge__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 5px rgba(34, 197, 94, 0.12);
}

.supervision-search-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(16px);
}

.project-input {
  width: 280px;
}

.project-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
}

.project-option small {
  color: #94a3b8;
  font-size: 11px;
}

.answer-input {
  flex: 1;
}

.supervision-alert {
  max-width: 1680px;
  margin: 14px auto 0;
}

.supervision-workspace {
  display: grid;
  grid-template-columns: minmax(260px, 330px) minmax(0, 1fr);
  gap: 18px;
  margin-top: 18px;
}

.answer-list-panel,
.answer-detail-panel {
  min-height: 650px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}

.answer-list-panel {
  padding: 16px;
}

.answer-detail-panel {
  padding: 18px;
}

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.panel-heading > div:first-child {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.panel-heading span {
  font-weight: 800;
}

.panel-heading small {
  color: #94a3b8;
}

.answer-list-item {
  width: 100%;
  margin-bottom: 10px;
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  text-align: left;
  background: #fff;
  cursor: pointer;
  transition: 180ms ease;
}

.answer-list-item:hover,
.answer-list-item.is-active {
  border-color: rgba(37, 99, 235, 0.45);
  background: #f8fbff;
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.09);
}

.answer-list-item__topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.answer-list-item time,
.answer-list-item > span,
.answer-list-item code {
  color: #64748b;
  font-size: 12px;
}

.answer-list-item strong,
.answer-list-item > span,
.answer-list-item code {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}

.answer-list-item strong {
  margin-bottom: 6px;
  color: #1e293b;
  white-space: nowrap;
}

.answer-list-item > span {
  display: -webkit-box;
  margin-bottom: 10px;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.answer-list-item code {
  color: #2563eb;
  white-space: nowrap;
}

.answer-summary-card,
.execution-card {
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: #fff;
}

.answer-summary-card {
  padding: 20px;
}

.answer-summary-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.answer-summary-card__label {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.answer-summary-card h2 {
  margin: 5px 0 0;
  color: #1d4ed8;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 18px;
  overflow-wrap: anywhere;
}

.answer-summary-actions {
  display: flex;
  flex-wrap: wrap;
}

.answer-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(100px, 1fr));
  gap: 10px;
  margin-top: 18px;
}

.answer-metrics article {
  padding: 12px;
  border-radius: 12px;
  background: #f8fafc;
}

.answer-metrics span,
.answer-text-grid span,
.step-detail__section > span {
  display: block;
  margin-bottom: 5px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.answer-metrics strong {
  color: #0f172a;
  font-size: 18px;
}

.answer-text-grid {
  display: grid;
  grid-template-columns: 1fr 1.25fr;
  gap: 12px;
  margin-top: 12px;
}

.answer-text-grid article {
  padding: 14px;
  border: 1px solid #edf2f7;
  border-radius: 12px;
}

.answer-text-grid p {
  margin: 0;
  color: #334155;
  line-height: 1.65;
  white-space: pre-wrap;
}

.execution-card {
  margin-top: 16px;
  padding: 18px;
}

.panel-heading--graph {
  gap: 16px;
}

.panel-heading--graph > div:first-child {
  display: block;
}

.panel-heading--graph small {
  display: block;
  margin-top: 4px;
}

.graph-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.graph-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.graph-legend i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.execution-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  min-height: 470px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  overflow: hidden;
}

.execution-empty {
  min-height: 360px;
  border: 1px dashed #cbd5e1;
  border-radius: 14px;
  background: #f8fafc;
}

.execution-flow-shell {
  min-width: 0;
  min-height: 620px;
  background: #f8fafc;
}

.execution-flow {
  width: 100%;
  height: 620px;
}

.execution-flow :deep(.vue-flow__edge-path) {
  stroke-linecap: round;
}

.execution-flow :deep(.vue-flow__controls) {
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 10px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.09);
}

.execution-flow :deep(.vue-flow__controls-button) {
  width: 34px;
  height: 34px;
  border-color: #edf2f7;
  color: #334155;
  background: rgba(255, 255, 255, 0.96);
}

.execution-flow :deep(.vue-flow__minimap) {
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
}

.step-detail {
  padding: 18px;
  border-left: 1px solid #e2e8f0;
  background: #fff;
  overflow: auto;
}

.step-detail__head {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
  font-size: 12px;
}

.step-detail h3 {
  margin: 12px 0;
  font-size: 19px;
  line-height: 1.35;
}

.step-event-list {
  margin: 0 0 14px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #f8fafc;
}

.step-event-list > span {
  display: block;
  margin-bottom: 8px;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.step-event-list button {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  width: 100%;
  margin-top: 6px;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 9px;
  color: #475569;
  text-align: left;
  background: transparent;
  cursor: pointer;
}

.step-event-list button:hover,
.step-event-list button.is-active {
  border-color: #bfdbfe;
  color: #1d4ed8;
  background: #eff6ff;
}

.step-event-list button b {
  display: inline-grid;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  place-items: center;
  color: #fff;
  background: #64748b;
  font-size: 11px;
}

.step-event-list button.is-active b {
  background: #2563eb;
}

.step-event-list button span {
  overflow: hidden;
  font-size: 12px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-detail dl {
  margin: 0;
}

.step-detail dl > div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
}

.step-detail dt {
  color: #94a3b8;
}

.step-detail dd {
  margin: 0;
  color: #334155;
  overflow-wrap: anywhere;
}

.step-detail__section {
  margin-top: 16px;
}

.step-detail__section p,
.step-detail__section pre {
  margin: 0;
  color: #334155;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.step-detail__section pre {
  max-height: 260px;
  padding: 12px;
  border-radius: 10px;
  background: #0f172a;
  color: #dbeafe;
  overflow: auto;
}

.panel-loading,
.detail-loading {
  padding: 22px;
}

@media (max-width: 1100px) {
  .supervision-workspace,
  .execution-grid {
    grid-template-columns: 1fr;
  }

  .answer-list-panel {
    min-height: auto;
  }

  .step-detail {
    border-top: 1px solid #e2e8f0;
    border-left: 0;
  }

  .execution-flow-shell,
  .execution-flow {
    min-height: 560px;
    height: 560px;
  }
}

@media (max-width: 760px) {
  .agent-supervision {
    padding: 16px;
  }

  .supervision-hero,
  .supervision-search-card {
    align-items: stretch;
    flex-direction: column;
  }

  .project-input,
  .answer-input {
    width: 100%;
  }

  .answer-metrics,
  .answer-text-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
