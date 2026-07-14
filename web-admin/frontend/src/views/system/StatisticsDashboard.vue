<template>
  <div v-loading="loading" class="statistics-page">
    <div class="statistics-page__ambient statistics-page__ambient--left" aria-hidden="true" />
    <div class="statistics-page__ambient statistics-page__ambient--right" aria-hidden="true" />
    <div class="statistics-page__mesh" aria-hidden="true" />

    <section class="panel-card panel-card--wide statistics-controls">
      <div class="panel-card__head">
        <div>
          <div class="panel-card__eyebrow">Statistics</div>
          <h1 class="panel-card__title">统计页面</h1>
        </div>
        <div class="panel-card__tag">统计范围 {{ currentScopeLabel }}</div>
      </div>
      <div class="statistics-hero__controls">
        <div class="statistics-hero__controls-main">
          <el-select
            v-model="selectedProjectScope"
            class="statistics-page__project-scope"
            filterable
            clearable
            :loading="projectScopeLoading"
            placeholder="选择统计项目"
          >
            <el-option label="全局统计" value="" />
            <el-option
              v-for="item in normalizedProjectScopeOptions"
              :key="item.value"
              :label="item.recentLabel || item.label"
              :value="item.value"
            />
          </el-select>
          <el-select v-model="days" class="statistics-page__range" @change="refresh">
            <el-option :value="7" label="近 7 天" />
            <el-option :value="30" label="近 30 天" />
            <el-option :value="90" label="近 90 天" />
          </el-select>
        </div>
        <div class="statistics-hero__controls-actions">
          <el-button plain @click="copyCurrentStatisticsLink">复制当前统计链接</el-button>
          <el-button @click="refresh">刷新</el-button>
        </div>
      </div>
      <div class="statistics-hero__meta">
        <span>统计窗口 {{ days }} 天</span>
        <span>生成时间 {{ formatDateTime(data.generated_at) }}</span>
        <span>查看人 {{ data.viewer.username || "-" }}</span>
      </div>
    </section>

    <section v-if="aiReport" class="panel-card panel-card--wide ai-report-panel">
      <div class="panel-card__head">
        <div class="panel-card__head-copy">
          <div class="panel-card__eyebrow">AI Ready Report</div>
          <h2 class="panel-card__title">给 AI 直接读取的数据报表</h2>
        </div>
        <div class="panel-card__actions">
          <el-button size="small" @click="sendToAiAnalysis">发给 AI 分析</el-button>
          <el-button size="small" @click="copyAiReport">复制 AI 报表</el-button>
          <el-button size="small" plain @click="aiReportExpanded = !aiReportExpanded">
            {{ aiReportExpanded ? "收起报表" : "展开报表" }}
          </el-button>
        </div>
      </div>
      <div v-if="!aiReportExpanded" class="ai-report-collapsed">
        <strong>{{ aiReport.conclusion || aiReport.summary || "AI 报表已生成" }}</strong>
        <div class="ai-report-collapsed__metrics">
          <span>{{ aiReportAnalysisMode.label || "结论待生成" }}</span>
          <span>健康分 {{ aiReportKeyMetrics.health_score || 0 }}</span>
          <span>活跃项目 {{ aiReportKeyMetrics.active_projects || 0 }}</span>
          <span>工作闭环率 {{ formatPercent(aiReportKeyMetrics.completion_rate) }}</span>
        </div>
      </div>
      <template v-else>
        <div class="ai-report-grid">
          <article class="ai-report-block">
            <span class="ai-report-block__label">摘要</span>
            <p class="ai-report-block__summary">{{ aiReport.summary }}</p>
            <p class="ai-report-block__summary ai-report-block__summary--muted">{{ aiReport.conclusion }}</p>
            <div class="ai-report-kpis">
              <span>能力覆盖 {{ aiReport.capability_coverage_percent || 0 }}%</span>
              <span>{{ aiReportAnalysisMode.label || "结论待生成" }}</span>
              <span>健康分 {{ aiReportKeyMetrics.health_score || 0 }}</span>
              <span>活跃项目 {{ aiReportKeyMetrics.active_projects || 0 }}</span>
              <span>活跃智能体 {{ aiReportKeyMetrics.active_agents || 0 }}</span>
              <span>完成会话 {{ aiReportKeyMetrics.completed_sessions || 0 }}</span>
              <span>工作闭环率 {{ formatPercent(aiReportKeyMetrics.completion_rate) }}</span>
              <span>项目集中度 {{ formatPercent(aiReportKeyMetrics.project_concentration_percent) }}</span>
              <span>模型调用 {{ aiReportKeyMetrics.model_calls || 0 }}</span>
              <span>总 token {{ aiReportKeyMetrics.total_tokens || 0 }}</span>
              <span>总成本 ${{ Number(aiReportKeyMetrics.total_cost_usd || 0).toFixed(4) }}</span>
            </div>
          </article>
          <article class="ai-report-block">
            <span class="ai-report-block__label">AI 当前应重点关注</span>
            <div v-if="aiReportFocusPoints.length" class="ai-focus-list">
              <article v-for="item in aiReportFocusPoints" :key="item.key" class="ai-focus-item" :class="`is-${item.status || 'neutral'}`">
                <strong>{{ item.title }}</strong>
                <small>{{ item.evidence }}</small>
                <p>{{ item.recommended_action }}</p>
              </article>
            </div>
            <el-empty v-else description="暂无 AI 关注点" />
          </article>
          <article class="ai-report-block">
            <span class="ai-report-block__label">建议 AI 下一步提问</span>
            <div v-if="aiReportQuestions.length" class="ai-question-list">
              <article v-for="question in aiReportQuestions" :key="question" class="ai-question-item">{{ question }}</article>
            </div>
            <el-empty v-else description="暂无建议提问" />
          </article>
        </div>
        <div v-if="aiReportRequiredMetrics.length" class="ai-metric-gap-list">
          <article v-for="item in aiReportRequiredMetrics" :key="item.key" class="ai-metric-gap-item">
            <strong>{{ item.title }}</strong>
            <small>{{ item.reason }}</small>
          </article>
        </div>
        <pre v-if="aiReportStructuredPreview" class="ai-report-markdown">{{ aiReportStructuredPreview }}</pre>
        <pre v-else-if="aiReportMarkdown" class="ai-report-markdown">{{ aiReportMarkdown }}</pre>
      </template>
    </section>

    <section class="statistics-layout">
      <article class="panel-card panel-card--wide">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">AI Employee Usage</div>
            <h2 class="panel-card__title">入口 / 智能体 / 开发中账户统计</h2>
          </div>
          <div class="panel-card__tag">真实智能体和入口流量分开看</div>
        </div>
        <div class="activity-judgement">
          <strong>{{ activityJudgement.title }}</strong>
          <span>{{ activityJudgement.meta }}</span>
        </div>
        <div v-if="hasActivityCharts" class="activity-chart">
          <div class="activity-chart__legend">
            <span v-for="item in activityLegendItems" :key="item.label">
              <i :style="{ background: item.color }" />
              {{ item.label }}
            </span>
          </div>
          <div class="activity-chart-grid">
            <article class="activity-chart-card">
              <div class="activity-chart-card__head">
                <strong>入口活跃度</strong>
                <span>{{ entryActivityChartItems.length }} 个入口</span>
              </div>
              <div v-if="entryActivityChartItems.length" ref="entryActivityChartRef" class="activity-chart__canvas" />
              <el-empty v-else description="暂无入口活跃数据" />
            </article>
            <article class="activity-chart-card">
              <div class="activity-chart-card__head">
                <strong>智能体活跃度</strong>
                <span>{{ agentActivityChartItems.length }} 个智能体</span>
              </div>
              <div v-if="agentActivityChartItems.length" ref="agentActivityChartRef" class="activity-chart__canvas" />
              <el-empty v-else description="暂无智能体活跃数据" />
            </article>
            <article class="activity-chart-card">
              <div class="activity-chart-card__head">
                <strong>开发中账户统计</strong>
                <span>{{ developerActivityChartItems.length }} 个账户</span>
              </div>
              <div v-if="developerActivityChartItems.length" ref="developerActivityChartRef" class="activity-chart__canvas" />
              <el-empty v-else description="暂无用户管理账户数据" />
            </article>
          </div>
          <div class="activity-stat-row">
            <article v-for="item in activityStatCards" :key="item.label" class="activity-stat-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <small>{{ item.hint }}</small>
            </article>
          </div>
        </div>
        <el-empty
          v-else
          :description="Number(data?.usage?.summary?.query_scope_events || 0) > 0
            ? '当前只有 query 入口流量，尚未稳定归因到真实 AI 智能体'
            : '当前窗口内暂无入口、智能体或开发者活跃数据'"
        />
      </article>

      <article class="panel-card panel-card--wide">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">Technical Activity</div>
            <h2 class="panel-card__title">项目技术活跃度</h2>
          </div>
        </div>
        <div class="activity-judgement">
          <strong>{{ projectActivityJudgement.title }}</strong>
          <span>{{ projectActivityJudgement.meta }}</span>
        </div>
        <div v-if="projectActivityItems.length" class="project-activity-chart">
          <div ref="projectChartRef" class="project-activity-chart__canvas" />
          <div class="activity-stat-row">
            <article v-for="item in projectActivityCards" :key="item.label" class="activity-stat-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <small>{{ item.hint }}</small>
            </article>
          </div>
        </div>
        <el-empty v-else description="暂无项目活跃数据" />
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

