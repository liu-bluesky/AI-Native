<template>
  <div class="chat-layout" v-loading="loading">
    <!-- Sidebar: Settings -->
    <div class="chat-sidebar">
      <div class="sidebar-header">
        <h2>AI 对话中心</h2>
        <el-tag :type="wsStatusType" size="small" effect="light">{{ wsStatusText }}</el-tag>
      </div>

      <el-form label-position="top" class="settings-form" size="default">
        <el-form-item label="选择项目">
          <el-select v-model="selectedProjectId" filterable placeholder="请选择项目" class="full-width">
            <el-option v-for="item in projects" :key="item.id" :label="`${item.name}`" :value="item.id">
              <span style="float: left">{{ item.name }}</span>
              <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px">{{ item.id }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="执行员工">
          <el-select v-model="selectedEmployeeId" filterable clearable placeholder="项目默认" class="full-width">
            <el-option
              v-for="item in projectEmployees"
              :key="item.id"
              :label="`${item.name || item.id}`"
              :value="item.id"
            >
              <div style="display: flex; flex-direction: column; gap: 4px; padding: 4px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="font-weight: 500;">{{ item.name || item.id }}</span>
                  <el-tag size="small" :type="item.role === 'admin' ? 'danger' : 'info'">{{ item.role || 'member' }}</el-tag>
                </div>
                <div v-if="item.skill_names && item.skill_names.length" style="font-size: 12px; color: var(--el-text-color-secondary);">
                  技能: {{ item.skill_names.join(', ') }}
                </div>
                <div v-if="item.rule_domains && item.rule_domains.length" style="font-size: 12px; color: var(--el-text-color-secondary);">
                  规则域: {{ item.rule_domains.join(', ') }}
                </div>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="模型供应商">
          <el-select v-model="selectedProviderId" filterable placeholder="默认" class="full-width" @change="handleProviderChange">
            <el-option v-for="item in providers" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型版本">
          <el-select v-model="selectedModelName" filterable allow-create default-first-option placeholder="默认" class="full-width">
            <el-option v-for="item in availableModels" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="温度 (Temperature)">
          <el-slider v-model="temperature" :min="0" :max="2" :step="0.1" show-input :show-input-controls="false" />
        </el-form-item>
      </el-form>
      
      <div class="sidebar-footer">
        <el-button plain @click="clearMessages" class="full-width" :disabled="chatLoading || !messages.length">
          <el-icon><Delete /></el-icon> 清空会话
        </el-button>
      </div>
    </div>

    <!-- Main Chat Area -->
    <div class="chat-main">
      <div class="chat-messages" ref="messagesContainer">
        <el-empty v-if="!messages.length" description="选择项目并开始你的对话吧 ✨" :image-size="120" />
        <div v-else class="message-list-inner">
          <div v-for="(item, idx) in messages" :key="idx" :class="['message-row', item.role === 'user' ? 'is-user' : 'is-ai']">
            <div class="message-avatar">
              <el-avatar :size="36" :class="item.role === 'user' ? 'avatar-user' : 'avatar-ai'">
                {{ item.role === 'user' ? 'U' : 'AI' }}
              </el-avatar>
            </div>
            <div class="message-content-wrapper">
              <div class="message-meta">
                <span class="role-name">{{ item.role === 'user' ? 'You' : 'Assistant' }}</span>
                <span v-if="item.time || item.created_at" class="message-time">{{ item.time || item.created_at }}</span>
              </div>
              <div class="message-bubble">
                <div class="message-text" v-html="formatContent(item.content) || (chatLoading && idx === messages.length - 1 ? '思考中...' : '')"></div>
                <!-- Images -->
                <div v-if="extractImages(item).length" class="message-images">
                  <el-image
                    v-for="(img, imageIndex) in extractImages(item)"
                    :key="imageIndex"
                    :src="img"
                    class="preview-image"
                    fit="cover"
                    :preview-src-list="extractImages(item)"
                    :initial-index="imageIndex"
                    preview-teleported
                  />
                </div>
                <div v-if="extractAttachments(item).length" class="message-attachments">
                  <div v-for="(attachment, attachmentIndex) in extractAttachments(item)" :key="`att-${idx}-${attachmentIndex}`" class="attachment-item">
                    <el-tag size="small" :type="attachmentTagType(attachment.kind)" effect="plain">
                      {{ attachmentTypeLabel(attachment) }}
                    </el-tag>
                    <span class="attachment-name">{{ attachment.name }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Composer Area -->
      <div class="chat-composer">
        <div class="chat-input-wrapper" :class="{ 'is-focused': inputFocused, 'is-dragover': isDragging }" @dragover.prevent="handleDragOver" @dragleave.prevent="handleDragLeave" @drop.prevent="handleDrop">
          <div v-if="uploadFiles.length > 0" class="upload-preview-area">
            <div v-for="(file, idx) in uploadFiles" :key="idx" class="preview-item">
              <img v-if="file.url" :src="file.url" class="preview-img" />
              <div v-else class="preview-doc">
                <el-icon :size="24"><Document /></el-icon>
                <span class="doc-name">{{ file.name }}</span>
                <span class="doc-type">{{ formatFileType(file.name) }}</span>
              </div>
              <div class="remove-mask" @click="removeFile(idx)">
                <el-icon><Delete /></el-icon>
              </div>
            </div>
          </div>
          
          <el-input
            v-model="draftText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 6 }"
            placeholder="输入你的问题，按 Enter 发送，Shift + Enter 换行。支持粘贴图片。"
            resize="none"
            :disabled="chatLoading"
            @keydown.enter.exact.prevent="doSend"
            @focus="inputFocused = true"
            @blur="inputFocused = false"
            @paste="handlePaste"
            class="chat-textarea"
          />
          
          <div class="input-footer">
            <div class="footer-left">
              <el-upload
                action="#"
                :auto-upload="false"
                :show-file-list="false"
                accept="image/*"
                :multiple="true"
                :on-change="handleFileChange"
                :disabled="chatLoading"
              >
                <el-tooltip content="添加图片" placement="top">
                  <el-button text circle><el-icon><Picture /></el-icon></el-button>
                </el-tooltip>
              </el-upload>
              <el-upload
                action="#"
                :auto-upload="false"
                :show-file-list="false"
                accept=".wps,.doc,.docx,.pdf,.txt,.csv,.xlsx,.xls"
                :multiple="true"
                :on-change="handleFileChange"
                :disabled="chatLoading"
              >
                <el-tooltip content="添加文档" placement="top">
                  <el-button text circle><el-icon><Document /></el-icon></el-button>
                </el-tooltip>
              </el-upload>
            </div>
            <div class="footer-right">
              <span class="hint-text">按 Enter 发送</span>
              <el-tooltip v-if="chatLoading" content="暂停当前回答" placement="top">
                <el-button class="pause-generation-button" type="danger" plain @click="stopGeneration">
                  <el-icon><VideoPause /></el-icon>
                  <span>暂停</span>
                </el-button>
              </el-tooltip>
              <el-button v-else type="primary" :disabled="!canSend" @click="doSend" circle>
                <el-icon><Promotion /></el-icon>
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'
import { createProjectChatWsClient } from '@/utils/ws-chat.js'
import { Delete, Picture, Promotion, Document, VideoPause } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { extractTextFromFile } from '@/utils/file-extractor.js'

// 配置 marked 以支持代码高亮和换行
marked.setOptions({
  breaks: true,
  gfm: true,
})

const route = useRoute()

const loading = ref(false)
const chatLoading = ref(false)

const projects = ref([])
const providers = ref([])
const projectEmployees = ref([])
const messages = ref([])

const selectedProjectId = ref('')
const selectedEmployeeId = ref('')
const selectedProviderId = ref('')
const selectedModelName = ref('')
const defaultProviderId = ref('')
const defaultModelName = ref('')
const temperature = ref(0.2)

const wsConnected = ref(false)
const wsClient = ref(null)
const wsProjectId = ref('')
const pendingRequests = new Map()

const maxUploadLimit = ref(6)
const chatMaxTokens = ref(512)

const wsStatusText = computed(() => (wsConnected.value ? '已连接' : '未连接'))
const wsStatusType = computed(() => (wsConnected.value ? 'success' : 'info'))

const availableModels = computed(() => {
  const selected = (providers.value || []).find((item) => item.id === selectedProviderId.value)
  return Array.isArray(selected?.models) ? selected.models : []
})

const messagesContainer = ref(null)
const draftText = ref('')
const uploadFiles = ref([])
const inputFocused = ref(false)
const isDragging = ref(false)
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'heic', 'heif'])
const MAX_DOC_CHARS_PER_FILE = 1200
const MAX_DOC_TOTAL_CHARS = 3000

