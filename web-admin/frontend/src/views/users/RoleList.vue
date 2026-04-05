<template>
  <div v-loading="loading" class="settings-page">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__eyebrow">Role Registry</div>
        <h1 class="settings-hero__title">角色管理</h1>
        <p class="settings-hero__summary">
          统一维护角色权限和使用边界，列表默认按最新创建优先展示。
        </p>
        <div class="settings-hero__meta">
          <span>总角色 {{ roles.length }}</span>
          <span>当前筛选 {{ filteredRoles.length }}</span>
        </div>
      </div>

      <div class="settings-hero__actions">
        <el-button @click="refresh">刷新</el-button>
        <el-button v-if="canCreate" type="primary" @click="openCreateDialog">新增角色</el-button>
      </div>
    </section>

    <section class="filter-panel">
      <div class="filter-panel__grid">
        <el-input
          v-model="filters.query"
          clearable
          placeholder="搜索角色 ID、名称或创建人"
        />
        <el-select v-model="filters.builtIn" placeholder="角色类型">
          <el-option label="全部角色" value="all" />
          <el-option label="内置角色" value="built_in" />
          <el-option label="自定义角色" value="custom" />
        </el-select>
        <el-select v-model="filters.sort" placeholder="排序方式">
          <el-option label="最新创建" value="created_desc" />
          <el-option label="最早创建" value="created_asc" />
          <el-option label="名称 A-Z" value="name_asc" />
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
          <div class="table-panel__eyebrow">Permission Matrix</div>
          <div class="table-panel__title">角色列表</div>
        </div>
        <div class="table-panel__meta">共 {{ filteredRoles.length }} 条</div>
      </div>

      <el-table :data="pagedRoles" stripe>
        <el-table-column prop="id" label="角色 ID" width="140" />
        <el-table-column prop="name" label="角色名称" min-width="160" />
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
        <el-table-column label="创建人" width="140">
          <template #default="{ row }">{{ row.created_by || (row.built_in ? 'system' : '-') }}</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="220">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at, { withSeconds: true }) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="220">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at, { withSeconds: true }) }}
          </template>
        </el-table-column>
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

      <div v-if="filteredRoles.length" class="table-panel__pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, jumper, sizes"
          :total="filteredRoles.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>

      <el-empty v-if="!loading && !filteredRoles.length" description="暂无角色" />
    </section>

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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime, parseDateTime } from '@/utils/date.js'
import { getFallbackPath, hasPermission, setPermissionArray } from '@/utils/permissions.js'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const roles = ref([])
const catalogGroups = ref([])
const showDialog = ref(false)
const formRef = ref(null)
const formMode = ref('create')
const currentPage = ref(1)
const pageSize = ref(10)

const filters = reactive({
  query: '',
  builtIn: 'all',
  sort: 'created_desc',
})

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
    form.permissions = value ? ['*'] : []
  },
})

const dialogTitle = computed(() => (formMode.value === 'edit' ? '编辑角色' : '新增角色'))
const canCreate = computed(() => hasPermission('button.roles.create'))
const canUpdate = computed(() => hasPermission('button.roles.update'))
const canDelete = computed(() => hasPermission('button.roles.delete'))

function normalizeTimestamp(value) {
  return parseDateTime(value)?.getTime() || 0
}

const filteredRoles = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  const list = (roles.value || []).filter((item) => {
    const matchesKeyword =
      !keyword ||
      String(item?.id || '').toLowerCase().includes(keyword) ||
      String(item?.name || '').toLowerCase().includes(keyword) ||
      String(item?.created_by || '').toLowerCase().includes(keyword)
    if (filters.builtIn === 'built_in') return matchesKeyword && Boolean(item?.built_in)
    if (filters.builtIn === 'custom') return matchesKeyword && !item?.built_in
    return matchesKeyword
  })
  return list.sort((left, right) => {
    if (filters.sort === 'created_asc') {
      return normalizeTimestamp(left?.created_at) - normalizeTimestamp(right?.created_at)
    }
    if (filters.sort === 'name_asc') {
      return String(left?.name || '').localeCompare(String(right?.name || ''), 'zh-CN')
    }
    return normalizeTimestamp(right?.created_at) - normalizeTimestamp(left?.created_at)
  })
})

const pagedRoles = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredRoles.value.slice(start, start + pageSize.value)
})

watch(
  () => [filters.query, filters.builtIn, filters.sort, pageSize.value],
  () => {
    currentPage.value = 1
  },
)

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
  roles.value = Array.isArray(data?.roles) ? data.roles : []
}

async function fetchCatalog() {
  const data = await api.get('/roles/catalog')
  catalogGroups.value = Array.isArray(data?.groups) ? data.groups : []
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

async function refreshCurrentSessionPermissions() {
  const data = await api.get('/auth/me')
  localStorage.setItem('username', data?.username || '')
  localStorage.setItem('role', data?.role || 'user')
  setPermissionArray(data?.permissions || [])
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
    await refreshCurrentSessionPermissions()
    ElMessage.success('角色保存成功')
    showDialog.value = false
    if (!hasPermission('menu.roles')) {
      await router.replace(getFallbackPath())
      return
    }
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

.permission-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(240px, 1fr));
  gap: 8px 12px;
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
  .filter-panel__grid,
  .permission-grid {
    grid-template-columns: 1fr;
  }
}
</style>
