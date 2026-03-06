<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    :width="width"
    destroy-on-close
    @update:model-value="handleVisibleChange"
    @close="handleClose"
  >
    <div class="chat-body">
      <div class="message-list">
        <template v-if="messages.length">
          <div
            v-for="(item, idx) in messages"
            :key="item.id || `${item.role || 'message'}-${idx}`"
            class="message-item"
            :class="`message-${String(item.role || 'assistant')}`"
          >
            <div class="message-meta">
              <el-tag size="small" :type="roleTagType(item.role)">
                {{ roleLabel(item.role) }}
              </el-tag>
              <span v-if="item.created_at || item.time" class="time-text">
                {{ item.created_at || item.time }}
              </span>
            </div>
            <div class="message-content">{{ item.content || '' }}</div>
            <div v-if="extractImages(item).length" class="message-images">
              <el-image
                v-for="(img, imageIndex) in extractImages(item)"
                :key="`img-${idx}-${imageIndex}`"
                :src="img"
                class="message-image"
                fit="cover"
                :preview-src-list="extractImages(item)"
                :initial-index="imageIndex"
                preview-teleported
              />
            </div>
          </div>
        </template>
        <el-empty v-else :description="emptyText" :image-size="56" />
      </div>

      <div class="composer">
        <el-input
          v-model="draftText"
          type="textarea"
          :rows="4"
          :maxlength="maxInputLength"
          :placeholder="placeholder"
          show-word-limit
          :disabled="loading || disabled"
        />

        <el-upload
          v-if="allowImage"
          ref="uploadRef"
          v-model:file-list="uploadFiles"
          class="upload-box"
          :auto-upload="false"
          list-type="picture"
          :accept="accept"
          :limit="maxImages"
          :on-change="handleFileChange"
          :on-exceed="handleExceed"
          :on-remove="handleFileRemove"
          :disabled="loading || disabled"
        >
          <el-button>添加图片</el-button>
          <template #tip>
            <div class="upload-tip">
              最多 {{ maxImages }} 张，单张不超过 {{ maxImageSizeMB }}MB
            </div>
          </template>
        </el-upload>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button v-if="showClear" :disabled="loading" @click="clearDraft">清空输入</el-button>
        <div class="footer-right">
          <el-button :disabled="loading" @click="handleCancel">{{ cancelText }}</el-button>
          <el-button type="primary" :loading="loading" :disabled="!canSend" @click="handleSend">
            {{ sendText }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: 'AI 对话' },
  width: { type: String, default: '760px' },
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  allowImage: { type: Boolean, default: true },
  maxImages: { type: Number, default: 6 },
  maxImageSizeMB: { type: Number, default: 5 },
  maxInputLength: { type: Number, default: 4000 },
  placeholder: { type: String, default: '输入问题，支持多行文本...' },
  accept: { type: String, default: 'image/*' },
  emptyText: { type: String, default: '暂无对话记录' },
  sendText: { type: String, default: '发送' },
  cancelText: { type: String, default: '关闭' },
  showClear: { type: Boolean, default: true },
  clearOnSend: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue', 'send', 'cancel', 'close', 'clear'])

const draftText = ref('')
const uploadFiles = ref([])
const uploadRef = ref(null)

const canSend = computed(() => {
  if (props.loading || props.disabled) return false
  if (String(draftText.value || '').trim()) return true
  if (!props.allowImage) return false
  return uploadFiles.value.length > 0
})

function roleLabel(role) {
  const value = String(role || '').toLowerCase()
  if (value === 'user') return '用户'
  if (value === 'assistant') return 'AI'
  if (value === 'system') return '系统'
  if (value === 'tool') return '工具'
  return '消息'
}

function roleTagType(role) {
  const value = String(role || '').toLowerCase()
  if (value === 'user') return 'primary'
  if (value === 'assistant') return 'success'
  if (value === 'system') return 'warning'
  return 'info'
}

function extractImages(message) {
  if (!message || !Array.isArray(message.images)) return []
  return message.images
    .map((item) => String(item || '').trim())
    .filter(Boolean)
}

function resetDraft() {
  draftText.value = ''
  uploadFiles.value = []
  uploadRef.value?.clearFiles?.()
}

function clearDraft() {
  resetDraft()
  emit('clear')
}

function handleVisibleChange(value) {
  emit('update:modelValue', value)
}

function handleClose() {
  emit('close')
}

function handleCancel() {
  emit('cancel')
  emit('update:modelValue', false)
}

function handleExceed() {
  ElMessage.warning(`最多只能上传 ${props.maxImages} 张图片`)
}

function handleFileRemove() {
  uploadFiles.value = uploadFiles.value.filter((item) => item.status !== 'fail')
}

function handleFileChange(file, files) {
  const normalized = files.filter((item) => {
    const raw = item.raw
    if (!raw) return false
    if (!String(raw.type || '').startsWith('image/')) {
      ElMessage.error('仅支持图片文件')
      return false
    }
    const sizeMB = raw.size / (1024 * 1024)
    if (sizeMB > props.maxImageSizeMB) {
      ElMessage.error(`图片 ${raw.name} 超过 ${props.maxImageSizeMB}MB`)
      return false
    }
    return true
  })
  if (normalized.length !== files.length && file?.name) {
    uploadRef.value?.clearFiles?.()
  }
  uploadFiles.value = normalized
}

function handleSend() {
  if (!canSend.value) return
  const payload = {
    text: String(draftText.value || ''),
    files: uploadFiles.value.map((item) => item.raw).filter(Boolean),
  }
  emit('send', payload)
  if (props.clearOnSend) {
    resetDraft()
  }
}
</script>

<style scoped>
.chat-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message-list {
  min-height: 220px;
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-lg);
  padding: 12px;
  background: var(--color-bg-layout);
  box-sizing: border-box;
}

.message-item {
  padding: 10px 12px;
  border-radius: var(--radius-base);
  background: var(--color-bg-container);
  border: 1px solid var(--color-border-secondary);
}

.message-item + .message-item {
  margin-top: 10px;
}

.message-user {
  border-left: 3px solid var(--color-primary-6);
}

.message-assistant {
  border-left: 3px solid var(--el-color-success);
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.time-text {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.message-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.message-image {
  width: 88px;
  height: 88px;
  border-radius: var(--radius-base);
  overflow: hidden;
  border: 1px solid var(--color-border-secondary);
}

.composer {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.upload-box {
  width: 100%;
}

.upload-tip {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-right {
  display: flex;
  gap: 8px;
}
</style>
