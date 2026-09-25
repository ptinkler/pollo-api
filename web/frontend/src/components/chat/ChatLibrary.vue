<script setup>
import { ref, computed, onMounted, onBeforeUnmount, inject } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchChatLibrary, deleteLibraryItem, chatMediaUrl } from '../../composables/useChat'

const emit = defineEmits(['open-media'])
const showToast = inject('showToast', () => {})

const items = ref([])
const loading = ref(true)
const filter = ref('all')   // all | unattached | image | video

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'image', label: 'Images' },
  { id: 'video', label: 'Videos' },
  { id: 'unattached', label: 'Unattached' },
]

const shown = computed(() => items.value.filter(i =>
  filter.value === 'all' ||
  (filter.value === 'unattached' ? !i.attached : i.kind === filter.value)))

const counts = computed(() => ({
  all: items.value.length,
  image: items.value.filter(i => i.kind === 'image').length,
  video: items.value.filter(i => i.kind === 'video').length,
  unattached: items.value.filter(i => !i.attached).length,
}))

async function load() {
  try {
    items.value = (await fetchChatLibrary()).items
  } catch (e) {
    showToast(`Couldn't load library: ${e.message}`, 'error')
  } finally {
    loading.value = false
  }
}

// Detached videos may still be rendering — refresh while any are pending
let timer = null
onMounted(() => {
  load()
  timer = setInterval(() => {
    if (items.value.some(i => i.status === 'pending')) load()
  }, 10000)
})
onBeforeUnmount(() => clearInterval(timer))

async function remove(item) {
  if (!confirm('Delete this from the library? The file is removed permanently.')) return
  try {
    await deleteLibraryItem(item.id)
    items.value = items.value.filter(i => i.id !== item.id)
  } catch (e) {
    showToast(`Delete failed: ${e.message}`, 'error')
  }
}

const url = (i) => chatMediaUrl(i.conversation_id, i.file)
const shortModel = (id) => (id || '').split('/').pop()
const fmtCost = (c) => (!c ? '' : c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`)
const fmtDate = (iso) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
</script>

<template>
  <div class="library">
    <div class="lib-head">
      <h2>Library</h2>
      <div class="filters">
        <button
          v-for="f in FILTERS"
          :key="f.id"
          class="filter"
          :class="{ active: filter === f.id }"
          @click="filter = f.id"
        >{{ f.label }} <span class="count">{{ counts[f.id] }}</span></button>
      </div>
    </div>
    <p class="lib-sub">Every image and video from your chats. Media from edited or retried replies stays here as <em>unattached</em>.</p>

    <div v-if="loading" class="lib-empty"><div class="spinner"></div></div>
    <div v-else-if="!shown.length" class="lib-empty">
      {{ items.length ? 'Nothing matches this filter.' : 'No images or videos yet — ask for one in a chat.' }}
    </div>

    <div v-else class="grid">
      <div v-for="i in shown" :key="i.id" class="card">
        <div class="thumb">
          <template v-if="i.status === 'done' && i.file">
            <img
              v-if="i.kind === 'image'"
              :src="url(i)"
              :alt="i.prompt || ''"
              loading="lazy"
              @click="emit('open-media', { url: url(i), kind: 'image', prompt: i.prompt })"
            />
            <video v-else :src="url(i)" controls loop playsinline preload="metadata"></video>
          </template>
          <div v-else-if="i.status === 'pending'" class="state"><div class="spinner"></div> Rendering…</div>
          <div v-else class="state err">Failed{{ i.error ? `: ${i.error}` : '' }}</div>
          <span v-if="!i.attached" class="tag">unattached</span>
        </div>
        <div class="info">
          <p class="prompt" :title="i.prompt">{{ i.prompt || '—' }}</p>
          <div class="meta">
            <span :title="i.model">{{ i.kind === 'image' ? '🖼' : '🎬' }} {{ shortModel(i.model) }}</span>
            <span v-if="i.cost">{{ fmtCost(i.cost) }}</span>
            <span>{{ fmtDate(i.created_at) }}</span>
          </div>
          <div class="actions">
            <RouterLink
              v-if="i.conversation_title"
              :to="{ name: 'chat-conversation', params: { id: i.conversation_id } }"
              class="from"
              :title="i.attached ? 'Open the chat' : 'Open the chat it came from'"
            >↗ {{ i.conversation_title }}</RouterLink>
            <a v-if="i.file" :href="url(i)" :download="i.file" class="act" title="Download">⤓</a>
            <button v-if="!i.attached" class="act" title="Delete" @click="remove(i)">🗑</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.library {
  max-width: 1200px;
  margin: 0 auto;
}

.lib-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.lib-head h2 {
  font-size: 1.4rem;
  font-weight: 600;
}

.lib-sub {
  color: var(--text2);
  font-size: 0.85rem;
  margin: 6px 0 18px;
}

.filters {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.filter {
  padding: 5px 11px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text2);
  font-size: 0.8rem;
  cursor: pointer;
}

.filter.active {
  background: rgba(108, 92, 231, 0.2);
  border-color: var(--accent);
  color: var(--text);
}

.count {
  opacity: 0.6;
  margin-left: 2px;
}

.lib-empty {
  display: grid;
  place-items: center;
  padding: 80px 20px;
  color: var(--text2);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 14px;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.thumb {
  position: relative;
  aspect-ratio: 1;
  background: #000;
}

.thumb img,
.thumb video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.thumb img {
  cursor: zoom-in;
}

.state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  font-size: 0.8rem;
  color: var(--text2);
  text-align: center;
}

.state.err {
  color: var(--red);
}

.tag {
  position: absolute;
  top: 8px;
  left: 8px;
  font-size: 0.68rem;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.7);
  color: var(--yellow);
}

.info {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.prompt {
  font-size: 0.8rem;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 0.7rem;
  color: var(--text2);
}

.actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.from {
  flex: 1;
  min-width: 0;
  font-size: 0.75rem;
  color: var(--accent2);
  text-decoration: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.from:hover {
  text-decoration: underline;
}

.act {
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  font-size: 0.85rem;
  padding: 3px 6px;
  border-radius: 6px;
  text-decoration: none;
}

.act:hover {
  background: var(--surface2);
  color: var(--text);
}
</style>