import api from "@/utils/api.js";
import { formatDateTime } from "@/utils/date.js";
import { useRoute, useRouter } from "vue-router";
import { openRouteInDesktop } from "@/utils/desktop-app-bridge.js";

echarts.use([BarChart, DataZoomComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const RECENT_STATISTICS_PROJECTS_STORAGE_KEY = "statistics_recent_project_ids";
const STATISTICS_ANALYSIS_DRAFT_STORAGE_PREFIX = "statistics_analysis_draft";
const STATISTICS_ANALYSIS_DRAFT_QUERY_KEY = "statistics_analysis_draft_key";
const ACTIVITY_GROUP_COLORS = {
  agent: "#2563eb",
  entry: "#f97316",
  developer: "#16a34a",
  project: "#0f766e",
};
const route = useRoute();
const router = useRouter();
const loading = ref(false);
const projectScopeLoading = ref(false);
const days = ref(7);
const aiReportExpanded = ref(false);
const entryActivityChartRef = ref(null);
const agentActivityChartRef = ref(null);
const developerActivityChartRef = ref(null);
const projectChartRef = ref(null);
const data = ref({
  generated_at: "",
  viewer: {},
  usage: {
    summary: {},
    daily: [],
    top_tools: [],
    top_employees: [],
    top_scopes: [],
    top_developers: [],
    top_projects: [],
    tool_health: {},
  },
  live_activity: {
    summary: {},
    endpoint_breakdown: [],
    top_projects: [],
    top_agents: [],
  },
  ai_report: null,
});
const projectScopeOptions = ref([]);
const recentProjectIds = ref([]);
const userAccounts = ref([]);

function loadRecentProjectIds() {
  try {
    const raw = window.localStorage.getItem(RECENT_STATISTICS_PROJECTS_STORAGE_KEY);
    const parsed = JSON.parse(raw || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.map((item) => String(item || "").trim()).filter(Boolean).slice(0, 8);
  } catch {
    return [];
  }
}

function saveRecentProjectIds(items) {
  try {
    window.localStorage.setItem(
      RECENT_STATISTICS_PROJECTS_STORAGE_KEY,
      JSON.stringify(items.slice(0, 8)),
    );
  } catch {
    // ignore storage errors
  }
}

function rememberRecentProject(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) return;
  const nextItems = [
    normalizedProjectId,
    ...recentProjectIds.value.filter((item) => item !== normalizedProjectId),
  ].slice(0, 8);
  recentProjectIds.value = nextItems;
  saveRecentProjectIds(nextItems);
}

function buildStatisticsAnalysisDraftStorageKey() {
  return `${STATISTICS_ANALYSIS_DRAFT_STORAGE_PREFIX}:${Date.now()}:${Math.random().toString(36).slice(2, 10)}`;
}

const scopedProjectId = computed(() => String(route.query.project_id || "").trim());
const selectedProjectScope = computed({
  get() {
    return scopedProjectId.value;
  },
  async set(value) {
    const normalizedValue = String(value || "").trim();
    const nextQuery = { ...route.query };
    if (normalizedValue) {
      nextQuery.project_id = normalizedValue;
      rememberRecentProject(normalizedValue);
    } else {
      delete nextQuery.project_id;
    }
    await router.replace({ query: nextQuery });
  },
});
const currentScopeLabel = computed(() => {
  const scope = data.value?.scope || data.value?.ai_report?.scope || null;
  const scopeProjectName = String(scope?.project_name || "").trim();
  const scopeDisplayName = String(scope?.display_name || "").trim();
  const topLevelProjectName = String(data.value?.project_name || "").trim();
  if (scopeDisplayName) return scopeDisplayName;
  if (scopeProjectName) return scopeProjectName;
  if (topLevelProjectName) return topLevelProjectName;
  if (scopedProjectId.value) return scopedProjectId.value;
  return "全局统计";
});
const currentScopedProjectName = computed(() => {
  const scope = data.value?.scope || data.value?.ai_report?.scope || null;
  return String(scope?.project_name || data.value?.project_name || "").trim();
});
const normalizedProjectScopeOptions = computed(() => {
  const items = Array.isArray(projectScopeOptions.value) ? projectScopeOptions.value : [];
  const normalized = items
    .map((item) => ({
      value: String(item?.value || "").trim(),
      label: String(item?.label || "").trim(),
    }))
    .filter((item) => item.value && item.label);
  const selectedId = scopedProjectId.value;
  const selectedName = currentScopedProjectName.value;
  if (
    selectedId &&
    selectedName &&
    !normalized.some((item) => item.value === selectedId)
  ) {
    normalized.unshift({ value: selectedId, label: selectedName });
  }
  const recentMap = new Map(recentProjectIds.value.map((item, index) => [item, index]));
  return normalized
    .map((item) => ({
      ...item,
      recentRank: recentMap.has(item.value) ? recentMap.get(item.value) : Number.POSITIVE_INFINITY,
      recentLabel: recentMap.has(item.value) ? `${item.label} · 最近` : item.label,
    }))
    .sort((left, right) => {
      if (left.recentRank !== right.recentRank) {
        return left.recentRank - right.recentRank;
      }
      return left.label.localeCompare(right.label, "zh-CN");
    });
});

const usageSummary = computed(() => data.value?.usage?.summary || {});
const liveSummary = computed(() => data.value?.live_activity?.summary || {});

function formatPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

const leadingProject = computed(() => {
  const usageTop = Array.isArray(data.value?.usage?.top_projects) ? data.value.usage.top_projects[0] : null;
  return usageTop || null;
});

const projectConcentrationPercent = computed(() => {
  const leader = leadingProject.value;
  const totalEvents = Number(usageSummary.value.total_events || 0);
  const leaderEvents = Number(
    leader?.cnt || leader?.event_count || leader?.active_entries || 0,
  );
  if (totalEvents <= 0) return 0;
  return Math.round((leaderEvents / totalEvents) * 1000) / 10;
});

const aiReport = computed(() => data.value?.ai_report || null);
const aiReportAnalysisMode = computed(() => aiReport.value?.analysis_mode || aiReport.value?.measurement_position || {});
const aiReportKeyMetrics = computed(() => aiReport.value?.key_metrics || aiReport.value?.snapshot || {});
const aiReportFocusPoints = computed(() => {
  if (Array.isArray(aiReport.value?.priority_focus)) return aiReport.value.priority_focus;
  return Array.isArray(aiReport.value?.focus_points) ? aiReport.value.focus_points : [];
});
const aiReportQuestions = computed(() => {
  if (Array.isArray(aiReport.value?.next_questions)) return aiReport.value.next_questions;
  return Array.isArray(aiReport.value?.suggested_questions) ? aiReport.value.suggested_questions : [];
});
const aiReportRequiredMetrics = computed(() => {
  if (Array.isArray(aiReport.value?.must_track_metrics)) return aiReport.value.must_track_metrics;
  return Array.isArray(aiReport.value?.required_metrics) ? aiReport.value.required_metrics : [];
});
const aiReportMarkdown = computed(() => String(aiReport.value?.markdown || "").trim());
const aiReportStructuredPreview = computed(() => {
  const payload = aiReport.value?.structured_payload;
  if (!payload || typeof payload !== "object") return "";
  return JSON.stringify(payload, null, 2);
});
let entryActivityChart = null;
let agentActivityChart = null;
let developerActivityChart = null;
let projectChart = null;

function compactChartLabel(value, maxLength = 14) {
  const normalized = String(value || "").trim();
  if (!normalized) return "-";
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}...` : normalized;
}

function normalizeActivityKey(value) {
  return String(value || "").trim().toLowerCase();
}

function createHorizontalDataZoom(itemCount, visibleCount = 7) {
  const total = Math.max(0, Number(itemCount || 0));
  const end = total > visibleCount ? Math.round((visibleCount / total) * 100) : 100;
  return [
    {
      type: "slider",
      show: true,
      height: 16,
      left: 42,
      right: 22,
      bottom: 8,
      start: 0,
      end,
      brushSelect: false,
      borderColor: "rgba(148, 163, 184, 0.24)",
      fillerColor: "rgba(37, 99, 235, 0.12)",
      handleStyle: {
        color: "#2563eb",
        borderColor: "#2563eb",
      },
      textStyle: {
        color: "#64748b",
      },
    },
    {
      type: "inside",
      start: 0,
      end,
    },
  ];
}

const activityLegendItems = computed(() => [
  { label: "智能体", color: ACTIVITY_GROUP_COLORS.agent },
  { label: "入口", color: ACTIVITY_GROUP_COLORS.entry },
  { label: "开发中账户", color: ACTIVITY_GROUP_COLORS.developer },
]);

const agentActivityChartItems = computed(() => (
  agentActivityItems.value.map((item) => ({
    key: `agent:${item.employee_id || item.employee_name}`,
    group: "agent",
    groupLabel: "智能体",
    name: item.employee_name || item.label || item.employee_id || "未知智能体",
    value: Number(item.activity_score || item.cnt || 0),
    meta: `调用 ${item.cnt || 0} · 在线 ${item.active_entries || 0}`,
  })).filter((item) => item.value > 0)
));

const entryActivityChartItems = computed(() => (
  entryScopeItems.value.map((item) => ({
    key: `entry:${item.scope_id || item.scope_label}`,
    group: "entry",
    groupLabel: "入口",
    name: item.scope_label || item.scope_id || "未知入口",
    value: Number(item.activity_score || item.cnt || 0),
    meta: `事件 ${item.cnt || 0} · 工具 ${item.tool_calls || 0}`,
  })).filter((item) => item.value > 0)
));

const developerActivityChartItems = computed(() => (
  userManagementAccountItems.value.map((item) => ({
    key: `account:${item.username}`,
    group: "developer",
    groupLabel: "开发中账户",
    name: item.username || "未知账户",
    value: Number(item.cnt || 0),
    meta: `${item.role_name || item.role || "未标记角色"} · 交互 ${item.cnt || 0}`,
  }))
));

const activityChartItems = computed(() => [
  ...entryActivityChartItems.value,
  ...agentActivityChartItems.value,
  ...developerActivityChartItems.value,
].sort((left, right) => right.value - left.value));

const hasActivityCharts = computed(() => activityChartItems.value.length > 0);

const activityJudgement = computed(() => {
  const leader = activityChartItems.value[0];
  if (!leader) {
    return {
      title: "还没有足够活跃数据",
      meta: "等入口、真实智能体或开发者产生稳定记录后再判断。",
    };
  }
  const agentCount = agentActivityItems.value.length;
  const entryCount = entryScopeItems.value.length;
  const developerCount = userManagementAccountItems.value.length;
  return {
    title: `当前主力是${leader.groupLabel}：${leader.name}`,
    meta: `活跃分 ${leader.value} · 覆盖 ${entryCount} 个入口、${agentCount} 个智能体、${developerCount} 个账户`,
  };
});

const activityStatCards = computed(() => [
  {
    label: "主入口",
    value: entryScopeItems.value[0]?.scope_label || entryScopeItems.value[0]?.scope_id || "暂无",
    hint: entryScopeItems.value[0]
      ? `事件 ${entryScopeItems.value[0].cnt || 0} · 工具 ${entryScopeItems.value[0].tool_calls || 0}`
      : "入口流量不足",
  },
  {
    label: "主智能体",
    value: agentActivityItems.value[0]?.employee_name || agentActivityItems.value[0]?.employee_id || "暂无",
    hint: agentActivityItems.value[0]
      ? `活跃分 ${agentActivityItems.value[0].activity_score || 0}`
      : "真实 AI 智能体调用不足",
  },
  {
    label: "主账户",
    value: userManagementAccountItems.value[0]?.username || "暂无",
    hint: userManagementAccountItems.value[0]
      ? `交互 ${userManagementAccountItems.value[0].cnt || 0}`
      : "用户管理账户不足",
  },
]);

function createActivityChartOption(items, color, maxLabelLength = 14) {
  return {
    animationDuration: 400,
    grid: {
      top: 18,
      right: 18,
      bottom: 62,
      left: 34,
      containLabel: true,
    },
    dataZoom: createHorizontalDataZoom(items.length, 6),
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "shadow",
      },
      backgroundColor: "rgba(15, 23, 42, 0.92)",
      borderWidth: 0,
      textStyle: {
        color: "#e2e8f0",
      },
      formatter(params) {
        const item = items[params?.[0]?.dataIndex] || {};
        return `${item.groupLabel || ""}<br/>${item.name || ""}: ${item.value || 0}<br/>${item.meta || ""}`;
      },
    },
    xAxis: {
      type: "category",
      data: items.map((item) => compactChartLabel(item.name, maxLabelLength)),
      axisLine: {
        lineStyle: {
          color: "rgba(148, 163, 184, 0.35)",
        },
      },
      axisTick: { show: false },
      axisLabel: {
        color: "#64748b",
        fontSize: 11,
        interval: 0,
        rotate: 32,
      },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#475569",
        fontSize: 12,
      },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 34,
        borderRadius: [8, 8, 0, 0],
        label: {
          show: true,
          position: "top",
          color: "#0f172a",
          fontSize: 12,
          fontWeight: 700,
        },
        data: items.map((item) => ({
          value: item.value,
          itemStyle: {
            color,
          },
        })),
      },
    ],
  };
}

const entryActivityChartOption = computed(() => (
  createActivityChartOption(entryActivityChartItems.value, ACTIVITY_GROUP_COLORS.entry)
));

const agentActivityChartOption = computed(() => (
  createActivityChartOption(agentActivityChartItems.value, ACTIVITY_GROUP_COLORS.agent)
));

const developerActivityChartOption = computed(() => (
  createActivityChartOption(developerActivityChartItems.value, ACTIVITY_GROUP_COLORS.developer)
));

const projectActivityJudgement = computed(() => {
  const leader = projectActivityItems.value[0];
  if (!leader) {
    return {
      title: "项目活跃度还不足以排序",
      meta: "暂无可归因项目或在线入口样本。",
    };
  }
  const concentration = projectConcentrationPercent.value;
  return {
    title: `主项目：${leader.display_name}`,
    meta: `活跃分 ${leader.activity_score || 0} · 集中度 ${formatPercent(concentration)} · 在线 ${leader.active_entries || 0}`,
  };
});

const projectActivityCards = computed(() => [
  {
    label: "活跃项目",
    value: projectActivityItems.value.length,
    hint: `统计窗口 ${days.value} 天`,
  },
  {
    label: "项目集中度",
    value: formatPercent(projectConcentrationPercent.value),
    hint: leadingProject.value?.project_name || leadingProject.value?.project_id || "暂无主项目",
  },
  {
    label: "最活跃项目",
    value: projectActivityItems.value
      .slice()
      .sort((left, right) => Number(right.activity_score || 0) - Number(left.activity_score || 0))[0]?.display_name || "暂无",
    hint: "按技术活跃样本判断",
  },
]);

const projectChartOption = computed(() => {
  const items = projectActivityItems.value;
  return {
    animationDuration: 400,
    grid: {
      top: 18,
      right: 18,
      bottom: 62,
      left: 34,
      containLabel: true,
    },
    dataZoom: createHorizontalDataZoom(items.length, 8),
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "shadow",
      },
      backgroundColor: "rgba(15, 23, 42, 0.92)",
      borderWidth: 0,
      textStyle: {
        color: "#e2e8f0",
      },
      formatter(params) {
        const item = items[params?.[0]?.dataIndex] || {};
        return [
          `${item.display_name || ""}: ${item.activity_score || 0}`,
          `归因 ${item.cnt || 0} · 在线 ${item.active_entries || 0} · 开发账户 ${item.developer_count || 0}`,
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: items.map((item) => compactChartLabel(item.display_name, 16)),
      axisLine: {
        lineStyle: {
          color: "rgba(148, 163, 184, 0.35)",
        },
      },
      axisTick: { show: false },
      axisLabel: {
        color: "#64748b",
        fontSize: 11,
        interval: 0,
        rotate: 32,
      },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#475569",
        fontSize: 12,
      },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 34,
        borderRadius: [8, 8, 0, 0],
        label: {
          show: true,
          position: "top",
          color: "#0f172a",
          fontSize: 12,
          fontWeight: 700,
        },
        data: items.map((item, index) => ({
          value: Number(item.activity_score || 0),
          itemStyle: {
            color: index === 0 ? ACTIVITY_GROUP_COLORS.project : "#14b8a6",
          },
        })),
      },
    ],
  };
});

function disposeEntryActivityChart() {
  if (!entryActivityChart) return;
  entryActivityChart.dispose();
  entryActivityChart = null;
}

function disposeAgentActivityChart() {
  if (!agentActivityChart) return;
  agentActivityChart.dispose();
  agentActivityChart = null;
}

function disposeDeveloperActivityChart() {
  if (!developerActivityChart) return;
  developerActivityChart.dispose();
  developerActivityChart = null;
}

function disposeActivityCharts() {
  disposeEntryActivityChart();
  disposeAgentActivityChart();
  disposeDeveloperActivityChart();
}

function disposeProjectChart() {
  if (!projectChart) return;
  projectChart.dispose();
  projectChart = null;
}

function resizeActivityCharts() {
  entryActivityChart?.resize();
  agentActivityChart?.resize();
  developerActivityChart?.resize();
}

function resizeProjectChart() {
  if (!projectChart) return;
  projectChart.resize();
}

async function renderEntryActivityChart() {
  await nextTick();
  if (!entryActivityChartItems.value.length || !entryActivityChartRef.value) {
    disposeEntryActivityChart();
    return;
  }
  entryActivityChart =
    echarts.getInstanceByDom(entryActivityChartRef.value) ||
    echarts.init(entryActivityChartRef.value);
  entryActivityChart.setOption(entryActivityChartOption.value, true);
  entryActivityChart.resize();
}

async function renderAgentActivityChart() {
  await nextTick();
  if (!agentActivityChartItems.value.length || !agentActivityChartRef.value) {
    disposeAgentActivityChart();
    return;
  }
  agentActivityChart =
    echarts.getInstanceByDom(agentActivityChartRef.value) ||
    echarts.init(agentActivityChartRef.value);
  agentActivityChart.setOption(agentActivityChartOption.value, true);
  agentActivityChart.resize();
}

async function renderDeveloperActivityChart() {
  await nextTick();
  if (!developerActivityChartItems.value.length || !developerActivityChartRef.value) {
    disposeDeveloperActivityChart();
    return;
  }
  developerActivityChart =
    echarts.getInstanceByDom(developerActivityChartRef.value) ||
    echarts.init(developerActivityChartRef.value);
  developerActivityChart.setOption(developerActivityChartOption.value, true);
  developerActivityChart.resize();
}

function renderActivityCharts() {
  renderEntryActivityChart();
  renderAgentActivityChart();
  renderDeveloperActivityChart();
}

async function renderProjectChart() {
  await nextTick();
  if (!projectActivityItems.value.length || !projectChartRef.value) {
    disposeProjectChart();
    return;
  }
  projectChart =
    echarts.getInstanceByDom(projectChartRef.value) ||
    echarts.init(projectChartRef.value);
  projectChart.setOption(projectChartOption.value, true);
  projectChart.resize();
}

function withPercent(list, key) {
  const items = Array.isArray(list) ? list : [];
  const maxValue = items.reduce((value, item) => Math.max(value, Number(item?.[key] || 0)), 0) || 1;
  return items.map((item) => ({
    ...item,
    percent: Math.max(8, Math.round((Number(item?.[key] || 0) / maxValue) * 100)),
  }));
}

const rankedDevelopers = computed(() => withPercent(data.value?.usage?.top_developers, "cnt"));
const userManagementAccountItems = computed(() => {
  const usageByAccount = new Map();
  for (const item of rankedDevelopers.value) {
    const key = normalizeActivityKey(item?.developer_name);
    if (!key) continue;
    usageByAccount.set(key, Number(item?.cnt || 0));
  }
  const accounts = Array.isArray(userAccounts.value) ? userAccounts.value : [];
  return withPercent(
    accounts
      .map((item) => {
        const username = String(item?.username || "").trim();
        const cnt = usageByAccount.get(normalizeActivityKey(username)) || 0;
        return {
          username,
          role: String(item?.role || "").trim(),
          role_name: String(item?.role_name || item?.role || "").trim(),
          created_by: String(item?.created_by || "").trim(),
          cnt,
        };
      })
      .filter((item) => item.username)
      .sort((left, right) => {
        const countDiff = Number(right.cnt || 0) - Number(left.cnt || 0);
        if (countDiff !== 0) return countDiff;
        return left.username.localeCompare(right.username, "zh-CN");
      }),
    "cnt",
  );
});
const PROJECT_NAME_ALIASES = new Set([
  "当前项目",
  "<当前项目名>",
]);

function normalizeProjectName(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return "";
  if (PROJECT_NAME_ALIASES.has(normalized)) return "";
  return normalized;
}

function resolveProjectDisplayName(projectName, projectId) {
  return normalizeProjectName(projectName) || String(projectId || "").trim() || "未标记项目";
}

const entryScopeItems = computed(() => {
  const usageScopes = Array.isArray(data.value?.usage?.top_scopes) ? data.value.usage.top_scopes : [];
  return withPercent(
    usageScopes
      .map((row) => ({
        ...row,
        activity_score:
          Number(row?.cnt || 0) +
          Number(row?.tool_calls || 0) +
          Number(row?.attributed_employee_count || 0),
      }))
      .sort((left, right) => Number(right.activity_score || 0) - Number(left.activity_score || 0)),
    "activity_score",
  );
});

const agentActivityItems = computed(() => {
  const usageAgents = Array.isArray(data.value?.usage?.top_employees) ? data.value.usage.top_employees : [];
  const liveAgents = Array.isArray(data.value?.live_activity?.top_agents) ? data.value.live_activity.top_agents : [];
  const merged = new Map();

  for (const row of usageAgents) {
    const key = row?.employee_id || row?.employee_name;
    if (!key) continue;
    merged.set(key, {
      employee_id: row.employee_id || "",
      employee_name: row.employee_name || row.label || row.employee_id || "未知智能体",
      cnt: Number(row.cnt || 0),
      active_entries: 0,
      project_count: 0,
      activity_score: Number(row.cnt || 0),
    });
  }

  for (const row of liveAgents) {
    const key = row?.employee_id || row?.employee_name;
    if (!key) continue;
    const existing = merged.get(key) || {
      employee_id: row.employee_id || "",
      employee_name: row.employee_name || row.employee_id || "未知智能体",
      cnt: 0,
      active_entries: 0,
      project_count: 0,
      activity_score: 0,
    };
    const activeEntries = Number(row.active_entries || 0);
    merged.set(key, {
      ...existing,
      employee_id: existing.employee_id || row.employee_id || "",
      employee_name: existing.employee_name || row.employee_name || row.employee_id || "未知智能体",
      active_entries: activeEntries,
      project_count: Number(row.project_count || 0),
      activity_score: Number(existing.cnt || 0) + activeEntries,
    });
  }

  return [...merged.values()]
    .sort((left, right) => Number(right.activity_score || 0) - Number(left.activity_score || 0));
});

const projectActivityItems = computed(() => {
  const usageProjects = Array.isArray(data.value?.usage?.top_projects)
    ? data.value.usage.top_projects
    : [];
  const liveProjects = Array.isArray(data.value?.live_activity?.top_projects)
    ? data.value.live_activity.top_projects
    : [];
  const merged = new Map();

  for (const row of usageProjects) {
    const normalizedProjectName = normalizeProjectName(row?.project_name);
    const key = row?.project_id || normalizedProjectName;
    if (!key) continue;
    merged.set(key, {
      project_id: row.project_id || "",
      project_name: normalizedProjectName,
      cnt: Number(row.cnt || 0),
      session_count: 0,
      event_count: Number(row.tool_calls || row.cnt || 0),
      active_entries: 0,
      developer_count: Number(row.developer_count || 0),
      avg_duration_ms: Number(row.avg_duration_ms || 0),
    });
  }

  for (const row of liveProjects) {
    const normalizedProjectName = normalizeProjectName(row?.project_name);
    const key = row?.project_id || normalizedProjectName;
    if (!key) continue;
    const existing = merged.get(key) || {
      project_id: row.project_id || "",
      project_name: "",
      session_count: 0,
      event_count: 0,
      active_entries: 0,
      developer_count: 0,
      avg_duration_ms: 0,
    };
    merged.set(key, {
      ...existing,
      project_id: existing.project_id || row.project_id || "",
      project_name: existing.project_name || normalizedProjectName,
      active_entries: Number(row.active_entries || 0),
      developer_count: Number(row.developer_count || 0),
    });
  }

  return withPercent(
    [...merged.values()]
      .map((row) => ({
        ...row,
        display_name: resolveProjectDisplayName(row.project_name, row.project_id),
        activity_score:
          Number(row.cnt || 0) +
          Number(row.event_count || 0) +
          Number(row.active_entries || 0) +
          Number(row.developer_count || 0),
      }))
      .sort((left, right) => Number(right.activity_score || 0) - Number(left.activity_score || 0)),
    "activity_score",
  );
});

async function fetchUserAccounts() {
  try {
    const response = await api.get("/users");
    userAccounts.value = Array.isArray(response?.users) ? response.users : [];
  } catch (err) {
    userAccounts.value = [];
    if (Number(err?.status || 0) !== 403) {
      ElMessage.error(err?.message || "用户管理账户加载失败");
    }
  }
}

async function copyAiReport() {
  const textToCopy = aiReportStructuredPreview.value || aiReportMarkdown.value;
  if (!textToCopy) {
    ElMessage.warning("当前没有可复制的 AI 报表");
    return;
  }
  if (!navigator?.clipboard?.writeText) {
    ElMessage.error("当前环境不支持剪贴板复制");
    return;
  }
  try {
    await navigator.clipboard.writeText(textToCopy);
    ElMessage.success("AI 报表已复制");
  } catch (err) {
    ElMessage.error(err?.message || "复制 AI 报表失败");
  }
}

async function copyCurrentStatisticsLink() {
  if (!navigator?.clipboard?.writeText) {
    ElMessage.error("当前环境不支持剪贴板复制");
    return;
  }
  try {
    await navigator.clipboard.writeText(window.location.href);
    ElMessage.success("当前统计链接已复制");
  } catch (err) {
    ElMessage.error(err?.message || "复制统计链接失败");
  }
}

function buildStatisticsAnalysisPrompt() {
  const payload = aiReport.value?.structured_payload;
  const scopeLabel = currentScopeLabel.value;
  const link = window.location.href;
  const serializedPayload = payload && typeof payload === "object"
    ? JSON.stringify(payload, null, 2)
    : aiReportMarkdown.value;
  return [
    `请基于下面这份统计数据，从运营大师视角分析当前系统最值得投入的优化方向。`,
    `要求重点判断：`,
    `1. 当前最该优先补的是归因链路、交付闭环、工具稳定性，还是 ROI 主链`,
    `2. 给出未来两周最值得做的 3 条升级动作，并按收益 / 成本排序`,
    `3. 明确哪些指标已经够用，哪些指标还是盲区`,
    "",
    `[统计范围] ${scopeLabel}`,
    `[统计链接] ${link}`,
    "",
    `[结构化统计报表]`,
    typeof serializedPayload === "string" && serializedPayload.trim().startsWith("{")
      ? `\`\`\`json\n${serializedPayload}\n\`\`\``
      : String(serializedPayload || "").trim(),
  ]
    .filter(Boolean)
    .join("\n");
}

