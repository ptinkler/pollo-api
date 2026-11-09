<!-- Settings card: live VPN status (Gluetun) with a restart control. -->
<script setup>
import { ref, onMounted } from 'vue'
import { apiGet, apiPost } from '../../composables/useApi'

const status = ref(null)
const loading = ref(false)
const restarting = ref(false)
const message = ref('')

async function load() {
  loading.value = true
  try {
    status.value = await apiGet('/api/vpn/status')
  } catch {
    status.value = null
  } finally {
    loading.value = false
  }
}
async function restart() {
  restarting.value = true
  message.value = ''
  try {
    const r = await apiPost('/api/vpn/restart', {})
    message.value = r.message || (r.ok ? 'Restarted' : 'Restart failed')
    setTimeout(load, 10000)
  } catch (e) {
    message.value = e.message
  } finally {
    restarting.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="scard">
    <div class="ctitle">Network / VPN</div>
    <div v-if="loading && !status" class="cnote">Checking…</div>
    <template v-else-if="status">
      <div class="row">
        <span class="k">Tunnel</span>
        <span class="v" :class="status.vpn?.status === 'running' ? 'ok' : 'bad'">{{
          status.vpn?.status || 'unknown'
        }}</span>
      </div>
      <div class="row">
        <span class="k">Public IP</span>
        <span class="v">{{ status.public_ip?.ip || '—' }}</span>
      </div>
      <div class="row">
        <span class="k">Country</span>
        <span class="v">{{ (status.server_countries || []).join(', ') || status.public_ip?.country || '—' }}</span>
      </div>
      <div class="cactions">
        <button class="btn" :disabled="restarting" @click="restart">
          {{ restarting ? 'Restarting…' : 'Restart tunnel' }}
        </button>
        <span v-if="message" class="cmsg">{{ message }}</span>
      </div>
    </template>
    <div v-else class="cnote">VPN control server unreachable.</div>
  </section>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 13px;
}
.k {
  color: var(--smuted);
}
.v {
  color: var(--sfg);
  font-variant-numeric: tabular-nums;
}
.v.ok {
  color: var(--ssuccess);
}
.v.bad {
  color: var(--swarn);
}
</style>
