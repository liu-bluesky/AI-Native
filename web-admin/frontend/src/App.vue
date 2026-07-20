<template>
  <router-view />
</template>

<script setup>
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'

import api from './utils/api.js'
import { syncCurrentUser } from './utils/auth.js'
import { authStateVersion, clearAuthSession, getStoredToken } from './utils/auth-storage.js'
import {
  buildApiBaseUrl,
  getServerScopedStorageKey,
  resolveServerOrigin,
  serverProfileVersion,
} from './utils/server-profile.js'
import {
  readGlobalBotConnectorConfigFile,
  readGlobalMcpConfigFile,
} from './modules/project-chat/services/projectChatStorage.js'
import {
  hasNativeDesktopBridge,
  listNativeFeishuLocalBotListeners,
  startNativeFeishuLocalBotListener,
  stopNativeFeishuLocalBotListener,
} from './utils/native-desktop-bridge.js'

const router = useRouter()
const ONLINE_HEARTBEAT_INTERVAL_MS = 60 * 1000
let onlineHeartbeatTimer = null
let onlineHeartbeatPending = false
let localBotSyncTimer = null
let localBotSyncPending = false
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

function buildDesktopBackendApiBaseUrl() {
  const baseUrl = String(buildApiBaseUrl() || '').trim()
  if (/^https?:\/\//i.test(baseUrl)) return baseUrl
  const origin = String(resolveServerOrigin() || '').trim()
  if (/^https?:\/\//i.test(origin)) {
    return `${origin.replace(/\/+$/, '')}/${baseUrl.replace(/^\/+/, '')}`
  }
  return baseUrl
}

function connectorString(value, fallback = '') {
  const normalized = String(value || '').trim()
  return normalized || String(fallback || '').trim()
}

function connectorEnabledForLocalFeishu(connector = {}) {
  return (
    connector?.enabled !== false &&
    connector?.auto_start_worker === true &&
    connectorString(connector.platform).toLowerCase() === 'feishu' &&
    connectorString(connector.event_receive_mode || connector.eventReceiveMode).toLowerCase() === 'long_connection' &&
    connectorString(connector.id)
  )
}

async function fetchDesktopModelRuntime(providerId) {
  const normalizedProviderId = connectorString(providerId)
  if (!normalizedProviderId) return null
  const data = await api.get(
    `/llm/providers/${encodeURIComponent(normalizedProviderId)}/desktop-runtime`,
  )
  const runtime = data?.runtime && typeof data.runtime === 'object' ? data.runtime : {}
  const baseUrl = connectorString(runtime.base_url || runtime.baseUrl)
  const apiKey = connectorString(runtime.api_key || runtime.apiKey)
  if (!baseUrl || !apiKey) {
    throw new Error(`机器人模型供应商缺少桌面运行时：${normalizedProviderId}`)
  }
  return runtime
}

async function buildConnectorModelRuntime(connector = {}) {
  const existing =
    connector?.model_runtime && typeof connector.model_runtime === 'object'
      ? connector.model_runtime
      : connector?.modelRuntime && typeof connector.modelRuntime === 'object'
        ? connector.modelRuntime
        : null
  if (existing?.baseUrl || existing?.base_url) return existing
  const providerId = connectorString(connector.provider_id || connector.providerId)
  if (!providerId) return null
  const runtime = await fetchDesktopModelRuntime(providerId)
  const modelName = connectorString(
    connector.model_name || connector.modelName,
    runtime?.model_name || runtime?.modelName || runtime?.default_model || runtime?.defaultModel,
  )
  if (!modelName) {
    throw new Error(`机器人模型供应商缺少可用模型名：${providerId}`)
  }
  return {
    mode: 'direct-openai-compatible',
    providerId,
    modelName,
    baseUrl: connectorString(runtime.base_url || runtime.baseUrl),
    apiKey: connectorString(runtime.api_key || runtime.apiKey),
    temperature:
      Number.isFinite(Number(runtime.temperature)) && runtime.temperature !== ''
        ? Number(runtime.temperature)
        : null,
  }
}

function scheduleLocalBotListenerSync() {
  if (!hasNativeDesktopBridge()) return
  if (localBotSyncTimer !== null) {
    window.clearTimeout(localBotSyncTimer)
  }
  localBotSyncTimer = window.setTimeout(() => {
    localBotSyncTimer = null
    void syncLocalBotListeners()
  }, 500)
}

async function syncLocalBotListeners() {
  if (!hasNativeDesktopBridge() || !getStoredToken() || localBotSyncPending) return
  localBotSyncPending = true
  try {
    const configData = await readGlobalBotConnectorConfigFile()
    const connectors = Array.isArray(configData?.config?.connectors)
      ? configData.config.connectors
      : []
    const enabled = connectors.filter(connectorEnabledForLocalFeishu)
    const enabledIds = new Set(enabled.map((item) => connectorString(item.id)).filter(Boolean))
    const listeners = await listNativeFeishuLocalBotListeners()
    for (const listener of Array.isArray(listeners) ? listeners : []) {
      const connectorId = connectorString(listener?.connectorId || listener?.connector_id)
      if (!connectorId || enabledIds.has(connectorId)) continue
      try {
        await stopNativeFeishuLocalBotListener(connectorId)
      } catch (err) {
        console.warn('stop desktop feishu bot listener failed', err)
      }
    }

    const mcpData = await readGlobalMcpConfigFile()
    const mcpConfig = mcpData?.config && typeof mcpData.config === 'object'
      ? mcpData.config
      : {}
    for (const connector of enabled) {
      const connectorId = connectorString(connector.id)
      if (!connectorId) continue
      try {
        const modelRuntime = await buildConnectorModelRuntime(connector)
        await startNativeFeishuLocalBotListener({
          connectorId,
          workspacePath: '',
          ownerUsername: connectorString(
            window.localStorage?.getItem(getServerScopedStorageKey('username')) ||
              window.localStorage?.getItem('username'),
          ),
          modelRuntime,
          mcpConfig,
          backendContext: {
            apiBaseUrl: buildDesktopBackendApiBaseUrl(),
            token: getStoredToken(),
          },
          permissionDecision: null,
        })
      } catch (err) {
        console.warn('start desktop feishu bot listener failed', err)
      }
    }
  } finally {
    localBotSyncPending = false
  }
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

function handleGlobalFeedbackShortcut(event) {
  if (!event.altKey || !event.shiftKey || String(event.key).toLowerCase() !== 'f') return
  event.preventDefault()
  if (getStoredToken()) router.push('/feedback?mode=create&source=global_shortcut')
}

onMounted(async () => {
  await router.isReady()

  const currentPath = router.currentRoute.value.path
  const publicPaths = AUTH_PUBLIC_PATHS
  window.addEventListener('storage', handleAuthStorageChange)
  window.addEventListener('keydown', handleGlobalFeedbackShortcut)

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
        scheduleLocalBotListenerSync()
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
    scheduleLocalBotListenerSync()
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
  if (localBotSyncTimer !== null) {
    window.clearTimeout(localBotSyncTimer)
    localBotSyncTimer = null
  }
  stopOnlineHeartbeat()
  window.removeEventListener('storage', handleAuthStorageChange)
  window.removeEventListener('keydown', handleGlobalFeedbackShortcut)
  window.removeEventListener('local-bot-connectors-config-updated', scheduleLocalBotListenerSync)
})

onMounted(() => {
  window.addEventListener('local-bot-connectors-config-updated', scheduleLocalBotListenerSync)
})
</script>
