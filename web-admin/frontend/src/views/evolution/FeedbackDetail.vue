<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>反馈详情: {{ feedbackId }}</h3>
      <div class="toolbar-actions">
        <el-button @click="$router.back()">返回</el-button>
        <el-button type="warning" @click="openAnalyzeDialog">重新反思</el-button>
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
      </el-form>
    </el-card>

    <el-card v-if="bug" shadow="never" class="section-card">
      <template #header>反馈信息</template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item v-if="!isBatchAggregateBug" label="标题">{{ bug.title }}</el-descriptions-item>
        <el-descriptions-item v-else label="工单类型">
          <el-tag type="warning" size="small">批量汇总工单</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTag(bug.status)" size="small">{{ bug.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="员工 ID">{{ bug.employee_id }}</el-descriptions-item>
        <el-descriptions-item label="分类">{{ formatCategory(bug.category) }}</el-descriptions-item>
        <el-descriptions-item label="严重级别">
          <el-tag :type="severityTag(bug.severity)" size="small">{{ bug.severity }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="会话 ID">{{ bug.session_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="规则 ID">{{ bug.rule_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="提交人">{{ bug.reporter || '-' }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatDateTime(bug.updated_at) }}</el-descriptions-item>
      </el-descriptions>
      <template v-if="isBatchAggregateBug">
        <h4 class="section-title">来源反馈工单</h4>
        <div class="source-feedback-list">
          <el-tag
            v-for="fid in batchSourceFeedbackIds"
            :key="fid"
            class="source-feedback-tag"
            @click="goFeedbackDetail(fid)"
          >
            {{ fid }}
          </el-tag>
        </div>
      </template>
      <h4 class="section-title">问题现象</h4>
      <p class="plain-text">{{ bug.symptom }}</p>
      <h4 class="section-title">期望结果</h4>
      <p class="plain-text">{{ bug.expected }}</p>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>AI 反思结果</template>
      <el-empty v-if="!analysis" description="尚未生成反思结果" :image-size="60" />
      <template v-else>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="类型">{{ analysis.bug_type }}</el-descriptions-item>
          <el-descriptions-item label="置信度">{{ analysis.confidence }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ analysis.model_name }}</el-descriptions-item>
          <el-descriptions-item label="生成时间">{{ formatDateTime(analysis.generated_at) }}</el-descriptions-item>
        </el-descriptions>
        <h4 class="section-title">直接原因</h4>
        <p class="plain-text">{{ analysis.direct_cause }}</p>
        <h4 class="section-title">根因</h4>
        <p class="plain-text">{{ analysis.root_cause }}</p>
      </template>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>规则候选</template>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="已发布后可点击“规则详情”查看最新规则内容，或前往规则列表检索。"
        class="candidate-tip"
      />
      <el-empty v-if="!candidates.length" description="暂无候选规则" :image-size="60" />
      <el-table v-else :data="candidates" stripe>
        <el-table-column prop="id" label="ID" width="130" />
        <el-table-column prop="risk_level" label="风险" width="90" />
        <el-table-column label="分类" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ formatCategory(row.category) }}</template>
        </el-table-column>
        <el-table-column prop="confidence" label="置信度" width="90" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联反馈" width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ formatCandidateFeedbackIds(row) }}</template>
        </el-table-column>
        <el-table-column prop="target_rule_id" label="目标规则" min-width="140" show-overflow-tooltip />
        <el-table-column label="建议内容" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">{{ row.proposed_rule_content }}</template>
        </el-table-column>
        <el-table-column label="可执行规则" min-width="320" show-overflow-tooltip>
          <template #default="{ row }">{{ row.executable_rule_content || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="360" fixed="right" class-name="table-action-column">
          <template #default="{ row }">
            <el-button
              v-for="action in getPrimaryCandidateActions(row)"
              :key="`${row.id}-${action.key}`"
              text
              :type="action.type"
              @click="handleCandidateAction(row, action.key)"
            >
              {{ action.label }}
            </el-button>
            <el-dropdown
              v-if="getOverflowCandidateActions(row).length"
              trigger="click"
              @command="(actionKey) => handleCandidateAction(row, actionKey)"
            >
              <el-button text type="primary" size="small">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="action in getOverflowCandidateActions(row)"
                    :key="`${row.id}-${action.key}`"
                    :command="action.key"
                  >
                    {{ action.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>审核日志</template>
      <el-empty v-if="!reviews.length" description="暂无审核日志" :image-size="60" />
      <el-table v-else :data="reviews" stripe>
        <el-table-column label="时间" width="220">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="reviewer" label="审核人" width="120" />
        <el-table-column prop="action" label="动作" width="120" />
        <el-table-column prop="comment" label="备注" min-width="220" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-dialog v-model="showReviewDialog" title="候选审核" width="620px">
      <el-form :model="reviewForm" label-width="110px">
        <el-form-item label="动作">
          <el-tag>{{ reviewForm.action }}</el-tag>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="reviewForm.comment" type="textarea" :rows="3" placeholder="可选" />
        </el-form-item>
        <el-form-item label="编辑内容" v-if="reviewForm.action === 'edit'">
          <el-input
            v-model="reviewForm.edited_content"
            type="textarea"
            :rows="8"
            placeholder="请输入编辑后的规则内容"
          />
        </el-form-item>
        <el-form-item label="可执行规则" v-if="reviewForm.action === 'edit'">
          <el-input
            v-model="reviewForm.edited_executable_content"
            type="textarea"
            :rows="8"
            placeholder="可选：编辑可执行规则内容"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showReviewDialog = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="submitReview">确认</el-button>
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
              :key="`detail-dlg-provider-${item.id}`"
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
              :key="`detail-dlg-model-${item.provider_id}-${item.model_name}`"
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
        <el-button type="primary" :loading="analyzeSubmitting" @click="runAnalyze">开始反思</el-button>
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
const actionLoading = ref(false)
const showReviewDialog = ref(false)
const showAnalyzeDialog = ref(false)
const analyzeSubmitting = ref(false)

const feedbackId = computed(() => route.params.feedbackId)
const employeeId = computed(() => route.params.id)
const projectId = ref(localStorage.getItem('project_id') || 'default')
const projectOptions = ref([])

const bug = ref(null)
const analysis = ref(null)
const candidates = ref([])
const reviews = ref([])
const reflectionProviders = ref([])
const reflectionOptions = ref([])
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

const reviewForm = reactive({
  candidate_id: '',
  action: 'approve',
  comment: '',
  edited_content: '',
  edited_executable_content: '',
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
const isBatchAggregateBug = computed(() => Boolean(bug.value?.source_context?.batch_mode))
const batchSourceFeedbackIds = computed(() => {
  const raw = bug.value?.source_context?.batch_feedback_ids
  if (!Array.isArray(raw)) return []
  return raw.map((item) => String(item || '').trim()).filter(Boolean)
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
  fetchReflectionConfig()
  fetchDetail()
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
    approved: 'success',
    rejected: 'danger',
    published: 'success',
    rolled_back: 'info',
    closed: 'success',
    analyze_failed: 'danger',
  }[status] || 'info'
}

function canReview(candidate) {
  return String(candidate?.status || '').trim().toLowerCase() === 'pending'
}

function getCandidateActions(candidate) {
  const actions = []
  if (canReview(candidate)) {
    actions.push({ key: 'approve', label: '通过', type: 'success' })
    actions.push({ key: 'edit', label: '编辑后通过', type: 'warning' })
    actions.push({ key: 'reject', label: '拒绝', type: 'danger' })
  }
  if (candidate.status === 'approved') {
    actions.push({ key: 'publish', label: '发布', type: 'primary' })
  }
  if (candidate.status === 'published') {
    actions.push({ key: 'rollback', label: '回滚' })
  }
  if (candidate.target_rule_id) {
    actions.push({ key: 'rule-detail', label: '规则详情', type: 'info' })
  }
  return actions
}

function getPrimaryCandidateActions(candidate) {
  return getCandidateActions(candidate).slice(0, 3)
}

function getOverflowCandidateActions(candidate) {
  return getCandidateActions(candidate).slice(3)
}

function handleCandidateAction(candidate, actionKey) {
  switch (actionKey) {
    case 'approve':
    case 'edit':
    case 'reject':
      openReview(candidate, actionKey)
      break
    case 'publish':
      void publishCandidate(candidate)
      break
    case 'rollback':
      void rollbackCandidate(candidate)
      break
    case 'rule-detail':
      goRuleDetail(candidate.target_rule_id)
      break
    default:
      break
  }
}

function formatCandidateFeedbackIds(candidate) {
  const sourceIds = Array.isArray(candidate?.source_feedback_ids) ? candidate.source_feedback_ids : []
  if (sourceIds.length) return sourceIds.join(', ')
  const ids = Array.isArray(candidate?.feedback_ids) ? candidate.feedback_ids : []
  return (ids.length ? ids : [candidate?.feedback_id]).filter(Boolean).join(', ')
}

function goRuleDetail(ruleId) {
  const id = String(ruleId || '').trim()
  if (!id) return
  router.push(`/rules/${encodeURIComponent(id)}`)
}

function goFeedbackDetail(id) {
  const value = String(id || '').trim()
  if (!value) return
  router.push(`/feedback/${employeeId.value}/${value}`)
}

async function fetchDetail() {
  loading.value = true
  try {
    const data = await api.get(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs/${feedbackId.value}`)
    bug.value = data.bug || null
    analysis.value = data.analysis || null
    candidates.value = data.candidates || []
    reviews.value = data.reviews || []
  } catch (e) {
    ElMessage.error(e.detail || '加载反馈详情失败')
  } finally {
    loading.value = false
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
  if (!String(employeeId.value || '').trim()) return
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
  if (!String(employeeId.value || '').trim()) {
    ElMessage.warning('缺少员工 ID，无法保存反思配置')
    return
  }
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

function openAnalyzeDialog() {
  showAnalyzeDialog.value = true
}

async function runAnalyze() {
  if (reflectionForm.model_name && !String(reflectionForm.provider_id || '').trim()) {
    ElMessage.warning('选择反思模型时必须同时选择供应商')
    return
  }
  analyzeSubmitting.value = true
  try {
    await api.post(`/projects/${encodeURIComponent(projectId.value)}/feedback/bugs/${feedbackId.value}/analyze`, {
      provider_id: reflectionForm.provider_id || undefined,
      model_name: reflectionForm.model_name || undefined,
      temperature: Number(reflectionForm.temperature),
    })
    ElMessage.success('反思完成')
    showAnalyzeDialog.value = false
    fetchDetail()
  } catch (e) {
    ElMessage.error(e.detail || '反思失败')
  } finally {
    analyzeSubmitting.value = false
  }
}

function openReview(candidate, action) {
  reviewForm.candidate_id = candidate.id
  reviewForm.action = action
  reviewForm.comment = ''
  reviewForm.edited_content = action === 'edit' ? candidate.proposed_rule_content || '' : ''
  reviewForm.edited_executable_content = action === 'edit' ? candidate.executable_rule_content || '' : ''
  showReviewDialog.value = true
}

async function submitReview() {
  if (reviewForm.action === 'edit' && !reviewForm.edited_content.trim()) {
    ElMessage.warning('请填写编辑内容')
    return
  }
  actionLoading.value = true
  try {
    await api.post(
      `/projects/${encodeURIComponent(projectId.value)}/feedback/candidates/${reviewForm.candidate_id}/review`,
      {
        reviewed_by: localStorage.getItem('username') || 'admin',
        action: reviewForm.action,
        comment: reviewForm.comment,
        edited_content: reviewForm.edited_content,
        edited_executable_content: reviewForm.edited_executable_content,
      },
    )
    ElMessage.success('审核已提交')
    showReviewDialog.value = false
    fetchDetail()
  } catch (e) {
    ElMessage.error(e.detail || '审核失败')
  } finally {
    actionLoading.value = false
  }
}

async function publishCandidate(candidate) {
  await ElMessageBox.confirm('确认发布该候选规则？', '发布确认')
  try {
    await api.post(
      `/projects/${encodeURIComponent(projectId.value)}/feedback/candidates/${candidate.id}/publish`,
      {
        published_by: localStorage.getItem('username') || 'admin',
      },
    )
    ElMessage.success(candidate?.target_rule_id ? '发布成功，可点“规则详情”查看' : '发布成功，可去规则列表查看')
    fetchDetail()
  } catch (e) {
    ElMessage.error(e.detail || '发布失败')
  }
}

async function rollbackCandidate(candidate) {
  await ElMessageBox.confirm('确认回滚该候选规则？', '回滚确认')
  try {
    await api.post(
      `/projects/${encodeURIComponent(projectId.value)}/feedback/candidates/${candidate.id}/rollback`,
      {
        rolled_back_by: localStorage.getItem('username') || 'admin',
      },
    )
    ElMessage.success('回滚成功')
    fetchDetail()
  } catch (e) {
    ElMessage.error(e.detail || '回滚失败')
  }
}

onMounted(async () => {
  await fetchProjectOptions()
  fetchReflectionConfig()
  fetchDetail()
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

.candidate-tip {
  margin-bottom: 10px;
}

.section-title {
  margin: 12px 0 8px;
}

.plain-text {
  white-space: pre-wrap;
  color: var(--color-text-secondary);
  margin: 0;
}

.source-feedback-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.source-feedback-tag {
  cursor: pointer;
}
</style>
