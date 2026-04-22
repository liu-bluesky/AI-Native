<template>
  <div v-loading="loading" class="statistics-page">
    <div class="statistics-page__ambient statistics-page__ambient--left" aria-hidden="true" />
    <div class="statistics-page__ambient statistics-page__ambient--right" aria-hidden="true" />
    <div class="statistics-page__mesh" aria-hidden="true" />

    <section class="statistics-hero">
      <div class="statistics-hero__copy">
        <div class="statistics-hero__eyebrow">Operations Insight</div>
        <h1 class="statistics-hero__title">统计不只看次数，要先给判断。</h1>
        <p class="statistics-hero__summary">
          这页把入口流量、真实 AI 员工、项目归因、工作会话和统计盲区压成一条判断链，不再把内容拆成只看次数的并列卡片。
        </p>
        <div class="statistics-hero__meta">
          <span>统计窗口 {{ days }} 天</span>
          <span>生成时间 {{ formatDateTime(data.generated_at) }}</span>
          <span>查看人 {{ data.viewer.username || "-" }}</span>
        </div>
      </div>

      <aside class="statistics-hero__focus">
        <div class="statistics-hero__score">
          <span>观测健康分</span>
          <strong>{{ data.insights.health_score || 0 }}</strong>
          <small>{{ healthLabel }}</small>
        </div>

        <div class="statistics-hero__controls">
          <el-select v-model="days" class="statistics-page__range" @change="refresh">
            <el-option :value="7" label="近 7 天" />
            <el-option :value="30" label="近 30 天" />
            <el-option :value="90" label="近 90 天" />
          </el-select>
          <el-button @click="refresh">刷新</el-button>
        </div>

        <div class="statistics-hero__flow">
          <article
            v-for="item in data.insights.flow || []"
            :key="item.label"
            class="statistics-hero__flow-card"
          >
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.meta }}</small>
          </article>
        </div>
      </aside>
    </section>

    <section class="summary-grid">
      <article v-for="card in summaryCards" :key="card.label" class="summary-card">
        <span class="summary-card__label">{{ card.label }}</span>
        <strong class="summary-card__value">{{ card.value }}</strong>
        <small class="summary-card__hint">{{ card.hint }}</small>
      </article>
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
        <div v-if="usageDaily.length" class="trend-list">
          <div v-for="item in usageDaily" :key="item.date" class="trend-row">
            <div class="trend-row__meta">
              <span class="trend-row__date">{{ item.date }}</span>
              <strong class="trend-row__value">{{ item.total_events }}</strong>
            </div>
            <div class="trend-row__bar-shell">
              <div class="trend-row__bar trend-row__bar--total" :style="{ width: `${item.totalPercent}%` }" />
              <div class="trend-row__bar trend-row__bar--tool" :style="{ width: `${item.toolPercent}%` }" />
            </div>
            <div class="trend-row__tags">
              <span>工具 {{ item.tool_calls }}</span>
              <span>连接 {{ item.connections }}</span>
            </div>
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
        <div class="compact-split">
          <div class="compact-split__block">
            <div class="compact-split__title">智能体</div>
            <p class="compact-split__hint">这里只统计真实 AI 员工调用，不再把 `mcp:query` 当成智能体。</p>
            <div v-if="agentActivityItems.length" class="agent-list">
              <article v-for="item in agentActivityItems" :key="item.employee_id" class="agent-list__item">
                <div class="agent-list__meta">
                  <strong>{{ item.employee_name || item.label || item.employee_id }}</strong>
                  <small>调用 {{ item.cnt || 0 }} · 在线 {{ item.active_entries || 0 }} · 项目 {{ item.project_count || 0 }}</small>
                </div>
                <span class="agent-list__score">{{ item.activity_score }}</span>
              </article>
            </div>
            <el-empty
              v-else
              :description="Number(data?.usage?.summary?.query_scope_events || 0) > 0
                ? '当前只有 query 入口流量，尚未稳定归因到真实 AI 员工'
                : '当前窗口内没有真实 AI 员工调用记录'"
            />
          </div>
          <div class="compact-split__block">
            <div class="compact-split__title">入口 / 编排器</div>
            <p class="compact-split__hint">这里单独看 `mcp:query`、`project:*`、`employee:*` 等入口 scope，反映实际承接流量的主入口。</p>
            <div v-if="entryScopeItems.length" class="scope-list">
              <article v-for="item in entryScopeItems" :key="item.scope_id" class="scope-list__item">
                <div class="scope-list__meta">
                  <strong>{{ item.scope_label || item.scope_id }}</strong>
                  <small>事件 {{ item.cnt || 0 }} · 工具 {{ item.tool_calls || 0 }} · 归因员工 {{ item.attributed_employee_count || 0 }}</small>
                </div>
                <span class="scope-list__score">{{ item.activity_score }}</span>
              </article>
            </div>
            <el-empty v-else description="当前窗口内暂无入口 scope 流量" />
          </div>
          <div class="compact-split__block">
            <div class="compact-split__title">开发者</div>
            <div v-if="rankedDevelopers.length" class="mini-rank-list">
              <article v-for="item in rankedDevelopers" :key="item.developer_name" class="mini-rank-list__item">
                <span>{{ item.developer_name }}</span>
                <strong>{{ item.cnt }}</strong>
              </article>
            </div>
            <el-empty v-else description="暂无开发者活跃数据" />
          </div>
        </div>
      </article>

      <article class="panel-card">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">Project Activity</div>
            <h2 class="panel-card__title">项目活跃度</h2>
          </div>
        </div>
        <div v-if="projectActivityItems.length" class="rank-list">
          <article v-for="item in projectActivityItems" :key="item.project_id || item.project_name" class="rank-list__item rank-list__item--tool">
            <div class="rank-list__meta">
              <div class="rank-list__meta-body">
                <strong>{{ item.project_name || item.project_id }}</strong>
                <small>
                  归因 {{ item.cnt || 0 }}
                  <template v-if="item.session_count || item.active_entries">
                    · 会话 {{ item.session_count || 0 }} · 在线 {{ item.active_entries || 0 }}
                  </template>
                  <template v-if="Number(item.avg_duration_ms || 0) > 0">
                    · 平均 {{ Math.round(Number(item.avg_duration_ms || 0)) }}ms
                  </template>
                </small>
              </div>
              <span class="rank-list__score">{{ item.activity_score }}</span>
            </div>
            <div class="rank-list__bar-shell">
              <div class="rank-list__bar" :style="{ width: `${item.percent}%` }" />
            </div>
          </article>
        </div>
        <el-empty v-else description="暂无项目活跃数据" />
      </article>

      <article class="panel-card">
        <div class="panel-card__head">
          <div>
            <div class="panel-card__eyebrow">Work Sessions</div>
            <h2 class="panel-card__title">工作会话推进</h2>
          </div>
        </div>
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
              <strong>{{ item.project_name }}</strong>
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
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import api from "@/utils/api.js";
import { formatDateTime } from "@/utils/date.js";

