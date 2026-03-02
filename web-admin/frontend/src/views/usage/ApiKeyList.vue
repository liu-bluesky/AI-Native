<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>API Key 管理</h3>
      <el-button type="primary" @click="showCreate = true">创建 Key</el-button>
    </div>

    <el-table :data="keys" stripe>
      <el-table-column prop="key" label="Key" width="340" />
      <el-table-column prop="developer_name" label="用户" width="140" />
      <el-table-column prop="created_by" label="创建人" width="120" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" />
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.is_active" text type="danger" @click="handleDeactivate(row)">停用</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && !keys.length" description="暂无 API Key" :image-size="60" />

    <el-dialog v-model="showCreate" title="创建 API Key" width="400px">
      <el-form :model="form" label-position="top">
        <el-form-item label="用户姓名" required>
          <el-input v-model="form.developer_name" placeholder="输入用户姓名" />
        </el-form-item>
        <el-form-item label="创建人">
          <el-input v-model="form.created_by" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const loading = ref(false)
const keys = ref([])
const showCreate = ref(false)
const creating = ref(false)
const form = reactive({ developer_name: '', created_by: '' })

async function fetchKeys() {
  loading.value = true
  try {
    const { keys: list } = await api.get('/usage/keys')
    keys.value = list
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!form.developer_name.trim()) {
    ElMessage.error('请输入用户姓名')
    return
  }
  creating.value = true
  try {
    const result = await api.post('/usage/keys', form)
    ElMessage.success(`Key 已创建: ${result.key}`)
    showCreate.value = false
    form.developer_name = ''
    form.created_by = ''
    fetchKeys()
  } catch {
    ElMessage.error('创建失败')
  } finally {
    creating.value = false
  }
}

async function handleDeactivate(row) {
  await ElMessageBox.confirm(`确定停用「${row.developer_name}」的 Key？`, '确认')
  try {
    await api.delete(`/usage/keys/${row.key}`)
    ElMessage.success('已停用')
    fetchKeys()
  } catch {
    ElMessage.error('操作失败')
  }
}

onMounted(fetchKeys)
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
