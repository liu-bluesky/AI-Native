<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>候选规则审核: {{ employeeId }}</h3>
      <el-button @click="$router.back()">返回</el-button>
    </div>

    <el-empty v-if="!candidates.length && !loading" description="暂无待审候选规则" />

    <el-card v-for="c in candidates" :key="c.id" class="candidate-card">
      <template #header>
        <div class="card-header">
          <span>{{ c.title }}</span>
          <el-tag :type="riskColor(c.risk_domain)" size="small">{{ c.risk_domain }}</el-tag>
        </div>
      </template>

      <el-descriptions :column="2" size="small">
        <el-descriptions-item label="ID">{{ c.id }}</el-descriptions-item>
        <el-descriptions-item label="置信度">{{ c.confidence }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ c.source_type }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ c.status }}</el-descriptions-item>
      </el-descriptions>

      <p class="desc">{{ c.description }}</p>

      <div class="actions">
        <el-button type="success" size="small" @click="handleAction(c.id, 'approve')">确认入库</el-button>
        <el-button type="warning" size="small" @click="openEdit(c)">编辑后入库</el-button>
        <el-button type="danger" size="small" @click="handleAction(c.id, 'reject')">拒绝</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const route = useRoute()
const loading = ref(false)
const employeeId = computed(() => route.params.id)
const candidates = ref([])

function riskColor(domain) {
  return { low: 'success', medium: 'warning', high: 'danger' }[domain] || 'info'
}

async function fetchCandidates() {
  loading.value = true
  try {
    const data = await api.get(`/evolution/${employeeId.value}/candidates`)
    candidates.value = data.candidates || []
  } catch {
    ElMessage.error('加载候选列表失败')
  } finally {
    loading.value = false
  }
}

async function handleAction(candidateId, action) {
  const username = localStorage.getItem('username') || 'admin'
  try {
    await api.post(`/evolution/candidates/${candidateId}/review`, {
      reviewed_by: username,
      action,
    })
    ElMessage.success(action === 'approve' ? '已入库' : '已拒绝')
    fetchCandidates()
  } catch {
    ElMessage.error('操作失败')
  }
}

async function openEdit(candidate) {
  const { value } = await ElMessageBox.prompt('编辑规则描述', '编辑后入库', {
    inputValue: candidate.description,
    inputType: 'textarea',
  })
  if (!value) return
  const username = localStorage.getItem('username') || 'admin'
  try {
    await api.post(`/evolution/candidates/${candidate.id}/review`, {
      reviewed_by: username,
      action: 'edit',
      edits: value,
    })
    ElMessage.success('已更新')
    fetchCandidates()
  } catch {
    ElMessage.error('编辑失败')
  }
}

onMounted(fetchCandidates)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 { margin: 0; }
.candidate-card { margin-bottom: 16px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.desc { color: var(--color-text-secondary); margin: 12px 0; }
.actions { display: flex; gap: 8px; }
</style>
