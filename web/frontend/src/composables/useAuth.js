import { ref } from 'vue'

// Shared across all callers.
const isAuthenticated = ref(false)
const currentUser = ref(null)
const showLogin = ref(false)

async function _post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || 'Request failed')
  return data
}

function _signedIn(user) {
  isAuthenticated.value = true
  currentUser.value = user
  showLogin.value = false
}

async function _checkStatus() {
  try {
    const res = await fetch('/api/auth/status', { credentials: 'same-origin' })
    const data = await res.json()
    isAuthenticated.value = data.authenticated
    currentUser.value = data.user
    if (!data.authenticated) showLogin.value = true
  } catch {
    // Server unreachable — leave state as-is
  }
}

_checkStatus()

export function useAuth() {
  async function login(email, password) {
    _signedIn(await _post('/api/auth/login', { email, password }))
  }

  // One-click local dev account (only works when the server has DEV_LOGIN on).
  async function devLogin() {
    _signedIn(await _post('/api/auth/dev-login', {}))
  }

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' })
    isAuthenticated.value = false
    currentUser.value = null
    showLogin.value = true
  }

  function promptLogin() {
    showLogin.value = true
  }

  return { isAuthenticated, currentUser, showLogin, login, devLogin, logout, promptLogin }
}
