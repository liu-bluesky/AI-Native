function wsBaseUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}`
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

export function createProjectChatWsClient({ projectId, token, onMessage, onOpen, onClose, onError }) {
  const path = `/api/projects/${encodeURIComponent(projectId)}/chat/ws`
  const socket = new WebSocket(normalizeWsUrl(path, token))

  let openResolved = false
  let resolveReady
  let rejectReady
  const ready = new Promise((resolve, reject) => {
    resolveReady = resolve
    rejectReady = reject
  })

  socket.onopen = () => {
    openResolved = true
    resolveReady?.()
    onOpen?.()
  }
  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(String(event?.data || '{}'))
      onMessage?.(data)
    } catch {
      onMessage?.({ type: 'error', message: 'WebSocket 消息解析失败' })
    }
  }
  socket.onerror = () => {
    if (!openResolved) {
      rejectReady?.(new Error('WebSocket 连接失败'))
    }
    onError?.()
  }
  socket.onclose = (event) => {
    if (!openResolved) {
      rejectReady?.(new Error(`WebSocket 已关闭（${event?.code || 1000}）`))
    }
    onClose?.(event)
  }

  return {
    ready,
    isOpen() {
      return socket.readyState === WebSocket.OPEN
    },
    send(payload) {
      if (socket.readyState !== WebSocket.OPEN) {
        throw new Error('WebSocket 未连接')
      }
      socket.send(JSON.stringify(payload || {}))
    },
    close(code = 1000, reason = 'client close') {
      if (
        socket.readyState === WebSocket.CONNECTING
        || socket.readyState === WebSocket.OPEN
      ) {
        socket.close(code, reason)
      }
    },
  }
}