const canSend = computed(() => {
  if (chatLoading.value) return false
  if (String(draftText.value || '').trim()) return true
  return uploadFiles.value.length > 0
})

function formatContent(text) {
  if (!text) return ''
  try {
    return marked.parse(text)
  } catch (e) {
    return text
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function extractImages(message) {
  if (!message || !Array.isArray(message.images)) return []
  return message.images.map(item => String(item || '').trim()).filter(Boolean)
}

function fileExtension(name) {
  const text = String(name || '').trim()
  const idx = text.lastIndexOf('.')
  if (idx < 0 || idx === text.length - 1) return ''
  return text.slice(idx + 1).toLowerCase()
}

function isImageFile(file) {
  const mime = String(file?.type || '').toLowerCase()
  if (mime.startsWith('image/')) return true
  return IMAGE_EXTENSIONS.has(fileExtension(file?.name || ''))
}

function formatFileType(name) {
  const ext = fileExtension(name)
  return ext ? ext.toUpperCase() : 'FILE'
}

function clipText(text, maxChars) {
  const value = String(text || '').trim()
  if (!value) return ''
  if (value.length <= maxChars) return value
  return `${value.slice(0, maxChars)}\n（内容已截断）`
}

function normalizeAttachment(name) {
  const normalizedName = String(name || '').trim()
  if (!normalizedName) return null
  const ext = fileExtension(normalizedName)
  const kind = IMAGE_EXTENSIONS.has(ext) ? 'image' : 'document'
  return {
    name: normalizedName,
    kind,
    ext,
  }
}

function extractAttachments(message) {
  const values = Array.isArray(message?.attachments) ? message.attachments : []
  return values
    .map(normalizeAttachment)
    .filter(Boolean)
}

function attachmentTagType(kind) {
  return kind === 'image' ? 'success' : 'info'
}

function attachmentTypeLabel(attachment) {
  const ext = String(attachment?.ext || '').trim().toUpperCase()
  if (ext) return ext
  return attachment?.kind === 'image' ? '图片' : '文档'
}

function handleFileChange(file) {
  const raw = file.raw
  if (!raw) return
  const isImage = isImageFile(raw)
  const isDocument = String(raw.name || '').match(/\.(wps|doc|docx|pdf|txt|csv|xlsx|xls)$/i)
  if (!isImage && !isDocument) {
    ElMessage.error('仅支持图片或办公文档(wps/doc/pdf等)')
    return
  }
  const sizeMB = raw.size / (1024 * 1024)
  if (sizeMB > 15) {
    ElMessage.error(`文件超过 15MB`)
    return
  }
  if (uploadFiles.value.length >= maxUploadLimit.value) {
    ElMessage.warning(`最多只能上传 ${maxUploadLimit.value} 个文件`)
    return
  }
  
  if (isImage) {
    file.url = URL.createObjectURL(raw)
    file.kind = 'image'
  } else {
    file.url = ''
    file.kind = 'document'
  }
  uploadFiles.value.push(file)
}

function handleDragOver() {
  isDragging.value = true
}

function handleDragLeave() {
  isDragging.value = false
}

function handleDrop(e) {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return
  for (let i = 0; i < files.length; i++) {
    handleFileChange({ raw: files[i], name: files[i].name })
  }
}

function handlePaste(event) {
  if (!event.clipboardData || !event.clipboardData.items) return
  
  const items = event.clipboardData.items
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.type.indexOf('image') !== -1 || item.type.indexOf('text/plain') === -1) {
      const file = item.getAsFile()
      if (file) {
        event.preventDefault()
        handleFileChange({ raw: file, name: file.name || 'clipboard_file' })
      }
    }
  }
}

