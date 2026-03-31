import axios from 'axios'

import { clearAuthSession } from './auth-storage.js'

const api = axios.create({ baseURL: '/api' })

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
      const currentPath = String(window.location.hash || '#/intro').replace(/^#/, '') || '/intro'
      const publicPaths = new Set(['/intro', '/market', '/updates', '/login', '/register'])
      if (!publicPaths.has(currentPath)) {
        window.location.hash = '#/login'
      }
    }
    return Promise.reject(normalizeApiError(err))
  },
)

export default api
