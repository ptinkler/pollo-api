<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { characterAvatar } from '../../composables/useCharacters'

// Attached characters as chips, plus a menu to attach more. Editing and
// creating happen in CharacterEditor; this only emits 'edit' / 'create'.
const props = defineProps({
  modelValue: { type: Array, default: () => [] }, // attached character ids
  characters: { type: Array, default: () => [] }, // what can be attached
  allowCreate: { type: Boolean, default: true },
  createLabel: { type: String, default: '＋ New character' },
})
const emit = defineEmits(['update:modelValue', 'edit', 'create'])

const open = ref(false)
const root = ref(null)

const byId = computed(() => new Map(props.characters.map(c => [c.id, c])))
const attached = computed(() => props.modelValue.map(id => byId.value.get(id)).filter(Boolean))
const available = computed(() => props.characters.filter(c => !props.modelValue.includes(c.id)))

function attach(c) {
  emit('update:modelValue', [...props.modelValue, c.id])
  close()
}

function detach(c) {
  emit(
    'update:modelValue',
    props.modelValue.filter(id => id !== c.id),
  )
}

function onDocClick(e) {
  if (root.value && !root.value.contains(e.target)) close()
}

function toggle() {
  if (open.value) return close()
  open.value = true
  document.addEventListener('mousedown', onDocClick)
}

function close() {
  open.value = false
  document.removeEventListener('mousedown', onDocClick)
}

function create() {
  close()
  emit('create')
}

onBeforeUnmount(() => document.removeEventListener('mousedown', onDocClick))
</script>

<template>
  <div ref="root" class="char-picker">
    <div class="chips">
      <span
        v-for="c in attached"
        :key="c.id"
        class="chip"
        :class="{ adhoc: c.adhoc }"
        :title="(c.adhoc ? 'This chat only — ' : '') + (c.description || c.name)"
      >
        <button class="chip-main" @click="emit('edit', c)">
          <img v-if="characterAvatar(c)" :src="characterAvatar(c)" alt="" />
          <span v-else class="avatar-blank">👤</span>
          {{ c.name }}
        </button>
        <button class="chip-x" :title="`Detach ${c.name}`" @click="detach(c)">✕</button>
      </span>
      <button class="add" @click="toggle">{{ attached.length ? '＋' : '＋ Add character' }}</button>
    </div>

    <div v-if="open" class="menu">
      <button v-for="c in available" :key="c.id" class="item" @click="attach(c)">
        <img v-if="characterAvatar(c)" :src="characterAvatar(c)" alt="" />
        <span v-else class="avatar-blank">👤</span>
        <span class="item-name">{{ c.name }}</span>
        <span v-if="c.adhoc" class="tag">this chat</span>
      </button>
      <p v-if="!available.length" class="empty">{{ characters.length ? 'All attached' : 'No characters yet' }}</p>
      <button v-if="allowCreate" class="item create" @click="create">{{ createLabel }}</button>
    </div>
  </div>
</template>

<style scoped>
.char-picker {
  position: relative;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface2);
  font-size: 0.8rem;
  overflow: hidden;
}

.chip.adhoc {
  border-style: dashed;
}

.chip-main {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px 3px 3px;
  background: none;
  border: none;
  color: var(--text);
  cursor: pointer;
  font: inherit;
}

.chip img,
.item img,
.avatar-blank {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  display: inline-grid;
  place-items: center;
  font-size: 0.7rem;
  background: var(--surface);
}

.chip-x {
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  padding: 0 8px 0 2px;
  font-size: 0.7rem;
}

.chip-x:hover {
  color: var(--text);
}

.add {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px dashed var(--border);
  background: none;
  color: var(--text2);
  cursor: pointer;
  font-size: 0.8rem;
}

.add:hover {
  color: var(--text);
  border-color: var(--accent);
}

.menu {
  position: absolute;
  z-index: 50;
  top: calc(100% + 4px);
  left: 0;
  min-width: 220px;
  max-height: 280px;
  overflow-y: auto;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}

.item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  border-radius: 8px;
  background: none;
  color: var(--text);
  text-align: left;
  cursor: pointer;
  font-size: 0.85rem;
}

.item:hover {
  background: var(--surface2);
}

.item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item.create {
  color: var(--accent2);
  font-weight: 600;
  border-top: 1px solid var(--border);
  border-radius: 0 0 8px 8px;
}

.tag {
  font-size: 0.65rem;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--surface2);
  color: var(--yellow);
}

.empty {
  font-size: 0.8rem;
  color: var(--text2);
  padding: 6px 8px;
}
</style>
