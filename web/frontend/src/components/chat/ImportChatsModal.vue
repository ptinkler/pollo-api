<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  cancelChatGptUpload,
  fetchChatGptImport,
  sendChatGptUploadChunk,
  startChatGptImport,
  startChatGptUpload,
} from '../../composables/useChat'

// Import chats from a ChatGPT export: upload the zip (in chunks, then it's
// imported straight away) or pick one already in the server's imports
// folder, and follow the import (it runs on the server; closing this doesn't
// stop it). Emits `imported` when one finishes, so the list can reload.
const props = defineProps({
  visible: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'imported'])

const POLL_MS = 1500
const CHUNK_TRIES = 4 // per chunk, each after the API's own retries
const CHUNK_RETRY_MS = 5000

const folder = ref('')
const files = ref([])
const selected = ref(null)
const job = ref(null)
const loading = ref(false)
const error = ref('')
const upload = ref(null) // { id, name, size, sent } while uploading
const picker = ref(null)
let timer = null
let cancelled = false

const running = computed(() => job.value?.state === 'running')
const busy = computed(() => running.value || !!upload.value)
const finished = computed(() => ['done', 'error'].includes(job.value?.state) && job.value?.file)

function fmtSize(bytes) {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / 1e6))} MB`
}

function fmtDate(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

async function refresh() {
  try {
    const data = await fetchChatGptImport()
    folder.value = data.folder
    files.value = data.files
    const was = job.value?.state
    job.value = data.job
    if (!files.value.some(f => f.name === selected.value)) selected.value = files.value[0]?.name || null
    if (was === 'running' && data.job.state !== 'running') emit('imported')
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
  clearTimeout(timer)
  if (props.visible && running.value) timer = setTimeout(refresh, POLL_MS)
}

watch(
  () => props.visible,
  async v => {
    clearTimeout(timer)
    if (!v) return
    loading.value = true
    await refresh()
    loading.value = false
  },
)
onBeforeUnmount(() => clearTimeout(timer))

// Leaving the page stops an upload
function warnOnLeave(e) {
  e.preventDefault()
}
watch(upload, (now, before) => {
  if (now && !before) window.addEventListener('beforeunload', warnOnLeave)
  if (!now) window.removeEventListener('beforeunload', warnOnLeave)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', warnOnLeave))

async function sendChunk(id, offset, blob) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await sendChatGptUploadChunk(id, offset, blob)
    } catch (e) {
      if (attempt >= CHUNK_TRIES || cancelled) throw e
      await new Promise(resolve => setTimeout(resolve, CHUNK_RETRY_MS))
    }
  }
}

async function uploadFile(file) {
  error.value = ''
  cancelled = false
  let id = null
  try {
    const started = await startChatGptUpload(file.name, file.size)
    id = started.id
    upload.value = { id, name: file.name, size: file.size, sent: 0 }
    let done = null
    for (let offset = 0; offset < file.size && !cancelled; offset += started.chunk_size) {
      done = await sendChunk(id, offset, file.slice(offset, offset + started.chunk_size))
      upload.value.sent = done.received
    }
    if (cancelled) return
    upload.value = null
    await refresh()
    selected.value = done.file
    await start()
  } catch (e) {
    if (cancelled) return // a chunk still on its way when it was cancelled
    error.value = `Upload failed: ${e.message}`
    if (id) cancelChatGptUpload(id).catch(() => {})
  } finally {
    upload.value = null
  }
}

function onPick(e) {
  const [file] = e.target.files
  e.target.value = ''
  if (file) uploadFile(file)
}

function cancelUpload() {
  cancelled = true
  const id = upload.value?.id
  upload.value = null
  if (id) cancelChatGptUpload(id).catch(() => {})
}

async function start() {
  if (!selected.value) return
  try {
    job.value = await startChatGptImport(selected.value)
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
  refresh()
}
</script>

<template>
  <div v-if="visible" class="import-overlay" @click.self="emit('close')">
    <div class="import-modal">
      <button class="modal-close" @click="emit('close')">&times;</button>
      <h3>Import from ChatGPT</h3>
      <p class="hint">
        In ChatGPT: Settings → Data controls → Export data, then upload the zip it emails you (or copy it into
        <code>{{ folder || 'the imports folder' }}</code> on the server). Its chats go in a <strong>ChatGPT</strong>
        space. Importing a newer export later only adds what's new; chats you delete here aren't imported again.
      </p>
      <input ref="picker" type="file" accept=".zip,application/zip" hidden @change="onPick" />

      <div v-if="loading" class="note">Looking for exports…</div>
      <div v-else-if="!files.length" class="note">No exports yet: upload one below.</div>
      <ul v-else class="file-list">
        <li
          v-for="f in files"
          :key="f.name"
          :class="['file-item', { active: selected === f.name }]"
          :title="f.name"
          @click="!busy && (selected = f.name)"
        >
          <span class="file-name">{{ f.name }}</span>
          <span class="file-meta">{{ fmtSize(f.size) }} · {{ fmtDate(f.modified) }}</span>
        </li>
      </ul>

      <div v-if="upload" class="progress">
        <div class="bar"><span :style="{ width: `${(100 * upload.sent) / upload.size}%` }"></span></div>
        Uploading {{ upload.name }}… {{ fmtSize(upload.sent) }} / {{ fmtSize(upload.size) }}. Keep this tab open; it's
        imported once it's up.
      </div>
      <div v-else-if="running" class="progress">
        <div class="bar"><span :style="{ width: `${job.total ? (100 * job.processed) / job.total : 0}%` }"></span></div>
        Importing {{ job.file }}… {{ job.processed || 0 }} / {{ job.total || '?' }} chats
      </div>
      <div v-else-if="finished && job.state === 'error'" class="result error">
        Import of {{ job.file }} failed: {{ job.error }}
      </div>
      <div v-else-if="finished" class="result">
        <strong>{{ job.file }}</strong
        >: {{ job.new }} new, {{ job.updated }} updated, {{ job.unchanged }} unchanged
        <template v-if="job.deleted">, {{ job.deleted }} deleted here (skipped)</template>. {{ job.images }} images
        copied<template v-if="job.missing_images">, {{ job.missing_images }} not in the export</template>.
        <ul v-if="job.failed?.length" class="failed">
          <li v-for="(f, i) in job.failed" :key="i">{{ f.title || 'Untitled' }}: {{ f.error }}</li>
        </ul>
      </div>
      <p v-if="error" class="result error">{{ error }}</p>

      <div class="actions">
        <button v-if="upload" class="btn btn-secondary" @click="cancelUpload">Cancel upload</button>
        <button v-else class="btn btn-secondary" :disabled="busy" @click="picker.click()">Upload export…</button>
        <span class="spacer"></span>
        <button class="btn btn-secondary" @click="emit('close')">Close</button>
        <button class="btn btn-primary" :disabled="!selected || busy" @click="start">
          {{ running ? 'Importing…' : 'Import' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.import-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.import-modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  width: 480px;
  max-width: 100%;
  max-height: 100%;
  overflow-y: auto;
  position: relative;
}

.import-modal h3 {
  margin: 0 0 10px;
  font-size: 1rem;
  font-weight: 600;
}

.modal-close {
  position: absolute;
  top: 12px;
  right: 14px;
  background: none;
  border: none;
  font-size: 1.4rem;
  color: var(--text2);
  cursor: pointer;
  line-height: 1;
  padding: 2px 6px;
}

.modal-close:hover {
  color: var(--text);
}

.hint,
.note {
  color: var(--text2);
  font-size: 0.82rem;
  line-height: 1.45;
  margin: 0 0 14px;
}

.hint code {
  word-break: break-all;
}

.file-list {
  list-style: none;
  margin: 0 0 14px;
  padding: 0;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.file-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--border);
}

.file-item:last-child {
  border-bottom: none;
}

.file-item:hover {
  background: var(--surface2);
}

.file-item.active {
  background: rgba(108, 92, 231, 0.2);
}

.file-name {
  font-size: 0.82rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  font-size: 0.72rem;
  color: var(--text2);
}

.progress,
.result {
  font-size: 0.82rem;
  margin: 0 0 14px;
  line-height: 1.45;
}

.result.error {
  color: var(--danger, #e74c3c);
}

.bar {
  height: 6px;
  border-radius: 3px;
  background: var(--surface2);
  overflow: hidden;
  margin-bottom: 6px;
}

.bar span {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.3s;
}

.failed {
  margin: 6px 0 0;
  padding-left: 18px;
  color: var(--text2);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.spacer {
  flex: 1;
}
</style>
