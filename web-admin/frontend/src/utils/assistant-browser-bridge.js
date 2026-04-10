const MAX_REQUEST_LOGS = 80
const MAX_TEXT_PREVIEW = 800
const MAX_LIST_ITEMS = 20
const SENSITIVE_KEY_PATTERN = /(authorization|token|password|secret|cookie|set-cookie|api[-_]?key|session)/i

const bridgeState = {
  installed: false,
  nextRequestId: 1,
  requests: [],
  requestMap: new Map(),
  originalFetch: null,
  originalXhrOpen: null,
  originalXhrSend: null,
}

function nowIso() {
  return new Date().toISOString()
}

function clipText(value, limit = MAX_TEXT_PREVIEW) {
  const normalized = String(value ?? '').replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit)}...`
}

function escapeCssIdentifier(value) {
  const normalized = String(value || '').trim()
  if (!normalized) return ''
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
    return CSS.escape(normalized)
  }
  return normalized.replace(/([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, '\\$1')
}

function escapeCssAttributeValue(value) {
  return String(value || '')
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
}

function sanitizeKeyValueEntries(input) {
  if (!input || typeof input !== 'object') return {}
  const result = {}
  for (const [key, rawValue] of Object.entries(input)) {
    const normalizedKey = String(key || '').trim()
    if (!normalizedKey) continue
    if (SENSITIVE_KEY_PATTERN.test(normalizedKey)) {
      result[normalizedKey] = '[redacted]'
      continue
    }
    result[normalizedKey] = summarizeUnknown(rawValue)
  }
  return result
}

function sanitizeUrl(rawUrl) {
  const normalized = String(rawUrl || '').trim()
  if (!normalized) return ''
  try {
    const resolved = new URL(normalized, window.location.origin)
    const next = new URL(resolved.toString())
    for (const key of Array.from(next.searchParams.keys())) {
      if (SENSITIVE_KEY_PATTERN.test(key)) {
        next.searchParams.set(key, '[redacted]')
      }
    }
    if (next.origin === window.location.origin) {
      return `${next.pathname}${next.search}${next.hash}`
    }
    return next.toString()
  } catch {
    return normalized
  }
}

function summarizeUnknown(value) {
  if (value == null) return ''
  if (typeof value === 'string') return clipText(value)
  if (typeof value === 'number' || typeof value === 'boolean') return value
  if (value instanceof Blob) {
    return {
      type: String(value.type || '').trim() || 'application/octet-stream',
      size: Number(value.size || 0),
    }
  }
  if (value instanceof ArrayBuffer) {
    return {
      type: 'array-buffer',
      byteLength: Number(value.byteLength || 0),
    }
  }
  if (ArrayBuffer.isView(value)) {
    return {
      type: 'typed-array',
      byteLength: Number(value.byteLength || 0),
    }
  }
  if (Array.isArray(value)) {
    return value.slice(0, 8).map((item) => summarizeUnknown(item))
  }
  if (value instanceof FormData) {
    const items = []
    value.forEach((entryValue, key) => {
      items.push({
        key: String(key || '').trim(),
        value: summarizeUnknown(entryValue),
      })
    })
    return {
      type: 'form-data',
      items: items.slice(0, 12),
    }
  }
  if (value instanceof URLSearchParams) {
    return sanitizeKeyValueEntries(Object.fromEntries(value.entries()))
  }
  if (typeof value === 'object') {
    try {
      return sanitizeKeyValueEntries(value)
    } catch {
      return clipText(JSON.stringify(value))
    }
  }
  return clipText(String(value))
}

function summarizeBody(body) {
  if (body == null) return ''
  if (typeof body === 'string') {
    try {
      return sanitizeKeyValueEntries(JSON.parse(body))
    } catch {
      return clipText(body)
    }
  }
  return summarizeUnknown(body)
}

function createRequestEntry({ source = '', method = 'GET', url = '', requestSummary = '' } = {}) {
  const id = `abr-${Date.now()}-${bridgeState.nextRequestId++}`
  const entry = {
    id,
    source: String(source || '').trim() || 'unknown',
    method: String(method || 'GET').trim().toUpperCase(),
    url: sanitizeUrl(url),
    state: 'pending',
    status: 0,
    ok: false,
    started_at: nowIso(),
    finished_at: '',
    duration_ms: 0,
    request_summary: requestSummary || '',
    response_summary: '',
    error_message: '',
  }
  bridgeState.requests.unshift(entry)
  bridgeState.requestMap.set(id, entry)
  if (bridgeState.requests.length > MAX_REQUEST_LOGS) {
    const removed = bridgeState.requests.splice(MAX_REQUEST_LOGS)
    removed.forEach((item) => bridgeState.requestMap.delete(item.id))
  }
  return entry
}

function finalizeRequestEntry(entry, patch = {}) {
  if (!entry) return
  const current = bridgeState.requestMap.get(entry.id)
  if (!current) return
  Object.assign(current, patch)
}

async function summarizeFetchResponse(response) {
  if (!response) return ''
  const contentType = String(response.headers?.get('content-type') || '').trim().toLowerCase()
  if (contentType.includes('application/json')) {
    try {
      return summarizeUnknown(await response.clone().json())
    } catch {
      return clipText(await response.clone().text())
    }
  }
  if (contentType.startsWith('text/') || contentType.includes('json') || contentType.includes('xml')) {
    try {
      return clipText(await response.clone().text())
    } catch {
      return ''
    }
  }
  return {
    type: contentType || 'binary',
    size: Number(response.headers?.get('content-length') || 0) || undefined,
  }
}

function attachFetchInterceptor() {
  if (typeof window.fetch !== 'function' || bridgeState.originalFetch) return
  bridgeState.originalFetch = window.fetch.bind(window)
  window.fetch = async (...args) => {
    const [input, init] = args
    const method = String(init?.method || input?.method || 'GET').trim().toUpperCase()
    const url = typeof input === 'string' ? input : input?.url
    const requestSummary = summarizeBody(init?.body)
    const entry = createRequestEntry({
      source: 'fetch',
      method,
      url,
      requestSummary,
    })
    const startedAt = Date.now()
    try {
      const response = await bridgeState.originalFetch(...args)
      finalizeRequestEntry(entry, {
        state: response.ok ? 'success' : 'error',
        status: Number(response.status || 0),
        ok: Boolean(response.ok),
        finished_at: nowIso(),
        duration_ms: Date.now() - startedAt,
      })
      void summarizeFetchResponse(response).then((summary) => {
        finalizeRequestEntry(entry, {
          response_summary: summary,
        })
      })
      return response
    } catch (error) {
      finalizeRequestEntry(entry, {
        state: 'error',
        status: 0,
        ok: false,
        finished_at: nowIso(),
        duration_ms: Date.now() - startedAt,
        error_message: clipText(error?.message || 'fetch failed'),
      })
      throw error
    }
  }
}

function attachXhrInterceptor() {
  if (typeof window.XMLHttpRequest === 'undefined' || bridgeState.originalXhrOpen) return
  bridgeState.originalXhrOpen = window.XMLHttpRequest.prototype.open
  bridgeState.originalXhrSend = window.XMLHttpRequest.prototype.send

  window.XMLHttpRequest.prototype.open = function patchedOpen(method, url, ...rest) {
    this.__assistantBridgeMeta = {
      method: String(method || 'GET').trim().toUpperCase(),
      url: String(url || '').trim(),
    }
    return bridgeState.originalXhrOpen.call(this, method, url, ...rest)
  }

  window.XMLHttpRequest.prototype.send = function patchedSend(body) {
    const meta = this.__assistantBridgeMeta || {}
    const startedAt = Date.now()
    const entry = createRequestEntry({
      source: 'xhr',
      method: meta.method || 'GET',
      url: meta.url || '',
      requestSummary: summarizeBody(body),
    })

    const finalize = () => {
      let responseSummary = ''
      try {
        if (this.responseType === '' || this.responseType === 'text') {
          responseSummary = clipText(this.responseText || '')
        } else if (this.responseType === 'json') {
          responseSummary = summarizeUnknown(this.response)
        } else if (this.response instanceof Blob) {
          responseSummary = summarizeUnknown(this.response)
        } else if (this.response != null) {
          responseSummary = summarizeUnknown(this.response)
        }
      } catch {
        responseSummary = ''
      }
      finalizeRequestEntry(entry, {
        state: Number(this.status || 0) >= 200 && Number(this.status || 0) < 400 ? 'success' : 'error',
        status: Number(this.status || 0),
        ok: Number(this.status || 0) >= 200 && Number(this.status || 0) < 400,
        finished_at: nowIso(),
        duration_ms: Date.now() - startedAt,
        response_summary: responseSummary,
      })
    }

    const handleError = () => {
      finalizeRequestEntry(entry, {
        state: 'error',
        status: Number(this.status || 0),
        ok: false,
        finished_at: nowIso(),
        duration_ms: Date.now() - startedAt,
        error_message: clipText(this.statusText || 'xhr failed'),
      })
    }

    this.addEventListener('loadend', finalize, { once: true })
    this.addEventListener('error', handleError, { once: true })
    this.addEventListener('abort', handleError, { once: true })
    return bridgeState.originalXhrSend.call(this, body)
  }
}

export function ensureAssistantBrowserBridgeInstalled() {
  if (bridgeState.installed || typeof window === 'undefined') return
  bridgeState.installed = true
  attachFetchInterceptor()
  attachXhrInterceptor()
}

function serializeRequestEntry(entry) {
  return {
    id: entry.id,
    source: entry.source,
    method: entry.method,
    url: entry.url,
    state: entry.state,
    status: entry.status,
    ok: entry.ok,
    started_at: entry.started_at,
    finished_at: entry.finished_at,
    duration_ms: entry.duration_ms,
    request_summary: entry.request_summary,
    response_summary: entry.response_summary,
    error_message: entry.error_message,
  }
}

function getRecentRequestEntries(options = {}) {
  const limit = Math.max(1, Math.min(Number(options.limit || 10), MAX_REQUEST_LOGS))
  const onlyErrors = Boolean(options.only_errors)
  const includePending = options.include_pending !== false
  const keyword = clipText(options.keyword || '', 120).toLowerCase()
  return bridgeState.requests
    .filter((entry) => {
      if (!includePending && entry.state === 'pending') return false
      if (onlyErrors && entry.state !== 'error') return false
      if (!keyword) return true
      const haystack = [
        entry.method,
        entry.url,
        entry.state,
        entry.request_summary,
        entry.response_summary,
        entry.error_message,
      ]
        .map((item) => clipText(item))
        .join(' ')
        .toLowerCase()
      return haystack.includes(keyword)
    })
    .slice(0, limit)
    .map(serializeRequestEntry)
}

function serializeElement(element) {
  if (!element || !(element instanceof Element)) return null
  const rect = element.getBoundingClientRect()
  const tag = String(element.tagName || '').toLowerCase()
  const ariaLabel = clipText(element.getAttribute('aria-label') || '', 240)
  const title = clipText(element.getAttribute('title') || '', 240)
  const placeholder = clipText(element.getAttribute('placeholder') || '', 240)
  const name = clipText(element.getAttribute('name') || '', 160)
  const role = clipText(element.getAttribute('role') || '', 120)
  const testId = clipText(
    element.getAttribute('data-testid') ||
      element.getAttribute('data-test-id') ||
      element.getAttribute('data-qa') ||
      '',
    160,
  )
  const selectorHint = (() => {
    if (testId) {
      return `[data-testid="${escapeCssAttributeValue(testId)}"]`
    }
    const id = String(element.id || '').trim()
    if (id) {
      return `#${escapeCssIdentifier(id)}`
    }
    if (ariaLabel) {
      return `${tag}[aria-label="${escapeCssAttributeValue(ariaLabel)}"]`
    }
    if (title) {
      return `${tag}[title="${escapeCssAttributeValue(title)}"]`
    }
    if (name) {
      return `${tag}[name="${escapeCssAttributeValue(name)}"]`
    }
    return tag || ''
  })()
  const accessibleName =
    ariaLabel ||
    title ||
    placeholder ||
    clipText(element.textContent || '', 240) ||
    clipText('value' in element ? element.value : '', 240)
  return {
    tag,
    id: String(element.id || '').trim(),
    class_name: clipText(element.className || '', 200),
    text: clipText(element.textContent || ''),
    value: clipText('value' in element ? element.value : ''),
    role,
    name,
    title,
    aria_label: ariaLabel,
    placeholder,
    data_testid: testId,
    accessible_name: accessibleName,
    selector_hint: selectorHint,
    visible: rect.width > 0 && rect.height > 0,
    disabled: Boolean(element.disabled),
    checked: Boolean(element.checked),
    rect: {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    },
  }
}

