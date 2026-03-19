<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>同步状态: {{ employeeId }}</h3>
      <el-button size="small" @click="$router.back()">返回</el-button>
    </div>

    <el-row :gutter="16" class="stats-row">
      <el-col :span="8">
        <el-statistic title="事件总数" :value="stats.total" />
      </el-col>
      <el-col :span="8">
        <el-statistic title="待推送" :value="stats.pending" />
      </el-col>
    </el-row>

    <el-table :data="events" stripe>
      <el-table-column prop="event_type" label="类型" width="140" />
      <el-table-column prop="message" label="消息" show-overflow-tooltip />
      <el-table-column prop="level" label="级别" width="80">
        <template #default="{ row }">
          <el-tag :type="levelColor(row.level)" size="small">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="delivered" label="已推送" width="80" align="center">
        <template #default="{ row }">{{ row.delivered ? '是' : '否' }}</template>
      </el-table-column>
      <el-table-column label="时间" width="220">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!events.length && !loading" description="暂无同步事件" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'

const route = useRoute()
const loading = ref(false)
const employeeId = computed(() => route.params.id)
const events = ref([])
const stats = reactive({ total: 0, pending: 0 })

function levelColor(level) {
  return { info: '', warning: 'warning', error: 'danger' }[level] || 'info'
}

async function fetchEvents() {
  loading.value = true
  try {
    const data = await api.get(`/sync/${employeeId.value}`)
    events.value = data.events || []
  } catch {
    ElMessage.error('加载同步事件失败')
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  try {
    const data = await api.get(`/sync/${employeeId.value}/stats`)
    Object.assign(stats, data)
  } catch { /* ignore */ }
}

onMounted(() => {
  fetchEvents()
  fetchStats()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 { margin: 0; }

.stats-row {
  margin-bottom: 16px;
}
</style>