function removeFile(index) {
  uploadFiles.value.splice(index, 1)
}

function resetDraft() {
  draftText.value = ''
  uploadFiles.value = []
}

function nowText() {
  return new Date().toLocaleString()
}

function toHistoryRows(sourceMessages) {
  return (sourceMessages || [])
    .map((item) => ({
      role: String(item.role || '').trim().toLowerCase(),
      content: String(item.content || '').trim(),
    }))
    .filter((item) => (item.role === 'user' || item.role === 'assistant') && item.content)
    .slice(-20)
}

async function fetchSystemConfig() {
  try {
    const data = await api.get('/system-config')
    if (data?.config?.chat_upload_max_limit) {
      maxUploadLimit.value = Number(data.config.chat_upload_max_limit)
    }
    if (data?.config?.chat_max_tokens) {
      chatMaxTokens.value = Number(data.config.chat_max_tokens)
    }
  } catch (err) {
    console.error('加载系统配置失败', err)
  }
}

async function fetchProjects() {
  const data = await api.get('/projects')
  projects.value = data.projects || []
}

function syncProjectFromRoute() {
  const routeProjectId = String(route.query.project_id || '').trim()
  const cachedProjectId = String(localStorage.getItem('project_id') || '').trim()
  const initialProjectId = routeProjectId || cachedProjectId
  const exists = (projects.value || []).some((item) => item.id === initialProjectId)
  selectedProjectId.value = exists ? initialProjectId : String(projects.value[0]?.id || '')
}