function requireElement(selector) {
  const normalizedSelector = String(selector || '').trim()
  if (!normalizedSelector) {
    throw new Error('selector is required')
  }
  const element = document.querySelector(normalizedSelector)
  if (!element) {
    throw new Error(`未找到元素: ${normalizedSelector}`)
  }
  return element
}

function setElementValue(element, value) {
  const normalizedValue = String(value ?? '')
  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    const prototype = Object.getPrototypeOf(element)
    const descriptor = Object.getOwnPropertyDescriptor(prototype, 'value')
    descriptor?.set?.call(element, normalizedValue)
  } else if (element instanceof HTMLSelectElement) {
    element.value = normalizedValue
  } else if (element.isContentEditable) {
    element.textContent = normalizedValue
  } else {
    throw new Error('目标元素不支持填充')
  }
  element.dispatchEvent(new Event('input', { bubbles: true }))
  element.dispatchEvent(new Event('change', { bubbles: true }))
}

function buildPageContext() {
  return {
    title: String(document.title || '').trim(),
    url: sanitizeUrl(window.location.href),
    path: sanitizeUrl(window.location.pathname + window.location.search + window.location.hash),
  }
}

function waitForNavigationTick(delayMs) {
  const timeoutMs = Math.max(0, Math.min(Number(delayMs || 0), 2000))
  if (!timeoutMs) {
    return Promise.resolve()
  }
  return new Promise((resolve) => {
    window.setTimeout(resolve, timeoutMs)
  })
}

