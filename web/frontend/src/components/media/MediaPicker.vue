<script setup>
import { ref, computed, watch, inject } from 'vue'
import MediaGrid from './MediaGrid.vue'
import MediaFilters from './MediaFilters.vue'
import { fetchMedia, uploadMedia, useMediaFilters } from '../../composables/useMedia'
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

const items = ref([])
const loading = ref(false)
const uploading = ref(0)
const selected = ref(new Set())
const shown = computed(() => items.value.filter(i => props.kinds.includes(i.kind)))
const { filters, filtered } = useMediaFilters(shown, { kind: 'all', origin: props.origin })
const byId = computed(() => Object.fromEntries(items.value.map(i => [i.id, i])))
const kindCount = kind => [...selected.value].filter(id => byId.value[id]?.kind === kind).length
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

watch(
  () => props.open,
  async open => {
    if (!open) return
    selected.value = new Set()
    filters.origin = props.origin
    filters.source = props.source
    loading.value = true
    try {
      items.value = await fetchMedia()
    } catch (e) {
      showToast(`Couldn't load the library: ${e.message}`, 'error')
    } finally {
      loading.value = false
    }
  },
)

function toggle(item) {
  if (selected.value.has(item.id)) {
    const next = new Set(selected.value)
    next.delete(item.id)
    selected.value = next
    return
  }
  if (!props.multiple) return (selected.value = new Set([item.id]))
  if (props.limits) {
    const cap = props.limits[item.kind]
    if (cap != null && kindCount(item.kind) >= cap)
      return showToast(`Up to ${cap} ${item.kind}${cap === 1 ? '' : 's'}`, 'error')
  } else if (props.max != null && selected.value.size >= props.max) {
    return showToast(`Pick up to ${props.max}`, 'error')
  }
  selected.value = new Set(selected.value).add(item.id)
}

async function upload(files) {
  for (const file of [...files]) {
    const kind = kindOf(file)
    if (!kind || !props.kinds.includes(kind)) continue
    uploading.value++
    try {
      const item = await uploadMedia(file)
      items.value = [item, ...items.value]
      if (![item.origin, 'all'].includes(filters.origin)) filters.origin = 'all' // so the upload shows
      toggle(item) // pre-select what was just uploaded
    } catch (e) {
      showToast(`Upload failed: ${e.message}`, 'error')
    } finally {
      uploading.value--
    }
  }
}

function confirm() {
  emit(
    'pick',
    items.value.filter(i => selected.value.has(i.id)),
  )
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
          <button class="x" title="Close" @click="emit('close')">✕</button>
        </div>

        <div class="toolbar">
          <label class="btn btn-secondary upload">
            ⬆ Upload from computer
            <input type="file" :accept="accept" :multiple="multiple" hidden @change="upload(takeFiles($event))" />
          </label>
          <span v-if="uploading" class="muted">Uploading {{ uploading }}…</span>
          <span class="muted hint">or drop files here, or choose from your uploads and creations below</span>
        </div>
        <MediaFilters v-model:filters="filters" :show-kind="false" />

        <div class="body">
          <p v-if="loading" class="muted">Loading…</p>
          <p v-else-if="!filtered.length" class="muted">Nothing here yet — upload above.</p>
          <MediaGrid v-else :items="filtered" :selected="selected" selectable @toggle="toggle" />
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
  background: rgba(0, 0, 0, 0.7);
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
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 20px;
}

.head {
  display: flex;
  align-items: center;
}

.head h3 {
  flex: 1;
  font-size: 1.1rem;
}

.x {
  background: none;
  border: none;
  color: var(--text2);
  font-size: 1rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.upload {
  padding: 8px 14px;
  cursor: pointer;
}

.body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.muted {
  font-size: 0.8rem;
  color: var(--text2);
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

.actions .btn {
  padding: 8px 16px;
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
