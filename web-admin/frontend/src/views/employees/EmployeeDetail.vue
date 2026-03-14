<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>员工详情: {{ emp.name }}</h3>
      <div>
        <el-button
          v-if="canUpdateEmployeeEntry"
          type="primary"
          @click="$router.push(`/employees/${route.params.id}/edit`)"
        >
          编辑
        </el-button>
        <el-button @click="$router.push(`/employees/${route.params.id}/usage`)">使用统计</el-button>
        <el-button v-if="canDeleteEmployeeEntry" type="danger" @click="handleDelete">删除</el-button>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>
    <div class="quick-actions" v-if="emp.id">
      <el-button
        v-if="emp.feedback_upgrade_enabled"
        text
        type="primary"
        @click="$router.push(`/feedback/${route.params.id}`)"
      >
        反馈
      </el-button>
      <el-tag v-else size="small" type="info">反馈模块未开启</el-tag>
      <el-button text @click="$router.push(`/memory/${route.params.id}`)">记忆</el-button>
      <el-button text @click="$router.push(`/sync/${route.params.id}`)">同步</el-button>
    </div>

    <el-descriptions :column="2" border v-if="emp.id">
      <el-descriptions-item label="ID">{{ emp.id }}</el-descriptions-item>
      <el-descriptions-item label="名称">{{ emp.name }}</el-descriptions-item>
      <el-descriptions-item label="描述" :span="2">{{ emp.description || '-' }}</el-descriptions-item>
      <el-descriptions-item label="核心目标" :span="2">{{ emp.goal || '-' }}</el-descriptions-item>
      <el-descriptions-item label="语调">{{ emp.tone }}</el-descriptions-item>
      <el-descriptions-item label="风格">{{ emp.verbosity }}</el-descriptions-item>
      <el-descriptions-item label="语言">{{ emp.language }}</el-descriptions-item>
      <el-descriptions-item label="记忆作用域">{{ emp.memory_scope }}</el-descriptions-item>
      <el-descriptions-item label="记忆保留">{{ emp.memory_retention_days }} 天</el-descriptions-item>
      <el-descriptions-item label="自动进化">{{ emp.auto_evolve ? '开启' : '关闭' }}</el-descriptions-item>
      <el-descriptions-item label="MCP 服务">{{ emp.mcp_enabled ? '开启' : '关闭' }}</el-descriptions-item>
      <el-descriptions-item label="反馈升级">{{ emp.feedback_upgrade_enabled ? '开启' : '关闭' }}</el-descriptions-item>
      <el-descriptions-item label="进化阈值">{{ emp.evolve_threshold }}</el-descriptions-item>
      <el-descriptions-item label="创建人">{{ formatRecordOwner(emp) }}</el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ emp.created_at }}</el-descriptions-item>
    </el-descriptions>

    <h4 class="section-title">技能</h4>
    <el-tag
      v-for="(s, idx) in (emp.skill_names?.length ? emp.skill_names : emp.skills)"
      :key="`${s}-${idx}`"
      class="inline-tag"
    >
      {{ s }}
    </el-tag>
    <el-empty v-if="!emp.skills?.length" description="暂无技能" :image-size="60" />

    <h4 class="section-title">绑定规则标题</h4>
    <div v-if="emp.rule_bindings?.length">
      <div v-for="rule in emp.rule_bindings" :key="rule.id" class="rule-domain-row">
        <el-tag type="warning">{{ rule.title || rule.id }}</el-tag>
        <span class="rule-domain-text">{{ rule.domain || '未知领域' }}</span>
        <span class="rule-id-text">{{ rule.id }}</span>
      </div>
    </div>
    <el-empty v-if="!emp.rule_bindings?.length" description="暂无规则" :image-size="60" />

    <h4 class="section-title">风格提示</h4>
    <div v-if="displayStyleHints.length" class="style-hint-panel">
      <div class="style-hint-head">
        <el-tag size="small" type="info">共 {{ displayStyleHints.length }} 条</el-tag>
        <span class="style-hint-desc">用于约束该员工的回答表达方式，不是业务规则。</span>
      </div>
      <div class="style-hint-list">
        <div v-for="(h, i) in displayStyleHints" :key="`${h}-${i}`" class="style-hint-item">
          <span class="style-hint-index">{{ i + 1 }}</span>
          <span class="style-hint-text">{{ h }}</span>
        </div>
      </div>
    </div>
    <el-empty v-else description="暂无风格提示" :image-size="60" />

    <h4 class="section-title">默认工作流</h4>
    <div v-if="displayWorkflow.length" class="style-hint-panel">
      <div class="style-hint-list">
        <div v-for="(h, i) in displayWorkflow" :key="`${h}-${i}`" class="style-hint-item">
          <span class="style-hint-index">{{ i + 1 }}</span>
          <span class="style-hint-text">{{ h }}</span>
        </div>
      </div>
    </div>
    <el-empty v-else description="暂无默认工作流" :image-size="60" />

    <h4 class="section-title">工具使用策略</h4>
    <div v-if="emp.tool_usage_policy" class="style-hint-panel">
      <div class="style-hint-text">{{ emp.tool_usage_policy }}</div>
    </div>
    <el-empty v-else description="暂无工具使用策略" :image-size="60" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import {
  formatRecordOwner,
  getOwnershipDeniedMessage,
} from '@/utils/ownership.js'
import { canDeleteEmployee, canUpdateEmployee } from '@/utils/employee-permissions.js'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const emp = reactive({})
const canUpdateEmployeeEntry = computed(() => canUpdateEmployee(emp))
const canDeleteEmployeeEntry = computed(() => canDeleteEmployee(emp))

const displayStyleHints = computed(() => {
  const seen = new Set()
  const normalized = []
  for (const item of emp.style_hints || []) {
    const value = String(item || '').trim()
    if (!value || seen.has(value)) continue
    seen.add(value)
    normalized.push(value)
  }
  return normalized
})

const displayWorkflow = computed(() => {
  const seen = new Set()
  const normalized = []
  for (const item of emp.default_workflow || []) {
    const value = String(item || '').trim()
    if (!value || seen.has(value)) continue
    seen.add(value)
    normalized.push(value)
  }
  return normalized
})

async function fetchDetail() {
  loading.value = true
  try {
    const { employee } = await api.get(`/employees/${route.params.id}`)
    Object.assign(emp, employee)
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete() {
  if (!canDeleteEmployeeEntry.value) {
    ElMessage.warning(getOwnershipDeniedMessage(emp, '删除'))
    return
  }
  await ElMessageBox.confirm(`确定删除员工「${emp.name}」？`, '确认')
  try {
    await api.delete(`/employees/${route.params.id}`)
    ElMessage.success('已删除')
    router.push('/employees')
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(fetchDetail)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.quick-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.rule-domain-row {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.rule-domain-text {
  color: var(--color-text-secondary);
  font-size: 13px;
}

.rule-id-text {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.style-hint-panel {
  border: 1px solid var(--color-border-secondary);
  border-radius: 8px;
  background: var(--color-bg-container);
  padding: 10px 12px;
}

.style-hint-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.style-hint-desc {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.style-hint-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.style-hint-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--color-bg-elevated);
}

.style-hint-index {
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  border-radius: 999px;
  background: var(--color-primary-6);
  color: var(--color-bg-container);
  font-size: 12px;
}

.style-hint-text {
  color: var(--color-text-primary);
  font-size: 13px;
  line-height: 1.5;
}

.section-title {
  margin-top: 20px;
}

.inline-tag {
  margin-right: 6px;
}

.toolbar h3 { margin: 0; }
</style>
