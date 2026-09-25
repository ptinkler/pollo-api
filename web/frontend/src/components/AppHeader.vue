<script setup>
import { RouterLink, useRoute } from 'vue-router'
import VpnStatus from './VpnStatus.vue'
import CreditDisplay from './CreditDisplay.vue'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const { hasKey, showKeyModal } = useAuth()
</script>

<template>
  <header class="app-header">
    <RouterLink to="/" class="logo">
      <h1>🎬 <span>Pollo</span> Video Generator</h1>
    </RouterLink>
    <div class="header-right">
      <RouterLink to="/chat" class="nav-link" :class="{ active: route.path.startsWith('/chat') }">💬<span class="nav-text"> Chat</span></RouterLink>
      <CreditDisplay />
      <VpnStatus />
      <button
        class="key-btn"
        :class="{ 'key-set': hasKey, 'key-missing': !hasKey }"
        @click="showKeyModal = true"
        :title="hasKey ? 'API key set — click to change' : 'No API key — click to set'"
      >🔑</button>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.nav-link {
  text-decoration: none;
  color: var(--text2);
  font-size: 0.87rem;
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: all 0.2s;
}

.nav-link:hover,
.nav-link.active {
  color: var(--text);
  border-color: var(--accent);
}

@media (max-width: 600px) {
  .nav-text {
    display: none;
  }
}

.logo {
  text-decoration: none;
  color: inherit;
}

.logo h1 {
  font-size: 1.4rem;
  font-weight: 600;
  cursor: pointer;
}

.logo h1 span {
  color: var(--accent2);
}

.key-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.key-btn.key-set {
  border-color: var(--green);
  box-shadow: 0 0 6px rgba(0, 184, 148, 0.3);
}

.key-btn.key-missing {
  border-color: var(--red);
  box-shadow: 0 0 6px rgba(225, 112, 85, 0.35);
  animation: pulse 1.5s ease-in-out infinite;
}
</style>
