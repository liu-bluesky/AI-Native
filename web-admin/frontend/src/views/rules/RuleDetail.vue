<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>规则详情: {{ rule.title }}</h3>
      <div>
        <el-button
          v-if="isManagedExperienceRule"
          type="primary"
          @click="openProjectDetail"
        >
          到项目详情编辑
        </el-button>
        <el-button
          v-else
          type="primary"
          :disabled="!canManageRecord(rule)"
          @click="$router.push(`/rules/${route.params.id}/edit`)"
        >
          编辑
        </el-button>
        <el-button
          type="danger"
          :disabled="isManagedExperienceRule || !canManageRecord(rule)"
          @click="handleDelete"
        >删除</el-button>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-descriptions :column="2" border v-if="rule.id">
      <el-descriptions-item label="ID">{{ rule.id }}</el-descriptions-item>
      <el-descriptions-item label="领域">{{ rule.domain }}</el-descriptions-item>
      <el-descriptions-item label="标题" :span="2">{{ rule.title }}</el-descriptions-item>
      <el-descriptions-item label="级别">
        <el-tag :type="sevColor(rule.severity)" size="small">{{ rule.severity }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="风险域">{{ rule.risk_domain }}</el-descriptions-item>
      <el-descriptions-item label="置信度">{{ rule.confidence }}</el-descriptions-item>
      <el-descriptions-item label="使用次数">{{ rule.use_count }}</el-descriptions-item>
      <el-descriptions-item label="版本">{{ rule.version }}</el-descriptions-item>
      <el-descriptions-item label="创建人">{{ formatRecordOwner(rule) }}</el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ rule.created_at }}</el-descriptions-item>
    </el-descriptions>

    <el-alert
      v-if="isManagedExperienceRule"
      class="section-alert"
      type="info"
      :closable="false"
      show-icon
      :title="`这条规则由项目经验工作流维护，请到${primarySourceProject?.name || '关联项目'}详情页编辑或删除。`"
    />

    <h4 class="section-title">规则内容</h4>
    <div class="rule-content" v-if="rule.content">{{ rule.content }}</div>
    <el-empty v-else description="暂无内容" :image-size="60" />

    <h4 class="section-title">绑定员工</h4>
    <div v-if="boundEmployeeRows.length" class="bound-rows">
      <el-tag
        v-for="item in boundEmployeeRows"
        :key="item.id"
        class="bound-tag"
        type="warning"
      >
        {{ item.name }} ({{ item.id }})
      </el-tag>
    </div>
    <el-empty v-else description="暂无绑定员工" :image-size="60" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import {
  canManageRecord,
  formatRecordOwner,
  getOwnershipDeniedMessage,
} from '@/utils/ownership.js'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const rule = reactive({})
const employeesById = ref(new Map())
const boundEmployeeRows = ref([])
const sourceProjectBindings = computed(() =>
  Array.isArray(rule.source_project_bindings) ? rule.source_project_bindings : [],
)
const primarySourceProject = computed(() => sourceProjectBindings.value[0] || null)
const isManagedExperienceRule = computed(() =>
  rule.system_source === 'project_experience' || rule.system_source === 'development_experience',
)

function sevColor(s) {
  return { required: 'danger', recommended: 'warning', optional: 'info' }[s] || 'info'
}

async function fetchDetail() {
  loading.value = true
  try {
    const data = await api.get(`/rules/${route.params.id}`)
    Object.assign(rule, data.rule)
    const ids = Array.isArray(data?.rule?.bound_employees) ? data.rule.bound_employees : []
    boundEmployeeRows.value = ids.map((id) => ({
      id,
      name: employeesById.value.get(id) || id,
    }))
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function fetchEmployees() {
  try {
    const data = await api.get('/employees')
    const rows = Array.isArray(data?.employees) ? data.employees : []
    const map = new Map()
    for (const item of rows) {
      const id = String(item?.id || '').trim()
      if (!id) continue
      map.set(id, String(item?.name || id))
    }
    employeesById.value = map
  } catch {
    employeesById.value = new Map()
  }
}

async function handleDelete() {
  if (isManagedExperienceRule.value) {
    ElMessage.warning('经验规则请到项目详情中管理')
    return
  }
  if (!canManageRecord(rule)) {
    ElMessage.warning(getOwnershipDeniedMessage(rule, '删除'))
    return
  }
  await ElMessageBox.confirm(`确定删除规则「${rule.title}」？`, '确认')
  try {
    await api.delete(`/rules/${route.params.id}`)
    ElMessage.success('已删除')
    router.push('/rules')
  } catch {
    ElMessage.error('删除失败')
  }
}

function openProjectDetail() {
  const projectId = String(primarySourceProject.value?.id || '').trim()
  if (!projectId) {
    ElMessage.warning('当前经验规则未关联可跳转的项目')
    return
  }
  router.push(`/projects/${projectId}`)
}

onMounted(async () => {
  await fetchEmployees()
  await fetchDetail()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 { margin: 0; }
.rule-content {
  background: var(--color-bg-container);
  padding: 16px;
  border-radius: 4px;
  border: 1px solid var(--color-border-secondary);
  white-space: pre-wrap;
  line-height: 1.6;
}

.section-title {
  margin-top: 20px;
}

.section-alert {
  margin-top: 16px;
}

.bound-rows {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.bound-tag {
  margin-right: 0;
}
</style>
