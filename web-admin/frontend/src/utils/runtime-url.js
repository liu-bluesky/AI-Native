import { buildServerUrl, resolveServerOrigin } from '@/utils/server-profile.js'

function normalizePath(pathname) {
  const path = String(pathname || '').trim()
  if (!path) return '/'
  return path.startsWith('/') ? path : `/${path}`
}

function normalizeOrigin(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

function currentOrigin() {
  return normalizeOrigin(resolveServerOrigin())
}

let configuredRuntimeOrigin = ''

export function setConfiguredRuntimeOrigin(origin) {
  configuredRuntimeOrigin = normalizeOrigin(origin)
  return configuredRuntimeOrigin
}

export async function fetchConfiguredRuntimeOrigin({ force = false } = {}) {
  // Remote runtime discovery was part of the removed backend project flow.
  // Keep this helper async for callers while resolving only from local state.
  if (force || !configuredRuntimeOrigin) {
    setConfiguredRuntimeOrigin(currentOrigin())
  }
  return configuredRuntimeOrigin || currentOrigin()
}

export function buildRuntimeUrl(pathname, originOverride = '') {
  const origin =
    normalizeOrigin(originOverride) || configuredRuntimeOrigin || currentOrigin()
  const path = normalizePath(pathname)
  if (!origin) return path
  if (origin === currentOrigin()) return buildServerUrl(path, origin)
  return `${origin}${path}`
}
