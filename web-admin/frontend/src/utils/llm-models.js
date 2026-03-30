export const DEFAULT_MODEL_TYPE = 'text_generation'

const CHAT_PARAMETER_FALLBACKS = {
  image_resolution: {
    dictionaryKey: 'llm_image_resolutions',
    defaultValue: '1080x1080',
    valueType: 'string',
    fallbackOptions: [
      {
        id: '720x720',
        label: '720x720',
        description: '固定尺寸基准值，后端会结合当前图片比例自动换算最终尺寸。',
      },
      {
        id: '1080x1080',
        label: '1080x1080',
        description: '固定尺寸基准值，后端会结合当前图片比例自动换算最终尺寸。',
      },
      {
        id: '2160x2160',
        label: '2160x2160',
        description: '固定尺寸基准值，后端会结合当前图片比例自动换算最终尺寸。',
      },
    ],
  },
  image_aspect_ratio: {
    dictionaryKey: 'llm_image_aspect_ratios',
    defaultValue: '1:1',
    valueType: 'string',
  },
  image_style: {
    dictionaryKey: 'llm_image_styles',
    defaultValue: 'auto',
    valueType: 'string',
  },
  image_quality: {
    dictionaryKey: 'llm_image_qualities',
    defaultValue: 'high',
    valueType: 'string',
  },
  video_aspect_ratio: {
    dictionaryKey: 'llm_video_aspect_ratios',
    defaultValue: '16:9',
    valueType: 'string',
  },
  video_style: {
    dictionaryKey: 'llm_video_styles',
    defaultValue: 'cinematic',
    valueType: 'string',
  },
  video_duration_seconds: {
    dictionaryKey: 'llm_video_duration_seconds',
    defaultValue: 5,
    valueType: 'number',
  },
  video_motion_strength: {
    dictionaryKey: 'llm_video_motion_strengths',
    defaultValue: 'medium',
    valueType: 'string',
  },
}

export const FALLBACK_MODEL_TYPE_OPTIONS = [
  {
    id: 'text_generation',
    label: '文本生成',
    description: '适合问答、写作、代码与通用对话。',
    chat_parameter_mode: 'text',
  },
  {
    id: 'multimodal_chat',
    label: '多模态对话',
    description: '支持图文理解和通用对话，参数面板沿用文本模式。',
    chat_parameter_mode: 'text',
  },
  {
    id: 'image_generation',
    label: '图片生成',
    description: '适合根据提示词或参考图生成图片。',
    chat_parameter_mode: 'image',
  },
  {
    id: 'video_generation',
    label: '视频生成',
    description: '适合生成短视频或动画片段。',
    chat_parameter_mode: 'video',
  },
  {
    id: 'audio_generation',
    label: '音频生成',
    description: '适合语音、配音或音频内容生成。',
    chat_parameter_mode: 'text',
  },
]

function getChatParameterConfig(parameterKey) {
  const config = CHAT_PARAMETER_FALLBACKS[String(parameterKey || '').trim()]
  if (!config) {
    throw new Error(`Unsupported chat parameter key: ${parameterKey}`)
  }
  return config
}

function coerceChatParameterValue(parameterKey, value) {
  const config = getChatParameterConfig(parameterKey)
  if (config.valueType === 'number') {
    const normalized = Number(value)
    return Number.isFinite(normalized) ? normalized : Number(config.defaultValue)
  }
  return String(value || '').trim()
}

export function listChatParameterKeys() {
  return Object.keys(CHAT_PARAMETER_FALLBACKS)
}

export function getChatParameterDictionaryKey(parameterKey) {
  return String(getChatParameterConfig(parameterKey).dictionaryKey || '').trim()
}

export function getChatParameterFallbackOptions(parameterKey) {
  const config = getChatParameterConfig(parameterKey)
  const fallbackOptions = Array.isArray(config.fallbackOptions)
    ? config.fallbackOptions
    : []
  if (fallbackOptions.length) {
    return fallbackOptions.map((item) => ({
      id: String(item?.id || '').trim(),
      label: String(item?.label || item?.id || '').trim(),
      description: String(item?.description || '').trim(),
    })).filter((item) => item.id)
  }
  const defaultValue = getChatParameterDefaultValue(parameterKey)
  return [
    {
      id: String(defaultValue),
      label: String(defaultValue),
      description: '',
    },
  ]
}

