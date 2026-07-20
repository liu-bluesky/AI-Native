<template>
  <el-dialog
    v-model="visible"
    title="反馈这条 AI 回复"
    width="min(720px, 94vw)"
    append-to-body
    destroy-on-close
    class="reply-bug-dialog"
  >
    <div class="reply-bug-dialog__body">
      <section class="answer-card">
        <div>
          <span>回答 ID</span>
          <el-button link type="primary" @click="openSupervision">{{ answerId }}</el-button>
        </div>
        <p>{{ answerPreview || '当前回复内容为空' }}</p>
      </section>

      <el-alert
        v-if="snapshotError"
        :title="snapshotError"
        type="warning"
        show-icon
        :closable="false"
      />
      <section v-else class="snapshot-card" v-loading="snapshotLoading">
        <div>
          <strong>执行监管证据</strong>
          <p>系统会附带脱敏后的步骤状态，不上传工具参数、密钥或完整日志。</p>
        </div>
        <el-tag :type="supervisionSnapshot.steps.length ? 'success' : 'info'">
          {{ supervisionSnapshot.steps.length ? `${supervisionSnapshot.steps.length} 个步骤` : '暂无监管步骤' }}
        </el-tag>
      </section>

      <el-form label-position="top">
        <el-form-item label="这条回复有什么问题？" required>
          <el-input
            v-model="description"
            type="textarea"
            :rows="5"
            maxlength="4000"
            show-word-limit
            placeholder="例如：回复说任务执行成功，但文件没有生成；或回答内容与实际结果不一致。"
          />
        </el-form-item>
        <el-form-item label="你期望的结果">
          <el-input
            v-model="expectedResult"
            type="textarea"
            :rows="3"
            maxlength="2000"
            placeholder="说明正确结果或希望系统如何处理。"
          />
        </el-form-item>
      </el-form>

      <section v-if="createdTicket" class="submitted-card">
        <div>
          <strong>反馈已提交</strong>
          <el-tag type="success">等待处理</el-tag>
        </div>
        <p>回答内容和脱敏后的执行监管证据已随工单提交，后续由处理人员核查并回复。</p>
        <span>反馈编号：{{ createdTicket.id }}</span>
      </section>
    </div>

    <template #footer>
      <el-button @click="visible = false">{{ createdTicket ? '关闭' : '取消' }}</el-button>
      <el-button v-if="createdTicket" @click="openMyFeedback">查看我的反馈</el-button>
      <el-button v-else type="primary" :loading="submitting" @click="submitFeedback">
        提交反馈
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import api from '@/utils/api.js'
import { openRouteInDesktop } from '@/utils/desktop-app-bridge.js'
import { createIdempotencyKey } from '@/utils/user-feedback.js'
import { getAgentSupervisionAnswer } from '@/modules/agent-supervision/services/agentSupervisionStorage.js'

const props = defineProps({
  projectId: { type: String, default: '' },
})
const route = useRoute()
const router = useRouter()
const visible = ref(false)
const snapshotLoading = ref(false)
const snapshotError = ref('')
const submitting = ref(false)
const answerId = ref('')
const assistantMessageId = ref('')
const chatSessionId = ref('')
const answerContent = ref('')
const answerPreview = ref('')
const description = ref('')
const expectedResult = ref('')
const createdTicket = ref(null)
const supervisionSnapshot = reactive({
  answer_id: '',
  status: '',
  provider_id: '',
  model_name: '',
  duration_ms: 0,
  steps: [],
})

function sanitizeSupervisionDetail(detail) {
  const raw = detail && typeof detail === 'object' ? detail : {}
  const steps = Array.isArray(raw.steps) ? raw.steps : []
  return {
    answer_id: String(raw.answer_id || answerId.value).slice(0, 160),
    status: String(raw.status || '').slice(0, 40),
    provider_id: String(raw.provider_id || '').slice(0, 120),
    model_name: String(raw.model_name || '').slice(0, 160),
    duration_ms: Number(raw.duration_ms || raw.durationMs || 0),
    steps: steps.slice(0, 120).map((step) => {
      const meta = step?.meta && typeof step.meta === 'object' ? step.meta : {}
      const permissionDecision = meta.permission_decision && typeof meta.permission_decision === 'object'
        ? meta.permission_decision
        : {}
      return {
        id: String(step?.id || '').slice(0, 120),
        type: String(step?.type || step?.kind || '').slice(0, 80),
        status: String(step?.status || step?.phase || '').slice(0, 40),
        title: String(step?.title || '').slice(0, 240),
        summary: String(step?.summary || step?.detail || '').slice(0, 1000),
        tool_name: String(step?.tool_name || meta.tool_name || '').slice(0, 160),
        duration_ms: Number(step?.duration_ms || step?.durationMs || 0),
        risk_level: String(meta.risk_level || '').slice(0, 40),
        permission_behavior: String(meta.permission_behavior || permissionDecision.behavior || '').slice(0, 40),
      }
    }),
  }
}

