import { ref } from 'vue'

const PERMISSION_STORAGE_KEY = 'permissions'
const permissionStateVersion = ref(0)

const PATH_PERMISSION_MAP = [
  { prefix: '/ai/chat', permission: 'menu.ai.chat' },
  { prefix: '/users', permission: 'menu.users' },
  { prefix: '/roles', permission: 'menu.roles' },
  { prefix: '/projects', permission: 'menu.projects' },
  { prefix: '/employees/create', permission: 'menu.employees.create' },
  { prefix: '/employees', permission: 'menu.employees' },
  { prefix: '/skill-resources', permission: 'menu.skills' },
  { prefix: '/skills', permission: 'menu.skills' },
  { prefix: '/rules', permission: 'menu.rules' },
  { prefix: '/system/config', permission: 'menu.system.config' },
  { prefix: '/llm/providers', permission: 'menu.llm.providers' },
  { prefix: '/usage/keys', permission: 'menu.usage.keys' },
]

const LEGACY_USER_PERMISSION_KEYS = new Set([
  'menu.ai.chat',
  'menu.projects',
  'menu.employees',
  'menu.employees.create',
  'button.project.chat',
  'button.employees.update',
  'button.employees.delete',
])
const FALLBACK_PATHS = [
  '/ai/chat',
  '/employees',
  '/projects',
  '/skill-resources',
  '/users',
  '/roles',
  '/skills',
  '/rules',
  '/system/config',
  '/usage/keys',
]

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

export function hasPermission(permissionKey) {
  permissionStateVersion.value
  const target = String(permissionKey || '').trim()
  if (!target) return true
  if (localStorage.getItem(PERMISSION_STORAGE_KEY) === null) {
    return legacyUserFallback(target)
  }
  const permissions = getPermissionArray()
  if (permissions.includes('*')) return true
  return permissions.includes(target)
}

export function pathPermission(path) {
  const currentPath = String(path || '').trim()
  if (!currentPath) return ''
  const matched = PATH_PERMISSION_MAP.find(
    (item) => currentPath === item.prefix || currentPath.startsWith(`${item.prefix}/`),
  )
  return matched?.permission || ''
}

export function getFallbackPath() {
  return FALLBACK_PATHS.find((path) => {
    const permission = pathPermission(path)
    return !permission || hasPermission(permission)
  }) || '/login'
}
