<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>角色管理</h3>
      <div class="toolbar-right">
        <el-button v-if="canCreate" type="primary" @click="openCreateDialog">新增角色</el-button>
        <el-button @click="refresh">刷新</el-button>
      </div>
    </div>

    <el-table :data="roles" stripe>
      <el-table-column prop="id" label="角色 ID" width="140" />
      <el-table-column prop="name" label="角色名称" width="160" />
      <el-table-column label="内置" width="90">
        <template #default="{ row }">
          <el-tag :type="row.built_in ? 'warning' : 'info'" size="small">
            {{ row.built_in ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
      <el-table-column label="权限数" width="100">
        <template #default="{ row }">
          {{ row.permissions?.includes('*') ? '全部' : row.permissions?.length || 0 }}
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" min-width="180" />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canUpdate" text type="primary" @click="openEditDialog(row)">编辑</el-button>
          <el-button
            v-if="canDelete && !row.built_in"
            text
            type="danger"
            @click="deleteRole(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !roles.length" description="暂无角色" />

    <el-dialog v-model="showDialog" :title="dialogTitle" width="760px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="90px">
        <el-form-item label="角色 ID" prop="id">
          <el-input
            v-model="form.id"
            :disabled="formMode === 'edit'"
            placeholder="如: auditor（2-32位，小写字母开头）"
          />
        </el-form-item>
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" placeholder="如: 审计员" />
        </el-form-item>
        <el-form-item label="角色描述">
          <el-input v-model="form.description" placeholder="可选" />
        </el-form-item>
      </el-form>

      <el-divider content-position="left">菜单权限</el-divider>
      <el-checkbox-group v-model="form.permissions" class="permission-grid">
        <el-checkbox
          v-for="item in menuItems"
          :key="item.key"
          :label="item.key"
          :disabled="allPermissionSelected"
        >
          {{ item.label }}
        </el-checkbox>
      </el-checkbox-group>

      <el-divider content-position="left">按钮权限</el-divider>
      <el-checkbox-group v-model="form.permissions" class="permission-grid">
        <el-checkbox
          v-for="item in buttonItems"
          :key="item.key"
          :label="item.key"
          :disabled="allPermissionSelected"
        >
          {{ item.label }}
        </el-checkbox>
      </el-checkbox-group>

      <el-divider content-position="left">高级</el-divider>
      <el-checkbox v-model="allPermissionSelected">
        全部权限（*）
      </el-checkbox>

      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { hasPermission } from '@/utils/permissions.js'

const loading = ref(false)
const saving = ref(false)
const roles = ref([])
const catalogGroups = ref([])
const showDialog = ref(false)
const formRef = ref(null)
const formMode = ref('create')

const form = reactive({
  id: '',
  name: '',
  description: '',
  permissions: [],
})

const rules = {
  id: [
    { required: true, message: '请输入角色 ID', trigger: 'blur' },
    {
      pattern: /^[a-z][a-z0-9_.-]{1,31}$/,
      message: '2-32位，小写字母开头，仅支持小写字母数字_.-',
      trigger: 'blur',
    },
  ],
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
}

const menuItems = computed(() => {
  const group = (catalogGroups.value || []).find((item) => item.group === 'menu')
  return group?.items || []
})

const buttonItems = computed(() => {
  const group = (catalogGroups.value || []).find((item) => item.group === 'button')
  return group?.items || []
})

const allPermissionSelected = computed({
  get() {
    return (form.permissions || []).includes('*')
  },
  set(value) {
    if (value) {
      form.permissions = ['*']
      return
    }
    form.permissions = []
  },
})

const dialogTitle = computed(() => (formMode.value === 'edit' ? '编辑角色' : '新增角色'))
const canCreate = computed(() => hasPermission('button.roles.create'))
const canUpdate = computed(() => hasPermission('button.roles.update'))
const canDelete = computed(() => hasPermission('button.roles.delete'))

function resetForm() {
  form.id = ''
  form.name = ''
  form.description = ''
  form.permissions = []
}

function openCreateDialog() {
  resetForm()
  formMode.value = 'create'
  showDialog.value = true
}

function openEditDialog(row) {
  formMode.value = 'edit'
  form.id = String(row.id || '')
  form.name = String(row.name || '')
  form.description = String(row.description || '')
  form.permissions = Array.isArray(row.permissions) ? [...row.permissions] : []
  showDialog.value = true
}

async function fetchRoles() {
  const data = await api.get('/roles')
  roles.value = data.roles || []
}

async function fetchCatalog() {
  const data = await api.get('/roles/catalog')
  catalogGroups.value = data.groups || []
}

async function refresh() {
  loading.value = true
  try {
    await Promise.all([fetchRoles(), fetchCatalog()])
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '加载角色失败')
    roles.value = []
    catalogGroups.value = []
  } finally {
    loading.value = false
  }
}

async function submitRole() {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = {
      id: form.id,
      name: form.name,
      description: form.description,
      permissions: form.permissions,
    }
    if (formMode.value === 'edit') {
      await api.put(`/roles/${encodeURIComponent(form.id)}`, {
        name: payload.name,
        description: payload.description,
        permissions: payload.permissions,
      })
    } else {
      await api.post('/roles', payload)
    }
    ElMessage.success('角色保存成功')
    showDialog.value = false
    await refresh()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '角色保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteRole(row) {
  await ElMessageBox.confirm(`确定删除角色 ${row.name || row.id}？`, '确认', { type: 'warning' })
  try {
    await api.delete(`/roles/${encodeURIComponent(row.id)}`)
    ElMessage.success('角色已删除')
    await refresh()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '删除角色失败')
  }
}

onMounted(refresh)
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
  gap: 8px;
}

.permission-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(240px, 1fr));
  gap: 8px 12px;
}
</style>
