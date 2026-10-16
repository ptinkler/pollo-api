<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useChatDefaults } from '../../composables/useChatDefaults'

// "Default for": where the item being edited applies by default — all chats
// and/or any spaces — picked from a searchable dropdown (click to tick or
// untick). Part of the editor's form: picks are kept here (`dirty` reports
// them) until the editor saves and calls `commit(id)` with the saved item's
// id, so they work for new items too.
const props = defineProps({
  kind: { type: String, required: true }, // 'character' | 'instruction' | 'instruction_group'
  itemId: { type: Number, default: null }, // null = not saved yet
})
const emit = defineEmits(['update:dirty'])

const GLOBAL = 'global'
const SEARCH_FROM = 6 // the list gets a search box once there are this many spaces

const { spaces, membership, setMembership, ensureLoaded } = useChatDefaults()
const picked = ref(new Set()) // GLOBAL and/or space ids
const open = ref(false)
const query = ref('')
const root = ref(null)
const searchInput = ref(null)

const saved = computed(() => {
  if (props.itemId == null) return new Set()
  const m = membership(props.kind, props.itemId)
  return new Set([...(m.global ? [GLOBAL] : []), ...m.spaceIds])
})
const dirty = computed(() => picked.value.size !== saved.value.size || [...picked.value].some(k => !saved.value.has(k)))

const options = computed(() => [
  { key: GLOBAL, icon: '🌐', name: 'All chats' },
  ...spaces.value.map(s => ({ key: s.id, icon: '🗂', name: s.name })),
])
const shown = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? options.value.filter(o => o.name.toLowerCase().includes(q)) : options.value
})
const summary = computed(() => {
  const names = options.value.filter(o => picked.value.has(o.key)).map(o => o.name)
  return names.length ? names.join(', ') : 'Nowhere'
})

function reset() {
  picked.value = new Set(saved.value)
}

function toggle(key) {
  const next = new Set(picked.value)
  if (!next.delete(key)) next.add(key)
  picked.value = next
}

function onDocClick(e) {
  if (root.value && !root.value.contains(e.target)) close()
}

async function openMenu() {
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

onMounted(async () => {
  await ensureLoaded()
  reset()
})
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocClick))
watch(() => [props.kind, props.itemId], reset)
watch(dirty, d => emit('update:dirty', d), { immediate: true })

// Write the picks for the saved item (the id it was saved under)
async function commit(id) {
  if (!dirty.value && id === props.itemId) return
  await setMembership(props.kind, id, {
    global: picked.value.has(GLOBAL),
    spaceIds: [...picked.value].filter(k => k !== GLOBAL),
  })
}

defineExpose({ commit, dirty })
</script>

<template>
  <div ref="root" class="def-toggles">
    <span class="label">Default for</span>
    <div class="picker">
      <button
        type="button"
        class="trigger"
        :class="{ none: !picked.size }"
        :aria-expanded="open"
        :title="summary"
        @click="openMenu"
      >
        <span class="summary">{{ summary }}</span>
        <span class="caret">▾</span>
      </button>
      <div v-if="open" class="menu" role="listbox" aria-multiselectable="true">
        <input
          v-if="spaces.length >= SEARCH_FROM"
          ref="searchInput"
          v-model="query"
          type="search"
          class="search"
          placeholder="Search spaces"
          aria-label="Search spaces"
          @keydown.esc.stop="close"
        />
        <button
          v-for="o in shown"
          :key="o.key"
          type="button"
          class="option"
          role="option"
          :aria-selected="picked.has(o.key)"
          @click="toggle(o.key)"
        >
          <span class="tick">{{ picked.has(o.key) ? '✓' : '' }}</span>
          <span class="icon">{{ o.icon }}</span>
          <span class="name">{{ o.name }}</span>
        </button>
        <p v-if="!shown.length" class="empty">No spaces match</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.def-toggles {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  min-width: 0;
}

.label {
  flex-shrink: 0;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text2);
}

.picker {
  position: relative;
  min-width: 0;
  flex: 1;
}

.trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface2);
  color: var(--text);
  font-size: 0.82rem;
  cursor: pointer;
}

.trigger:hover {
  border-color: var(--text2);
}

.trigger.none {
  color: var(--text2);
}

.summary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.caret {
  flex-shrink: 0;
  font-size: 0.7rem;
  color: var(--text2);
}

.menu {
  position: absolute;
  z-index: 20;
  bottom: calc(100% + 4px); /* opens upwards: it sits at the foot of the editors */
  left: 0;
  width: min(300px, 100%);
  min-width: 220px;
  max-height: 280px;
  overflow-y: auto;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
}

.search {
  margin-bottom: 4px;
  padding: 6px 9px;
  border-radius: 7px;
  font-size: 0.82rem;
}

.option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: none;
  color: var(--text);
  text-align: left;
  font-size: 0.85rem;
  cursor: pointer;
}

.option:hover {
  background: var(--surface2);
}

.option[aria-selected='true'] {
  background: rgba(108, 92, 231, 0.16);
}

.tick {
  width: 12px;
  flex-shrink: 0;
  color: var(--accent2);
  font-weight: 700;
}

.icon {
  flex-shrink: 0;
}

.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty {
  font-size: 0.8rem;
  color: var(--text2);
  padding: 6px 8px;
}
</style>
