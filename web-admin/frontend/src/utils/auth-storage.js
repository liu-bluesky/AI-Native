import { ref } from 'vue'

import { clearPermissionArray, setPermissionArray } from './permissions.js'

export const authStateVersion = ref(0)
const REMEMBER_LOGIN_INFO_STORAGE_KEY = 'remember_login_info'

function bumpAuthState() {
  authStateVersion.value += 1
}

function setStorageValue(key, value) {
  const normalized = String(value || '').trim()
  if (normalized) {
    localStorage.setItem(key, normalized)
    return
  }
  localStorage.removeItem(key)
}

function normalizeRememberLoginInfo(payload = {}) {
  return {
    enabled: payload.enabled === true,
    username: String(payload.username || '').trim(),
    password: String(payload.password || ''),
  }
}

export function getStoredToken() {
  return String(localStorage.getItem('token') || '').trim()
}

export function hasStoredToken() {
  return Boolean(getStoredToken())
}

export function getRememberedLoginInfo() {
  try {
    const raw = localStorage.getItem(REMEMBER_LOGIN_INFO_STORAGE_KEY)
    if (!raw) {
      return normalizeRememberLoginInfo()
    }
    return normalizeRememberLoginInfo(JSON.parse(raw))
  } catch {
    localStorage.removeItem(REMEMBER_LOGIN_INFO_STORAGE_KEY)
    return normalizeRememberLoginInfo()
  }
}

export function persistRememberedLoginInfo(payload = {}) {
  const normalized = normalizeRememberLoginInfo(payload)
  if (!normalized.enabled || !normalized.username) {
    localStorage.removeItem(REMEMBER_LOGIN_INFO_STORAGE_KEY)
    return
  }
  localStorage.setItem(REMEMBER_LOGIN_INFO_STORAGE_KEY, JSON.stringify(normalized))
}

export function persistAuthSession(payload = {}) {
  setStorageValue('token', payload.token)
  setStorageValue('username', payload.username || payload.email || '')
  setStorageValue('display_name', payload.display_name || '')
  setStorageValue('role', payload.role || 'user')
  setPermissionArray(payload.permissions || [])
  bumpAuthState()
}

export function syncStoredProfile(payload = {}) {
  setStorageValue('username', payload.username || '')
  setStorageValue('display_name', payload.display_name || '')
  setStorageValue('role', payload.role || 'user')
  setPermissionArray(payload.permissions || [])
  bumpAuthState()
}

export function clearAuthSession() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  localStorage.removeItem('display_name')
  localStorage.removeItem('role')
  clearPermissionArray()
  bumpAuthState()
}

export function getStoredAuthProfile() {
  return {
    authenticated: hasStoredToken(),
    token: getStoredToken(),
    username: String(localStorage.getItem('username') || '').trim(),
    displayName: String(localStorage.getItem('display_name') || '').trim(),
    role: String(localStorage.getItem('role') || 'user').trim() || 'user',
  }
}
