<template>
  <router-view />
</template>

<script setup>
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  authStateVersion,
  getStoredToken,
} from './utils/auth-storage.js'
import {
  getServerScopedStorageKey,
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
import {
  canUseDesktopUpdater,
  checkDesktopUpdate,
  downloadDesktopUpdate,
} from './utils/desktop-updater.js'
import {
  resolveLocalMainModelRuntime,
} from './services/local-main-model-runtime.js'

const router = useRouter()
let onlineHeartbeatTimer = null
let localBotSyncTimer = null
let localBotSyncPending = false
let desktopUpdateCheckStarted = false
const AUTH_PUBLIC_PATHS = new Set(['/loading', '/init', '/intro', '/market', '/updates', '/login', '/register'])

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

function stopOnlineHeartbeat() {
  if (onlineHeartbeatTimer !== null) {
    window.clearInterval(onlineHeartbeatTimer)
    onlineHeartbeatTimer = null
  }
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

function buildConnectorModelRuntime(connector = {}) {
  void connector
  try {
    return resolveLocalMainModelRuntime()
  } catch (error) {
    throw new Error(
      `系统主对话模型未配置可用运行时（${connectorString(
        error?.message,
        "请先在主对话模型设置中配置模型",
      )}）`,
    )
  }
}

function emitLocalBotRuntimeDiagnostic(connector, error) {
  const detail = {
    connectorId: connectorString(connector?.id),
    message: connectorString(error?.message || error, "机器人未启动：缺少本地模型运行时"),
  }
  console.warn("skip desktop feishu bot listener without local model runtime", detail)
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent("local-bot-runtime-diagnostic", { detail }),
    )
  }
}

function resolveRunnableLocalBotListeners(connectors) {
  const runnable = []
  for (const connector of Array.isArray(connectors) ? connectors : []) {
    const connectorId = connectorString(connector?.id)
    if (!connectorId) continue
    try {
      const modelRuntime = buildConnectorModelRuntime(connector)
      if (!modelRuntime) {
        emitLocalBotRuntimeDiagnostic(connector)
        continue
      }
      runnable.push({ connector, connectorId, modelRuntime })
    } catch (error) {
      emitLocalBotRuntimeDiagnostic(connector, error)
    }
  }
  return runnable
}

function connectorRuntimeLabel(connector) {
  return connectorString(
    connector?.name || connector?.id,
    "未命名机器人",
  )
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
  if (
    !hasNativeDesktopBridge() ||
    localBotSyncPending
  ) return
  localBotSyncPending = true
  try {
    const configData = await readGlobalBotConnectorConfigFile()
    const connectors = Array.isArray(configData?.config?.connectors)
      ? configData.config.connectors
      : []
    const enabled = connectors.filter(connectorEnabledForLocalFeishu)
    const runnable = resolveRunnableLocalBotListeners(enabled)
    const listeners = await listNativeFeishuLocalBotListeners()
    for (const listener of Array.isArray(listeners) ? listeners : []) {
      const connectorId = connectorString(listener?.connectorId || listener?.connector_id)
      if (!connectorId) continue
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
    for (const item of runnable) {
      const { connector, connectorId, modelRuntime } = item
      try {
        await startNativeFeishuLocalBotListener({
          connectorId,
          modelRuntime,
          mcpConfig,
          permissionDecision: null,
        })
      } catch (err) {
        console.warn(
          `start desktop feishu bot listener failed for ${connectorRuntimeLabel(connector)}`,
          err,
        )
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
  return
}

async function checkForDesktopUpdate() {
  if (
    desktopUpdateCheckStarted ||
    router.currentRoute.value.path === '/updates' ||
    !canUseDesktopUpdater()
  ) return
  desktopUpdateCheckStarted = true
  try {
    const update = await checkDesktopUpdate()
    const version = String(update?.version || '').trim()
    if (!version) return
    const promptKey = `desktop_update_prompted:${version}`
    try {
      if (window.sessionStorage.getItem(promptKey) === '1') return
      window.sessionStorage.setItem(promptKey, '1')
    } catch {
      // Session storage is optional; the update prompt can still continue.
    }
    const notes = String(update?.notes || '').trim()
    const message = notes ? `发现新版本 ${version}\n\n${notes}` : `发现新版本 ${version}`
    try {
      await ElMessageBox.confirm(message, '版本更新', {
        type: 'info',
        confirmButtonText: '打开下载',
        cancelButtonText: '稍后提醒',
        distinguishCancelAndClose: true,
      })
    } catch {
      return
    }

    try {
      await downloadDesktopUpdate(update)
      ElMessage.success('已打开系统浏览器，请下载对应版本的安装包')
    } catch (error) {
      const detail = String(error?.message || error || '').trim()
      ElMessage.error(detail || '版本更新失败，请稍后重试')
    }
  } catch (error) {
    console.debug('desktop update check skipped', error)
  }
}

onMounted(async () => {
  await router.isReady()

  const embeddedDesktopRoute = isEmbeddedDesktopRoute(router.currentRoute.value)
  window.addEventListener('storage', handleAuthStorageChange)
  window.addEventListener('keydown', handleGlobalFeedbackShortcut)

  if (!embeddedDesktopRoute && router.currentRoute.value.path !== '/updates') {
    void checkForDesktopUpdate()
  }

  scheduleLocalBotListenerSync()
})

watch(
  () => [authStateVersion.value, serverProfileVersion.value],
  () => {
    stopOnlineHeartbeat()
    scheduleLocalBotListenerSync()
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
