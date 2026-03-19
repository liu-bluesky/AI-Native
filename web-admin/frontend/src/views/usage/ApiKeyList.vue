<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>API Key 管理</h3>
      <el-button v-if="canCreateKey" type="primary" @click="showCreate = true">创建 Key</el-button>
    </div>

    <el-table :data="keys" stripe>
      <el-table-column prop="key" label="Key" width="340" />
      <el-table-column prop="developer_name" label="用户" width="140" />
      <el-table-column label="创建时间" min-width="220">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="canDeleteKey"
            text
            type="danger"
            @click="handleDelete(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && !keys.length" description="暂无 API Key" :image-size="60" />

    <el-dialog v-model="showCreate" title="创建 API Key" width="400px">
      <el-form :model="form" label-position="top">
        <el-form-item label="用户姓名" required>
          <el-input v-model="form.developer_name" placeholder="输入用户姓名" />
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
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'
import { hasPermission } from '@/utils/permissions.js'

const loading = ref(false)
const keys = ref([])
const showCreate = ref(false)
const creating = ref(false)
const form = reactive({ developer_name: '' })
const canCreateKey = computed(() => hasPermission('button.apikey.create'))
const canDeleteKey = computed(() => hasPermission('button.apikey.deactivate'))

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
    fetchKeys()
  } catch {
    ElMessage.error('创建失败')
  } finally {
    creating.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除「${row.developer_name}」的 Key？删除后不可恢复。`, '确认')
  try {
    await api.delete(`/usage/keys/${row.key}`)
    ElMessage.success('已删除')
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
