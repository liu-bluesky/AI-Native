import { ref } from 'vue'

import { getServerScopedStorageKey, isSameOriginServer } from './server-profile.js'

const PERMISSION_STORAGE_KEY = 'permissions'
const CHAT_SETTINGS_ROUTE_PREFIX = '/ai/chat/settings'
const permissionStateVersion = ref(0)

const PATH_PERMISSION_MAP = [
  { prefix: '/ai/chat', permission: 'menu.ai.chat' },
  { prefix: '/user/settings', permission: '' },
  { prefix: '/users', permission: 'menu.users' },
  { prefix: '/departments', permission: 'menu.departments' },
  { prefix: '/roles', permission: 'menu.roles' },
  { prefix: '/projects', permission: 'menu.projects' },
  { prefix: '/materials', permission: 'menu.projects' },
  { prefix: '/agent-templates', permission: 'menu.employees' },
  { prefix: '/employees/create', permission: 'menu.employees.create' },
  { prefix: '/employees', permission: 'menu.employees' },
  { prefix: '/memory', permission: 'menu.employees' },
  { prefix: '/skill-resources', permission: 'menu.skills' },
  { prefix: '/skills', permission: 'menu.skills' },
  { prefix: '/rules', permission: 'menu.rules' },
  { prefix: '/system/bot-connectors', permission: 'menu.system.config' },
  { prefix: '/system/config', permission: 'menu.system.config' },
  { prefix: '/changelog-entries', permission: 'menu.system.changelog' },
  { prefix: '/work-sessions', permission: 'menu.system.work_sessions' },
  { prefix: '/statistics', permission: 'menu.statistics' },
  { prefix: '/dictionaries', permission: ['menu.system.dictionaries', 'menu.system.config'] },
  { prefix: '/llm/providers', permission: 'menu.llm.providers' },
  { prefix: '/usage/keys', permission: 'menu.usage.keys' },
]

const LEGACY_USER_PERMISSION_KEYS = new Set([
  'menu.ai.chat',
  'menu.projects',
  'menu.employees',
  'menu.employees.create',
  'menu.system.changelog',
  'menu.system.work_sessions',
  'button.project.chat',
  'button.changelog.create',
  'button.changelog.update',
  'button.changelog.delete',
  'button.employees.update',
  'button.employees.delete',
])
const FALLBACK_PATHS = [
  '/ai/chat',
  '/user/settings',
  '/agent-templates',
  '/employees',
  '/projects',
  '/skill-resources',
  '/users',
  '/departments',
  '/roles',
  '/skills',
  '/rules',
  '/system/config',
  '/changelog-entries',
  '/work-sessions',
  '/statistics',
  '/dictionaries',
  '/usage/keys',
]

export function isSuperAdmin() {
  const role = getScopedStorageValue('role') || 'user'
  const roleIds = parsePermissionArray(getScopedStorageValue('role_ids'))
    .map((item) => String(item || '').trim().toLowerCase())
  const username = getScopedStorageValue('username').toLowerCase()
  return role === 'admin' || roleIds.includes('admin') || username === 'admin'
}

function getScopedStorageValue(key) {
  const scoped = localStorage.getItem(getServerScopedStorageKey(key))
  if (scoped !== null) return String(scoped || '').trim()
  if (isSameOriginServer()) {
    return String(localStorage.getItem(key) || '').trim()
  }
  return ''
}

function setScopedStorageValue(key, value) {
  const normalized = String(value || '').trim()
  if (normalized) {
    localStorage.setItem(getServerScopedStorageKey(key), normalized)
    if (isSameOriginServer()) {
      localStorage.setItem(key, normalized)
    }
    return
  }
  localStorage.removeItem(getServerScopedStorageKey(key))
  if (isSameOriginServer()) {
    localStorage.removeItem(key)
  }
}

function removeScopedStorageValue(key) {
  localStorage.removeItem(getServerScopedStorageKey(key))
  if (isSameOriginServer()) {
    localStorage.removeItem(key)
  }
}

function parsePermissionArray(rawValue) {
  if (!rawValue) return []
  try {
    const parsed = JSON.parse(rawValue)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((item) => String(item || '').trim())
      .filter(Boolean)
  } catch {
    return []
  }
}

function legacyUserFallback(permissionKey) {
  const role = (getScopedStorageValue('role') || 'user').toLowerCase()
  const roleIds = parsePermissionArray(getScopedStorageValue('role_ids'))
    .map((item) => String(item || '').trim().toLowerCase())
  if (role === 'admin' || roleIds.includes('admin')) return true
  if (role !== 'user') return false
  return LEGACY_USER_PERMISSION_KEYS.has(permissionKey)
}

export function getPermissionArray() {
  return parsePermissionArray(getScopedStorageValue(PERMISSION_STORAGE_KEY))
}

export function setPermissionArray(values) {
  const normalized = (Array.isArray(values) ? values : [])
    .map((item) => String(item || '').trim())
    .filter(Boolean)
  setScopedStorageValue(PERMISSION_STORAGE_KEY, JSON.stringify(Array.from(new Set(normalized))))
  permissionStateVersion.value += 1
}

export function clearPermissionArray() {
  removeScopedStorageValue(PERMISSION_STORAGE_KEY)
  permissionStateVersion.value += 1
}

function hasSinglePermission(permissionKey) {
  const target = String(permissionKey || '').trim()
  if (!target) return true
  if (isSuperAdmin()) return true
  if (!getScopedStorageValue(PERMISSION_STORAGE_KEY)) {
    return legacyUserFallback(target)
  }
  const permissions = getPermissionArray()
  if (permissions.includes('*')) return true
  return permissions.includes(target)
}

export function hasAnyPermission(permissionKeys) {
  const targets = (Array.isArray(permissionKeys) ? permissionKeys : [permissionKeys])
    .map((item) => String(item || '').trim())
    .filter(Boolean)
  if (!targets.length) return true
  return targets.some((item) => hasSinglePermission(item))
}

export function hasPermission(permissionKey) {
  permissionStateVersion.value
  if (Array.isArray(permissionKey)) {
    return hasAnyPermission(permissionKey)
  }
  return hasSinglePermission(permissionKey)
}

export function pathPermission(path) {
  let currentPath = String(path || '').trim()
  if (!currentPath) return ''
  currentPath = currentPath.split('#')[0]?.split('?')[0] || currentPath
  if (currentPath.startsWith(CHAT_SETTINGS_ROUTE_PREFIX)) {
    const stripped = currentPath.slice(CHAT_SETTINGS_ROUTE_PREFIX.length)
    currentPath = stripped.startsWith('/') ? stripped : `/${stripped}`
    if (!currentPath || currentPath === '/') currentPath = '/ai/chat'
  }
  const matched = PATH_PERMISSION_MAP.find(
    (item) => currentPath === item.prefix || currentPath.startsWith(`${item.prefix}/`),
  )
  return matched?.permission || ''
}

export function canAccessPath(path) {
  const permission = pathPermission(path)
  return !permission || hasPermission(permission)
}

export function getFallbackPath() {
  return FALLBACK_PATHS.find((path) => {
    const permission = pathPermission(path)
    return !permission || hasPermission(permission)
  }) || '/login'
}
