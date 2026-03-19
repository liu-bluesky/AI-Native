function pad2(value) {
  return String(value).padStart(2, '0')
}

function formatClock(date, withSeconds = false) {
  const value = `${pad2(date.getHours())}:${pad2(date.getMinutes())}`
  if (!withSeconds) return value
  return `${value}:${pad2(date.getSeconds())}`
}

function formatAbsoluteDate(date, withSeconds = false) {
  return `${date.getFullYear()}年${pad2(date.getMonth() + 1)}月${pad2(date.getDate())}日 ${formatClock(date, withSeconds)}`
}

function normalizeDateString(value) {
  let normalized = String(value || '').trim()
  if (!normalized) return ''
  normalized = normalized.replace(
    /(\.\d{3})\d+(?=(Z|[+-]\d{2}:?\d{2})?$)/,
    '$1',
  )
  if (/^\d{4}-\d{2}-\d{2} /.test(normalized)) {
    normalized = normalized.replace(' ', 'T')
  }
  return normalized
}

function getDayStart(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

export function parseDateTime(value) {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : new Date(value.getTime())
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    const timestamp = value < 1e12 ? value * 1000 : value
    const date = new Date(timestamp)
    return Number.isNaN(date.getTime()) ? null : date
  }

  const raw = normalizeDateString(value)
  if (!raw) return null

  if (/^\d+$/.test(raw)) {
    const numeric = Number(raw)
    if (!Number.isFinite(numeric)) return null
    const timestamp = raw.length <= 10 ? numeric * 1000 : numeric
    const date = new Date(timestamp)
    return Number.isNaN(date.getTime()) ? null : date
  }

  const date = new Date(raw)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value, options = {}) {
  const { fallback = '-', withSeconds = false } = options
  const raw = String(value || '').trim()
  const date = parseDateTime(value)
  if (!date) return raw || fallback
  return formatAbsoluteDate(date, withSeconds)
}

export function formatRelativeDateTime(value, options = {}) {
  const { fallback = '-', now } = options
  const raw = String(value || '').trim()
  const date = parseDateTime(value)
  if (!date) return raw || fallback

  const current = parseDateTime(now) || new Date()
  const diffDays = Math.floor((getDayStart(current) - getDayStart(date)) / 86400000)

  if (diffDays === 0) {
    return `今天 ${formatClock(date)}`
  }
  if (diffDays === 1) {
    return `昨天 ${formatClock(date)}`
  }
  if (date.getFullYear() === current.getFullYear()) {
    return `${pad2(date.getMonth() + 1)}月${pad2(date.getDate())}日 ${formatClock(date)}`
  }
  return formatAbsoluteDate(date)
}

export function formatDateGroupLabel(value, options = {}) {
  const { fallback = '更早', now } = options
  const date = parseDateTime(value)
  if (!date) return fallback

  const current = parseDateTime(now) || new Date()
  const diffDays = Math.floor((getDayStart(current) - getDayStart(date)) / 86400000)

  if (diffDays === 0) return '今天'
  if (diffDays === 1) return '昨天'
  if (diffDays > 1 && diffDays <= 30) return '近 30 天'
  if (date.getFullYear() === current.getFullYear()) {
    return `${date.getMonth() + 1}月`
  }
  return `${date.getFullYear()}年${pad2(date.getMonth() + 1)}月`
}
