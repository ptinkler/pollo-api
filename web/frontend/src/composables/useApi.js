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
      if (response.ok || response.status < 500 || attempt === retries) {
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

// JSON (or FormData) request with the error's `detail` as the message
async function apiSend(method, endpoint, data) {
  const isForm = data instanceof FormData
  const options = { method }
  if (data !== undefined) {
    options.body = isForm ? data : JSON.stringify(data)
    if (!isForm) options.headers = { 'Content-Type': 'application/json' }
  }
  const response = await fetchWithRetry(`${BASE_URL}${endpoint}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `API error: ${response.status}`)
  }
  return response.json()
}

export const apiPost = (endpoint, data = {}) => apiSend('POST', endpoint, data)
export const apiPut = (endpoint, data = {}) => apiSend('PUT', endpoint, data)
export const apiPatch = (endpoint, data = {}) => apiSend('PATCH', endpoint, data)
export const apiDelete = (endpoint) => apiSend('DELETE', endpoint)

/** POST a file as multipart form data (field "file"). */
export function apiUpload(endpoint, file) {
  const form = new FormData()
  form.append('file', file)
  return apiSend('POST', endpoint, form)
}

// `?a=1&b=2` from an object, or '' when empty
const query = (params) => {
  const qs = new URLSearchParams(params).toString()
  return qs ? `?${qs}` : ''
}

// Project APIs
export const fetchProjects = (params = {}) => apiGet(`/api/projects${query(params)}`)
export const fetchProject = (name, params = {}) => apiGet(`/api/projects/${encodeURIComponent(name)}${query(params)}`)
export const createProject = (data) => apiPost('/api/projects', data)
export const updateProject = (name, data) => apiPut(`/api/projects/${encodeURIComponent(name)}`, data)
export const archiveProject = (slug) => apiPost(`/api/projects/${encodeURIComponent(slug)}/archive`)
export const unarchiveProject = (slug) => apiPost(`/api/projects/${encodeURIComponent(slug)}/unarchive`)
export const deleteProject = (slug) => apiDelete(`/api/projects/${encodeURIComponent(slug)}`)

// Job APIs
export const fetchJobs = (params = {}) => apiGet(`/api/jobs${query(params)}`)
export const fetchJob = (jobId) => apiGet(`/api/jobs/${jobId}`)
export const checkJob = (jobId) => apiPost(`/api/jobs/${jobId}/check`)
export const downloadJobVideo = (jobId) => apiPost(`/api/jobs/${jobId}/download`)
export const deleteJob = (jobId) => apiDelete(`/api/jobs/${jobId}`)
export const archiveJob = (jobId) => apiPost(`/api/jobs/${jobId}/archive`)
export const unarchiveJob = (jobId) => apiPost(`/api/jobs/${jobId}/unarchive`)
// Starred generations (per media file) — the home page's Favourites tab
export const fetchFavourites = () => apiGet('/api/favourites')
export const addFavourite = (jobId, filename) => apiPost('/api/favourites', { job_id: jobId, filename })
export const removeFavourite = (filename) => apiDelete(`/api/favourites/${encodeURIComponent(filename)}`)
export const bulkMoveJobs = (jobIds, targetProject) =>
  apiPost('/api/jobs/bulk-move', { job_ids: jobIds, target_project: targetProject })

// Generate API
export const generateVideo = (data) => apiPost('/api/generate', data)
export const generateImage = (data) => apiPost('/api/generate-image', data)

// Source / ref image upload (saved in the project; returns { image_url: "local:<file>" })
export const uploadSourceImage = (project, file) =>
  apiUpload(`/api/projects/${encodeURIComponent(project)}/source-image`, file)
export const uploadRefImage = (project, file) =>
  apiUpload(`/api/projects/${encodeURIComponent(project)}/ref-image`, file)
export const deleteSourceImage = (project, filename) =>
  apiDelete(`/api/projects/${encodeURIComponent(project)}/source-image${filename ? query({ f: filename }) : ''}`)
export const getRefImageUrl = (project, filename) =>
  `/api/projects/${encodeURIComponent(project)}/source-image?f=${encodeURIComponent(filename)}`

// "local:<file>" refs (images uploaded into the project) → their preview URL, else null
export const localImageFilename = (url) => ((url || '').startsWith('local:') ? url.slice(6) : '')
export const getLocalImagePreviewUrl = (project, url) => {
  const filename = localImageFilename(url)
  return filename ? getRefImageUrl(project, filename) : null
}

// Models API
export const fetchModels = (legacy = false) => apiGet(`/api/models?legacy=${legacy ? 'true' : 'false'}`)

// Usage / Credits API
export const fetchUsage = (days = 30) => apiGet(`/api/usage?days=${days}`)
export const fetchBalance = () => apiGet('/api/usage/balance')
export const fetchUsageProjectDetails = (project, days = 30) => apiGet(`/api/usage/project/${encodeURIComponent(project)}?days=${days}`)
export const fetchCreditEstimate = ({ model, resolution, length, generate_audio }) => {
  const params = new URLSearchParams({ model })
  if (resolution != null) params.set('resolution', resolution)
  if (length != null) params.set('length', length)
  if (generate_audio != null) params.set('generate_audio', generate_audio)
  return apiGet(`/api/usage/estimate?${params.toString()}`)
}

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
