<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>记忆管理: {{ employeeId }}</h3>
      <div class="toolbar-right">
        <el-input v-model="query" placeholder="搜索记忆" size="small" class="search-input"
          @keyup.enter="fetchMemories" clearable />
        <el-button size="small" type="primary" @click="fetchMemories">搜索</el-button>
        <el-button
          size="small"
          type="danger"
          plain
          :disabled="!selectedMemoryIds.length"
          @click="handleBatchDelete"
        >
          批量删除
        </el-button>
        <el-button size="small" @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-row :gutter="16" class="stats-row">
      <el-col :span="8">
        <el-statistic title="记忆总数" :value="memCount" />
      </el-col>
      <el-col :span="8">
        <el-button type="warning" size="small" @click="handleCompress">压缩记忆</el-button>
      </el-col>
      <el-col :span="8">
        <el-button size="small" @click="fetchImportant">仅看重要记忆</el-button>
      </el-col>
    </el-row>

    <el-table :data="memories" stripe row-key="id" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="46" />
      <el-table-column prop="project_name" label="项目" width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.project_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="type" label="类型" width="140">
        <template #default="{ row }">{{ getMemoryTypeLabel(row.type) }}</template>
      </el-table-column>
      <el-table-column prop="content" label="内容" show-overflow-tooltip />
      <el-table-column prop="importance" label="重要度" width="80" align="center" />
      <el-table-column prop="scope" label="作用域" width="120" />
      <el-table-column prop="access_count" label="访问" width="70" align="center" />
      <el-table-column label="创建时间" width="220">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="80" fixed="right" class-name="table-action-column">
        <template #default="{ row }">
          <el-button text type="danger" size="small" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!memories.length && !loading" description="暂无记忆" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'

const route = useRoute()
const loading = ref(false)
const employeeId = computed(() => route.params.id)
const memories = ref([])
const selectedMemoryIds = ref([])
const memCount = ref(0)
const query = ref('')
const MEMORY_TYPE_LABELS = {
  'project-context': '项目上下文',
  'user-preference': '用户偏好',
  'key-event': '关键事件',
  'learned-pattern': '学习模式',
  'long-term-goal': '长期目标',
  taboo: '禁忌项',
  'stable-preference': '稳定偏好',
  'decision-pattern': '决策模式',
}

function getMemoryTypeLabel(type) {
  const key = String(type || '').trim()
  return MEMORY_TYPE_LABELS[key] || key || '-'
}

async function fetchMemories() {
  loading.value = true
  try {
    const params = query.value ? `?query=${encodeURIComponent(query.value)}` : ''
    const data = await api.get(`/memory/${employeeId.value}${params}`)
    memories.value = data.memories || []
    selectedMemoryIds.value = []
  } catch {
    ElMessage.error('加载记忆失败')
  } finally {
    loading.value = false
  }
}

async function fetchCount() {
  try {
    const data = await api.get(`/memory/${employeeId.value}/count`)
    memCount.value = data.count || 0
  } catch { /* ignore */ }
}

async function fetchImportant() {
  loading.value = true
  try {
    const data = await api.get(`/memory/${employeeId.value}/important`)
    memories.value = data.memories || []
    selectedMemoryIds.value = []
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete(memoryId) {
  await ElMessageBox.confirm('确定删除该记忆？', '确认')
  try {
    await api.delete(`/memory/item/${memoryId}`)
    ElMessage.success('已删除')
    fetchMemories()
    fetchCount()
  } catch {
    ElMessage.error('删除失败')
  }
}

function onSelectionChange(rows) {
  selectedMemoryIds.value = (rows || []).map((item) => String(item.id || '').trim()).filter(Boolean)
}

async function handleBatchDelete() {
  if (!selectedMemoryIds.value.length) {
    ElMessage.warning('请先勾选要删除的记忆')
    return
  }
  await ElMessageBox.confirm(`确认批量删除 ${selectedMemoryIds.value.length} 条记忆？`, '批量删除确认', { type: 'warning' })
  try {
    const result = await api.post('/memory/batch-delete', {
      employee_id: employeeId.value,
      memory_ids: selectedMemoryIds.value,
    })
    const deletedCount = Number(result.deleted_count || 0)
    const skippedCount = Number((result.skipped_ids || []).length || 0)
    const missingCount = Number((result.missing_ids || []).length || 0)
    if (deletedCount > 0) {
      ElMessage.success(`批量删除完成：成功 ${deletedCount} 条`)
    } else {
      ElMessage.warning('未删除任何记忆')
    }
    if (skippedCount > 0 || missingCount > 0) {
      ElMessage.warning(`跳过 ${skippedCount} 条，缺失 ${missingCount} 条`)
    }
    await fetchMemories()
    await fetchCount()
  } catch {
    ElMessage.error('批量删除失败')
  }
}

async function handleCompress() {
  await ElMessageBox.confirm('压缩将保留前50条重要记忆，删除其余。继续？', '压缩记忆')
  try {
    const data = await api.post(`/memory/${employeeId.value}/compress`, { keep_top: 50 })
    ElMessage.success(`已压缩，移除 ${data.removed_count} 条`)
    fetchMemories()
    fetchCount()
  } catch {
    ElMessage.error('压缩失败')
  }
}

onMounted(() => {
  fetchMemories()
  fetchCount()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar h3 {
  margin: 0;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-input {
  width: 200px;
}

.stats-row {
  margin-bottom: 16px;
}
</style>
