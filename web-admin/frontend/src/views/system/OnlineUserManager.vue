<template>
  <div v-loading="loading" class="settings-page">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__eyebrow">Live Presence</div>
        <h1 class="settings-hero__title">在线用户</h1>
        <p class="settings-hero__summary">
          仅超级管理员可见。基于最近心跳展示当前仍在线的账号、访问位置与最近活跃时间。
        </p>
        <div class="settings-hero__meta">
          <span>当前在线 {{ users.length }}</span>
          <span>在线窗口 {{ ttlSeconds }} 秒</span>
        </div>
      </div>

      <div class="settings-hero__actions">
        <el-button @click="refresh">刷新</el-button>
      </div>
    </section>

    <section class="filter-panel">
      <div class="filter-panel__grid">
        <el-input
          v-model="filters.query"
          clearable
          placeholder="搜索用户名、角色、路径或 IP"
        />
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
          <div class="table-panel__eyebrow">Presence Registry</div>
          <div class="table-panel__title">在线列表</div>
        </div>
        <div class="table-panel__meta">共 {{ filteredUsers.length }} 条</div>
      </div>

      <el-table :data="pagedUsers" stripe>
        <el-table-column label="用户名" min-width="160">
          <template #default="{ row }">{{ row.username || '-' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small">
              {{ row.role === 'admin' ? '超级管理员' : row.role || 'user' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="当前位置" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">{{ row.current_path || '-' }}</template>
        </el-table-column>
        <el-table-column label="IP" min-width="130">
          <template #default="{ row }">{{ row.client_ip || '-' }}</template>
        </el-table-column>
        <el-table-column label="最近活跃" min-width="180">
          <template #default="{ row }">{{ formatDateTime(row.last_seen_at) }}</template>
        </el-table-column>
        <el-table-column label="首次出现" min-width="180">
          <template #default="{ row }">{{ formatDateTime(row.first_seen_at) }}</template>
        </el-table-column>
        <el-table-column label="客户端" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">{{ row.user_agent || '-' }}</template>
        </el-table-column>
      </el-table>

      <div v-if="filteredUsers.length" class="table-panel__pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, jumper, sizes"
          :total="filteredUsers.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>

      <el-empty v-if="!loading && !filteredUsers.length" description="当前没有在线用户" />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'

const loading = ref(false)
const users = ref([])
const currentPage = ref(1)
const pageSize = ref(10)
const ttlSeconds = ref(150)
let refreshTimer = null

const filters = reactive({
  query: '',
})

const filteredUsers = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  return (users.value || []).filter((item) => {
    if (!keyword) return true
    const haystack = [
      item.username,
      item.role,
      item.current_path,
      item.client_ip,
      item.user_agent,
    ]
      .map((value) => String(value || '').toLowerCase())
      .join('\n')
    return haystack.includes(keyword)
  })
})

const pagedUsers = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredUsers.value.slice(start, start + pageSize.value)
})

watch(
  () => [filters.query, pageSize.value],
  () => {
    currentPage.value = 1
  },
)

async function refresh() {
  loading.value = true
  try {
    const response = await api.get('/system/online-users')
    users.value = Array.isArray(response?.items) ? response.items : []
    ttlSeconds.value = Number(response?.ttl_seconds || 150)
  } catch (err) {
    ElMessage.error(err?.message || '在线用户加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void refresh()
  refreshTimer = window.setInterval(() => {
    void refresh()
  }, 30 * 1000)
})

onUnmounted(() => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.settings-page {
  display: grid;
  gap: 20px;
}

.settings-hero,
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
  grid-template-columns: minmax(0, 1fr) 180px;
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

@media (max-width: 900px) {
  .settings-hero {
    flex-direction: column;
  }

  .filter-panel__grid {
    grid-template-columns: 1fr;
  }
}
</style>
