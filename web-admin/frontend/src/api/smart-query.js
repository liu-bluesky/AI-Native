import api from '@/utils/api.js'

export async function smartQuery(projectId, message) {
  return api.post(`/projects/${encodeURIComponent(projectId)}/smart-query`, { message })
}
