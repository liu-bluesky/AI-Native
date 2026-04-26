<template>
  <div class="market-page">
    <div class="market-page__ambient market-page__ambient--left" aria-hidden="true" />
    <div class="market-page__ambient market-page__ambient--right" aria-hidden="true" />
    <div class="market-page__mesh" aria-hidden="true" />

    <header class="market-nav">
      <button type="button" class="market-nav__brand" @click="router.push('/intro')">
        <span class="market-nav__mark">AI</span>
        <span class="market-nav__body">
          <span class="market-nav__name">AI 员工工厂</span>
          <span class="market-nav__meta">技能、员工与规则市场</span>
        </span>
      </button>

      <div class="market-nav__actions">
        <el-button text class="market-nav__link" @click="router.push('/intro')">官网</el-button>
        <el-button
          v-if="authenticated"
          class="market-nav__secondary"
          @click="router.push('/ai/chat')"
        >
          进入工作台
        </el-button>
        <el-button
          v-else
          type="primary"
          class="market-nav__primary"
          @click="showAuthDialog = true"
        >
          登录后进入
        </el-button>
      </div>
    </header>

    <main class="market-main">
      <section class="market-surface" :class="{ 'is-locked': !authenticated }">
        <div v-if="!authenticated" class="market-gate">
          <div class="market-gate__eyebrow">Access Required</div>
          <h2 class="market-gate__title">进入市场前先完成登录或注册。</h2>
          <p class="market-gate__text">
            市场目录会复用你的账号体系，后续其他入口也可以直接调用同一套登录注册封装。
          </p>
          <div class="market-gate__actions">
            <el-button type="primary" class="market-nav__primary" @click="showAuthDialog = true">
              立即登录或注册
            </el-button>
            <el-button class="market-nav__secondary" @click="router.push({ path: '/login', query: { redirect: '/market' } })">
              跳转到登录页
            </el-button>
          </div>
        </div>

        <div v-if="authenticated" class="market-content">
          <section class="market-toolbar">
            <div class="market-toolbar__summary">
              <article v-for="item in summaryItems" :key="item.label" class="market-toolbar__stat">
                <strong>{{ item.value }}</strong>
                <span>{{ item.label }}</span>
              </article>
            </div>

            <div class="market-tabs" role="tablist" aria-label="市场分类">
              <button
                v-for="tab in marketTabs"
                :key="tab.key"
                type="button"
                class="market-tabs__item"
                :class="{ 'is-active': activeTab === tab.key }"
                @click="activeTab = tab.key"
              >
                <span>{{ tab.label }}</span>
                <small>{{ tab.count }}</small>
              </button>
            </div>
          </section>

          <div class="market-section" v-for="section in filteredMarketSections" :key="section.key">
            <div class="market-section__head">
              <div>
                <div class="market-section__eyebrow">{{ section.eyebrow }}</div>
                <h2 class="market-section__title">{{ section.title }}</h2>
              </div>
              <div class="market-section__count">{{ section.items.length }} 项</div>
            </div>

            <div class="market-grid" v-if="section.items.length">
              <article
                v-for="item in section.items"
                :key="`${section.key}-${item.id}`"
                class="market-card"
                :class="`market-card--${section.key}`"
              >
                <div class="market-card__tag">{{ section.label }}</div>
                <h3 class="market-card__title">{{ item.name || item.title }}</h3>
                <p class="market-card__text">{{ item.description || item.goal || item.domain }}</p>

                <div class="market-card__status" v-if="section.key === 'cli_plugins'">
                  <span
                    class="market-card__status-badge"
                    :class="`is-${resolveCliPluginStatus(item).status}`"
                  >
                    {{ resolveCliPluginStatus(item).status_label }}
                  </span>
                  <span class="market-card__status-text">
                    {{ resolveCliPluginStatus(item).status_reason || '等待检测' }}
                  </span>
                </div>

                <div class="market-card__meta" v-if="section.key === 'cli_plugins'">
                  <span>{{ item.vendor || '第三方' }}</span>
                  <span>本地 {{ resolveCliPluginStatus(item).installed_version || '-' }}</span>
                  <span>最新 {{ resolveCliPluginStatus(item).latest_version || '-' }}</span>
                  <span>{{ item.requires_restart ? '安装后需重启' : '安装后可直接使用' }}</span>
                </div>

                <div class="market-card__meta" v-else-if="section.key === 'skills'">
                  <span>版本 {{ item.version || '1.0.0' }}</span>
                  <span>{{ item.tool_count }} 个工具</span>
                </div>

                <div class="market-card__meta" v-else-if="section.key === 'employees'">
                  <span>{{ item.skill_names?.length || 0 }} 个技能</span>
                  <span>{{ item.feedback_upgrade_enabled ? '反馈升级已开' : '反馈升级已关' }}</span>
                </div>

                <div class="market-card__meta" v-else>
                  <span>{{ item.domain }}</span>
                  <span>{{ item.bound_employee_count }} 名员工绑定</span>
                </div>

                <div class="market-card__chips" v-if="section.key === 'cli_plugins' && item.tags?.length">
                  <span v-for="tag in item.tags.slice(0, 4)" :key="tag">{{ tag }}</span>
                </div>

                <div class="market-card__command" v-if="section.key === 'cli_plugins'">
                  <code>{{ item.install_command }}</code>
                </div>

                <div class="market-card__actions" v-if="section.key === 'cli_plugins'">
                  <el-button size="small" @click="sendPluginInstallPromptToChat(item)">
                    交给 AI 安装
                  </el-button>
                  <el-button size="small" @click="copyPluginInstallCommand(item)">
                    复制命令
                  </el-button>
                </div>

                <div class="market-card__chips" v-else-if="section.key === 'skills' && item.tags?.length">
                  <span v-for="tag in item.tags.slice(0, 4)" :key="tag">{{ tag }}</span>
                </div>

                <div class="market-card__chips" v-else-if="section.key === 'employees' && item.skill_names?.length">
                  <span v-for="skillName in item.skill_names.slice(0, 4)" :key="skillName">{{ skillName }}</span>
                </div>

                <div
                  class="market-card__chips"
                  v-else-if="section.key === 'rules' && item.bound_employee_names?.length"
                >
                  <span v-for="employeeName in item.bound_employee_names.slice(0, 4)" :key="employeeName">
                    {{ employeeName }}
                  </span>
                </div>
              </article>
            </div>

            <el-empty v-else description="暂无内容" :image-size="56" />
          </div>
        </div>

        <div v-if="authenticated && loading" class="market-loading">
          <div class="market-loading__bar" />
          <div class="market-loading__text">正在加载市场目录...</div>
        </div>
      </section>
    </main>

    <AuthDialog
      v-model="showAuthDialog"
      title="登录后进入能力市场"
      description="市场目录统一承载技能、员工和规则，后续其他入口也可直接复用这套登录注册能力。"
      @success="fetchCatalog"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ElMessage } from 'element-plus'