const loading = ref(false);
const days = ref(7);
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
});

const usageSummary = computed(() => data.value?.usage?.summary || {});
const liveSummary = computed(() => data.value?.live_activity?.summary || {});
const workSessionSummary = computed(() => data.value?.work_sessions?.summary || {});
const toolHealthSummary = computed(() => data.value?.usage?.tool_health || {});

const summaryCards = computed(() => [
  {
    label: "MCP 交互",
    value: usageSummary.value.total_events || 0,
    hint: `近 ${days.value} 天 · 工具 ${usageSummary.value.tool_calls || 0} / 连接 ${usageSummary.value.connections || 0}`,
  },
  {
    label: "工具完成态",
    value: `${Number(usageSummary.value.tool_success_rate || 0).toFixed(0)}%`,
    hint: `完成 ${usageSummary.value.finalized_tool_calls || 0} · 异常 ${Number(usageSummary.value.failed_tool_calls || 0) + Number(usageSummary.value.timeout_tool_calls || 0)}`,
  },
  {
    label: "项目归因",
    value: usageSummary.value.active_projects || liveSummary.value.active_projects || 0,
    hint: `Query 入口 ${usageSummary.value.query_scope_events || 0} · 在线 ${liveSummary.value.active_entries || 0}`,
  },
  {
    label: "工作会话",
    value: workSessionSummary.value.total_sessions || 0,
    hint: `进行中 ${workSessionSummary.value.in_progress_sessions || 0} · 完成 ${workSessionSummary.value.completed_sessions || 0}`,
  },
]);

