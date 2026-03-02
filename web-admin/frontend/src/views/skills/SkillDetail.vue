<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>技能详情: {{ skill.name }}</h3>
      <div>
        <el-button type="primary" @click="$router.push(`/skills/${route.params.id}/edit`)">编辑</el-button>
        <el-button type="danger" @click="handleDelete">删除</el-button>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-descriptions :column="2" border v-if="skill.id">
      <el-descriptions-item label="ID">{{ skill.id }}</el-descriptions-item>
      <el-descriptions-item label="名称">{{ skill.name }}</el-descriptions-item>
      <el-descriptions-item label="版本">{{ skill.version }}</el-descriptions-item>
      <el-descriptions-item label="MCP 服务">{{ skill.mcp_service || '-' }}</el-descriptions-item>
      <el-descriptions-item label="描述" :span="2">{{ skill.description || '-' }}</el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ skill.created_at }}</el-descriptions-item>
      <el-descriptions-item label="更新时间">{{ skill.updated_at }}</el-descriptions-item>
    </el-descriptions>

    <h4 class="section-title">标签</h4>
    <el-tag v-for="t in (skill.tags || [])" :key="t" class="inline-tag">{{ t }}</el-tag>
    <el-empty v-if="!(skill.tags || []).length" description="暂无标签" :image-size="60" />

    <h4 class="section-title">工具列表</h4>
    <el-table v-if="(skill.tools || []).length" :data="skill.tools" stripe size="small">
      <el-table-column prop="name" label="工具名" width="200" />
      <el-table-column prop="description" label="描述" />
    </el-table>
    <el-empty v-else description="暂无工具" :image-size="60" />

    <h4 class="section-title">资源列表</h4>
    <el-table v-if="(skill.resources || []).length" :data="skill.resources" stripe size="small">
      <el-table-column prop="name" label="资源名" width="200" />
      <el-table-column prop="description" label="描述" />
    </el-table>
    <el-empty v-else description="暂无资源" :image-size="60" />
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
const skill = reactive({})

async function fetchDetail() {
  loading.value = true
  try {
    const data = await api.get(`/skills/${route.params.id}`)
    Object.assign(skill, data.skill)
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete() {
  await ElMessageBox.confirm(`确定删除技能「${skill.name}」？`, '确认')
  try {
    await api.delete(`/skills/${route.params.id}`)
    ElMessage.success('已删除')
    router.push('/skills')
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

.inline-tag {
  margin-right: 6px;
}
</style>
