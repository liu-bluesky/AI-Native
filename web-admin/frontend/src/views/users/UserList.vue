<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>用户管理</h3>
      <div class="toolbar-right">
        <el-button v-if="canViewRoles" @click="$router.push('/roles')">角色管理</el-button>
        <el-button v-if="canCreateUser" type="primary" @click="openCreateDialog">新增用户</el-button>
        <el-button @click="fetchUsers">刷新</el-button>
      </div>
    </div>

    <el-table :data="users" stripe>
      <el-table-column prop="username" label="账号" min-width="160" />
      <el-table-column prop="role" label="角色" width="120">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : 'info'">
            {{ row.role_name || row.role }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="220">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="canUpdateUserPassword"
            text
            type="primary"
            @click="openPasswordDialog(row)"
          >
            重置密码
          </el-button>
          <el-button v-if="canDeleteUser" text type="danger" @click="deleteUser(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!users.length && !loading" description="暂无用户" />

    <el-dialog v-model="showCreateDialog" title="新增用户" width="520px">
      <el-form :model="createForm" :rules="createRules" ref="createFormRef" label-width="90px">
        <el-form-item label="账号" prop="username">
          <el-input v-model="createForm.username" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option
              v-for="item in roleOptions"
              :key="item.id"
              :label="`${item.name} (${item.id})`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createUser">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showPasswordDialog" title="重置密码" width="520px">
      <el-form :model="passwordForm" :rules="passwordRules" ref="passwordFormRef" label-width="90px">
        <el-form-item label="账号">
          <el-input :model-value="passwordForm.username" disabled />
        </el-form-item>
        <el-form-item label="新密码" prop="password">
          <el-input
            v-model="passwordForm.password"
            type="password"
            show-password
            placeholder="至少 6 位"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPasswordDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="updatePassword">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'
import { hasPermission } from '@/utils/permissions.js'

const loading = ref(false)
const saving = ref(false)
const users = ref([])
const roleOptions = ref([])
const showCreateDialog = ref(false)
const showPasswordDialog = ref(false)
const createFormRef = ref(null)
const passwordFormRef = ref(null)

const createForm = reactive({
  username: '',
  role: 'user',
  password: '',
})

const passwordForm = reactive({
  username: '',
  password: '',
})

const createRules = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$/,
      message: '账号仅支持字母数字_.-，长度 2-64',
      trigger: 'blur',
    },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

const passwordRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

const canCreateUser = computed(() => hasPermission('button.users.create'))
const canUpdateUserPassword = computed(() => hasPermission('button.users.update_password'))
const canDeleteUser = computed(() => hasPermission('button.users.delete'))
const canViewRoles = computed(() => hasPermission('menu.roles'))

function resetCreateForm() {
  createForm.username = ''
  createForm.role = roleOptions.value[0]?.id || 'user'
  createForm.password = ''
}

function openCreateDialog() {
  if (!roleOptions.value.length) {
    ElMessage.warning('暂无可用角色，请先到角色管理创建角色')
    return
  }
  resetCreateForm()
  showCreateDialog.value = true
}

function openPasswordDialog(row) {
  passwordForm.username = String(row.username || '')
  passwordForm.password = ''
  showPasswordDialog.value = true
}

async function fetchUsers() {
  loading.value = true
  try {
    const data = await api.get('/users')
    users.value = data.users || []
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '加载用户失败')
    users.value = []
  } finally {
    loading.value = false
  }
}

async function fetchRoles() {
  try {
    const data = await api.get('/users/role-options')
    roleOptions.value = data.roles || []
    if (!createForm.role && roleOptions.value.length) {
      createForm.role = roleOptions.value[0].id
    }
  } catch (err) {
    roleOptions.value = []
    ElMessage.error(err?.detail || err?.message || '加载角色失败')
  }
}

async function createUser() {
  await createFormRef.value.validate()
  saving.value = true
  try {
    await api.post('/users', {
      username: createForm.username,
      role: createForm.role,
      password: createForm.password,
    })
    ElMessage.success('用户创建成功')
    showCreateDialog.value = false
    await fetchUsers()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '创建用户失败')
  } finally {
    saving.value = false
  }
}

async function updatePassword() {
  await passwordFormRef.value.validate()
  saving.value = true
  try {
    await api.put(`/users/${encodeURIComponent(passwordForm.username)}/password`, {
      password: passwordForm.password,
    })
    ElMessage.success('密码更新成功')
    showPasswordDialog.value = false
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '更新密码失败')
  } finally {
    saving.value = false
  }
}

async function deleteUser(row) {
  await ElMessageBox.confirm(`确定删除用户 ${row.username}？`, '确认', { type: 'warning' })
  try {
    await api.delete(`/users/${encodeURIComponent(row.username)}`)
    ElMessage.success('用户已删除')
    await fetchUsers()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '删除用户失败')
  }
}

onMounted(fetchUsers)
onMounted(fetchRoles)
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
</style>
