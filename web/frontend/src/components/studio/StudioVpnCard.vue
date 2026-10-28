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
  <section class="card">
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
      <div class="actions">
        <button class="btn" :disabled="restarting" @click="restart">
          {{ restarting ? 'Restarting…' : 'Restart tunnel' }}
        </button>
        <span v-if="message" class="msg">{{ message }}</span>
      </div>
    </template>
    <div v-else class="cnote">VPN control server unreachable.</div>
  </section>
</template>

<style scoped>
.card {
  border: 1px solid var(--sborder);
  background: var(--sbg);
  border-radius: 14px;
  padding: 18px 20px;
  margin-bottom: 16px;
}
.ctitle {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--sfaint);
  font-weight: 650;
  margin-bottom: 14px;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 0;
}
.k {
  color: var(--smuted);
  font-size: 13px;
}
.v {
  color: var(--sfg);
  font-size: 13px;
}
.v.ok {
  color: #5fd08a;
}
.v.bad {
  color: #e2a04a;
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}
.btn {
  padding: 7px 14px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  color: var(--sfg);
  background: none;
  cursor: pointer;
}
.btn:hover:not(:disabled) {
  background: var(--shover);
}
.btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.msg {
  font-size: 12px;
  color: var(--smuted);
}
.cnote {
  color: var(--smuted);
  font-size: 13px;
  line-height: 1.6;
}
</style>
