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

const router = useRouter()
const ONLINE_HEARTBEAT_INTERVAL_MS = 60 * 1000
let onlineHeartbeatTimer = null
let onlineHeartbeatPending = false

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

onMounted(async () => {
  await router.isReady()

  const currentPath = router.currentRoute.value.path
  const publicPaths = new Set(['/intro', '/market', '/login', '/register'])
  const initBypassPaths = new Set(['/intro', '/market'])

  try {
    const { initialized } = await api.get('/init/status')
    if (!initialized && !initBypassPaths.has(currentPath)) {
      router.replace('/init')
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
    if (!initBypassPaths.has(currentPath)) {
      router.replace('/login')
    }
  }
})

watch(
  () => authStateVersion.value,
  () => {
    if (!getStoredToken()) {
      stopOnlineHeartbeat()
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
})
</script>
