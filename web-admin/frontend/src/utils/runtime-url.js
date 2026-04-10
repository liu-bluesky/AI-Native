import api from '@/utils/api.js'

function normalizePath(pathname) {
  const path = String(pathname || '').trim()
  if (!path) return '/'
  return path.startsWith('/') ? path : `/${path}`
}

function normalizeOrigin(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

function currentOrigin() {
  if (typeof window === 'undefined' || !window.location?.origin) {
    return ''
  }
  return normalizeOrigin(window.location.origin)
}

let configuredRuntimeOrigin = ''
let configuredRuntimeOriginPromise = null

export function setConfiguredRuntimeOrigin(origin) {
  configuredRuntimeOrigin = normalizeOrigin(origin)
  return configuredRuntimeOrigin
}

export async function fetchConfiguredRuntimeOrigin({ force = false } = {}) {
  if (!force && configuredRuntimeOrigin) return configuredRuntimeOrigin
  if (!force && configuredRuntimeOriginPromise) return configuredRuntimeOriginPromise
  configuredRuntimeOriginPromise = (async () => {
    try {
      const data = await api.get('/projects/query-mcp/runtime')
      return setConfiguredRuntimeOrigin(data?.runtime?.origin || '')
    } catch {
      return configuredRuntimeOrigin || currentOrigin()
    } finally {
      configuredRuntimeOriginPromise = null
    }
  })()
  return configuredRuntimeOriginPromise
}

export function buildRuntimeUrl(pathname, originOverride = '') {
  const origin =
    normalizeOrigin(originOverride) || configuredRuntimeOrigin || currentOrigin()
  const path = normalizePath(pathname)
  if (!origin) return path
  return `${origin}${path}`
}
