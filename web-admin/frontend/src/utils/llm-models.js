export const DEFAULT_MODEL_TYPE = 'text_generation'

const MODEL_TYPE_ALIASES = {
  chat: 'text_generation',
  chat_completion: 'text_generation',
  chat_completions: 'text_generation',
  completion: 'text_generation',
  text: 'text_generation',
  text_generation: 'text_generation',
  vision: 'multimodal_chat',
  vision_chat: 'multimodal_chat',
  multimodal: 'multimodal_chat',
  multimodal_chat: 'multimodal_chat',
  image: 'image_generation',
  images: 'image_generation',
  image_generation: 'image_generation',
  video: 'video_generation',
  videos: 'video_generation',
  video_generation: 'video_generation',
  speech: 'audio_generation',
  tts: 'audio_generation',
  text_to_speech: 'audio_generation',
  audio: 'audio_generation',
  audio_generation: 'audio_generation',
  transcription: 'audio_transcription',
  transcriptions: 'audio_transcription',
  speech_to_text: 'audio_transcription',
  stt: 'audio_transcription',
  asr: 'audio_transcription',
  audio_transcription: 'audio_transcription',
}

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

export const DEFAULT_ATTACHMENT_MODE = 'local_extract'
export const UNSUPPORTED_ATTACHMENT_MODE = 'unsupported'

export const ATTACHMENT_MODE_LABELS = {
  provider_file: '供应商文件直传',
  inline_image: '图片内联输入',
  local_extract: '本地解析文本',
  retrieval: '检索增强',
  unsupported: '不支持附件',
}

export function normalizeAttachmentMode(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (ATTACHMENT_MODE_LABELS[normalized]) return normalized
  return DEFAULT_ATTACHMENT_MODE
}

export function isAttachmentSupportedMode(mode) {
  return normalizeAttachmentMode(mode) !== UNSUPPORTED_ATTACHMENT_MODE
}

export const FALLBACK_MODEL_TYPE_OPTIONS = [
  {
    id: 'text_generation',
    label: 'Chat Completions / 文本对话',
    description: '适合问答、写作、代码与通用对话；常见别名：chat_completion、text。',
    chat_parameter_mode: 'text',
    project_chat_allowed_file_types: [],
    attachment_mode: 'local_extract',
    attachment_max_files: 6,
    attachment_max_file_size_mb: 15,
  },
  {
    id: 'multimodal_chat',
    label: 'Vision Chat / 多模态对话',
    description: '支持图文理解和通用对话；常见别名：vision_chat、multimodal。',
    chat_parameter_mode: 'text',
    project_chat_allowed_file_types: [],
    attachment_mode: 'inline_image',
    attachment_max_files: 6,
    attachment_max_file_size_mb: 15,
  },
  {
    id: 'image_generation',
    label: 'Images / 图片生成',
    description: '适合根据提示词或参考图生成图片；常见别名：image、images。',
    chat_parameter_mode: 'image',
    project_chat_allowed_file_types: [],
    attachment_mode: 'unsupported',
    attachment_max_files: 0,
    attachment_max_file_size_mb: 0,
  },
  {
    id: 'video_generation',
    label: 'Videos / 视频生成',
    description: '适合生成短视频或动画片段；常见别名：video、videos。',
    chat_parameter_mode: 'video',
    project_chat_allowed_file_types: [],
    attachment_mode: 'unsupported',
    attachment_max_files: 0,
    attachment_max_file_size_mb: 0,
  },
  {
    id: 'audio_generation',
    label: 'Speech / 音频生成',
    description: '适合语音、配音或音频内容生成；常见别名：speech、tts。',
    chat_parameter_mode: 'text',
    project_chat_allowed_file_types: [],
    attachment_mode: 'unsupported',
    attachment_max_files: 0,
    attachment_max_file_size_mb: 0,
  },
  {
    id: 'audio_transcription',
    label: 'Transcriptions / 音频转写',
    description: '适合语音识别、语音转文本与实时转写场景；常见别名：transcription、speech_to_text、asr。',
    chat_parameter_mode: 'text',
    project_chat_allowed_file_types: [],
    attachment_mode: 'unsupported',
    attachment_max_files: 0,
    attachment_max_file_size_mb: 0,
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
  const normalized = String(value || '').trim().toLowerCase().replace(/[-\s]+/g, '_')
  const allowed = new Set((Array.isArray(options) ? options : []).map((item) => String(item?.id || '').trim()).filter(Boolean))
  if (allowed.has(normalized)) return normalized
  const aliased = MODEL_TYPE_ALIASES[normalized]
  if (allowed.has(aliased)) return aliased
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
      project_chat_allowed_file_types: normalizeModelTypeFileTypes(item?.project_chat_allowed_file_types),
      attachment_mode: normalizeAttachmentMode(item?.attachment_mode),
      attachment_max_files: coercePositiveInt(item?.attachment_max_files, 6),
      attachment_max_file_size_mb: coercePositiveInt(item?.attachment_max_file_size_mb, 15),
    })
  })
  if (!map.has(DEFAULT_MODEL_TYPE)) {
    map.set(DEFAULT_MODEL_TYPE, {
      id: DEFAULT_MODEL_TYPE,
      label: '文本生成',
      description: '',
      chat_parameter_mode: 'text',
      project_chat_allowed_file_types: [],
      attachment_mode: DEFAULT_ATTACHMENT_MODE,
      attachment_max_files: 6,
      attachment_max_file_size_mb: 15,
    })
  }
  return map
}

function coercePositiveInt(value, fallback) {
  const normalized = Number(value)
  if (!Number.isFinite(normalized) || normalized < 0) return fallback
  return Math.floor(normalized)
}

function normalizeModelTypeFileTypes(value) {
  if (!Array.isArray(value)) return []
  const seen = new Set()
  return value
    .map((item) => String(item || '').trim().toLowerCase())
    .filter((item) => {
      if (!item || seen.has(item)) return false
      seen.add(item)
      return true
    })
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
