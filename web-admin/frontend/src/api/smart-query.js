import axios from 'axios'

export async function smartQuery(projectId, message) {
  const response = await axios.post(`/api/projects/${projectId}/smart-query`, { message })
  return response.data
}
