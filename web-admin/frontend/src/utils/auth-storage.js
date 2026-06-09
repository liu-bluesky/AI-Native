import { ref } from 'vue'

import { clearPermissionArray, setPermissionArray } from './permissions.js'
import {
  getServerScopedStorageKey,
  isSameOriginServer,
  resolveServerOrigin,
} from './server-profile.js'

export const authStateVersion = ref(0)
const REMEMBER_LOGIN_INFO_STORAGE_KEY = 'remember_login_info'

function bumpAuthState() {
  authStateVersion.value += 1
}

function setStorageValue(key, value) {
  const normalized = String(value || '').trim()
  const scopedKey = getServerScopedStorageKey(key)
  if (normalized) {
    localStorage.setItem(scopedKey, normalized)
    if (isSameOriginServer()) {
      localStorage.setItem(key, normalized)
    }
    return
  }
  localStorage.removeItem(scopedKey)
  if (isSameOriginServer()) {
    localStorage.removeItem(key)
  }
}

function getStorageValue(key) {
  const scopedValue = localStorage.getItem(getServerScopedStorageKey(key))
  if (scopedValue !== null) return String(scopedValue || '').trim()
  if (isSameOriginServer()) {
    return String(localStorage.getItem(key) || '').trim()
  }
  return ''
}

function removeStorageValue(key) {
  localStorage.removeItem(getServerScopedStorageKey(key))
  if (isSameOriginServer()) {
    localStorage.removeItem(key)
  }
}

function setJsonStorageValue(key, value) {
  const serialized = JSON.stringify(value)
  localStorage.setItem(getServerScopedStorageKey(key), serialized)
  if (isSameOriginServer()) {
    localStorage.setItem(key, serialized)
  }
}

function getJsonStorageValue(key, fallbackValue) {
  const scopedRaw = localStorage.getItem(getServerScopedStorageKey(key))
  const raw = scopedRaw !== null ? scopedRaw : isSameOriginServer() ? localStorage.getItem(key) : null
  if (!raw) return fallbackValue
  try {
    return JSON.parse(raw)
  } catch {
    localStorage.removeItem(getServerScopedStorageKey(key))
    if (isSameOriginServer()) localStorage.removeItem(key)
    return fallbackValue
  }
}

function removeJsonStorageValue(key) {
  localStorage.removeItem(getServerScopedStorageKey(key))
  if (isSameOriginServer()) {
    localStorage.removeItem(key)
  }
}

function normalizeRoleIds(payload = {}) {
  const normalized = []
  const seen = new Set()
  const roleIds = Array.isArray(payload.role_ids) ? payload.role_ids : []
  for (const item of [...roleIds, payload.role || 'user']) {
    const roleId = String(item || '').trim().toLowerCase()
    if (!roleId || seen.has(roleId)) continue
    seen.add(roleId)
    normalized.push(roleId)
  }
  return normalized.length ? normalized : ['user']
}

function setRoleIds(payload = {}) {
  setJsonStorageValue('role_ids', normalizeRoleIds(payload))
}

function getStoredRoleIds() {
  const parsed = getJsonStorageValue('role_ids', [])
  return Array.isArray(parsed) ? parsed : []
}

function normalizeRememberLoginInfo(payload = {}) {
  return {
    enabled: payload.enabled === true,
    username: String(payload.username || '').trim(),
    password: String(payload.password || ''),
  }
}

export function getStoredToken() {
  return getStorageValue('token')
}

export function hasStoredToken() {
  return Boolean(getStoredToken())
}

export function getRememberedLoginInfo() {
  return normalizeRememberLoginInfo(
    getJsonStorageValue(REMEMBER_LOGIN_INFO_STORAGE_KEY, normalizeRememberLoginInfo()),
  )
}

export function persistRememberedLoginInfo(payload = {}) {
  const normalized = normalizeRememberLoginInfo(payload)
  if (!normalized.enabled || !normalized.username) {
    removeJsonStorageValue(REMEMBER_LOGIN_INFO_STORAGE_KEY)
    return
  }
  setJsonStorageValue(REMEMBER_LOGIN_INFO_STORAGE_KEY, normalized)
}

export function persistAuthSession(payload = {}) {
  setStorageValue('token', payload.token)
  setStorageValue('username', payload.username || payload.email || '')
  setStorageValue('display_name', payload.display_name || '')
  setStorageValue('role', payload.role || 'user')
  setRoleIds(payload)
  setPermissionArray(payload.permissions || [])
  bumpAuthState()
}

export function syncStoredProfile(payload = {}) {
  setStorageValue('username', payload.username || '')
  setStorageValue('display_name', payload.display_name || '')
  setStorageValue('role', payload.role || 'user')
  setRoleIds(payload)
  setPermissionArray(payload.permissions || [])
  bumpAuthState()
}

export function clearAuthSession() {
  removeStorageValue('token')
  removeStorageValue('username')
  removeStorageValue('display_name')
  removeStorageValue('role')
  removeJsonStorageValue('role_ids')
  clearPermissionArray()
  bumpAuthState()
}

export function getStoredAuthProfile() {
  return {
    authenticated: hasStoredToken(),
    token: getStoredToken(),
    username: getStorageValue('username'),
    displayName: getStorageValue('display_name'),
    role: getStorageValue('role') || 'user',
    roleIds: normalizeRoleIds({
      role: getStorageValue('role') || 'user',
      role_ids: getStoredRoleIds(),
    }),
    serverOrigin: resolveServerOrigin(),
  }
}
