<template>
  <div>
    <h3>上传技能包</h3>
    <el-form :model="form" label-width="120px" class="form-wrap">
      <el-form-item label="技能包文件">
        <el-upload
          ref="uploadRef"
          class="upload-box"
          drag
          :auto-upload="false"
          :limit="1"
          accept=".zip"
          :file-list="fileList"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :on-exceed="handleExceed"
        >
          <div class="upload-title">拖拽 ZIP 到这里，或点击选择文件</div>
          <div class="hint">仅支持 .zip，压缩包内应包含 SKILL.md 或 manifest.*，建议包含 tools/ 与 resources/。</div>
        </el-upload>
      </el-form-item>
      <el-form-item label="名称(可选)">
        <el-input v-model="form.name" placeholder="留空则使用技能包中的元数据" />
      </el-form-item>
      <el-form-item label="版本(可选)">
        <el-input v-model="form.version" placeholder="留空则读取 manifest 或默认 1.0.0" />
      </el-form-item>
      <el-form-item label="描述(可选)">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="留空则读取技能包元数据" />
      </el-form-item>
      <el-form-item label="MCP 服务(可选)">
        <el-input v-model="form.mcp_service" placeholder="例如：skills-service；留空则读取技能包元数据" />
        <div class="hint">仅用于分类和展示，不影响技能导入或执行；不确定时可留空。</div>
        <div class="mcp-example-row">
          <span class="hint">示例：</span>
          <el-tag
            v-for="svc in mcpServiceExamples"
            :key="svc"
            size="small"
            effect="plain"
            class="mcp-tag"
            @click="form.mcp_service = svc"
          >
            {{ svc }}
          </el-tag>
        </div>
      </el-form-item>

      <el-divider content-position="left">标签</el-divider>
      <el-form-item label="标签列表">
        <div v-for="(tag, i) in form.tags" :key="i" class="tag-row">
          <el-input v-model="form.tags[i]" size="small" />
          <el-button text type="danger" size="small" @click="form.tags.splice(i, 1)">删除</el-button>
        </div>
        <el-button text type="primary" size="small" @click="form.tags.push('')">+ 添加标签</el-button>
      </el-form-item>

      <ResourceShareSettings :form="form" />

      <el-divider content-position="left">服务</el-divider>
      <el-form-item label="独立 MCP 服务">
        <el-switch v-model="form.mcp_enabled" />
        <div class="hint">
          开启后，平台将为该技能提供独立的网络访问入口（HTTP / SSE），供外部客户端直接挂载使用。
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="handleCreate">导入技能</el-button>
        <el-button @click="$router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'
import ResourceShareSettings from '@/components/ResourceShareSettings.vue'

const router = useRouter()
const uploadRef = ref(null)
const loading = ref(false)
const skillFile = ref(null)
const fileList = ref([])

const mcpServiceExamples = [
  'skills-service',
  'rules-service',
  'memory-service',
  'persona-service',
  'evolution-engine',
  'sync-service',
]

const form = reactive({
  name: '',
  version: '',
  description: '',
  share_scope: 'private',
  shared_with_usernames: [],
  mcp_service: '',
  tags: [],
  mcp_enabled: false,
})

function handleFileChange(uploadFile, uploadFiles) {
  fileList.value = uploadFiles.slice(-1)
  skillFile.value = uploadFile.raw || null
}

function handleFileRemove() {
  fileList.value = []
  skillFile.value = null
}

function handleExceed() {
  ElMessage.warning('只能上传一个技能包文件')
}

async function handleCreate() {
  if (!skillFile.value) {
    ElMessage.error('请先上传技能包文件（.zip）')
    return
  }
  loading.value = true
  try {
    const payload = new FormData()
    payload.append('file', skillFile.value)
    if (form.name.trim()) payload.append('name', form.name.trim())
    if (form.version.trim()) payload.append('version', form.version.trim())
    if (form.description.trim()) payload.append('description', form.description.trim())
    payload.append('share_scope', String(form.share_scope || 'private').trim() || 'private')
    const sharedUsers = Array.isArray(form.shared_with_usernames)
      ? form.shared_with_usernames.map((item) => String(item || '').trim()).filter(Boolean)
      : []
    if (sharedUsers.length) payload.append('shared_with_usernames', sharedUsers.join(','))
    if (form.mcp_service.trim()) payload.append('mcp_service', form.mcp_service.trim())
    payload.append('mcp_enabled', form.mcp_enabled ? 'true' : '')
    const tags = form.tags.map((t) => t.trim()).filter(Boolean)
    if (tags.length) payload.append('tags', tags.join(','))
    const { skill } = await api.post('/skills/import-file', payload, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(`技能「${skill.name}」导入成功`)
    router.push('/skills')
  } catch (e) {
    ElMessage.error(e.detail || '导入失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.form-wrap {
  max-width: 700px;
}

.upload-box {
  width: 100%;
}

.upload-title {
  margin-bottom: 4px;
}

.hint {
  margin-top: 6px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.mcp-example-row {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.mcp-tag {
  cursor: pointer;
}

.tag-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
</style>
