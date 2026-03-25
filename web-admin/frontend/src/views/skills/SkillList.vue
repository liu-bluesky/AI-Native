<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>技能目录</h3>
      <div class="toolbar-actions">
        <el-button size="small" @click="$router.push('/skill-resources')">浏览技能资源</el-button>
        <el-button type="primary" size="small" @click="$router.push('/skills/create')">导入技能</el-button>
      </div>
    </div>

    <el-table :data="skills" stripe>
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="description" label="描述" show-overflow-tooltip />
      <el-table-column prop="version" label="版本" width="90" />
      <el-table-column label="创建人" width="120">
        <template #default="{ row }">
          {{ formatRecordOwner(row) }}
        </template>
      </el-table-column>
      <el-table-column prop="mcp_service" label="MCP 服务" width="140" />
      <el-table-column label="标签" width="200">
        <template #default="{ row }">
          <el-tag v-for="t in row.tags" :key="t" size="small" class="tag-item">{{ t }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="工具数" width="80" align="center">
        <template #default="{ row }">{{ row.tools?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="代理声明 / 生效状态" width="260">
        <template #default="{ row }">
          <div class="proxy-status-cell">
            <div class="proxy-status-tags">
              <el-tag :type="proxyDeclarationType(row)" size="small">
                {{ proxyDeclarationLabel(row) }}
              </el-tag>
              <el-tag :type="proxyEffectiveType(row)" size="small">
                {{ proxyEffectiveLabel(row) }}
              </el-tag>
            </div>
            <div class="proxy-status-summary">
              {{ row.proxy_status?.summary || '未分析' }}
            </div>
            <el-popover placement="left" trigger="hover" width="320">
              <template #reference>
                <el-button text type="primary" size="small">查看详情</el-button>
              </template>
              <div class="proxy-popover">
                <div class="proxy-popover__title">代理状态</div>
                <div class="proxy-popover__item">显式声明: {{ row.proxy_status?.declared_count || 0 }}</div>
                <div class="proxy-popover__item">解析入口: {{ row.proxy_status?.resolved_count || 0 }}</div>
                <div class="proxy-popover__item">生效入口: {{ row.proxy_status?.effective_count || 0 }}</div>
                <div class="proxy-popover__item">
                  来源:
                  {{
                    row.proxy_status?.declaration_status === 'declared'
                      ? '技能包显式声明'
                      : row.proxy_status?.declaration_status === 'auto_inferred'
                        ? '上传时自动推断'
                      : '无'
                  }}
                </div>
                <div
                  v-for="(tip, index) in (row.proxy_status?.diagnostics?.guidance || [])"
                  :key="`${row.id}-tip-${index}`"
                  class="proxy-popover__tip"
                >
                  {{ tip }}
                </div>
                <div v-if="(row.proxy_entries || []).length" class="proxy-popover__entries">
                  <div class="proxy-popover__subtitle">入口列表</div>
                  <div
                    v-for="entry in row.proxy_entries"
                    :key="`${row.id}-${entry.name}-${entry.path}`"
                    class="proxy-entry"
                  >
                    <div class="proxy-entry__head">
                      <span>{{ entry.name }}</span>
                      <el-tag size="small" effect="plain">
                        {{ entry.source === 'declared' ? '显式' : '自动' }}
                      </el-tag>
                    </div>
                    <div class="proxy-entry__meta">{{ entry.runtime || '-' }} · {{ entry.path || '-' }}</div>
                  </div>
                </div>
                <div class="proxy-popover__actions" v-if="canManageRow(row)">
                  <el-button
                    size="small"
                    type="primary"
                    plain
                    :disabled="!row.proxy_status?.diagnostics?.can_refresh"
                    @click.stop="refreshProxyEntries(row)"
                  >
                    重扫声明
                  </el-button>
                </div>
              </div>
            </el-popover>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="350" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.mcp_enabled" text type="success" size="small" @click="showSingleMcpConfig(row)">接入</el-button>
          <el-button v-if="row.mcp_enabled" text type="warning" size="small" :disabled="!canManageRow(row)" @click="disableMcp(row)">关闭 MCP</el-button>
          <el-button v-else text type="warning" size="small" :disabled="!canManageRow(row)" @click="enableMcp(row)">开启 MCP</el-button>
          <el-button text type="info" size="small" @click="showConfigs(row)">配置</el-button>
          <el-button text type="primary" size="small" @click="$router.push(`/skills/${row.id}`)">详情</el-button>
          <el-button text type="primary" size="small" :disabled="!canManageRow(row)" @click="$router.push(`/skills/${row.id}/edit`)">编辑</el-button>
          <el-button text type="success" size="small" @click="handleDownload(row.id, row.name)">下载</el-button>
          <el-button text type="danger" size="small" :disabled="!canManageRow(row)" @click="handleDelete(row.id)">删除</el-button>
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

    <el-dialog v-model="showConfigDialog" :title="configDialogTitle" width="650px">
      <el-table :data="configList" stripe size="small" v-loading="configLoading">
        <el-table-column prop="user" label="用户" width="120" />
        <el-table-column prop="file" label="配置文件" width="220" />
        <el-table-column label="连接信息">
          <template #default="{ row }">
            {{ row.config.type }}://{{ row.config.host }}:{{ row.config.port }}/{{ row.config.database }}
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!configLoading && !configList.length" description="暂无配置" :image-size="60" />
      <template #footer>
        <el-button @click="showConfigDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import {
  canManageRecord,
  formatRecordOwner,
  getOwnershipDeniedMessage,
} from '@/utils/ownership.js'
import { buildRuntimeUrl } from '@/utils/runtime-url.js'