const healthLabel = computed(() => {
  const score = Number(data.value?.insights?.health_score || 0);
  if (score >= 80) return "主链状态稳定";
  if (score >= 60) return "有结论，但还不够完整";
  return "能看见问题，但观测还偏弱";
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
  const maxTotal = daily.reduce((value, item) => Math.max(value, Number(item?.total_events || 0)), 0) || 1;
  return daily.map((item) => {
    const totalEvents = Number(item?.total_events || 0);
    const toolCalls = Number(item?.tool_calls || 0);
    return {
      ...item,
      totalPercent: Math.max(6, Math.round((totalEvents / maxTotal) * 100)),
      toolPercent: Math.max(4, Math.round((toolCalls / maxTotal) * 100)),
    };
  });
});

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
      project_name: item?.project_name || item?.project_id || "未标记项目",
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
    const key = row?.project_id || row?.project_name;
    if (!key) continue;
    merged.set(key, {
      project_id: row.project_id || "",
      project_name: row.project_name || row.project_id || "未标记项目",
      cnt: Number(row.cnt || 0),
      session_count: 0,
      event_count: Number(row.tool_calls || row.cnt || 0),
      active_entries: 0,
      developer_count: Number(row.developer_count || 0),
      avg_duration_ms: Number(row.avg_duration_ms || 0),
    });
  }

  for (const row of workProjects) {
    const key = row?.project_id || row?.project_name;
    if (!key) continue;
    const existing = merged.get(key) || {
      project_id: row.project_id || "",
      project_name: row.project_name || row.project_id || "未标记项目",
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
      project_name: existing.project_name || row.project_name || row.project_id || "未标记项目",
      session_count: Number(row.session_count || 0),
      event_count: Math.max(Number(existing.event_count || 0), Number(row.event_count || 0)),
    });
  }

  for (const row of liveProjects) {
    const key = row?.project_id || row?.project_name;
    if (!key) continue;
    const existing = merged.get(key) || {
      project_id: row.project_id || "",
      project_name: row.project_name || row.project_id || "未标记项目",
      session_count: 0,
      event_count: 0,
      active_entries: 0,
      developer_count: 0,
      avg_duration_ms: 0,
    };
    merged.set(key, {
      ...existing,
      project_id: existing.project_id || row.project_id || "",
      project_name: existing.project_name || row.project_name || row.project_id || "未标记项目",
      active_entries: Number(row.active_entries || 0),
      developer_count: Number(row.developer_count || 0),
    });
  }

  return withPercent(
    [...merged.values()]
      .map((row) => ({
        ...row,
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

async function refresh() {
  loading.value = true;
  try {
    const response = await api.get("/statistics/overview", {
      params: { days: days.value },
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
.summary-grid,
.story-grid,
.statistics-layout {
  position: relative;
  z-index: 1;
}

.statistics-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 420px);
  gap: 20px;
  align-items: stretch;
  margin-bottom: 18px;
}

.statistics-hero__copy,
.statistics-hero__focus,
.summary-card,
.story-card,
.panel-card {
  border: 1px solid rgba(255, 255, 255, 0.84);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(20px);
}

.statistics-hero__copy {
  padding: 28px;
  border-radius: 34px;
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
  max-width: 13ch;
  margin: 10px 0 0;
  color: #0f172a;
  font-size: clamp(38px, 6vw, 72px);
  line-height: 0.96;
  letter-spacing: -0.06em;
}

.statistics-hero__summary {
  max-width: 54ch;
  margin: 16px 0 0;
  color: #475569;
  font-size: 15px;
  line-height: 1.75;
}

.statistics-hero__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
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

.statistics-hero__focus {
  display: grid;
  gap: 16px;
  padding: 22px;
  border-radius: 30px;
  background:
    radial-gradient(circle at top left, rgba(251, 146, 60, 0.12), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(248, 250, 252, 0.78));
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
  letter-spacing: -0.06em;
}

.statistics-hero__controls {
  display: flex;
  gap: 10px;
}

.statistics-page__range {
  width: 124px;
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
  letter-spacing: -0.04em;
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
  letter-spacing: -0.05em;
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
  letter-spacing: -0.05em;
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
}

.panel-card--wide {
  grid-column: span 2;
}

.trend-list {
  display: grid;
  gap: 12px;
}

.trend-row {
  display: grid;
  grid-template-columns: 118px minmax(0, 1fr) 126px;
  gap: 12px;
  align-items: center;
}

.trend-row__meta,
.trend-row__tags {
  display: grid;
  gap: 2px;
  color: #64748b;
  font-size: 12px;
}

.trend-row__value {
  color: #0f172a;
  font-size: 20px;
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
  letter-spacing: -0.05em;
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
  letter-spacing: -0.04em;
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
  word-break: break-all;
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
  .story-grid,
  .statistics-layout,
  .compact-split,
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

  .statistics-hero__flow,
  .session-summary-grid,
  .live-grid,
  .runtime-grid,
  .tool-overview-grid {
    grid-template-columns: 1fr 1fr;
  }

  .trend-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .statistics-hero__flow,
  .session-summary-grid,
  .live-grid,
  .runtime-grid,
  .tool-overview-grid,
  .runtime-columns {
    grid-template-columns: 1fr;
  }
}
</style>
