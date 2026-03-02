<template>
  <div>
    <div class="toolbar">
      <h3>AI 员工列表</h3>
      <el-button type="primary" @click="$router.push('/employees/create')">创建员工</el-button>
    </div>
    <el-table :data="employees" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="140" />
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="description" label="描述" />
      <el-table-column prop="tone" label="语调" width="100" />
      <el-table-column prop="verbosity" label="风格" width="100" />
      <el-table-column label="技能数" width="80">
        <template #default="{ row }">{{ row.skills?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="360" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="$router.push(`/employees/${row.id}`)">详情</el-button>
          <el-button text type="primary" @click="$router.push(`/employees/${row.id}/edit`)">编辑</el-button>
          <el-button text type="success" @click="$router.push(`/evolution/${row.id}`)">进化</el-button>
          <el-button text type="warning" @click="$router.push(`/review/${row.id}`)">审核</el-button>
          <el-button text @click="$router.push(`/memory/${row.id}`)">记忆</el-button>
          <el-button text @click="$router.push(`/sync/${row.id}`)">同步</el-button>
          <el-button text type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const employees = ref([])
const loading = ref(false)

async function fetchList() {
  loading.value = true
  try {
    const { employees: list } = await api.get('/employees')
    employees.value = list
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除员工「${row.name}」？`, '确认')
  try {
    await api.delete(`/employees/${row.id}`)
    ElMessage.success('已删除')
    fetchList()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(fetchList)
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
