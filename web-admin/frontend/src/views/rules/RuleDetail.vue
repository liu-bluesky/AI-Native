<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>规则详情: {{ rule.title }}</h3>
      <div>
        <el-button type="primary" @click="$router.push(`/rules/${route.params.id}/edit`)">编辑</el-button>
        <el-button type="danger" @click="handleDelete">删除</el-button>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-descriptions :column="2" border v-if="rule.id">
      <el-descriptions-item label="ID">{{ rule.id }}</el-descriptions-item>
      <el-descriptions-item label="领域">{{ rule.domain }}</el-descriptions-item>
      <el-descriptions-item label="标题" :span="2">{{ rule.title }}</el-descriptions-item>
      <el-descriptions-item label="级别">
        <el-tag :type="sevColor(rule.severity)" size="small">{{ rule.severity }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="风险域">{{ rule.risk_domain }}</el-descriptions-item>
      <el-descriptions-item label="置信度">{{ rule.confidence }}</el-descriptions-item>
      <el-descriptions-item label="使用次数">{{ rule.use_count }}</el-descriptions-item>
      <el-descriptions-item label="版本">{{ rule.version }}</el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ rule.created_at }}</el-descriptions-item>
    </el-descriptions>

    <h4 class="section-title">规则内容</h4>
    <div class="rule-content" v-if="rule.content">{{ rule.content }}</div>
    <el-empty v-else description="暂无内容" :image-size="60" />
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
const rule = reactive({})

function sevColor(s) {
  return { required: 'danger', recommended: 'warning', optional: 'info' }[s] || 'info'
}

async function fetchDetail() {
  loading.value = true
  try {
    const data = await api.get(`/rules/${route.params.id}`)
    Object.assign(rule, data.rule)
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete() {
  await ElMessageBox.confirm(`确定删除规则「${rule.title}」？`, '确认')
  try {
    await api.delete(`/rules/${route.params.id}`)
    ElMessage.success('已删除')
    router.push('/rules')
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
.rule-content {
  background: var(--color-bg-container);
  padding: 16px;
  border-radius: 4px;
  border: 1px solid var(--color-border-secondary);
  white-space: pre-wrap;
  line-height: 1.6;
}

.section-title {
  margin-top: 20px;
}
</style>
