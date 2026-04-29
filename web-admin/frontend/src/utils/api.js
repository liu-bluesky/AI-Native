import axios from 'axios'

import { clearAuthSession } from './auth-storage.js'

const api = axios.create({ baseURL: '/api' })
const AUTH_PUBLIC_PATHS = new Set(['/init', '/intro', '/market', '/updates', '/login', '/register'])

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

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const projectId = localStorage.getItem('project_id') || 'default'
  config.headers['X-Project-Id'] = projectId
  return config
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401) {
      clearAuthSession()
      redirectToLogin()
    }
    return Promise.reject(normalizeApiError(err))
  },
)

export default api