function persistStatisticsAnalysisDraft(prompt) {
  const storageKey = buildStatisticsAnalysisDraftStorageKey();
  const payload = {
    prompt: String(prompt || "").trim(),
    created_at: new Date().toISOString(),
    source: "statistics-dashboard",
    scope: currentScopeLabel.value,
    project_id: scopedProjectId.value,
    link: window.location.href,
  };
  window.localStorage.setItem(storageKey, JSON.stringify(payload));
  return storageKey;
}

async function sendToAiAnalysis() {
  if (!aiReport.value) {
    ElMessage.warning("当前还没有可发送的 AI 报表");
    return;
  }
  const prompt = buildStatisticsAnalysisPrompt();
  if (!prompt.trim()) {
    ElMessage.warning("当前报表内容为空，暂时无法发给 AI");
    return;
  }
  const draftKey = persistStatisticsAnalysisDraft(prompt);
  const query = {
    [STATISTICS_ANALYSIS_DRAFT_QUERY_KEY]: draftKey,
  };
  if (scopedProjectId.value) {
    query.project_id = scopedProjectId.value;
  }
  await openRouteInDesktop(
    router,
    { path: "/ai/chat", query },
    {
      mode: "new-window",
      appId: "chat",
      title: "AI 对话",
      summary: `统计分析 · ${currentScopeLabel.value}`,
      eyebrow: "Statistics Insight",
    },
  );
  ElMessage.success("已把统计报表送到 AI 对话输入框");
}

