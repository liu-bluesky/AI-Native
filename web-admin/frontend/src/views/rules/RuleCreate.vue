<template>
  <div>
    <h3>新建规则</h3>
    <el-form :model="form" :rules="rules" ref="formRef" label-width="120px" class="form-wrap">
      <el-form-item label="领域" prop="domain">
        <el-input v-model="form.domain" placeholder="如：error-handling" />
      </el-form-item>
      <el-form-item label="标题" prop="title">
        <el-input v-model="form.title" placeholder="规则标题" />
      </el-form-item>
      <el-form-item label="内容" prop="content">
        <el-input v-model="form.content" type="textarea" :rows="6" placeholder="规则详细内容" />
      </el-form-item>
      <el-form-item label="级别">
        <el-select v-model="form.severity">
          <el-option label="必须" value="required" />
          <el-option label="推荐" value="recommended" />
          <el-option label="可选" value="optional" />
        </el-select>
        <div class="field-hint">
          必须：强约束，默认应遵守；推荐：优先遵守，可按上下文调整；可选：建议参考，不强制执行。
        </div>
      </el-form-item>
      <el-form-item label="风险域">
        <el-select v-model="form.risk_domain">
          <el-option label="低" value="low" />
          <el-option label="中" value="medium" />
          <el-option label="高" value="high" />
        </el-select>
        <div class="field-hint">
          低风险：风格/命名类；中风险：架构/性能类；高风险：安全/合规类，通常需要人工审核。
        </div>
      </el-form-item>
      
      <el-form-item label="独立 MCP 服务">
        <el-switch v-model="form.mcp_enabled" />
        <div class="field-hint">
          开启后，平台将为该规则提供独立的网络访问入口（HTTP / SSE），供外部客户端直接挂载使用。
        </div>
      </el-form-item>
      
      <el-form-item label="服务名称" v-if="form.mcp_enabled">
        <el-input v-model="form.mcp_service" placeholder="留空则自动生成" />
        <div class="field-hint">
          客户端配置文件中显示的 mcpServers key，如：my-rule-service。
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="handleCreate">创建规则</el-button>
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

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  domain: '',
  title: '',
  content: '',
  severity: 'recommended',
  risk_domain: 'low',
  mcp_enabled: false,
  mcp_service: '',
})

const rules = {
  domain: [{ required: true, message: '请输入领域', trigger: 'blur' }],
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入内容', trigger: 'blur' }],
}

async function handleCreate() {
  await formRef.value.validate()
  loading.value = true
  try {
    const { rule } = await api.post('/rules', { ...form })
    ElMessage.success(`规则「${rule.title}」创建成功`)
    router.push('/rules')
  } catch (e) {
    ElMessage.error(e.detail || '创建失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.form-wrap {
  max-width: 600px;
}

.field-hint {
  margin-top: 6px;
  color: var(--color-text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}
</style>
