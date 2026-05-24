import { ref, computed } from 'vue'

// Module-level singletons shared across all composable calls
const isAuthenticated = ref(false)
const authEnabled = ref(true)
const showKeyModal = ref(false)
const _initialized = ref(false)

async function _checkStatus() {
  try {
    const res = await fetch('/api/auth/status', { credentials: 'same-origin' })
    const data = await res.json()
    authEnabled.value = data.enabled
    isAuthenticated.value = data.authenticated
    if (data.enabled && !data.authenticated) {
      showKeyModal.value = true
    }
  } catch {
    // Server unreachable — leave state as-is
  }
  _initialized.value = true
}

// Kick off status check once on module load
_checkStatus()

export function useAuth() {
  const hasKey = computed(() => isAuthenticated.value)

  async function login(key) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: key.trim() }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || 'Invalid API key')
    }
    isAuthenticated.value = true
    showKeyModal.value = false
  }

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' })
    isAuthenticated.value = false
    showKeyModal.value = true
  }

  function promptForKey() {
    showKeyModal.value = true
  }

  return { hasKey, isAuthenticated, authEnabled, showKeyModal, login, logout, promptForKey }
}