async function fetchProjectScopes() {
  projectScopeLoading.value = true;
  try {
    const response = await api.get("/projects", {
      params: {
        page: 1,
        page_size: 100,
      },
    });
    const projects = Array.isArray(response?.projects) ? response.projects : [];
    projectScopeOptions.value = projects
      .map((item) => ({
        value: String(item?.id || "").trim(),
        label: String(item?.name || item?.id || "").trim(),
      }))
      .filter((item) => item.value && item.label);
  } catch (err) {
    projectScopeOptions.value = [];
    if (Number(err?.status || 0) !== 403) {
      ElMessage.error(err?.message || "项目列表加载失败");
    }
  } finally {
    projectScopeLoading.value = false;
  }
}

async function refresh() {
  loading.value = true;
  try {
    const response = await api.get("/statistics/overview", {
      params: {
        days: days.value,
        ...(scopedProjectId.value ? { project_id: scopedProjectId.value } : {}),
      },
    });
    data.value = {
      ...data.value,
      ...(response || {}),
    };
  } catch (err) {
    ElMessage.error(err?.message || "统计数据加载失败");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  recentProjectIds.value = loadRecentProjectIds();
  if (scopedProjectId.value) {
    rememberRecentProject(scopedProjectId.value);
  }
  window.addEventListener("resize", resizeActivityCharts);
  window.addEventListener("resize", resizeProjectChart);
  fetchProjectScopes();
  fetchUserAccounts();
  refresh();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeActivityCharts);
  window.removeEventListener("resize", resizeProjectChart);
  disposeActivityCharts();
  disposeProjectChart();
});

