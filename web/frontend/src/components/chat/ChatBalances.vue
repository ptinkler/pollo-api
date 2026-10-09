<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { fmtCost } from '../../utils/format'

// The chips over the chat: what this chat cost, and what's left with each provider
const props = defineProps({
  providers: { type: Object, required: true }, // which API keys the server has
  balances: { type: Object, required: true }, // from useChatBalances
  spend: { type: Object, default: null }, // the chat's /spend
})

const fmtUsd = v => (v == null ? '—' : `$${v.toFixed(2)}`)
const fmtCredits = v => (v == null ? '—' : Math.round(v).toLocaleString())
const joinAmounts = (usd, credits, creditsLabel) =>
  [usd ? fmtCost(usd) : '', credits ? `${credits.toLocaleString()} ${creditsLabel}` : ''].filter(Boolean).join(' + ')

const spendLabel = computed(() => (props.spend ? joinAmounts(props.spend.usd, props.spend.credits, 'cr') : ''))
const spendTitle = computed(() => {
  const inherited = props.spend ? joinAmounts(props.spend.inherited_usd, props.spend.inherited_credits, 'credits') : ''
  return (
    'Spent on this chat, every branch included (dollars: OpenRouter/Venice; credits: Pollo)' +
    (inherited ? `. ${inherited} of it was spent before it was branched off another chat.` : '')
  )
})
</script>

<template>
  <div class="balances">
    <span v-if="spendLabel" class="balance spend" :title="spendTitle"
      >This chat <b>{{ spendLabel }}</b></span
    >
    <span
      v-if="providers.openrouter"
      class="balance"
      title="OpenRouter balance — credits bought minus used (chat text, OpenRouter images/videos)"
    >
      OpenRouter <b>{{ fmtUsd(balances.openrouter) }}</b>
    </span>
    <span v-if="providers.venice" class="balance venice" title="Venice balance in USD (Venice text, images and videos)">
      Venice <b>{{ fmtUsd(balances.venice) }}</b>
    </span>
    <RouterLink to="/usage" class="balance pollo" title="Pollo credits remaining (Pollo images/videos) — open Usage">
      Pollo <b>{{ fmtCredits(balances.pollo) }}</b>
    </RouterLink>
  </div>
</template>

<style scoped>
.balance.spend b {
  color: #7ed6a5;
}

.balances {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 16px 0;
}

.balance {
  font-size: 0.75rem;
  color: var(--text2);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 10px;
  white-space: nowrap;
  text-decoration: none;
}

.balance b {
  color: var(--text);
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-weight: 600;
}

.balance.venice b {
  color: #e8a33d;
}

.balance.pollo b {
  color: var(--accent2);
}

.balance.pollo:hover {
  border-color: var(--accent2);
}
</style>
