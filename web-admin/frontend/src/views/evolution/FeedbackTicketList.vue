<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>反馈工单: {{ employeeId }}</h3>
      <div class="toolbar-actions">
        <el-button
          type="danger"
          plain
          :disabled="!selectedFeedbackIds.length"
          @click="deleteSelectedBugs"
        >
          批量删除
        </el-button>
        <el-button
          type="warning"
          plain
          :disabled="feedbackDisabled || !selectedFeedbackIds.length"
          @click="openBatchAnalyzePage"
        >
          批量反思
        </el-button>
        <el-button @click="$router.back()">返回</el-button>
        <el-button type="primary" :disabled="feedbackDisabled" @click="openCreate">新建反馈</el-button>
      </div>
    </div>

    <el-card shadow="never" class="filter-card">
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
        <el-form-item label="项目反馈开关">
          <el-switch
            v-model="projectConfig.enabled"
            :disabled="configLoading || !projectConfig.enabled_global"
            :loading="configLoading"
            @change="toggleProjectConfig"
          />
          <el-tag size="small" :type="projectConfig.enabled_global ? 'success' : 'danger'" class="ml8">
            {{ projectConfig.enabled_global ? '全局已开' : '全局已关' }}
          </el-tag>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="new" value="new" />
            <el-option label="analyzing" value="analyzing" />
            <el-option label="pending_review" value="pending_review" />
            <el-option label="closed" value="closed" />
            <el-option label="analyze_failed" value="analyze_failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-select
            v-model="filters.category"
            clearable
            filterable
            placeholder="全部"
            style="width: 180px"
          >
            <el-option v-for="item in categoryOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="规则">
          <el-select
            v-model="filters.rule_id"
            clearable
            filterable
            placeholder="按规则筛选"
            style="width: 260px"
          >
            <el-option
              v-for="item in ruleOptions"
              :key="item.value"
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
          <el-button plain @click="saveReflectionConfig">保存反思模型</el-button>
        </el-form-item>
        <el-form-item label="严重级别">
          <el-select v-model="filters.severity" clearable placeholder="全部" style="width: 130px">
            <el-option label="low" value="low" />
            <el-option label="medium" value="medium" />
            <el-option label="high" value="high" />
            <el-option label="critical" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="runQuery">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    <el-alert
      v-if="feedbackDisabled"
      class="warn-alert"
      type="warning"
      :closable="false"
      show-icon
      title="当前项目反馈模块已关闭（或全局关闭），无法新建/反思反馈。"
    />

    <el-card shadow="never" class="summary-card">
      <template #header>分类汇总（手动升级）</template>
      <el-empty v-if="!summaryRows.length" description="暂无分类汇总数据" :image-size="50" />
      <el-table v-else :data="summaryRows" stripe>
        <el-table-column label="分类" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatCategory(row.category) }}</template>
        </el-table-column>
        <el-table-column prop="total" label="总数" width="80" align="center" />
        <el-table-column prop="pending_review_count" label="待审核" width="90" align="center" />
        <el-table-column prop="closed_count" label="已关闭" width="90" align="center" />
        <el-table-column label="最近更新" min-width="220">
          <template #default="{ row }">{{ formatDateTime(row.latest_updated_at) }}</template>
        </el-table-column>
        <el-table-column label="样例标题" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ (row.sample_titles || []).join(' / ') || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="110" fixed="right" class-name="table-action-column">
          <template #default="{ row }">
            <el-button text type="primary" :disabled="feedbackDisabled || !row.feedback_ids?.length" @click="openManualUpgrade(row)">
              手动升级
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-table
      :data="bugs"
      stripe
      row-key="id"
      @selection-change="onBugSelectionChange"
    >
      <el-table-column type="selection" width="46" />
      <el-table-column prop="id" label="ID" width="140" />
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="分类" width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ formatCategory(row.category) }}</template>
      </el-table-column>
      <el-table-column prop="severity" label="级别" width="100">
        <template #default="{ row }">
          <el-tag :type="severityTag(row.severity)" size="small">{{ row.severity }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="130">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="220">
        <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="290" fixed="right" class-name="table-action-column">
        <template #default="{ row }">
          <el-button text type="primary" @click="openDetail(row.id)">详情</el-button>
          <el-button
            text
            type="success"
            :disabled="row.status === 'analyzing' || feedbackDisabled"
            @click="analyze(row.id)"
          >
            反思
          </el-button>
          <el-button text type="danger" @click="deleteSingleBug(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!bugs.length && !loading" description="暂无反馈" :image-size="60" />

    <el-dialog v-model="showCreateDialog" title="新建反馈" width="640px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="标题" required>
          <el-input v-model="createForm.title" placeholder="反馈标题" />
        </el-form-item>
        <el-form-item label="现象" required>
          <el-input v-model="createForm.symptom" type="textarea" :rows="3" placeholder="具体问题现象" />
        </el-form-item>
        <el-form-item label="期望" required>
          <el-input v-model="createForm.expected" type="textarea" :rows="3" placeholder="希望输出/行为" />
        </el-form-item>
        <el-form-item label="严重级别">
          <el-select v-model="createForm.severity" style="width: 160px">
            <el-option label="low" value="low" />
            <el-option label="medium" value="medium" />
            <el-option label="high" value="high" />
            <el-option label="critical" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item label="问题分类">
          <el-select
            v-model="createForm.category"
            filterable
            placeholder="请选择问题分类"
            style="width: 260px"
          >
            <el-option v-for="item in categoryOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="会话 ID">
          <el-input v-model="createForm.session_id" placeholder="可选" />
        </el-form-item>
        <el-form-item label="规则">
          <el-select
            v-model="createForm.rule_id"
            clearable
            filterable
            placeholder="可选，关联已有规则"
            style="width: 320px"
          >
            <el-option
              v-for="item in ruleOptions"
              :key="`create-${item.value}`"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showManualDialog" title="按分类手动升级" width="760px">
      <el-form :model="manualForm" label-width="120px">
        <el-form-item label="分类">
          <el-select
            v-model="manualForm.category"
            filterable
            allow-create
            default-first-option
            placeholder="请选择分类"
            style="width: 260px"
          >
            <el-option v-for="item in categoryOptions" :key="`manual-cat-${item.value}`" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联反馈">
          <el-tag v-for="fid in manualForm.feedback_ids" :key="fid" class="fid-tag">{{ fid }}</el-tag>
        </el-form-item>
        <el-form-item label="目标规则 ID">
          <el-select
            v-model="manualForm.target_rule_id"
            clearable
            filterable
            placeholder="可选，不填则发布时自动新建规则"
            style="width: 360px"
          >
            <el-option
              v-for="item in ruleOptions"
              :key="`manual-${item.value}`"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="风险级别">
          <el-select v-model="manualForm.risk_level" style="width: 180px">
            <el-option label="low" value="low" />
            <el-option label="medium" value="medium" />
            <el-option label="high" value="high" />
          </el-select>
        </el-form-item>
        <el-form-item label="置信度">
          <el-input-number v-model="manualForm.confidence" :step="0.05" :min="0" :max="1" />
        </el-form-item>
        <el-form-item label="升级建议" required>
          <el-input
            v-model="manualForm.proposed_rule_content"
            type="textarea"
            :rows="10"
            placeholder="请输入你希望发布的规则内容（人工整理后的最终版本）"
          />
        </el-form-item>
        <el-form-item label="可执行规则">
          <el-input
            v-model="manualForm.executable_rule_content"
            type="textarea"
            :rows="8"
            placeholder="可选：可执行约束/检查清单。留空则由系统根据关联反馈自动生成。"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="manualForm.comment" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showManualDialog = false">取消</el-button>
        <el-button type="primary" :loading="manualSubmitting" @click="submitManualUpgrade">创建候选</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showAnalyzeDialog" title="选择反思模型" width="620px">
      <el-form :model="reflectionForm" label-width="100px">
        <el-form-item label="供应商">
          <el-select
            v-model="reflectionForm.provider_id"
            clearable
            filterable
            placeholder="默认配置或临时选择"
            style="width: 100%"
            @change="onReflectionProviderChange"
          >
            <el-option
              v-for="item in reflectionProviders"
              :key="`dlg-provider-${item.id}`"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="模型">
          <el-select
            v-model="reflectionForm.model_name"
            clearable
            filterable
            allow-create
            default-first-option
            placeholder="默认配置或临时输入"
            style="width: 100%"
          >
            <el-option
              v-for="item in availableReflectionModels"
              :key="`dlg-model-${item.provider_id}-${item.model_name}`"
              :label="item.model_name"
              :value="item.model_name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="温度">
          <el-input-number v-model="reflectionForm.temperature" :min="0" :max="2" :step="0.1" :precision="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAnalyzeDialog = false">取消</el-button>
        <el-button type="primary" :loading="analyzeSubmitting" @click="submitAnalyze">开始反思</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const submitting = ref(false)
const manualSubmitting = ref(false)
const analyzeSubmitting = ref(false)
const configLoading = ref(false)
const showCreateDialog = ref(false)
const showManualDialog = ref(false)
const showAnalyzeDialog = ref(false)
const analyzeTargetFeedbackId = ref('')
const employeeId = computed(() => route.params.id)
const projectId = ref(localStorage.getItem('project_id') || 'default')
const projectOptions = ref([])
const ruleOptions = ref([])
const reflectionProviders = ref([])
const reflectionOptions = ref([])
const projectConfig = reactive({
  enabled: true,
  enabled_global: true,
})
const feedbackDisabled = computed(() => !projectConfig.enabled || !projectConfig.enabled_global)

const filters = reactive({
  status: '',
  category: '',
  rule_id: '',
  severity: '',
})

const bugs = ref([])
const selectedFeedbackIds = ref([])
const summaryRows = ref([])
const categoryOptions = [
  { label: '通用', value: 'general' },
  { label: '界面设计', value: 'ui-design' },
  { label: '开发规范', value: 'development-spec' },
  { label: '代码质量', value: 'code-quality' },
  { label: '性能优化', value: 'performance' },
  { label: '安全合规', value: 'security' },
  { label: '数据模型', value: 'data-model' },
  { label: '其他', value: 'other' },
]

const createForm = reactive({
  title: '',
  symptom: '',
  expected: '',
  category: 'development-spec',
  severity: 'medium',
  session_id: '',
  rule_id: '',
})
const manualForm = reactive({
  category: '',
  target_rule_id: '',
  risk_level: 'medium',
  confidence: 0.8,
  proposed_rule_content: '',
  executable_rule_content: '',
  feedback_ids: [],
  comment: '',
})
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

function normalizeProjectId(value) {
  return String(value || '').trim()
}

function persistProject() {
  const nextValue = normalizeProjectId(projectId.value)
  const fallback = projectOptions.value[0]?.value || 'default'
  const selected = nextValue && projectOptions.value.some((item) => item.value === nextValue)
    ? nextValue
    : fallback
  projectId.value = selected
  localStorage.setItem('project_id', selected)
  fetchProjectConfig()
  fetchReflectionConfig()
  fetchBugs()
  fetchSummary()
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

function formatCategory(value) {
  const key = String(value || '').trim()
  if (!key) return '-'
  const matched = categoryOptions.find((item) => item.value === key)
  return matched ? matched.label : key
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

async function fetchProjectConfig() {
  configLoading.value = true
  try {
    const data = await api.get(`/projects/${encodeURIComponent(projectId.value)}/feedback/config`)
    const cfg = data.config || {}
    projectConfig.enabled = cfg.enabled !== false
    projectConfig.enabled_global = cfg.enabled_global !== false
  } catch (e) {
    ElMessage.error(e.detail || '读取项目反馈开关失败')
  } finally {
    configLoading.value = false
  }
}

function onReflectionProviderChange(providerId) {
  const value = String(providerId || '').trim()
  if (!value) return
  const candidate = reflectionOptions.value.find((item) => String(item.provider_id || '').trim() === value && item.is_default)
    || reflectionOptions.value.find((item) => String(item.provider_id || '').trim() === value)
  if (candidate && !reflectionForm.model_name) {
    reflectionForm.model_name = String(candidate.model_name || '').trim()
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

async function saveReflectionConfig() {
  if (!String(reflectionForm.provider_id || '').trim()) {
    ElMessage.warning('请先选择反思供应商')
    return
  }
  if (!String(reflectionForm.model_name || '').trim()) {
    ElMessage.warning('请先选择反思模型')
    return
  }
  try {
    await api.put(`/projects/${encodeURIComponent(projectId.value)}/feedback/reflection/config`, {
      employee_id: employeeId.value,
      provider_id: reflectionForm.provider_id,
      model_name: reflectionForm.model_name,
      temperature: Number(reflectionForm.temperature),
    })
    ElMessage.success('反思模型配置已保存')
    fetchReflectionConfig()
  } catch (e) {
    ElMessage.error(e.detail || '保存反思模型配置失败')
  }
}

async function toggleProjectConfig(nextEnabled) {
  configLoading.value = true
  try {
    const data = await api.patch(`/projects/${encodeURIComponent(projectId.value)}/feedback/config`, {
      enabled: Boolean(nextEnabled),
    })
    const cfg = data.config || {}
    projectConfig.enabled = cfg.enabled !== false
    projectConfig.enabled_global = cfg.enabled_global !== false
    ElMessage.success(projectConfig.enabled ? '项目反馈模块已开启' : '项目反馈模块已关闭')
    fetchBugs()
    fetchSummary()
  } catch (e) {
    projectConfig.enabled = !nextEnabled
    ElMessage.error(e.detail || '更新项目反馈开关失败')
  } finally {
    configLoading.value = false
  }
}

function severityTag(severity) {
  return {
    low: 'info',
    medium: 'warning',
    high: 'danger',
    critical: 'danger',
  }[severity] || 'info'
}

function statusTag(status) {
  return {
    new: 'info',
    analyzing: 'warning',
    pending_review: 'warning',
    closed: 'success',
    analyze_failed: 'danger',
  }[status] || 'info'
}

async function fetchBugs() {
  if (feedbackDisabled.value) {
    bugs.value = []
    selectedFeedbackIds.value = []
    return
  }
  loading.value = true
  try {
    const data = await api.get(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs`, {
      params: {
        employee_id: employeeId.value,
        status: filters.status || undefined,
        category: filters.category || undefined,
        rule_id: filters.rule_id || undefined,
        severity: filters.severity || undefined,
      },
    })
    bugs.value = data.bugs || []
    selectedFeedbackIds.value = []
  } catch (e) {
    ElMessage.error(e.detail || '加载反馈列表失败')
  } finally {
    loading.value = false
  }
}

async function fetchSummary() {
  if (feedbackDisabled.value) {
    summaryRows.value = []
    return
  }
  try {
    const data = await api.get(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs/summary`, {
      params: {
        employee_id: employeeId.value,
        rule_id: filters.rule_id || undefined,
        status: filters.status || undefined,
        severity: filters.severity || undefined,
      },
    })
    summaryRows.value = data.summary || []
  } catch (e) {
    ElMessage.error(e.detail || '加载分类汇总失败')
  }
}

async function runQuery() {
  await fetchBugs()
  await fetchSummary()
}

function openCreate() {
  createForm.title = ''
  createForm.symptom = ''
  createForm.expected = ''
  createForm.category = 'development-spec'
  createForm.severity = 'medium'
  createForm.session_id = ''
  createForm.rule_id = ''
  showCreateDialog.value = true
}

async function submitCreate() {
  if (feedbackDisabled.value) {
    ElMessage.warning('当前项目反馈模块已关闭')
    return
  }
  if (!createForm.title.trim() || !createForm.symptom.trim() || !createForm.expected.trim()) {
    ElMessage.warning('请填写标题、现象和期望')
    return
  }
  submitting.value = true
  try {
    await api.post(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs`, {
      employee_id: employeeId.value,
      title: createForm.title,
      symptom: createForm.symptom,
      expected: createForm.expected,
      category: createForm.category,
      severity: createForm.severity,
      session_id: createForm.session_id,
      rule_id: createForm.rule_id,
    })
    ElMessage.success('反馈已提交')
    showCreateDialog.value = false
    fetchBugs()
    fetchSummary()
  } catch (e) {
    ElMessage.error(e.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

async function analyze(feedbackId) {
  if (feedbackDisabled.value) {
    ElMessage.warning('当前项目反馈模块已关闭')
    return
  }
  analyzeTargetFeedbackId.value = String(feedbackId || '').trim()
  if (!analyzeTargetFeedbackId.value) return
  showAnalyzeDialog.value = true
}

function openBatchAnalyzePage() {
  if (feedbackDisabled.value) {
    ElMessage.warning('当前项目反馈模块已关闭')
    return
  }
  if (!selectedFeedbackIds.value.length) {
    ElMessage.warning('请先勾选要反思的反馈')
    return
  }
  router.push({
    path: `/feedback/${employeeId.value}/batch-analyze`,
    query: {
      feedback_ids: selectedFeedbackIds.value.join(','),
    },
  })
}

async function submitAnalyze() {
  if (!analyzeTargetFeedbackId.value) {
    ElMessage.warning('缺少反馈 ID，无法反思')
    return
  }
  if (reflectionForm.model_name && !String(reflectionForm.provider_id || '').trim()) {
    ElMessage.warning('选择反思模型时必须同时选择供应商')
    return
  }
  analyzeSubmitting.value = true
  try {
    await api.post(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs/${analyzeTargetFeedbackId.value}/analyze`, {
      provider_id: reflectionForm.provider_id || undefined,
      model_name: reflectionForm.model_name || undefined,
      temperature: Number(reflectionForm.temperature),
    })
    ElMessage.success('已完成反思并生成候选')
    showAnalyzeDialog.value = false
    analyzeTargetFeedbackId.value = ''
    fetchBugs()
    fetchSummary()
  } catch (e) {
    ElMessage.error(e.detail || '反思失败')
  } finally {
    analyzeSubmitting.value = false
  }
}

function openDetail(feedbackId) {
  router.push(`/feedback/${employeeId.value}/${feedbackId}`)
}

function onBugSelectionChange(rows) {
  selectedFeedbackIds.value = (rows || []).map((item) => String(item.id || '')).filter(Boolean)
}

async function deleteSingleBug(row) {
  const feedbackId = String(row?.id || '').trim()
  if (!feedbackId) return
  await ElMessageBox.confirm(`确认删除反馈工单 ${feedbackId}？`, '删除确认', { type: 'warning' })
  try {
    await api.delete(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs/${feedbackId}`, {
      params: { employee_id: employeeId.value },
    })
    ElMessage.success('删除成功')
    await runQuery()
  } catch (e) {
    ElMessage.error(e.detail || '删除失败')
  }
}

async function deleteSelectedBugs() {
  if (!selectedFeedbackIds.value.length) {
    ElMessage.warning('请先勾选要删除的反馈')
    return
  }
  await ElMessageBox.confirm(`确认批量删除 ${selectedFeedbackIds.value.length} 条反馈？`, '批量删除确认', { type: 'warning' })
  try {
    const result = await api.post(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs/batch-delete`, {
      employee_id: employeeId.value,
      feedback_ids: selectedFeedbackIds.value,
    })
    const deletedCount = Number(result.deleted_count || 0)
    const skippedCount = Number((result.skipped_ids || []).length || 0)
    const missingCount = Number((result.missing_ids || []).length || 0)
    if (deletedCount > 0) {
      ElMessage.success(`批量删除完成：成功 ${deletedCount} 条`)
    } else {
      ElMessage.warning('未删除任何反馈')
    }
    if (skippedCount > 0 || missingCount > 0) {
      ElMessage.warning(`跳过 ${skippedCount} 条，缺失 ${missingCount} 条`)
    }
    await runQuery()
  } catch (e) {
    ElMessage.error(e.detail || '批量删除失败')
  }
}

function openManualUpgrade(row) {
  manualForm.category = row.category || 'general'
  manualForm.target_rule_id = ''
  manualForm.risk_level = 'medium'
  manualForm.confidence = 0.8
  manualForm.proposed_rule_content = ''
  manualForm.executable_rule_content = ''
  manualForm.feedback_ids = Array.isArray(row.feedback_ids) ? row.feedback_ids.slice(0, 20) : []
  manualForm.comment = ''
  showManualDialog.value = true
}

async function submitManualUpgrade() {
  if (feedbackDisabled.value) {
    ElMessage.warning('当前项目反馈模块已关闭')
    return
  }
  if (!manualForm.proposed_rule_content.trim()) {
    ElMessage.warning('请填写升级建议内容')
    return
  }
  if (!manualForm.feedback_ids.length) {
    ElMessage.warning('缺少关联反馈 ID')
    return
  }
  manualSubmitting.value = true
  try {
    await api.post(`/projects/${encodeURIComponent(projectId.value)}/feedback/candidates/manual`, {
      employee_id: employeeId.value,
      category: manualForm.category,
      target_rule_id: manualForm.target_rule_id,
      risk_level: manualForm.risk_level,
      confidence: manualForm.confidence,
      proposed_rule_content: manualForm.proposed_rule_content,
      executable_rule_content: manualForm.executable_rule_content,
      feedback_ids: manualForm.feedback_ids,
      comment: manualForm.comment,
    })
    ElMessage.success('手动升级候选已创建，请到反馈详情中审核/发布')
    showManualDialog.value = false
    fetchBugs()
    fetchSummary()
  } catch (e) {
    ElMessage.error(e.detail || '创建手动候选失败')
  } finally {
    manualSubmitting.value = false
  }
}

onMounted(async () => {
  await fetchProjectOptions()
  await fetchRuleOptions()
  await fetchReflectionConfig()
  await fetchProjectConfig()
  await runQuery()
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

.filter-card {
  margin-bottom: 12px;
}
.warn-alert {
  margin-bottom: 12px;
}

.summary-card {
  margin-bottom: 12px;
}

.fid-tag {
  margin-right: 8px;
  margin-bottom: 6px;
}
.ml8 {
  margin-left: 8px;
}

.project-input {
  width: 220px;
}
</style>
