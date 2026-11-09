<!-- Studio center pane: the media library (all generated images/videos),
     reusing MediaGrid + useMedia with server-side paging. -->
<script setup>
import { ref, inject, onMounted } from 'vue'
import { confirmDialog } from '../../composables/useDialog'
import MediaGrid from '../media/MediaGrid.vue'
import { fetchMediaPage, deleteMediaMany, downloadMediaMany } from '../../composables/useMedia'

defineEmits(['close'])
const showToast = inject('showToast')

const PAGE = 30
const KINDS = [
  { id: 'all', label: 'All' },
  { id: 'image', label: 'Images' },
  { id: 'video', label: 'Videos' },
]
const SOURCES = [
  { id: 'all', label: 'Any source' },
  { id: 'generated', label: 'Generated' },
  { id: 'upload', label: 'Uploaded' },
]

const ORIGINS = [
  { id: 'all', label: 'Everywhere' },
  { id: 'chat', label: 'Chats' },
  { id: 'library', label: 'Library' },
  { id: 'orphan', label: 'Orphaned' },
]

const items = ref([])
const total = ref(0)
const kind = ref('all')
const source = ref('all')
const origin = ref('all')
const q = ref('')
const loading = ref(false)
const preview = ref(null)
const picked = ref(new Set()) // ids chosen for a bulk action
const busy = ref(false)
function toggle(item) {
  const next = new Set(picked.value)
  if (!next.delete(item.id)) next.add(item.id)
  picked.value = next
}
const selectAll = () => (picked.value = new Set(items.value.map(i => i.id)))
const clearPicked = () => (picked.value = new Set())
async function bulkDownload() {
  busy.value = true
  try {
    await downloadMediaMany([...picked.value])
  } catch (e) {
    showToast(e.message, 'error')
  } finally {
    busy.value = false
  }
}
async function bulkDelete() {
  const n = picked.value.size
  const ok = await confirmDialog({
    title: `Delete ${n} item${n === 1 ? '' : 's'}?`,
    message: "This removes the files and can't be undone.",
    confirmLabel: 'Delete',
    danger: true,
  })
  if (!ok) return
  busy.value = true
  try {
    await deleteMediaMany([...picked.value])
    clearPicked()
    await load()
  } catch (e) {
    showToast(e.message, 'error')
  } finally {
    busy.value = false
  }
}

function params(offset) {
  return {
    offset,
    limit: PAGE,
    q: q.value || undefined,
    kind: kind.value === 'all' ? undefined : kind.value,
    source: source.value === 'all' ? undefined : source.value,
    origin: origin.value === 'all' ? undefined : origin.value,
  }
}
async function load() {
  loading.value = true
  try {
    const { items: page, total: t } = await fetchMediaPage(params(0))
    items.value = page
    total.value = t
  } finally {
    loading.value = false
  }
}
async function loadMore() {
  if (items.value.length >= total.value) return
  const { items: page } = await fetchMediaPage(params(items.value.length))
  items.value = [...items.value, ...page]
}
function setKind(k) {
  kind.value = k
  load()
}
function setSource(s) {
  source.value = s
  load()
}

function setOrigin(o) {
  origin.value = o
  load()
}

onMounted(load)
</script>

<template>
  <div class="media">
    <div class="mhead">
      <h1>Media library</h1>
      <span v-if="total" class="gcount">{{ total }} item{{ total === 1 ? '' : 's' }}</span>
      <span class="spacer"></span>
      <button class="btn" @click="$emit('close')">
        <svg class="ic"><use href="#s-chevL" /></svg> Back
      </button>
    </div>
    <div class="mbar">
      <div class="seg">
        <button v-for="k in KINDS" :key="k.id" :class="{ on: kind === k.id }" @click="setKind(k.id)">
          {{ k.label }}
        </button>
      </div>
      <div class="seg">
        <button v-for="s in SOURCES" :key="s.id" :class="{ on: source === s.id }" @click="setSource(s.id)">
          {{ s.label }}
        </button>
      </div>
      <div class="seg">
        <button v-for="o in ORIGINS" :key="o.id" :class="{ on: origin === o.id }" @click="setOrigin(o.id)">
          {{ o.label }}
        </button>
      </div>
      <div class="sbox msearch">
        <svg class="ic"><use href="#s-search" /></svg>
        <input v-model="q" type="search" placeholder="Search prompts…" @keyup.enter="load" />
      </div>
    </div>

    <div class="mbody">
      <div v-if="loading && !items.length" class="empty">Loading…</div>
      <div v-else-if="!items.length" class="empty">No media yet.</div>
      <MediaGrid
        v-else
        :items="items"
        :selected="picked"
        checkboxes
        :has-more="items.length < total"
        @open="preview = $event"
        @toggle="toggle"
        @more="loadMore"
      />
    </div>

    <div v-if="picked.size" class="bulkbar">
      <span>{{ picked.size }} selected</span>
      <button class="btn btn-sm" :disabled="busy" @click="bulkDownload">Download</button>
      <button class="btn btn-sm btn-danger-quiet" :disabled="busy" @click="bulkDelete">Delete</button>
      <button class="btn btn-sm" @click="selectAll">Select all loaded</button>
      <button class="btn btn-sm btn-quiet" @click="clearPicked">Clear</button>
    </div>

    <div v-if="preview" class="ovl" @click="preview = null">
      <video v-if="preview.kind === 'video'" :src="preview.url" class="pv" controls autoplay @click.stop />
      <img v-else :src="preview.url" class="pv" alt="" @click.stop />
    </div>
  </div>
</template>

<style scoped>
.media {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.mhead {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 10px 18px;
  border-bottom: 1px solid var(--sborder2);
}
h1 {
  font-size: 15px;
  font-weight: 600;
}
.gcount {
  font-size: 12px;
  color: var(--smuted);
}
.spacer {
  flex: 1;
}
.mbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding: 10px 18px;
}
.msearch {
  flex: 1;
  min-width: 180px;
  max-width: 320px;
  margin-left: auto;
}
.mbody {
  flex: 1;
  overflow-y: auto;
  padding: 4px 18px 24px;
}
.bulkbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-top: 1px solid var(--sborder2);
  background: var(--spanel2);
}
.bulkbar span {
  flex: 1;
  color: var(--sfg);
  font-size: 13px;
}
.ovl {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.82);
  padding: 32px;
  cursor: zoom-out;
}
.pv {
  max-width: 92vw;
  max-height: 92vh;
  border-radius: var(--r);
  cursor: default;
}
</style>
