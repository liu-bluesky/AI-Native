<template>
  <div>
    <h3>新建人设</h3>
    <el-form :model="form" :rules="rules" ref="formRef" label-width="120px" class="form-wrap">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="如：前端专家" />
      </el-form-item>
      <el-form-item label="语调">
        <el-select v-model="form.tone">
          <el-option label="专业" value="professional" />
          <el-option label="友好" value="friendly" />
          <el-option label="严格" value="strict" />
          <el-option label="导师" value="mentor" />
        </el-select>
      </el-form-item>
      <el-form-item label="风格">
        <el-select v-model="form.verbosity">
          <el-option label="详细" value="verbose" />
          <el-option label="简洁" value="concise" />
          <el-option label="极简" value="minimal" />
        </el-select>
      </el-form-item>
      <el-form-item label="语言">
        <el-input v-model="form.language" placeholder="zh-CN" />
      </el-form-item>

      <el-divider content-position="left">行为准则</el-divider>
      <el-form-item label="行为列表">
        <div v-for="(b, i) in form.behaviors" :key="i" class="list-row">
          <el-input v-model="form.behaviors[i]" size="small" />
          <el-button text type="danger" size="small" @click="form.behaviors.splice(i, 1)">删除</el-button>
        </div>
        <el-button text type="primary" size="small" @click="form.behaviors.push('')">+ 添加行为</el-button>
      </el-form-item>

      <el-divider content-position="left">风格提示</el-divider>
      <el-form-item label="提示列表">
        <div v-for="(h, i) in form.style_hints" :key="i" class="list-row">
          <el-input v-model="form.style_hints[i]" size="small" />
          <el-button text type="danger" size="small" @click="form.style_hints.splice(i, 1)">删除</el-button>
        </div>
        <el-button text type="primary" size="small" @click="form.style_hints.push('')">+ 添加提示</el-button>
      </el-form-item>

      <el-divider content-position="left">决策策略（高级）</el-divider>
      <el-form-item label="风险偏好">
        <el-select v-model="form.decision_policy.risk_preference">
          <el-option label="保守" value="conservative" />
          <el-option label="平衡" value="balanced" />
          <el-option label="激进" value="aggressive" />
        </el-select>
      </el-form-item>
      <el-form-item label="不确定时">
        <el-select v-model="form.decision_policy.uncertain_action">
          <el-option label="请求确认" value="ask_for_confirmation" />
          <el-option label="使用默认" value="use_default" />
          <el-option label="跳过" value="skip" />
        </el-select>
      </el-form-item>

      <el-divider content-position="left">漂移控制（高级）</el-divider>
      <el-form-item label="启用">
        <el-switch v-model="form.drift_control.enabled" />
      </el-form-item>
      <el-form-item label="窗口天数" v-if="form.drift_control.enabled">
        <el-input-number v-model="form.drift_control.window_days" :min="7" :max="365" />
      </el-form-item>
      <el-form-item label="最大漂移分" v-if="form.drift_control.enabled">
        <el-slider v-model="form.drift_control.max_drift_score" :min="0.05" :max="1" :step="0.05" show-input />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="handleCreate">创建人设</el-button>
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
  name: '',
  tone: 'professional',
  verbosity: 'concise',
  language: 'zh-CN',
  behaviors: [],
  style_hints: [],
  decision_policy: {
    risk_preference: 'balanced',
    uncertain_action: 'ask_for_confirmation',
  },
  drift_control: {
    enabled: true,
    window_days: 30,
    max_drift_score: 0.25,
  },
})

const rules = {
  name: [{ required: true, message: '请输入人设名称', trigger: 'blur' }],
}

async function handleCreate() {
  await formRef.value.validate()
  loading.value = true
  try {
    const payload = {
      ...form,
      behaviors: form.behaviors.filter(Boolean),
      style_hints: form.style_hints.filter(Boolean),
    }
    const { persona } = await api.post('/personas', payload)
    ElMessage.success(`人设「${persona.name}」创建成功`)
    router.push('/personas')
  } catch (e) {
    ElMessage.error(e.detail || '创建失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.form-wrap {
  max-width: 650px;
}

.list-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
</style>