async function fetchProvidersByProject(projectId) {
  if (!projectId) {
    providers.value = []
    projectEmployees.value = []
    selectedEmployeeId.value = ''
    selectedProviderId.value = ''
    selectedModelName.value = ''
    return
  }
  const data = await api.get(`/projects/${encodeURIComponent(projectId)}/chat/providers`)
  providers.value = data.providers || []
  projectEmployees.value = data.employees || []
  selectedEmployeeId.value = String(data.default_employee_id || projectEmployees.value[0]?.id || '')
  defaultProviderId.value = String(data.default_provider_id || '')
  defaultModelName.value = String(data.default_model_name || '')
  selectedProviderId.value = defaultProviderId.value
  selectedModelName.value = defaultModelName.value
}

function mapHistoryMessage(item) {
  const attachments = Array.isArray(item?.attachments) ? item.attachments : []
  const images = Array.isArray(item?.images) ? item.images : []
  return {
    id: String(item?.id || ''),
    role: String(item?.role || 'assistant'),
    content: String(item?.content || ''),
    images: images,
    attachments,
    time: String(item?.created_at || ''),
  }
}

async function fetchChatHistory(projectId) {
  if (!projectId) {
    messages.value = []
    return
  }
  try {
    const data = await api.get(`/projects/${encodeURIComponent(projectId)}/chat/history`, {
      params: { limit: 200 },
    })
    messages.value = (data.messages || []).map(mapHistoryMessage)
    scrollToBottom()
  } catch (err) {
    messages.value = []
    ElMessage.error(err?.detail || err?.message || '加载聊天记录失败')
  }
}

function handleProviderChange() {
  const selected = (providers.value || []).find((item) => item.id === selectedProviderId.value)
  const modelList = Array.isArray(selected?.models) ? selected.models : []
  if (!selectedModelName.value || !modelList.includes(selectedModelName.value)) {
    selectedModelName.value = String(selected?.default_model || modelList[0] || '')
  }
}

async function clearMessages() {
  if (!selectedProjectId.value) {
    messages.value = []
    return
  }
  try {
    await api.delete(`/projects/${encodeURIComponent(selectedProjectId.value)}/chat/history`)
    messages.value = []
    ElMessage.success('聊天记录已清空')
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '清空聊天记录失败')
  }
}

function isIntentOnlyReply(text) {
  const value = String(text || '').trim()
  if (!value || value.length > 180) return false
  return /^(我先|我会先|我去|我来|让我先|先帮你|正在|稍等)/.test(value)
    || /(查一下|查询一下|先查|先检索|马上返回|稍后返回)/.test(value)
}

