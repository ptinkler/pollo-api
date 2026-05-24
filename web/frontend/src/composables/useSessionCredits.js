import { ref, computed } from 'vue'
import { fetchBalance } from './useApi'

/**
 * Session credit tracker.
 * "Session" = page lifetime (in-memory only, resets on close/refresh).
 */

// Global state — shared across all components, lives in memory only
const sessionCreditsUsed = ref(0)
const balance = ref(null)
const balanceLoading = ref(false)
const lastFetchedAt = ref(0)

// Minimum interval between balance fetches (30 seconds)
const BALANCE_FETCH_INTERVAL = 30_000

function addCredits(amount) {
  if (amount && amount > 0) {
    sessionCreditsUsed.value += amount
    // Immediately subtract from local balance for instant UI feedback
    if (balance.value) {
      balance.value = {
        ...balance.value,
        availableCredits: balance.value.availableCredits - amount,
      }
    }
  }
}

async function refreshBalance(force = false) {
  const now = Date.now()
  if (!force && balanceLoading.value) return
  if (!force && now - lastFetchedAt.value < BALANCE_FETCH_INTERVAL) return

  balanceLoading.value = true
  try {
    balance.value = await fetchBalance()
    lastFetchedAt.value = Date.now()
  } catch {
    // Silently fail — balance display will show "—"
  } finally {
    balanceLoading.value = false
  }
}

const creditsRemaining = computed(() => {
  if (!balance.value) return null
  return balance.value.availableCredits
})

export function useSessionCredits() {
  return {
    sessionCreditsUsed,
    balance,
    balanceLoading,
    creditsRemaining,
    addCredits,
    refreshBalance,
  }
}

