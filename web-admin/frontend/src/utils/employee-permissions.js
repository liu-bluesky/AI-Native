import { canManageRecord } from './ownership.js'
import { hasPermission } from './permissions.js'

export function canCreateEmployee() {
  return hasPermission('menu.employees.create')
}

export function canUpdateEmployee(record) {
  return canManageRecord(record)
}

export function canDeleteEmployee(record) {
  return canManageRecord(record)
}
