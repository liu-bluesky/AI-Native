<template>
  <div class="agent-supervision">
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
    </section>

    <el-alert
      v-if="errorMessage"
      class="supervision-alert"
      type="error"
      :closable="false"
      show-icon
      :title="errorMessage"
    />

    <div v-if="detailLoading" class="detail-loading">
      <el-skeleton :rows="12" animated />
    </div>
    <el-empty
      v-else-if="!detail"
      class="supervision-empty"
      description="输入回答 ID 查看执行链路"
    />
    <section v-else class="execution-card">
            <div class="model-title">
              <div>
                <small>当前模型</small>
                <h2>{{ modelSummary.names || "未采集模型名称" }}</h2>
              </div>
              <span>
                供应商：{{ modelSummary.providers || "未采集供应商名称" }}
              </span>
            </div>
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
            <div class="token-overview">
              <div class="token-overview__primary">
                <span>{{ tokenSummary.totalLabel }}</span>
                <strong>{{ tokenSummary.hasActual ? formatToken(tokenSummary.total) : "暂无" }}</strong>
                <small v-if="tokenSummary.hasActual">
                  模型供应商 usage 覆盖 {{ tokenSummary.actualRounds }} / {{ tokenSummary.modelRounds }} 轮
                </small>
                <small v-else>
                  当前回答没有采集到模型供应商 usage，不使用预估值代替
                </small>
              </div>
              <dl class="token-overview__breakdown">
                <div>
                  <dt>实际输入累计</dt>
                  <dd>{{ tokenSummary.hasActual ? formatToken(tokenSummary.input) : "—" }}</dd>
                </div>
                <div>
                  <dt>实际输出累计</dt>
                  <dd>{{ tokenSummary.hasActual ? formatToken(tokenSummary.output) : "—" }}</dd>
                </div>
                <div>
                  <dt>缓存命中累计</dt>
                  <dd>{{ tokenSummary.hasActual ? formatToken(tokenSummary.cachedInput) : "—" }}</dd>
                </div>
                <div>
                  <dt>推理 Token 累计</dt>
                  <dd>{{ tokenSummary.hasActual ? formatToken(tokenSummary.reasoning) : "—" }}</dd>
                </div>
                <div>
                  <dt>上下文输入累计（预估）</dt>
                  <dd>{{ tokenSummary.estimatedContext ? `约 ${formatToken(tokenSummary.estimatedContext)}` : "—" }}</dd>
                </div>
              </dl>
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
                    <div v-if="selectedStep.model_step_index">
                      <dt>模型循环</dt>
                      <dd>第 {{ selectedStep.model_step_index }} 轮</dd>
                    </div>
                    <div v-if="selectedStep.context_message_count">
                      <dt>上下文消息</dt>
                      <dd>{{ selectedStep.context_message_count }} 条</dd>
                    </div>
                    <div v-if="selectedStep.context_input_tokens">
                      <dt>上下文 Token（预估）</dt>
                      <dd>约 {{ selectedStep.context_input_tokens.toLocaleString() }}</dd>
                    </div>
                    <div v-if="selectedStep.model_input_tokens">
                      <dt>实际输入 Token</dt>
                      <dd>{{ selectedStep.model_input_tokens.toLocaleString() }}</dd>
                    </div>
                    <div v-if="selectedStep.model_output_tokens">
                      <dt>实际输出 Token</dt>
                      <dd>{{ selectedStep.model_output_tokens.toLocaleString() }}</dd>
                    </div>
                    <div v-if="selectedStep.model_total_tokens">
                      <dt>实际总 Token</dt>
                      <dd>{{ selectedStep.model_total_tokens.toLocaleString() }}</dd>
                    </div>
                    <div v-if="selectedStep.model_cached_input_tokens">
                      <dt>缓存命中 Token</dt>
                      <dd>{{ selectedStep.model_cached_input_tokens.toLocaleString() }}</dd>
                    </div>
                    <div v-if="selectedStep.model_reasoning_tokens">
                      <dt>推理 Token</dt>
                      <dd>{{ selectedStep.model_reasoning_tokens.toLocaleString() }}</dd>
                    </div>
                    <div v-if="selectedStep.model_token_source">
                      <dt>Token 来源</dt>
                      <dd>{{ tokenSourceLabel(selectedStep.model_token_source) }}</dd>
                    </div>
                  </dl>
                  <div v-if="selectedContextMessages.length" class="context-snapshot">
                    <div class="context-snapshot__head">
                      <span>本节点执行上下文</span>
                      <small>每轮独立快照 · Token 为输入消息预估值</small>
                    </div>
                    <div class="context-message-list">
                      <article
                        v-for="(message, index) in selectedContextMessages"
                        :key="`${selectedStep.step_id}-context-${index}`"
                        class="context-message"
                      >
                        <header>
                          <b>{{ contextRoleLabel(message.role) }}</b>
                          <span v-if="message.tool_call_id">
                            {{ message.tool_call_id }}
                          </span>
                          <span v-if="message.tool_call_count">
                            {{ message.tool_call_count }} 个工具调用
                          </span>
                        </header>
                        <pre>{{ message.content_preview || "（无文本内容）" }}</pre>
                      </article>
                    </div>
                  </div>
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
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Search } from "@element-plus/icons-vue";
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
import { fetchProjectChatProviders } from "@/modules/project-chat/services/projectChatSettingsApi.js";
import { getStoredProjectContextId } from "@/utils/desktop-shell.js";
import { fetchAllVisibleProjects } from "@/utils/projects.js";

