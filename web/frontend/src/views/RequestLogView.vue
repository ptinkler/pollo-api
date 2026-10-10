<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { apiGet } from '../composables/useApi'
import { useCopy } from '../composables/useClipboard'

// The provider request log (web/request_log.py): every call to Venice,
// OpenRouter and Pollo — chat replies, images, videos — with the exact
// body sent and what came back (images cut short).
const showToast = inject('showToast', () => {})
const { copiedKey, copy } = useCopy()

const entries = ref([])
const loading = ref(true)
const failedOnly = ref(false)
const open = ref(new Set())

const shown = computed(() => entries.value.filter(e => !failedOnly.value || e.error || e.status >= 400))
const key = (e, i) => `${e.at}-${i}`

async function load() {
  loading.value = true
  try {
    entries.value = (await apiGet('/api/chat/request-log?limit=200')).entries
  } catch (e) {
    showToast(`Couldn't load the request log: ${e.message}`, 'error')
  } finally {
    loading.value = false
  }
}

function toggle(k) {
  const next = new Set(open.value)
  next.has(k) ? next.delete(k) : next.add(k)
  open.value = next
}

const ok = e => !e.error && e.status < 400
const flagged = e => Object.values(e.flags || {}).some(v => String(v).toLowerCase() === 'true')
const fmtTime = s => new Date(s).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'medium' })
const json = e => JSON.stringify(e, null, 2)

onMounted(load)
</script>

<template>
  <div class="log-view">
    <header class="log-head">
      <div>
        <h1>Request log</h1>
        <p class="sub">
          What was sent to Venice, OpenRouter and Pollo — chat replies, images and videos — and what came back, newest
          first. Click one to see both. Images are shown as their type and size. The server keeps this in
          <code>logs/requests.jsonl</code> in its data folder.
        </p>
      </div>
      <label class="failed-only"><input v-model="failedOnly" type="checkbox" /> Failures only</label>
      <button class="btn btn-secondary small" @click="load">⟳ Refresh</button>
    </header>

    <p v-if="loading" class="sub">Loading…</p>
    <p v-else-if="!shown.length" class="sub">
      {{ entries.length ? 'No failures.' : 'No requests yet — send something in a chat.' }}
    </p>

    <div v-for="(e, i) in shown" :key="key(e, i)" class="entry" :class="{ bad: !ok(e) }">
      <button class="row" @click="toggle(key(e, i))">
        <span class="status" :class="ok(e) ? 'good' : 'fail'">{{ e.status ?? '—' }}</span>
        <span class="when">{{ fmtTime(e.at) }}</span>
        <span class="provider">{{ e.provider }}</span>
        <span class="path">{{ e.path }}</span>
        <span class="model">{{ e.model }}</span>
        <span v-if="flagged(e)" class="flag" :title="JSON.stringify(e.flags)">⚑ flagged</span>
        <span class="secs">{{ e.seconds != null ? `${e.seconds}s` : '' }}</span>
      </button>
      <p v-if="e.error" class="err">{{ e.error }}</p>
      <div v-if="open.has(key(e, i))" class="detail">
        <button class="btn btn-secondary small" @click="copy(json(e), key(e, i))">
          {{ copiedKey === key(e, i) ? '✓ Copied' : '⧉ Copy JSON' }}
        </button>
        <h4>Sent</h4>
        <pre>{{ json(e.request) }}</pre>
        <h4>Response</h4>
        <pre v-if="e.response != null">{{ typeof e.response === 'string' ? e.response : json(e.response) }}</pre>
        <p v-else class="sub">Nothing recorded (the connection failed, or the provider sent no body).</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-view {
  max-width: 1000px;
  margin: 0 auto;
}

.log-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.log-head > div {
  flex: 1;
}

.log-head h1 {
  font-size: 1.5rem;
}

.sub {
  font-size: 0.85rem;
  color: var(--text2);
  margin-top: 4px;
}

.failed-only {
  font-size: 0.82rem;
  color: var(--text2);
  white-space: nowrap;
  margin-top: 6px;
}

.btn.small {
  padding: 6px 12px;
  font-size: 0.8rem;
}

.entry {
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 8px;
  background: var(--surface);
}

.entry.bad {
  border-color: rgba(225, 112, 85, 0.35);
}

.row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: none;
  background: none;
  color: var(--text);
  font-size: 0.82rem;
  text-align: left;
  cursor: pointer;
}

.status {
  min-width: 36px;
  text-align: center;
  border-radius: 6px;
  padding: 1px 6px;
  font-variant-numeric: tabular-nums;
}

.status.good {
  background: rgba(0, 184, 148, 0.16);
  color: #4fd1a5;
}

.status.fail {
  background: rgba(225, 112, 85, 0.18);
  color: #ff8a6e;
}

.when,
.secs {
  color: var(--text2);
  white-space: nowrap;
}

.provider {
  color: var(--text2);
  text-transform: capitalize;
}

.path {
  font-family: monospace;
}

.model {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text2);
}

.flag {
  color: #ff8a6e;
  white-space: nowrap;
}

.err {
  padding: 0 12px 8px;
  font-size: 0.8rem;
  color: var(--red);
  word-break: break-word;
}

.detail {
  padding: 0 12px 12px;
}

.detail h4 {
  margin-top: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.detail pre {
  margin-top: 8px;
  padding: 12px;
  border-radius: 8px;
  background: var(--bg);
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 60vh;
  overflow: auto;
}

@media (max-width: 640px) {
  .log-head {
    flex-wrap: wrap;
  }

  .when {
    display: none;
  }
}
</style>
