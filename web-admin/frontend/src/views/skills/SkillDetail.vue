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
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'
import {
  canManageRecord,
  formatRecordOwner,
  getOwnershipDeniedMessage,
} from '@/utils/ownership.js'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const skill = reactive({})
const packageLoading = ref(false)
const fileLoading = ref(false)
const packageTree = ref([])
const activeFilePath = ref('')
const activeFile = reactive({
  path: '',
  size: 0,
  content: '',
  is_binary: false,
  truncated: false,
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

function formatFileSize(size) {
  const value = Number(size || 0)
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
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
  await fetchDetail()
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
  .package-browser__body {
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
