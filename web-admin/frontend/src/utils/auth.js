import api from './api.js'
import { persistAuthSession, syncStoredProfile } from './auth-storage.js'

export function resolveSafeRedirectPath(rawValue, fallbackPath = '/workbench') {
  const value = Array.isArray(rawValue) ? rawValue[0] : rawValue
  const normalized = String(value || '').trim()
  if (!normalized.startsWith('/') || normalized.startsWith('//')) {
    return fallbackPath
  }
  return normalized
}

export async function loginWithPassword(payload) {
  const data = await api.post('/auth/login', payload)
  persistAuthSession(data || {})
  return data
}

export async function registerWithEmail(payload) {
  return api.post('/auth/register', payload)
}

export async function syncCurrentUser() {
  const data = await api.get('/auth/me')
  syncStoredProfile(data || {})
  return data
}
