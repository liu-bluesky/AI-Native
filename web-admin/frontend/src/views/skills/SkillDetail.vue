<template>
  <div v-loading="loading" class="skill-detail-page">
    <div class="detail-topbar">
      <div class="detail-title-group">
        <p class="detail-eyebrow">Skill Directory</p>
        <h3>技能详情: {{ skill.name || route.params.id }}</h3>
        <p class="detail-subtitle">
          查看技能元信息、工具资源，以及本地技能包目录结构与文件内容。
        </p>
      </div>
      <div class="detail-actions">
        <el-button
          type="primary"
          :disabled="!canManageRecord(skill)"
          @click="$router.push(`/skills/${route.params.id}/edit`)"
        >
          编辑
        </el-button>
        <el-button type="danger" :disabled="!canManageRecord(skill)" @click="handleDelete">删除</el-button>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>

    <div class="detail-summary" v-if="skill.id">
      <div class="summary-main">
        <div class="summary-meta">
          <span class="summary-pill">{{ skill.id }}</span>
          <span class="summary-pill">v{{ skill.version || '-' }}</span>
          <span class="summary-pill">{{ skill.mcp_service || '未配置 MCP 服务' }}</span>
        </div>
        <p class="summary-description">{{ skill.description || '暂无描述' }}</p>
      </div>
      <div class="summary-side">
        <div class="summary-item">
          <span class="summary-label">创建人</span>
          <span class="summary-value">{{ formatRecordOwner(skill) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">创建时间</span>
          <span class="summary-value">{{ formatDateTime(skill.created_at) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">更新时间</span>
          <span class="summary-value">{{ formatDateTime(skill.updated_at) }}</span>
        </div>
      </div>
    </div>

    <div class="meta-grid">
      <section class="meta-panel">
        <div class="panel-head">
          <div>
            <h4>代理状态</h4>
            <p class="panel-desc">{{ skill.proxy_status?.summary || '未分析' }}</p>
          </div>
          <el-button
            v-if="canManageRecord(skill)"
            size="small"
            type="primary"
            plain
            :disabled="!skill.proxy_status?.diagnostics?.can_refresh"
            :loading="refreshingProxy"
            @click="refreshProxyEntries"
          >
            重扫声明
          </el-button>
        </div>
        <div class="proxy-status-tags">
          <el-tag :type="proxyDeclarationType(skill)">
            {{ proxyDeclarationLabel(skill) }}
          </el-tag>
          <el-tag :type="proxyEffectiveType(skill)">
            {{ proxyEffectiveLabel(skill) }}
          </el-tag>
        </div>
        <div class="proxy-stats">
          <div class="proxy-stat-card">
            <span class="proxy-stat-label">显式声明</span>
            <strong>{{ skill.proxy_status?.declared_count || 0 }}</strong>
          </div>
          <div class="proxy-stat-card">
            <span class="proxy-stat-label">解析入口</span>
            <strong>{{ skill.proxy_status?.resolved_count || 0 }}</strong>
          </div>
          <div class="proxy-stat-card">
            <span class="proxy-stat-label">生效入口</span>
            <strong>{{ skill.proxy_status?.effective_count || 0 }}</strong>
          </div>
        </div>
        <div
          v-if="(skill.proxy_status?.diagnostics?.guidance || []).length"
          class="proxy-guidance"
        >
          <div class="proxy-guidance__title">如何让它生效</div>
          <div
            v-for="(tip, index) in (skill.proxy_status?.diagnostics?.guidance || [])"
            :key="`tip-${index}`"
            class="proxy-guidance__item"
          >
            {{ tip }}
          </div>
        </div>
        <div class="proxy-diagnostics">
          <div class="proxy-diagnostics__title">诊断信息</div>
          <div class="proxy-diagnostics__item">
            package 目录: {{ skill.proxy_status?.diagnostics?.package_exists ? '正常' : '缺失' }}
          </div>
          <div class="proxy-diagnostics__item">
            tools 目录: {{ skill.proxy_status?.diagnostics?.tools_dir_exists ? '存在' : '无' }}
          </div>
          <div class="proxy-diagnostics__item">
            scripts 目录: {{ skill.proxy_status?.diagnostics?.scripts_dir_exists ? '存在' : '无' }}
          </div>
          <div
            v-if="(skill.proxy_status?.diagnostics?.candidate_files || []).length"
            class="proxy-candidates"
          >
            <div class="proxy-diagnostics__subtitle">候选脚本</div>
            <div
              v-for="file in skill.proxy_status?.diagnostics?.candidate_files || []"
              :key="file"
              class="proxy-candidates__item"
            >
              {{ file }}
            </div>
          </div>
        </div>
      </section>

      <section class="meta-panel meta-panel-wide">
        <div class="panel-head">
          <div>
            <h4>安装到员工</h4>
            <p class="panel-desc">技能只和员工绑定；项目只是员工的使用范围，不是技能绑定对象。</p>
          </div>
          <el-button text type="primary" :loading="targetLoading" @click="refreshInstallTargets">
            刷新目标
          </el-button>
        </div>
        <div class="activation-grid">
          <div class="activation-form">
            <el-form :model="installForm" label-width="92px">
              <el-form-item label="员工" required>
                <el-select
                  v-model="installForm.employee_id"
                  filterable
                  clearable
                  placeholder="选择要安装技能的员工"
                  style="width: 100%"
                  @change="handleEmployeeChange"
                >
                  <el-option
                    v-for="item in employeeOptions"
                    :key="item.id"
                    :label="`${item.name} (${item.id})`"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
            </el-form>
            <div v-if="contextHintText" class="activation-context">
              {{ contextHintText }}
            </div>
          </div>
          <div class="activation-status">
            <div class="activation-card">
              <span class="activation-card__label">员工技能状态</span>
              <strong>{{ employeeSkillStatusLabel }}</strong>
              <span class="activation-card__meta">{{ employeeSkillStatusMeta }}</span>
            </div>
            <div class="activation-hint">
              说明：安装会同步写入员工技能清单。若你是在项目聊天里使用该员工，项目侧会通过“员工已加入项目”这层关系间接获得该技能。
            </div>
          </div>
        </div>
        <div class="activation-actions">
          <el-button
            type="primary"
            :loading="installing"
            :disabled="!installForm.employee_id"
            @click="installSkillFlow"
          >
            安装到员工
          </el-button>
        </div>
      </section>

      <section class="meta-panel">
        <div class="panel-head">
          <h4>标签</h4>
        </div>
        <div v-if="(skill.tags || []).length" class="tag-wrap">
          <span v-for="t in (skill.tags || [])" :key="t" class="tag-chip">{{ t }}</span>
        </div>
        <el-empty v-else description="暂无标签" :image-size="50" />
      </section>

      <section class="meta-panel">
        <div class="panel-head">
          <h4>工具列表</h4>
          <span class="panel-meta">{{ skill.tools?.length || 0 }} 项</span>
        </div>
        <el-table v-if="(skill.tools || []).length" :data="skill.tools" stripe size="small">
          <el-table-column prop="name" label="工具名" width="200" />
          <el-table-column prop="description" label="描述" />
        </el-table>
        <el-empty v-else description="暂无工具" :image-size="50" />
      </section>

      <section class="meta-panel meta-panel-wide">
        <div class="panel-head">
          <h4>代理入口</h4>
          <span class="panel-meta">{{ skill.proxy_entries?.length || 0 }} 项</span>
        </div>
        <el-table v-if="(skill.proxy_entries || []).length" :data="skill.proxy_entries" stripe size="small">
          <el-table-column prop="name" label="入口名" width="180" />
          <el-table-column prop="runtime" label="运行时" width="100" />
          <el-table-column prop="path" label="路径" width="260" show-overflow-tooltip />
          <el-table-column label="来源" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">
                {{ row.source === 'declared' ? '显式' : '自动' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" />
        </el-table>
        <el-empty v-else description="暂无代理入口" :image-size="50" />
      </section>

      <section class="meta-panel meta-panel-wide">
        <div class="panel-head">
          <h4>资源列表</h4>
          <span class="panel-meta">{{ skill.resources?.length || 0 }} 项</span>
        </div>
        <el-table v-if="(skill.resources || []).length" :data="skill.resources" stripe size="small">
          <el-table-column prop="name" label="资源名" width="220" />
          <el-table-column prop="description" label="描述" />
        </el-table>
        <el-empty v-else description="暂无资源" :image-size="50" />
      </section>
    </div>

    <section class="package-browser">
      <div class="panel-head package-browser__head">
        <div>
          <h4>技能包目录</h4>
          <p class="panel-desc">左侧查看目录结构，右侧预览文本文件内容。</p>
        </div>
        <el-button text type="primary" :loading="packageLoading" @click="refreshPackageBrowser">
          刷新目录
        </el-button>
      </div>

      <div class="package-browser__body">
        <aside class="package-tree">
          <div class="package-tree__title">目录结构</div>
          <el-tree
            v-if="packageTree.length"
            :data="packageTree"
            node-key="path"
            highlight-current
            default-expand-all
            :expand-on-click-node="false"
            :current-node-key="activeFilePath"
            @node-click="handleNodeClick"
          >
            <template #default="{ data }">
              <div class="tree-node" :class="`is-${data.kind}`">
                <span class="tree-node__name">{{ data.label }}</span>
                <span v-if="data.kind === 'file'" class="tree-node__meta">
                  {{ formatFileSize(data.size) }}
                </span>
              </div>
            </template>
          </el-tree>
          <el-empty v-else description="目录为空" :image-size="48" />
        </aside>

        <section class="package-preview">
          <div class="package-preview__header">
            <div>
              <div class="package-preview__path">{{ activeFile.path || '请选择左侧文件' }}</div>
              <div class="package-preview__meta" v-if="activeFile.path">
                <span>{{ formatFileSize(activeFile.size) }}</span>
                <span v-if="activeFile.truncated">内容已截断显示</span>
                <span v-if="activeFile.is_binary">二进制文件不可预览</span>
              </div>
            </div>
          </div>

          <div v-loading="fileLoading" class="package-preview__content">
            <el-empty
              v-if="!activeFile.path && !fileLoading"
              description="点击左侧文件查看内容"
              :image-size="64"
            />
            <el-empty
              v-else-if="activeFile.is_binary && !fileLoading"
              description="该文件为二进制内容，当前不提供文本预览"
              :image-size="64"
            />
            <pre v-else-if="activeFile.path && !fileLoading" class="code-view">{{ activeFile.content }}</pre>
          </div>
        </section>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'
import { isChatSettingsRoutePath } from '@/utils/chat-settings-route.js'
import {
  canManageRecord,
  formatRecordOwner,
  getOwnershipDeniedMessage,
} from '@/utils/ownership.js'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const refreshingProxy = ref(false)
const targetLoading = ref(false)
const employeeBindingLoading = ref(false)
const installing = ref(false)
const skill = reactive({})
const packageLoading = ref(false)
const fileLoading = ref(false)
const packageTree = ref([])
const employeeOptions = ref([])
const employeeBindings = ref([])
const activeFilePath = ref('')
const activeFile = reactive({
  path: '',
  size: 0,
  content: '',
  is_binary: false,
  truncated: false,
})
const installForm = reactive({
  employee_id: '',
})
const chatContext = reactive({
  is_settings_route: false,
  project_id: '',
  selected_employee_ids: [],
  auto_selected_employee_id: '',
})

const currentSkillBinding = computed(() => {
  const skillId = String(skill.id || '').trim()
  if (!skillId) return null
  return (
    employeeBindings.value.find((item) => String(item.skill_id || '').trim() === skillId) || null
  )
})

const employeeSkillStatusLabel = computed(() => {
  if (!installForm.employee_id) return '待选择员工'
  if (employeeBindingLoading.value) return '检查中'
  const binding = currentSkillBinding.value
  if (!binding) return '未安装'
  return binding.installed_at ? '已安装' : '员工已绑定'
})

const employeeSkillStatusMeta = computed(() => {
  if (!installForm.employee_id) {
    if (chatContext.is_settings_route && chatContext.selected_employee_ids.length > 1) {
      return '当前聊天选择了多个员工，请手动选择一个员工查看绑定状态。'
    }
    if (chatContext.is_settings_route && chatContext.project_id) {
      return '当前聊天没有锁定单个员工，请先选择员工。'
    }
    return '先选择目标员工。'
  }
  if (employeeBindingLoading.value) return '正在读取员工当前技能绑定。'
  const binding = currentSkillBinding.value
  if (!binding) return '当前员工还没有接入这个技能。'
  const tools = Array.isArray(binding.enabled_tools) ? binding.enabled_tools.length : 0
  if (binding.installed_at) {
    return `已启用 ${tools} 个工具，安装时间 ${formatDateTime(binding.installed_at)}`
  }
  return `员工资料里已绑定该技能${tools ? `，默认启用 ${tools} 个工具` : ''}`
})

const contextHintText = computed(() => {
  if (!chatContext.is_settings_route) return ''
  if (!chatContext.project_id) return '当前位于聊天设置页，但没有识别到项目上下文。'
  if (chatContext.auto_selected_employee_id) {
    return `已按当前聊天设置自动选择员工 ${chatContext.auto_selected_employee_id}。`
  }
  if (chatContext.selected_employee_ids.length > 1) {
    return `当前聊天已选择 ${chatContext.selected_employee_ids.length} 个员工，请手动选择一个员工安装。`
  }
  return '当前聊天未锁定单个员工，请手动选择一个员工。'
})

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

async function fetchInstallTargets() {
  targetLoading.value = true
  try {
    const employeesRes = await api.get('/employees').catch(() => ({ employees: [] }))
    employeeOptions.value = Array.isArray(employeesRes?.employees) ? employeesRes.employees : []
  } finally {
    targetLoading.value = false
  }
}

function normalizeSelectedEmployeeIds(rawSettings = {}) {
  const values = []
  const selectedList = Array.isArray(rawSettings?.selected_employee_ids)
    ? rawSettings.selected_employee_ids
    : []
  for (const item of selectedList) {
    const value = String(item || '').trim()
    if (value && !values.includes(value)) {
      values.push(value)
    }
  }
  const legacyValue = String(rawSettings?.selected_employee_id || '').trim()
  if (legacyValue && !values.includes(legacyValue)) {
    values.push(legacyValue)
  }
  return values
}

async function hydrateChatContext() {
  chatContext.is_settings_route = isChatSettingsRoutePath(route.path)
  chatContext.project_id = ''
  chatContext.selected_employee_ids = []
  chatContext.auto_selected_employee_id = ''
  if (!chatContext.is_settings_route) {
    return
  }
  const projectId = String(
    route.query.project_id || (typeof window !== 'undefined' ? window.localStorage.getItem('project_id') : '') || '',
  ).trim()
  if (!projectId) {
    return
  }
  chatContext.project_id = projectId
  try {
    const data = await api.get(`/projects/${encodeURIComponent(projectId)}/chat/settings`)
    const selectedEmployeeIds = normalizeSelectedEmployeeIds(data?.settings || {})
    chatContext.selected_employee_ids = selectedEmployeeIds
    if (selectedEmployeeIds.length === 1) {
      installForm.employee_id = selectedEmployeeIds[0]
      chatContext.auto_selected_employee_id = selectedEmployeeIds[0]
      await fetchEmployeeBindings(selectedEmployeeIds[0])
    }
  } catch {
    chatContext.selected_employee_ids = []
  }
}

async function fetchEmployeeBindings(employeeId = installForm.employee_id) {
  const normalizedEmployeeId = String(employeeId || '').trim()
  if (!normalizedEmployeeId) {
    employeeBindings.value = []
    return
  }
  employeeBindingLoading.value = true
  try {
    const data = await api.get(`/employees/${normalizedEmployeeId}/skills`)
    employeeBindings.value = Array.isArray(data?.bindings) ? data.bindings : []
  } catch {
    employeeBindings.value = []
  } finally {
    employeeBindingLoading.value = false
  }
}

function refreshInstallTargets() {
  void fetchInstallTargets()
  if (installForm.employee_id) {
    void fetchEmployeeBindings()
  }
  if (chatContext.is_settings_route) {
    void hydrateChatContext()
  }
}

function handleEmployeeChange(value) {
  installForm.employee_id = String(value || '').trim()
  chatContext.auto_selected_employee_id = ''
  void fetchEmployeeBindings()
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

function resetActiveFile() {
  activeFilePath.value = ''
  activeFile.path = ''
  activeFile.size = 0
  activeFile.content = ''
  activeFile.is_binary = false
  activeFile.truncated = false
}

function findFirstFile(nodes) {
  for (const node of nodes || []) {
    if (node.kind === 'file') return node
    const nested = findFirstFile(node.children || [])
    if (nested) return nested
  }
  return null
}

async function fetchPackageTree() {
  packageLoading.value = true
  try {
    const data = await api.get(`/skills/${route.params.id}/package-tree`)
    packageTree.value = Array.isArray(data.tree) ? data.tree : []
    const firstFile = findFirstFile(packageTree.value)
    if (firstFile) {
      await fetchFileContent(firstFile.path)
    } else {
      resetActiveFile()
    }
  } catch (err) {
    packageTree.value = []
    resetActiveFile()
    ElMessage.error(err?.detail || err?.message || '加载技能目录失败')
  } finally {
    packageLoading.value = false
  }
}

async function fetchFileContent(path) {
  const targetPath = String(path || '').trim()
  if (!targetPath) {
    resetActiveFile()
    return
  }
  fileLoading.value = true
  try {
    const data = await api.get(`/skills/${route.params.id}/package-file`, {
      params: { path: targetPath },
    })
    const file = data?.file || {}
    activeFilePath.value = String(file.path || targetPath)
    activeFile.path = String(file.path || targetPath)
    activeFile.size = Number(file.size || 0)
    activeFile.content = String(file.content || '')
    activeFile.is_binary = !!file.is_binary
    activeFile.truncated = !!file.truncated
  } catch (err) {
    resetActiveFile()
    ElMessage.error(err?.detail || err?.message || '加载文件内容失败')
  } finally {
    fileLoading.value = false
  }
}

function handleNodeClick(node) {
  if (String(node?.kind || '') !== 'file') return
  void fetchFileContent(node.path)
}

function refreshPackageBrowser() {
  void fetchPackageTree()
}

async function refreshProxyEntries() {
  if (!canManageRecord(skill)) {
    ElMessage.warning(getOwnershipDeniedMessage(skill, '重扫'))
    return
  }
  try {
    refreshingProxy.value = true
    const data = await api.post(`/skills/${route.params.id}/refresh-proxy-entries`)
    Object.keys(skill).forEach((key) => delete skill[key])
    Object.assign(skill, data.skill || {})
    ElMessage.success('已完成代理声明重扫')
  } catch {
    ElMessage.error('重扫代理声明失败')
  } finally {
    refreshingProxy.value = false
  }
}

function formatFileSize(size) {
  const value = Number(size || 0)
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

async function installSkillFlow() {
  const employeeId = String(installForm.employee_id || '').trim()
  const skillId = String(skill.id || '').trim()
  if (!employeeId) {
    ElMessage.warning('请选择员工')
    return
  }
  if (!skillId) {
    ElMessage.warning('技能信息未加载完成')
    return
  }
  const enabledTools = Array.isArray(skill.tools)
    ? skill.tools.map((item) => String(item?.name || '').trim()).filter(Boolean)
    : []
  try {
    installing.value = true
    const installResult = await api.post(`/employees/${employeeId}/skills`, {
      skill_id: skillId,
      enabled_tools: enabledTools,
    })
    const installText = currentSkillBinding.value
      ? '已刷新员工技能绑定'
      : installResult?.enabled_tools?.length
      ? `已安装并启用 ${installResult.enabled_tools.length} 个工具`
      : '已安装技能'
    await Promise.all([fetchInstallTargets(), fetchEmployeeBindings(employeeId)])
    ElMessage.success(installText)
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '安装失败')
  } finally {
    installing.value = false
  }
}

async function handleDelete() {
  if (!canManageRecord(skill)) {
    ElMessage.warning(getOwnershipDeniedMessage(skill, '删除'))
    return
  }
  await ElMessageBox.confirm(`确定删除技能「${skill.name}」？`, '确认')
  try {
    await api.delete(`/skills/${route.params.id}`)
    ElMessage.success('已删除')
    router.push('/skills')
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(async () => {
  await Promise.all([fetchDetail(), fetchInstallTargets(), hydrateChatContext()])
  await fetchPackageTree()
})
</script>

<style scoped>
.skill-detail-page {
  min-height: 100%;
  padding: 14px 16px 16px;
  background:
    radial-gradient(circle at top left, rgba(255, 244, 214, 0.5), transparent 24%),
    linear-gradient(180deg, #f6f3ee 0%, #f7f7f8 32%, #f5f5f6 100%);
  color: #2b2f36;
}

.detail-topbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}

.detail-title-group h3 {
  margin: 0;
  font-size: 28px;
  line-height: 1.2;
  color: #171717;
}

.detail-eyebrow {
  margin: 0 0 6px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #9ca3af;
}

.detail-subtitle {
  margin: 8px 0 0;
  max-width: 720px;
  color: #6b7280;
  line-height: 1.7;
}

.detail-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-summary {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(260px, 0.9fr);
  gap: 18px;
  margin-bottom: 18px;
  padding: 18px 20px;
  border: 1px solid rgba(17, 24, 39, 0.08);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.56);
  backdrop-filter: blur(14px);
}

.summary-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.summary-pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: #eceff3;
  color: #4b5563;
  font-size: 12px;
}

.summary-description {
  margin: 0;
  color: #2b2f36;
  line-height: 1.9;
}

.summary-side {
  display: grid;
  gap: 12px;
}

.summary-item {
  display: grid;
  gap: 4px;
}

.summary-label {
  color: #9ca3af;
  font-size: 12px;
}

.summary-value {
  color: #111827;
  font-size: 14px;
  line-height: 1.6;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-bottom: 18px;
}

.meta-panel {
  padding: 18px 20px;
  border: 1px solid rgba(17, 24, 39, 0.08);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.62);
}

.meta-panel-wide {
  grid-column: 1 / -1;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-head h4 {
  margin: 0;
  font-size: 16px;
  color: #171717;
}

.panel-meta {
  color: #9ca3af;
  font-size: 12px;
}

.panel-desc {
  margin: 6px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.tag-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.proxy-status-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.proxy-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.proxy-stat-card {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 16px;
  background: #f7f7f8;
  border: 1px solid rgba(17, 24, 39, 0.06);
}

.proxy-stat-label {
  font-size: 12px;
  color: #9ca3af;
}

.proxy-guidance {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 248, 220, 0.55);
  border: 1px solid rgba(245, 158, 11, 0.16);
}

.proxy-guidance__title,
.proxy-diagnostics__title,
.proxy-diagnostics__subtitle {
  font-size: 12px;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.proxy-guidance__item,
.proxy-diagnostics__item,
.proxy-candidates__item {
  color: #374151;
  font-size: 13px;
  line-height: 1.6;
}

.proxy-diagnostics {
  display: grid;
  gap: 8px;
}

.proxy-candidates {
  display: grid;
  gap: 6px;
  margin-top: 4px;
}

.activation-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(260px, 0.9fr);
  gap: 16px;
}

.activation-form {
  padding: 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(247, 247, 248, 0.96));
  border: 1px solid rgba(17, 24, 39, 0.08);
}

.activation-status {
  display: grid;
  gap: 12px;
}

.activation-card {
  display: grid;
  gap: 6px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(17, 24, 39, 0.08);
  background: rgba(248, 248, 249, 0.92);
}

.activation-card strong {
  color: #171717;
  font-size: 16px;
}

.activation-card__label {
  color: #9ca3af;
  font-size: 12px;
}

.activation-card__meta {
  color: #4b5563;
  font-size: 13px;
  line-height: 1.7;
}

.activation-hint {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 245, 230, 0.78);
  color: #7c5b28;
  line-height: 1.7;
}

.activation-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: #f4f4f5;
  border: 1px solid rgba(17, 24, 39, 0.06);
  color: #4b5563;
  font-size: 13px;
}

.package-browser {
  padding: 18px 20px;
  border: 1px solid rgba(17, 24, 39, 0.08);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.62);
}

.package-browser__head {
  margin-bottom: 14px;
}

.package-browser__body {
  display: grid;
  grid-template-columns: 272px minmax(0, 1fr);
  gap: 18px;
  min-height: 620px;
}

.package-tree,
.package-preview {
  min-height: 0;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(17, 24, 39, 0.06);
}

.package-tree {
  padding: 14px 10px 14px 12px;
  overflow: auto;
}

.package-tree__title {
  margin-bottom: 10px;
  padding: 0 6px;
  color: #6b7280;
  font-size: 12px;
}

.tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-width: 0;
}

.tree-node__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-node__meta {
  color: #9ca3af;
  font-size: 11px;
  flex-shrink: 0;
}

.package-preview {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.package-preview__header {
  padding: 16px 18px 14px;
  border-bottom: 1px solid rgba(17, 24, 39, 0.06);
}

.package-preview__path {
  color: #111827;
  font-size: 14px;
  font-weight: 600;
  word-break: break-all;
}

.package-preview__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
  color: #9ca3af;
  font-size: 12px;
}

.package-preview__content {
  flex: 1;
  min-height: 0;
  padding: 0;
  overflow: auto;
}

.code-view {
  margin: 0;
  min-height: 100%;
  padding: 18px;
  background: transparent;
  color: #2b2f36;
  font-size: 13px;
  line-height: 1.8;
  font-family: "SFMono-Regular", "Menlo", "Monaco", "Consolas", monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

:deep(.el-tree) {
  background: transparent;
  color: #2b2f36;
}

:deep(.el-tree-node__content) {
  height: 34px;
  border-radius: 12px;
}

:deep(.el-tree-node__content:hover) {
  background: #f4f4f5;
}

:deep(.el-tree--highlight-current .el-tree-node.is-current > .el-tree-node__content) {
  background: #eceff3;
}

@media (max-width: 960px) {
  .detail-summary,
  .meta-grid,
  .package-browser__body,
  .activation-grid {
    grid-template-columns: 1fr;
  }

  .skill-detail-page {
    padding: 12px;
  }

  .detail-topbar {
    flex-direction: column;
  }
}
</style>