watch(activityChartItems, () => {
  renderActivityCharts();
});

watch(projectActivityItems, () => {
  renderProjectChart();
});

watch(scopedProjectId, () => {
  refresh();
});
</script>

<style scoped>
.statistics-page {
  position: relative;
  min-height: 100%;
  padding: 32px;
  overflow: visible;
  box-sizing: border-box;
  background:
    radial-gradient(circle at 18% 0%, rgba(125, 211, 252, 0.16), transparent 26%),
    radial-gradient(circle at 82% 14%, rgba(103, 232, 249, 0.12), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%);
}

.statistics-page__project-scope {
  width: 100%;
}

.statistics-page__ambient,
.statistics-page__mesh {
  position: absolute;
  pointer-events: none;
}

.statistics-page__ambient {
  width: 34rem;
  height: 34rem;
  border-radius: 999px;
  filter: blur(88px);
}

.statistics-page__ambient--left {
  left: -6rem;
  top: -4rem;
  background: rgba(125, 211, 252, 0.14);
}

.statistics-page__ambient--right {
  right: -8rem;
  top: 12rem;
  background: rgba(251, 146, 60, 0.12);
}

.statistics-page__mesh {
  inset: 0;
  background-image:
    linear-gradient(rgba(15, 23, 42, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.02) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: radial-gradient(circle at center, black 45%, transparent 84%);
  opacity: 0.45;
}

.statistics-hero,
.upgrade-briefing,
.summary-grid,
.story-grid,
.statistics-layout {
  position: relative;
  z-index: 1;
}

.statistics-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(420px, 520px);
  gap: 18px;
  align-items: stretch;
  margin-bottom: 18px;
}

