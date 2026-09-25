<script setup>
import { ref, watch } from 'vue'
import { useAuth } from '../composables/useAuth'

// Rendered once in App.vue so it works on every page, including
// full-screen ones without the AppHeader (e.g. chat).
const { hasKey, showKeyModal, login, logout } = useAuth()
const keyInput = ref('')
const loginError = ref('')

watch(showKeyModal, (open) => {
  if (open) {
    keyInput.value = ''
    loginError.value = ''
  }
})

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
