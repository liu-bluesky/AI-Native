import api from './api.js'
import {
  getStoredAuthProfile,
  isExternalAuthSession,
  persistAuthSession,
  syncStoredProfile,
} from './auth-storage.js'
import { loginWithExternalAccount } from './external-login.js'

const POST_LOGIN_PUBLIC_PATHS = new Set(['/loading', '/init', '/login', '/register'])

export function resolveSafeRedirectPath(rawValue, fallbackPath = '/workbench') {
  const value = Array.isArray(rawValue) ? rawValue[0] : rawValue
  const normalized = String(value || '').trim()
  const path = normalized.split('?')[0].split('#')[0]
  if (
    !normalized.startsWith('/') ||
    normalized.startsWith('//') ||
    POST_LOGIN_PUBLIC_PATHS.has(path)
  ) {
    return fallbackPath
  }
  return normalized
}

export async function loginWithPassword(payload) {
  const data = await loginWithExternalAccount({
    account: String(payload.username || payload.account || '').trim(),
    password: String(payload.password || ''),
  })
  persistAuthSession(data || {})
  return data
}

export async function registerWithEmail(payload) {
  return api.post('/auth/register', payload)
}

export async function syncCurrentUser() {
  if (isExternalAuthSession()) {
    const profile = getStoredAuthProfile()
    return {
      username: profile.username,
      display_name: profile.displayName,
      role: profile.role,
      role_ids: profile.roleIds,
    }
  }
  const data = await api.get('/auth/me')
  syncStoredProfile(data || {})
  return data
}
