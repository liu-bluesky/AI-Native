import {
  FALLBACK_MODEL_TYPE_OPTIONS,
  getChatParameterDefaultValue,
  getChatParameterDictionaryKey,
  getChatParameterFallbackOptions,
  listChatParameterKeys,
} from './llm-models.js'

export async function fetchDictionary(dictionaryKey) {
  const normalizedKey = String(dictionaryKey || '').trim()
  if (!normalizedKey) {
    throw new Error('dictionaryKey is required')
  }
  if (normalizedKey === 'llm_model_types') {
    return { options: FALLBACK_MODEL_TYPE_OPTIONS, default_value: undefined }
  }
  const parameterKey = listChatParameterKeys().find(
    (key) => getChatParameterDictionaryKey(key) === normalizedKey,
  )
  if (!parameterKey) {
    return { options: [], default_value: undefined }
  }
  return {
    options: getChatParameterFallbackOptions(parameterKey),
    default_value: getChatParameterDefaultValue(parameterKey),
  }
}
