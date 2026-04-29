<template>
  <div v-loading="loading" class="statistics-page">
    <div class="statistics-page__ambient statistics-page__ambient--left" aria-hidden="true" />
    <div class="statistics-page__ambient statistics-page__ambient--right" aria-hidden="true" />
    <div class="statistics-page__mesh" aria-hidden="true" />

    <section class="statistics-hero">
      <div class="statistics-hero__copy">
        <div class="statistics-hero__eyebrow">Upgrade Intelligence</div>
        <h1 class="statistics-hero__title">统计驱动下一次升级</h1>
        <p class="statistics-hero__summary">
          先判断系统现在卡在哪里，再把证据、升级动作和验证口径放到同一条闭环里。
        </p>
        <div class="upgrade-decision" :class="`is-${upgradeDecision.tone}`">
          <span>当前判断</span>
          <strong>{{ upgradeDecision.title }}</strong>
          <p>{{ upgradeDecision.description }}</p>
        </div>
        <div class="statistics-hero__meta">
          <span>统计窗口 {{ days }} 天</span>
          <span>统计范围 {{ currentScopeLabel }}</span>
          <span>生成时间 {{ formatDateTime(data.generated_at) }}</span>
          <span>查看人 {{ data.viewer.username || "-" }}</span>
        </div>
      </div>

      <aside class="upgrade-loop-panel">
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

        <div class="upgrade-loop-panel__head">
          <div>
            <span>循环升级状态</span>
            <strong>{{ upgradeDecision.status }}</strong>
          </div>
          <b>{{ data.insights.health_score || 0 }}</b>
        </div>

        <div class="upgrade-loop">
          <article
            v-for="item in upgradeLoopSteps"
            :key="item.label"
            class="upgrade-loop__step"
            :class="`is-${item.tone}`"
          >
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.meta }}</small>
          </article>
        </div>
      </aside>
    </section>

    <section class="upgrade-briefing">
      <article class="upgrade-briefing__primary">
        <span>Next Upgrade</span>
        <strong>{{ upgradeAction.title }}</strong>
        <p>{{ upgradeAction.description }}</p>
        <small>{{ upgradeAction.evidence }}</small>
      </article>
      <div class="upgrade-briefing__signals">
        <article v-for="card in upgradeSignalCards" :key="card.label" class="upgrade-signal-card">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small>{{ card.hint }}</small>
        </article>
      </div>
    </section>

    <section class="summary-grid">
      <article v-for="card in summaryCards" :key="card.label" class="summary-card">
        <span class="summary-card__label">{{ card.label }}</span>
        <strong class="summary-card__value">{{ card.value }}</strong>
        <small class="summary-card__hint">{{ card.hint }}</small>
      </article>
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
          <span>工作完成率 {{ formatPercent(aiReportKeyMetrics.completion_rate) }}</span>
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
              <span>工作完成率 {{ formatPercent(aiReportKeyMetrics.completion_rate) }}</span>
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

    <section class="story-grid">
      <article class="story-card">
        <div class="story-card__head">
          <div>
            <div class="story-card__eyebrow">What Matters</div>
            <h2 class="story-card__title">现在先看什么</h2>
          </div>
        </div>
        <div v-if="highlightItems.length" class="signal-list">
          <article
            v-for="item in highlightItems"
            :key="item.label"
            class="signal-list__item"
            :class="`is-${item.tone || 'neutral'}`"
          >
            <span class="signal-list__label">{{ item.label }}</span>
            <strong class="signal-list__value">{{ item.value }}</strong>
            <small class="signal-list__meta">{{ item.meta }}</small>
          </article>
        </div>
        <el-empty v-else description="当前窗口内还没有足够的高信号数据" />
      </article>

      <article class="story-card story-card--risk">
        <div class="story-card__head">
          <div>
            <div class="story-card__eyebrow">Blind Spots</div>
            <h2 class="story-card__title">当前缺点 / 统计盲区</h2>
          </div>
        </div>

        <div v-if="alertItems.length" class="alert-list">
          <article
            v-for="item in alertItems"
            :key="item.title"
            class="alert-list__item"
            :class="`is-${item.tone || 'neutral'}`"
          >
            <strong>{{ item.title }}</strong>
            <p>{{ item.description }}</p>
          </article>
        </div>

        <div class="gap-list">
          <article v-for="item in blindSpotItems" :key="item.key" class="gap-list__item">
            <strong>{{ item.title }}</strong>
            <p>{{ item.description }}</p>
          </article>
        </div>
      </article>
    </section>

    <section class="statistics-layout">
      <article class="panel-card panel-card--wide">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">Activity Trend</div>
            <h2 class="panel-card__title">MCP 交互趋势</h2>
          </div>
          <div class="panel-card__tag">先看趋势，再看明细</div>
        </div>
        <div v-if="usageDaily.length" class="trend-chart">
          <div ref="trendChartRef" class="trend-chart__canvas" />
          <div class="trend-chart__summary">
            <span>总交互 {{ usageSummary.total_events || 0 }}</span>
            <span>工具 {{ usageSummary.tool_calls || 0 }}</span>
            <span>连接 {{ usageSummary.connections || 0 }}</span>
          </div>
        </div>
        <el-empty v-else description="当前窗口内暂无 MCP 趋势数据" />
      </article>

      <article class="panel-card panel-card--wide">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">AI Employee Usage</div>
            <h2 class="panel-card__title">入口 / 智能体 / 开发者活跃度</h2>
          </div>
          <div class="panel-card__tag">真实员工和入口流量分开看</div>
        </div>
        <div class="activity-judgement">
          <strong>{{ activityJudgement.title }}</strong>
          <span>{{ activityJudgement.meta }}</span>
        </div>
        <div v-if="activityChartItems.length" class="activity-chart">
          <div ref="activityChartRef" class="activity-chart__canvas" />
          <div class="activity-chart__legend">
            <span v-for="item in activityLegendItems" :key="item.label">
              <i :style="{ background: item.color }" />
              {{ item.label }}
            </span>
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
            ? '当前只有 query 入口流量，尚未稳定归因到真实 AI 员工'
            : '当前窗口内暂无入口、智能体或开发者活跃数据'"
        />
      </article>

      <article class="panel-card panel-card--wide">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">Project Activity</div>
            <h2 class="panel-card__title">项目活跃度</h2>
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

      <article class="panel-card panel-card--wide">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">Delivery Closure</div>
            <h2 class="panel-card__title">工作会话闭环趋势</h2>
          </div>
          <div class="panel-card__tag">先看完成率，再看最近会话</div>
        </div>
        <div v-if="workSessionDaily.length" class="trend-chart trend-chart--closure">
          <div ref="closureTrendChartRef" class="trend-chart__canvas" />
          <div class="trend-chart__summary">
            <span>完成率 {{ formatPercent(workCompletionRate) }}</span>
            <span>闭环缺口 {{ workSessionSummary.closure_gap_sessions || 0 }}</span>
            <span>阻塞率 {{ formatPercent(workSessionSummary.blocked_rate) }}</span>
          </div>
        </div>
        <el-empty v-else description="当前窗口内暂无工作会话趋势数据" />
        <div class="session-summary-grid">
          <article v-for="card in workSessionCards" :key="card.label" class="session-summary-pill">
            <span>{{ card.label }}</span>
            <strong>{{ card.value }}</strong>
            <small>{{ card.hint }}</small>
          </article>
        </div>
        <div v-if="recentSessions.length" class="session-list">
          <article
            v-for="item in recentSessions"
            :key="item.session_id"
            class="session-card"
            :class="item.statusClass"
          >
            <div class="session-card__head">
              <strong>{{ item.display_name }}</strong>
              <span class="session-card__status">{{ item.statusLabel }}</span>
            </div>
            <div class="session-card__meta">
              <span>{{ item.session_id }}</span>
              <span>{{ formatDateTime(item.latest_updated_at) }}</span>
            </div>
            <p>{{ item.stageLabel }}</p>
            <p>{{ item.verificationLabel }}</p>
          </article>
        </div>
        <el-empty v-else description="当前窗口内暂无工作会话轨迹" />
      </article>

      <article class="panel-card panel-card--wide">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">Tool Coverage</div>
            <h2 class="panel-card__title">工具频次与稳定性放在一起看</h2>
          </div>
          <div class="panel-card__tag">频次、完成态和时延在同一屏收束</div>
        </div>
        <div class="tool-overview-grid">
          <article v-for="card in toolOverviewCards" :key="card.label" class="tool-overview-card">
            <span>{{ card.label }}</span>
            <strong>{{ card.value }}</strong>
            <small>{{ card.hint }}</small>
          </article>
        </div>
        <div v-if="rankedTools.length" class="rank-list">
          <article v-for="item in rankedTools" :key="item.tool_name" class="rank-list__item rank-list__item--tool">
            <div class="rank-list__meta">
              <div class="rank-list__meta-body">
                <strong>{{ item.tool_name }}</strong>
                <small>
                  成功 {{ Number(item.success_rate || 0).toFixed(1) }}%
                  <template v-if="Number(item.avg_duration_ms || 0) > 0">
                    · 平均 {{ Math.round(Number(item.avg_duration_ms || 0)) }}ms
                  </template>
                </small>
              </div>
              <span class="rank-list__score">{{ item.cnt }}</span>
            </div>
            <div class="rank-list__bar-shell">
              <div class="rank-list__bar" :style="{ width: `${item.percent}%` }" />
            </div>
          </article>
        </div>
        <el-empty v-else description="当前窗口内还没有足够的工具调用数据" />
      </article>

      <article class="panel-card">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">Live MCP</div>
            <h2 class="panel-card__title">在线入口状态</h2>
          </div>
        </div>
        <div class="live-grid">
          <article class="live-grid__item">
            <span>活跃入口</span>
            <strong>{{ liveSummary.active_entries || 0 }}</strong>
          </article>
          <article class="live-grid__item">
            <span>入口类型</span>
            <strong>{{ liveSummary.active_endpoint_types || 0 }}</strong>
          </article>
          <article class="live-grid__item">
            <span>关联项目</span>
            <strong>{{ liveSummary.active_projects || 0 }}</strong>
          </article>
          <article class="live-grid__item">
            <span>开发者</span>
            <strong>{{ liveSummary.active_developers || 0 }}</strong>
          </article>
        </div>
        <div v-if="endpointItems.length" class="endpoint-list">
          <article v-for="item in endpointItems" :key="item.endpoint_type" class="endpoint-list__item">
            <span>{{ item.endpoint_type }}</span>
            <strong>{{ item.count }}</strong>
          </article>
        </div>
        <el-empty v-else description="当前没有在线入口快照" />
      </article>

      <article class="panel-card">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">Runtime Metrics</div>
            <h2 class="panel-card__title">运行指标</h2>
          </div>
          <div class="panel-card__tag">服务端计数器与耗时样本</div>
        </div>
        <div class="runtime-grid">
          <article class="runtime-grid__item">
            <span>Counter</span>
            <strong>{{ data.runtime_metrics.counter_total || 0 }}</strong>
          </article>
          <article class="runtime-grid__item">
            <span>Histogram</span>
            <strong>{{ data.runtime_metrics.histogram_total || 0 }}</strong>
          </article>
          <article class="runtime-grid__item">
            <span>峰值样本</span>
            <strong>{{ runtimeHistogramItems[0]?.count || 0 }}</strong>
          </article>
          <article class="runtime-grid__item">
            <span>平均耗时</span>
            <strong>{{ runtimeHistogramItems[0]?.avg ? `${Math.round(Number(runtimeHistogramItems[0]?.avg || 0))}ms` : "暂无" }}</strong>
          </article>
        </div>
        <div v-if="runtimeCounterItems.length || runtimeHistogramItems.length" class="runtime-columns">
          <div class="runtime-column">
            <div class="runtime-column__title">Top Counters</div>
            <div v-if="runtimeCounterItems.length" class="metric-list">
              <article v-for="item in runtimeCounterItems" :key="item.key" class="metric-list__item">
                <span>{{ item.key }}</span>
                <strong>{{ item.value }}</strong>
              </article>
            </div>
            <el-empty v-else description="暂无 counter 指标" />
          </div>
          <div class="runtime-column">
            <div class="runtime-column__title">Top Histograms</div>
            <div v-if="runtimeHistogramItems.length" class="metric-list">
              <article v-for="item in runtimeHistogramItems" :key="item.key" class="metric-list__item">
                <div class="metric-list__body">
                  <span>{{ item.key }}</span>
                  <small>count {{ item.count }} · avg {{ Math.round(Number(item.avg || 0)) }}ms</small>
                </div>
                <strong>{{ Math.round(Number(item.max || 0)) }}ms</strong>
              </article>
            </div>
            <el-empty v-else description="暂无 histogram 指标" />
          </div>
        </div>
        <el-empty v-else description="当前还没有可展示的运行指标" />
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

