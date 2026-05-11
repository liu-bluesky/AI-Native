<template>
  <div v-loading="loading" class="settings-page">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__eyebrow">Department Scope</div>
        <h1 class="settings-hero__title">部门管理</h1>
        <p class="settings-hero__summary">
          维护组织层级、部门负责人和用户归属，用于控制上级可见下级、同级默认隔离的数据范围。
        </p>
        <div class="settings-hero__meta">
          <span>部门 {{ departments.length }}</span>
          <span>启用 {{ enabledCount }}</span>
          <span>成员关系 {{ membershipCount }}</span>
        </div>
      </div>
      <div class="settings-hero__actions">
        <el-button plain @click="$router.push('/users')">用户管理</el-button>
        <el-button @click="fetchAll">刷新</el-button>
        <el-button v-if="canCreateDepartment" type="primary" @click="openCreateDialog">
          新增部门
        </el-button>
      </div>
    </section>

    <section class="filter-panel">
      <div class="filter-panel__grid">
        <el-input v-model="filters.query" clearable placeholder="搜索部门、负责人或成员" />
        <el-select v-model="filters.enabled" clearable placeholder="启用状态">
          <el-option label="全部状态" value="" />
          <el-option label="启用" value="enabled" />
          <el-option label="停用" value="disabled" />
        </el-select>
        <el-select v-model="filters.manager" clearable placeholder="负责人">
          <el-option label="全部负责人" value="" />
          <el-option
            v-for="item in managerOptions"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
      </div>
    </section>

    <section class="table-panel">
      <div class="table-panel__head">
        <div>
          <div class="table-panel__eyebrow">Hierarchy</div>
          <div class="table-panel__title">部门结构</div>
        </div>
        <div class="table-panel__meta">当前 {{ filteredDepartments.length }} 条</div>
      </div>

      <el-table :data="filteredDepartments" row-key="id" stripe>
        <el-table-column label="部门" min-width="240">
          <template #default="{ row }">
            <div class="department-name" :style="{ paddingLeft: `${Number(row.depth || 0) * 18}px` }">
              <span class="department-name__title">{{ row.name }}</span>
              <el-tag v-if="!row.enabled" size="small" type="info">停用</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="160">
          <template #default="{ row }">{{ row.manager_username || '-' }}</template>
        </el-table-column>
        <el-table-column label="成员" min-width="240">
          <template #default="{ row }">
            <div class="member-tags">
              <el-tag
                v-for="username in row.usernames.slice(0, 4)"
                :key="username"
                size="small"
              >
                {{ username }}
              </el-tag>
              <span v-if="row.usernames.length > 4" class="muted-text">
                +{{ row.usernames.length - 4 }}
              </span>
              <span v-if="!row.usernames.length" class="muted-text">暂无成员</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="排序" width="90" prop="sort_order" />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="canUpdateDepartment"
              text
              type="primary"
              @click="openEditDialog(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="canAssignUsers"
              text
              type="primary"
              @click="openAssignDialog(row)"
            >
              分配用户
            </el-button>
            <el-button
              v-if="canDeleteDepartment"
              text
              type="danger"
              @click="deleteDepartment(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!filteredDepartments.length && !loading" description="暂无部门" />
    </section>

    <el-dialog v-model="showEditDialog" :title="editingId ? '编辑部门' : '新增部门'" width="560px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="96px">
        <el-form-item label="部门名称" prop="name">
          <el-input v-model="editForm.name" placeholder="请输入部门名称" />
        </el-form-item>
        <el-form-item label="上级部门">
          <el-select v-model="editForm.parent_id" clearable filterable style="width: 100%">
            <el-option label="无上级部门" value="" />
            <el-option
              v-for="item in parentOptions"
              :key="item.id"
              :label="`${indentLabel(item.depth)}${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="editForm.manager_username" clearable filterable style="width: 100%">
            <el-option
              v-for="item in users"
              :key="item.username"
              :label="item.username"
              :value="item.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="editForm.description"
            type="textarea"
            :rows="3"
            placeholder="可选，说明部门职责"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="editForm.sort_order" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editForm.enabled" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDepartment">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showAssignDialog" title="分配用户" width="560px">
      <div class="assign-title">{{ assignTarget?.name || '' }}</div>
      <el-select
        v-model="assignUsernames"
        multiple
        filterable
        collapse-tags
        collapse-tags-tooltip
        style="width: 100%"
        placeholder="选择部门成员"
      >
        <el-option
          v-for="item in users"
          :key="item.username"
          :label="`${item.username}${item.role_name ? ` · ${item.role_name}` : ''}`"
          :value="item.username"
        />
      </el-select>
      <template #footer>
        <el-button @click="showAssignDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDepartmentUsers">保存</el-button>
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
const departments = ref([])
const users = ref([])
const showEditDialog = ref(false)
const showAssignDialog = ref(false)
const editFormRef = ref(null)
const editingId = ref('')
const assignTarget = ref(null)
const assignUsernames = ref([])

const filters = reactive({
  query: '',
  enabled: '',
  manager: '',
})

const editForm = reactive({
  name: '',
  parent_id: '',
  manager_username: '',
  description: '',
  enabled: true,
  sort_order: 100,
})

const editRules = {
  name: [{ required: true, message: '请输入部门名称', trigger: 'blur' }],
}

