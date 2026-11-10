<script setup>
import { ref, reactive, computed, watch, inject, onBeforeUnmount } from 'vue'
import MediaGrid from './MediaGrid.vue'
import MediaFilters from './MediaFilters.vue'
import { fetchMediaPage, uploadMedia } from '../../composables/useMedia'
import { takeFiles } from '../../utils/files'

// Pick media from the library, or upload new from this computer (they go into
// the library and come back selected). Supports several kinds (image/video) at
// once with per-kind caps, for reference-to-video. Emits 'pick' with the chosen
// items; the caller imports them where they're used.
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: 'Choose images' },
  multiple: { type: Boolean, default: true },
  max: { type: Number, default: null }, // total that can be picked when no per-kind limits (null = no limit)
  kinds: { type: Array, default: () => ['image'] }, // which media kinds to show / accept
  limits: { type: Object, default: null }, // per-kind caps, e.g. { image: 10, video: 5 } (overrides `max`)
  origin: { type: String, default: 'all' }, // where-from filter it opens on
  source: { type: String, default: 'all' }, // source filter it opens on ('upload' = your uploads, not generated)
})
const emit = defineEmits(['pick', 'close'])
const showToast = inject('showToast', () => {})

// A page at a time, filtered server-side: the whole library in one request is
// a long wait before anything shows (and most of it is never scrolled to).
const PAGE = 30
const items = ref([])
const total = ref(0)
const loading = ref(false)
const uploading = ref(0)
const filters = reactive({ kind: 'all', source: props.source, origin: props.origin, q: '' })
const hasMore = computed(() => items.value.length < total.value)

// What's ticked, by id — kept as the items themselves so a pick survives
// scrolling on, searching, or changing a filter.
const picked = ref(new Map())
const selected = computed(() => new Set(picked.value.keys()))
const kindCount = kind => [...picked.value.values()].filter(i => i.kind === kind).length
// Per-kind tallies for the footer, e.g. "Images 2/10 · Videos 1/5"
const tallies = computed(() => props.kinds.map(k => ({ kind: k, n: kindCount(k), cap: props.limits?.[k] ?? null })))

const ACCEPT = { image: 'image/png,image/jpeg,image/webp,image/gif', video: 'video/mp4' }
const accept = computed(() =>
  props.kinds
    .map(k => ACCEPT[k])
    .filter(Boolean)
    .join(','),
)
const kindOf = file => (file.type.startsWith('video/') ? 'video' : file.type.startsWith('image/') ? 'image' : null)

// The dialog only ever offers `kinds`; one of them narrows the query, and both
// is every kind the library holds, so it asks for all of them.
const kindParam = () => (filters.kind !== 'all' ? filters.kind : props.kinds.length === 1 ? props.kinds[0] : undefined)
const params = offset => ({
  offset,
  limit: PAGE,
  kind: kindParam(),
  source: filters.source === 'all' ? undefined : filters.source,
  origin: filters.origin === 'all' ? undefined : filters.origin,
  q: filters.q.trim() || undefined,
})

let seq = 0
async function load() {
  const mine = ++seq
  loading.value = true
  try {
    const { items: page, total: t } = await fetchMediaPage(params(0))
    if (mine !== seq) return // a newer search already answered
    items.value = page
    total.value = t
  } catch (e) {
    if (mine === seq) showToast(`Couldn't load the library: ${e.message}`, 'error')
  } finally {
    if (mine === seq) loading.value = false
  }
}
async function loadMore() {
  if (!hasMore.value || loading.value) return
  const mine = seq
  const { items: page } = await fetchMediaPage(params(items.value.length))
  if (mine === seq) items.value = [...items.value, ...page]
}

// Typing re-queries, but only once you pause
let searchTimer = null
watch(
  () => filters.q,
  () => {
    clearTimeout(searchTimer)
    searchTimer = setTimeout(load, 250)
  },
)
watch([() => filters.kind, () => filters.source, () => filters.origin], load)
onBeforeUnmount(() => clearTimeout(searchTimer))

watch(
  () => props.open,
  open => {
    if (!open) return
    picked.value = new Map()
    filters.origin = props.origin
    filters.source = props.source
    filters.kind = 'all'
    filters.q = ''
    load()
  },
)