.statistics-hero__copy,
.statistics-hero__focus,
.upgrade-loop-panel,
.upgrade-briefing__primary,
.summary-card,
.story-card,
.panel-card {
  border: 1px solid rgba(255, 255, 255, 0.84);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(20px);
}

.statistics-hero__copy {
  display: grid;
  gap: 18px;
  min-height: 398px;
  padding: 30px;
  border-radius: 30px;
  min-width: 0;
}

.statistics-hero__eyebrow,
.story-card__eyebrow,
.panel-card__eyebrow {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #64748b;
}

.statistics-hero__title {
  max-width: 16ch;
  margin: 0;
  color: #0f172a;
  font-size: 46px;
  line-height: 1.04;
  letter-spacing: 0;
}

.statistics-hero__summary {
  max-width: 50ch;
  margin: 0;
  color: #475569;
  font-size: 15px;
  line-height: 1.7;
}

.upgrade-decision {
  display: grid;
  gap: 8px;
  max-width: 680px;
  padding: 18px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 22px;
  background: rgba(248, 250, 252, 0.82);
}

.upgrade-decision.is-good {
  background: rgba(236, 253, 245, 0.72);
}

.upgrade-decision.is-warning,
.upgrade-decision.is-attention {
  background: rgba(255, 247, 237, 0.82);
}

.upgrade-decision span,
.upgrade-loop-panel__head span,
.upgrade-briefing__primary span,
.upgrade-signal-card span {
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.upgrade-decision strong {
  color: #0f172a;
  font-size: 20px;
  line-height: 1.35;
}

.upgrade-decision p {
  margin: 0;
  color: #475569;
  font-size: 14px;
  line-height: 1.7;
}

.statistics-hero__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: auto;
}

.statistics-hero__meta span,
.panel-card__tag {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: #526071;
  font-size: 12px;
  font-weight: 700;
}

.statistics-hero__meta span {
  padding: 6px 9px;
  font-size: 11px;
}

.upgrade-loop-panel {
  display: grid;
  gap: 16px;
  padding: 22px;
  border-radius: 30px;
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, 0.12), transparent 36%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.86), rgba(248, 250, 252, 0.78));
  min-width: 0;
}

.upgrade-loop-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.76);
}

.upgrade-loop-panel__head div {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.upgrade-loop-panel__head strong {
  color: #0f172a;
  font-size: 24px;
  line-height: 1.2;
}

.upgrade-loop-panel__head b {
  display: inline-grid;
  width: 82px;
  height: 82px;
  place-items: center;
  border-radius: 28px;
  background: #0f172a;
  color: #ffffff;
  font-size: 38px;
  line-height: 1;
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.16);
}

.upgrade-loop {
  display: grid;
  gap: 10px;
}

.upgrade-loop__step {
  display: grid;
  grid-template-columns: 68px minmax(0, 1fr);
  gap: 4px 12px;
  align-items: center;
  padding: 13px 14px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
}

.upgrade-loop__step span {
  grid-row: span 2;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.upgrade-loop__step strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upgrade-loop__step small {
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upgrade-loop__step.is-good {
  border-color: rgba(22, 163, 74, 0.18);
  background: rgba(236, 253, 245, 0.74);
}

.upgrade-loop__step.is-warning,
.upgrade-loop__step.is-attention {
  border-color: rgba(249, 115, 22, 0.2);
  background: rgba(255, 247, 237, 0.82);
}

.upgrade-briefing {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.55fr);
  gap: 14px;
  margin-bottom: 18px;
}

.upgrade-briefing__primary {
  display: grid;
  gap: 10px;
  padding: 22px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top right, rgba(103, 232, 249, 0.16), transparent 40%),
    #0f172a;
  color: #e2e8f0;
}

.upgrade-briefing__primary span,
.upgrade-briefing__primary small {
  color: #a7b5c8;
}

.upgrade-briefing__primary strong {
  color: #ffffff;
  font-size: 23px;
  line-height: 1.35;
}

.upgrade-briefing__primary p {
  margin: 0;
  color: #dbeafe;
  font-size: 14px;
  line-height: 1.7;
}

.upgrade-briefing__primary small {
  font-size: 12px;
  line-height: 1.5;
}

