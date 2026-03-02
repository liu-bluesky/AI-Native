<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>人设管理</h3>
      <el-button type="primary" size="small" @click="$router.push('/personas/create')">新建人设</el-button>
    </div>

    <el-table :data="personas" stripe>
      <el-table-column prop="name" label="名称" width="140" />
      <el-table-column prop="tone" label="语调" width="100" />
      <el-table-column prop="verbosity" label="风格" width="100" />
      <el-table-column prop="language" label="语言" width="80" />
      <el-table-column label="行为准则" show-overflow-tooltip>
        <template #default="{ row }">
          {{ (row.behaviors || []).join('、') || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="alignment_score" label="对齐分" width="90" align="center" />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="$router.push(`/personas/${row.id}`)">详情</el-button>
          <el-button text type="primary" size="small" @click="$router.push(`/personas/${row.id}/edit`)">编辑</el-button>
          <el-button text size="small" @click="showSnapshots(row.id)">快照</el-button>
          <el-button text type="danger" size="small" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!personas.length && !loading" description="暂无人设" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const loading = ref(false)
const personas = ref([])

async function fetchPersonas() {
  loading.value = true
  try {
    const data = await api.get('/personas')
    personas.value = data.personas || []
  } catch {
    ElMessage.error('加载人设列表失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete(personaId) {
  await ElMessageBox.confirm('确定删除该人设？', '确认')
  try {
    await api.delete(`/personas/${personaId}`)
    ElMessage.success('已删除')
    fetchPersonas()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function showSnapshots(personaId) {
  try {
    const data = await api.get(`/personas/${personaId}/snapshots`)
    const snaps = data.snapshots || []
    ElMessage.info(snaps.length ? `共 ${snaps.length} 个快照` : '暂无快照')
  } catch {
    ElMessage.error('加载快照失败')
  }
}

onMounted(fetchPersonas)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 { margin: 0; }
</style>
