<script setup>
import { ref, computed, watch, inject } from 'vue'
import MediaGrid from './MediaGrid.vue'
import MediaFilters from './MediaFilters.vue'
import { fetchMedia, uploadMedia, useMediaFilters } from '../../composables/useMedia'

// Pick images from the media library, or upload new ones from this
// computer (they go into the library and come back selected). Emits
// 'pick' with the chosen items; the caller imports them where they're used.
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: 'Choose images' },
  multiple: { type: Boolean, default: true },
  max: { type: Number, default: null },   // most that can be picked (null = no limit)
})
const emit = defineEmits(['pick', 'close'])
const showToast = inject('showToast', () => {})

const items = ref([])
const loading = ref(false)
const uploading = ref(0)
const selected = ref(new Set())
const images = computed(() => items.value.filter(i => i.kind === 'image'))
const { filters, filtered } = useMediaFilters(images, { kind: 'image' })
const limit = computed(() => (props.multiple ? props.max : 1))

watch(() => props.open, async (open) => {
  if (!open) return
  selected.value = new Set()
  loading.value = true
  try {
    items.value = await fetchMedia()
  } catch (e) {
    showToast(`Couldn't load the library: ${e.message}`, 'error')
  } finally {
    loading.value = false
  }
})

function toggle(item) {
  const next = new Set(limit.value === 1 ? [] : selected.value)
  if (selected.value.has(item.id)) next.delete(item.id)
  else if (limit.value == null || next.size < limit.value) next.add(item.id)
  else return showToast(`Pick up to ${limit.value}`, 'error')
  selected.value = next
}

async function upload(files) {
  for (const file of [...files].filter(f => f.type.startsWith('image/'))) {
    uploading.value++
    try {
      const item = await uploadMedia(file)
      items.value = [item, ...items.value]
      toggle(item)
    } catch (e) {
      showToast(`Upload failed: ${e.message}`, 'error')
    } finally {
      uploading.value--
    }
  }
}

function confirm() {
  emit('pick', items.value.filter(i => selected.value.has(i.id)))
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="backdrop" @click.self="emit('close')" @keydown.esc="emit('close')">
      <div class="dialog" role="dialog" :aria-label="title"
           @dragover.prevent @drop.prevent="upload($event.dataTransfer?.files || [])">
        <div class="head">
          <h3>{{ title }}</h3>
          <button class="x" title="Close" @click="emit('close')">✕</button>
        </div>

        <div class="toolbar">
          <label class="btn btn-secondary upload">
            ⬆ Upload from computer
            <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" :multiple="multiple" hidden
                   @change="upload($event.target.files); $event.target.value = ''" />
          </label>
          <span v-if="uploading" class="muted">Uploading {{ uploading }}…</span>
          <span class="muted hint">or drop images here, or choose from your uploads and creations below</span>
        </div>
        <MediaFilters :filters="filters" :show-kind="false" />

        <div class="body">
          <p v-if="loading" class="muted">Loading…</p>
          <p v-else-if="!filtered.length" class="muted">Nothing here yet — upload an image above.</p>
          <MediaGrid v-else :items="filtered" :selected="selected" selectable @toggle="toggle" />
        </div>

        <div class="actions">
          <span class="muted">{{ selected.size }} selected</span>
          <span class="spacer"></span>
          <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
          <button class="btn btn-primary" :disabled="!selected.size" @click="confirm">
            {{ selected.size > 1 ? `Use ${selected.size} images` : 'Use image' }}
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
