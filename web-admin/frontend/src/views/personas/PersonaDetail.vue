<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>人设详情: {{ persona.name }}</h3>
      <div>
        <el-button type="primary" @click="$router.push(`/personas/${route.params.id}/edit`)">编辑</el-button>
        <el-button type="danger" @click="handleDelete">删除</el-button>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-descriptions :column="2" border v-if="persona.id">
      <el-descriptions-item label="ID">{{ persona.id }}</el-descriptions-item>
      <el-descriptions-item label="名称">{{ persona.name }}</el-descriptions-item>
      <el-descriptions-item label="语调">{{ persona.tone }}</el-descriptions-item>
      <el-descriptions-item label="风格">{{ persona.verbosity }}</el-descriptions-item>
      <el-descriptions-item label="语言">{{ persona.language }}</el-descriptions-item>
      <el-descriptions-item label="对齐分">{{ persona.alignment_score }}</el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ persona.created_at }}</el-descriptions-item>
      <el-descriptions-item label="更新时间">{{ persona.updated_at }}</el-descriptions-item>
    </el-descriptions>

    <h4 class="section-title">行为准则</h4>
    <ul v-if="(persona.behaviors || []).length">
      <li v-for="(b, i) in persona.behaviors" :key="i">{{ b }}</li>
    </ul>
    <el-empty v-else description="暂无行为准则" :image-size="60" />

    <h4 class="section-title">风格提示</h4>
    <el-tag v-for="h in (persona.style_hints || [])" :key="h" class="hint-tag">{{ h }}</el-tag>
    <el-empty v-if="!(persona.style_hints || []).length" description="暂无风格提示" :image-size="60" />

    <h4 class="section-title">决策策略</h4>
    <el-descriptions :column="1" size="small" border v-if="persona.decision_policy">
      <el-descriptions-item label="优先级">{{ (persona.decision_policy.priority_order || []).join(' > ') || '-' }}</el-descriptions-item>
      <el-descriptions-item label="风险偏好">{{ persona.decision_policy.risk_preference }}</el-descriptions-item>
      <el-descriptions-item label="不确定时">{{ persona.decision_policy.uncertain_action }}</el-descriptions-item>
      <el-descriptions-item label="禁止目标">{{ (persona.decision_policy.forbidden_goals || []).join('、') || '-' }}</el-descriptions-item>
    </el-descriptions>

    <h4 class="section-title">漂移控制</h4>
    <el-descriptions :column="1" size="small" border v-if="persona.drift_control">
      <el-descriptions-item label="启用">{{ persona.drift_control.enabled ? '是' : '否' }}</el-descriptions-item>
      <el-descriptions-item label="窗口">{{ persona.drift_control.window_days }} 天</el-descriptions-item>
      <el-descriptions-item label="最大漂移">{{ persona.drift_control.max_drift_score }}</el-descriptions-item>
      <el-descriptions-item label="漂移告警">{{ persona.drift_control.alert_on_drift ? '是' : '否' }}</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const persona = reactive({})

async function fetchDetail() {
  loading.value = true
  try {
    const data = await api.get(`/personas/${route.params.id}`)
    Object.assign(persona, data.persona)
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete() {
  await ElMessageBox.confirm(`确定删除人设「${persona.name}」？`, '确认')
  try {
    await api.delete(`/personas/${route.params.id}`)
    ElMessage.success('已删除')
    router.push('/personas')
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(fetchDetail)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 { margin: 0; }

.section-title {
  margin-top: 20px;
}

.hint-tag {
  margin-right: 6px;
  margin-bottom: 6px;
}
</style>