import AuthDialog from '@/components/auth/AuthDialog.vue'
import api from '@/utils/api.js'
import { authStateVersion, hasStoredToken } from '@/utils/auth-storage.js'

const router = useRouter()
const loading = ref(false)
const showAuthDialog = ref(false)
const activeTab = ref('all')
const catalog = reactive({
  cli_plugins: [],
  skills: [],
  employees: [],
  rules: [],
})
const meta = reactive({
  cli_plugin_count: 0,
  skill_count: 0,
  employee_count: 0,
  rule_count: 0,
})
const PLUGIN_INSTALL_DRAFT_STORAGE_PREFIX = 'plugin-install-draft:'
const PLUGIN_INSTALL_DRAFT_QUERY_KEY = 'plugin_install_draft_key'

const authenticated = computed(() => {
  authStateVersion.value
  return hasStoredToken()
})

const summaryItems = computed(() => {
  return [
    { label: 'CLI 插件', value: String(meta.cli_plugin_count || 0).padStart(2, '0') },
    { label: '技能', value: String(meta.skill_count || 0).padStart(2, '0') },
    { label: '员工', value: String(meta.employee_count || 0).padStart(2, '0') },
    { label: '规则', value: String(meta.rule_count || 0).padStart(2, '0') },
  ]
})

