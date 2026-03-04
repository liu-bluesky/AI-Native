<template>
  <div>
    <div class="toolbar">
      <h3>AI 员工列表</h3>
      <el-button type="primary" @click="$router.push('/employees/create')">创建员工</el-button>
    </div>
    <el-alert
      class="usage-alert"
      type="info"
      :closable="false"
      show-icon
      title="功能说明：反馈=提交/反思/发布（需开启反馈升级）；记忆=查看与检索员工记忆（含自动写入的用户提问）；同步=查看同步事件。"
    />
    <el-table :data="employees" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="140" />
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="description" label="描述" />
      <el-table-column prop="tone" label="语调" width="100" />
      <el-table-column prop="verbosity" label="风格" width="100" />
      <el-table-column label="反馈升级" width="100">
        <template #default="{ row }">
          <el-tag :type="row.feedback_upgrade_enabled ? 'success' : 'info'" size="small">
            {{ row.feedback_upgrade_enabled ? "已开" : "已关" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="技能数" width="80">
        <template #default="{ row }">{{ row.skills?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="700" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="$router.push(`/employees/${row.id}`)">详情</el-button>
          <el-button text type="primary" @click="$router.push(`/employees/${row.id}/edit`)">编辑</el-button>
          <el-button v-if="row.mcp_enabled" text type="success" @click="showEmployeeMcpConfig(row)">接入</el-button>
          <el-button v-if="row.mcp_enabled" text type="warning" @click="disableEmployeeMcp(row)">关闭 MCP</el-button>
          <el-button v-else text type="warning" @click="enableEmployeeMcp(row)">开启 MCP</el-button>
          <el-button text type="info" @click="showEmployeeConfigTest(row)">测试</el-button>
          <el-button text type="primary" @click="$router.push(`/employees/${row.id}/usage`)">统计</el-button>
          <el-button
            v-if="row.feedback_upgrade_enabled"
            text
            type="primary"
            @click="$router.push(`/feedback/${row.id}`)"
          >
            反馈
          </el-button>
          <el-button
            v-if="!row.feedback_upgrade_enabled"
            text
            type="primary"
            @click="enableFeedbackUpgrade(row)"
          >
            开启反馈
          </el-button>
          <el-button
            v-else
            text
            type="warning"
            @click="disableFeedbackUpgrade(row)"
          >
            关闭反馈
          </el-button>
          <el-button text @click="$router.push(`/memory/${row.id}`)">记忆</el-button>
          <el-button text @click="$router.push(`/sync/${row.id}`)">同步</el-button>
          <el-button text type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showMcpConfig" :title="mcpDialogTitle" width="600px">
      <div class="mcp-desc">
        <p>{{ mcpDialogDesc }}</p>
      </div>

      <el-tabs v-model="mcpTab" class="mcp-tabs">
        <el-tab-pane label="SSE (网络接入)" name="sse">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpSseConfig }}</code></pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="HTTP (Inspector 桥接)" name="http">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpHttpConfig }}</code></pre>
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button type="primary" @click="copyActiveMcpConfig">复制当前配置</el-button>
        <el-button @click="showMcpConfig = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showConfigTestDialog" :title="testDialogTitle" width="760px">
      <div v-loading="testLoading">
        <el-alert
          v-if="testResult"
          :title="testSummaryText"
          :type="testAlertType"
          show-icon
          :closable="false"
        />

        <el-row :gutter="16" class="test-stats-row" v-if="testResult">
          <el-col :span="6">
            <el-statistic title="技能总数" :value="testResult.summary.skills_total" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="技能可用" :value="testResult.summary.skills_available" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="脚本可执行" :value="testResult.summary.skills_executable" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="规则匹配领域" :value="testResult.summary.rule_domains_matched" />
          </el-col>
        </el-row>

        <h4 class="test-section-title">技能检查</h4>
        <el-table :data="testResult?.skills || []" stripe size="small" v-if="testResult">
          <el-table-column prop="skill_id" label="技能 ID" width="120" />
          <el-table-column prop="name" label="名称" width="130" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="checkTagType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="entry_count" label="脚本数" width="80" align="center" />
          <el-table-column label="样例脚本" show-overflow-tooltip>
            <template #default="{ row }">{{ (row.sample_entries || []).join(' | ') || '-' }}</template>
          </el-table-column>
          <el-table-column prop="message" label="结果" width="180" />
        </el-table>
        <el-empty v-else description="暂无测试结果" :image-size="50" />

        <h4 class="test-section-title">规则检查</h4>
        <el-table :data="testResult?.rule_domains || []" stripe size="small" v-if="testResult">
          <el-table-column prop="domain" label="规则领域" width="130" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="checkTagType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="matched_rule_count" label="匹配规则数" width="110" align="center" />
          <el-table-column label="样例标题" show-overflow-tooltip>
            <template #default="{ row }">{{ (row.sample_titles || []).join(' / ') || '-' }}</template>
          </el-table-column>
          <el-table-column prop="message" label="结果" width="180" />
        </el-table>
        <el-empty v-else description="暂无测试结果" :image-size="50" />

        <h4 class="test-section-title">问题清单</h4>
        <div class="issue-list" v-if="testResult && (blockingIssues.length || warningIssues.length)">
          <el-tag
            v-for="item in blockingIssues"
            :key="`block-${item}`"
            type="danger"
            class="issue-tag"
          >
            阻塞: {{ item }}
          </el-tag>
          <el-tag
            v-for="item in warningIssues"
            :key="`warn-${item}`"
            type="warning"
            class="issue-tag"
          >
            警告: {{ item }}
          </el-tag>
        </div>
        <el-empty v-else description="未发现问题" :image-size="50" />
      </div>

      <template #footer>
        <el-button type="primary" :loading="testLoading" @click="runConfigTest">重新测试</el-button>
        <el-button @click="showConfigTestDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

