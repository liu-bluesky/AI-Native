function normalizePath(pathname) {
  const path = String(pathname || '').trim()
  if (!path) return '/'
  return path.startsWith('/') ? path : `/${path}`
}

function currentOrigin() {
  if (typeof window === 'undefined' || !window.location?.origin) {
    return ''
  }
  return String(window.location.origin).replace(/\/+$/, '')
}

export function buildRuntimeUrl(pathname) {
  const origin = currentOrigin()
  const path = normalizePath(pathname)
  if (!origin) return path
  return new URL(path, `${origin}/`).toString()
}
