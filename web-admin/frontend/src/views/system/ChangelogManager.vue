<template>
  <div v-loading="loading" class="settings-page">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__eyebrow">Release Registry</div>
        <h1 class="settings-hero__title">更新日志</h1>
        <p class="settings-hero__summary">
          独立维护官网更新日志条目。发布后会直接出现在 `/updates`。
        </p>
        <div class="settings-hero__meta">
          <span>总条目 {{ entries.length }}</span>
          <span>已发布 {{ publishedCount }}</span>
        </div>
      </div>

      <div class="settings-hero__actions">
        <el-button @click="refresh">刷新</el-button>
        <el-button v-if="canCreate" type="primary" @click="openCreateDialog">新增条目</el-button>
      </div>
    </section>

    <section class="filter-panel">
      <div class="filter-panel__grid">
        <el-input
          v-model="filters.query"
          clearable
          placeholder="搜索版本、标题或摘要"
        />
        <el-select v-model="filters.published" placeholder="发布状态">
          <el-option label="全部状态" value="all" />
          <el-option label="仅已发布" value="published" />
          <el-option label="仅草稿" value="draft" />
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
          <div class="table-panel__eyebrow">Release Items</div>
          <div class="table-panel__title">条目列表</div>
        </div>
        <div class="table-panel__meta">共 {{ filteredEntries.length }} 条</div>
      </div>

      <el-table :data="pagedEntries" stripe>
        <el-table-column label="版本" width="140">
          <template #default="{ row }">{{ row.version || '-' }}</template>
        </el-table-column>
        <el-table-column label="标题" min-width="220">
          <template #default="{ row }">{{ resolveDisplayTitle(row) }}</template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="220" show-overflow-tooltip />
        <el-table-column label="发布日期" width="140">
          <template #default="{ row }">{{ row.release_date || '-' }}</template>
        </el-table-column>
        <el-table-column label="发布状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.published ? 'success' : 'info'" size="small">
              {{ row.published ? '已发布' : '草稿' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="排序" width="90">
          <template #default="{ row }">{{ row.sort_order }}</template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canUpdate" text type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button v-if="canDelete" text type="danger" @click="deleteEntry(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="filteredEntries.length" class="table-panel__pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, sizes"
          :total="filteredEntries.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>

      <el-empty v-if="!loading && !filteredEntries.length" description="暂无更新日志条目" />
    </section>

    <el-dialog v-model="showDialog" :title="dialogTitle" width="820px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <div class="form-grid">
          <el-form-item label="版本号">
            <el-input v-model="form.version" placeholder="如：v1.2.0" />
          </el-form-item>
          <el-form-item label="发布日期">
            <el-date-picker
              v-model="form.release_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="排序">
            <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
          </el-form-item>
          <el-form-item label="公开发布">
            <el-switch v-model="form.published" />
          </el-form-item>
        </div>

        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="例如：发布桌面端安装包" />
        </el-form-item>

        <el-form-item label="摘要">
          <el-input
            v-model="form.summary"
            type="textarea"
            :rows="3"
            resize="vertical"
            placeholder="一句话概括这一版。可选。"
          />
        </el-form-item>

        <el-form-item label="变更内容">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="10"
            resize="vertical"
            placeholder="- 新增更新日志独立菜单
- 支持更新日志条目增删改查"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEntry">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'
import { hasPermission } from '@/utils/permissions.js'

const loading = ref(false)
const saving = ref(false)
const entries = ref([])
const showDialog = ref(false)
const formRef = ref(null)
const formMode = ref('create')
const editingId = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

const filters = reactive({
  query: '',
  published: 'all',
})

const form = reactive({
  version: '',
  title: '',
  summary: '',
  content: '',
  release_date: '',
  published: false,
  sort_order: 100,
})

const rules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
}

const canCreate = computed(() => hasPermission('button.changelog.create'))
const canUpdate = computed(() => hasPermission('button.changelog.update'))
const canDelete = computed(() => hasPermission('button.changelog.delete'))
const dialogTitle = computed(() => (formMode.value === 'edit' ? '编辑更新日志' : '新增更新日志'))

const publishedCount = computed(() => entries.value.filter((item) => item?.published).length)

const filteredEntries = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  return (entries.value || []).filter((item) => {
    const matchesKeyword =
      !keyword ||
      String(item?.version || '').toLowerCase().includes(keyword) ||
      String(item?.title || '').toLowerCase().includes(keyword) ||
      String(item?.summary || '').toLowerCase().includes(keyword)
    if (filters.published === 'published') {
      return matchesKeyword && Boolean(item?.published)
    }
    if (filters.published === 'draft') {
      return matchesKeyword && !item?.published
    }
    return matchesKeyword
  })
})

const pagedEntries = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredEntries.value.slice(start, start + pageSize.value)
})

watch(
  () => [filters.query, filters.published, pageSize.value],
  () => {
    currentPage.value = 1
  },
)

function resetForm() {
  editingId.value = ''
  form.version = ''
  form.title = ''
  form.summary = ''
  form.content = ''
  form.release_date = ''
  form.published = false
  form.sort_order = 100
}

function resolveDisplayTitle(row) {
  const title = String(row?.title || '').trim()
  if (title) return title
  return String(row?.version || '').trim() || '-'
}

function openCreateDialog() {
  resetForm()
  formMode.value = 'create'
  showDialog.value = true
}

function openEditDialog(row) {
  resetForm()
  formMode.value = 'edit'
  editingId.value = String(row?.id || '')
  form.version = String(row?.version || '')
  form.title = String(row?.title || '')
  form.summary = String(row?.summary || '')
  form.content = String(row?.content || '')
  form.release_date = String(row?.release_date || '')
  form.published = Boolean(row?.published)
  form.sort_order = Number(row?.sort_order || 100)
  showDialog.value = true
}

async function fetchEntries() {
  const data = await api.get('/changelog-entries')
  entries.value = Array.isArray(data?.items) ? data.items : []
}

async function refresh() {
  loading.value = true
  try {
    await fetchEntries()
  } catch (err) {
    entries.value = []
    ElMessage.error(err?.detail || err?.message || '加载更新日志失败')
  } finally {
    loading.value = false
  }
}

async function submitEntry() {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = {
      version: form.version,
      title: form.title,
      summary: form.summary,
      content: form.content,
      release_date: form.release_date,
      published: form.published,
      sort_order: Number(form.sort_order || 100),
    }
    if (formMode.value === 'edit') {
      await api.put(`/changelog-entries/${encodeURIComponent(editingId.value)}`, payload)
    } else {
      await api.post('/changelog-entries', payload)
    }
    showDialog.value = false
    ElMessage.success('更新日志已保存')
    await refresh()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '保存更新日志失败')
  } finally {
    saving.value = false
  }
}

async function deleteEntry(row) {
  await ElMessageBox.confirm(`确定删除「${resolveDisplayTitle(row)}」？`, '确认', {
    type: 'warning',
  })
  try {
    await api.delete(`/changelog-entries/${encodeURIComponent(row.id)}`)
    ElMessage.success('更新日志已删除')
    await refresh()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '删除更新日志失败')
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
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

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
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

  .filter-panel__grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
