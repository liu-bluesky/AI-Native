import { ref } from 'vue'

import { clearPermissionArray, setPermissionArray } from './permissions.js'

export const authStateVersion = ref(0)

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

export function getStoredToken() {
  return String(localStorage.getItem('token') || '').trim()
}

export function hasStoredToken() {
  return Boolean(getStoredToken())
}

export function persistAuthSession(payload = {}) {
  setStorageValue('token', payload.token)
  setStorageValue('username', payload.username || payload.email || '')
  setStorageValue('role', payload.role || 'user')
  setPermissionArray(payload.permissions || [])
  bumpAuthState()
}

export function syncStoredProfile(payload = {}) {
  setStorageValue('username', payload.username || '')
  setStorageValue('role', payload.role || 'user')
  setPermissionArray(payload.permissions || [])
  bumpAuthState()
}

export function clearAuthSession() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  localStorage.removeItem('role')
  clearPermissionArray()
  bumpAuthState()
}

export function getStoredAuthProfile() {
  return {
    authenticated: hasStoredToken(),
    token: getStoredToken(),
    username: String(localStorage.getItem('username') || '').trim(),
    role: String(localStorage.getItem('role') || 'user').trim() || 'user',
  }
}