const marketSections = computed(() => [
  {
    key: 'cli_plugins',
    eyebrow: 'CLI Plugin',
    title: 'CLI 插件市场',
    label: 'CLI',
    items: catalog.cli_plugins,
  },
  {
    key: 'skills',
    eyebrow: 'Skill',
    title: '技能市场',
    label: 'Skill',
    items: catalog.skills,
  },
  {
    key: 'employees',
    eyebrow: 'Employee',
    title: '员工市场',
    label: 'Employee',
    items: catalog.employees,
  },
  {
    key: 'rules',
    eyebrow: 'Rule',
    title: '规则市场',
    label: 'Rule',
    items: catalog.rules,
  },
])

const marketTabs = computed(() => [
  {
    key: 'all',
    label: '全部',
    count: catalog.cli_plugins.length + catalog.skills.length + catalog.employees.length + catalog.rules.length,
  },
  {
    key: 'cli_plugins',
    label: 'CLI 插件',
    count: catalog.cli_plugins.length,
  },
  {
    key: 'skills',
    label: '技能',
    count: catalog.skills.length,
  },
  {
    key: 'employees',
    label: '员工',
    count: catalog.employees.length,
  },
  {
    key: 'rules',
    label: '规则',
    count: catalog.rules.length,
  },
])

const filteredMarketSections = computed(() => {
  if (activeTab.value === 'all') return marketSections.value
  return marketSections.value.filter((section) => section.key === activeTab.value)
})

function resolveCliPluginStatus(item) {
  const rawStatus = item?.install_status && typeof item.install_status === 'object' ? item.install_status : {}
  const status = String(rawStatus.status || '').trim() || 'unknown'
  return {
    status,
    status_label: String(rawStatus.status_label || '').trim() || '状态未知',
    status_reason: String(rawStatus.status_reason || '').trim(),
    installed: rawStatus.installed === true,
    installed_version: String(rawStatus.installed_version || '').trim(),
    latest_version: String(rawStatus.latest_version || '').trim(),
    update_available: rawStatus.update_available === true,
  }
}

async function fetchCatalog() {
  if (!authenticated.value) {
    return
  }

  loading.value = true
  try {
    const data = await api.get('/market/catalog')
    catalog.cli_plugins = Array.isArray(data?.catalog?.cli_plugins) ? data.catalog.cli_plugins : []
    catalog.skills = Array.isArray(data?.catalog?.skills) ? data.catalog.skills : []
    catalog.employees = Array.isArray(data?.catalog?.employees) ? data.catalog.employees : []
    catalog.rules = Array.isArray(data?.catalog?.rules) ? data.catalog.rules : []
    meta.cli_plugin_count = Number(data?.meta?.cli_plugin_count || catalog.cli_plugins.length || 0)
    meta.skill_count = Number(data?.meta?.skill_count || catalog.skills.length || 0)
    meta.employee_count = Number(data?.meta?.employee_count || catalog.employees.length || 0)
    meta.rule_count = Number(data?.meta?.rule_count || catalog.rules.length || 0)
  } catch (err) {
    catalog.cli_plugins = []
    catalog.skills = []
    catalog.employees = []
    catalog.rules = []
    meta.cli_plugin_count = 0
    meta.skill_count = 0
    meta.employee_count = 0
    meta.rule_count = 0
    ElMessage.error(err?.detail || err?.message || '加载市场目录失败')
  } finally {
    loading.value = false
  }
}

async function copyPluginInstallCommand(item) {
  const command = String(item?.install_command || '').trim()
  if (!command) {
    ElMessage.warning('当前插件没有可复制的安装命令')
    return
  }
  try {
    await navigator.clipboard.writeText(command)
    ElMessage.success('安装命令已复制')
  } catch (err) {
    ElMessage.error(err?.message || '复制安装命令失败')
  }
}

function buildPluginInstallPrompt(item) {
  const prompt = String(item?.ai_install_prompt || '').trim()
  if (prompt) return prompt
  const docsUrl = String(item?.docs_url || '').trim()
  const name = String(item?.name || 'CLI 插件').trim()
  return docsUrl ? `帮我安装 ${name}：${docsUrl}` : `帮我安装 ${name}`
}

