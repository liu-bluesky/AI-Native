<template>
  <div v-loading="loading" class="settings-page">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__eyebrow">MCP Monitor</div>
        <h1 class="settings-hero__title">系统 MCP 在线开发监控</h1>
        <p class="settings-hero__summary">
          仅超级管理员可见。这里监控的是系统提供的 MCP 入口运行态，包括项目、员工、技能、规则和统一查询 MCP，
          用最近请求窗口判断当前哪些入口正在被接入和使用。
        </p>
        <div class="settings-hero__meta">
          <span>活跃窗口 {{ ttlSeconds }} 秒</span>
        </div>
      </div>

      <div class="settings-hero__actions">
        <el-button @click="refresh">刷新状态</el-button>
      </div>
    </section>

    <section class="stats-grid">
      <article v-for="card in summaryCards" :key="card.label" class="stat-card">
        <div class="stat-card__label">{{ card.label }}</div>
        <div class="stat-card__value">{{ card.value }}</div>
        <div class="stat-card__hint">{{ card.hint }}</div>
      </article>
    </section>

    <section class="filter-panel">
      <div class="filter-panel__grid">
        <el-input
          v-model="filters.query"
          clearable
          placeholder="搜索类型、对象、项目、开发者、IP、路径或会话"
        />
        <el-select v-model="filters.endpointType" placeholder="入口类型">
          <el-option label="全部类型" value="all" />
          <el-option label="项目" value="project" />
          <el-option label="员工" value="employee" />
          <el-option label="技能" value="skill" />
          <el-option label="规则" value="rule" />
          <el-option label="统一查询" value="query" />
        </el-select>
        <el-select v-model="filters.transport" placeholder="传输方式">
          <el-option label="全部方式" value="all" />
          <el-option label="SSE" value="sse" />
          <el-option label="Streamable HTTP" value="streamable-http" />
          <el-option label="Messages" value="messages" />
        </el-select>
        <el-select v-model="filters.method" placeholder="请求方法">
          <el-option label="全部方法" value="all" />
          <el-option label="GET" value="GET" />
          <el-option label="POST" value="POST" />
        </el-select>
        <el-select v-model="pageSize" placeholder="每页条数">
          <el-option :value="10" label="10 条/页" />
          <el-option :value="20" label="20 条/页" />
          <el-option :value="50" label="50 条/页" />
        </el-select>
      </div>
    </section>

    <section class="table-panel">
      <div class="table-panel__head">
        <div>
          <div class="table-panel__eyebrow">Live System Activity</div>
          <div class="table-panel__title">在线开发中的系统 MCP 会话</div>
        </div>
        <div class="table-panel__meta">共 {{ filteredItems.length }} 条</div>
      </div>

      <el-table :data="pagedItems" stripe>
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="endpointTagType(row.endpoint_type)" size="small">
              {{ endpointTypeLabel(row.endpoint_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="对象" min-width="220">
          <template #default="{ row }">
            <div class="entity-cell">
              <div class="entity-cell__title">{{ row.entity_name || row.entity_id || '-' }}</div>
              <div class="entity-cell__meta">{{ row.entity_id || '-' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="关联项目" min-width="220">
          <template #default="{ row }">
            <div class="entity-cell">
              <div class="entity-cell__title">{{ row.project_name || '-' }}</div>
              <div class="entity-cell__meta">{{ row.project_id || '-' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="使用者" min-width="220">
          <template #default="{ row }">
            <div class="entity-cell">
              <div class="entity-cell__title">{{ row.key_owner_username || row.developer_name || '-' }}</div>
              <div class="entity-cell__meta">
                {{ row.developer_name ? `API Key 标识 · ${row.developer_name}` : '未记录 API Key 标识' }}
              </div>
              <div class="entity-cell__meta">{{ row.api_key || '未记录 API Key' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="传输" width="140">
          <template #default="{ row }">
            <el-tag type="info" size="small">
              {{ transportLabel(row.transport) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" min-width="140">
          <template #default="{ row }">
            <span>{{ row.client_ip || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="请求" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="request-cell">
              <div class="request-cell__method">{{ row.method || '-' }}</div>
              <div class="request-cell__path">{{ row.path || '-' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="会话" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.session_id || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最近活跃" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.last_seen_at) }}
          </template>
        </el-table-column>
        <el-table-column label="首次出现" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.first_seen_at) }}
          </template>
        </el-table-column>
        <el-table-column label="请求数" width="100">
          <template #default="{ row }">
            {{ row.request_count || 0 }}
          </template>
        </el-table-column>
      </el-table>

      <div v-if="filteredItems.length" class="table-panel__pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, jumper, sizes"
          :total="filteredItems.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>

      <el-empty v-if="!loading && !filteredItems.length" description="最近没有系统 MCP 在线开发活动" />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'

const loading = ref(false)
const activityItems = ref([])
const summary = ref({
  active_entries: 0,
  active_endpoint_types: 0,
  active_projects: 0,
  active_developers: 0,
})
const currentPage = ref(1)
const pageSize = ref(10)
const ttlSeconds = ref(180)
let refreshTimer = null

const filters = reactive({
  query: '',
  endpointType: 'all',
  transport: 'all',
  method: 'all',
})

const summaryCards = computed(() => [
  { label: '活跃入口', value: summary.value.active_entries, hint: '最近 TTL 窗口内的系统 MCP 活动条目' },
  { label: '入口类型', value: summary.value.active_endpoint_types, hint: '当前被使用的 MCP 类别数' },
  { label: '关联项目', value: summary.value.active_projects, hint: '被接入中的项目数' },
  { label: '在线开发者', value: summary.value.active_developers, hint: '按入口 + 对象 + 开发者 + IP 聚合' },
  { label: '活跃窗口', value: ttlSeconds.value, hint: '超过该秒数未继续请求会自动消失' },
])

const filteredItems = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  return (activityItems.value || []).filter((item) => {
    const endpointType = String(item?.endpoint_type || '').trim()
    const transport = String(item?.transport || '').trim()
    const method = String(item?.method || '').trim().toUpperCase()
    if (filters.endpointType !== 'all' && endpointType !== filters.endpointType) {
      return false
    }
    if (filters.transport !== 'all' && transport !== filters.transport) {
      return false
    }
    if (filters.method !== 'all' && method !== filters.method) {
      return false
    }
    if (!keyword) {
      return true
    }
    const haystack = [
      item?.endpoint_type,
      item?.entity_name,
      item?.entity_id,
      item?.project_name,
      item?.project_id,
      item?.key_owner_username,
      item?.developer_name,
      item?.api_key,
      item?.client_ip,
      item?.transport,
      item?.method,
      item?.path,
      item?.session_id,
    ]
      .map((value) => String(value || '').toLowerCase())
      .join('\n')
    return haystack.includes(keyword)
  })
})

const pagedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredItems.value.slice(start, start + pageSize.value)
})

watch(
  () => [filters.query, filters.endpointType, filters.transport, filters.method, pageSize.value],
  () => {
    currentPage.value = 1
  },
)

async function refresh() {
  loading.value = true
  try {
    const response = await api.get('/system/mcp-monitor/activity')
    activityItems.value = Array.isArray(response?.items) ? response.items : []
    ttlSeconds.value = Number(response?.ttl_seconds || 180)
    summary.value = {
      active_entries: Number(response?.summary?.active_entries || 0),
      active_endpoint_types: Number(response?.summary?.active_endpoint_types || 0),
      active_projects: Number(response?.summary?.active_projects || 0),
      active_developers: Number(response?.summary?.active_developers || 0),
    }
  } catch (err) {
    ElMessage.error(err?.message || '系统 MCP 活动加载失败')
  } finally {
    loading.value = false
  }
}

function endpointTypeLabel(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'project') return '项目'
  if (normalized === 'employee') return '员工'
  if (normalized === 'skill') return '技能'
  if (normalized === 'rule') return '规则'
  if (normalized === 'query') return '统一查询'
  return value || '-'
}

function endpointTagType(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'project') return 'success'
  if (normalized === 'employee') return 'warning'
  if (normalized === 'skill') return 'info'
  if (normalized === 'rule') return 'danger'
  if (normalized === 'query') return 'info'
  return 'info'
}

function transportLabel(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'sse') return 'SSE'
  if (normalized === 'streamable-http') return 'Streamable HTTP'
  if (normalized === 'messages') return 'Messages'
  if (normalized === 'http') return 'HTTP'
  return value || '-'
}

function clearRefreshTimer() {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(() => {
  void refresh()
  refreshTimer = window.setInterval(() => {
    void refresh()
  }, 20 * 1000)
})

onUnmounted(() => {
  clearRefreshTimer()
})
</script>

<style scoped>
.settings-page {
  display: grid;
  gap: 20px;
}

.settings-hero,
.stats-grid,
.filter-panel,
.table-panel {
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.92);
  border-radius: 28px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(18px);
}

.settings-hero,
.filter-panel,
.table-panel {
  padding: 24px;
}

.settings-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.settings-hero__eyebrow,
.table-panel__eyebrow,
.stat-card__label {
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #64748b;
}

.settings-hero__title,
.table-panel__title {
  margin: 8px 0 0;
  font-size: 28px;
  line-height: 1.15;
  color: #0f172a;
}

.settings-hero__summary {
  margin: 14px 0 0;
  max-width: 760px;
  color: #475569;
  line-height: 1.7;
}

.settings-hero__meta {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  color: #64748b;
  flex-wrap: wrap;
}

.settings-hero__actions {
  display: flex;
  align-items: flex-start;
}

.stats-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: 20px 24px;
}

.stat-card {
  display: grid;
  gap: 8px;
  min-height: 110px;
  padding: 18px;
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.95), rgba(241, 245, 249, 0.88));
  border: 1px solid rgba(226, 232, 240, 0.95);
}

.stat-card__value {
  font-size: 32px;
  font-weight: 700;
  color: #0f172a;
}

.stat-card__hint {
  color: #64748b;
  line-height: 1.6;
}

.filter-panel__grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) repeat(4, minmax(140px, 180px));
  gap: 14px;
}

.table-panel__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.table-panel__meta {
  color: #64748b;
}

.table-panel__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}

.entity-cell {
  display: grid;
  gap: 6px;
}

.entity-cell__title {
  color: #0f172a;
  font-weight: 600;
}

.entity-cell__meta {
  color: #64748b;
  line-height: 1.5;
}

.request-cell {
  display: grid;
  gap: 6px;
}

.request-cell__method {
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.request-cell__path {
  color: #334155;
  word-break: break-all;
}

@media (max-width: 1080px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .filter-panel__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .settings-hero {
    flex-direction: column;
  }
}

@media (max-width: 640px) {
  .stats-grid,
  .filter-panel__grid {
    grid-template-columns: 1fr;
  }
}
</style>