function handleSocketMessage(eventData) {
  const eventType = String(eventData?.type || '').trim().toLowerCase()
  const requestId = String(eventData?.request_id || '').trim()
  if (eventType === 'ready' || eventType === 'pong' || eventType === 'start') {
    return
  }
  if (!requestId) {
    if (eventType === 'error') {
      ElMessage.error(String(eventData?.message || '对话异常'))
    }
    return
  }
  const pending = pendingRequests.get(requestId)
  if (!pending) return
  const row = messages.value[pending.assistantIndex]
  if (!row) {
    pendingRequests.delete(requestId)
    pending.reject(new Error('消息上下文已失效'))
    return
  }
  if (eventType === 'delta') {
    row.content = `${row.content || ''}${String(eventData?.content || '')}`
    scrollToBottom()
    return
  }
  if (eventType === 'tool_start') {
    const toolName = String(eventData?.tool_name || '工具')
    row.content = `${row.content || ''}\n\n> ⏳ 正在调用工具：\`${toolName}\``
    scrollToBottom()
    return
  }
  if (eventType === 'tool_result') {
    const toolName = String(eventData?.tool_name || '工具')
    row.content = `${row.content || ''}\n\n> ✅ 工具调用完成：\`${toolName}\``
    scrollToBottom()
    return
  }
  if (eventType === 'done') {
    const doneContent = String(eventData?.content || '').trim()
    const currentContent = String(row.content || '').trim()
    if (!currentContent) {
      row.content = doneContent
    } else if (doneContent && currentContent !== doneContent) {
      if (
        isIntentOnlyReply(currentContent)
        || /达到最大处理轮次|已停止生成/.test(doneContent)
      ) {
        row.content = doneContent
      }
    }
    pendingRequests.delete(requestId)
    pending.resolve(row.content || '')
    scrollToBottom()
    return
  }
  if (eventType === 'error') {
    const message = String(eventData?.message || '未知错误')
    row.content = `对话失败：${message}`
    pendingRequests.delete(requestId)
    pending.reject(new Error(message))
    scrollToBottom()
  }
}

function rejectPendingRequests(reason) {
  const message = String(reason || '连接已断开').trim()
  const items = Array.from(pendingRequests.entries())
  for (const [requestId, pending] of items) {
    const row = messages.value[pending.assistantIndex]
    if (row && !String(row.content || '').trim()) {
      row.content = `请求失败：${message}`
    }
    pending.reject(new Error(message))
    pendingRequests.delete(requestId)
  }
}

function disconnectWs(reason = '') {
  if (wsClient.value) {
    wsClient.value.close(1000, reason || 'client close')
  }
  wsClient.value = null
  wsConnected.value = false
  wsProjectId.value = ''
}

async function ensureWsClient(projectId) {
  const normalizedProjectId = String(projectId || '').trim()
  if (!normalizedProjectId) {
    throw new Error('缺少项目 ID')
  }
  if (
    wsClient.value
    && wsProjectId.value === normalizedProjectId
    && wsClient.value.isOpen()
  ) {
    return wsClient.value
  }
  disconnectWs('switch project')

  const token = String(localStorage.getItem('token') || '').trim()
  if (!token) {
    throw new Error('登录状态失效，请重新登录')
  }
  wsProjectId.value = normalizedProjectId
  const client = createProjectChatWsClient({
    projectId: normalizedProjectId,
    token,
    onOpen: () => {
      wsConnected.value = true
    },
    onMessage: handleSocketMessage,
    onError: () => {
      wsConnected.value = false
    },
    onClose: (event) => {
      wsConnected.value = false
      wsClient.value = null
      const code = Number(event?.code || 1000)
      if (code === 1000) return
      const reason = String(event?.reason || '').trim() || `连接关闭(${code})`
      rejectPendingRequests(reason)
      ElMessage.warning(`WebSocket 断开：${reason}`)
    },
  })
  wsClient.value = client
  await client.ready
  wsConnected.value = true
  return client
}

function getActiveRequestId() {
  const entries = Array.from(pendingRequests.entries())
  if (entries.length > 0) {
    return entries[entries.length - 1][0]
  }
  return null
}

