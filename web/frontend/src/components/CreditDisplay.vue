<script setup>
import { useSessionCredits } from '../composables/useSessionCredits'

const { sessionCreditsUsed, creditsRemaining } = useSessionCredits()
</script>

<template>
  <router-link to="/usage" class="credit-display" title="Credits remaining / used this session">
    <span class="credit-remaining" v-if="creditsRemaining !== null">
      {{ Math.round(creditsRemaining).toLocaleString() }}
    </span>
    <span class="credit-remaining credit-unknown" v-else>—</span>
    <template v-if="sessionCreditsUsed > 0">
      <span class="credit-separator">|</span>
      <span class="credit-session">-{{ Math.round(sessionCreditsUsed) }}</span>
    </template>
  </router-link>
</template>

<style scoped>
.credit-display {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  font-family: 'SF Mono', 'Fira Code', monospace;
  background: var(--bg-card, #1a1a2e);
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
  padding: 0.3rem 0.6rem;
  white-space: nowrap;
  text-decoration: none;
  transition: border-color 0.15s;
}

.credit-display:hover {
  border-color: var(--accent-color, #6366f1);
}

.credit-remaining {
  color: var(--accent-color, #6366f1);
  font-weight: 600;
}

.credit-unknown {
  opacity: 0.5;
}

.credit-separator {
  color: var(--text-secondary, #555);
  font-size: 0.7rem;
}

.credit-session {
  color: #f59e0b;
  font-size: 0.75rem;
}
</style>