import api from "@/utils/api.js";
import { formatDateTime } from "@/utils/date.js";
import { useRoute, useRouter } from "vue-router";
import { openRouteInDesktop } from "@/utils/desktop-app-bridge.js";

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

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
const trendChartRef = ref(null);
const closureTrendChartRef = ref(null);
const activityChartRef = ref(null);
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
  work_sessions: {
    summary: {},
    daily: [],
    recent: [],
    top_projects: [],
    top_employees: [],
  },
  live_activity: {
    summary: {},
    endpoint_breakdown: [],
    top_projects: [],
    top_agents: [],
  },
  runtime_metrics: {
    counter_total: 0,
    histogram_total: 0,
    top_counters: [],
    top_histograms: [],
  },
  insights: {
    health_score: 0,
    highlights: [],
    alerts: [],
    flow: [],
  },
  blind_spots: [],
  ai_report: null,
});
const projectScopeOptions = ref([]);
const recentProjectIds = ref([]);

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
const workSessionSummary = computed(() => data.value?.work_sessions?.summary || {});
const toolHealthSummary = computed(() => data.value?.usage?.tool_health || {});
const workCompletionRate = computed(() => Number(workSessionSummary.value.completion_rate || 0));

function formatPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

const leadingProject = computed(() => {
  const usageTop = Array.isArray(data.value?.usage?.top_projects) ? data.value.usage.top_projects[0] : null;
  const workTop = Array.isArray(data.value?.work_sessions?.top_projects) ? data.value.work_sessions.top_projects[0] : null;
  return usageTop || workTop || null;
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

const summaryCards = computed(() => [
  {
    label: "MCP 交互",
    value: usageSummary.value.total_events || 0,
    hint: `近 ${days.value} 天 · 工具 ${usageSummary.value.tool_calls || 0} / 连接 ${usageSummary.value.connections || 0}`,
  },
  {
    label: "工具成功率",
    value: `${Number(usageSummary.value.tool_success_rate || 0).toFixed(0)}%`,
    hint: `完成 ${usageSummary.value.finalized_tool_calls || 0} · 异常 ${Number(usageSummary.value.failed_tool_calls || 0) + Number(usageSummary.value.timeout_tool_calls || 0)}`,
  },
  {
    label: "工作完成率",
    value: formatPercent(workCompletionRate.value),
    hint: `完成 ${workSessionSummary.value.completed_sessions || 0} · 进行中 ${workSessionSummary.value.in_progress_sessions || 0}`,
  },
  {
    label: "项目集中度",
    value: formatPercent(projectConcentrationPercent.value),
    hint: `${leadingProject.value?.project_name || leadingProject.value?.project_id || "暂无主项目"} · ${Number(leadingProject.value?.cnt || leadingProject.value?.event_count || 0)} / ${usageSummary.value.total_events || 0}`,
  },
  {
    label: "活跃智能体",
    value: usageSummary.value.active_employees || liveSummary.value.active_agents || workSessionSummary.value.active_employees || 0,
    hint: `项目 ${usageSummary.value.active_projects || workSessionSummary.value.active_projects || liveSummary.value.active_projects || 0} · Query ${usageSummary.value.query_scope_events || 0}`,
  },
  {
    label: "模型 / ROI",
    value: `${usageSummary.value.active_models || 0} / ${usageSummary.value.active_prompt_versions || 0}`,
    hint: `模型调用 ${usageSummary.value.model_calls || 0} · token ${usageSummary.value.total_tokens || 0} · $${Number(usageSummary.value.total_cost_usd || 0).toFixed(4)}`,
  },
]);

const healthLabel = computed(() => {
  const score = Number(data.value?.insights?.health_score || 0);
  if (score >= 80) return "主链状态稳定";
  if (score >= 60) return "有结论，但还不够完整";
  return "能看见问题，但观测还偏弱";
});

const upgradeDecision = computed(() => {
  const score = Number(data.value?.insights?.health_score || 0);
  const completionRate = Number(workCompletionRate.value || 0);
  const activePromptVersions = Number(usageSummary.value.active_prompt_versions || 0);
  const totalTokens = Number(usageSummary.value.total_tokens || 0);
  const hasCost = Number(usageSummary.value.total_cost_usd || 0) > 0;
  if (completionRate > 0 && completionRate < 40) {
    return {
      tone: "warning",
      status: "先补闭环",
      title: "工作闭环偏低，升级先看交付完成率",
      description: `当前完成率 ${formatPercent(completionRate)}，比继续堆工具调用更需要把进行中的会话收口到可验证结果。`,
    };
  }
  if (totalTokens > 0 && (!hasCost || activePromptVersions <= 0)) {
    return {
      tone: "attention",
      status: "补齐度量",
      title: "AI 成本与 Prompt 版本还没形成 ROI 判断",
      description: "已经能看到模型调用和 token，但缺少成本、Prompt 版本或结果指标，升级效果还不能稳定复盘。",
    };
  }
  if (score >= 80) {
    return {
      tone: "good",
      status: "可以优化",
      title: "观测主链稳定，可以进入针对性优化",
      description: "入口、项目、工具和工作会话已经能形成判断链，下一步应围绕最高价值缺口做升级。",
    };
  }
  return {
    tone: "neutral",
    status: "先稳观测",
    title: "统计链路还不完整，先补齐关键观测点",
    description: "当前数据能指出方向，但还不足以支撑稳定的升级判断，需要先补齐盲区和验证口径。",
  };
});

const upgradeAction = computed(() => {
  const focus = aiReportFocusPoints.value[0];
  if (focus) {
    return {
      title: focus.title || "优先处理 AI 关注点",
      description: focus.recommended_action || focus.evidence || "先把 AI 报表中的最高优先级问题转成可执行升级任务。",
      evidence: focus.evidence || "来源：AI Ready Report",
    };
  }
  const alert = alertItems.value[0];
  if (alert) {
    return {
      title: alert.title || "优先处理当前告警",
      description: alert.description || "先处理影响判断质量的异常信号。",
      evidence: "来源：当前统计告警",
    };
  }
  const blindSpot = blindSpotItems.value[0];
  if (blindSpot) {
    return {
      title: blindSpot.title || "先补统计盲区",
      description: blindSpot.description || "先补齐会影响升级判断的数据缺口。",
      evidence: "来源：统计盲区",
    };
  }
  return {
    title: "把最高频路径沉淀成下一轮升级任务",
    description: "当前没有强告警时，优先选择最高频入口、最活跃项目或闭环缺口作为下一次升级对象。",
    evidence: `健康分 ${data.value?.insights?.health_score || 0} · 统计窗口 ${days.value} 天`,
  };
});

const upgradeLoopSteps = computed(() => [
  {
    label: "观测",
    value: data.value?.insights?.health_score || 0,
    meta: healthLabel.value,
    tone: Number(data.value?.insights?.health_score || 0) >= 80 ? "good" : "neutral",
  },
  {
    label: "判断",
    value: upgradeDecision.value.status,
    meta: upgradeDecision.value.title,
    tone: upgradeDecision.value.tone,
  },
  {
    label: "升级",
    value: aiReportFocusPoints.value.length || alertItems.value.length || blindSpotItems.value.length || "待定",
    meta: "可转任务的关注点",
    tone: aiReportFocusPoints.value.length || alertItems.value.length ? "attention" : "neutral",
  },
  {
    label: "验证",
    value: formatPercent(workCompletionRate.value),
    meta: `闭环缺口 ${workSessionSummary.value.closure_gap_sessions || 0}`,
    tone: Number(workCompletionRate.value || 0) >= 60 ? "good" : "warning",
  },
]);

const upgradeSignalCards = computed(() => [
  {
    label: "主链健康",
    value: data.value?.insights?.health_score || 0,
    hint: healthLabel.value,
  },
  {
    label: "闭环完成",
    value: formatPercent(workCompletionRate.value),
    hint: `完成 ${workSessionSummary.value.completed_sessions || 0} / 进行中 ${workSessionSummary.value.in_progress_sessions || 0}`,
  },
  {
    label: "主项目集中",
    value: formatPercent(projectConcentrationPercent.value),
    hint: leadingProject.value?.project_name || leadingProject.value?.project_id || "暂无主项目",
  },
  {
    label: "ROI 可见性",
    value: `${usageSummary.value.active_models || 0}/${usageSummary.value.active_prompt_versions || 0}`,
    hint: `模型 / Prompt 版本 · token ${usageSummary.value.total_tokens || 0}`,
  },
]);

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
const highlightItems = computed(() => data.value?.insights?.highlights || []);
const alertItems = computed(() => data.value?.insights?.alerts || []);
const blindSpotItems = computed(() => data.value?.blind_spots || []);
const workSessionCards = computed(() => [
  {
    label: "进行中",
    value: workSessionSummary.value.in_progress_sessions || 0,
    hint: "仍在推进的工作会话",
  },
  {
    label: "已完成",
    value: workSessionSummary.value.completed_sessions || 0,
    hint: "已经收尾并写回验证的会话",
  },
  {
    label: "完成率",
    value: formatPercent(workSessionSummary.value.completion_rate),
    hint: `闭环缺口 ${workSessionSummary.value.closure_gap_sessions || 0}`,
  },
  {
    label: "阻塞",
    value: workSessionSummary.value.blocked_sessions || 0,
    hint: "需要重点排查的会话",
  },
  {
    label: "参与智能体",
    value: workSessionSummary.value.active_employees || 0,
    hint: "近窗口内出现在会话轨迹里的真实 AI 员工",
  },
]);
const toolOverviewCards = computed(() => [
  {
    label: "成功率",
    value: `${Number(toolHealthSummary.value.success_rate || 0).toFixed(0)}%`,
    hint: `成功 ${toolHealthSummary.value.successful_calls || 0} / 失败 ${Number(toolHealthSummary.value.failed_calls || 0) + Number(toolHealthSummary.value.timeout_calls || 0)}`,
  },
  {
    label: "完成态",
    value: toolHealthSummary.value.finalized_calls || 0,
    hint: "已记录 success / failed / timeout 的调用",
  },
  {
    label: "平均时延",
    value: toolHealthSummary.value.avg_duration_ms ? `${Math.round(Number(toolHealthSummary.value.avg_duration_ms || 0))}ms` : "暂无",
    hint: "仅基于完成态样本计算",
  },
  {
    label: "工具覆盖",
    value: usageSummary.value.active_tools || 0,
    hint: "近窗口内实际被调用过的工具数",
  },
]);

const usageDaily = computed(() => {
  const daily = Array.isArray(data.value?.usage?.daily) ? data.value.usage.daily : [];
  return daily.map((item) => ({
    ...item,
    total_events: Number(item?.total_events || 0),
    tool_calls: Number(item?.tool_calls || 0),
    connections: Number(item?.connections || 0),
  }));
});

const workSessionDaily = computed(() => {
  const daily = Array.isArray(data.value?.work_sessions?.daily) ? data.value.work_sessions.daily : [];
  return daily.map((item) => ({
    ...item,
    total_sessions: Number(item?.total_sessions || 0),
    completed_sessions: Number(item?.completed_sessions || 0),
    in_progress_sessions: Number(item?.in_progress_sessions || 0),
    blocked_sessions: Number(item?.blocked_sessions || 0),
    completion_rate: Number(item?.completion_rate || 0),
  }));
});

let trendChart = null;
let closureTrendChart = null;
let activityChart = null;
let projectChart = null;

function compactChartLabel(value, maxLength = 14) {
  const normalized = String(value || "").trim();
  if (!normalized) return "-";
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}...` : normalized;
}

const trendChartOption = computed(() => {
  const labels = usageDaily.value.map((item) => item.date || "");
  const totalSeries = usageDaily.value.map((item) => item.total_events || 0);
  const toolSeries = usageDaily.value.map((item) => item.tool_calls || 0);
  const connectionSeries = usageDaily.value.map((item) => item.connections || 0);
  return {
    animationDuration: 400,
    color: ["#f97316", "#2563eb", "#0f172a"],
    grid: {
      top: 42,
      right: 16,
      bottom: 24,
      left: 16,
      containLabel: true,
    },
    legend: {
      top: 0,
      icon: "circle",
      itemWidth: 10,
      itemHeight: 10,
      textStyle: {
        color: "#475569",
        fontSize: 12,
      },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(15, 23, 42, 0.92)",
      borderWidth: 0,
      textStyle: {
        color: "#e2e8f0",
      },
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: labels,
      axisLine: {
        lineStyle: {
          color: "rgba(148, 163, 184, 0.35)",
        },
      },
      axisTick: {
        show: false,
      },
      axisLabel: {
        color: "#64748b",
        fontSize: 11,
      },
    },
    yAxis: {
      type: "value",
      splitNumber: 4,
      axisLine: {
        show: false,
      },
      axisTick: {
        show: false,
      },
      axisLabel: {
        color: "#64748b",
        fontSize: 11,
      },
      splitLine: {
        lineStyle: {
          color: "rgba(148, 163, 184, 0.18)",
        },
      },
    },
    series: [
      {
        name: "总交互",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 8,
        lineStyle: {
          width: 3,
        },
        areaStyle: {
          color: "rgba(249, 115, 22, 0.12)",
        },
        data: totalSeries,
      },
      {
        name: "工具调用",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 7,
        lineStyle: {
          width: 2.5,
        },
        data: toolSeries,
      },
      {
        name: "连接",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: {
          width: 2,
          type: "dashed",
        },
        data: connectionSeries,
      },
    ],
  };
});

const closureTrendChartOption = computed(() => {
  const labels = workSessionDaily.value.map((item) => item.date || "");
  const completedSeries = workSessionDaily.value.map((item) => item.completed_sessions || 0);
  const progressSeries = workSessionDaily.value.map((item) => item.in_progress_sessions || 0);
  const completionRateSeries = workSessionDaily.value.map((item) => item.completion_rate || 0);
  return {
    animationDuration: 400,
    color: ["#16a34a", "#f97316", "#2563eb"],
    grid: {
      top: 42,
      right: 18,
      bottom: 24,
      left: 16,
      containLabel: true,
    },
    legend: {
      top: 0,
      icon: "circle",
      itemWidth: 10,
      itemHeight: 10,
      textStyle: {
        color: "#475569",
        fontSize: 12,
      },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(15, 23, 42, 0.92)",
      borderWidth: 0,
      textStyle: {
        color: "#e2e8f0",
      },
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: labels,
      axisLine: {
        lineStyle: {
          color: "rgba(148, 163, 184, 0.35)",
        },
      },
      axisTick: {
        show: false,
      },
      axisLabel: {
        color: "#64748b",
        fontSize: 11,
      },
    },
    yAxis: [
      {
        type: "value",
        splitNumber: 4,
        axisLine: {
          show: false,
        },
        axisTick: {
          show: false,
        },
        axisLabel: {
          color: "#64748b",
          fontSize: 11,
        },
        splitLine: {
          lineStyle: {
            color: "rgba(148, 163, 184, 0.18)",
          },
        },
      },
      {
        type: "value",
        min: 0,
        max: 100,
        axisLine: {
          show: false,
        },
        axisTick: {
          show: false,
        },
        axisLabel: {
          color: "#64748b",
          fontSize: 11,
          formatter: "{value}%",
        },
        splitLine: {
          show: false,
        },
      },
    ],
    series: [
      {
        name: "已完成",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 8,
        lineStyle: {
          width: 3,
        },
        areaStyle: {
          color: "rgba(22, 163, 74, 0.12)",
        },
        data: completedSeries,
      },
      {
        name: "进行中",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 7,
        lineStyle: {
          width: 2.5,
        },
        data: progressSeries,
      },
      {
        name: "完成率",
        type: "line",
        smooth: true,
        yAxisIndex: 1,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: {
          width: 2,
          type: "dashed",
        },
        data: completionRateSeries,
      },
    ],
  };
});

const activityLegendItems = computed(() => [
  { label: "智能体", color: ACTIVITY_GROUP_COLORS.agent },
  { label: "入口", color: ACTIVITY_GROUP_COLORS.entry },
  { label: "开发者", color: ACTIVITY_GROUP_COLORS.developer },
]);

const activityChartItems = computed(() => {
  const agentRows = agentActivityItems.value.slice(0, 4).map((item) => ({
    key: `agent:${item.employee_id || item.employee_name}`,
    group: "agent",
    groupLabel: "智能体",
    name: item.employee_name || item.label || item.employee_id || "未知智能体",
    value: Number(item.activity_score || item.cnt || 0),
    meta: `调用 ${item.cnt || 0} · 在线 ${item.active_entries || 0}`,
  }));
  const entryRows = entryScopeItems.value.slice(0, 4).map((item) => ({
    key: `entry:${item.scope_id || item.scope_label}`,
    group: "entry",
    groupLabel: "入口",
    name: item.scope_label || item.scope_id || "未知入口",
    value: Number(item.activity_score || item.cnt || 0),
    meta: `事件 ${item.cnt || 0} · 工具 ${item.tool_calls || 0}`,
  }));
  const developerRows = rankedDevelopers.value.slice(0, 4).map((item) => ({
    key: `developer:${item.developer_name}`,
    group: "developer",
    groupLabel: "开发者",
    name: item.developer_name || "未知开发者",
    value: Number(item.cnt || 0),
    meta: `记录 ${item.cnt || 0}`,
  }));
  return [...agentRows, ...entryRows, ...developerRows]
    .filter((item) => item.value > 0)
    .sort((left, right) => right.value - left.value)
    .slice(0, 10);
});

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
  const developerCount = rankedDevelopers.value.length;
  return {
    title: `当前主力是${leader.groupLabel}：${leader.name}`,
    meta: `活跃分 ${leader.value} · 覆盖 ${entryCount} 个入口、${agentCount} 个智能体、${developerCount} 位开发者`,
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
      : "真实 AI 员工调用不足",
  },
  {
    label: "主开发者",
    value: rankedDevelopers.value[0]?.developer_name || "暂无",
    hint: rankedDevelopers.value[0] ? `记录 ${rankedDevelopers.value[0].cnt || 0}` : "开发者记录不足",
  },
]);

const activityChartOption = computed(() => {
  const items = activityChartItems.value;
  return {
    animationDuration: 400,
    grid: {
      top: 8,
      right: 34,
      bottom: 8,
      left: 116,
      containLabel: false,
    },
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
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: {
        lineStyle: {
          color: "rgba(148, 163, 184, 0.16)",
        },
      },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: items.map((item) => compactChartLabel(item.name)),
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
        barWidth: 14,
        borderRadius: [0, 8, 8, 0],
        label: {
          show: true,
          position: "right",
          color: "#0f172a",
          fontSize: 12,
          fontWeight: 700,
        },
        data: items.map((item) => ({
          value: item.value,
          itemStyle: {
            color: ACTIVITY_GROUP_COLORS[item.group] || "#64748b",
          },
        })),
      },
    ],
  };
});

const projectActivityJudgement = computed(() => {
  const leader = projectActivityItems.value[0];
  if (!leader) {
    return {
      title: "项目活跃度还不足以排序",
      meta: "暂无可归因项目、在线入口或工作会话样本。",
    };
  }
  const concentration = projectConcentrationPercent.value;
  return {
    title: `主项目：${leader.display_name}`,
    meta: `活跃分 ${leader.activity_score || 0} · 集中度 ${formatPercent(concentration)} · 会话 ${leader.session_count || 0}`,
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
    label: "会话最多",
    value: projectActivityItems.value
      .slice()
      .sort((left, right) => Number(right.session_count || 0) - Number(left.session_count || 0))[0]?.display_name || "暂无",
    hint: "按工作会话数判断",
  },
]);

const projectChartOption = computed(() => {
  const items = projectActivityItems.value.slice(0, 8);
  return {
    animationDuration: 400,
    grid: {
      top: 8,
      right: 34,
      bottom: 8,
      left: 132,
      containLabel: false,
    },
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
          `归因 ${item.cnt || 0} · 会话 ${item.session_count || 0} · 在线 ${item.active_entries || 0}`,
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: {
        lineStyle: {
          color: "rgba(148, 163, 184, 0.16)",
        },
      },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: items.map((item) => compactChartLabel(item.display_name, 16)),
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
        barWidth: 16,
        borderRadius: [0, 8, 8, 0],
        label: {
          show: true,
          position: "right",
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

function disposeTrendChart() {
  if (!trendChart) return;
  trendChart.dispose();
  trendChart = null;
}

function disposeClosureTrendChart() {
  if (!closureTrendChart) return;
  closureTrendChart.dispose();
  closureTrendChart = null;
}

function disposeActivityChart() {
  if (!activityChart) return;
  activityChart.dispose();
  activityChart = null;
}

function disposeProjectChart() {
  if (!projectChart) return;
  projectChart.dispose();
  projectChart = null;
}

function resizeTrendChart() {
  if (!trendChart) return;
  trendChart.resize();
}

function resizeClosureTrendChart() {
  if (!closureTrendChart) return;
  closureTrendChart.resize();
}

function resizeActivityChart() {
  if (!activityChart) return;
  activityChart.resize();
}

function resizeProjectChart() {
  if (!projectChart) return;
  projectChart.resize();
}

async function renderTrendChart() {
  await nextTick();
  if (!usageDaily.value.length || !trendChartRef.value) {
    disposeTrendChart();
    return;
  }
  trendChart = echarts.getInstanceByDom(trendChartRef.value) || echarts.init(trendChartRef.value);
  trendChart.setOption(trendChartOption.value, true);
  trendChart.resize();
}

async function renderClosureTrendChart() {
  await nextTick();
  if (!workSessionDaily.value.length || !closureTrendChartRef.value) {
    disposeClosureTrendChart();
    return;
  }
  closureTrendChart =
    echarts.getInstanceByDom(closureTrendChartRef.value) ||
    echarts.init(closureTrendChartRef.value);
  closureTrendChart.setOption(closureTrendChartOption.value, true);
  closureTrendChart.resize();
}

async function renderActivityChart() {
  await nextTick();
  if (!activityChartItems.value.length || !activityChartRef.value) {
    disposeActivityChart();
    return;
  }
  activityChart =
    echarts.getInstanceByDom(activityChartRef.value) ||
    echarts.init(activityChartRef.value);
  activityChart.setOption(activityChartOption.value, true);
  activityChart.resize();
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

const rankedTools = computed(() => withPercent(data.value?.usage?.top_tools, "cnt"));
const rankedDevelopers = computed(() => withPercent(data.value?.usage?.top_developers, "cnt"));
const endpointItems = computed(() => withPercent(data.value?.live_activity?.endpoint_breakdown, "count"));
const runtimeCounterItems = computed(() => {
  const counters = Array.isArray(data.value?.runtime_metrics?.top_counters)
    ? data.value.runtime_metrics.top_counters
    : [];
  return counters.slice(0, 4);
});
const runtimeHistogramItems = computed(() => {
  const histograms = Array.isArray(data.value?.runtime_metrics?.top_histograms)
    ? data.value.runtime_metrics.top_histograms
    : [];
  return histograms.slice(0, 4);
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
      .sort((left, right) => Number(right.activity_score || 0) - Number(left.activity_score || 0))
      .slice(0, 6),
    "activity_score",
  );
});

const recentSessions = computed(() => {
  const sessions = Array.isArray(data.value?.work_sessions?.recent) ? data.value.work_sessions.recent : [];
  return sessions.slice(0, 4).map((item) => {
    const rawStatus = String(item?.latest_status || "").toLowerCase();
    let statusLabel = "进行中";
    let statusClass = "";
    if (rawStatus === "completed") {
      statusLabel = "已完成";
      statusClass = "is-done";
    } else if (["blocked", "failed"].includes(rawStatus)) {
      statusLabel = "待处理";
      statusClass = "is-warning";
    }
    return {
      ...item,
      statusClass,
      statusLabel,
      project_name: normalizeProjectName(item?.project_name),
      display_name: resolveProjectDisplayName(item?.project_name, item?.project_id),
      stageLabel: [item?.phases?.[0], item?.steps?.[0]].filter(Boolean).join(" · ") || "阶段信息待补齐",
      verificationLabel: item?.verification?.[0] || "还没有写入验证说明",
    };
  });
});

const agentActivityItems = computed(() => {
  const usageAgents = Array.isArray(data.value?.usage?.top_employees) ? data.value.usage.top_employees : [];
  const liveAgents = Array.isArray(data.value?.live_activity?.top_agents) ? data.value.live_activity.top_agents : [];
  const workSessionAgents = Array.isArray(data.value?.work_sessions?.top_employees)
    ? data.value.work_sessions.top_employees
    : [];
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

  for (const row of workSessionAgents) {
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
    const sessionEvents = Number(row.event_count || row.session_count || 0);
    merged.set(key, {
      ...existing,
      employee_id: existing.employee_id || row.employee_id || "",
      employee_name: existing.employee_name || row.employee_name || row.employee_id || "未知智能体",
      cnt: Math.max(Number(existing.cnt || 0), sessionEvents),
      project_count: Math.max(Number(existing.project_count || 0), Number(row.project_count || 0)),
      activity_score: Number(existing.activity_score || 0) + sessionEvents,
    });
  }

  return [...merged.values()]
    .sort((left, right) => Number(right.activity_score || 0) - Number(left.activity_score || 0))
    .slice(0, 6);
});

const projectActivityItems = computed(() => {
  const usageProjects = Array.isArray(data.value?.usage?.top_projects)
    ? data.value.usage.top_projects
    : [];
  const workProjects = Array.isArray(data.value?.work_sessions?.top_projects)
    ? data.value.work_sessions.top_projects
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

  for (const row of workProjects) {
    const normalizedProjectName = normalizeProjectName(row?.project_name);
    const key = row?.project_id || normalizedProjectName;
    if (!key) continue;
    const existing = merged.get(key) || {
      project_id: row.project_id || "",
      project_name: "",
      cnt: 0,
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
      session_count: Number(row.session_count || 0),
      event_count: Math.max(Number(existing.event_count || 0), Number(row.event_count || 0)),
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
          Number(row.session_count || 0),
      }))
      .sort((left, right) => Number(right.activity_score || 0) - Number(left.activity_score || 0))
      .slice(0, 8),
    "activity_score",
  );
});

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
  window.addEventListener("resize", resizeTrendChart);
  window.addEventListener("resize", resizeClosureTrendChart);
  window.addEventListener("resize", resizeActivityChart);
  window.addEventListener("resize", resizeProjectChart);
  fetchProjectScopes();
  refresh();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeTrendChart);
  window.removeEventListener("resize", resizeClosureTrendChart);
  window.removeEventListener("resize", resizeActivityChart);
  window.removeEventListener("resize", resizeProjectChart);
  disposeTrendChart();
  disposeClosureTrendChart();
  disposeActivityChart();
  disposeProjectChart();
});

watch(usageDaily, () => {
  renderTrendChart();
});

watch(workSessionDaily, () => {
  renderClosureTrendChart();
});

watch(activityChartItems, () => {
  renderActivityChart();
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
  min-height: 100vh;
  padding: 32px;
  overflow: hidden;
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

.activity-chart__canvas,
.project-activity-chart__canvas {
  width: 100%;
  height: 330px;
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
  .story-grid,
  .statistics-layout,
  .compact-split,
  .ai-report-grid,
  .ai-metric-gap-list,
  .summary-grid,
  .tool-overview-grid,
  .runtime-columns {
    grid-template-columns: 1fr;
  }

  .panel-card--wide {
    grid-column: auto;
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
