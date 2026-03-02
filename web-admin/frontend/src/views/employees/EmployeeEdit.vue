<template>
  <div v-loading="loading">
    <h3>编辑员工: {{ form.name }}</h3>
    <el-form :model="form" :rules="rules" ref="formRef" label-width="120px" class="form-wrap">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>

      <el-divider content-position="left">技能配置</el-divider>
      <el-form-item label="选择技能">
        <el-checkbox-group v-model="form.skills">
          <el-checkbox
            v-for="s in availableSkills"
            :key="s.id"
            :label="s.id"
            :value="s.id"
            :disabled="optionsLoading"
          >
            {{ s.name }} ({{ s.id }})
          </el-checkbox>
        </el-checkbox-group>
        <div class="field-hint">来源：系统技能目录（可在“技能目录”中导入/维护）。</div>
      </el-form-item>

      <el-divider content-position="left">规则绑定</el-divider>
      <el-form-item label="领域筛选">
        <el-select
          v-model="ruleDomainFilter"
          clearable
          filterable
          class="select-wide"
          :disabled="optionsLoading"
          placeholder="全部领域"
        >
          <el-option v-for="d in availableDomains" :key="d" :label="d" :value="d" />
        </el-select>
        <div class="field-hint">领域仅用于筛选规则，不直接保存绑定。</div>
      </el-form-item>

      <el-form-item label="规则标题">
        <el-select
          v-model="selectedRuleIds"
          class="select-wide"
          multiple
          filterable
          clearable
          collapse-tags
          collapse-tags-tooltip
          :disabled="optionsLoading"
          placeholder="从系统规则中选择标题"
        >
          <el-option
            v-for="rule in filteredRules"
            :key="rule.id"
            :label="rule.title"
            :value="rule.id"
          />
        </el-select>
        <div class="field-hint">来源：/api/rules。选中后系统会自动归并为规则领域保存。</div>
        <div v-if="filteredRules.length" class="domain-catalog">
          <div v-for="rule in filteredRules" :key="rule.id" class="domain-catalog-item">
            <el-tag size="small" :type="selectedRuleIds.includes(rule.id) ? 'success' : 'info'">
              {{ selectedRuleIds.includes(rule.id) ? '已选' : '可选' }}
            </el-tag>
            <span class="domain-catalog-name">{{ rule.title }}</span>
            <span class="domain-catalog-text">{{ rule.domain || '未分配领域' }}</span>
          </div>
        </div>
        <div v-if="!optionsLoading && !filteredRules.length" class="empty-action">
          当前筛选下暂无可选规则，请先在规则管理中创建。
        </div>
        <div class="preview-line">
          <span class="preview-label">保存领域：</span>
          <el-tag
            v-for="domain in form.rule_domains"
            :key="domain"
            size="small"
            class="preview-tag"
          >
            {{ domain }}
          </el-tag>
          <span v-if="!form.rule_domains.length" class="preview-empty">未选择</span>
        </div>
      </el-form-item>

      <el-divider content-position="left">人设设定</el-divider>
      <el-form-item label="语调">
        <el-select v-model="form.tone">
          <el-option label="专业" value="professional" />
          <el-option label="友好" value="friendly" />
          <el-option label="严格" value="strict" />
          <el-option label="导师" value="mentor" />
        </el-select>
      </el-form-item>
      <el-form-item label="风格">
        <el-select v-model="form.verbosity">
          <el-option label="详细" value="verbose" />
          <el-option label="简洁" value="concise" />
          <el-option label="极简" value="minimal" />
        </el-select>
      </el-form-item>
      <el-form-item label="风格提示">
        <div class="field-hint style-hint-desc">
          用于约束回答表达方式（不是业务规则），例如“先结论后步骤”“输出清单化”。
        </div>
        <div class="style-preset-row">
          <el-tag
            v-for="preset in styleHintPresets"
            :key="preset"
            class="style-preset-tag"
            :type="form.style_hints.includes(preset) ? 'success' : 'info'"
            @click="addStyleHintPreset(preset)"
          >
            {{ preset }}
          </el-tag>
        </div>
        <div v-for="(hint, i) in form.style_hints" :key="i" class="hint-row">
          <el-input
            v-model="form.style_hints[i]"
            size="small"
            placeholder="例如：先给结论，再给操作步骤"
          />
          <el-button text type="danger" size="small" @click="removeStyleHint(i)">删除</el-button>
        </div>
        <el-button text type="primary" size="small" @click="addStyleHintRow">+ 添加提示</el-button>
        <div class="field-hint">获取方式：可从团队写作规范、评审高频意见、优秀历史回复中提炼。</div>
      </el-form-item>

      <el-divider content-position="left">进化配置</el-divider>
      <el-form-item label="自动学习">
        <el-switch v-model="form.auto_evolve" />
      </el-form-item>
      <el-form-item label="入库阈值" v-if="form.auto_evolve">
        <el-slider v-model="form.evolve_threshold" :min="0.5" :max="1" :step="0.05" show-input />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        <el-button @click="$router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'