.upgrade-briefing__signals {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.upgrade-signal-card {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.upgrade-signal-card strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 28px;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upgrade-signal-card small {
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.statistics-hero__focus {
  display: grid;
  gap: 16px;
  padding: 22px;
  border-radius: 30px;
  background:
    radial-gradient(circle at top left, rgba(251, 146, 60, 0.12), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(248, 250, 252, 0.78));
  min-width: 0;
}

.statistics-hero__score {
  display: grid;
  gap: 8px;
  padding: 18px;
  border-radius: 26px;
  background: #0f172a;
  color: #dbeafe;
  box-shadow: 0 24px 50px rgba(15, 23, 42, 0.18);
}

.statistics-hero__score span,
.statistics-hero__score small {
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.statistics-hero__score strong {
  font-size: 60px;
  line-height: 1;
  color: #ffffff;
  letter-spacing: 0;
}

.statistics-hero__controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
}

.upgrade-loop-panel .statistics-hero__controls {
  grid-template-columns: 1fr;
}

.statistics-hero__controls-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(116px, 132px);
  gap: 10px;
  min-width: 0;
}

.statistics-hero__controls-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.statistics-page__range {
  width: 100%;
}

.statistics-hero__flow {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.statistics-hero__flow-card {
  display: grid;
  gap: 6px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
}

.statistics-hero__flow-card span,
.summary-card__label,
.tool-overview-card span {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.statistics-hero__flow-card strong {
  color: #0f172a;
  font-size: 28px;
  letter-spacing: 0;
}

.statistics-hero__flow-card small,
.summary-card__hint,
.tool-overview-card small,
.session-summary-pill small {
  color: #526071;
  font-size: 12px;
  line-height: 1.6;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.summary-card {
  display: grid;
  gap: 8px;
  min-height: 136px;
  padding: 18px;
  border-radius: 26px;
}

.summary-card__value,
.tool-overview-card strong {
  color: #0f172a;
  font-size: 36px;
  line-height: 1;
  letter-spacing: 0;
}

.executive-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
  gap: 18px;
  margin-bottom: 18px;
}

.executive-portfolio-panel {
  display: grid;
  grid-row: span 2;
  gap: 16px;
}

.executive-project-list,
.executive-risk-list {
  display: grid;
  gap: 12px;
}

.executive-project-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.76);
}

.executive-project-card.is-blocked,
.executive-project-card.is-at_risk {
  border-color: rgba(249, 115, 22, 0.22);
  background: rgba(255, 247, 237, 0.86);
}

.executive-project-card.is-healthy {
  border-color: rgba(22, 163, 74, 0.16);
  background: rgba(236, 253, 245, 0.78);
}

.executive-project-card__main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  min-width: 0;
}

.executive-project-card__main div {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.executive-project-card__main strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 17px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.executive-project-card__main small,
.executive-project-card__metrics span,
.executive-risk-item small {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.executive-project-card__main span {
  flex: 0 0 auto;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.08);
  color: #334155;
  font-size: 12px;
  font-weight: 800;
}

.executive-project-card__metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.executive-work-list {
  display: grid;
  gap: 8px;
}

.executive-work-item {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.74);
}

.executive-work-item div {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.executive-work-item strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.executive-work-item small,
.executive-work-item p,
.executive-project-card__empty {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.executive-work-item small {
  flex: 0 0 auto;
}

.executive-work-item p {
  margin: 0;
}

.executive-risk-panel {
  display: grid;
  align-content: start;
  gap: 14px;
}

.executive-risk-item {
  display: grid;
  gap: 6px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.86);
}

.executive-risk-item strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 14px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.story-grid {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 18px;
  margin-bottom: 18px;
}

.story-card {
  display: grid;
  gap: 16px;
  padding: 22px;
  border-radius: 30px;
}

.story-card--risk {
  background:
    radial-gradient(circle at top right, rgba(251, 146, 60, 0.14), transparent 38%),
    rgba(255, 255, 255, 0.74);
}

.story-card__head,
.panel-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.story-card__head > :first-child,
.panel-card__head > :first-child,
.panel-card__head-copy {
  min-width: 0;
  flex: 1 1 320px;
}

.panel-card__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  flex: 0 1 auto;
  max-width: 100%;
}

.story-card__title,
.panel-card__title {
  margin: 6px 0 0;
  color: #0f172a;
  font-size: 24px;
  line-height: 1.15;
}

.signal-list,
.alert-list,
.gap-list,
.rank-list,
.metric-list,
.endpoint-list,
.mini-rank-list,
.agent-list,
.scope-list {
  display: grid;
  gap: 12px;
}

.signal-list__item,
.alert-list__item,
.gap-list__item,
.session-card,
.endpoint-list__item,
.mini-rank-list__item,
.metric-list__item {
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.7);
}

.signal-list__item {
  display: grid;
  gap: 8px;
  padding: 16px;
}

.signal-list__item.is-warm {
  background: linear-gradient(180deg, rgba(255, 237, 213, 0.86), rgba(255, 255, 255, 0.76));
}

.signal-list__item.is-cool {
  background: linear-gradient(180deg, rgba(224, 242, 254, 0.88), rgba(255, 255, 255, 0.76));
}