const employees = ref([])
const loading = ref(false)
const showMcpConfig = ref(false)
const mcpTab = ref('sse')
const currentEmployee = ref(null)
const mcpDialogTitle = ref('员工 MCP 接入')
const mcpDialogDesc = ref('将该员工配置挂载到 AI 编辑器后，模型即可按员工配置读取技能、规则和记忆。')
const showConfigTestDialog = ref(false)
const testDialogTitle = ref('员工配置测试')
const testLoading = ref(false)
const testTargetEmployee = ref(null)
const testResult = ref(null)

const mcpSseConfig = computed(() => {
  if (!currentEmployee.value) return ''
  const serverName = `employee-${currentEmployee.value.id}`
  return JSON.stringify({
    mcpServers: {
      [serverName]: {
        type: 'sse',
        url: `http://localhost:8000/mcp/employees/${currentEmployee.value.id}/sse?key=YOUR_API_KEY&project_id=default`,
      },
    },
  }, null, 2)
})

const mcpHttpConfig = computed(() => {
  if (!currentEmployee.value) return ''
  const serverName = `employee-${currentEmployee.value.id}`
  return JSON.stringify({
    mcpServers: {
      [serverName]: {
        command: 'npx',
        args: [
          '-y',
          '@modelcontextprotocol/inspector',
          `http://localhost:8000/mcp/employees/${currentEmployee.value.id}/mcp?key=YOUR_API_KEY&project_id=default`,
        ],
      },
    },
  }, null, 2)
})

const blockingIssues = computed(() => testResult.value?.blocking_issues || [])
const warningIssues = computed(() => testResult.value?.warning_issues || [])
const testAlertType = computed(() => {
  const status = testResult.value?.summary?.overall_status
  return { healthy: 'success', warning: 'warning', failed: 'error' }[status] || 'info'
})
const testSummaryText = computed(() => {
  const summary = testResult.value?.summary
  if (!summary) return '等待测试'
  if (summary.overall_status === 'healthy') return '配置测试通过：技能与规则均可用'
  if (summary.overall_status === 'warning') return '配置测试通过，但存在警告项'
  return '配置测试失败：存在阻塞问题'
})

