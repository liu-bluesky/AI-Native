import { buildWsBaseUrl } from './server-profile.js'

function wsBaseUrl() {
  return buildWsBaseUrl()
}

function normalizeWsUrl(pathname, token) {
  const path = String(pathname || '').trim()
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  const url = new URL(`${wsBaseUrl()}${cleanPath}`)
  if (token) {
    url.searchParams.set('token', token)
  }
  return url.toString()
}

function createChatWsClient({
  path,
  token,
  label = '实时连接',
  onMessage,
  onOpen,
  onClose,
  onError,
  onStale,
  heartbeatIntervalMs = 30000,
  heartbeatTimeoutMs = 60000,
}) {
  const socket = new WebSocket(normalizeWsUrl(path, token))

  let openResolved = false
  let closed = false
  let heartbeatTimer = null
  let staleTimer = null
  let lastPongAt = Date.now()
  let resolveReady
  let rejectReady
  const channelLabel = String(label || '实时连接').trim() || '实时连接'
  const ready = new Promise((resolve, reject) => {
    resolveReady = resolve
    rejectReady = reject
  })

  function channelError(message) {
    const err = new Error(`${channelLabel}：${message}`)
    err.channelLabel = channelLabel
    return err
  }

  function clearHeartbeat() {
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    if (staleTimer !== null) {
      window.clearInterval(staleTimer)
      staleTimer = null
    }
  }

  function safeSend(payload) {
    if (socket.readyState !== WebSocket.OPEN) {
      return false
    }
    try {
      socket.send(JSON.stringify(payload || {}))
      return true
    } catch {
      return false
    }
  }

  function startHeartbeat() {
    clearHeartbeat()
    const intervalMs = Math.max(5000, Number(heartbeatIntervalMs || 30000))
    const timeoutMs = Math.max(intervalMs + 5000, Number(heartbeatTimeoutMs || 60000))
    lastPongAt = Date.now()
    heartbeatTimer = window.setInterval(() => {
      safeSend({
        type: 'ping',
        request_id: `ping-${Date.now().toString(36)}`,
        sent_at: Date.now(),
      })
    }, intervalMs)
    staleTimer = window.setInterval(() => {
      if (Date.now() - lastPongAt <= timeoutMs) return
      onStale?.(`${channelLabel}心跳超时（${Math.round((Date.now() - lastPongAt) / 1000)}s 未收到响应）`)
      try {
        socket.close(4000, `${channelLabel} heartbeat timeout`)
      } catch {
        // ignore close race
      }
    }, Math.min(10000, intervalMs))
  }

  socket.onopen = () => {
    openResolved = true
    closed = false
    startHeartbeat()
    resolveReady?.()
    onOpen?.()
  }
  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(String(event?.data || '{}'))
      if (String(data?.type || '').trim() === 'pong') {
        lastPongAt = Date.now()
      }
      Promise.resolve(onMessage?.(data)).catch(() => {})
    } catch {
      Promise.resolve(onMessage?.({ type: 'error', message: 'WebSocket 消息解析失败' })).catch(() => {})
    }
  }
  socket.onerror = () => {
    if (!openResolved) {
      rejectReady?.(channelError('连接失败'))
    }
    onError?.()
  }
  socket.onclose = (event) => {
    if (closed) return
    closed = true
    clearHeartbeat()
    if (!openResolved) {
      rejectReady?.(channelError(`连接已关闭（${event?.code || 1000}）`))
    }
    onClose?.(event)
  }

  return {
    ready,
    isOpen() {
      return socket.readyState === WebSocket.OPEN
    },
    send(payload) {
      if (!safeSend(payload)) {
        throw channelError('未连接')
      }
      return true
    },
    trySend(payload) {
      return safeSend(payload)
    },
    close(code = 1000, reason = 'client close') {
      clearHeartbeat()
      if (
        socket.readyState === WebSocket.CONNECTING
        || socket.readyState === WebSocket.OPEN
      ) {
        socket.close(code, reason)
      }
    },
  }
}

export function createProjectChatWsClient({
  projectId,
  token,
  onMessage,
  onOpen,
  onClose,
  onError,
  onStale,
  heartbeatIntervalMs,
  heartbeatTimeoutMs,
}) {
  return createChatWsClient({
    path: `/api/projects/${encodeURIComponent(projectId)}/chat/ws`,
    label: '项目聊天实时连接',
    token,
    onMessage,
    onOpen,
    onClose,
    onError,
    onStale,
    heartbeatIntervalMs,
    heartbeatTimeoutMs,
  })
}

export function createGlobalAssistantWsClient({ token, onMessage, onOpen, onClose, onError }) {
  return createChatWsClient({
    path: '/api/projects/chat/global/ws',
    label: '全局 AI 助手实时连接',
    token,
    onMessage,
    onOpen,
    onClose,
    onError,
  })
}

export function createMarketCliPluginWsClient({ token, onMessage, onOpen, onClose, onError }) {
  return createChatWsClient({
    path: '/api/market/cli-plugins/install-tasks/ws',
    label: '插件安装任务实时连接',
    token,
    onMessage,
    onOpen,
    onClose,
    onError,
  })
}

export function createMarketCliPluginLoginTaskWsClient({ token, onMessage, onOpen, onClose, onError }) {
  return createChatWsClient({
    path: '/api/market/cli-plugins/login-tasks/ws',
    label: '插件登录任务实时连接',
    token,
    onMessage,
    onOpen,
    onClose,
    onError,
  })
}
