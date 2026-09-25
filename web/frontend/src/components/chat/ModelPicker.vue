<script setup>
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'
import { useModelFavourites } from '../../composables/useModelFavourites'

const props = defineProps({
  modelValue: { type: String, default: '' },
  models: { type: Array, default: () => [] },
  label: { type: String, required: true },
  icon: { type: String, default: '' },
  kind: { type: String, default: 'text' },  // text | image | video
  loading: { type: Boolean, default: false },
  // Render the trigger as a small text button (e.g. "Try another model…")
  // instead of the labelled picker box, for one-off picks
  triggerText: { type: String, default: '' },
  allowNone: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const query = ref('')
const root = ref(null)
const searchInput = ref(null)

const current = computed(() => props.models.find(m => m.id === props.modelValue))

const { favourites, isFavourite, toggleFavourite } = useModelFavourites()

const matches = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q
    ? props.models.filter(m => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q))
    : props.models
})

// Favourites keep the order they were starred in; models that have left
// the catalogue are skipped rather than shown broken
const favouriteModels = computed(() => {
  const byId = new Map(matches.value.map(m => [m.id, m]))
  return (favourites[props.kind] || []).map(id => byId.get(id)).filter(Boolean)
})
const otherModels = computed(() =>
  matches.value.filter(m => !isFavourite(props.kind, m.id)).slice(0, 200))
const filtered = computed(() => [...favouriteModels.value, ...otherModels.value])

const sections = computed(() => {
  const out = []
  if (favouriteModels.value.length) out.push({ id: 'fav', label: '★ Favourites', models: favouriteModels.value })
  // Only label the main list when there's a favourites list to tell it apart from
  out.push({ id: 'all', label: favouriteModels.value.length ? 'All models' : '', models: otherModels.value })
  return out
})

function perMillion(price) {
  const n = Number(price)
  if (!price || Number.isNaN(n)) return null
  if (n === 0) return 'free'
  const v = n * 1e6
  return `$${v < 1 ? v.toFixed(2) : v.toFixed(v < 10 ? 1 : 0)}`
}

function badges(m) {
  const out = []
  if (props.kind === 'text') {
    if (m.input_modalities?.includes('image')) out.push({ t: 'vision', title: 'Accepts images' })
    if (m.supports_tools) out.push({ t: 'tools', title: 'Can create images/videos in Auto mode' })
    const p = perMillion(m.prompt_price)
    const c = perMillion(m.completion_price)
    if (p) out.push({ t: p === 'free' ? 'free' : `${p}/${c}`, title: 'Input/output price per million tokens' })
  } else if (props.kind === 'image') {
    if (m.input_modalities?.includes('image')) out.push({ t: 'edits', title: 'Accepts reference images' })
  } else if (props.kind === 'video') {
    if (m.frame_images?.includes('first_frame')) out.push({ t: 'img→vid', title: 'Can animate an image' })
    if (m.durations?.length) out.push({ t: `${Math.min(...m.durations)}–${Math.max(...m.durations)}s`, title: 'Durations' })
    if (m.generate_audio) out.push({ t: 'audio', title: 'Can generate audio' })
  }
  return out
}

function onDocClick(e) {
  if (root.value && !root.value.contains(e.target)) close()
}

async function toggle() {
  if (open.value) return close()
  open.value = true
  query.value = ''
  document.addEventListener('mousedown', onDocClick)
  await nextTick()
  searchInput.value?.focus()
}

function close() {
  open.value = false
  document.removeEventListener('mousedown', onDocClick)
}

function pick(m) {
  emit('update:modelValue', m.id)
  close()
}

function onKeydown(e) {
  if (e.key === 'Escape') close()
  if (e.key === 'Enter' && filtered.value.length) pick(filtered.value[0])
}

onBeforeUnmount(() => document.removeEventListener('mousedown', onDocClick))
</script>

