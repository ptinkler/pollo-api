import { apiGet, apiPost, apiPut } from './useApi'

// Account + per-user keys (OAuth sign-in, admin, provider keys).
export const fetchMe = () => apiGet('/api/auth/me')
export const fetchAuthProviders = () => apiGet('/api/auth/providers')
export const fetchUserKeys = () => apiGet('/api/keys')
export const saveUserKeys = keys => apiPut('/api/keys', { keys })

// Per-user source-media hosting (where uploads go for Pollo to fetch).
export const fetchUploadPrefs = () => apiGet('/api/settings/uploads')
export const saveUploadPrefs = prefs => apiPut('/api/settings/uploads', prefs)
export const testSelfhost = selfhost_base => apiPost('/api/settings/uploads/test-selfhost', { selfhost_base })

export const UPLOAD_HOSTS = [
  { id: 'litterbox', label: 'Litterbox (temp host, up to ~1GB)' },
  { id: 'tmpfiles', label: 'tmpfiles.org (temp host)' },
  { id: 'selfhost', label: 'Self-host from this instance' },
]
export const EXPIRY_LABELS = { 60: '1 hour', 720: '12 hours', 1440: '24 hours', 4320: '72 hours' }

// Provider sign-in is a full-page redirect so the OAuth cookies land correctly.
export const authLoginUrl = provider => `/api/auth/login/${provider}`

export const PROVIDER_LABELS = { google: 'Google', microsoft: 'Microsoft', x: 'X' }
export const KEY_PROVIDERS = [
  { id: 'pollo', label: 'Pollo' },
  { id: 'venice', label: 'Venice' },
  { id: 'openrouter', label: 'OpenRouter' },
]
