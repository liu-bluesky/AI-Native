import { createRouter, createWebHashHistory } from 'vue-router'
import { getFallbackPath } from '@/utils/permissions.js'
import { isChatSettingsRoutePath, resolveSettingsAwarePath } from '@/utils/chat-settings-route.js'
import api from '@/utils/api.js'
import { getStoredToken, isExternalAuthSession } from '@/utils/auth-storage.js'
import { resolveServerOrigin } from '@/utils/server-profile.js'

const SettingsCenterChatStub = { render: () => null }

const routes = [
  { path: '/loading', component: () => import('../views/auth/LoadingPage.vue') },
  { path: '/init', component: () => import('../views/auth/InitPage.vue') },
  { path: '/intro', component: () => import('../views/public/IntroPage.vue') },
  { path: '/updates', component: () => import('../views/public/ChangelogPage.vue') },
  { path: '/login', component: () => import('../views/auth/LoginPage.vue') },
  { path: '/register', component: () => import('../views/auth/RegisterPage.vue') },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/loading',
    children: [
      { path: 'workbench', component: () => import('../views/desktop/DesktopWorkbench.vue') },
      { path: 'desktop', redirect: '/workbench' },
      { path: 'ai/chat', component: () => import('../views/projects/ProjectChat.vue') },
      { path: 'projects', component: () => import('../views/projects/ProjectList.vue') },
      { path: 'projects/:id', component: () => import('../views/projects/ProjectDetail.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

const PUBLIC_PATHS = new Set(['/loading', '/init', '/intro', '/updates', '/login', '/register'])
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
  if (isExternalAuthSession()) return true
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

  return true
})

export default router