export function getChatParameterDefaultValue(parameterKey) {
  return coerceChatParameterValue(parameterKey, getChatParameterConfig(parameterKey).defaultValue)
}

export function resolveChatParameterOptions(parameterKey, options = []) {
  const source = Array.isArray(options) && options.length
    ? options
    : getChatParameterFallbackOptions(parameterKey)
  return source
    .map((item) => {
      const id = String(item?.id || '').trim()
      if (!id) return null
      return {
        id,
        label: String(item?.label || id).trim() || id,
        description: String(item?.description || '').trim(),
        value: coerceChatParameterValue(parameterKey, id),
      }
    })
    .filter(Boolean)
}

export function normalizeChatParameterValue(parameterKey, value, options = []) {
  const normalized = coerceChatParameterValue(parameterKey, value)
  const resolvedOptions = resolveChatParameterOptions(parameterKey, options)
  if (resolvedOptions.some((item) => item.value === normalized)) {
    return normalized
  }
  return getChatParameterDefaultValue(parameterKey)
}

export function formatChatParameterValueLabel(parameterKey, value, options = []) {
  const normalized = normalizeChatParameterValue(parameterKey, value, options)
  const matched = resolveChatParameterOptions(parameterKey, options).find((item) => item.value === normalized)
  return matched?.label || String(normalized)
}

export function normalizeModelType(value, options = FALLBACK_MODEL_TYPE_OPTIONS) {
  const normalized = String(value || '').trim().toLowerCase()
  const allowed = new Set((Array.isArray(options) ? options : []).map((item) => String(item?.id || '').trim()).filter(Boolean))
  if (allowed.has(normalized)) return normalized
  return DEFAULT_MODEL_TYPE
}

export function buildModelTypeMetaMap(options = FALLBACK_MODEL_TYPE_OPTIONS) {
  const map = new Map()
  const source = Array.isArray(options) && options.length ? options : FALLBACK_MODEL_TYPE_OPTIONS
  source.forEach((item) => {
    const id = String(item?.id || '').trim()
    if (!id) return
    map.set(id, {
      id,
      label: String(item?.label || id).trim(),
      description: String(item?.description || '').trim(),
      chat_parameter_mode: String(item?.chat_parameter_mode || 'text').trim() || 'text',
    })
  })
  if (!map.has(DEFAULT_MODEL_TYPE)) {
    map.set(DEFAULT_MODEL_TYPE, {
      id: DEFAULT_MODEL_TYPE,
      label: '文本生成',
      description: '',
      chat_parameter_mode: 'text',
    })
  }
  return map
}

export function normalizeProviderModelConfigs(provider, options = FALLBACK_MODEL_TYPE_OPTIONS) {
  const values = []
  const seen = new Set()
  const rawConfigs = Array.isArray(provider?.model_configs) ? provider.model_configs : []
  const push = (nameValue, typeValue = DEFAULT_MODEL_TYPE) => {
    const name = String(nameValue || '').trim()
    if (!name || seen.has(name)) return
    seen.add(name)
    values.push({
      name,
      model_type: normalizeModelType(typeValue, options),
    })
  }
  rawConfigs.forEach((item) => {
    if (!item || typeof item !== 'object') return
    push(item.name || item.model_name, item.model_type)
  })
  if (Array.isArray(provider?.models)) {
    provider.models.forEach((item) => push(item, DEFAULT_MODEL_TYPE))
  }
  const defaultModel = String(provider?.default_model || '').trim()
  if (defaultModel && !seen.has(defaultModel)) {
    push(defaultModel, DEFAULT_MODEL_TYPE)
  }
  return values
}

export function normalizeProviderModelNames(provider, options = FALLBACK_MODEL_TYPE_OPTIONS) {
  return normalizeProviderModelConfigs(provider, options).map((item) => item.name)
}

export function findProviderModelConfig(provider, modelName = '', options = FALLBACK_MODEL_TYPE_OPTIONS) {
  const normalizedName = String(modelName || '').trim()
  const configs = normalizeProviderModelConfigs(provider, options)
  if (normalizedName) {
    return configs.find((item) => item.name === normalizedName) || null
  }
  return configs[0] || null
}
