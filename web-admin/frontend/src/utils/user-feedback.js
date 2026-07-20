export const FEEDBACK_CATEGORIES = [
  { value: 'product_bug', label: '产品功能有问题', short: '功能异常、菜单缺失或数据错误', icon: 'BG' },
  { value: 'ui_experience', label: '页面或交互体验', short: '布局、操作路径或视觉体验问题', icon: 'UI' },
  { value: 'performance_stability', label: '性能与稳定性', short: '卡顿、崩溃、加载慢或连接异常', icon: 'PS' },
  { value: 'ai_answer', label: 'AI 回答有问题', short: '内容错误、答非所问或表达不佳', icon: 'AI' },
  { value: 'ai_execution', label: 'AI 执行过程有问题', short: '工具、权限、任务或产物执行失败', icon: 'EX' },
  { value: 'feature_request', label: '功能建议', short: '希望新增或改进的产品能力', icon: 'FR' },
  { value: 'security_privacy', label: '安全与隐私', short: '权限、敏感信息或数据安全问题', icon: 'SP' },
  { value: 'other', label: '其他反馈', short: '不属于以上类型的意见与建议', icon: 'OT' },
]

export const FEEDBACK_STATUSES = [
  { value: 'submitted', label: '已提交', type: 'info' },
  { value: 'triaged', label: '已受理', type: 'primary' },
  { value: 'processing', label: '处理中', type: 'warning' },
  { value: 'waiting_user', label: '待用户补充', type: 'warning' },
  { value: 'resolved', label: '已解决', type: 'success' },
  { value: 'closed', label: '已关闭', type: 'info' },
  { value: 'withdrawn', label: '已撤回', type: 'info' },
]

export const FEEDBACK_PRIORITIES = [
  { value: 'low', label: '低' },
  { value: 'normal', label: '普通' },
  { value: 'high', label: '高' },
  { value: 'urgent', label: '紧急' },
]

export function feedbackCategoryLabel(value) {
  return FEEDBACK_CATEGORIES.find((item) => item.value === value)?.label || value || '其他反馈'
}

export function feedbackStatusMeta(value) {
  return FEEDBACK_STATUSES.find((item) => item.value === value) || { label: value || '未知', type: 'info' }
}

export function collectFeedbackContext(route) {
  const colorScheme = window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  return {
    route_path: String(route?.fullPath || window.location.hash || '').slice(0, 500),
    page_title: String(document.title || '').slice(0, 200),
    client_type: window.__TAURI_INTERNALS__ ? 'desktop' : 'web',
    client_version: String(import.meta.env.VITE_APP_VERSION || ''),
    os_name: String(navigator.userAgentData?.platform || navigator.platform || '').slice(0, 120),
    window_size: `${window.innerWidth}x${window.innerHeight}`,
    screen_size: `${window.screen?.width || 0}x${window.screen?.height || 0}`,
    theme: colorScheme,
    scale_factor: Number(window.devicePixelRatio || 1),
  }
}

export function createIdempotencyKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  return `feedback-${Date.now()}-${Math.random().toString(16).slice(2)}`
}
