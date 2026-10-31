<script setup>
import { ref, watch, onMounted } from 'vue'
import { useAuth } from '../composables/useAuth'
import { fetchAuthProviders, authLoginUrl } from '../composables/useAccount'

const { showLogin, login, devLogin } = useAuth()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
const providers = ref([])
const devAvailable = ref(false)

onMounted(async () => {
  try {
    const info = await fetchAuthProviders()
    providers.value = info.providers || []
    devAvailable.value = !!info.dev_login
  } catch {
    providers.value = []
  }
})

async function devSignIn() {
  busy.value = true
  error.value = ''
  try {
    await devLogin()
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

watch(showLogin, open => {
  if (open) {
    password.value = ''
    error.value = ''
  }
})

async function submit() {
  if (!email.value.trim() || !password.value) return
  busy.value = true
  error.value = ''
  try {
    await login(email.value.trim(), password.value)
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

const providerLabels = { google: 'Google', microsoft: 'Microsoft', x: 'X' }
</script>

<template>
  <Teleport to="body">
    <div v-if="showLogin" class="modal-backdrop">
      <div class="modal-box">
        <h3>Sign in</h3>
        <input v-model="email" type="email" placeholder="Email" autocomplete="username" @keydown.enter="submit" />
        <input
          v-model="password"
          type="password"
          placeholder="Password"
          autocomplete="current-password"
          @keydown.enter="submit"
        />
        <p v-if="error" class="error-hint">{{ error }}</p>
        <button class="btn btn-primary" :disabled="busy || !email.trim() || !password" @click="submit">Sign in</button>
        <template v-if="providers.length">
          <div class="divider">or</div>
          <a v-for="p in providers" :key="p" class="btn btn-secondary oauth" :href="authLoginUrl(p)">
            Continue with {{ providerLabels[p] || p }}
          </a>
        </template>
        <template v-if="devAvailable">
          <div class="divider">dev</div>
          <button class="btn btn-secondary oauth" :disabled="busy" @click="devSignIn">🛠 Dev sign-in</button>
        </template>
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
  width: 360px;
  max-width: 90vw;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.modal-box h3 {
  font-size: 1.1rem;
  font-weight: 600;
}

.error-hint {
  font-size: 0.8rem;
  color: var(--red);
}

.modal-box input {
  width: 100%;
  font-size: 0.9rem;
}

.divider {
  text-align: center;
  font-size: 0.75rem;
  color: var(--text2);
}

.oauth {
  text-align: center;
  text-decoration: none;
}
</style>
