<template>
  <div v-loading="loading" class="settings-page">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__eyebrow">Access Control</div>
        <h1 class="settings-hero__title">用户管理</h1>
        <p class="settings-hero__summary">
          管理系统账号、角色归属和密码更新，列表默认按最新创建排序。
        </p>
        <div class="settings-hero__meta">
          <span>总账号 {{ users.length }}</span>
          <span>当前筛选 {{ filteredUsers.length }}</span>
        </div>
      </div>

      <div class="settings-hero__actions">
        <el-button v-if="canViewRoles" plain @click="$router.push('/roles')">角色管理</el-button>
        <el-button @click="fetchUsers">刷新</el-button>
        <el-button v-if="canCreateUser" type="primary" @click="openCreateDialog">新增用户</el-button>
      </div>
    </section>

    <section class="filter-panel">
      <div class="filter-panel__grid">
        <el-input
          v-model="filters.query"
          clearable
          placeholder="搜索账号或创建人"
        />
        <el-select v-model="filters.role" clearable placeholder="筛选角色">
          <el-option label="全部角色" value="" />
          <el-option
            v-for="item in roleOptions"
            :key="item.id"
            :label="`${item.name} (${item.id})`"
            :value="item.id"
          />
        </el-select>
        <el-select v-model="filters.sort" placeholder="排序方式">
          <el-option label="最新创建" value="created_desc" />
          <el-option label="最早创建" value="created_asc" />
          <el-option label="账号 A-Z" value="username_asc" />
        </el-select>
        <el-select v-model="pageSize" placeholder="每页条数">
          <el-option :value="10" label="10 条/页" />
          <el-option :value="20" label="20 条/页" />
          <el-option :value="50" label="50 条/页" />
        </el-select>
      </div>
    </section>

    <section class="table-panel">
      <div class="table-panel__head">
        <div>
          <div class="table-panel__eyebrow">Account List</div>
          <div class="table-panel__title">账号清单</div>
        </div>
        <div class="table-panel__meta">
          共 {{ filteredUsers.length }} 条
        </div>
      </div>

      <el-table :data="pagedUsers" stripe>
        <el-table-column prop="username" label="账号" min-width="180" />
        <el-table-column prop="role" label="角色" width="140">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'">
              {{ row.role_name || row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建人" width="160">
          <template #default="{ row }">{{ row.created_by || '-' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="220">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at, { withSeconds: true }) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="canEditRow(row)"
              text
              type="primary"
              @click="openEditDialog(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="canResetPasswordRow(row)"
              text
              type="primary"
              @click="openPasswordDialog(row)"
            >
              重置密码
            </el-button>
            <el-button v-if="canDeleteUser" text type="danger" @click="deleteUser(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="filteredUsers.length" class="table-panel__pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, sizes"
          :total="filteredUsers.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>

      <el-empty v-if="!filteredUsers.length && !loading" description="暂无用户" />
    </section>

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
          <el-input
            v-model="createForm.password"
            type="password"
            show-password
            placeholder="至少 6 位"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createUser">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑账户" width="520px">
      <el-form :model="editForm" :rules="editRules" ref="editFormRef" label-width="90px">
        <el-form-item label="账号" prop="username">
          <el-input v-model="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="editForm.role" :disabled="isEditingCurrentUser" style="width: 100%">
            <el-option
              v-for="item in roleOptions"
              :key="item.id"
              :label="`${item.name} (${item.id})`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <div v-if="isEditingCurrentUser" class="dialog-inline-hint">
          当前登录账号只允许修改自己的密码，角色仍需由超级管理员维护。
        </div>
        <el-form-item label="新密码" prop="password">
          <el-input
            v-model="editForm.password"
            type="password"
            show-password
            placeholder="留空表示不修改"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="updateUser">保存</el-button>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { authStateVersion, getStoredAuthProfile } from '@/utils/auth-storage.js'
import { formatDateTime, parseDateTime } from '@/utils/date.js'
import { hasPermission } from '@/utils/permissions.js'

const USERNAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$/

const loading = ref(false)
const saving = ref(false)
const users = ref([])
const roleOptions = ref([])
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showPasswordDialog = ref(false)
const createFormRef = ref(null)
const editFormRef = ref(null)
const passwordFormRef = ref(null)
const currentPage = ref(1)
const pageSize = ref(10)

const filters = reactive({
  query: '',
  role: '',
  sort: 'created_desc',
})

const createForm = reactive({
  username: '',
  role: 'user',
  password: '',
})

const editForm = reactive({
  username: '',
  role: 'user',
  password: '',
})

const passwordForm = reactive({
  username: '',
  password: '',
})

const validateOptionalPassword = (_rule, value, callback) => {
  if (!String(value || '')) {
    callback()
    return
  }
  if (String(value).length < 6) {
    callback(new Error('密码至少 6 位'))
    return
  }
  callback()
}

const createRules = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    {
      pattern: USERNAME_PATTERN,
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

const editRules = {
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  password: [{ validator: validateOptionalPassword, trigger: 'blur' }],
}

const passwordRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

const currentUsername = computed(() => {
  authStateVersion.value
  return String(getStoredAuthProfile().username || '').trim()
})

const canCreateUser = computed(() => hasPermission('button.users.create'))
const canManageAnyUser = computed(() => hasPermission('button.users.update'))
const canManageAnyUserPassword = computed(() => hasPermission('button.users.update_password'))
const canDeleteUser = computed(() => hasPermission('button.users.delete'))
const canViewRoles = computed(() => hasPermission('menu.roles'))
const isEditingCurrentUser = computed(() => editForm.username === currentUsername.value)

function isCurrentUserRow(row) {
  return String(row?.username || '') === currentUsername.value
}

function canEditRow(row) {
  return canManageAnyUser.value || isCurrentUserRow(row)
}

function canResetPasswordRow(row) {
  return canManageAnyUserPassword.value || isCurrentUserRow(row)
}

function normalizeTimestamp(value) {
  return parseDateTime(value)?.getTime() || 0
}

const filteredUsers = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  const role = String(filters.role || '').trim()
  const list = (users.value || []).filter((item) => {
    const matchesKeyword =
      !keyword ||
      String(item?.username || '').toLowerCase().includes(keyword) ||
      String(item?.created_by || '').toLowerCase().includes(keyword)
    const matchesRole = !role || String(item?.role || '').trim() === role
    return matchesKeyword && matchesRole
  })
  return list.sort((left, right) => {
    if (filters.sort === 'created_asc') {
      return normalizeTimestamp(left?.created_at) - normalizeTimestamp(right?.created_at)
    }
    if (filters.sort === 'username_asc') {
      return String(left?.username || '').localeCompare(String(right?.username || ''), 'zh-CN')
    }
    return normalizeTimestamp(right?.created_at) - normalizeTimestamp(left?.created_at)
  })
})

const pagedUsers = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredUsers.value.slice(start, start + pageSize.value)
})

