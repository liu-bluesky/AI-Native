import {
  getNativeDesktopVersion,
  getNativeRuntimeInfo,
  hasNativeDesktopBridge,
  openNativeExternalUrl,
} from './native-desktop-bridge.js'
import { DESKTOP_UPDATE_ENDPOINT } from './backend-endpoints.js'

const UPDATE_PATH = '/desktop-updates/latest'

function normalizeUpdateEndpoint(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  try {
    const url = new URL(raw)
    if (!['http:', 'https:'].includes(url.protocol)) return ''
    if (url.pathname.endsWith('/api/desktop-updates/latest')) return url.toString()
    if (url.pathname.endsWith('/api')) {
      url.pathname = `${url.pathname}${UPDATE_PATH}`
    } else {
      url.pathname = `${url.pathname.replace(/\/+$/, '')}/api${UPDATE_PATH}`
    }
    return url.toString()
  } catch {
    return ''
  }
}

function normalizeTarget(value) {
  const raw = String(value || '').trim().toLowerCase()
  if (raw === 'macos' || raw === 'darwin') return 'darwin'
  if (raw === 'win32' || raw === 'windows') return 'windows'
  return raw
}

function normalizeArch(value) {
  const raw = String(value || '').trim().toLowerCase()
  if (raw === 'arm64') return 'aarch64'
  if (raw === 'amd64' || raw === 'x64') return 'x86_64'
  return raw
}

export function resolveDesktopDistribution(runtimeInfo = {}) {
  const target = normalizeTarget(runtimeInfo?.platform)
  const arch = normalizeArch(runtimeInfo?.arch)
  if (target === 'darwin' && ['aarch64', 'x86_64'].includes(arch)) {
    return { target, arch, platform: `darwin-${arch}` }
  }
  if (target === 'windows' && arch === 'x86_64') {
    return { target, arch, platform: 'windows-x86_64' }
  }
  return null
}

function parseVersion(value) {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(String(value || '').trim())
  if (!match) return null
  return match.slice(1).map(Number)
}

function compareVersions(left, right) {
  const a = parseVersion(left) || [0, 0, 0]
  const b = parseVersion(right) || [0, 0, 0]
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index]
  }
  return 0
}

function normalizeRelease(payload = {}, currentVersion = '', distribution = null) {
  return {
    version: String(payload.version || '').trim(),
    currentVersion: String(currentVersion || '').trim(),
    notes: String(payload.notes || payload.release_notes || ''),
    pubDate: String(payload.pub_date || payload.pubDate || '').trim(),
    url: String(payload.url || payload.download_url || '').trim(),
    platform: distribution?.platform || '',
    target: distribution?.target || '',
    arch: distribution?.arch || '',
  }
}

export function resolveDesktopUpdateEndpoint() {
  const configured = normalizeUpdateEndpoint(import.meta.env?.VITE_DESKTOP_UPDATE_ENDPOINT)
  if (configured) return configured
  return normalizeUpdateEndpoint(DESKTOP_UPDATE_ENDPOINT)
}

export function canUseDesktopUpdater() {
  return Boolean(hasNativeDesktopBridge() && resolveDesktopUpdateEndpoint())
}

export async function getDesktopVersion() {
  if (!hasNativeDesktopBridge()) return null
  return getNativeDesktopVersion()
}

export async function checkDesktopUpdate() {
  const endpoint = resolveDesktopUpdateEndpoint()
  if (!endpoint || !hasNativeDesktopBridge()) return null

  const [currentVersion, runtimeInfo] = await Promise.all([
    getDesktopVersion(),
    getNativeRuntimeInfo(),
  ])
  const distribution = resolveDesktopDistribution(runtimeInfo)
  if (!distribution) {
    throw new Error('当前仅支持 macOS 和 Windows 64 位版本下载')
  }

  const requestUrl = new URL(endpoint)
  requestUrl.searchParams.set('platform', distribution.platform)
  requestUrl.searchParams.set('target', distribution.target)
  requestUrl.searchParams.set('arch', distribution.arch)
  const response = await fetch(requestUrl.toString(), {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  if (response.status === 204) return null

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(String(data?.error || `版本更新服务返回 HTTP ${response.status}`).trim())
  }

  const update = normalizeRelease(data, currentVersion, distribution)
  if (!update.version || !update.url) {
    throw new Error('版本更新服务返回的数据不完整')
  }
  if (compareVersions(update.version, currentVersion) <= 0) return null
  return update
}

export async function downloadDesktopUpdate(update) {
  const url = String(update?.url || '').trim()
  if (!url) throw new Error('版本更新下载地址不可用')
  if (!/^https?:\/\//i.test(url)) throw new Error('版本更新下载地址无效')

  if (hasNativeDesktopBridge()) {
    const opened = await openNativeExternalUrl(url)
    if (!opened) throw new Error('无法打开系统浏览器下载版本更新')
    return true
  }

  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (!opened) throw new Error('浏览器阻止了下载窗口，请允许打开新窗口')
  return true
}
