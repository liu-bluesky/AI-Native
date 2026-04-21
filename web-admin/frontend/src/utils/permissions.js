import { ref } from 'vue'

const PERMISSION_STORAGE_KEY = 'permissions'
const CHAT_SETTINGS_ROUTE_PREFIX = '/ai/chat/settings'
const permissionStateVersion = ref(0)

const PATH_PERMISSION_MAP = [
  { prefix: '/ai/chat', permission: 'menu.ai.chat' },
  { prefix: '/user/settings', permission: '' },
  { prefix: '/users', permission: 'menu.users' },
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
  { prefix: '/system/config', permission: 'menu.system.config' },
  { prefix: '/changelog-entries', permission: 'menu.system.changelog' },
  { prefix: '/work-sessions', permission: 'menu.system.work_sessions' },
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
  '/roles',
  '/skills',
  '/rules',
  '/system/config',
  '/changelog-entries',
  '/work-sessions',
  '/dictionaries',
  '/usage/keys',
]

export function isSuperAdmin() {
  return String(localStorage.getItem('role') || 'user').trim().toLowerCase() === 'admin'
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
  const role = String(localStorage.getItem('role') || 'user').toLowerCase()
  if (role === 'admin') return true
  if (role !== 'user') return false
  return LEGACY_USER_PERMISSION_KEYS.has(permissionKey)
}

export function getPermissionArray() {
  return parsePermissionArray(localStorage.getItem(PERMISSION_STORAGE_KEY))
}

export function setPermissionArray(values) {
  const normalized = (Array.isArray(values) ? values : [])
    .map((item) => String(item || '').trim())
    .filter(Boolean)
  localStorage.setItem(PERMISSION_STORAGE_KEY, JSON.stringify(Array.from(new Set(normalized))))
  permissionStateVersion.value += 1
}

export function clearPermissionArray() {
  localStorage.removeItem(PERMISSION_STORAGE_KEY)
  permissionStateVersion.value += 1
}

function hasSinglePermission(permissionKey) {
  const target = String(permissionKey || '').trim()
  if (!target) return true
  if (localStorage.getItem(PERMISSION_STORAGE_KEY) === null) {
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