watch(
  () => [filters.query, filters.role, filters.sort, pageSize.value],
  () => {
    currentPage.value = 1
  },
)

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

function openEditDialog(row) {
  editForm.username = String(row?.username || '')
  editForm.role = String(row?.role || roleOptions.value[0]?.id || 'user')
  editForm.password = ''
  showEditDialog.value = true
}

function openPasswordDialog(row) {
  passwordForm.username = String(row?.username || '')
  passwordForm.password = ''
  showPasswordDialog.value = true
}

async function fetchUsers() {
  loading.value = true
  try {
    const data = await api.get('/users')
    users.value = Array.isArray(data?.users) ? data.users : []
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
    roleOptions.value = Array.isArray(data?.roles) ? data.roles : []
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

async function updateUser() {
  await editFormRef.value.validate()
  saving.value = true
  try {
    await api.put(`/users/${encodeURIComponent(editForm.username)}`, {
      role: editForm.role,
      password: editForm.password,
    })
    ElMessage.success('账户更新成功')
    showEditDialog.value = false
    await fetchUsers()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '更新账户失败')
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
.dialog-inline-hint {
  margin: -6px 0 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #7c8aa0;
}

.settings-page {
  display: grid;
  gap: 18px;
}

.settings-hero,
.filter-panel,
.table-panel {
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.74);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(18px);
}

.settings-hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 26px;
}

.settings-hero__copy {
  display: grid;
  gap: 10px;
}

.settings-hero__eyebrow,
.table-panel__eyebrow {
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #64748b;
}

.settings-hero__title,
.table-panel__title {
  margin: 0;
  font-size: 28px;
  color: #0f172a;
}

.settings-hero__summary {
  margin: 0;
  max-width: 560px;
  color: #475569;
  line-height: 1.7;
}

.settings-hero__meta,
.table-panel__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #64748b;
  font-size: 13px;
}

.settings-hero__actions {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-panel {
  padding: 18px 20px;
}

.filter-panel__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.table-panel {
  padding: 20px;
}

.table-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.table-panel__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}

@media (max-width: 960px) {
  .settings-hero,
  .table-panel__head {
    flex-direction: column;
    align-items: flex-start;
  }

  .settings-hero__actions {
    justify-content: flex-start;
  }

  .filter-panel__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .filter-panel__grid {
    grid-template-columns: 1fr;
  }
}
</style>