.signal-list__label {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.signal-list__value {
  color: #0f172a;
  font-size: 30px;
  line-height: 1;
  letter-spacing: 0;
}

.signal-list__meta,
.gap-list__item p,
.alert-list__item p {
  color: #526071;
  font-size: 13px;
  line-height: 1.7;
}

.alert-list__item,
.gap-list__item {
  padding: 14px 16px;
}

.alert-list__item strong,
.gap-list__item strong {
  color: #0f172a;
  font-size: 15px;
}

.alert-list__item.is-critical {
  border-color: rgba(239, 68, 68, 0.18);
  background: rgba(254, 242, 242, 0.84);
}

.alert-list__item.is-warning {
  border-color: rgba(249, 115, 22, 0.18);
  background: rgba(255, 247, 237, 0.86);
}

.statistics-layout {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.panel-card {
  padding: 22px;
  border-radius: 30px;
  background:
    radial-gradient(circle at top left, rgba(251, 146, 60, 0.08), transparent 32%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(248, 250, 252, 0.92));
  min-width: 0;
}

.panel-card--wide {
  grid-column: span 2;
}

.trend-chart {
  display: grid;
  gap: 14px;
}

.trend-chart--closure {
  margin-bottom: 18px;
}

.trend-chart__canvas {
  width: 100%;
  height: 320px;
}

.trend-chart__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.trend-chart__summary span {
  padding: 8px 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.trend-row__bar-shell,
.rank-list__bar-shell {
  position: relative;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(226, 232, 240, 0.92);
}

.trend-row__bar-shell {
  height: 14px;
}

.trend-row__bar,
.rank-list__bar {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: 999px;
}

.trend-row__bar--total {
  background: linear-gradient(90deg, #fb923c, #f97316);
  opacity: 0.34;
}

.trend-row__bar--tool {
  background: linear-gradient(90deg, #0ea5e9, #2563eb);
}

.rank-list__item {
  display: grid;
  gap: 10px;
}

.rank-list__item--tool,
.tool-overview-card {
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.68);
}

.rank-list__meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.rank-list__meta-body,
.agent-list__meta,
.scope-list__meta,
.metric-list__body {
  display: grid;
  gap: 4px;
}

.rank-list__meta strong,
.agent-list__meta strong,
.scope-list__meta strong {
  color: #0f172a;
  font-size: 15px;
}

.rank-list__meta small,
.agent-list__meta small,
.scope-list__meta small,
.metric-list__body small {
  color: #64748b;
  font-size: 12px;
}

.rank-list__score,
.agent-list__score,
.scope-list__score {
  color: #0f172a;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 0;
}

.activity-judgement {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 16px 0 14px;
  padding: 14px 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.9);
}

.activity-judgement strong {
  min-width: 0;
  color: #0f172a;
  font-size: 16px;
  line-height: 1.4;
}

.activity-judgement span {
  flex: 0 1 auto;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.5;
  text-align: right;
}

.activity-chart,
.project-activity-chart {
  display: grid;
  gap: 14px;
}

.activity-chart-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.activity-chart-card {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.68);
}

.activity-chart-card__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
}

.activity-chart-card__head strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 16px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-chart-card__head span {
  flex: 0 0 auto;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.activity-chart__canvas,
.project-activity-chart__canvas {
  width: 100%;
  height: 330px;
}

.activity-chart-card .activity-chart__canvas {
  height: 260px;
}

.project-activity-chart__canvas {
  height: 300px;
}

.activity-chart__legend,
.activity-stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.activity-chart__legend span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.76);
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.activity-chart__legend i {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.activity-stat-card {
  display: grid;
  flex: 1 1 180px;
  min-width: 0;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
}

.activity-stat-card span {
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.activity-stat-card strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 17px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-stat-card small {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.rank-list__bar-shell {
  height: 10px;
}

.rank-list__bar {
  background: linear-gradient(90deg, #f97316, #fb923c);
}

.compact-split,
.tool-overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.tool-overview-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 16px;
}

.compact-split__block {
  display: grid;
  gap: 10px;
}

.compact-split__title,
.runtime-column__title {
  color: #475569;
  font-size: 13px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.compact-split__hint {
  margin: -2px 0 2px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.7;
}

.agent-list__item,
.scope-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 22px;
}

.agent-list__item {
  border: 1px solid rgba(14, 165, 233, 0.12);
  background: linear-gradient(180deg, rgba(224, 242, 254, 0.86), rgba(255, 255, 255, 0.84));
}

.scope-list__item {
  border: 1px solid rgba(249, 115, 22, 0.12);
  background: linear-gradient(180deg, rgba(255, 237, 213, 0.86), rgba(255, 255, 255, 0.84));
}

.mini-rank-list__item,
.metric-list__item,
.endpoint-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
}

.mini-rank-list__item span,
.metric-list__item span,
.endpoint-list__item span {
  color: #475569;
  font-size: 13px;
}

.mini-rank-list__item strong,
.metric-list__item strong,
.endpoint-list__item strong {
  color: #0f172a;
  font-size: 15px;
}

.session-summary-grid,
.live-grid,
.runtime-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.ai-report-panel {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
}

.ai-report-collapsed {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.92);
}

.ai-report-collapsed strong {
  min-width: 0;
  color: #0f172a;
  font-size: 14px;
  line-height: 1.5;
}

.ai-report-collapsed__metrics {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.ai-report-collapsed__metrics span {
  display: inline-flex;
  align-items: center;
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.86);
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.ai-report-grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 14px;
}

.ai-report-block {
  display: grid;
  gap: 12px;
  padding: 18px;
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(255, 255, 255, 0.76);
  min-width: 0;
}

.ai-report-block__label {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #64748b;
}

.ai-report-block__summary {
  margin: 0;
  color: #0f172a;
  font-size: 15px;
  line-height: 1.7;
}

.ai-report-block__summary--muted {
  color: #475569;
  font-size: 13px;
}

.ai-report-kpis {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ai-report-kpis span,
.ai-question-item {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(248, 250, 252, 0.92);
  color: #334155;
  font-size: 12px;
  font-weight: 600;
  max-width: 100%;
}

.ai-focus-list,
.ai-question-list {
  display: grid;
  gap: 10px;
}

.ai-focus-item {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.92);
  color: #334155;
}

.ai-focus-item strong {
  color: #0f172a;
  font-size: 14px;
}

.ai-focus-item small,
.ai-focus-item p {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
}

.ai-focus-item.is-warning {
  background: rgba(255, 247, 237, 0.92);
}

.ai-focus-item.is-good {
  background: rgba(236, 253, 245, 0.92);
}

.ai-report-markdown {
  margin: 0;
  padding: 18px;
  border-radius: 24px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}

.ai-metric-gap-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.ai-metric-gap-item {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(255, 255, 255, 0.72);
}

.ai-metric-gap-item strong {
  color: #0f172a;
  font-size: 13px;
}

.ai-metric-gap-item small {
  color: #64748b;
  line-height: 1.6;
}

.session-summary-pill,
.live-grid__item,
.runtime-grid__item {
  display: grid;
  gap: 8px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.7);
  color: #64748b;
}

.session-summary-pill strong,
.live-grid__item strong,
.runtime-grid__item strong {
  color: #0f172a;
  font-size: 28px;
  line-height: 1;
  letter-spacing: 0;
}

.session-list {
  display: grid;
  gap: 12px;
}

.session-card {
  display: grid;
  gap: 10px;
  padding: 16px;
}

.session-card.is-done {
  background: rgba(236, 253, 245, 0.82);
}

.session-card.is-warning {
  background: rgba(255, 247, 237, 0.88);
}

.session-card__head,
.session-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.session-card__head strong {
  color: #0f172a;
  font-size: 15px;
}

.session-card__status {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(241, 245, 249, 0.88);
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.session-card__meta,
.session-card p {
  color: #526071;
  font-size: 12px;
}

.session-card p {
  margin: 0;
  word-break: break-word;
}

.runtime-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.runtime-column {
  display: grid;
  gap: 10px;
}

@media (max-width: 1180px) {
  .statistics-hero,
  .upgrade-briefing,
  .executive-grid,
  .story-grid,
  .statistics-layout,
  .compact-split,
  .ai-report-grid,
  .ai-metric-gap-list,
  .summary-grid,
  .activity-chart-grid,
  .tool-overview-grid,
  .runtime-columns {
    grid-template-columns: 1fr;
  }

  .panel-card--wide {
    grid-column: auto;
  }

  .executive-portfolio-panel {
    grid-row: auto;
  }
}

@media (max-width: 960px) {
  .statistics-page {
    padding: 22px;
  }

  .upgrade-briefing__signals {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .statistics-hero__controls {
    grid-template-columns: 1fr;
  }

  .statistics-hero__controls-actions {
    justify-content: flex-start;
  }

  .statistics-hero__flow,
  .upgrade-loop,
  .session-summary-grid,
  .live-grid,
  .runtime-grid,
  .ai-metric-gap-list,
  .tool-overview-grid {
    grid-template-columns: 1fr 1fr;
  }

  .trend-chart__canvas {
    height: 280px;
  }

  .activity-chart__canvas,
  .project-activity-chart__canvas {
    height: 300px;
  }

  .activity-chart-card .activity-chart__canvas {
    height: 260px;
  }
}

@media (max-width: 680px) {
  .statistics-page {
    padding: 16px;
  }

  .statistics-hero__copy,
  .statistics-hero__focus,
  .upgrade-loop-panel,
  .upgrade-briefing__primary,
  .story-card,
  .panel-card,
  .summary-card {
    padding: 18px;
    border-radius: 24px;
  }

  .statistics-hero__title {
    max-width: none;
    font-size: 28px;
  }

  .statistics-hero__copy {
    min-height: 0;
    padding: 18px;
    border-radius: 22px;
  }

  .upgrade-decision,
  .upgrade-loop-panel__head,
  .upgrade-signal-card {
    border-radius: 18px;
  }

  .upgrade-loop-panel__head {
    align-items: flex-start;
    flex-direction: column;
  }

  .upgrade-loop-panel__head b {
    width: 68px;
    height: 68px;
    border-radius: 22px;
    font-size: 32px;
  }

  .statistics-hero__score strong {
    font-size: 48px;
  }

  .statistics-hero__controls-main {
    grid-template-columns: 1fr;
  }

  .statistics-hero__controls-actions,
  .panel-card__actions {
    width: 100%;
  }

  .statistics-hero__controls-actions :deep(.el-button),
  .panel-card__actions :deep(.el-button) {
    flex: 1 1 100%;
    margin-left: 0;
  }

  .statistics-hero__flow,
  .upgrade-loop,
  .upgrade-briefing__signals,
  .session-summary-grid,
  .live-grid,
  .runtime-grid,
  .ai-metric-gap-list,
  .tool-overview-grid,
  .runtime-columns {
    grid-template-columns: 1fr;
  }

  .activity-judgement,
  .executive-project-card__main,
  .ai-report-collapsed {
    align-items: flex-start;
    flex-direction: column;
  }

  .activity-judgement span {
    text-align: left;
  }

  .ai-report-collapsed__metrics {
    justify-content: flex-start;
  }
}
</style>
