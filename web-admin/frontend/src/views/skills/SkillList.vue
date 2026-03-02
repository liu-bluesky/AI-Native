<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>技能目录</h3>
      <el-button type="primary" size="small" @click="$router.push('/skills/create')">导入技能</el-button>
    </div>

    <el-table :data="skills" stripe>
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="description" label="描述" show-overflow-tooltip />
      <el-table-column prop="version" label="版本" width="90" />
      <el-table-column prop="mcp_service" label="MCP 服务" width="140" />
      <el-table-column label="标签" width="200">
        <template #default="{ row }">
          <el-tag v-for="t in row.tags" :key="t" size="small" class="tag-item">{{ t }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="工具数" width="80" align="center">
        <template #default="{ row }">{{ row.tools?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.mcp_enabled" text type="success" size="small" @click="showSingleMcpConfig(row)">接入</el-button>
          <el-button v-else text type="warning" size="small" @click="enableMcp(row)">开启 MCP</el-button>
          <el-button text type="primary" size="small" @click="$router.push(`/skills/${row.id}/edit`)">编辑</el-button>
          <el-button text type="success" size="small" @click="handleDownload(row.id, row.name)">下载</el-button>
          <el-button text type="danger" size="small" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!skills.length && !loading" description="暂无技能" />

    <el-dialog v-model="showMcpConfig" :title="mcpDialogTitle" width="600px">
      <div class="mcp-desc">
        <p>{{ mcpDialogDesc }}</p>
      </div>
      
      <el-tabs v-model="mcpTab" class="mcp-tabs">
        <el-tab-pane label="SSE (网络接入)" name="sse">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpSseConfig }}</code></pre>
          </div>
          <div class="hint mt-2">提示：绝大多数现代 MCP 客户端（如 Cursor）原生支持 SSE URL。</div>
        </el-tab-pane>
        <el-tab-pane label="HTTP (Inspector 桥接)" name="http">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpHttpConfig }}</code></pre>
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button @click="copyActiveMcpConfig" type="primary">复制当前配置</el-button>
        <el-button @click="showMcpConfig = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const loading = ref(false)
const skills = ref([])

const showMcpConfig = ref(false)
const mcpDialogTitle = ref('接入 MCP 服务')
const mcpDialogDesc = ref('该技能已开启独立网络访问，无需本地环境即可挂载：')
const mcpTab = ref('sse')
const currentSkill = ref(null)

const mcpSseConfig = computed(() => {
  if (!currentSkill.value) return ''
  const serviceName = currentSkill.value.mcp_service || currentSkill.value.id
  return JSON.stringify({
    "mcpServers": {
      [serviceName]: {
        "type": "sse",
        "url": `http://localhost:8000/mcp/skills/${currentSkill.value.id}/sse`
      }
    }
  }, null, 2)
})

const mcpHttpConfig = computed(() => {
  if (!currentSkill.value) return ''
  const serviceName = currentSkill.value.mcp_service || currentSkill.value.id
  return JSON.stringify({
    "mcpServers": {
      [serviceName]: {
        "command": "npx",
        "args": [
          "-y",
          "@modelcontextprotocol/inspector",
          `http://localhost:8000/mcp/skills/${currentSkill.value.id}/sse`
        ]
      }
    }
  }, null, 2)
})

function showSingleMcpConfig(skill) {
  currentSkill.value = skill
  mcpDialogTitle.value = `独立技能接入: ${skill.name}`
  showMcpConfig.value = true
}

async function enableMcp(skill) {
  try {
    loading.value = true
    await api.put(`/skills/${skill.id}`, { mcp_enabled: true })
    ElMessage.success('已开启独立 MCP 服务')
    await fetchSkills()
    
    const updatedSkill = skills.value.find(s => s.id === skill.id) || skill
    showSingleMcpConfig(updatedSkill)
  } catch {
    ElMessage.error('开启 MCP 失败')
  } finally {
    loading.value = false
  }
}

async function copyActiveMcpConfig() {
  const content = mcpTab.value === 'sse' ? mcpSseConfig.value : mcpHttpConfig.value
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success('配置已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function fetchSkills() {
  loading.value = true
  try {
    const data = await api.get('/skills')
    skills.value = data.skills || []
  } catch {
    ElMessage.error('加载技能列表失败')
  } finally {
    loading.value = false
  }
}

async function handleDownload(skillId, skillName) {
  try {
    const response = await api.get(`/skills/${skillId}/export`, {
      responseType: 'blob'
    })
    const url = URL.createObjectURL(response)
    const a = document.createElement('a')
    a.href = url
    a.download = `${skillName || skillId}.zip`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch {
    ElMessage.error('下载失败')
  }
}

async function handleDelete(skillId) {
  await ElMessageBox.confirm('确定删除该技能？', '确认')
  try {
    await api.delete(`/skills/${skillId}`)
    ElMessage.success('已删除')
    fetchSkills()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(fetchSkills)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 { margin: 0; }

.tag-item {
  margin-right: 6px;
}

.mcp-desc {
  margin-bottom: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.mcp-code-wrap {
  background: #1e1e1e;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}

.mcp-code {
  margin: 0;
  color: #d4d4d4;
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
  line-height: 1.4;
}

.mt-2 {
  margin-top: 8px;
}
</style>
