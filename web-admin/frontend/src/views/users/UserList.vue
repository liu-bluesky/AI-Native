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
        <el-button v-if="canViewDepartments" plain @click="$router.push('/departments')">部门管理</el-button>
        <el-button @click="fetchUsers">刷新</el-button>
        <el-button plain :disabled="!filteredUsers.length" @click="exportUsers">导出</el-button>
        <el-button v-if="canCreateUser" plain @click="openInviteDialog">邀请注册</el-button>
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
        <el-select v-model="filters.departmentId" clearable placeholder="筛选部门">
          <el-option label="全部部门" value="" />
          <el-option
            v-for="item in departmentOptions"
            :key="item.id"
            :label="`${indentLabel(item.depth)}${item.name}`"
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
        <el-table-column prop="role" label="角色" min-width="220">
          <template #default="{ row }">
            <div class="role-tags">
              <el-tag
                v-for="item in userRoleItems(row)"
                :key="item.id"
                :type="item.id === 'admin' ? 'danger' : 'info'"
              >
                {{ item.name || item.id }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="创建人" width="160">
          <template #default="{ row }">{{ row.created_by || '-' }}</template>
        </el-table-column>
        <el-table-column label="部门" min-width="180">
          <template #default="{ row }">
            <div class="department-tags">
              <el-tag
                v-for="item in row.departments || []"
                :key="item.id"
                size="small"
                :type="item.is_primary ? 'success' : 'info'"
              >
                {{ item.name || item.id }}
              </el-tag>
              <span v-if="!(row.departments || []).length" class="muted-text">未分配</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="220">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at, { withSeconds: true }) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="260" fixed="right" class-name="table-action-column">
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
          layout="total, prev, pager, next, jumper, sizes"
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
        <el-form-item label="角色" prop="role_ids">
          <el-select
            v-model="createForm.role_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            style="width: 100%"
            placeholder="选择一个或多个角色"
          >
            <el-option
              v-for="item in roleOptions"
              :key="item.id"
              :label="`${item.name} (${item.id})`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="canAssignDepartments" label="部门">
          <el-select
            v-model="createForm.department_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            style="width: 100%"
            placeholder="选择用户部门"
          >
            <el-option
              v-for="item in departmentOptions"
              :key="item.id"
              :label="`${indentLabel(item.depth)}${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="canAssignDepartments && createForm.department_ids.length" label="主部门">
          <el-select v-model="createForm.primary_department_id" style="width: 100%">
            <el-option
              v-for="departmentId in createForm.department_ids"
              :key="departmentId"
              :label="departmentName(departmentId)"
              :value="departmentId"
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
        <el-form-item label="角色" prop="role_ids">
          <el-select
            v-model="editForm.role_ids"
            :disabled="isEditingCurrentUser"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            style="width: 100%"
            placeholder="选择一个或多个角色"
          >
            <el-option
              v-for="item in roleOptions"
              :key="item.id"
              :label="`${item.name} (${item.id})`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="canAssignDepartments" label="部门">
          <el-select
            v-model="editForm.department_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            style="width: 100%"
            placeholder="选择用户部门"
          >
            <el-option
              v-for="item in departmentOptions"
              :key="item.id"
              :label="`${indentLabel(item.depth)}${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="canAssignDepartments && editForm.department_ids.length" label="主部门">
          <el-select v-model="editForm.primary_department_id" style="width: 100%">
            <el-option
              v-for="departmentId in editForm.department_ids"
              :key="departmentId"
              :label="departmentName(departmentId)"
              :value="departmentId"
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

    <el-dialog v-model="showInviteDialog" title="邀请注册" width="560px">
      <el-form :model="inviteForm" label-width="90px">
        <el-form-item v-if="canAssignDepartments" label="部门">
          <el-select
            v-model="inviteForm.department_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            style="width: 100%"
            placeholder="选择注册后加入的部门"
          >
            <el-option
              v-for="item in departmentOptions"
              :key="item.id"
              :label="`${indentLabel(item.depth)}${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="canAssignDepartments && inviteForm.department_ids.length" label="主部门">
          <el-select v-model="inviteForm.primary_department_id" style="width: 100%">
            <el-option
              v-for="departmentId in inviteForm.department_ids"
              :key="departmentId"
              :label="departmentName(departmentId)"
              :value="departmentId"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="有效期">
          <el-input-number
            v-model="inviteForm.expires_in_hours"
            :min="1"
            :max="720"
            :step="24"
            style="width: 180px"
          />
          <span class="dialog-inline-suffix">小时</span>
        </el-form-item>
        <el-form-item v-if="inviteResult.link" label="邀请链接">
          <div class="invite-link-field">
            <el-input v-model="inviteResult.link" readonly />
            <el-button type="primary" plain @click="copyInviteLink">复制</el-button>
          </div>
        </el-form-item>
        <div v-if="inviteResult.expires_at" class="dialog-inline-hint">
          链接有效至 {{ formatDateTime(inviteResult.expires_at, { withSeconds: true }) }}。
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showInviteDialog = false">关闭</el-button>
        <el-button type="primary" :loading="inviteGenerating" @click="generateInviteLink">
          生成链接
        </el-button>
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
const departmentOptions = ref([])
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showPasswordDialog = ref(false)
const showInviteDialog = ref(false)
const createFormRef = ref(null)
const editFormRef = ref(null)
const passwordFormRef = ref(null)
const currentPage = ref(1)
const pageSize = ref(10)
const inviteGenerating = ref(false)