function stopGeneration() {
  const currentRequestId = getActiveRequestId()
  if (currentRequestId && wsClient.value && wsClient.value.isOpen()) {
    wsClient.value.send({ type: 'cancel', request_id: currentRequestId })
    ElMessage.info('已发送停止指令')
    return
  }
  ElMessage.warning('当前没有可暂停的生成任务')
}

async function doSend() {
  if (!canSend.value) return
  
  if (!selectedProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }

  const text = String(draftText.value || '').trim()
  const files = uploadFiles.value.map(item => item.raw).filter(Boolean)
  const imageFiles = files.filter((file) => isImageFile(file))
  
  const historyRows = toHistoryRows(messages.value)
  const imageUrls = uploadFiles.value
    .filter((item) => item.kind === 'image')
    .map((item) => item.url)
    .filter(Boolean)
  const attachmentNames = files.map((file) => String(file?.name || '').trim()).filter(Boolean)

  const readAsBase64 = (f) => new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(f)
  })
  const base64Images = await Promise.all(imageFiles.map(readAsBase64))
  
  let docsText = ''
  const docFiles = files.filter((file) => !isImageFile(file))
  if (docFiles.length > 0) {
    for (const file of docFiles) {
      const content = await extractTextFromFile(file)
      if (content) {
        const clipped = clipText(content, MAX_DOC_CHARS_PER_FILE)
        docsText += `\n\n【文档附件：${file.name}】\n${clipped}`
      }
      if (docsText.length >= MAX_DOC_TOTAL_CHARS) {
        docsText = clipText(docsText, MAX_DOC_TOTAL_CHARS)
        break
      }
    }
  }

  let userPrompt = text || (attachmentNames.length ? `我上传了附件：${attachmentNames.join('、')}。请先给我处理建议。` : '')
  if (docsText) {
    userPrompt += `${docsText}\n\n请先给简要结论：最多 5 条，每条不超过 40 字。`
  }

  messages.value.push({
    role: 'user',
    content: text || '（发送了附件）',
    images: imageUrls,
    attachments: attachmentNames,
    time: nowText(),
  })
  messages.value.push({
    role: 'assistant',
    content: '',
    time: nowText(),
  })
  
  const assistantIndex = messages.value.length - 1
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  
  chatLoading.value = true
  resetDraft()
  scrollToBottom()

  try {
    const client = await ensureWsClient(selectedProjectId.value)
    const donePromise = new Promise((resolve, reject) => {
      pendingRequests.set(requestId, { resolve, reject, assistantIndex })
    })
    client.send({
      request_id: requestId,
      message: userPrompt,
      employee_id: selectedEmployeeId.value || undefined,
      history: historyRows,
      provider_id: selectedProviderId.value || undefined,
      model_name: selectedModelName.value || undefined,
      temperature: Number(temperature.value),
      max_tokens: Number(chatMaxTokens.value || 512),
      attachment_names: attachmentNames,
      images: base64Images,
    })
    await donePromise
    if (!String(messages.value[assistantIndex]?.content || '').trim()) {
      messages.value[assistantIndex].content = '模型未返回内容。'
    }
  } catch (err) {
    messages.value[assistantIndex].content = `请求失败：${err?.message || '未知错误'}`
    ElMessage.error(err?.message || '对话失败')
  } finally {
    pendingRequests.delete(requestId)
    chatLoading.value = false
    scrollToBottom()
  }
}

