import { useAuth } from './useAuth'

const BASE_URL = ''

const RETRY_CONFIG = {
  maxRetries: 3,
  initialDelay: 500,
  maxDelay: 2000,
}

async function fetchWithRetry(url, options = {}, retries = RETRY_CONFIG.maxRetries) {
  let lastError
  let delay = RETRY_CONFIG.initialDelay

  const opts = { credentials: 'same-origin', ...options }

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, opts)
      if (response.status === 401) {
        const { promptForKey } = useAuth()
        promptForKey()
        throw new Error('API key required')
      }
      if (response.ok || response.status < 500) {
        return response
      }
      lastError = new Error(`API error: ${response.status}`)
    } catch (err) {
      lastError = err
      if (err.message === 'API key required') throw err
    }

    if (attempt < retries) {
      await new Promise(resolve => setTimeout(resolve, delay))
      delay = Math.min(delay * 2, RETRY_CONFIG.maxDelay)
    }
  }

  throw lastError
}

export async function apiGet(endpoint) {
  const response = await fetchWithRetry(`${BASE_URL}${endpoint}`)
  if (!response.ok) throw new Error(`API error: ${response.status}`)
  return response.json()
}

export async function apiPost(endpoint, data = {}) {
  const response = await fetchWithRetry(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `API error: ${response.status}`)
  }
  return response.json()
}

export async function apiPut(endpoint, data = {}) {
  const response = await fetchWithRetry(`${BASE_URL}${endpoint}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `API error: ${response.status}`)
  }
  return response.json()
}

export async function apiDelete(endpoint) {
  const response = await fetchWithRetry(`${BASE_URL}${endpoint}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `API error: ${response.status}`)
  }
  return response.json()
}

// Project APIs
export const fetchProjects = (params = {}) => {
  const query = new URLSearchParams(params).toString()
  return apiGet(`/api/projects${query ? '?' + query : ''}`)
}
export const fetchProject = (name, params = {}) => {
  const query = new URLSearchParams(params).toString()
  return apiGet(`/api/projects/${encodeURIComponent(name)}${query ? '?' + query : ''}`)
}
export const createProject = (data) => apiPost('/api/projects', data)
export const updateProject = (name, data) => apiPut(`/api/projects/${encodeURIComponent(name)}`, data)
export const archiveProject = (slug) => apiPost(`/api/projects/${encodeURIComponent(slug)}/archive`)
export const unarchiveProject = (slug) => apiPost(`/api/projects/${encodeURIComponent(slug)}/unarchive`)
export const deleteProject = (slug) => apiDelete(`/api/projects/${encodeURIComponent(slug)}`)

// Job APIs
export const fetchJobs = (params = {}) => {
  const query = new URLSearchParams(params).toString()
  return apiGet(`/api/jobs${query ? '?' + query : ''}`)
}
export const fetchJob = (jobId) => apiGet(`/api/jobs/${jobId}`)
export const checkJob = (jobId) => apiPost(`/api/jobs/${jobId}/check`)
export const downloadJobVideo = (jobId) => apiPost(`/api/jobs/${jobId}/download`)
export const deleteJob = (jobId) => apiDelete(`/api/jobs/${jobId}`)
export const archiveJob = (jobId) => apiPost(`/api/jobs/${jobId}/archive`)
export const unarchiveJob = (jobId) => apiPost(`/api/jobs/${jobId}/unarchive`)
export const bulkMoveJobs = (jobIds, targetProject) =>
  apiPost('/api/jobs/bulk-move', { job_ids: jobIds, target_project: targetProject })

// Generate API
export const generateVideo = (data) => apiPost('/api/generate', data)
export const generateImage = (data) => apiPost('/api/generate-image', data)

// Source image upload
export async function uploadSourceImage(project, file) {
  return _uploadImage(project, file, 'source-image')
}
export const deleteSourceImage = (project, filename) => {
  const query = filename ? '?f=' + encodeURIComponent(filename) : ''
  return apiDelete(`/api/projects/${encodeURIComponent(project)}/source-image${query}`)
}
export const getSourceImageUrl = (project) =>
  `/api/projects/${encodeURIComponent(project)}/source-image`

// Ref image upload
export async function uploadRefImage(project, file) {
  return _uploadImage(project, file, 'ref-image')
}
export const getRefImageUrl = (project, filename) =>
  `/api/projects/${encodeURIComponent(project)}/source-image?f=${encodeURIComponent(filename)}`

async function _uploadImage(project, file, endpoint) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetchWithRetry(
    `${BASE_URL}/api/projects/${encodeURIComponent(project)}/${endpoint}`,
    { method: 'POST', body: formData },
  )
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `Upload failed: ${response.status}`)
  }
  return response.json()
}

// Models API
export const fetchModels = () => apiGet('/api/models')

// Usage / Credits API
export const fetchUsage = (days = 30) => apiGet(`/api/usage?days=${days}`)
export const fetchBalance = () => apiGet('/api/usage/balance')
export const fetchUsageProjectDetails = (project, days = 30) => apiGet(`/api/usage/project/${encodeURIComponent(project)}?days=${days}`)

// Video APIs
export const deleteVideo = (project, filename) =>
  apiDelete(`/api/videos/${encodeURIComponent(project)}/${encodeURIComponent(filename)}`)

// URL helpers
export const getImageUrl = (project, thumbTs) => {
  const base = `/image/${encodeURIComponent(project)}`
  return thumbTs ? `${base}?t=${thumbTs}` : base
}
export const getVideoUrl = (project, filename) => `/video/${encodeURIComponent(project)}/${encodeURIComponent(filename)}`
export const getVideoThumbUrl = (project, filename) => `/video-thumb/${encodeURIComponent(project)}/${encodeURIComponent(filename)}`

export function getFilenameFromPath(videoPath) {
  if (!videoPath) return ''
  return videoPath.replace(/\\/g, '/').split('/').pop()
}
