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
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button
            v-for="action in getPrimaryPersonaActions(row)"
            :key="`${row.id}-${action.key}`"
            text
            :type="action.type"
            size="small"
            @click="handlePersonaAction(row, action.key)"
          >
            {{ action.label }}
          </el-button>
          <el-dropdown
            v-if="getOverflowPersonaActions(row).length"
            trigger="click"
            @command="(actionKey) => handlePersonaAction(row, actionKey)"
          >
            <el-button text type="primary" size="small">更多</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="action in getOverflowPersonaActions(row)"
                  :key="`${row.id}-${action.key}`"
                  :command="action.key"
                >
                  {{ action.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!personas.length && !loading" description="暂无人设" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const loading = ref(false)
const personas = ref([])
const router = useRouter()

function getPersonaActions() {
  return [
    { key: 'detail', label: '详情', type: 'primary' },
    { key: 'edit', label: '编辑', type: 'primary' },
    { key: 'snapshots', label: '快照' },
    { key: 'delete', label: '删除', type: 'danger' },
  ]
}

function getPrimaryPersonaActions(row) {
  return getPersonaActions(row).slice(0, 3)
}

function getOverflowPersonaActions(row) {
  return getPersonaActions(row).slice(3)
}

function handlePersonaAction(row, actionKey) {
  switch (actionKey) {
    case 'detail':
      router.push(`/personas/${row.id}`)
      break
    case 'edit':
      router.push(`/personas/${row.id}/edit`)
      break
    case 'snapshots':
      void showSnapshots(row.id)
      break
    case 'delete':
      void handleDelete(row.id)
      break
    default:
      break
  }
}

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