watch(selectedProjectId, async (value) => {
  const projectId = String(value || '').trim()
  if (!projectId) {
    rejectPendingRequests('已切换项目，当前请求取消')
    disconnectWs('switch project')
    providers.value = []
    projectEmployees.value = []
    selectedEmployeeId.value = ''
    selectedProviderId.value = ''
    selectedModelName.value = ''
    return
  }
  localStorage.setItem('project_id', projectId)
  rejectPendingRequests('已切换项目，当前请求取消')
  disconnectWs('switch project')
  try {
    await fetchProvidersByProject(projectId)
    await fetchChatHistory(projectId)
  } catch (err) {
    providers.value = []
    projectEmployees.value = []
    selectedEmployeeId.value = ''
    selectedProviderId.value = ''
    selectedModelName.value = ''
    messages.value = []
    ElMessage.error(err?.detail || err?.message || '加载模型供应商失败')
  }
})

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      fetchSystemConfig(),
      fetchProjects(),
    ])
    syncProjectFromRoute()
    if (selectedProjectId.value) {
      await fetchProvidersByProject(selectedProjectId.value)
      await fetchChatHistory(selectedProjectId.value)
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '初始化失败')
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  rejectPendingRequests('页面已关闭')
  disconnectWs('page closed')
})
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: calc(100vh - 120px);
  min-height: 600px;
  background: var(--el-bg-color);
  border-radius: var(--el-border-radius-large);
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0,0,0,0.05);
  border: 1px solid var(--el-border-color-light);
}

.chat-sidebar {
  width: 280px;
  background: var(--el-bg-color-page);
  border-right: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  padding: 20px;
  box-sizing: border-box;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.sidebar-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.settings-form {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.settings-form :deep(.el-form-item__label) {
  padding-bottom: 4px;
  font-weight: 500;
}

.full-width {
  width: 100%;
}

.sidebar-footer {
  margin-top: 16px;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  position: relative;
  min-width: 0;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  scroll-behavior: smooth;
}

.message-list-inner {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 800px;
  margin: 0 auto;
}

.message-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.message-row.is-user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}

.avatar-user {
  background: var(--el-color-primary);
  font-weight: bold;
}

.avatar-ai {
  background: #10a37f;
  font-weight: bold;
}

.message-content-wrapper {
  max-width: 80%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-row.is-user .message-content-wrapper {
  align-items: flex-end;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.role-name {
  font-weight: 600;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
  line-height: 1.6;
  font-size: 14px;
}

.message-text {
  word-break: break-word;
}

.message-text :deep(p) { margin-top: 0; margin-bottom: 0.8em; }
.message-text :deep(p:last-child) { margin-bottom: 0; }
.message-text :deep(pre) { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 8px; overflow-x: auto; margin: 8px 0; }
.message-text :deep(code) { background: #f0f0f0; padding: 2px 4px; border-radius: 4px; font-family: monospace; }
.message-text :deep(pre code) { padding: 0; background: transparent; color: inherit; }

.message-row.is-user .message-bubble {
  background: var(--el-color-primary-light-9);
  color: var(--el-text-color-primary);
  border-bottom-right-radius: 4px;
}

.message-row.is-ai .message-bubble {
  border-bottom-left-radius: 4px;
}

.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.message-attachments {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
}

.attachment-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.attachment-name {
  font-size: 12px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-image {
  width: 140px;
  height: 140px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
}

.chat-composer {
  padding: 20px 24px;
  background: #ffffff;
  display: flex;
  justify-content: center;
}

.chat-input-wrapper {
  width: 100%;
  max-width: 800px;
  border: 1px solid var(--el-border-color);
  border-radius: 16px;
  background: var(--el-bg-color);
  transition: border-color 0.2s, box-shadow 0.2s, background-color 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
}

.chat-input-wrapper.is-focused {
  border-color: var(--el-color-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.chat-input-wrapper.is-dragover {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
  border-style: dashed;
}

.upload-preview-area {
  display: flex;
  gap: 12px;
  padding: 12px 16px 0 16px;
  flex-wrap: wrap;
}

.preview-item {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}

.preview-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-doc {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  padding: 4px;
  box-sizing: border-box;
}

.doc-name {
  font-size: 10px;
  margin-top: 2px;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
}

.doc-type {
  font-size: 9px;
  line-height: 1;
  margin-top: 2px;
  padding: 2px 4px;
  border-radius: 8px;
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
}

.remove-mask {
  position: absolute;
  top: 0;
  right: 0;
  width: 20px;
  height: 20px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-bottom-left-radius: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}

.preview-item:hover .remove-mask {
  opacity: 1;
}

.chat-textarea :deep(.el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 12px 16px;
  font-size: 14px;
  resize: none;
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hint-text {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.pause-generation-button {
  border-radius: 999px;
  padding: 8px 14px;
  font-weight: 600;
}
</style>
