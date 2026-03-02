<template>
  <div v-loading="loading">
    <h3>编辑技能: {{ form.name }}</h3>
    <el-form :model="form" :rules="rules" ref="formRef" label-width="120px" class="form-wrap">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="版本">
        <el-input v-model="form.version" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="MCP 服务">
        <el-input v-model="form.mcp_service" />
        <div class="hint">仅用于分类和展示，不影响技能执行；不确定时可留空。</div>
      </el-form-item>

      <el-divider content-position="left">标签</el-divider>
      <el-form-item label="标签列表">
        <div v-for="(tag, i) in form.tags" :key="i" class="tag-row">
          <el-input v-model="form.tags[i]" size="small" />
          <el-button text type="danger" size="small" @click="form.tags.splice(i, 1)">删除</el-button>
        </div>
        <el-button text type="primary" size="small" @click="form.tags.push('')">+ 添加标签</el-button>
      </el-form-item>

      <el-divider content-position="left">服务</el-divider>
      <el-form-item label="独立 MCP 服务">
        <el-switch v-model="form.mcp_enabled" />
        <div class="hint">
          开启后，平台将为该技能提供独立的网络访问入口（HTTP / SSE），供外部客户端直接挂载使用。
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        <el-button @click="$router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'

const route = useRoute()
const router = useRouter()
const formRef = ref(null)
const loading = ref(false)
const saving = ref(false)

const form = reactive({
  name: '',
  version: '1.0.0',
  description: '',
  mcp_service: '',
  tags: [],
  mcp_enabled: false,
})

const rules = {
  name: [{ required: true, message: '请输入技能名称', trigger: 'blur' }],
}

async function fetchDetail() {
  loading.value = true
  try {
    const { skill } = await api.get(`/skills/${route.params.id}`)
    Object.assign(form, {
      name: skill.name || '',
      version: skill.version || '1.0.0',
      description: skill.description || '',
      mcp_service: skill.mcp_service || '',
      tags: [...(skill.tags || [])],
      mcp_enabled: skill.mcp_enabled || false,
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
    const payload = { ...form, tags: form.tags.filter(Boolean) }
    await api.put(`/skills/${route.params.id}`, payload)
    ElMessage.success('保存成功')
    router.push(`/skills/${route.params.id}`)
  } catch (e) {
    ElMessage.error(e.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(fetchDetail)
</script>

<style scoped>
.form-wrap {
  max-width: 600px;
}

.hint {
  margin-top: 6px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.tag-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
</style>
