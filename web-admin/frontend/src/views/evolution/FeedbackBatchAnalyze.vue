<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>批量综合反思: {{ employeeId }}</h3>
      <div class="toolbar-actions">
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-card shadow="never" class="project-card">
      <el-form inline>
        <el-form-item label="项目名称">
          <el-select
            v-model="projectId"
            filterable
            placeholder="请选择项目"
            class="project-input"
            @change="persistProject"
          >
            <el-option
              v-for="item in projectOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="config-card">
      <el-form inline>
        <el-form-item label="目标规则" required>
          <el-select
            v-model="targetRuleId"
            clearable
            filterable
            placeholder="请选择要升级的规则"
            style="width: 360px"
          >
            <el-option
              v-for="item in ruleOptions"
              :key="`batch-rule-${item.value}`"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="反思供应商">
          <el-select
            v-model="reflectionForm.provider_id"
            clearable
            filterable
            placeholder="默认配置或临时选择"
            style="width: 220px"
            @change="onReflectionProviderChange"
          >
            <el-option
              v-for="item in reflectionProviders"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="反思模型">
          <el-select
            v-model="reflectionForm.model_name"
            clearable
            filterable
            allow-create
            default-first-option
            placeholder="默认配置或临时输入"
            style="width: 220px"
          >
            <el-option
              v-for="item in availableReflectionModels"
              :key="`${item.provider_id}-${item.model_name}`"
              :label="item.model_name"
              :value="item.model_name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="温度">
          <el-input-number v-model="reflectionForm.temperature" :min="0" :max="2" :step="0.1" :precision="2" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="analyzing" :disabled="!feedbackIds.length" @click="runBatchAnalyze">
            生成综合内容
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>待分析反馈（{{ feedbackIds.length }}）</template>
      <el-empty v-if="!bugs.length" description="没有可分析的反馈，请返回列表重新勾选" :image-size="60" />
      <el-table v-else :data="bugs" stripe>
        <el-table-column prop="id" label="ID" width="130" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="140" />
        <el-table-column prop="rule_id" label="规则ID" min-width="140" show-overflow-tooltip />
        <el-table-column prop="symptom" label="现象" min-width="260" show-overflow-tooltip />
        <el-table-column prop="expected" label="期望" min-width="260" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card" v-if="candidate">
      <template #header>AI 综合生成结果</template>
      <el-form label-width="110px">
        <el-form-item label="候选ID">
          <el-tag>{{ candidate.id }}</el-tag>
        </el-form-item>
        <el-form-item label="汇总工单">
          <el-tag type="success">{{ aggregateBugId || '-' }}</el-tag>
        </el-form-item>
        <el-form-item label="关联反馈">
          <span>{{ (candidate.feedback_ids || []).join(', ') }}</span>
        </el-form-item>
        <el-form-item label="来源工单">
          <span>{{ (candidate.source_feedback_ids || feedbackIds).join(', ') }}</span>
        </el-form-item>
        <el-form-item label="建议内容">
          <el-input v-model="proposedContent" type="textarea" :rows="10" />
        </el-form-item>
        <el-form-item label="可执行规则">
          <el-input v-model="executableContent" type="textarea" :rows="6" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="openCandidateDetail">去详情审核/发布</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const analyzing = ref(false)
const employeeId = computed(() => route.params.id)
const projectId = ref(localStorage.getItem('project_id') || 'default')
const projectOptions = ref([])
const feedbackIds = ref([])
const bugs = ref([])
const ruleOptions = ref([])
const targetRuleId = ref('')
const aggregateBugId = ref('')
const candidate = ref(null)
const proposedContent = ref('')
const executableContent = ref('')
const reflectionProviders = ref([])
const reflectionOptions = ref([])

const reflectionForm = reactive({
  provider_id: '',
  model_name: '',
  temperature: 0.2,
})

const availableReflectionModels = computed(() => {
  const providerId = String(reflectionForm.provider_id || '').trim()
  if (!providerId) return reflectionOptions.value
  return reflectionOptions.value.filter((item) => String(item.provider_id || '').trim() === providerId)
})

function parseFeedbackIds() {
  const raw = String(route.query.feedback_ids || '').trim()
  const parsed = raw.split(',').map((item) => String(item || '').trim()).filter(Boolean)
  const seen = new Set()
  feedbackIds.value = parsed.filter((item) => {
    if (seen.has(item)) return false
    seen.add(item)
    return true
  })
}

function normalizeProjectId(value) {
  return String(value || '').trim()
}

async function fetchProjectOptions() {
  const current = normalizeProjectId(projectId.value)
  try {
    const data = await api.get('/projects')
    const projects = Array.isArray(data.projects) ? data.projects : []
    const options = projects
      .map((item) => {
        const id = normalizeProjectId(item.id)
        if (!id) return null
        const name = normalizeProjectId(item.name)
        return {
          value: id,
          label: name ? `${name} (${id})` : id,
        }
      })
      .filter(Boolean)
    if (current && !options.some((item) => item.value === current)) {
      options.unshift({ value: current, label: current })
    }
    projectOptions.value = options.length ? options : [{ value: 'default', label: 'default' }]

    if (!current) {
      projectId.value = projectOptions.value[0].value
      localStorage.setItem('project_id', projectId.value)
      return
    }

    const matchedByName = projects.find((item) => normalizeProjectId(item.name) === current)
    if (matchedByName) {
      const matchedId = normalizeProjectId(matchedByName.id)
      if (matchedId) {
        projectId.value = matchedId
        localStorage.setItem('project_id', matchedId)
      }
      return
    }

    if (!projectOptions.value.some((item) => item.value === current)) {
      projectId.value = projectOptions.value[0].value
      localStorage.setItem('project_id', projectId.value)
    }
  } catch {
    const fallback = current || 'default'
    projectId.value = fallback
    projectOptions.value = [{ value: fallback, label: fallback }]
    localStorage.setItem('project_id', fallback)
  }
}

