import { canManageRecord } from './ownership.js'

export function canUpdateEmployee(record) {
  return canManageRecord(record)
}

export function canDeleteEmployee(record) {
  return canManageRecord(record)
}
