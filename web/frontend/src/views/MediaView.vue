<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import MediaGrid from '../components/media/MediaGrid.vue'
import MediaFilters from '../components/media/MediaFilters.vue'
import CharacterEditor from '../components/characters/CharacterEditor.vue'
import {
  fetchMediaPage,
  uploadMedia,
  deleteMedia,
  importMedia,
  mediaOrigin,
  fetchBlockedCounts,
  clearBlocked,
} from '../composables/useMedia'
import { fetchCharacters } from '../composables/useCharacters'
import { fmtCost } from '../utils/format'
import { takeFiles } from '../utils/files'

const showToast = inject('showToast', () => {})

// The library is paged from the server (filters applied there) and grown as
// you scroll — only what's on screen is fetched. `items` is what's loaded so
// far, `total` how many match the current filters.
const PAGE = 60
const items = ref([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const uploading = ref(0)
const filters = reactive({ kind: 'all', source: 'all', origin: 'all', q: '' })
const filtersActive = computed(
  () => filters.kind !== 'all' || filters.source !== 'all' || filters.origin !== 'all' || !!filters.q.trim(),
)
// The chat sidebar's 🖼 Media button opens this filtered to chats
const ORIGINS = ['library', 'project', 'chat', 'orphan']
const route = useRoute()
if (ORIGINS.includes(route?.query.origin)) filters.origin = route.query.origin

// Generations a content filter blocked: failed cards in chats, and black
// images saved before the app caught those
const blocked = ref({ moderated: 0, black: 0 })
const blockedTotal = computed(() => blocked.value.moderated + blocked.value.black)
const clearing = ref(false)

async function loadBlocked() {
  try {
    blocked.value = await fetchBlockedCounts()
  } catch {
    /* the button just stays hidden */
  }
}

async function clearAllBlocked() {
  const { moderated, black } = blocked.value
  const parts = []
  if (moderated) parts.push(`${moderated} failed generation${moderated !== 1 ? 's' : ''} (removed from their chats)`)
  if (black) parts.push(`${black} black image${black !== 1 ? 's' : ''} (deleted)`)
  if (!confirm(`Clear everything a content filter blocked?\n\n${parts.join('\n')}`)) return
  clearing.value = true
  try {
    const { cleared } = await clearBlocked()
    showToast(`Cleared ${cleared} blocked generation${cleared !== 1 ? 's' : ''}`, 'success')
    await Promise.all([load(), loadBlocked()])
  } catch (e) {
    showToast(`Couldn't clear: ${e.message}`, 'error')
  } finally {
    clearing.value = false
  }
}

// Selecting: ticking any tile's circle (on hover) starts it, or the Select
// button (touch screens have no hover). While selecting, clicks toggle
// tiles and shift-click selects the range from the last one clicked.
const selectMode = ref(false)
const selected = ref(new Set())
const selecting = computed(() => selectMode.value || selected.value.size > 0)
const lastToggled = ref(null)
const busy = ref('') // what a bulk action is doing, e.g. "Deleting 3 of 40…"
const selectedItems = computed(() => items.value.filter(i => selected.value.has(i.id)))
const selectedImages = computed(() => selectedItems.value.filter(i => i.kind === 'image'))
const preview = ref(null)

// Characters: make a new one from images, or add images to an existing one
const charEditor = ref({ open: false, seed: [] })
const savedCharacters = ref([])
const addToCharacterId = ref('')

const queryParams = (extra = {}) => ({
  kind: filters.kind,
  source: filters.source,
  origin: filters.origin,
  q: filters.q,
  ...extra,
})

async function load() {
  loading.value = true
  try {
    const { items: page, total: t } = await fetchMediaPage(queryParams({ offset: 0, limit: PAGE }))
    items.value = page
    total.value = t
  } catch (e) {
    showToast(`Couldn't load media: ${e.message}`, 'error')
  } finally {
    loading.value = false
  }
}

// Next page, appended, when the grid scrolls near its end
async function loadMore() {
  if (loadingMore.value || items.value.length >= total.value) return
  loadingMore.value = true
  try {
    const { items: page, total: t } = await fetchMediaPage(queryParams({ offset: items.value.length, limit: PAGE }))
    const seen = new Set(items.value.map(i => i.id)) // a creation mid-scroll could shift the pages
    items.value = [...items.value, ...page.filter(i => !seen.has(i.id))]
    total.value = t
  } catch (e) {
    showToast(`Couldn't load more: ${e.message}`, 'error')
  } finally {
    loadingMore.value = false
  }
}

// Changing a filter (typing in search is debounced) reloads from the top
let reloadTimer
watch(filters, () => {
  clearTimeout(reloadTimer)
  reloadTimer = setTimeout(load, 250)
})

async function loadCharacters() {
  try {
    savedCharacters.value = await fetchCharacters()
  } catch {
    /* 401 handled by auth prompt */
  }
}

async function upload(files) {
  for (const file of [...files].filter(f => f.type.startsWith('image/'))) {
    uploading.value++
    try {
      items.value = [await uploadMedia(file), ...items.value]
      total.value++
    } catch (e) {
      showToast(`Upload failed: ${e.message}`, 'error')
    } finally {
      uploading.value--
    }
  }
}

function toggleSelectMode() {
  if (selecting.value) return clearSelection()
  selectMode.value = true
}

function clearSelection() {
  selectMode.value = false
  selected.value = new Set()
  lastToggled.value = null
}

async function selectAll() {
  // Select every match, not just the loaded page — fetch the rest first
  if (items.value.length < total.value) {
    try {
      const { items: all, total: t } = await fetchMediaPage(queryParams({ offset: 0, limit: 0 }))
      items.value = all
      total.value = t
    } catch (e) {
      return showToast(`Couldn't select all: ${e.message}`, 'error')
    }
  }
  selected.value = new Set(items.value.map(i => i.id))
}

function toggle(item, event) {
  const next = new Set(selected.value)
  const range = event?.shiftKey && lastToggled.value != null ? rangeTo(item) : null
  if (range) range.forEach(i => next.add(i.id))
  else if (!next.delete(item.id)) next.add(item.id)
  selected.value = next
  lastToggled.value = item.id
}

// The shown items from the last one clicked to this one
function rangeTo(item) {
  const list = items.value
  const a = list.findIndex(i => i.id === lastToggled.value)
  const b = list.findIndex(i => i.id === item.id)
  if (a === -1 || b === -1) return null
  return list.slice(Math.min(a, b), Math.max(a, b) + 1)
}

function onKey(e) {
  if (e.key === 'Escape' && selecting.value && !preview.value && !charEditor.value.open) clearSelection()
}

const DELETE_NOTE =
  'Creations also lose their generation record or chat message; copies used by characters, chats and generations stay.'

async function remove(list) {
  if (!list.length) return
  const what = list.length === 1 ? 'this item' : `${list.length} items`
  if (!confirm(`Delete ${what} permanently?\n\n${DELETE_NOTE}`)) return
  const gone = new Set()
  try {
    for (const [n, item] of list.entries()) {
      if (list.length > 1) busy.value = `Deleting ${n + 1} of ${list.length}…`
      try {
        await deleteMedia(item.id)
        gone.add(item.id)
      } catch (e) {
        showToast(`Couldn't delete ${item.name}: ${e.message}`, 'error')
      }
    }
  } finally {
    busy.value = ''
  }
  items.value = items.value.filter(i => !gone.has(i.id))
  total.value -= gone.size
  selected.value = new Set([...selected.value].filter(id => !gone.has(id)))
  if (preview.value && gone.has(preview.value.id)) preview.value = null
  if (gone.size) showToast(`Deleted ${gone.size} item${gone.size !== 1 ? 's' : ''}`, 'success')
}

function newCharacter(list) {
  const seed = list
    .filter(i => i.kind === 'image')
    .slice(0, 6)
    .map(i => ({ kind: 'media', mediaId: i.id, preview: i.thumb_url || i.url }))
  if (!seed.length) return showToast('Pick at least one image', 'error')
  preview.value = null
  charEditor.value = { open: true, seed }
}

async function addToCharacter(list) {
  const id = Number(addToCharacterId.value)
  addToCharacterId.value = ''
  if (!id) return
  const images = list.filter(i => i.kind === 'image')
  try {
    let c = null
    for (const [n, item] of images.entries()) {
      if (images.length > 1) busy.value = `Adding ${n + 1} of ${images.length}…`
      c = await importMedia(item.id, { target: 'character', character_id: id })
    }
    if (c) showToast(`Added ${images.length} image${images.length !== 1 ? 's' : ''} to ${c.name}`, 'success')
  } catch (e) {
    showToast(`Couldn't add: ${e.message}`, 'error')
  } finally {
    busy.value = ''
  }
}

function sourceLink(item) {
  if (item.origin === 'project') return { name: 'project-gallery', params: { project: item.project } }
  if (item.conversation_id) return { name: 'chat-conversation', params: { id: item.conversation_id } }
  return null
}

const fmtDate = s => (s ? new Date(s).toLocaleString() : '')

onMounted(() => {
  load()
  loadCharacters()
  loadBlocked()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  clearTimeout(reloadTimer)
})
</script>

<template>
  <div class="media-view" @dragover.prevent @drop.prevent="upload($event.dataTransfer?.files || [])">
    <header class="page-header">
      <div>
        <h1>Media</h1>
        <p class="sub">
          Everything you've uploaded or created, in projects, chats and here. Use them for characters, generations and
          chats with the 🗂 buttons there. Drop images anywhere on this page to upload.
        </p>
      </div>
      <label class="btn btn-primary upload">
        ⬆ Upload
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          multiple
          hidden
          @change="upload(takeFiles($event))"
        />
      </label>
    </header>

    <div class="bar">
      <MediaFilters v-model:filters="filters" />
      <button
        v-if="blockedTotal"
        class="btn btn-secondary small clear-blocked"
        :disabled="clearing"
        title="Remove failed generations a content filter blocked, and black images it sent back"
        @click="clearAllBlocked"
      >
        🧹 Clear blocked ({{ blockedTotal }})
      </button>
      <button class="btn btn-secondary small" @click="toggleSelectMode">{{ selecting ? 'Cancel' : 'Select' }}</button>
    </div>
    <p v-if="uploading" class="muted">Uploading {{ uploading }}…</p>

    <div v-if="selecting" class="selection-bar">
      <span>{{ selected.size }} selected</span>
      <button v-if="selected.size < total" class="btn btn-secondary small" :disabled="!!busy" @click="selectAll">
        Select all {{ total }}
      </button>
      <button v-if="selected.size" class="btn btn-secondary small" :disabled="!!busy" @click="clearSelection">
        Clear
      </button>
      <span class="hint">{{ busy || 'Shift-click selects a range · Esc clears' }}</span>
      <span class="spacer"></span>
      <button
        v-if="selectedImages.length"
        class="btn btn-secondary small"
        :disabled="!!busy"
        @click="newCharacter(selectedItems)"
      >
        👤 New character
      </button>
      <select
        v-if="selectedImages.length && savedCharacters.length"
        v-model="addToCharacterId"
        class="char-select"
        :disabled="!!busy"
        @change="addToCharacter(selectedItems)"
      >
        <option value="">Add to character…</option>
        <option v-for="c in savedCharacters" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <button v-if="selected.size" class="btn btn-danger small" :disabled="!!busy" @click="remove(selectedItems)">
        Delete {{ selected.size }}
      </button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="!total" class="empty-state">
      <h3>{{ filtersActive ? 'Nothing matches these filters' : 'No media yet' }}</h3>
      <p>Upload images here, or make some in a project or chat.</p>
    </div>
    <template v-else>
      <MediaGrid
        :items="items"
        :selected="selected"
        :selectable="selecting"
        :has-more="items.length < total"
        checkboxes
        @toggle="toggle"
        @open="preview = $event"
        @more="loadMore"
      />
      <p v-if="loadingMore" class="muted center">Loading more…</p>
    </template>

    <!-- Preview -->
    <Teleport to="body">
      <div v-if="preview" class="preview" @click.self="preview = null" @keydown.esc="preview = null">
        <div class="preview-card">
          <button class="x" title="Close" @click="preview = null">✕</button>
          <img v-if="preview.kind === 'image'" :src="preview.url" alt="" />
          <video v-else :src="preview.url" controls autoplay></video>
          <div class="info">
            <p class="where">
              {{ preview.source === 'upload' ? 'Uploaded' : 'Created' }} ·
              <RouterLink v-if="sourceLink(preview)" :to="sourceLink(preview)">{{ mediaOrigin(preview) }}</RouterLink>
              <span v-else>{{ mediaOrigin(preview) }}</span>
              · {{ fmtDate(preview.created_at) }}
            </p>
            <p v-if="preview.prompt" class="prompt">{{ preview.prompt }}</p>
            <p v-if="preview.model" class="muted">
              {{ preview.model }}<template v-if="preview.cost"> · {{ fmtCost(preview.cost) }}</template>
            </p>
            <div class="actions">
              <template v-if="preview.kind === 'image'">
                <button class="btn btn-secondary small" @click="newCharacter([preview])">👤 New character</button>
                <select
                  v-if="savedCharacters.length"
                  v-model="addToCharacterId"
                  class="char-select"
                  @change="addToCharacter([preview])"
                >
                  <option value="">Add to character…</option>
                  <option v-for="c in savedCharacters" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
              </template>
              <a class="btn btn-secondary small" :href="preview.url" :download="preview.name">⬇ Download</a>
              <span class="spacer"></span>
              <button class="btn btn-danger small" @click="remove([preview])">Delete</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <CharacterEditor
      :open="charEditor.open"
      :seed="charEditor.seed"
      @close="charEditor.open = false"
      @saved="
        c => {
          showToast(`Character “${c.name}” saved`, 'success')
          loadCharacters()
        }
      "
    />
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-header h1 {
  font-size: 1.5rem;
}

.sub,
.muted {
  font-size: 0.85rem;
  color: var(--text2);
  margin-top: 4px;
  line-height: 1.45;
}

.upload {
  cursor: pointer;
  flex-shrink: 0;
}

.bar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.bar > :first-child {
  flex: 1;
}

.btn.small {
  padding: 6px 12px;
  font-size: 0.8rem;
}

.selection-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--accent);
  font-size: 0.85rem;
  flex-wrap: wrap;
}

