import { reactive } from 'vue'
import { fetchOpenRouterCredits, fetchVeniceBalance } from './useChat'
import { useSessionCredits } from './useSessionCredits'

// What's left to spend with each provider the chat uses: OpenRouter and
// Venice in dollars, Pollo in credits. `providers`: which keys the server has.
export function useChatBalances(providers) {
  const { creditsRemaining, refreshBalance: refreshPollo } = useSessionCredits()
  const balances = reactive({ openrouter: null, venice: null, pollo: creditsRemaining })

  async function refresh() {
    refreshPollo(true)
    if (providers.openrouter) {
      try {
        balances.openrouter = (await fetchOpenRouterCredits()).remaining
      } catch {
        /* shown as — */
      }
    }
    if (providers.venice) {
      try {
        balances.venice = (await fetchVeniceBalance()).usd
      } catch {
        /* shown as — */
      }
    }
  }

  return { balances, refresh }
}