const loading = ref(false)
const skills = ref([])

const showMcpConfig = ref(false)
const mcpDialogTitle = ref('接入 MCP 服务')
const mcpDialogDesc = ref('该技能已开启独立网络访问，无需本地环境即可挂载：')
const mcpTab = ref('sse')
const currentSkill = ref(null)
const showConfigDialog = ref(false)
const configDialogTitle = ref('技能配置')
const configList = ref([])
const configLoading = ref(false)

const mcpSseConfig = computed(() => {
  if (!currentSkill.value) return ''
  const serviceName = currentSkill.value.mcp_service || currentSkill.value.id
  return JSON.stringify({
    "mcpServers": {
      [serviceName]: {
        "type": "sse",
        "url": buildRuntimeUrl(`/mcp/skills/${currentSkill.value.id}/sse`)
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
          buildRuntimeUrl(`/mcp/skills/${currentSkill.value.id}/mcp`)
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

function canManageRow(row) {
  return canManageRecord(row)
}

function proxyDeclarationLabel(row) {
  const status = row?.proxy_status?.declaration_status
  if (status === 'declared') return '已声明'
  if (status === 'auto_inferred') return '自动推断'
  return '无声明'
}

function proxyDeclarationType(row) {
  const status = row?.proxy_status?.declaration_status
  if (status === 'declared') return 'success'
  if (status === 'auto_inferred') return 'warning'
  return 'info'
}

function proxyEffectiveLabel(row) {
  const count = Number(row?.proxy_status?.effective_count || 0)
  return count > 0 ? `${count} 个生效` : '未生效'
}

function proxyEffectiveType(row) {
  const count = Number(row?.proxy_status?.effective_count || 0)
  return count > 0 ? 'success' : 'info'
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

async function refreshProxyEntries(skill) {
  try {
    loading.value = true
    const { skill: updatedSkill } = await api.post(`/skills/${skill.id}/refresh-proxy-entries`)
    const index = skills.value.findIndex((item) => item.id === skill.id)
    if (index >= 0) {
      skills.value[index] = updatedSkill
    } else {
      await fetchSkills()
    }
    ElMessage.success('已完成代理声明重扫')
  } catch {
    ElMessage.error('重扫代理声明失败')
  } finally {
    loading.value = false
  }
}

async function disableMcp(skill) {
  await ElMessageBox.confirm(`确定关闭技能「${skill.name}」的 MCP 服务？`, '确认')
  try {
    loading.value = true
    await api.put(`/skills/${skill.id}`, { mcp_enabled: false })
    ElMessage.success('已关闭独立 MCP 服务')
    await fetchSkills()
    if (currentSkill.value?.id === skill.id) {
      showMcpConfig.value = false
      currentSkill.value = null
    }
  } catch {
    ElMessage.error('关闭 MCP 失败')
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
  const row = skills.value.find((item) => item.id === skillId)
  if (row && !canManageRow(row)) {
    ElMessage.warning(getOwnershipDeniedMessage(row, '删除'))
    return
  }
  await ElMessageBox.confirm('确定删除该技能？', '确认')
  try {
    await api.delete(`/skills/${skillId}`)
    ElMessage.success('已删除')
    fetchSkills()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function showConfigs(skill) {
  configDialogTitle.value = `配置: ${skill.name}`
  configList.value = []
  showConfigDialog.value = true
  configLoading.value = true
  try {
    const { configs } = await api.get(`/skills/${skill.id}/configs`)
    configList.value = configs
  } catch {
    ElMessage.error('加载配置失败')
  } finally {
    configLoading.value = false
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

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.tag-item {
  margin-right: 6px;
}

.proxy-status-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.proxy-status-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.proxy-status-summary {
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.proxy-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.proxy-popover__title {
  font-weight: 600;
  color: var(--color-text-primary);
}

.proxy-popover__item {
  font-size: 13px;
  color: var(--color-text-primary);
}

.proxy-popover__tip {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.proxy-popover__entries {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--el-border-color-light);
}

.proxy-popover__subtitle {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.proxy-entry {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.proxy-entry__head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-primary);
}

.proxy-entry__meta {
  font-size: 12px;
  color: var(--color-text-secondary);
  word-break: break-all;
}

.proxy-popover__actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 6px;
  border-top: 1px dashed var(--el-border-color-light);
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