<template>
  <div ref="root" class="model-picker">
    <button v-if="triggerText" type="button" class="picker-trigger" :class="{ active: open }" @click="toggle">
      {{ triggerText }}
    </button>
    <button v-else type="button" class="picker-btn" :class="{ active: open }" @click="toggle" :title="modelValue || 'None selected'">
      <span class="picker-icon">{{ icon }}</span>
      <span class="picker-text">
        <span class="picker-label">{{ label }}</span>
        <span class="picker-value">
          <template v-if="loading">Loading…</template>
          <template v-else>{{ current?.name || modelValue || 'None' }}</template>
        </span>
      </span>
      <span class="chev">▾</span>
    </button>

    <div v-if="open" class="picker-pop">
      <input
        ref="searchInput"
        v-model="query"
        class="picker-search"
        :placeholder="`Search ${models.length} ${label.toLowerCase()} models…`"
        @keydown="onKeydown"
      />
      <div class="picker-list">
        <template v-for="section in sections" :key="section.id">
          <div v-if="section.label" class="picker-section">{{ section.label }}</div>
          <button
            v-if="section.id === 'all' && kind !== 'text' && allowNone && !query"
            type="button"
            class="picker-item"
            :class="{ selected: !modelValue }"
            @click="emit('update:modelValue', ''); close()"
          >
            <span class="item-name">None</span>
            <span class="item-id">Disable {{ kind }} generation</span>
          </button>
          <div
            v-for="m in section.models"
            :key="m.id"
            role="button"
            tabindex="0"
            class="picker-item"
            :class="{ selected: m.id === modelValue }"
            @click="pick(m)"
            @keydown.enter.prevent="pick(m)"
          >
            <span class="item-row">
              <span class="item-name">{{ m.name }}</span>
              <span class="item-badges">
                <span v-for="b in badges(m)" :key="b.t" class="item-badge" :title="b.title">{{ b.t }}</span>
              </span>
              <button
                type="button"
                class="star"
                :class="{ on: isFavourite(kind, m.id) }"
                :title="isFavourite(kind, m.id) ? 'Remove from favourites' : 'Add to favourites'"
                :aria-pressed="isFavourite(kind, m.id)"
                @click.stop="toggleFavourite(kind, m.id)"
                @keydown.enter.stop"
              >{{ isFavourite(kind, m.id) ? '★' : '☆' }}</button>
            </span>
            <span class="item-id">{{ m.id }}</span>
          </div>
        </template>
        <div v-if="!filtered.length" class="picker-empty">No models match “{{ query }}”</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-picker {
  position: relative;
  min-width: 0;
}

.picker-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 6px 10px;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s;
}

.picker-trigger {
  background: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 10px;
  color: var(--text);
  font-size: 0.78rem;
  cursor: pointer;
}

.picker-trigger:hover,
.picker-trigger.active {
  border-color: var(--accent);
}

.picker-btn:hover,
.picker-btn.active {
  border-color: var(--accent);
}

.picker-icon {
  font-size: 1rem;
}

.picker-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.picker-label {
  font-size: 0.65rem;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.picker-value {
  font-size: 0.85rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chev {
  color: var(--text2);
  font-size: 0.75rem;
}

.picker-pop {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 50;
  width: min(420px, 92vw);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.picker-search {
  width: 100%;
  border: none;
  border-bottom: 1px solid var(--border);
  border-radius: 0;
  padding: 10px 12px;
  background: var(--surface);
}

.picker-list {
  max-height: 360px;
  overflow-y: auto;
  padding: 4px;
}

.picker-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  background: none;
  border: none;
  border-radius: 8px;
  padding: 7px 10px;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.picker-item:hover {
  background: var(--surface2);
}

.picker-item.selected {
  background: rgba(108, 92, 231, 0.18);
}

.item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.item-name {
  font-size: 0.87rem;
}

.item-id {
  font-size: 0.72rem;
  color: var(--text2);
  font-family: monospace;
}

.item-badges {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  margin-left: auto;
}

.item-badge {
  font-size: 0.65rem;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--surface2);
  color: var(--accent2);
}

.picker-section {
  padding: 8px 10px 4px;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text2);
}

.picker-section:not(:first-child) {
  margin-top: 4px;
  border-top: 1px solid var(--border);
  padding-top: 10px;
}

.star {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text2);
  font-size: 1rem;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 6px;
  cursor: pointer;
  opacity: 0.45;
  transition: opacity 0.15s, color 0.15s;
}

.picker-item:hover .star,
.star:focus-visible {
  opacity: 1;
}

.star:hover {
  color: var(--yellow);
}

.star.on {
  color: var(--yellow);
  opacity: 1;
}

.picker-empty {
  padding: 16px;
  text-align: center;
  color: var(--text2);
  font-size: 0.85rem;
}
</style>
