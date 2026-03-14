<template>
  <div v-loading="loading">
    <h3>编辑规则: {{ form.title }}</h3>
    <el-form :model="form" :rules="rules" ref="formRef" label-width="120px" class="form-wrap">
      <el-form-item label="领域" prop="domain">
        <el-input v-model="form.domain" />
      </el-form-item>
      <el-form-item label="标题" prop="title">
        <el-input v-model="form.title" />
      </el-form-item>
      <el-form-item label="内容" prop="content">
        <el-input v-model="form.content" type="textarea" :rows="6" />
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

      <el-form-item label="绑定员工">
        <el-select
          v-model="form.bound_employees"
          class="select-wide"
          multiple
          filterable
          clearable
          collapse-tags
          collapse-tags-tooltip
          placeholder="可选，直接绑定到员工"
        >
          <el-option
            v-for="item in employees"
            :key="item.id"
            :label="`${item.name || item.id} (${item.id})`"
            :value="item.id"
          />
        </el-select>
        <div class="field-hint">
          修改后会同步更新员工的规则标题绑定（rule_ids）。
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
import { canManageRecord, getOwnershipDeniedMessage } from '@/utils/ownership.js'

const route = useRoute()
const router = useRouter()
const formRef = ref(null)
const loading = ref(false)
const saving = ref(false)
const employees = ref([])

const form = reactive({
  domain: '',
  title: '',
  content: '',
  severity: 'recommended',
  risk_domain: 'low',
  mcp_enabled: false,
  mcp_service: '',
  bound_employees: [],
})

const rules = {
  domain: [{ required: true, message: '请输入领域', trigger: 'blur' }],
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入内容', trigger: 'blur' }],
}

async function fetchDetail() {
  loading.value = true
  try {
    const { rule } = await api.get(`/rules/${route.params.id}`)
    if (!canManageRecord(rule)) {
      ElMessage.warning(getOwnershipDeniedMessage(rule, '编辑'))
      router.replace(`/rules/${route.params.id}`)
      return false
    }
    Object.assign(form, {
      domain: rule.domain || '',
      title: rule.title || '',
      content: rule.content || '',
      severity: rule.severity || 'recommended',
      risk_domain: rule.risk_domain || 'low',
      mcp_enabled: rule.mcp_enabled || false,
      mcp_service: rule.mcp_service || '',
      bound_employees: Array.isArray(rule.bound_employees) ? rule.bound_employees : [],
    })
    return true
  } catch {
    ElMessage.error('加载失败')
    return false
  } finally {
    loading.value = false
  }
}

async function fetchEmployees() {
  try {
    const data = await api.get('/employees')
    employees.value = data.employees || []
  } catch {
    employees.value = []
  }
}

async function handleSave() {
  await formRef.value.validate()
  saving.value = true
  try {
    await api.put(`/rules/${route.params.id}`, { ...form })
    ElMessage.success('保存成功')
    router.push(`/rules/${route.params.id}`)
  } catch (e) {
    ElMessage.error(e.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  const ok = await fetchDetail()
  if (!ok) return
  await fetchEmployees()
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
  line-height: 1.5;
}
</style>
