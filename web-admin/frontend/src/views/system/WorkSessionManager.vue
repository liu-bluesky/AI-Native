<template>
  <div v-loading="loading" class="settings-page">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__eyebrow">Execution Trace</div>
        <h1 class="settings-hero__title">工作轨迹</h1>
        <p class="settings-hero__summary">
          查看统一查询 MCP 保存的结构化执行轨迹。按 session 聚合，直接看到阶段、步骤、验证、风险与下一步。
        </p>
        <div class="settings-hero__meta">
          <span>会话 {{ sessions.length }}</span>
          <span>当前筛选 {{ filteredSessions.length }}</span>
        </div>
      </div>

      <div class="settings-hero__actions">
        <el-button @click="refresh">刷新</el-button>
      </div>
    </section>

    <section class="filter-panel">
      <div class="filter-panel__grid">
        <el-input v-model="filters.query" clearable placeholder="搜索 session、阶段、步骤、验证或文件" />
        <el-select v-model="filters.projectId" clearable filterable placeholder="筛选项目">
          <el-option label="全部项目" value="" />
          <el-option
            v-for="item in projectOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="filters.employeeId" clearable filterable placeholder="筛选员工">
          <el-option label="全部员工" value="" />
          <el-option
            v-for="item in employeeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
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
          <div class="table-panel__eyebrow">Session Registry</div>
          <div class="table-panel__title">会话列表</div>
        </div>
        <div class="table-panel__meta">共 {{ filteredSessions.length }} 条</div>
      </div>

      <el-table class="session-table" :data="pagedSessions" stripe @row-click="openSession">
        <el-table-column label="Session ID" min-width="180">
          <template #default="{ row }">{{ row.session_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="项目" min-width="220">
          <template #default="{ row }">
            <div class="session-main">
              <div class="session-main__title">{{ row.project_name || row.project_id || '-' }}</div>
              <div class="session-main__sub">{{ row.project_id || '-' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="阶段 / 步骤" min-width="220">
          <template #default="{ row }">
            <div class="tag-group">
              <el-tag
                v-for="item in row.phases || []"
                :key="`phase-${row.session_id}-${item}`"
                class="session-chip session-chip--phase"
                size="small"
                effect="plain"
              >
                {{ item }}
              </el-tag>
              <el-tag
                v-for="item in (row.steps || []).slice(0, 2)"
                :key="`step-${row.session_id}-${item}`"
                class="session-chip session-chip--step"
                size="small"
                type="info"
              >
                {{ item }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag class="session-chip session-chip--status" :type="statusTagType(row.latest_status)" size="small">
              {{ row.latest_status || 'unknown' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="验证" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ (row.verification || []).join(' / ') || '-' }}</template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="180">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="120" fixed="right" class-name="table-action-column">
          <template #default="{ row }">
            <el-button class="session-table__action" text type="primary" @click.stop="openSession(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="filteredSessions.length" class="table-panel__pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, jumper, sizes"
          :total="filteredSessions.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>

      <el-empty v-if="!loading && !filteredSessions.length" description="暂无工作轨迹" />
    </section>

    <el-drawer
      v-model="detailVisible"
      class="session-detail-drawer"
      :title="detailTitle"
      size="min(680px, 90vw)"
    >
      <template v-if="detailLoading">
        <div class="detail-loading">正在加载会话详情...</div>
      </template>

      <template v-else-if="activeSession">
        <WorkSessionDetailPanel :session="activeSession" :events="sessionEvents" />
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import WorkSessionDetailPanel from '@/components/WorkSessionDetailPanel.vue'
import api from '@/utils/api.js'

const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const sessions = ref([])
const activeSession = ref(null)
const sessionEvents = ref([])
const projectCatalog = ref([])
const employeeCatalog = ref([])
const currentPage = ref(1)
const pageSize = ref(10)

const filters = reactive({
  query: '',
  projectId: '',
  employeeId: '',
})

const projectOptions = computed(() => {
  return (projectCatalog.value || []).map((item) => {
    const value = String(item?.id || '').trim()
    const name = String(item?.name || '').trim()
    return {
      value,
      label: name ? `${name} (${value})` : value,
    }
  })
})

const employeeOptions = computed(() => {
  return (employeeCatalog.value || []).map((item) => {
    const value = String(item?.id || '').trim()
    const name = String(item?.name || '').trim()
    return {
      value,
      label: name ? `${name} (${value})` : value,
    }
  })
})

const filteredSessions = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  const projectId = String(filters.projectId || '').trim()
  const employeeId = String(filters.employeeId || '').trim()
  return (sessions.value || []).filter((item) => {
    if (projectId && String(item.project_id || '').trim() !== projectId) return false
    if (employeeId && String(item.employee_id || '').trim() !== employeeId) return false
    if (!keyword) return true
    const haystack = [
      item.session_id,
      item.project_name,
      item.project_id,
      item.employee_id,
      ...(item.phases || []),
      ...(item.steps || []),
      ...(item.verification || []),
      ...(item.changed_files || []),
      ...(item.risks || []),
      ...(item.next_steps || []),
    ]
      .map((value) => String(value || '').toLowerCase())
      .join('\n')
    return haystack.includes(keyword)
  })
})

const pagedSessions = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredSessions.value.slice(start, start + pageSize.value)
})

