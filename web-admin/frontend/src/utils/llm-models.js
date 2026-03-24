export const DEFAULT_MODEL_TYPE = 'text_generation'

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
