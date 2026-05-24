<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const status = ref('loading')   // loading | connected | error | unreachable
const publicIp = ref('')
const serverCountry = ref('')
const selectedCountry = ref('')
const restarting = ref(false)
const switching = ref(false)
const expanded = ref(false)
const errorMessage = ref('')
let timer = null

const countries = [
  'United States', 'United Kingdom', 'Canada', 'Australia',
  'Germany', 'France', 'Netherlands', 'Japan', 'Singapore',
  'Switzerland', 'Sweden', 'Brazil', 'India', 'South Korea',
  'Italy', 'Spain', 'Norway', 'Denmark', 'Ireland',
]

async function fetchStatus() {
  try {
    const r = await fetch('/api/vpn/status')
    if (!r.ok) throw new Error(`Status check failed (${r.status})`)
    const data = await r.json()
    const vpnStatus = data.vpn?.status ?? 'unknown'
    publicIp.value = data.public_ip?.public_ip || ''
    serverCountry.value = (data.server_countries || [])[0] || ''
    status.value = vpnStatus === 'running' ? 'connected'
                 : vpnStatus === 'unreachable' ? 'unreachable'
                 : 'error'
  } catch (err) {
    console.error('[VPN] Failed to fetch status:', err)
    status.value = 'unreachable'
    errorMessage.value = 'Could not reach VPN service'
  }
}

async function pollUntilConnected() {
  const maxAttempts = 15
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 4000))
    await fetchStatus()
    if (status.value === 'connected') return
  }
}

async function restart() {
  restarting.value = true
  status.value = 'loading'
  errorMessage.value = ''
  try {
    const r = await fetch('/api/vpn/restart', { method: 'POST' })
    if (!r.ok) throw new Error(`Restart request failed (${r.status})`)
    await pollUntilConnected()
  } catch (err) {
    console.error('[VPN] Restart failed:', err)
    status.value = 'error'
    errorMessage.value = `Restart failed: ${err.message || 'unknown error'}`
  } finally {
    restarting.value = false
  }
}

async function changeCountry(newCountry) {
  if (switching.value) return
  switching.value = true
  status.value = 'loading'
  errorMessage.value = ''
  try {
    const r = await fetch('/api/vpn/country', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ country: newCountry }),
    })
    if (!r.ok) throw new Error(`Country switch request failed (${r.status})`)
    await pollUntilConnected()
  } catch (err) {
    console.error('[VPN] Country change failed:', err)
    status.value = 'error'
    errorMessage.value = `Country switch failed: ${err.message || 'unknown error'}`
    selectedCountry.value = ''
  } finally {
    switching.value = false
  }
}

onMounted(() => {
  fetchStatus()
  timer = setInterval(fetchStatus, 30000)
})
onUnmounted(() => clearInterval(timer))

const statusColor = {
  connected: 'var(--accent)',
  error: '#e74c3c',
  unreachable: '#888',
  loading: '#f39c12',
}
</script>

<template>
  <div class="vpn-widget">
    <div class="vpn-status" @click="expanded = !expanded">
      <span class="dot" :style="{ background: statusColor[status] || '#888' }"></span>
      <span class="label">VPN</span>
      <span v-if="status === 'connected'" class="info">
        {{ serverCountry }}{{ publicIp ? ` · ${publicIp}` : '' }}
      </span>
      <span v-else-if="status === 'loading'" class="info">…</span>
      <span v-else class="info err">offline</span>
      <button
        class="restart-btn"
        :disabled="restarting"
        @click.stop="restart"
        title="Restart VPN"
      >
        <span :class="{ spinning: restarting }">{{ restarting ? '⟳' : '↻' }}</span>
      </button>
    </div>
    <div v-if="errorMessage" class="vpn-error" @click="errorMessage = ''">
      ⚠ {{ errorMessage }}
    </div>
    <div v-if="expanded && status === 'connected'" class="vpn-details">
      <div class="detail-row" v-if="publicIp">
        <span class="detail-label">IP</span>
        <span class="detail-value">{{ publicIp }}</span>
      </div>
      <div class="detail-row" v-if="serverCountry">
        <span class="detail-label">Country</span>
        <span class="detail-value">{{ serverCountry }}</span>
      </div>
      <div class="detail-row country-row">
        <span class="detail-label">Switch</span>
        <select
          v-model="selectedCountry"
          class="country-select"
          :disabled="switching"
          @change="changeCountry(selectedCountry); expanded = false"
        >
          <option value="" disabled>Country…</option>
          <option
            v-for="c in countries"
            :key="c"
            :value="c"
          >{{ c }}{{ c === serverCountry ? ' ✓' : '' }}</option>
        </select>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vpn-widget {
  position: relative;
}

.vpn-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary, #aaa);
  cursor: pointer;
  user-select: none;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.info {
  font-size: 0.75rem;
  opacity: 0.7;
}

.info.err {
  color: #e74c3c;
  opacity: 1;
}

.restart-btn {
  background: none;
  border: 1px solid var(--border, #444);
  color: var(--text-secondary, #aaa);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.restart-btn:hover:not(:disabled) {
  color: var(--text, #fff);
  border-color: var(--accent, #4fc3f7);
}

.restart-btn:disabled {
  opacity: 0.5;
  cursor: wait;
}

.spinning {
  display: inline-block;
  animation: spin 1s linear infinite;
}

.vpn-details {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  background: var(--bg-card, #1e1e2e);
  border: 1px solid var(--border, #444);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 0.75rem;
  min-width: 200px;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 3px 0;
}

.detail-label {
  color: var(--text-secondary, #888);
}

.detail-value {
  color: var(--text, #eee);
  font-family: monospace;
}

.country-row {
  margin-top: 4px;
  padding-top: 6px;
  border-top: 1px solid var(--border, #333);
}

.country-select {
  background: var(--bg-card, #1e1e2e);
  color: var(--text, #eee);
  border: 1px solid var(--border, #444);
  border-radius: 4px;
  padding: 3px 6px;
  font-size: 0.75rem;
  cursor: pointer;
  max-width: 140px;
}

.country-select:disabled {
  opacity: 0.5;
  cursor: wait;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.vpn-error {
  margin-top: 4px;
  padding: 6px 10px;
  font-size: 0.75rem;
  color: #e74c3c;
  background: rgba(231, 76, 60, 0.1);
  border: 1px solid rgba(231, 76, 60, 0.25);
  border-radius: 6px;
  cursor: pointer;
  user-select: none;
}
</style>