function toggle(item) {
  const next = new Map(picked.value)
  if (next.delete(item.id)) return (picked.value = next)
  if (!props.multiple) return (picked.value = new Map([[item.id, item]]))
  if (props.limits) {
    const cap = props.limits[item.kind]
    if (cap != null && kindCount(item.kind) >= cap)
      return showToast(`Up to ${cap} ${item.kind}${cap === 1 ? '' : 's'}`, 'error')
  } else if (props.max != null && picked.value.size >= props.max) {
    return showToast(`Pick up to ${props.max}`, 'error')
  }
  picked.value = next.set(item.id, item)
}

// An upload lands in the library and the server drops its cached list, so a
// reload brings it back at the top; the pick is held in `picked`, not in the
// page, so it survives that reload.
async function upload(files) {
  let widened = false
  for (const file of [...files]) {
    const kind = kindOf(file)
    if (!kind || !props.kinds.includes(kind)) continue
    uploading.value++
    try {
      const item = await uploadMedia(file)
      toggle(item) // pre-select what was just uploaded
      if (![item.origin, 'all'].includes(filters.origin)) {
        filters.origin = 'all' // so the upload shows (its watcher reloads)
        widened = true
      }
    } catch (e) {
      showToast(`Upload failed: ${e.message}`, 'error')
    } finally {
      uploading.value--
    }
  }
  if (!widened) await load()
}

function confirm() {
  emit('pick', [...picked.value.values()])
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="backdrop" @click.self="emit('close')" @keydown.esc="emit('close')">
      <div
        class="dialog"
        role="dialog"
        :aria-label="title"
        @dragover.prevent
        @drop.prevent="upload($event.dataTransfer?.files || [])"
      >
        <div class="head">
          <h3>{{ title }}</h3>
          <button class="iconbtn x" title="Close" @click="emit('close')">✕</button>
        </div>

        <div class="toolbar">
          <label class="btn upload">
            <svg class="ic"><use href="#s-download" /></svg> Upload from computer
            <input type="file" :accept="accept" :multiple="multiple" hidden @change="upload(takeFiles($event))" />
          </label>
          <span v-if="uploading" class="muted">Uploading {{ uploading }}…</span>
          <span class="muted hint">or drop files here, or choose from your uploads and creations below</span>
        </div>
        <MediaFilters v-model:filters="filters" :show-kind="false" />

        <div class="body">
          <p v-if="loading && !items.length" class="muted">Loading…</p>
          <p v-else-if="!items.length" class="muted">
            {{ filters.q.trim() ? 'Nothing matches that search.' : 'Nothing here yet — upload above.' }}
          </p>
          <MediaGrid
            v-else
            :items="items"
            :selected="selected"
            :has-more="hasMore"
            selectable
            @toggle="toggle"
            @more="loadMore"
          />
        </div>

        <div class="actions">
          <span class="muted tallies">
            <span v-for="t in tallies" :key="t.kind"
              >{{ t.kind === 'image' ? 'Images' : t.kind === 'video' ? 'Videos' : 'Audio' }} {{ t.n
              }}<template v-if="t.cap != null">/{{ t.cap }}</template></span
            >
          </span>
          <span class="spacer"></span>
          <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
          <button class="btn btn-primary" :disabled="!selected.size" @click="confirm">
            {{ selected.size > 1 ? `Add ${selected.size}` : 'Add' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 1200;
  background: rgba(0, 0, 0, 0.6);
  display: grid;
  place-items: center;
  padding: 16px;
}

.dialog {
  width: min(900px, 100%);
  height: min(720px, calc(100vh - 32px));
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--sbg);
  border: 1px solid var(--sborder);
  border-radius: var(--r-xl);
  box-shadow: var(--shadow-modal);
  padding: 14px 18px 16px;
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.head h3 {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
}

.x {
  width: 28px;
  height: 28px;
  margin-right: -6px;
  font-size: 13px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.upload .ic {
  transform: rotate(180deg);
}

.body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.muted {
  font-size: 12.5px;
  color: var(--smuted);
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tallies {
  display: flex;
  gap: 12px;
}

.spacer {
  flex: 1;
}

@media (max-width: 640px) {
  .hint {
    display: none;
  }
}
</style>
