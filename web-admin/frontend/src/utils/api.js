import axios from 'axios'

import { clearAuthSession, getStoredToken } from './auth-storage.js'
import { buildApiBaseUrl } from './server-profile.js'

const api = axios.create({ baseURL: buildApiBaseUrl() })
const AUTH_PUBLIC_PATHS = new Set(['/loading', '/init', '/intro', '/market', '/updates', '/login', '/register'])
const DESKTOP_OFFLINE_MODE_STORAGE_KEY = 'desktop_offline_mode'

function normalizeHashPath(hash) {
  return String(hash || '#/intro')
    .replace(/^#/, '')
    .split('?')[0]
    .split('#')[0]
    .trim() || '/intro'
}

function redirectToLogin() {
  if (typeof window === 'undefined') return
  const loginHash = '#/login'
  try {
    const targetWindow = window.parent && window.parent !== window ? window.parent : window
    const currentPath = normalizeHashPath(targetWindow.location.hash)
    if (!AUTH_PUBLIC_PATHS.has(currentPath)) {
      targetWindow.location.hash = loginHash
    }
  } catch {
    const currentPath = normalizeHashPath(window.location.hash)
    if (!AUTH_PUBLIC_PATHS.has(currentPath)) {
      window.location.hash = loginHash
    }
  }
}

function normalizeApiError(err) {
  const responseData = err?.response?.data
  const status = Number(err?.response?.status || 0)
  const detail = String(
    responseData?.detail || responseData?.message || '',
  ).trim()
  const rawMessage = String(err?.message || '').trim()
  let message = detail || rawMessage
  if (!message) {
    if (status === 401) {
      message = '登录已失效，请重新登录'
    } else if (status > 0) {
      message = `请求失败（HTTP ${status}）`
    } else if (String(err?.code || '').trim()) {
      message = `请求失败：${String(err.code).trim()}`
    } else {
      message = '请求失败：服务不可用或网络异常'
    }
  }
  return {
    ...(responseData && typeof responseData === 'object' ? responseData : {}),
    status,
    code: String(err?.code || '').trim(),
    message,
    detail: detail || message,
  }
}

function markDesktopBackendOnline() {
  try {
    window.sessionStorage?.removeItem(DESKTOP_OFFLINE_MODE_STORAGE_KEY)
  } catch {}
}

function markDesktopBackendOffline(error) {
  const status = Number(error?.status || 0)
  const code = String(error?.code || '').trim()
  const detail = String(error?.detail || error?.message || '').trim()
  const looksOffline =
    status === 0 ||
    status >= 500 ||
    code === 'ERR_NETWORK' ||
    code === 'ECONNABORTED' ||
    /ECONNREFUSED|Network Error|服务不可用|network/i.test(detail)
  if (!looksOffline) return
  try {
    window.sessionStorage?.setItem(DESKTOP_OFFLINE_MODE_STORAGE_KEY, '1')
  } catch {}
}

api.interceptors.request.use((config) => {
  config.baseURL = buildApiBaseUrl()
  const token = getStoredToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const projectId = localStorage.getItem('project_id') || 'default'
  config.headers['X-Project-Id'] = projectId
  return config
})

api.interceptors.response.use(
  (res) => {
    markDesktopBackendOnline()
    return res.data
  },
  (err) => {
    if (err.response?.status === 401) {
      clearAuthSession()
      redirectToLogin()
    }
    const normalizedError = normalizeApiError(err)
    markDesktopBackendOffline(normalizedError)
    return Promise.reject(normalizedError)
  },
)

export default api