async function loadSupervisionSnapshot() {
  snapshotLoading.value = true
  snapshotError.value = ''
  try {
    const detail = await getAgentSupervisionAnswer(props.projectId, answerId.value)
    Object.assign(supervisionSnapshot, sanitizeSupervisionDetail(detail))
    if (!detail) snapshotError.value = '本机监管库中没有找到该回答，仍可基于回复内容提交反馈。'
  } catch (error) {
    Object.assign(supervisionSnapshot, sanitizeSupervisionDetail(null))
    snapshotError.value = error?.message || '读取本机执行监管信息失败，仍可继续提交。'
  } finally {
    snapshotLoading.value = false
  }
}

async function open(payload = {}) {
  answerId.value = String(payload.answerId || '').trim()
  assistantMessageId.value = String(payload.item?.id || '').trim()
  chatSessionId.value = String(payload.chatSessionId || payload.item?.chatSessionId || payload.item?.chat_session_id || '').trim()
  answerContent.value = String(payload.item?.content || '').trim().slice(0, 12000)
  answerPreview.value = answerContent.value.slice(0, 600)
  description.value = ''
  expectedResult.value = ''
  createdTicket.value = null
  Object.assign(supervisionSnapshot, sanitizeSupervisionDetail(null))
  visible.value = true
  await loadSupervisionSnapshot()
}

async function submitFeedback() {
  if (!description.value.trim()) {
    ElMessage.warning('请先说明这条回复有什么问题')
    return
  }
  submitting.value = true
  try {
    const data = await api.post(
      `/projects/${encodeURIComponent(props.projectId)}/user-feedback/from-answer`,
      {
        answer_id: answerId.value,
        assistant_message_id: assistantMessageId.value,
        chat_session_id: chatSessionId.value,
        answer_snapshot: answerContent.value,
        description: description.value,
        expected_result: expectedResult.value,
        supervision_snapshot: { ...supervisionSnapshot },
        context: {
          route_path: route.fullPath,
          source_entry: 'project_chat_answer',
          client_type: window.__TAURI_INTERNALS__ ? 'desktop' : 'web',
        },
      },
      { headers: { 'Idempotency-Key': createIdempotencyKey() } },
    )
    createdTicket.value = data.item || null
    ElMessage.success(`Bug 反馈已创建：${data.item?.id || ''}`)
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || '提交回复 Bug 反馈失败')
  } finally {
    submitting.value = false
  }
}

function openSupervision() {
  openRouteInDesktop(
    router,
    { path: '/ai/supervision', query: { project_id: props.projectId, answer_id: answerId.value } },
    { mode: 'new-window', appId: 'agent-supervision', title: '智能体监管' },
  )
}

function openMyFeedback() {
  openRouteInDesktop(
    router,
    { path: '/feedback', query: { mode: 'mine' } },
    { mode: 'new-window', appId: 'user-feedback', title: '我的反馈' },
  )
}

defineExpose({ open })
</script>

<style scoped>
.reply-bug-dialog__body { display: grid; gap: 16px; }
.answer-card, .snapshot-card, .submitted-card { padding: 18px; border: 1px solid #dbe4f0; border-radius: 18px; background: #f8fafc; }
.answer-card > div, .snapshot-card, .submitted-card > div { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.answer-card span { color: #64748b; font-size: 12px; }
.answer-card p, .snapshot-card p, .submitted-card p { margin: 8px 0 0; color: #475569; line-height: 1.65; white-space: pre-wrap; }
.snapshot-card { align-items: center; }
.submitted-card { border-color: #bbf7d0; background: #f0fdf4; }
.submitted-card > span { display: block; margin-top: 10px; color: #166534; font-size: 13px; font-weight: 700; }
@media (max-width: 680px) { .snapshot-card, .submitted-card > div { flex-direction: column; } }
</style>
