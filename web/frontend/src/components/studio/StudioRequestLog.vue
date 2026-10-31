<!-- Provider request log (Venice / OpenRouter / Pollo) in the Studio center
     pane. Replaces the old /requests page. -->
<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { apiGet } from '../../composables/useApi'
import { useCopy } from '../../composables/useClipboard'

const emit = defineEmits(['close'])
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
  <div class="page">
    <div class="pwrap">
      <div class="phead">
        <div>
          <h1>Request log</h1>
          <p class="sub">
            What was sent to Venice, OpenRouter and Pollo and what came back, newest first. Click one to see both.
          </p>
        </div>
        <div class="hactions">
          <label class="failed"><input v-model="failedOnly" type="checkbox" /> Failures only</label>
          <button class="ghost" @click="load">⟳ Refresh</button>
          <button class="closebtn" @click="emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

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
          <button class="ghost small" @click="copy(json(e), key(e, i))">
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
  </div>
</template>

<style scoped>
.page {
  flex: 1;
  overflow-y: auto;
  padding: 32px 22px;
}
.pwrap {
  max-width: 1000px;
  margin: 0 auto;
}
.phead {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}
h1 {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.02em;
}
.sub {
  font-size: 13px;
  color: var(--smuted);
  margin-top: 6px;
  line-height: 1.5;
  max-width: 560px;
}
.hactions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.failed {
  font-size: 12px;
  color: var(--smuted);
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.ghost,
.closebtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 11px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  color: var(--smuted);
  background: none;
  cursor: pointer;
  font-size: 13px;
}
.ghost.small {
  padding: 4px 8px;
  font-size: 12px;
}
.ghost:hover,
.closebtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.entry {
  border: 1px solid var(--sborder);
  border-radius: 10px;
  margin-bottom: 8px;
  overflow: hidden;
}
.entry.bad {
  border-color: #e5484d66;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 12px;
  background: none;
  border: none;
  color: var(--sfg);
  cursor: pointer;
  text-align: left;
  font-size: 12.5px;
}
.row:hover {
  background: var(--shover);
}
.status {
  font-weight: 700;
  min-width: 34px;
}
.status.good {
  color: #2ec16b;
}
.status.fail {
  color: #e5484d;
}
.when {
  color: var(--sfaint);
}
.provider {
  font-weight: 600;
}
.path,
.model {
  color: var(--smuted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.path {
  flex: 1;
  min-width: 0;
}
.flag {
  color: #e2a03f;
}
.secs {
  color: var(--sfaint);
  margin-left: auto;
}
.err {
  padding: 6px 12px;
  color: #e5484d;
  font-size: 12px;
}
.detail {
  padding: 10px 12px;
  border-top: 1px solid var(--sborder2);
}
.detail h4 {
  font-size: 12px;
  color: var(--sfaint);
  margin: 10px 0 4px;
}
.detail pre {
  background: var(--sbg2);
  border-radius: 8px;
  padding: 10px;
  overflow-x: auto;
  font-size: 11.5px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