function persistPluginInstallDraft(prompt) {
  const key = `${PLUGIN_INSTALL_DRAFT_STORAGE_PREFIX}${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
  window.localStorage.setItem(
    key,
    JSON.stringify({
      prompt,
      source: 'market-cli-plugin',
    }),
  )
  return key
}

function sendPluginInstallPromptToChat(item) {
  const prompt = buildPluginInstallPrompt(item)
  const draftKey = persistPluginInstallDraft(prompt)
  const projectId = String(window.localStorage.getItem('project_id') || '').trim()
  router.push({
    path: '/ai/chat',
    query: {
      ...(projectId ? { project_id: projectId } : {}),
      [PLUGIN_INSTALL_DRAFT_QUERY_KEY]: draftKey,
    },
  })
}

onMounted(async () => {
  document.title = 'AI 员工工厂 | 能力市场'
  await fetchCatalog()
})
</script>

<style scoped>
.market-page {
  --page-bg:
    radial-gradient(circle at 18% 0%, rgba(125, 211, 252, 0.16), transparent 26%),
    radial-gradient(circle at 82% 14%, rgba(103, 232, 249, 0.12), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%);
  --page-text: #0f172a;
  --page-text-muted: #475569;
  --page-text-soft: #7c8aa0;
  --page-border: rgba(15, 23, 42, 0.08);
  --page-surface: rgba(255, 255, 255, 0.72);
  --page-surface-strong: rgba(255, 255, 255, 0.84);
  --page-shadow: 0 24px 64px rgba(15, 23, 42, 0.08);
  position: relative;
  min-height: 100dvh;
  overflow: clip;
  color: var(--page-text);
  background: var(--page-bg);
}

.market-page__ambient,
.market-page__mesh {
  position: absolute;
  pointer-events: none;
}

.market-page__ambient {
  width: 30rem;
  height: 30rem;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.72;
}

.market-page__ambient--left {
  top: -11rem;
  left: -13rem;
  background: rgba(125, 211, 252, 0.34);
}

.market-page__ambient--right {
  top: 5rem;
  right: -11rem;
  background: rgba(103, 232, 249, 0.22);
}

.market-page__mesh {
  inset: 0;
  opacity: 0.32;
  background:
    linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
  background-size: 88px 88px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.7), transparent 78%);
}

.market-nav,
.market-main {
  position: relative;
  z-index: 1;
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto;
}

.market-nav {
  position: sticky;
  top: 12px;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 18px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 999px;
  background: rgba(248, 250, 252, 0.58);
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(18px);
}

.market-nav__brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.market-nav__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  background: #0f172a;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
}

.market-nav__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.market-nav__name,
.market-gate__title,
.market-section__title,
.market-card__title {
  font-family: 'Avenir Next', 'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.market-nav__name {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.1;
}

.market-nav__meta {
  margin-top: 2px;
  color: #475569;
  font-size: 11px;
  line-height: 1.3;
}

.market-nav__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.market-nav__link,
.market-nav__secondary {
  color: #0f172a;
}

.market-nav__secondary {
  border-color: rgba(255, 255, 255, 0.84);
  background: rgba(255, 255, 255, 0.58);
  backdrop-filter: blur(14px);
}

.market-nav__primary {
  --el-button-bg-color: #0f172a;
  --el-button-border-color: #0f172a;
  --el-button-hover-bg-color: #1e293b;
  --el-button-hover-border-color: #1e293b;
  --el-button-active-bg-color: #020617;
  --el-button-active-border-color: #020617;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.16);
}

.market-main {
  padding: 28px 0 56px;
}

.market-surface,
.market-card,
.market-section {
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: var(--page-surface);
  box-shadow: var(--page-shadow);
  backdrop-filter: blur(20px);
}

.market-gate__eyebrow,
.market-section__eyebrow,
.market-card__tag {
  color: var(--page-text-soft);
  font-size: 12px;
  line-height: 1;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.market-toolbar {
  display: grid;
  gap: 16px;
  padding: 22px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.66);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
}

.market-toolbar__summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.market-toolbar__stat {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.58);
}

.market-toolbar__stat strong {
  color: #0f172a;
  font-size: 28px;
  line-height: 1;
  letter-spacing: -0.05em;
  font-family: 'Avenir Next', 'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.market-toolbar__stat span {
  color: #64748b;
  font-size: 12px;
}

.market-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.market-tabs__item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.56);
  color: #475569;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease;
}

.market-tabs__item span {
  font-size: 13px;
  font-weight: 600;
}

.market-tabs__item small {
  color: inherit;
  font-size: 12px;
}

.market-tabs__item:hover,
.market-tabs__item.is-active {
  transform: translateY(-1px);
  border-color: rgba(15, 23, 42, 0.18);
}

.market-tabs__item.is-active {
  background: #0f172a;
  color: #fff;
  box-shadow: 0 14px 30px rgba(15, 23, 42, 0.16);
}

.market-gate__text,
.market-card__text {
  color: var(--page-text-muted);
  font-size: 15px;
  line-height: 1.85;
}

.market-gate__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.market-card__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.market-card__chips span {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.56);
  color: #475569;
  font-size: 12px;
}

.market-surface {
  position: relative;
  margin-top: 24px;
  padding: 24px;
  overflow: hidden;
}

.market-surface.is-locked::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.18), rgba(248, 250, 252, 0.54));
  pointer-events: none;
}

.market-gate {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 18px;
  max-width: 620px;
  margin: 24px auto;
  padding: 28px;
  border: 1px solid rgba(255, 255, 255, 0.86);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.7);
  text-align: center;
}

.market-gate__title {
  margin: 0;
  font-size: clamp(34px, 4vw, 48px);
  line-height: 1;
  letter-spacing: -0.06em;
}

.market-content {
  display: grid;
  gap: 18px;
}

.market-section {
  padding: 22px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
}

.market-section__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.market-section__title {
  margin: 12px 0 0;
  color: #0f172a;
  font-size: 34px;
  line-height: 1;
  letter-spacing: -0.05em;
}

.market-section__count {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.56);
  color: #475569;
  font-size: 12px;
}

.market-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.market-card {
  display: grid;
  gap: 14px;
  min-height: 248px;
  padding: 20px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
}

.market-card__title {
  margin: 0;
  color: #0f172a;
  font-size: 28px;
  line-height: 1.06;
  letter-spacing: -0.05em;
}

.market-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: #64748b;
  font-size: 13px;
}

.market-card__status {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.market-card__status-badge {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.market-card__status-badge.is-not_installed {
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
}

.market-card__status-badge.is-installed {
  background: rgba(34, 197, 94, 0.16);
  color: #15803d;
}

.market-card__status-badge.is-update_available {
  background: rgba(245, 158, 11, 0.18);
  color: #b45309;
}

.market-card__status-badge.is-queued,
.market-card__status-badge.is-running {
  background: rgba(59, 130, 246, 0.14);
  color: #1d4ed8;
}

.market-card__status-badge.is-failed,
.market-card__status-badge.is-timeout {
  background: rgba(239, 68, 68, 0.14);
  color: #b91c1c;
}

.market-card__status-badge.is-unknown {
  background: rgba(59, 130, 246, 0.14);
  color: #1d4ed8;
}

.market-card__status-text {
  color: #64748b;
  font-size: 13px;
}

.market-card__command {
  padding: 12px 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.04);
  overflow-x: auto;
}

.market-card__command code {
  font-size: 12px;
  color: #0f172a;
  white-space: pre-wrap;
  word-break: break-all;
}

.market-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.plugin-install-dialog {
  display: grid;
  gap: 16px;
}

.plugin-install-dialog__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: #64748b;
  font-size: 13px;
}

.plugin-install-dialog__block {
  display: grid;
  gap: 8px;
}

.plugin-install-dialog__label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.plugin-install-dialog__block code,
.plugin-install-dialog__block pre {
  margin: 0;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.05);
  color: #0f172a;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.market-loading {
  display: grid;
  gap: 10px;
  margin-top: 16px;
  padding: 0 4px;
}

.market-loading__bar {
  width: 100%;
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(56, 189, 248, 0.12), rgba(56, 189, 248, 0.58), rgba(56, 189, 248, 0.12));
  background-size: 200% 100%;
  animation: marketLoading 1.4s linear infinite;
}

.market-loading__text {
  color: #64748b;
  font-size: 13px;
}

@media (max-width: 1180px) {
  .market-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 920px) {
  .market-nav {
    flex-wrap: wrap;
    border-radius: 30px;
  }
}

@media (max-width: 720px) {
  .market-nav,
  .market-main {
    width: min(100%, calc(100% - 28px));
  }

  .market-nav__actions {
    width: 100%;
    justify-content: flex-end;
  }

  .market-toolbar__summary,
  .market-grid {
    grid-template-columns: 1fr;
  }

  .market-section__head {
    flex-direction: column;
  }

  .market-card {
    min-height: auto;
  }
}

@keyframes marketLoading {
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
  }
}
</style>
