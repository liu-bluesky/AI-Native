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

      <el-table :data="pagedSessions" stripe @row-click="openSession">
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
              <el-tag v-for="item in row.phases || []" :key="`phase-${row.session_id}-${item}`" size="small" effect="plain">
                {{ item }}
              </el-tag>
              <el-tag v-for="item in (row.steps || []).slice(0, 2)" :key="`step-${row.session_id}-${item}`" size="small" type="info">
                {{ item }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.latest_status)" size="small">
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
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click.stop="openSession(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="filteredSessions.length" class="table-panel__pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, sizes"
          :total="filteredSessions.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>

      <el-empty v-if="!loading && !filteredSessions.length" description="暂无工作轨迹" />
    </section>

    <el-drawer v-model="detailVisible" :title="detailTitle" size="720px">
      <template v-if="detailLoading">
        <div class="detail-loading">正在加载会话详情...</div>
      </template>

      <template v-else-if="activeSession">
        <section class="detail-panel">
          <div class="detail-metrics">
            <div class="detail-metric">
              <span class="detail-metric__label">Session</span>
              <strong>{{ activeSession.session_id || '-' }}</strong>
            </div>
            <div class="detail-metric">
              <span class="detail-metric__label">项目</span>
              <strong>{{ activeSession.project_name || activeSession.project_id || '-' }}</strong>
            </div>
            <div class="detail-metric">
              <span class="detail-metric__label">状态</span>
              <strong>{{ activeSession.latest_status || '-' }}</strong>
            </div>
            <div class="detail-metric">
              <span class="detail-metric__label">事件数</span>
              <strong>{{ activeSession.event_count || 0 }}</strong>
            </div>
          </div>

          <div class="detail-section">
            <div class="detail-section__title">聚合字段</div>
            <div class="detail-chip-grid">
              <div class="detail-chip-box">
                <div class="detail-chip-box__label">阶段</div>
                <div class="tag-group">
                  <el-tag v-for="item in activeSession.phases || []" :key="`active-phase-${item}`" size="small" effect="plain">
                    {{ item }}
                  </el-tag>
                </div>
              </div>
              <div class="detail-chip-box">
                <div class="detail-chip-box__label">步骤</div>
                <div class="tag-group">
                  <el-tag v-for="item in activeSession.steps || []" :key="`active-step-${item}`" size="small" type="info">
                    {{ item }}
                  </el-tag>
                </div>
              </div>
            </div>
            <div class="detail-list-grid">
              <div class="detail-list-box">
                <div class="detail-list-box__label">相关文件</div>
                <ul>
                  <li v-for="item in activeSession.changed_files || []" :key="`file-${item}`">{{ item }}</li>
                </ul>
              </div>
              <div class="detail-list-box">
                <div class="detail-list-box__label">验证</div>
                <ul>
                  <li v-for="item in activeSession.verification || []" :key="`verify-${item}`">{{ item }}</li>
                </ul>
              </div>
              <div class="detail-list-box">
                <div class="detail-list-box__label">风险</div>
                <ul>
                  <li v-for="item in activeSession.risks || []" :key="`risk-${item}`">{{ item }}</li>
                </ul>
              </div>
              <div class="detail-list-box">
                <div class="detail-list-box__label">下一步</div>
                <ul>
                  <li v-for="item in activeSession.next_steps || []" :key="`next-${item}`">{{ item }}</li>
                </ul>
              </div>
            </div>
          </div>

          <div class="detail-section">
            <div class="detail-section__title">事件时间线</div>
            <div class="timeline-list">
              <article v-for="item in sessionEvents" :key="item.id" class="timeline-item">
                <div class="timeline-item__head">
                  <div>
                    <div class="timeline-item__title">
                      {{ item.phase || '未标注阶段' }}
                      <span v-if="item.step">/ {{ item.step }}</span>
                    </div>
                    <div class="timeline-item__meta">
                      <span>{{ item.event_type || item.source_kind || '-' }}</span>
                      <span>{{ item.status || '-' }}</span>
                      <span>{{ formatDateTime(item.created_at) }}</span>
                    </div>
                  </div>
                  <el-tag size="small" :type="statusTagType(item.status)">{{ item.status || 'unknown' }}</el-tag>
                </div>
                <p v-if="item.goal" class="timeline-item__text">{{ item.goal }}</p>
                <p v-if="item.content" class="timeline-item__text">{{ item.content }}</p>
                <ul v-if="item.facts?.length" class="timeline-item__list">
                  <li v-for="fact in item.facts" :key="`${item.id}-${fact}`">{{ fact }}</li>
                </ul>
              </article>
            </div>
          </div>
        </section>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'

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
  gap: 20px;
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
  padding: 24px;
}

.settings-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.settings-hero__eyebrow,
.table-panel__eyebrow,
.detail-section__title,
.detail-metric__label,
.detail-chip-box__label,
.detail-list-box__label {
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
  max-width: 720px;
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
  gap: 12px;
}

.filter-panel__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
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

.session-main__title {
  font-weight: 600;
  color: #0f172a;
}

.session-main__sub {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.tag-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-panel {
  display: grid;
  gap: 18px;
  padding: 8px;
}

.detail-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.detail-metric,
.detail-chip-box,
.detail-list-box,
.timeline-item {
  padding: 16px;
  border-radius: 20px;
  background: rgba(248, 250, 252, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.9);
}

.detail-metric strong {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  word-break: break-word;
}

.detail-section {
  display: grid;
  gap: 12px;
}

.detail-chip-grid,
.detail-list-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-list-box ul,
.timeline-item__list {
  margin: 10px 0 0;
  padding-left: 18px;
  color: #475569;
}

.timeline-list {
  display: grid;
  gap: 12px;
}

.timeline-item__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.timeline-item__title {
  font-weight: 600;
  color: #0f172a;
}

.timeline-item__meta {
  display: flex;
  gap: 10px;
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  flex-wrap: wrap;
}

.timeline-item__text {
  margin: 12px 0 0;
  color: #475569;
  line-height: 1.7;
  white-space: pre-wrap;
}

.detail-loading {
  padding: 24px 0;
  color: #64748b;
}

@media (max-width: 960px) {
  .settings-hero,
  .table-panel__head {
    flex-direction: column;
  }

  .filter-panel__grid,
  .detail-metrics,
  .detail-chip-grid,
  .detail-list-grid {
    grid-template-columns: 1fr;
  }
}
</style>