function buildNavigationTarget(rawTarget) {
  const target = String(rawTarget || '').trim()
  if (!target) {
    throw new Error('target is required')
  }
  if (/^https?:\/\//i.test(target)) {
    return { mode: 'absolute', url: target }
  }
  if (target.startsWith('#')) {
    const hash = target.startsWith('#/') ? target : `#/${target.replace(/^#+/, '').replace(/^\/+/, '')}`
    return { mode: 'hash', hash }
  }
  if (target.startsWith('/')) {
    return { mode: 'hash', hash: `#${target}` }
  }
  return {
    mode: 'hash',
    hash: `#/${target.replace(/^#+/, '').replace(/^\/+/, '')}`,
  }
}

async function runBrowserAction(args = {}) {
  const action = String(args.action || 'query_dom').trim().toLowerCase()
  if (action === 'query_dom') {
    const selector = String(args.selector || 'body').trim() || 'body'
    const limit = Math.max(1, Math.min(Number(args.limit || 5), MAX_LIST_ITEMS))
    const items = Array.from(document.querySelectorAll(selector))
      .slice(0, limit)
      .map((element) => serializeElement(element))
      .filter(Boolean)
    return {
      action,
      selector,
      count: items.length,
      items,
      page: buildPageContext(),
    }
  }

  if (action === 'get_text') {
    const element = requireElement(args.selector)
    return {
      action,
      selector: String(args.selector || '').trim(),
      text: clipText(element.innerText || element.textContent || ''),
      page: buildPageContext(),
    }
  }

  if (action === 'click') {
    const element = requireElement(args.selector)
    element.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' })
    element.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    element.click()
    return {
      action,
      selector: String(args.selector || '').trim(),
      clicked: true,
      element: serializeElement(element),
      page: buildPageContext(),
    }
  }

  if (action === 'focus') {
    const element = requireElement(args.selector)
    element.focus()
    return {
      action,
      selector: String(args.selector || '').trim(),
      focused: true,
      element: serializeElement(element),
      page: buildPageContext(),
    }
  }

  if (action === 'fill') {
    const element = requireElement(args.selector)
    element.focus()
    setElementValue(element, args.value)
    return {
      action,
      selector: String(args.selector || '').trim(),
      value: clipText(args.value || ''),
      element: serializeElement(element),
      page: buildPageContext(),
    }
  }

  if (action === 'select') {
    const element = requireElement(args.selector)
    if (!(element instanceof HTMLSelectElement)) {
      throw new Error('目标元素不是 select')
    }
    setElementValue(element, args.value)
    return {
      action,
      selector: String(args.selector || '').trim(),
      value: clipText(args.value || ''),
      element: serializeElement(element),
      page: buildPageContext(),
    }
  }

  if (action === 'scroll') {
    const selector = String(args.selector || '').trim()
    const behavior = String(args.behavior || 'smooth').trim() || 'smooth'
    const block = String(args.block || 'center').trim() || 'center'
    if (selector) {
      const element = requireElement(selector)
      element.scrollIntoView({ behavior, block, inline: 'nearest' })
      return {
        action,
        selector,
        element: serializeElement(element),
        page: buildPageContext(),
      }
    }
    window.scrollTo({
      top: Number(args.top || 0),
      left: Number(args.left || 0),
      behavior,
    })
    return {
      action,
      page: buildPageContext(),
      position: {
        top: Number(window.scrollY || 0),
        left: Number(window.scrollX || 0),
      },
    }
  }

  if (action === 'press') {
    const key = String(args.key || '').trim()
    if (!key) throw new Error('key is required')
    const selector = String(args.selector || '').trim()
    const element = selector ? requireElement(selector) : document.activeElement || document.body
    if (typeof element.focus === 'function') {
      element.focus()
    }
    for (const type of ['keydown', 'keyup']) {
      element.dispatchEvent(new KeyboardEvent(type, { key, bubbles: true }))
    }
    return {
      action,
      key,
      selector,
      element: serializeElement(element),
      page: buildPageContext(),
    }
  }

  if (action === 'navigate') {
    const target = String(args.target || args.value || '').trim()
    if (!target) throw new Error('target is required')
    const replace = Boolean(args.replace)
    const waitMs = Math.max(0, Math.min(Number(args.wait_ms || 180), 2000))
    const previousPage = buildPageContext()
    const normalizedTarget = target.toLowerCase()
    if (normalizedTarget === 'back') {
      window.history.back()
      await waitForNavigationTick(waitMs)
      return {
        action,
        target,
        navigated: true,
        previous_page: previousPage,
        page: buildPageContext(),
      }
    }
    if (normalizedTarget === 'forward') {
      window.history.forward()
      await waitForNavigationTick(waitMs)
      return {
        action,
        target,
        navigated: true,
        previous_page: previousPage,
        page: buildPageContext(),
      }
    }
    if (normalizedTarget === 'reload') {
      window.location.reload()
      return {
        action,
        target,
        reloading: true,
        previous_page: previousPage,
        page: previousPage,
      }
    }
    const navigation = buildNavigationTarget(target)
    if (navigation.mode === 'absolute') {
      if (replace) {
        window.location.replace(navigation.url)
      } else {
        window.location.assign(navigation.url)
      }
      return {
        action,
        target,
        navigated: true,
        previous_page: previousPage,
        page: buildPageContext(),
      }
    }
    const nextHash = navigation.hash
    if (replace) {
      const baseUrl = window.location.href.split('#')[0]
      window.location.replace(`${baseUrl}${nextHash}`)
    } else {
      window.location.hash = nextHash
    }
    await waitForNavigationTick(waitMs)
    return {
      action,
      target,
      navigated: true,
      previous_page: previousPage,
      page: buildPageContext(),
    }
  }

  if (action === 'run_script') {
    const script = String(args.script || '').trim()
    if (!script) throw new Error('script is required')
    const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
    const fn = new AsyncFunction(
      'context',
      `"use strict"; ${script}`,
    )
    const result = await fn({
      window,
      document,
      selector: String(args.selector || '').trim(),
      value: args.value,
      args: Array.isArray(args.args) ? args.args : [],
    })
    return {
      action,
      result: summarizeUnknown(result),
      page: buildPageContext(),
    }
  }

  throw new Error(`不支持的浏览器操作: ${action}`)
}

export async function executeAssistantBrowserToolCall(payload = {}) {
  ensureAssistantBrowserBridgeInstalled()
  const toolName = String(payload.tool_name || '').trim()
  const args = payload.args && typeof payload.args === 'object' ? payload.args : {}
  if (toolName === 'global_assistant_browser_requests') {
    return {
      tool: toolName,
      page: buildPageContext(),
      total_recent: bridgeState.requests.length,
      items: getRecentRequestEntries(args),
    }
  }
  if (toolName === 'global_assistant_browser_actions') {
    return {
      tool: toolName,
      ...(await runBrowserAction(args)),
    }
  }
  throw new Error(`不支持的浏览器工具: ${toolName}`)
}
