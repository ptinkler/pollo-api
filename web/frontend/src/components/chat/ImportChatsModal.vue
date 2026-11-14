<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  cancelChatGptUpload,
  chatExportUrl,
  fetchChatGptImport,
  fetchExportableChats,
  sendChatGptUploadChunk,
  startChatGptImport,
  startChatGptUpload,
} from '../../composables/useChat'
import BaseDialog from '../BaseDialog.vue'

// Import chats from a ChatGPT export, or from this app's own chat export
// (made below, here or on another server): upload the zip (in chunks, then
// it's imported straight away) or pick one already in the server's imports
// folder, and follow the import (it runs on the server; closing this doesn't
// stop it). Emits `imported` when one finishes, so the list can reload.
// The Export tab picks chats and downloads them as one zip.
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

// Export: pick chats, download them as one zip
const tab = ref('import')
const chats = ref(null) // null until loaded
const picked = ref(new Set())
const exportQuery = ref('')
const shownChats = computed(() => {
  const q = exportQuery.value.trim().toLowerCase()
  return (chats.value || []).filter(c => !q || (c.title || '').toLowerCase().includes(q))
})
const allShownPicked = computed(
  () => shownChats.value.length > 0 && shownChats.value.every(c => picked.value.has(c.id)),
)
const exportHref = computed(() => chatExportUrl([...picked.value]))
async function openExport() {
  tab.value = 'export'
  if (chats.value) return
  try {
    chats.value = (await fetchExportableChats()).chats
  } catch (e) {
    error.value = e.message
    chats.value = []
  }
}
function togglePick(id) {
  const next = new Set(picked.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  picked.value = next
}
function toggleAllShown() {
  const next = new Set(picked.value)
  const on = !allShownPicked.value
  for (const c of shownChats.value) on ? next.add(c.id) : next.delete(c.id)
  picked.value = next
}

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
    chats.value = null // fresh list each time it opens
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
  <BaseDialog :open="visible" title="Import / export chats" @close="emit('close')">
    <div class="seg tabs">
      <button :class="{ on: tab === 'import' }" @click="tab = 'import'">Import</button>
      <button :class="{ on: tab === 'export' }" @click="openExport">Export</button>
    </div>

    <template v-if="tab === 'export'">
      <p class="hint">
        Downloads the chats as one zip — every branch, picture and video. Import it here or on another server with
        <strong>Import</strong>. Attached characters and instructions don't travel; spaces go by name.
      </p>
      <input v-model="exportQuery" class="filter" type="search" placeholder="Filter chats…" />
      <div v-if="!chats" class="note">Loading chats…</div>
      <div v-else-if="!chats.length" class="note">No chats yet.</div>
      <ul v-else class="file-list">
        <li class="file-item pick all">
          <label
            ><input type="checkbox" :checked="allShownPicked" @change="toggleAllShown" />
            {{ exportQuery ? 'All matching' : 'All chats' }} ({{ shownChats.length }})</label
          >
        </li>
        <li v-for="c in shownChats" :key="c.id" class="file-item pick">
          <label :title="c.title">
            <input type="checkbox" :checked="picked.has(c.id)" @change="togglePick(c.id)" />
            <span class="file-name">{{ c.title || 'Untitled' }}</span>
            <span class="file-meta"
              ><template v-if="c.space">{{ c.space }} · </template>{{ fmtDate(c.updated_at) }}</span
            >
          </label>
        </li>
      </ul>
      <p v-if="error" class="result error">{{ error }}</p>
    </template>

    <template v-else>
      <p class="hint">
        Upload a chat export from this app (Export, here or on another server), or a ChatGPT one (Settings → Data
        controls → Export data, then the zip it emails you) — or copy it into
        <code>{{ folder || 'the imports folder' }}</code> on the server. ChatGPT chats go in a
        <strong>ChatGPT</strong> space. Importing a newer export later only adds what's new; chats you delete here
        aren't imported again.
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
    </template>

    <template v-if="tab === 'export'" #actions>
      <span class="spacer"></span>
      <button class="btn btn-secondary" @click="emit('close')">Close</button>
      <a
        v-if="picked.size"
        class="btn btn-primary"
        :href="exportHref"
        download
        :title="`Download ${picked.size} chat${picked.size === 1 ? '' : 's'} as a zip`"
        >Download {{ picked.size }} chat{{ picked.size === 1 ? '' : 's' }}</a
      >
      <button v-else class="btn btn-primary" disabled>Pick chats to export</button>
    </template>
    <template v-else #actions>
      <button v-if="upload" class="btn btn-secondary" @click="cancelUpload">Cancel upload</button>
      <button v-else class="btn btn-secondary" :disabled="busy" @click="picker.click()">Upload export…</button>
      <span class="spacer"></span>
      <button class="btn btn-secondary" @click="emit('close')">Close</button>
      <button class="btn btn-primary" :disabled="!selected || busy" @click="start">
        {{ running ? 'Importing…' : 'Import' }}
      </button>
    </template>
  </BaseDialog>
</template>

<style scoped>
.tabs {
  align-self: flex-start;
  margin-bottom: 4px;
}

.filter {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: inherit;
  font: inherit;
  font-size: 0.82rem;
}

.file-item.pick {
  padding: 0;
}

.file-item.pick label {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  align-items: center;
}

.file-item.pick .file-meta {
  grid-column: 2;
}

.file-item.all label {
  font-size: 0.82rem;
  color: var(--text2);
}

a.btn {
  text-decoration: none;
}

.hint,
.note {
  color: var(--text2);
  font-size: 0.82rem;
  line-height: 1.45;
}

.hint code {
  word-break: break-all;
}

.file-list {
  list-style: none;
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
  background: var(--saccent-soft);
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
  line-height: 1.45;
}

.result.error {
  color: var(--sdanger);
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
</style>