.hint {
  font-size: 0.75rem;
  color: var(--text2);
}

.char-select {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  font-size: 0.8rem;
}

.spacer {
  flex: 1;
}

.center {
  text-align: center;
  padding: 12px;
}

.empty-state {
  text-align: center;
  padding: 48px 16px;
  color: var(--text2);
}

.empty-state h3 {
  color: var(--text);
  margin-bottom: 6px;
}

.preview {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.85);
  display: grid;
  place-items: center;
  padding: 16px;
}

.preview-card {
  position: relative;
  width: min(960px, 100%);
  max-height: calc(100vh - 32px);
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
}

.preview-card img,
.preview-card video {
  display: block;
  width: 100%;
  max-height: 65vh;
  object-fit: contain;
  background: #000;
}

.x {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 1;
  background: rgba(0, 0, 0, 0.6);
  border: none;
  color: #fff;
  border-radius: 50%;
  width: 30px;
  height: 30px;
  cursor: pointer;
}

.info {
  padding: 12px 16px 16px;
}

.where a {
  color: var(--accent2);
}

.prompt {
  margin: 8px 0 4px;
  font-size: 0.9rem;
  line-height: 1.45;
  white-space: pre-wrap;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}

@media (max-width: 640px) {
  .page-header,
  .bar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
