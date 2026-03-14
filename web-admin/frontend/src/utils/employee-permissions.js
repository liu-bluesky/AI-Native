import { canManageRecord } from './ownership.js'
import { hasPermission } from './permissions.js'

export function canCreateEmployee() {
  return hasPermission('menu.employees.create')
}

export function canUpdateEmployee(record) {
  return hasPermission('button.employees.update') || canManageRecord(record)
}

export function canDeleteEmployee(record) {
  return hasPermission('button.employees.delete') || canManageRecord(record)
}
