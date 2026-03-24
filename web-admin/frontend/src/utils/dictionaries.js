import api from '@/utils/api.js'

export async function fetchDictionary(dictionaryKey) {
  const normalizedKey = String(dictionaryKey || '').trim()
  if (!normalizedKey) {
    throw new Error('dictionaryKey is required')
  }
  return api.get(`/dictionaries/${encodeURIComponent(normalizedKey)}`)
}
