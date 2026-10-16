<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useChatDefaults } from '../../composables/useChatDefaults'
import { useDropdown } from '../../composables/useDropdown'
import { ALL_CHATS, defaultIcon } from '../../utils/defaults'

// "Default for": where the item being edited applies by default — all chats
// and/or any spaces. Picked ones are pills (✕ removes); ＋ opens a searchable
// dropdown of them all (click to tick or untick). Part of the editor's form: picks are kept here (`dirty` reports
// them) until the editor saves and calls `commit(id)` with the saved item's
// id, so they work for new items too.
const props = defineProps({
  kind: { type: String, required: true }, // 'character' | 'instruction' | 'instruction_group'
  itemId: { type: Number, default: null }, // null = not saved yet
})
const emit = defineEmits(['update:dirty'])

const GLOBAL = 'global'

const { spaces, membership, setMembership, ensureLoaded } = useChatDefaults()
const picked = ref(new Set()) // GLOBAL and/or space ids
const query = ref('')
const searchInput = ref(null)
const { open, root, toggle: openMenu, close } = useDropdown({ focus: searchInput, onOpen: () => (query.value = '') })

const saved = computed(() => {
  if (props.itemId == null) return new Set()
  const m = membership(props.kind, props.itemId)
  return new Set([...(m.global ? [GLOBAL] : []), ...m.spaceIds])
})
const dirty = computed(() => picked.value.size !== saved.value.size || [...picked.value].some(k => !saved.value.has(k)))

const options = computed(() => [
  { key: GLOBAL, icon: defaultIcon(ALL_CHATS), name: ALL_CHATS },
  ...spaces.value.map(s => ({ key: s.id, icon: defaultIcon(s.name), name: s.name })),
])
const shown = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? options.value.filter(o => o.name.toLowerCase().includes(q)) : options.value
})
const pills = computed(() => options.value.filter(o => picked.value.has(o.key)))

function reset() {
  picked.value = new Set(saved.value)
}

function toggle(key) {
  const next = new Set(picked.value)
  if (!next.delete(key)) next.add(key)
  picked.value = next
}

onMounted(async () => {
  await ensureLoaded()
  reset()
})
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
    <span v-for="o in pills" :key="o.key" class="pill" :title="o.name">
      <span class="pill-name">{{ o.icon }} {{ o.name }}</span>
      <button type="button" class="pill-x" :title="`Not a default for ${o.name}`" @click="toggle(o.key)">✕</button>
    </span>
    <div class="picker">
      <button
        type="button"
        class="add"
        :aria-expanded="open"
        :title="pills.length ? 'Add or remove' : 'Make it a default'"
        @click="openMenu"
      >
        {{ pills.length ? '＋' : '＋ Add' }}
      </button>
      <div v-if="open" class="menu" role="listbox" aria-multiselectable="true">
        <input
          ref="searchInput"
          v-model="query"
          type="search"
          class="search"
          placeholder="Search spaces"
          aria-label="Search spaces"
          @keydown.esc.stop="close"
          @keydown.enter.prevent="shown[0] && toggle(shown[0].key)"
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
/* The menu hangs off the whole row, so pills coming and going don't move it */
.def-toggles {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  min-width: 0;
}

.pill {
  display: inline-flex;
  align-items: center;
  max-width: 220px;
  gap: 2px;
  padding: 2px 3px 2px 10px;
  border: 1px solid var(--accent);
  border-radius: 999px;
  background: rgba(108, 92, 231, 0.18);
  font-size: 0.78rem;
}

.pill-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pill-x {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  font-size: 0.68rem;
  padding: 2px 5px;
  border-radius: 999px;
}

.pill-x:hover {
  background: var(--border);
  color: var(--text);
}

.add {
  padding: 3px 10px;
  border: 1px dashed var(--border);
  border-radius: 999px;
  background: none;
  color: var(--text2);
  font-size: 0.78rem;
  cursor: pointer;
}

.add:hover {
  color: var(--text);
  border-color: var(--text2);
}

.label {
  flex-shrink: 0;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text2);
}

.picker {
  display: contents;
}

.menu {
  position: absolute;
  z-index: 20;
  bottom: calc(100% + 4px); /* opens upwards: it sits at the foot of the editors */
  left: 0;
  width: min(280px, 100%);
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
