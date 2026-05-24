<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import VpnStatus from './VpnStatus.vue'
import CreditDisplay from './CreditDisplay.vue'
import { useAuth } from '../composables/useAuth'

const { hasKey, showKeyModal, login, logout } = useAuth()
const keyInput = ref('')
const loginError = ref('')

function openModal() {
  keyInput.value = ''
  loginError.value = ''
  showKeyModal.value = true
}

async function save() {
  if (!keyInput.value.trim()) return
  loginError.value = ''
  try {
    await login(keyInput.value)
  } catch (err) {
    loginError.value = err.message
  }
}

async function clear() {
  await logout()
}

function onKeydown(e) {
  if (e.key === 'Enter') save()
  if (e.key === 'Escape') showKeyModal.value = false
}
</script>

<template>
  <header class="app-header">
    <RouterLink to="/" class="logo">
      <h1>🎬 <span>Pollo</span> Video Generator</h1>
    </RouterLink>
    <div class="header-right">
      <CreditDisplay />
      <VpnStatus />
      <button
        class="key-btn"
        :class="{ 'key-set': hasKey, 'key-missing': !hasKey }"
        @click="openModal"
        :title="hasKey ? 'API key set — click to change' : 'No API key — click to set'"
      >🔑</button>
    </div>
  </header>

  <!-- API key modal -->
  <Teleport to="body">
    <div v-if="showKeyModal" class="modal-backdrop" @click.self="showKeyModal = false">
      <div class="modal-box">
        <h3>API Key</h3>
        <p class="hint">Stored in HttpOnly cookie. Never readable by JavaScript.</p>
        <input
          v-model="keyInput"
          type="password"
          placeholder="Paste your API key…"
          class="key-input"
          autofocus
          @keydown="onKeydown"
        />
        <p v-if="loginError" class="error-hint">{{ loginError }}</p>
        <div class="modal-actions">
          <button class="btn btn-primary" @click="save" :disabled="!keyInput.trim()">Save</button>
          <button class="btn btn-secondary" @click="showKeyModal = false">Cancel</button>
          <button v-if="hasKey" class="btn btn-danger" @click="clear">Log out</button>
        </div>
      </div>
    </div>
  </Teleport>
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

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-box {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  width: 420px;
  max-width: 90vw;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.modal-box h3 {
  font-size: 1.1rem;
  font-weight: 600;
}

.hint {
  font-size: 0.8rem;
  color: var(--text2);
}

.hint code {
  font-size: 0.75rem;
  background: var(--surface2);
  padding: 1px 5px;
  border-radius: 4px;
}

.error-hint {
  font-size: 0.8rem;
  color: var(--red);
}

.key-input {
  width: 100%;
  font-family: monospace;
  font-size: 0.9rem;
}

.modal-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
