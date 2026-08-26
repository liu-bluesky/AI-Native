import { createMemoryHistory, createRouter, createWebHashHistory } from 'vue-router'
import { getFallbackPath } from '@/utils/permissions.js'
import { isChatSettingsRoutePath, resolveSettingsAwarePath } from '@/utils/chat-settings-route.js'
import { getStoredToken } from '@/utils/auth-storage.js'
import { isLocalProjectMode } from '@/services/local-project-repository.js'

const createPublicRoutes = () => [
  { path: '/loading', component: () => import('../views/auth/LoadingPage.vue') },
  { path: '/init', component: () => import('../views/auth/InitPage.vue') },
  { path: '/intro', component: () => import('../views/public/IntroPage.vue') },
  { path: '/market', component: () => import('../views/public/MarketPage.vue') },
  { path: '/updates', component: () => import('../views/public/ChangelogPage.vue') },
  { path: '/login', component: () => import('../views/auth/LoginPage.vue') },
  { path: '/register', component: () => import('../views/auth/RegisterPage.vue') },
]

const createDesktopAppRoutes = () => [
      { path: 'workbench', component: () => import('../views/desktop/DesktopWorkbench.vue') },
      { path: 'desktop/task-manager', component: () => import('../views/desktop/DesktopTaskManager.vue') },
      { path: 'work-logs', component: () => import('../views/desktop/ProjectWorkLog.vue') },
      { path: 'tasks', component: () => import('../views/tasks/TaskManager.vue') },
      { path: 'feedback', component: () => import('../views/desktop/DesktopFeedback.vue') },
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
          { path: 'chat', component: { render: () => null } },
          { path: 'system/config', component: () => import('../views/system/SystemConfig.vue') },
          { path: 'system/bot-connectors', component: () => import('../views/system/SystemBotConnectors.vue') },
          { path: 'system/ftp-credentials', component: () => import('../views/system/SystemFtpCredentials.vue') },
          { path: 'desktop/background', component: () => import('../views/desktop/DesktopWallpaperSettings.vue') },
          { path: 'changelog-entries', component: () => import('../views/system/ChangelogManager.vue') },
          { path: 'llm/providers', component: () => import('../views/llm/ModelProviderManager.vue') },
          { path: 'projects', component: () => import('../views/projects/ProjectList.vue') },
          { path: 'projects/:id', component: () => import('../views/projects/ProjectDetail.vue') },
          { path: 'employees', component: () => import('../views/employees/EmployeeList.vue') },
          { path: 'employees/create', component: () => import('../views/employees/EmployeeCreate.vue') },
          { path: 'employees/:id/edit', component: () => import('../views/employees/EmployeeEdit.vue') },
          { path: 'employees/:id/usage', component: () => import('../views/employees/EmployeeUsage.vue') },
          { path: 'employees/:id', component: () => import('../views/employees/EmployeeDetail.vue') },
          { path: 'memory/:id', component: () => import('../views/memory/MemoryManager.vue') },
        ],
      },
      { path: 'projects', component: () => import('../views/projects/ProjectList.vue') },
      { path: 'projects/:id', component: () => import('../views/projects/ProjectDetail.vue') },
      { path: 'employees', component: () => import('../views/employees/EmployeeList.vue') },
      { path: 'employees/create', component: () => import('../views/employees/EmployeeCreate.vue') },
      { path: 'employees/:id/edit', component: () => import('../views/employees/EmployeeEdit.vue') },
      { path: 'employees/:id/usage', component: () => import('../views/employees/EmployeeUsage.vue') },
      { path: 'employees/:id', component: () => import('../views/employees/EmployeeDetail.vue') },
      { path: 'memory/:id', component: () => import('../views/memory/MemoryManager.vue') },
      { path: 'system/config', component: () => import('../views/system/SystemConfig.vue') },
      { path: 'system/bot-connectors', component: () => import('../views/system/SystemBotConnectors.vue') },
      { path: 'system/ftp-credentials', component: () => import('../views/system/SystemFtpCredentials.vue') },
      { path: 'changelog-entries', component: () => import('../views/system/ChangelogManager.vue') },
  { path: 'llm/providers', component: () => import('../views/llm/ModelProviderManager.vue') },
]

function createDesktopWindowRoutes() {
  return [
    ...createPublicRoutes(),
    { path: '/', redirect: '/workbench' },
    ...createDesktopAppRoutes().map((route) => ({
      ...route,
      path: `/${String(route.path || '').replace(/^\/+/, '')}`,
    })),
  ]
}

const routes = [
  ...createPublicRoutes(),
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/loading',
    children: createDesktopAppRoutes(),
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export function createDesktopWindowRouter(windowId = '') {
  const desktopRouter = createRouter({
    history: createMemoryHistory(),
    routes: createDesktopWindowRoutes(),
  })
  Object.defineProperty(desktopRouter, '__aiEmployeeDesktopWindow', {
    value: { windowId: String(windowId || '').trim() },
    configurable: true,
  })
  return desktopRouter
}

const PUBLIC_PATHS = new Set(['/loading', '/init', '/intro', '/market', '/updates', '/login', '/register'])
const OFFLINE_DESKTOP_STARTUP_STORAGE_KEY = 'desktop_offline_startup'
let pendingOfflineDesktopStartup = false

export function markSystemInitialized() {
  // Initialization belongs to the removed server-side setup flow.
}

async function isSystemInitialized() {
  return isLocalProjectMode()
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

function isEmbeddedDesktopRoute(routeLocation = {}) {
  try {
    const embedded =
      String(routeLocation?.query?.embedded || '').trim() === '1' ||
      new URLSearchParams(window.location.search).get('embedded') === '1'
    return embedded && window.parent && window.parent !== window
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
  const allowOfflineDesktopShell =
    skipStartupStatusCheck && normalizedPath === '/workbench' && Boolean(token)
  const allowOfflineDesktopLocalApp =
    Boolean(token) &&
    (normalizedPath.startsWith('/ai/chat') || normalizedPath.startsWith('/ai/supervision'))
    && hasOfflineDesktopChatEntry()

  if (!token && !isPublic && !allowOfflineDesktopShell && !allowOfflineDesktopLocalApp) {
    return '/login'
  }

  if (
    token &&
    !isEmbeddedDesktopRoute(to) &&
    (normalizedPath === '/login' || normalizedPath === '/register')
  ) {
    return getFallbackPath()
  }

  if (isEmbeddedDesktopRoute(to)) {
    return true
  }

  if (
    !backendUnavailableForRoute &&
    isChatSettingsRoutePath(from.path) &&
    !isChatSettingsRoutePath(to.path) &&
    to.path.startsWith('/') &&
    to.path !== '/ai/chat' &&
    to.path !== '/ai/supervision' &&
    to.path !== '/workbench'
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

  return true
})

export default router
