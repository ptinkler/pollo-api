<!-- A thread's Generations gallery: flattens the thread's message media into
     cards (newest first) and hands them to GenerationGrid. Includes in-progress
     (pending) and failed tiles too, so it doubles as the live generation queue. -->
<script setup>
import { computed, ref, watch } from 'vue'
import { fetchMediaPage } from '../../composables/useMedia'
import { chatMediaUrl, chatMediaPreviewUrl } from '../../composables/useChat'
import GenerationGrid from './GenerationGrid.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  convId: { type: [String, Number], default: '' },
})
const emit = defineEmits(['open', 'favourite'])

function toCard(m, item, originals) {
  const hasFile = !!item.file
  const url = f => chatMediaUrl(props.convId, f)
  const thumb = f => (item.kind === 'image' ? chatMediaPreviewUrl(props.convId, f) : url(f))
  return {
    ...item,
    message_id: m.id,
    conversation_id: props.convId,
    model: item.model || m.model,
    // What the user typed (the parent message), vs the prompt the model ended up with
    original_prompt: originals.get(m.parent_id)?.content || '',
    cost: m.cost,
    created_at: m.created_at,
    url: hasFile ? url(item.file) : '',
    preview: hasFile ? thumb(item.file) : '',
  }
}

// Only generations — uploads on user messages aren't shown here
const isGeneration = item =>
  (item.kind === 'image' || item.kind === 'video') && (item.source || 'generated') === 'generated'

const items = computed(() => {
  const originals = new Map(props.messages.map(m => [m.id, m]))
  const out = props.messages.flatMap(m => (m.media || []).filter(isGeneration).map(i => toCard(m, i, originals)))
  return out.reverse()
})
// Files in this thread's folder that no message records (loaded on demand: it
// scans the whole library)
const showOrphans = ref(false)
const orphans = ref([])
const loadingOrphans = ref(false)
async function loadOrphans() {
  loadingOrphans.value = true
  try {
    const { items: all } = await fetchMediaPage({ origin: 'orphan' })
    orphans.value = (all || [])
      .filter(i => i.conversation_id === props.convId)
      .map(i => ({ ...i, status: 'done', file: i.name, preview: i.thumb_url || i.url, orphan: true }))
  } finally {
    loadingOrphans.value = false
  }
}
function toggleOrphans() {
  showOrphans.value = !showOrphans.value
  if (showOrphans.value) loadOrphans()
}
watch(
  () => props.convId,
  () => {
    showOrphans.value = false
    orphans.value = []
  },
)
// Orphans have no message to manage: open the file itself, and no favouriting
const onOpen = item => (item.orphan ? window.open(item.url, '_blank', 'noopener') : emit('open', item))
const onFavourite = item => !item.orphan && emit('favourite', item)
const shownItems = computed(() => (showOrphans.value ? orphans.value : items.value))
</script>

<template>
  <div class="gwrap">
    <div class="orphbar">
      <button
        :class="{ on: showOrphans }"
        title="Files in this thread that no message references"
        @click="toggleOrphans"
      >
        Orphaned<template v-if="showOrphans && !loadingOrphans"> ({{ orphans.length }})</template>
      </button>
    </div>
    <GenerationGrid
      :items="shownItems"
      :empty="
        showOrphans
          ? loadingOrphans
            ? 'Scanning…'
            : 'No orphaned files in this thread.'
          : 'No generations in this thread yet.'
      "
      @open="onOpen"
      @favourite="onFavourite"
    />
  </div>
</template>

<style scoped>
.gwrap {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.orphbar {
  padding: 6px 18px 0;
  display: flex;
  justify-content: flex-end;
}
.orphbar button {
  font: inherit;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--sborder);
  background: none;
  color: var(--smuted);
  cursor: pointer;
}
.orphbar button.on {
  background: var(--saccent-soft, var(--saccent));
  color: var(--sfg);
}
</style>
