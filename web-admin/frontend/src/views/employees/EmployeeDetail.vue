<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>员工详情: {{ emp.name }}</h3>
      <div>
        <el-button type="primary" @click="$router.push(`/employees/${route.params.id}/edit`)">编辑</el-button>
        <el-button @click="$router.push(`/employees/${route.params.id}/usage`)">使用统计</el-button>
        <el-button type="danger" @click="handleDelete">删除</el-button>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-descriptions :column="2" border v-if="emp.id">
      <el-descriptions-item label="ID">{{ emp.id }}</el-descriptions-item>
      <el-descriptions-item label="名称">{{ emp.name }}</el-descriptions-item>
      <el-descriptions-item label="描述" :span="2">{{ emp.description || '-' }}</el-descriptions-item>
      <el-descriptions-item label="语调">{{ emp.tone }}</el-descriptions-item>
      <el-descriptions-item label="风格">{{ emp.verbosity }}</el-descriptions-item>
      <el-descriptions-item label="语言">{{ emp.language }}</el-descriptions-item>
      <el-descriptions-item label="记忆作用域">{{ emp.memory_scope }}</el-descriptions-item>
      <el-descriptions-item label="记忆保留">{{ emp.memory_retention_days }} 天</el-descriptions-item>
      <el-descriptions-item label="自动进化">{{ emp.auto_evolve ? '开启' : '关闭' }}</el-descriptions-item>
      <el-descriptions-item label="进化阈值">{{ emp.evolve_threshold }}</el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ emp.created_at }}</el-descriptions-item>
    </el-descriptions>

    <h4 class="section-title">技能</h4>
    <el-tag v-for="s in emp.skills" :key="s" class="inline-tag">{{ s }}</el-tag>
    <el-empty v-if="!emp.skills?.length" description="暂无技能" :image-size="60" />

    <h4 class="section-title">规则领域</h4>
    <div v-if="emp.rule_domains?.length">
      <div v-for="d in emp.rule_domains" :key="d" class="rule-domain-row">
        <el-tag type="warning">{{ d }}</el-tag>
        <span class="rule-domain-text">
          {{ domainRuleTitles(d).join(' / ') || '该领域暂无规则标题' }}
        </span>
      </div>
    </div>
    <el-empty v-if="!emp.rule_domains?.length" description="暂无规则" :image-size="60" />

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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const emp = reactive({})
const rulesByDomain = ref({})

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

function buildRulesByDomain(rules) {
  const grouped = {}
  for (const rule of rules) {
    const domain = String(rule.domain || '').trim()
    const title = rule.title || ''
    if (!domain || !title) continue
    if (!grouped[domain]) grouped[domain] = []
    if (!grouped[domain].includes(title)) grouped[domain].push(title)
  }
  return grouped
}

function normalizeDomain(domain) {
  return String(domain || '').trim().toLowerCase()
}

function domainRuleTitles(domain) {
  const direct = rulesByDomain.value[domain]
  if (direct?.length) return direct.slice(0, 3)
  const target = normalizeDomain(domain)
  for (const [k, titles] of Object.entries(rulesByDomain.value)) {
    if (normalizeDomain(k) === target) {
      return titles.slice(0, 3)
    }
  }
  return []
}

async function fetchDetail() {
  loading.value = true
  try {
    const [{ employee }, rulesRes] = await Promise.all([
      api.get(`/employees/${route.params.id}`),
      api.get('/rules'),
    ])
    Object.assign(emp, employee)
    rulesByDomain.value = buildRulesByDomain(rulesRes.rules || [])
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete() {
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