const canCreateDepartment = computed(() => hasPermission('button.departments.create'))
const canUpdateDepartment = computed(() => hasPermission('button.departments.update'))
const canDeleteDepartment = computed(() => hasPermission('button.departments.delete'))
const canAssignUsers = computed(() => hasPermission('button.departments.assign_users'))
const enabledCount = computed(() => departments.value.filter((item) => item.enabled).length)
const membershipCount = computed(() =>
  departments.value.reduce((sum, item) => sum + Number(item.usernames?.length || 0), 0),
)
const managerOptions = computed(() => {
  const managers = departments.value
    .map((item) => String(item.manager_username || '').trim())
    .filter(Boolean)
  return [...new Set(managers)].sort()
})
const parentOptions = computed(() =>
  departments.value.filter((item) => item.id !== editingId.value && item.enabled),
)
const filteredDepartments = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  return departments.value.filter((item) => {
    const matchesEnabled =
      !filters.enabled ||
      (filters.enabled === 'enabled' && item.enabled) ||
      (filters.enabled === 'disabled' && !item.enabled)
    const matchesManager =
      !filters.manager || String(item.manager_username || '') === filters.manager
    const haystack = [
      item.name,
      item.manager_username,
      item.description,
      ...(Array.isArray(item.usernames) ? item.usernames : []),
    ]
      .join(' ')
      .toLowerCase()
    return matchesEnabled && matchesManager && (!keyword || haystack.includes(keyword))
  })
})

function indentLabel(depth) {
  return '　'.repeat(Math.max(0, Number(depth || 0)))
}

function resetEditForm() {
  editForm.name = ''
  editForm.parent_id = ''
  editForm.manager_username = ''
  editForm.description = ''
  editForm.enabled = true
  editForm.sort_order = 100
}

function openCreateDialog() {
  editingId.value = ''
  resetEditForm()
  showEditDialog.value = true
}

function openEditDialog(row) {
  editingId.value = row.id
  editForm.name = row.name || ''
  editForm.parent_id = row.parent_id || ''
  editForm.manager_username = row.manager_username || ''
  editForm.description = row.description || ''
  editForm.enabled = !!row.enabled
  editForm.sort_order = Number(row.sort_order || 100)
  showEditDialog.value = true
}

function openAssignDialog(row) {
  assignTarget.value = row
  assignUsernames.value = Array.isArray(row.usernames) ? row.usernames.slice() : []
  showAssignDialog.value = true
}

async function fetchDepartments() {
  const data = await api.get('/departments')
  departments.value = Array.isArray(data?.departments) ? data.departments : []
}

async function fetchUsers() {
  const data = await api.get('/departments/user-options')
  users.value = Array.isArray(data?.users) ? data.users : []
}

async function fetchAll() {
  loading.value = true
  try {
    await Promise.all([fetchDepartments(), fetchUsers()])
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '加载部门失败')
  } finally {
    loading.value = false
  }
}

async function saveDepartment() {
  await editFormRef.value.validate()
  saving.value = true
  try {
    const payload = {
      name: editForm.name,
      parent_id: editForm.parent_id,
      manager_username: editForm.manager_username,
      description: editForm.description,
      enabled: editForm.enabled,
      sort_order: editForm.sort_order,
    }
    if (editingId.value) {
      await api.put(`/departments/${encodeURIComponent(editingId.value)}`, payload)
      ElMessage.success('部门已更新')
    } else {
      await api.post('/departments', payload)
      ElMessage.success('部门已创建')
    }
    showEditDialog.value = false
    await fetchDepartments()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '保存部门失败')
  } finally {
    saving.value = false
  }
}

async function saveDepartmentUsers() {
  if (!assignTarget.value?.id) return
  saving.value = true
  try {
    await api.put(`/departments/${encodeURIComponent(assignTarget.value.id)}/users`, {
      usernames: assignUsernames.value,
    })
    ElMessage.success('部门成员已更新')
    showAssignDialog.value = false
    await fetchDepartments()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '分配用户失败')
  } finally {
    saving.value = false
  }
}

async function deleteDepartment(row) {
  try {
    await ElMessageBox.confirm(`确定删除部门 ${row.name}？`, '删除部门', {
      type: 'warning',
      confirmButtonText: '删除',
    })
  } catch {
    return
  }
  try {
    await api.delete(`/departments/${encodeURIComponent(row.id)}`)
    ElMessage.success('部门已删除')
    await fetchDepartments()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '删除部门失败')
  }
}

onMounted(fetchAll)
</script>

<style scoped>
.settings-page {
  display: grid;
  gap: 18px;
}

.settings-hero,
.filter-panel,
.table-panel {
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.08);
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
  letter-spacing: 0.12em;
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
  max-width: 640px;
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
  grid-template-columns: minmax(240px, 1fr) 180px 220px;
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

.department-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
}

.department-name__title {
  font-weight: 650;
  color: #0f172a;
}

.member-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.muted-text {
  color: #94a3b8;
  font-size: 13px;
}

.assign-title {
  margin-bottom: 12px;
  font-weight: 650;
  color: #0f172a;
}

@media (max-width: 860px) {
  .settings-hero {
    display: grid;
  }

  .filter-panel__grid {
    grid-template-columns: 1fr;
  }
}
</style>
