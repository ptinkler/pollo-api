import { apiGet, apiPut } from './useApi'

// Account + per-user keys (OAuth sign-in, admin, provider keys).
export const fetchMe = () => apiGet('/api/auth/me')
export const fetchAuthProviders = () => apiGet('/api/auth/providers')
export const fetchUserKeys = () => apiGet('/api/keys')
export const saveUserKeys = keys => apiPut('/api/keys', { keys })

// Provider sign-in is a full-page redirect so the OAuth cookies land correctly.
export const authLoginUrl = provider => `/api/auth/login/${provider}`

export const PROVIDER_LABELS = { google: 'Google', microsoft: 'Microsoft', x: 'X' }
export const KEY_PROVIDERS = [
  { id: 'pollo', label: 'Pollo' },
  { id: 'venice', label: 'Venice' },
  { id: 'openrouter', label: 'OpenRouter' },
]
