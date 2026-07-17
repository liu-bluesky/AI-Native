import { createRouter, createWebHashHistory } from 'vue-router'
import { getFallbackPath, hasPermission, isSuperAdmin, pathPermission } from '@/utils/permissions.js'
import { isChatSettingsRoutePath, resolveSettingsAwarePath } from '@/utils/chat-settings-route.js'
import api from '@/utils/api.js'
import { getStoredToken } from '@/utils/auth-storage.js'
import { resolveServerOrigin } from '@/utils/server-profile.js'

const SettingsCenterChatStub = { render: () => null }

const routes = [
  { path: '/loading', component: () => import('../views/auth/LoadingPage.vue') },
  { path: '/init', component: () => import('../views/auth/InitPage.vue') },
  { path: '/intro', component: () => import('../views/public/IntroPage.vue') },
  { path: '/market', component: () => import('../views/public/MarketPage.vue') },
  { path: '/updates', component: () => import('../views/public/ChangelogPage.vue') },
  { path: '/login', component: () => import('../views/auth/LoginPage.vue') },
  { path: '/register', component: () => import('../views/auth/RegisterPage.vue') },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/loading',
    children: [
      { path: 'workbench', component: () => import('../views/desktop/DesktopWorkbench.vue') },
      { path: 'work-logs', component: () => import('../views/desktop/ProjectWorkLog.vue') },
      { path: 'tasks', component: () => import('../views/tasks/TaskManager.vue') },
      { path: 'settings-center', component: () => import('../views/desktop/SettingsLauncher.vue') },
      { path: 'desktop/background', component: () => import('../views/desktop/DesktopWallpaperSettings.vue') },
      { path: 'desktop', redirect: '/workbench' },
      { path: 'ai/chat', component: () => import('../views/projects/ProjectChat.vue') },
      { path: 'ai/supervision', component: () => import('../views/desktop/AgentSupervision.vue') },
      {
        path: 'ai/chat/settings',
        component: () => import('../views/projects/ProjectChat.vue'),
        children: [
          { path: '', redirect: '/ai/chat/settings/chat' },
          { path: 'chat', component: SettingsCenterChatStub },
          { path: 'user/settings', component: () => import('../views/users/UserSettings.vue') },
          { path: 'system/config', component: () => import('../views/system/SystemConfig.vue') },
          { path: 'system/bot-connectors', component: () => import('../views/system/SystemBotConnectors.vue') },
          { path: 'system/ftp-credentials', component: () => import('../views/system/SystemFtpCredentials.vue') },
          { path: 'desktop/background', component: () => import('../views/desktop/DesktopWallpaperSettings.vue') },
          { path: 'changelog-entries', component: () => import('../views/system/ChangelogManager.vue') },
          { path: 'work-sessions', component: () => import('../views/system/WorkSessionManager.vue') },
          { path: 'statistics', component: () => import('../views/system/StatisticsDashboard.vue') },
          { path: 'online-users', component: () => import('../views/system/OnlineUserManager.vue'), meta: { superAdminOnly: true } },
          { path: 'mcp-monitor', component: () => import('../views/system/McpMonitorManager.vue'), meta: { superAdminOnly: true } },
          { path: 'dictionaries', component: () => import('../views/system/DictionaryManager.vue') },
          { path: 'llm/providers', component: () => import('../views/llm/ModelProviderManager.vue') },
          { path: 'projects', component: () => import('../views/projects/ProjectList.vue') },
          { path: 'projects/:id', component: () => import('../views/projects/ProjectDetail.vue') },
          { path: 'agent-templates', component: () => import('../views/agent-templates/AgentTemplateList.vue') },
          { path: 'employees', component: () => import('../views/employees/EmployeeList.vue') },
          { path: 'employees/create', component: () => import('../views/employees/EmployeeForm.vue') },
          { path: 'employees/:id/edit', component: () => import('../views/employees/EmployeeForm.vue') },
          { path: 'employees/:id/usage', component: () => import('../views/employees/EmployeeUsage.vue') },
          { path: 'employees/:id', component: () => import('../views/employees/EmployeeDetail.vue') },
          { path: 'skill-resources', component: () => import('../views/skills/SkillResourceList.vue') },
          { path: 'skill-resources/:source/:slug(.*)', component: () => import('../views/skills/SkillResourceDetail.vue') },
          { path: 'skills', component: () => import('../views/skills/SkillList.vue') },
          { path: 'skills/create', component: () => import('../views/skills/SkillCreate.vue') },
          { path: 'skills/:id/edit', component: () => import('../views/skills/SkillEdit.vue') },
          { path: 'skills/:id', component: () => import('../views/skills/SkillDetail.vue') },
          { path: 'rules', component: () => import('../views/rules/RuleList.vue') },
          { path: 'rules/create', component: () => import('../views/rules/RuleCreate.vue') },
          { path: 'rules/:id/edit', component: () => import('../views/rules/RuleEdit.vue') },
          { path: 'rules/:id', component: () => import('../views/rules/RuleDetail.vue') },
          { path: 'memory/:id', component: () => import('../views/memory/MemoryManager.vue') },
          { path: 'usage/keys', component: () => import('../views/usage/ApiKeyList.vue') },
          { path: 'feedback/:id', component: () => import('../views/evolution/FeedbackTicketList.vue') },
          { path: 'feedback/:id/batch-analyze', component: () => import('../views/evolution/FeedbackBatchAnalyze.vue') },
          { path: 'feedback/:id/:feedbackId', component: () => import('../views/evolution/FeedbackDetail.vue') },
          { path: 'users', component: () => import('../views/users/UserList.vue') },
          { path: 'departments', component: () => import('../views/users/DepartmentManager.vue') },
          { path: 'roles', component: () => import('../views/users/RoleList.vue') },
        ],
      },
      { path: 'users', component: () => import('../views/users/UserList.vue') },
      { path: 'departments', component: () => import('../views/users/DepartmentManager.vue') },
      { path: 'roles', component: () => import('../views/users/RoleList.vue') },
      { path: 'user/settings', component: () => import('../views/users/UserSettings.vue') },
      { path: 'projects', component: () => import('../views/projects/ProjectList.vue') },
      { path: 'projects/:id', component: () => import('../views/projects/ProjectDetail.vue') },
      {
        path: 'materials',
        component: () => import('../views/projects/ProjectCreationWorkspace.vue'),
        children: [
          { path: '', redirect: { path: '/materials/voices' } },
          { path: 'voices', component: () => import('../views/projects/ProjectVoiceLibrary.vue') },
        ],
      },
      { path: 'system/config', component: () => import('../views/system/SystemConfig.vue') },
      { path: 'system/bot-connectors', component: () => import('../views/system/SystemBotConnectors.vue') },
      { path: 'system/ftp-credentials', component: () => import('../views/system/SystemFtpCredentials.vue') },
      { path: 'changelog-entries', component: () => import('../views/system/ChangelogManager.vue') },
      { path: 'work-sessions', component: () => import('../views/system/WorkSessionManager.vue') },
      { path: 'statistics', component: () => import('../views/system/StatisticsDashboard.vue') },
      { path: 'online-users', component: () => import('../views/system/OnlineUserManager.vue'), meta: { superAdminOnly: true } },
      { path: 'mcp-monitor', component: () => import('../views/system/McpMonitorManager.vue'), meta: { superAdminOnly: true } },
      { path: 'dictionaries', component: () => import('../views/system/DictionaryManager.vue') },
      { path: 'employees', component: () => import('../views/employees/EmployeeList.vue') },
      { path: 'agent-templates', component: () => import('../views/agent-templates/AgentTemplateList.vue') },
      { path: 'employees/create', component: () => import('../views/employees/EmployeeForm.vue') },
      { path: 'employees/:id/edit', component: () => import('../views/employees/EmployeeForm.vue') },
      { path: 'employees/:id/usage', component: () => import('../views/employees/EmployeeUsage.vue') },
      { path: 'employees/:id', component: () => import('../views/employees/EmployeeDetail.vue') },
      { path: 'skill-resources', component: () => import('../views/skills/SkillResourceList.vue') },
      { path: 'skill-resources/:source/:slug(.*)', component: () => import('../views/skills/SkillResourceDetail.vue') },
      { path: 'skills', component: () => import('../views/skills/SkillList.vue') },
      { path: 'skills/create', component: () => import('../views/skills/SkillCreate.vue') },
      { path: 'skills/:id/edit', component: () => import('../views/skills/SkillEdit.vue') },
      { path: 'skills/:id', component: () => import('../views/skills/SkillDetail.vue') },
      { path: 'rules', component: () => import('../views/rules/RuleList.vue') },
      { path: 'rules/create', component: () => import('../views/rules/RuleCreate.vue') },
      { path: 'rules/:id/edit', component: () => import('../views/rules/RuleEdit.vue') },
      { path: 'rules/:id', component: () => import('../views/rules/RuleDetail.vue') },
      { path: 'memory/:id', component: () => import('../views/memory/MemoryManager.vue') },
      { path: 'usage/keys', component: () => import('../views/usage/ApiKeyList.vue') },
      { path: 'llm/providers', component: () => import('../views/llm/ModelProviderManager.vue') },
      { path: 'market', component: () => import('../views/public/MarketPage.vue') },
      { path: 'feedback/:id', component: () => import('../views/evolution/FeedbackTicketList.vue') },
      { path: 'feedback/:id/batch-analyze', component: () => import('../views/evolution/FeedbackBatchAnalyze.vue') },
      { path: 'feedback/:id/:feedbackId', component: () => import('../views/evolution/FeedbackDetail.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

const PUBLIC_PATHS = new Set(['/loading', '/init', '/intro', '/market', '/updates', '/login', '/register'])
const OFFLINE_DESKTOP_STARTUP_STORAGE_KEY = 'desktop_offline_startup'
const DESKTOP_OFFLINE_MODE_STORAGE_KEY = 'desktop_offline_mode'
let initializationStatus = null
let initializationStatusPromise = null
let initializationStatusOrigin = ''
let pendingOfflineDesktopStartup = false

export function markSystemInitialized() {
  initializationStatus = true
  initializationStatusPromise = null
}

async function isSystemInitialized() {
  const currentOrigin = resolveServerOrigin()
  if (initializationStatusOrigin !== currentOrigin) {
    initializationStatus = null
    initializationStatusPromise = null
    initializationStatusOrigin = currentOrigin
  }
  if (initializationStatus !== null) {
    return initializationStatus
  }
  if (!initializationStatusPromise) {
    initializationStatusPromise = api
      .get('/init/status')
      .then(({ initialized, setup_required: setupRequired }) => {
        initializationStatus = setupRequired === true ? false : Boolean(initialized)
        return initializationStatus
      })
      .finally(() => {
        initializationStatusPromise = null
      })
  }
  return initializationStatusPromise
}

function hasOfflineDesktopChatEntry() {
  try {
    return Boolean(
      getStoredToken() ||
        String(window.localStorage?.getItem('project_id') || '').trim() ||
        String(window.localStorage?.getItem('liuagent:cached-project-list') || '').trim(),
    )
  } catch {
    return Boolean(getStoredToken())
  }
}

function consumeOfflineDesktopStartupFlag() {
  try {
    if (window.sessionStorage?.getItem(OFFLINE_DESKTOP_STARTUP_STORAGE_KEY) !== '1') {
      return false
    }
    window.sessionStorage.removeItem(OFFLINE_DESKTOP_STARTUP_STORAGE_KEY)
    return true
  } catch {
    return false
  }
}

function isDesktopOfflineMode() {
  try {
    return window.sessionStorage?.getItem(DESKTOP_OFFLINE_MODE_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

function isEmbeddedDesktopRoute(routeLocation = {}) {
  try {
    return (
      String(routeLocation?.query?.embedded || '').trim() === '1' ||
      new URLSearchParams(window.location.search).get('embedded') === '1'
    )
  } catch {
    return false
  }
}

router.beforeEach(async (to, from) => {
  const normalizedPath = String(to.path || '').trim() || '/'
  let backendUnavailableForRoute = false

  if (normalizedPath === '/') {
    if (hasOfflineDesktopChatEntry()) {
      pendingOfflineDesktopStartup = true
      return '/workbench'
    }
    return { path: '/loading', query: { offline_entry: '1' } }
  }

  if (normalizedPath === '/loading') {
    return true
  }

  const skipStartupStatusCheck =
    isEmbeddedDesktopRoute(to) ||
    (
      normalizedPath === '/workbench' &&
      (pendingOfflineDesktopStartup || consumeOfflineDesktopStartupFlag())
    )
  if (skipStartupStatusCheck) {
    pendingOfflineDesktopStartup = false
  } else {
    try {
      const initialized = await isSystemInitialized()
      if (!initialized && normalizedPath !== '/init') {
        return '/init'
      }
      if (initialized && normalizedPath === '/init') {
        return getStoredToken() ? getFallbackPath() : '/login'
      }
    } catch {
      backendUnavailableForRoute = true
      if (normalizedPath === '/') {
        return '/init'
      }
    }
  }

  const token = getStoredToken()
  const isPublic = PUBLIC_PATHS.has(normalizedPath)
  const bypassDesktopFallbacks = backendUnavailableForRoute || isDesktopOfflineMode()
  const allowOfflineDesktopShell =
    skipStartupStatusCheck && (normalizedPath === '/workbench' || isEmbeddedDesktopRoute(to))
  const allowOfflineDesktopLocalApp =
    (normalizedPath.startsWith('/ai/chat') || normalizedPath.startsWith('/ai/supervision'))
    && hasOfflineDesktopChatEntry()

  if (!token && !isPublic && !allowOfflineDesktopShell && !allowOfflineDesktopLocalApp) {
    return '/login'
  }

  if (token && (normalizedPath === '/login' || normalizedPath === '/register')) {
    return getFallbackPath()
  }

  if (isEmbeddedDesktopRoute(to)) {
    return true
  }

  if (
    !bypassDesktopFallbacks &&
    isChatSettingsRoutePath(from.path) &&
    !isChatSettingsRoutePath(to.path) &&
    to.path.startsWith('/') &&
    to.path !== '/ai/chat'
    && to.path !== '/ai/supervision'
    && to.path !== '/workbench'
  ) {
    const rewritten = resolveSettingsAwarePath(from.path, to.path, to.path)
    if (rewritten !== to.path) {
      return {
        path: rewritten,
        query: to.query,
        hash: to.hash,
      }
    }
  }

  const requiredPermission = pathPermission(to.path)
  if (!bypassDesktopFallbacks && requiredPermission && !hasPermission(requiredPermission)) {
    const fallback = getFallbackPath()
    if (fallback === to.path) {
      return '/login'
    }
    return fallback
  }

  if (
    !bypassDesktopFallbacks &&
    to.matched.some((record) => record.meta?.superAdminOnly) &&
    !isSuperAdmin()
  ) {
    const fallback = getFallbackPath()
    if (fallback === to.path) {
      return '/ai/chat'
    }
    return fallback
  }

  return true
})

export default router