const route = useRoute()
const router = useRouter()
const formRef = ref(null)
const loading = ref(false)
const saving = ref(false)
const optionsLoading = ref(false)
const availableSkills = ref([])
const availableRules = ref([])
const selectedRuleIds = ref([])
const ruleDomainFilter = ref('')

const form = reactive({
  name: '',
  description: '',
  skills: [],
  rule_domains: [],
  tone: 'professional',
  verbosity: 'concise',
  style_hints: [],
  auto_evolve: true,
  evolve_threshold: 0.8,
})

const rules = {
  name: [{ required: true, message: '请输入员工名称', trigger: 'blur' }],
}

const styleHintPresets = [
  '先给结论后给步骤',
  '输出结构化清单',
  '标注风险与前置条件',
  '给出可执行命令示例',
  '默认使用简洁中文',
]

async function fetchDetail() {
  loading.value = true
  try {
    const { employee } = await api.get(`/employees/${route.params.id}`)
    Object.assign(form, {
      name: employee.name,
      description: employee.description || '',
      skills: employee.skills || [],
      rule_domains: employee.rule_domains || [],
      tone: employee.tone || 'professional',
      verbosity: employee.verbosity || 'concise',
      style_hints: employee.style_hints || [],
      auto_evolve: employee.auto_evolve ?? true,
      evolve_threshold: employee.evolve_threshold ?? 0.8,
    })
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = { ...form, style_hints: normalizeStyleHints(form.style_hints) }
    await api.put(`/employees/${route.params.id}`, payload)
    ElMessage.success('保存成功')
    router.push(`/employees/${route.params.id}`)
  } catch (e) {
    ElMessage.error(e.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function ensureOptionCoverage() {
  const skillIds = new Set(availableSkills.value.map((s) => s.id))
  for (const skillId of form.skills || []) {
    if (!skillIds.has(skillId)) {
      availableSkills.value.push({ id: skillId, name: `${skillId} (历史配置)` })
      skillIds.add(skillId)
    }
  }
}

const ruleMap = computed(() =>
  new Map(availableRules.value.map((rule) => [rule.id, rule]))
)

function normalizeDomain(domain) {
  return String(domain || '').trim().toLowerCase()
}

const availableDomains = computed(() => {
  const seen = new Set()
  const domains = []
  for (const rule of availableRules.value) {
    const domain = String(rule.domain || '').trim()
    const normalized = normalizeDomain(domain)
    if (!domain || seen.has(normalized)) continue
    seen.add(normalized)
    domains.push(domain)
  }
  for (const existingDomain of form.rule_domains || []) {
    const normalized = normalizeDomain(existingDomain)
    if (!existingDomain || seen.has(normalized)) continue
    seen.add(normalized)
    domains.push(existingDomain)
  }
  return domains
})

const filteredRules = computed(() => {
  if (!ruleDomainFilter.value) return availableRules.value
  const target = normalizeDomain(ruleDomainFilter.value)
  return availableRules.value.filter((rule) => normalizeDomain(rule.domain) === target)
})

function collectRuleDomainsByRuleIds(ruleIds) {
  const seen = new Set()
  const domains = []
  for (const ruleId of ruleIds) {
    const rule = ruleMap.value.get(ruleId)
    const domain = String(rule?.domain || '').trim()
    const normalized = normalizeDomain(domain)
    if (!domain || seen.has(normalized)) continue
    seen.add(normalized)
    domains.push(domain)
  }
  return domains
}

function syncRuleDomainsFromSelectedRules() {
  form.rule_domains = collectRuleDomainsByRuleIds(selectedRuleIds.value)
}

watch(selectedRuleIds, syncRuleDomainsFromSelectedRules, { immediate: true })

function hydrateSelectedRulesFromDomains(domains = []) {
  if (!domains.length) return
  const targets = new Set(domains.map(normalizeDomain).filter(Boolean))
  selectedRuleIds.value = availableRules.value
    .filter((rule) => targets.has(normalizeDomain(rule.domain)))
    .map((rule) => rule.id)
  if (!ruleDomainFilter.value && domains[0]) {
    for (const domain of availableDomains.value) {
      if (normalizeDomain(domain) === normalizeDomain(domains[0])) {
        ruleDomainFilter.value = domain
        break
      }
    }
  }
}

function addStyleHintRow() {
  form.style_hints.push('')
}

function removeStyleHint(index) {
  form.style_hints.splice(index, 1)
}

function addStyleHintPreset(preset) {
  if (form.style_hints.includes(preset)) return
  form.style_hints.push(preset)
}

function normalizeStyleHints(hints) {
  const seen = new Set()
  const result = []
  for (const item of hints || []) {
    const value = String(item || '').trim()
    if (!value || seen.has(value)) continue
    seen.add(value)
    result.push(value)
  }
  return result
}

async function fetchSelectionOptions() {
  optionsLoading.value = true
  try {
    const [skillsRes, rulesRes] = await Promise.all([
      api.get('/skills'),
      api.get('/rules'),
    ])
    availableSkills.value = (skillsRes.skills || []).map((s) => ({
      id: s.id,
      name: s.name || s.id,
    }))
    availableRules.value = (rulesRes.rules || []).map((rule) => ({
      id: rule.id,
      title: String(rule.title || rule.id || '').trim(),
      domain: String(rule.domain || '').trim(),
    }))
    ensureOptionCoverage()
    hydrateSelectedRulesFromDomains(form.rule_domains)
  } catch {
    ElMessage.error('加载技能/规则选项失败')
  } finally {
    optionsLoading.value = false
  }
}

onMounted(async () => {
  await fetchDetail()
  await fetchSelectionOptions()
})
</script>

<style scoped>
.form-wrap {
  max-width: 600px;
}

.select-wide {
  width: 100%;
}

.field-hint {
  margin-top: 6px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.domain-catalog {
  margin-top: 8px;
  padding: 8px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 4px;
  background: var(--color-bg-container);
}

.domain-catalog-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.domain-catalog-item:last-child {
  margin-bottom: 0;
}

.domain-catalog-name {
  min-width: 72px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.domain-catalog-text {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.empty-action {
  margin-top: 8px;
  color: var(--el-color-warning);
}

.preview-line {
  margin-top: 8px;
}

.preview-label {
  color: var(--color-text-secondary);
  margin-right: 8px;
}

.preview-tag {
  margin-right: 6px;
  margin-bottom: 6px;
}

.preview-empty {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.hint-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}

.style-hint-desc {
  margin-bottom: 6px;
}

.style-preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.style-preset-tag {
  cursor: pointer;
}
</style>