const detailTitle = computed(() => {
  const sessionId = String(activeSession.value?.session_id || '').trim()
  return sessionId ? `工作轨迹 · ${sessionId}` : '工作轨迹详情'
})

watch(
  () => [filters.query, filters.projectId, filters.employeeId, pageSize.value],
  () => {
    currentPage.value = 1
  },
)

function statusTagType(status) {
  const value = String(status || '').trim().toLowerCase()
  if (value === 'completed') return 'success'
  if (value === 'blocked' || value === 'failed') return 'danger'
  if (value === 'in_progress') return 'warning'
  return 'info'
}

async function refresh() {
  loading.value = true
  try {
    const [response, meta] = await Promise.all([
      api.get('/work-sessions', {
        params: {
          limit: 200,
        },
      }),
      api.get('/work-sessions/meta'),
    ])
    sessions.value = Array.isArray(response?.items) ? response.items : []
    projectCatalog.value = Array.isArray(meta?.projects) ? meta.projects : []
    employeeCatalog.value = Array.isArray(meta?.employees) ? meta.employees : []
  } catch (err) {
    ElMessage.error(err?.message || '工作轨迹加载失败')
  } finally {
    loading.value = false
  }
}

async function openSession(row) {
  const sessionId = String(row?.session_id || '').trim()
  if (!sessionId) return
  detailVisible.value = true
  detailLoading.value = true
  try {
    const response = await api.get(`/work-sessions/${encodeURIComponent(sessionId)}`, {
      params: {
        project_id: row?.project_id || undefined,
        employee_id: row?.employee_id || undefined,
      },
    })
    activeSession.value = response?.session || null
    sessionEvents.value = Array.isArray(response?.items) ? response.items : []
  } catch (err) {
    ElMessage.error(err?.message || '工作轨迹详情加载失败')
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

onMounted(() => {
  refresh()
})
</script>

<style scoped>
.settings-page {
  display: grid;
  gap: 16px;
}

.settings-hero,
.filter-panel,
.table-panel,
.detail-panel {
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.92);
  border-radius: 28px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(18px);
}

.settings-hero,
.filter-panel,
.table-panel {
  padding: 22px;
}

.settings-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.settings-hero__eyebrow,
.table-panel__eyebrow {
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
  margin: 12px 0 0;
  max-width: 680px;
  color: #475569;
  line-height: 1.6;
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
  gap: 12px;
}

.filter-panel__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.table-panel__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.table-panel__meta {
  color: #64748b;
}

.table-panel__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.session-table :deep(.el-table__header th.el-table__cell) {
  padding: 9px 0;
  background: rgba(248, 250, 252, 0.76);
}

.session-table :deep(.el-table__header .cell) {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #64748b;
}

.session-table :deep(.el-table__body td.el-table__cell) {
  padding: 10px 0;
}

.session-table :deep(.el-table__body .cell) {
  line-height: 1.45;
}

.session-table :deep(.el-table__row) {
  cursor: pointer;
}

.session-main {
  display: grid;
  gap: 2px;
}

.session-main__title {
  font-weight: 600;
  font-size: 13px;
  line-height: 1.35;
  color: #0f172a;
}

.session-main__sub {
  color: #64748b;
  font-size: 11px;
  line-height: 1.35;
}

.tag-group {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.tag-group :deep(.el-tag),
.session-chip {
  --el-tag-border-radius: 999px;
  height: 22px;
  padding: 0 8px;
  font-size: 11px;
  line-height: 20px;
}

.session-chip--phase {
  background: rgba(255, 255, 255, 0.58);
}

.session-chip--step {
  background: rgba(240, 249, 255, 0.86);
}

.session-chip--status {
  min-width: 64px;
  justify-content: center;
}

.session-table__action {
  padding: 4px 0;
  font-size: 12px;
}

.session-detail-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 18px 18px 14px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.76);
}

.session-detail-drawer :deep(.el-drawer__title) {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.session-detail-drawer :deep(.el-drawer__body) {
  padding: 16px 18px 18px;
}

.detail-loading {
  padding: 18px 2px 12px;
  color: #64748b;
}

@media (max-width: 960px) {
  .settings-hero,
  .table-panel__head {
    flex-direction: column;
  }

  .filter-panel__grid {
    grid-template-columns: 1fr;
  }

  .settings-hero,
  .filter-panel,
  .table-panel {
    padding: 18px;
  }
}
</style>
