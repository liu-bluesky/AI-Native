<template>
  <router-view />
  <GlobalAiAssistant />
</template>

<script setup>
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'

import GlobalAiAssistant from './components/GlobalAiAssistant.vue'
import api from './utils/api.js'
import { syncCurrentUser } from './utils/auth.js'
import { authStateVersion, clearAuthSession, getStoredToken } from './utils/auth-storage.js'
import { getServerScopedStorageKey, serverProfileVersion } from './utils/server-profile.js'

const router = useRouter()
const ONLINE_HEARTBEAT_INTERVAL_MS = 60 * 1000
let onlineHeartbeatTimer = null
let onlineHeartbeatPending = false
const AUTH_PUBLIC_PATHS = new Set(['/loading', '/init', '/intro', '/market', '/updates', '/login', '/register'])

function stopOnlineHeartbeat() {
  if (onlineHeartbeatTimer !== null) {
    window.clearInterval(onlineHeartbeatTimer)
    onlineHeartbeatTimer = null
  }
}

async function sendOnlineHeartbeat() {
  if (!getStoredToken() || onlineHeartbeatPending) return
  onlineHeartbeatPending = true
  try {
    await api.post('/system/online-users/heartbeat', {
      current_path: router.currentRoute.value.fullPath || router.currentRoute.value.path || '',
    })
  } catch (err) {
    if (Number(err?.status || 0) !== 401) {
      console.debug('online heartbeat failed', err)
    }
  } finally {
    onlineHeartbeatPending = false
  }
}

function startOnlineHeartbeat() {
  stopOnlineHeartbeat()
  void sendOnlineHeartbeat()
  onlineHeartbeatTimer = window.setInterval(() => {
    void sendOnlineHeartbeat()
  }, ONLINE_HEARTBEAT_INTERVAL_MS)
}

function redirectToLoginIfNeeded() {
  const currentRoute = router.currentRoute.value
  const currentPath = currentRoute.path || ''
  if (AUTH_PUBLIC_PATHS.has(currentPath)) return
  router.replace({
    path: '/login',
    query: currentRoute.fullPath ? { redirect: currentRoute.fullPath } : {},
  })
}

function handleAuthStorageChange(event) {
  const key = String(event?.key || '').trim()
  if (key !== getServerScopedStorageKey('token') && key !== 'token') return
  if (getStoredToken()) return
  stopOnlineHeartbeat()
  redirectToLoginIfNeeded()
}

onMounted(async () => {
  await router.isReady()

  const currentPath = router.currentRoute.value.path
  const publicPaths = AUTH_PUBLIC_PATHS
  window.addEventListener('storage', handleAuthStorageChange)

  try {
    const { initialized, setup_required: setupRequired } = await api.get('/init/status')
    const setupRequiredValue = setupRequired === true || initialized === false
    if (currentPath === '/loading') {
      return
    }
    if (setupRequiredValue && currentPath !== '/init') {
      router.replace('/init')
      return
    }
    if (!setupRequiredValue && currentPath === '/init') {
      router.replace(getStoredToken() ? '/workbench' : '/login')
      return
    }

    const token = getStoredToken()
    if (!token && !publicPaths.has(currentPath)) {
      router.replace('/login')
      return
    }
    if (token) {
      try {
        await syncCurrentUser()
        startOnlineHeartbeat()
      } catch {
        clearAuthSession()
        stopOnlineHeartbeat()
        if (!publicPaths.has(currentPath)) {
          router.replace('/login')
        }
        return
      }
    }
  } catch {
    stopOnlineHeartbeat()
    if (!publicPaths.has(currentPath)) {
      router.replace('/login')
    }
  }
})

watch(
  () => [authStateVersion.value, serverProfileVersion.value],
  () => {
    if (!getStoredToken()) {
      stopOnlineHeartbeat()
      redirectToLoginIfNeeded()
      return
    }
    startOnlineHeartbeat()
  },
)

watch(
  () => router.currentRoute.value.fullPath,
  () => {
    if (getStoredToken()) {
      void sendOnlineHeartbeat()
    }
  },
)

onBeforeUnmount(() => {
  stopOnlineHeartbeat()
  window.removeEventListener('storage', handleAuthStorageChange)
})
</script>
