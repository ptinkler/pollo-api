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
        const { promptLogin } = useAuth()
        promptLogin()
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
export const apiDelete = endpoint => apiSend('DELETE', endpoint)

/** POST a file as multipart form data (field "file"). */
export function apiUpload(endpoint, file) {
  const form = new FormData()
  form.append('file', file)
  return apiSend('POST', endpoint, form)
}

// Pollo credits remaining (the only legacy /api/usage route Studio still uses).
export const fetchBalance = () => apiGet('/api/usage/balance')
