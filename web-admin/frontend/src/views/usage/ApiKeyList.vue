<template>
  <div v-loading="loading" class="settings-page">
    <section class="settings-hero">
      <div class="settings-hero__copy">
        <div class="settings-hero__eyebrow">Access Tokens</div>
        <h1 class="settings-hero__title">API Key 管理</h1>
        <p class="settings-hero__summary">
          管理当前账号创建的访问密钥，支持按用户、创建人和时间快速筛选。
        </p>
        <div class="settings-hero__meta">
          <span>总 Key {{ keys.length }}</span>
          <span>当前筛选 {{ filteredKeys.length }}</span>
        </div>
      </div>

      <div class="settings-hero__actions">
        <el-button @click="fetchKeys">刷新</el-button>
        <el-button v-if="canCreateKey" type="primary" @click="showCreate = true">创建 Key</el-button>
      </div>
    </section>

    <section class="filter-panel">
      <div class="filter-panel__grid">
        <el-input
          v-model="filters.query"
          clearable
          placeholder="搜索 Key、用户或创建人"
        />
        <el-select v-model="filters.sort" placeholder="排序方式">
          <el-option label="最新创建" value="created_desc" />
          <el-option label="最早创建" value="created_asc" />
          <el-option label="用户 A-Z" value="developer_asc" />
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
          <div class="table-panel__eyebrow">Token List</div>
          <div class="table-panel__title">密钥列表</div>
        </div>
        <div class="table-panel__meta">共 {{ filteredKeys.length }} 条</div>
      </div>

      <el-table :data="pagedKeys" stripe>
        <el-table-column prop="key" label="Key" min-width="340" show-overflow-tooltip />
        <el-table-column prop="developer_name" label="用户" min-width="140" />
        <el-table-column label="创建人" width="160">
          <template #default="{ row }">{{ row.created_by || '-' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="220">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at, { withSeconds: true }) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="100" fixed="right" class-name="table-action-column">
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

      <div v-if="filteredKeys.length" class="table-panel__pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next, jumper, sizes"
          :total="filteredKeys.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>

      <el-empty v-if="!loading && !filteredKeys.length" description="暂无 API Key" :image-size="60" />
    </section>

    <el-dialog v-model="showCreate" title="创建 API Key" width="420px">
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime, parseDateTime } from '@/utils/date.js'
import { hasPermission } from '@/utils/permissions.js'

const loading = ref(false)
const keys = ref([])
const showCreate = ref(false)
const creating = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)

const filters = reactive({
  query: '',
  sort: 'created_desc',
})

const form = reactive({ developer_name: '' })
const canCreateKey = computed(() => hasPermission('button.apikey.create'))
const canDeleteKey = computed(() => hasPermission('button.apikey.deactivate'))

function normalizeTimestamp(value) {
  return parseDateTime(value)?.getTime() || 0
}

const filteredKeys = computed(() => {
  const keyword = String(filters.query || '').trim().toLowerCase()
  const list = (keys.value || []).filter((item) => {
    return (
      !keyword ||
      String(item?.key || '').toLowerCase().includes(keyword) ||
      String(item?.developer_name || '').toLowerCase().includes(keyword) ||
      String(item?.created_by || '').toLowerCase().includes(keyword)
    )
  })
  return list.sort((left, right) => {
    if (filters.sort === 'created_asc') {
      return normalizeTimestamp(left?.created_at) - normalizeTimestamp(right?.created_at)
    }
    if (filters.sort === 'developer_asc') {
      return String(left?.developer_name || '').localeCompare(String(right?.developer_name || ''), 'zh-CN')
    }
    return normalizeTimestamp(right?.created_at) - normalizeTimestamp(left?.created_at)
  })
})

const pagedKeys = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredKeys.value.slice(start, start + pageSize.value)
})

watch(
  () => [filters.query, filters.sort, pageSize.value],
  () => {
    currentPage.value = 1
  },
)

async function fetchKeys() {
  loading.value = true
  try {
    const { keys: list } = await api.get('/usage/keys')
    keys.value = Array.isArray(list) ? list : []
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '加载失败')
    keys.value = []
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
    await fetchKeys()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除「${row.developer_name}」的 Key？删除后不可恢复。`, '确认')
  try {
    await api.delete(`/usage/keys/${row.key}`)
    ElMessage.success('已删除')
    await fetchKeys()
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '操作失败')
  }
}

onMounted(fetchKeys)
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
    grid-template-columns: 1fr;
  }
}
</style>