function persistProject() {
  const nextValue = normalizeProjectId(projectId.value)
  const fallback = projectOptions.value[0]?.value || 'default'
  const selected = nextValue && projectOptions.value.some((item) => item.value === nextValue)
    ? nextValue
    : fallback
  projectId.value = selected
  localStorage.setItem('project_id', selected)
  fetchRuleOptions()
  fetchReflectionConfig()
  fetchSelectedBugs()
}

async function fetchRuleOptions() {
  try {
    const data = await api.get('/rules')
    const rules = Array.isArray(data.rules) ? data.rules : []
    ruleOptions.value = rules.map((rule) => {
      const id = String(rule.id || '').trim()
      const title = String(rule.title || '').trim()
      const domain = String(rule.domain || '').trim()
      const label = [title, id, domain ? `领域:${domain}` : ''].filter(Boolean).join(' | ')
      return { value: id, label: label || id }
    }).filter((item) => item.value)
  } catch {
    ruleOptions.value = []
  }
}

function onReflectionProviderChange(providerId) {
  const value = String(providerId || '').trim()
  if (!value) return
  const candidateModel = reflectionOptions.value.find((item) => String(item.provider_id || '').trim() === value && item.is_default)
    || reflectionOptions.value.find((item) => String(item.provider_id || '').trim() === value)
  if (candidateModel && !reflectionForm.model_name) {
    reflectionForm.model_name = String(candidateModel.model_name || '').trim()
  }
}

async function fetchReflectionConfig() {
  try {
    const data = await api.get(`/projects/${encodeURIComponent(projectId.value)}/feedback/reflection/config`, {
      params: { employee_id: employeeId.value },
    })
    reflectionProviders.value = Array.isArray(data.providers) ? data.providers : []
    reflectionOptions.value = Array.isArray(data.options) ? data.options : []
    const config = data.config || {}
    reflectionForm.provider_id = String(config.provider_id || '')
    reflectionForm.model_name = String(config.model_name || '')
    const temperature = Number(config.temperature)
    reflectionForm.temperature = Number.isFinite(temperature) ? temperature : 0.2
    if (reflectionForm.provider_id && !reflectionForm.model_name) {
      onReflectionProviderChange(reflectionForm.provider_id)
    }
  } catch {
    reflectionProviders.value = []
    reflectionOptions.value = []
  }
}

async function fetchSelectedBugs() {
  if (!feedbackIds.value.length) {
    bugs.value = []
    return
  }
  loading.value = true
  try {
    const tasks = feedbackIds.value.map((feedbackId) => api.get(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs/${feedbackId}`))
    const results = await Promise.allSettled(tasks)
    bugs.value = results
      .filter((item) => item.status === 'fulfilled')
      .map((item) => item.value?.bug)
      .filter(Boolean)
    if (!targetRuleId.value) {
      const uniqRuleIds = [...new Set(bugs.value.map((item) => String(item.rule_id || '').trim()).filter(Boolean))]
      if (uniqRuleIds.length === 1) {
        targetRuleId.value = uniqRuleIds[0]
      }
    }
    if (!bugs.value.length) {
      ElMessage.warning('没有加载到可分析的反馈，请返回列表重新勾选')
    }
  } finally {
    loading.value = false
  }
}

async function runBatchAnalyze() {
  if (!feedbackIds.value.length) {
    ElMessage.warning('缺少反馈 ID，无法综合分析')
    return
  }
  if (reflectionForm.model_name && !String(reflectionForm.provider_id || '').trim()) {
    ElMessage.warning('选择反思模型时必须同时选择供应商')
    return
  }
  if (!String(targetRuleId.value || '').trim()) {
    ElMessage.warning('请选择目标规则后再执行批量反思')
    return
  }
  analyzing.value = true
  try {
    const data = await api.post(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs/batch-analyze`, {
      feedback_ids: feedbackIds.value,
      target_rule_id: targetRuleId.value,
      provider_id: reflectionForm.provider_id || undefined,
      model_name: reflectionForm.model_name || undefined,
      temperature: Number(reflectionForm.temperature),
    })
    aggregateBugId.value = String(data?.bug?.id || '')
    candidate.value = data.candidate || null
    proposedContent.value = String(candidate.value?.proposed_rule_content || '')
    executableContent.value = String(candidate.value?.executable_rule_content || '')
    ElMessage.success('已完成综合分析并生成一份候选内容')
    fetchSelectedBugs()
  } catch (e) {
    ElMessage.error(e.detail || '综合分析失败')
  } finally {
    analyzing.value = false
  }
}

function openCandidateDetail() {
  const firstId = String(
    aggregateBugId.value
      || (candidate.value?.feedback_ids || [])[0]
      || (feedbackIds.value || [])[0]
      || '',
  ).trim()
  if (!firstId) return
  router.push(`/feedback/${employeeId.value}/${firstId}`)
}

onMounted(async () => {
  await fetchProjectOptions()
  parseFeedbackIds()
  await fetchRuleOptions()
  await fetchReflectionConfig()
  await fetchSelectedBugs()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.toolbar h3 {
  margin: 0;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.project-card {
  margin-bottom: 12px;
}

.config-card {
  margin-bottom: 12px;
}

.project-input {
  width: 220px;
}

.section-card {
  margin-bottom: 12px;
}
</style>
