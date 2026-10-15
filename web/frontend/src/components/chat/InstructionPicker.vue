<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'

// Attached instruction groups and snippets as chips, plus a menu to attach
// more. Editing, creating and grouping happen in InstructionsDialog; this
// only attaches/detaches and emits 'manage' to open that dialog.
const props = defineProps({
  instructions: { type: Array, default: () => [] }, // all saved snippets
  groups: { type: Array, default: () => [] }, // all saved groups
  snippetIds: { type: Array, default: () => [] }, // attached snippet ids
  groupIds: { type: Array, default: () => [] }, // attached group ids
  manageable: { type: Boolean, default: true }, // show the "Manage & create…" item
})
const emit = defineEmits(['update:snippetIds', 'update:groupIds', 'manage'])

const open = ref(false)
const root = ref(null)

const snippetById = computed(() => new Map(props.instructions.map(s => [s.id, s])))
const groupById = computed(() => new Map(props.groups.map(g => [g.id, g])))
const attachedGroups = computed(() => props.groupIds.map(id => groupById.value.get(id)).filter(Boolean))
const attachedSnippets = computed(() => props.snippetIds.map(id => snippetById.value.get(id)).filter(Boolean))
const availableGroups = computed(() => props.groups.filter(g => !props.groupIds.includes(g.id)))
const availableSnippets = computed(() => props.instructions.filter(s => !props.snippetIds.includes(s.id)))
const nothingToAdd = computed(() => !availableGroups.value.length && !availableSnippets.value.length)

function groupTitle(g) {
  const n = g.snippet_ids?.length || 0
  return `Group — ${n} snippet${n === 1 ? '' : 's'}`
}

function attachGroup(g) {
  emit('update:groupIds', [...props.groupIds, g.id])
  close()
}

function detachGroup(g) {
  emit(
    'update:groupIds',
    props.groupIds.filter(id => id !== g.id),
  )
}

function attachSnippet(s) {
  emit('update:snippetIds', [...props.snippetIds, s.id])
  close()
}

function detachSnippet(s) {
  emit(
    'update:snippetIds',
    props.snippetIds.filter(id => id !== s.id),
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

function manage() {
  close()
  emit('manage')
}

onBeforeUnmount(() => document.removeEventListener('mousedown', onDocClick))
</script>

<template>
  <div ref="root" class="ins-picker">
    <div class="chips">
      <span v-for="g in attachedGroups" :key="`g${g.id}`" class="chip group" :title="groupTitle(g)">
        <span class="chip-main">📦 {{ g.name }}</span>
        <button class="chip-x" :title="`Detach ${g.name}`" @click="detachGroup(g)">✕</button>
      </span>
      <span v-for="s in attachedSnippets" :key="`s${s.id}`" class="chip" :title="s.content || s.name">
        <span class="chip-main">{{ s.name }}</span>
        <button class="chip-x" :title="`Detach ${s.name}`" @click="detachSnippet(s)">✕</button>
      </span>
      <button class="add" @click="toggle">
        {{ attachedGroups.length || attachedSnippets.length ? '＋' : '＋ Add instructions' }}
      </button>
    </div>

    <div v-if="open" class="menu">
      <p v-if="availableGroups.length" class="menu-head">Groups</p>
      <button v-for="g in availableGroups" :key="`g${g.id}`" class="item" @click="attachGroup(g)">
        <span class="item-name">📦 {{ g.name }}</span>
        <span class="tag">{{ g.snippet_ids?.length || 0 }}</span>
      </button>
      <p v-if="availableSnippets.length" class="menu-head">Snippets</p>
      <button v-for="s in availableSnippets" :key="`s${s.id}`" class="item" @click="attachSnippet(s)">
        <span class="item-name">{{ s.name }}</span>
      </button>
      <p v-if="nothingToAdd" class="empty">
        {{ instructions.length || groups.length ? 'All attached' : 'None saved yet' }}
      </p>
      <button v-if="manageable" class="item create" @click="manage">⚙ Manage &amp; create…</button>
    </div>
  </div>
</template>

<style scoped>
.ins-picker {
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

.chip.group {
  border-color: var(--accent2);
}

.chip-main {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 4px 3px 10px;
  color: var(--text);
}

.chip-x {
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  padding: 0 8px 0 4px;
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
  max-height: 300px;
  overflow-y: auto;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}

.menu-head {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text2);
  padding: 6px 8px 2px;
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
  margin-top: 4px;
}

.tag {
  font-size: 0.65rem;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--surface2);
  color: var(--accent2);
}

.empty {
  font-size: 0.8rem;
  color: var(--text2);
  padding: 6px 8px;
}
</style>