const filters = reactive({
  query: '',
  role: '',
  departmentId: '',
  sort: 'created_desc',
})

const createForm = reactive({
  username: '',
  role_ids: [],
  password: '',
  department_ids: [],
  primary_department_id: '',
})

const editForm = reactive({
  username: '',
  role_ids: [],
  password: '',
  department_ids: [],
  primary_department_id: '',
})

const passwordForm = reactive({
  username: '',
  password: '',
})

const inviteForm = reactive({
  department_ids: [],
  primary_department_id: '',
  expires_in_hours: 168,
})

const inviteResult = reactive({
  token: '',
  link: '',
  expires_at: '',
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
  role_ids: [{ type: 'array', required: true, min: 1, message: '请选择角色', trigger: 'change' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

const editRules = {
  role_ids: [{ type: 'array', required: true, min: 1, message: '请选择角色', trigger: 'change' }],
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
const canViewDepartments = computed(() => hasPermission('menu.departments'))
const canAssignDepartments = computed(() => hasPermission('button.departments.assign_users'))
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

function escapeCsvCell(value) {
  const text = String(value ?? '')
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

function buildUserExportFilename() {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
  return `users-${timestamp}.csv`
}

function buildUserExportCsv(list) {
  const headers = ['账号', '角色ID', '角色名称', '部门', '创建人', '创建时间']
  const rows = list.map((item) => [
    item?.username || '',
    userRoleItems(item).map((role) => role.id).join(';'),
    userRoleItems(item).map((role) => role.name || role.id).join(';'),
    (item?.departments || []).map((department) => department.name || department.id).join(';'),
    item?.created_by || '',
    formatDateTime(item?.created_at, { withSeconds: true }) || '',
  ])
  return [headers, ...rows]
    .map((row) => row.map((cell) => escapeCsvCell(cell)).join(','))
    .join('\n')
}

function downloadTextFile(content, filename, mimeType = 'text/plain;charset=utf-8;') {
  const blob = new Blob([`\uFEFF${content}`], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

const filteredUsers = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  const role = String(filters.role || '').trim()
  const departmentId = String(filters.departmentId || '').trim()
  const list = (users.value || []).filter((item) => {
    const matchesKeyword =
      !keyword ||
      String(item?.username || '').toLowerCase().includes(keyword) ||
      String(item?.created_by || '').toLowerCase().includes(keyword) ||
      (item?.departments || []).some((department) =>
        String(department?.name || department?.id || '').toLowerCase().includes(keyword),
      )
    const itemRoleIds = userRoleItems(item).map((roleItem) => String(roleItem.id || '').trim())
    const matchesRole = !role || itemRoleIds.includes(role)
    const matchesDepartment =
      !departmentId ||
      (item?.department_ids || []).some((itemDepartmentId) => itemDepartmentId === departmentId)
    return matchesKeyword && matchesRole && matchesDepartment
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
  () => [filters.query, filters.role, filters.departmentId, filters.sort, pageSize.value],
  () => {
    currentPage.value = 1
  },
)

watch(
  () => inviteForm.department_ids.slice(),
  () => {
    if (!inviteForm.department_ids.includes(inviteForm.primary_department_id)) {
      inviteForm.primary_department_id = inviteForm.department_ids[0] || ''
    }
    inviteResult.token = ''
    inviteResult.link = ''
    inviteResult.expires_at = ''
  },
)

watch(
  () => [inviteForm.primary_department_id, inviteForm.expires_in_hours],
  () => {
    inviteResult.token = ''
    inviteResult.link = ''
    inviteResult.expires_at = ''
  },
)

function resetCreateForm() {
  createForm.username = ''
  createForm.role_ids = [roleOptions.value[0]?.id || 'user'].filter(Boolean)
  createForm.password = ''
  createForm.department_ids = []
  createForm.primary_department_id = ''
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
  editForm.role_ids = normalizeRoleIds(row?.role_ids, row?.role || roleOptions.value[0]?.id || 'user')
  editForm.password = ''
  editForm.department_ids = Array.isArray(row?.department_ids) ? row.department_ids.slice() : []
  editForm.primary_department_id = String(row?.primary_department_id || editForm.department_ids[0] || '')
  showEditDialog.value = true
}

function openPasswordDialog(row) {
  passwordForm.username = String(row?.username || '')
  passwordForm.password = ''
  showPasswordDialog.value = true
}

function resetInviteForm() {
  inviteForm.department_ids = []
  inviteForm.primary_department_id = ''
  inviteForm.expires_in_hours = 168
  inviteResult.token = ''
  inviteResult.link = ''
  inviteResult.expires_at = ''
}

function openInviteDialog() {
  resetInviteForm()
  showInviteDialog.value = true
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

async function fetchDepartments() {
  if (!canViewDepartments.value) {
    departmentOptions.value = []
    return
  }
  try {
    const data = await api.get('/departments/options')
    departmentOptions.value = Array.isArray(data?.departments) ? data.departments : []
  } catch {
    departmentOptions.value = []
  }
}

async function fetchRoles() {
  try {
    const data = await api.get('/users/role-options')
    roleOptions.value = Array.isArray(data?.roles) ? data.roles : []
    if (!createForm.role_ids.length && roleOptions.value.length) {
      createForm.role_ids = [roleOptions.value[0].id]
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
    const payload = {
      username: createForm.username,
      role: createForm.role_ids[0] || 'user',
      role_ids: createForm.role_ids,
      password: createForm.password,
    }
    if (canAssignDepartments.value) {
      payload.department_ids = createForm.department_ids
      payload.primary_department_id = createForm.primary_department_id || createForm.department_ids[0] || ''
    }
    await api.post('/users', payload)
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
    const payload = {
      role: editForm.role_ids[0] || 'user',
      role_ids: editForm.role_ids,
      password: editForm.password,
    }
    if (canAssignDepartments.value) {
      payload.department_ids = editForm.department_ids
      payload.primary_department_id = editForm.primary_department_id || editForm.department_ids[0] || ''
    }
    await api.put(`/users/${encodeURIComponent(editForm.username)}`, payload)
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

function buildInviteRegisterUrl(token) {
  const baseUrl = `${window.location.origin}${window.location.pathname}`
  return `${baseUrl}#/register?invite=${encodeURIComponent(token)}`
}

async function generateInviteLink() {
  inviteGenerating.value = true
  try {
    const payload = {
      department_ids: canAssignDepartments.value ? inviteForm.department_ids : [],
      primary_department_id:
        canAssignDepartments.value
          ? inviteForm.primary_department_id || inviteForm.department_ids[0] || ''
          : '',
      expires_in_hours: inviteForm.expires_in_hours,
    }
    const data = await api.post('/auth/invitations', payload)
    inviteResult.token = String(data?.token || '')
    inviteResult.link = buildInviteRegisterUrl(inviteResult.token)
    inviteResult.expires_at = String(data?.expires_at || '')
    ElMessage.success('邀请链接已生成')
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '生成邀请链接失败')
  } finally {
    inviteGenerating.value = false
  }
}

async function copyInviteLink() {
  if (!inviteResult.link) {
    return
  }
  try {
    if (!navigator?.clipboard?.writeText) {
      throw new Error('clipboard_unavailable')
    }
    await navigator.clipboard.writeText(inviteResult.link)
    ElMessage.success('邀请链接已复制')
  } catch {
    ElMessage.warning('当前浏览器不支持自动复制，请手动复制链接')
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

function exportUsers() {
  if (!filteredUsers.value.length) {
    ElMessage.warning('暂无可导出的用户')
    return
  }
  try {
    const content = buildUserExportCsv(filteredUsers.value)
    downloadTextFile(content, buildUserExportFilename(), 'text/csv;charset=utf-8;')
    ElMessage.success(`已导出 ${filteredUsers.value.length} 条用户记录`)
  } catch (err) {
    ElMessage.error(err?.message || '导出用户失败')
  }
}

onMounted(fetchUsers)
onMounted(fetchRoles)
onMounted(fetchDepartments)

function indentLabel(depth) {
  return '　'.repeat(Math.max(0, Number(depth || 0)))
}

function departmentName(departmentId) {
  const item = departmentOptions.value.find((department) => department.id === departmentId)
  return item?.name || departmentId
}

function normalizeRoleIds(values, fallbackRole = 'user') {
  const normalized = []
  const seen = new Set()
  const rawValues = Array.isArray(values) ? values : []
  for (const item of [...rawValues, fallbackRole]) {
    const roleId = String(item || '').trim()
    if (!roleId || seen.has(roleId)) continue
    seen.add(roleId)
    normalized.push(roleId)
  }
  return normalized.length ? normalized : ['user']
}

function roleName(roleId) {
  const item = roleOptions.value.find((role) => role.id === roleId)
  return item?.name || roleId
}

function userRoleItems(row) {
  const roleIds = normalizeRoleIds(row?.role_ids, row?.role)
  return roleIds.map((roleId, index) => {
    const matchedRole = (row?.roles || []).find((item) => item.id === roleId)
    return {
      id: roleId,
      name:
        matchedRole?.name ||
        (Array.isArray(row?.role_names) ? row.role_names[index] : '') ||
        (roleId === row?.role ? row?.role_name : '') ||
        roleName(roleId),
    }
  })
}
</script>

<style scoped>
.dialog-inline-hint {
  margin: -6px 0 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #7c8aa0;
}

.dialog-inline-suffix {
  margin-left: 10px;
  color: #64748b;
  font-size: 13px;
}

.invite-link-field {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  width: 100%;
}

.department-tags,
.role-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.muted-text {
  color: #94a3b8;
  font-size: 13px;
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
  grid-template-columns: repeat(5, minmax(0, 1fr));
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