const route = useRoute();
const router = useRouter();
const projectId = ref(
  String(route.query.project_id || getStoredProjectContextId() || "").trim(),
);
const searchQuery = ref(String(route.query.answer_id || "").trim());
const projectOptions = ref([]);
const providerNameById = ref(new Map());
const projectsLoading = ref(false);
const searching = ref(false);
const detailLoading = ref(false);
const detail = ref(null);
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
  ["request", "context_build", "plan", "operation", "final_answer"].map(
    (type) => ({ type, ...GRAPH_TYPES[type] }),
  ),
);
const selectedGroupSteps = computed(() => {
  if (!selectedStageStepIds.value.length) return selectedStep.value ? [selectedStep.value] : [];
  const stepIds = new Set(selectedStageStepIds.value);
  return (detail.value?.steps || []).filter((step) => stepIds.has(step.step_id));
});
const selectedContextMessages = computed(() => {
  const snapshot = selectedStep.value?.context_snapshot;
  if (!snapshot || typeof snapshot !== "object") return [];
  if (Array.isArray(snapshot.messages_redacted)) return snapshot.messages_redacted;
  if (Array.isArray(snapshot.messagesRedacted)) return snapshot.messagesRedacted;
  return [];
});
const modelSummary = computed(() => {
  const modelSteps = (detail.value?.steps || []).filter(
    (step) => String(step?.step_type || "").trim() === "model_call",
  );
  const uniqueValues = (field) => [
    ...new Set(
      modelSteps
        .map((step) => String(step?.[field] || "").trim())
        .filter(Boolean),
    ),
  ];
  const providerNames = [
    ...new Set(
      modelSteps
        .map((step) => {
          const storedName = String(step?.provider_name || "").trim();
          if (storedName) return storedName;
          const providerId = String(step?.provider_id || "").trim();
          return providerId
            ? String(providerNameById.value.get(providerId) || "").trim()
            : "";
        })
        .filter(Boolean),
    ),
  ];
  return {
    names: uniqueValues("model_name").join(" / "),
    providers: providerNames.join(" / "),
  };
});
const tokenSummary = computed(() => {
  const modelSteps = (detail.value?.steps || []).filter(
    (step) => String(step?.step_type || "").trim() === "model_call",
  );
  const actualSteps = modelSteps.filter(
    (step) => String(step?.model_token_source || "").trim() === "provider_response_usage",
  );
  const sum = (steps, field) =>
    steps.reduce((total, step) => total + Math.max(0, Number(step?.[field] || 0)), 0);
  const modelRounds = Math.max(
    modelSteps.length,
    Math.max(0, Number(detail.value?.run?.model_round_count || 0)),
  );
  const actualRounds = actualSteps.length;
  const hasActual = actualRounds > 0;
  const hasCompleteActual = hasActual && actualRounds === modelRounds;
  return {
    modelRounds,
    actualRounds,
    hasActual,
    hasCompleteActual,
    totalLabel: hasCompleteActual
      ? "全链路实际 Token"
      : hasActual
        ? "已采集实际 Token（非全量）"
        : "全链路实际 Token",
    input: sum(actualSteps, "model_input_tokens"),
    output: sum(actualSteps, "model_output_tokens"),
    total: sum(actualSteps, "model_total_tokens"),
    cachedInput: sum(actualSteps, "model_cached_input_tokens"),
    reasoning: sum(actualSteps, "model_reasoning_tokens"),
    estimatedContext: sum(modelSteps, "context_input_tokens"),
  };
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

function tokenSourceLabel(source) {
  return String(source || "").trim() === "provider_response_usage"
    ? "模型供应商 usage"
    : String(source || "").trim() || "未知";
}

function contextRoleLabel(role) {
  return {
    system: "系统",
    developer: "开发者",
    user: "用户",
    assistant: "智能体",
    tool: "工具结果",
  }[String(role || "").trim()] || String(role || "未知角色");
}

function formatDuration(value) {
  const duration = Number(value || 0);
  if (!duration) return "—";
  if (duration < 1000) return `${Math.round(duration)} ms`;
  if (duration < 60_000) return `${(duration / 1000).toFixed(1)} 秒`;
  return `${Math.floor(duration / 60_000)} 分 ${Math.round((duration % 60_000) / 1000)} 秒`;
}

function formatToken(value) {
  return Math.max(0, Number(value || 0)).toLocaleString();
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

async function loadProviderNames(nextProjectId) {
  const normalizedProjectId = String(nextProjectId || "").trim();
  providerNameById.value = new Map();
  if (!normalizedProjectId) return;
  try {
    const data = await fetchProjectChatProviders(normalizedProjectId, {
      includeRuntimeExternalTools: false,
    });
    providerNameById.value = new Map(
      (Array.isArray(data?.providers) ? data.providers : [])
        .map((provider) => [
          String(provider?.id || "").trim(),
          String(provider?.name || "").trim(),
        ])
        .filter(([providerId, providerName]) => providerId && providerName),
    );
  } catch {
    providerNameById.value = new Map();
  }
}

async function handleProjectChange(nextProjectId) {
  resetExecutionFlow();
  projectId.value = String(nextProjectId || "").trim();
  searchQuery.value = "";
  detail.value = null;
  selectedStep.value = null;
  errorMessage.value = "";
  await loadProviderNames(projectId.value);
  await router.replace({
    path: "/ai/supervision",
    query: projectId.value ? { project_id: projectId.value } : {},
  });
}

async function runSearch() {
  const normalizedProjectId = String(projectId.value || "").trim();
  const normalizedAnswerId = String(searchQuery.value || "").trim();
  if (!normalizedProjectId) {
    errorMessage.value = "请先选择项目";
    return;
  }
  if (!normalizedAnswerId) {
    errorMessage.value = "请输入回答 ID";
    return;
  }
  searching.value = true;
  errorMessage.value = "";
  try {
    await loadProviderNames(normalizedProjectId);
    const directDetail = await getAgentSupervisionAnswer(
      normalizedProjectId,
      normalizedAnswerId,
    );
    if (directDetail) {
      detail.value = directDetail;
      selectedStep.value = directDetail.steps?.[0] || null;
      await prepareExecutionFlow();
      await router.replace({
        path: "/ai/supervision",
        query: {
          project_id: normalizedProjectId,
          answer_id: directDetail.answer_id || normalizedAnswerId,
        },
      });
      await nextTick();
      await focusInitialFlow();
      return;
    }
    const results = await searchAgentSupervisionAnswers(
      normalizedProjectId,
      normalizedAnswerId,
      20,
    );
    const exact = results.find(
      (item) =>
        item.answer_id === normalizedAnswerId ||
        item.assistant_message_id === normalizedAnswerId,
    );
    if (exact) {
      await selectAnswer(exact.answer_id);
    } else {
      detail.value = null;
      resetExecutionFlow();
      errorMessage.value = "本机监管库中没有找到该回答 ID";
    }
  } catch (error) {
    detail.value = null;
    resetExecutionFlow();
    errorMessage.value = normalizeError(error, "读取桌面监管库失败");
  } finally {
    searching.value = false;
  }
}

async function selectAnswer(answerId) {
  const normalizedProjectId = String(projectId.value || "").trim();
  const normalizedAnswerId = String(answerId || "").trim();
  if (!normalizedProjectId || !normalizedAnswerId) return;
  resetExecutionFlow();
  detailLoading.value = true;
  errorMessage.value = "";
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

onMounted(async () => {
  await loadProjectOptions();
  await loadProviderNames(projectId.value);
  if (searchQuery.value) {
    await runSearch();
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

.supervision-search-card,
.execution-card,
.supervision-alert,
.detail-loading,
.supervision-empty {
  width: 100%;
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
  margin-top: 14px;
}

.supervision-empty,
.detail-loading {
  min-height: 420px;
  margin-top: 16px;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.92);
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

.model-title {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e2e8f0;
}

.model-title small {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.model-title h2 {
  margin: 3px 0 0;
  color: #0f172a;
  font-size: 24px;
  line-height: 1.2;
}

.model-title > span {
  color: #64748b;
  font-size: 13px;
}

.token-overview {
  display: grid;
  grid-template-columns: minmax(240px, 0.8fr) minmax(560px, 2fr);
  gap: 12px;
  margin-bottom: 14px;
}

.token-overview__primary,
.token-overview__breakdown {
  border: 1px solid #dbeafe;
  border-radius: 14px;
  background: #f8fbff;
}

.token-overview__primary {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 104px;
  padding: 16px 18px;
}

.token-overview__primary span {
  color: #475569;
  font-size: 13px;
  font-weight: 700;
}

.token-overview__primary strong {
  margin: 4px 0;
  color: #1d4ed8;
  font-size: 30px;
  line-height: 1.1;
}

.token-overview__primary small {
  color: #64748b;
  line-height: 1.45;
}

.token-overview__breakdown {
  display: grid;
  grid-template-columns: repeat(5, minmax(104px, 1fr));
  margin: 0;
  overflow: hidden;
}

.token-overview__breakdown > div {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  min-height: 104px;
  padding: 14px;
  border-left: 1px solid #dbeafe;
}

.token-overview__breakdown > div:first-child {
  border-left: 0;
}

.token-overview__breakdown dt {
  color: #64748b;
  font-size: 12px;
}

.token-overview__breakdown dd {
  margin: 0;
  color: #0f172a;
  font-size: 17px;
  font-weight: 800;
}

.execution-card {
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: #fff;
}

.step-detail__section > span {
  display: block;
  margin-bottom: 5px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
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
  grid-template-columns: minmax(0, 1fr) 400px;
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

.context-snapshot {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

.context-snapshot__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.context-snapshot__head span {
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.context-snapshot__head small {
  max-width: 190px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
  text-align: right;
}

.context-message-list {
  display: grid;
  gap: 10px;
  max-height: 480px;
  overflow: auto;
}

.context-message {
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.context-message header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 7px;
}

.context-message header b {
  color: #2563eb;
  font-size: 12px;
}

.context-message header span {
  padding: 2px 6px;
  border-radius: 6px;
  color: #64748b;
  background: #e2e8f0;
  font-size: 10px;
}

.context-message pre {
  margin: 0;
  color: #334155;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
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

.detail-loading {
  padding: 22px;
}

@media (max-width: 1100px) {
  .token-overview {
    grid-template-columns: 1fr;
  }

  .execution-grid {
    grid-template-columns: 1fr;
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

  .supervision-search-card {
    align-items: stretch;
    flex-direction: column;
  }

  .project-input,
  .answer-input {
    width: 100%;
  }

  .model-title {
    align-items: flex-start;
    flex-direction: column;
  }

  .token-overview__breakdown {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .token-overview__breakdown > div,
  .token-overview__breakdown > div:first-child {
    min-height: 82px;
    border-top: 1px solid #dbeafe;
    border-left: 0;
  }

  .token-overview__breakdown > div:nth-child(-n + 2) {
    border-top: 0;
  }

  .token-overview__breakdown > div:nth-child(even) {
    border-left: 1px solid #dbeafe;
  }
}
</style>