async function fetchList() {
  loading.value = true
  try {
    const { employees: list } = await api.get('/employees')
    employees.value = list
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除员工「${row.name}」？`, '确认')
  try {
    await api.delete(`/employees/${row.id}`)
    ElMessage.success('已删除')
    fetchList()
  } catch {
    ElMessage.error('删除失败')
  }
}

function showEmployeeMcpConfig(row) {
  currentEmployee.value = row
  mcpTab.value = 'sse'
  mcpDialogTitle.value = `员工接入: ${row.name}`
  showMcpConfig.value = true
}

async function enableEmployeeMcp(row) {
  try {
    loading.value = true
    await api.put(`/employees/${row.id}`, { mcp_enabled: true })
    ElMessage.success('已开启员工 MCP 服务')
    await fetchList()
    const updated = employees.value.find((item) => item.id === row.id) || row
    showEmployeeMcpConfig(updated)
  } catch (e) {
    ElMessage.error(e.detail || '开启 MCP 失败')
  } finally {
    loading.value = false
  }
}

async function disableEmployeeMcp(row) {
  await ElMessageBox.confirm(`确定关闭员工「${row.name}」的 MCP 服务？`, '确认')
  try {
    loading.value = true
    await api.put(`/employees/${row.id}`, { mcp_enabled: false })
    ElMessage.success('已关闭员工 MCP 服务')
    await fetchList()
    if (currentEmployee.value?.id === row.id) {
      showMcpConfig.value = false
      currentEmployee.value = null
    }
  } catch (e) {
    ElMessage.error(e.detail || '关闭 MCP 失败')
  } finally {
    loading.value = false
  }
}

async function enableFeedbackUpgrade(row) {
  try {
    loading.value = true
    await api.put(`/employees/${row.id}`, { feedback_upgrade_enabled: true })
    ElMessage.success('已开启反馈升级')
    await fetchList()
  } catch (e) {
    ElMessage.error(e.detail || '开启反馈失败')
  } finally {
    loading.value = false
  }
}

async function disableFeedbackUpgrade(row) {
  await ElMessageBox.confirm(`确定关闭员工「${row.name}」的反馈升级模块？`, '确认')
  try {
    loading.value = true
    await api.put(`/employees/${row.id}`, { feedback_upgrade_enabled: false })
    ElMessage.success('已关闭反馈升级')
    await fetchList()
  } catch (e) {
    ElMessage.error(e.detail || '关闭反馈失败')
  } finally {
    loading.value = false
  }
}

function checkTagType(status) {
  return { ok: 'success', warning: 'warning', missing: 'danger' }[status] || 'info'
}

async function runConfigTest() {
  if (!testTargetEmployee.value?.id) return
  testLoading.value = true
  try {
    const data = await api.get(`/employees/${testTargetEmployee.value.id}/config-test`)
    testResult.value = data
    if (data.summary?.overall_status === 'failed') {
      ElMessage.error('配置测试发现阻塞问题')
    } else if (data.summary?.overall_status === 'warning') {
      ElMessage.warning('配置测试通过，但存在警告项')
    } else {
      ElMessage.success('配置测试通过')
    }
  } catch (e) {
    ElMessage.error(e.detail || '配置测试失败')
  } finally {
    testLoading.value = false
  }
}

async function showEmployeeConfigTest(row) {
  testTargetEmployee.value = row
  testDialogTitle.value = `配置测试: ${row.name}`
  testResult.value = null
  showConfigTestDialog.value = true
  await runConfigTest()
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

onMounted(fetchList)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.usage-alert {
  margin-bottom: 12px;
}
.toolbar h3 { margin: 0; }

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

.test-stats-row {
  margin: 16px 0;
}

.test-section-title {
  margin: 16px 0 8px;
}

.issue-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.issue-tag {
  margin-right: 0;
}
</style>
