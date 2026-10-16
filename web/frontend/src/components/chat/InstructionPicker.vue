<script setup>
import { ref, computed } from 'vue'
import { instructionColor } from '../../utils/format'
import { defaultIcon as fromIcon, defaultTitle as fromTitle } from '../../utils/defaults'
import { useDropdown } from '../../composables/useDropdown'

// Attached instruction groups and snippets as chips, plus a menu to attach
// more. Editing and creating happen in InstructionEditor (and the Instructions page); this
// only attaches/detaches, and emits 'edit' ({ kind, id }: a chip was
// clicked) or 'manage' to open that dialog.
const props = defineProps({
  instructions: { type: Array, default: () => [] }, // all saved snippets
  groups: { type: Array, default: () => [] }, // all saved groups
  snippetIds: { type: Array, default: () => [] }, // attached snippet ids
  groupIds: { type: Array, default: () => [] }, // attached group ids
  manageable: { type: Boolean, default: true }, // show the "Manage & create…" item
  // Attached by the chat's defaults: [{ id, from }] — shown, but changed in the defaults, not here
  inheritedSnippets: { type: Array, default: () => [] },
  inheritedGroups: { type: Array, default: () => [] },
  // Defaults switched off in this chat: [{ id, from }] — offered in the menu to switch back on
  hiddenSnippets: { type: Array, default: () => [] },
  hiddenGroups: { type: Array, default: () => [] },
})
// 'hide' / 'unhide': { kind, id } — a default switched off / on in this chat only
const emit = defineEmits(['update:snippetIds', 'update:groupIds', 'manage', 'edit', 'hide', 'unhide'])

const SEARCH_FROM = 8 // the menu gets a search box once there's this much to pick from

const query = ref('')
const searchInput = ref(null)
const { open, root, toggle, close } = useDropdown({ focus: searchInput, onOpen: () => (query.value = '') })

const snippetById = computed(() => new Map(props.instructions.map(s => [s.id, s])))
const groupById = computed(() => new Map(props.groups.map(g => [g.id, g])))
const inheritedGroupIds = computed(() => [...props.inheritedGroups, ...props.hiddenGroups].map(x => x.id))
const inheritedSnippetIds = computed(() => [...props.inheritedSnippets, ...props.hiddenSnippets].map(x => x.id))
const fromDefaults = (list, byId) =>
  list.map(x => byId.get(x.id) && { ...byId.get(x.id), from: x.from }).filter(Boolean)
const defaultGroups = computed(() => fromDefaults(props.inheritedGroups, groupById.value))
const defaultSnippets = computed(() => fromDefaults(props.inheritedSnippets, snippetById.value))
const hiddenGroupItems = computed(() => fromDefaults(props.hiddenGroups, groupById.value).filter(matches))
const hiddenSnippetItems = computed(() => fromDefaults(props.hiddenSnippets, snippetById.value).filter(matches))
const attachedGroups = computed(() =>
  props.groupIds
    .filter(id => !inheritedGroupIds.value.includes(id))
    .map(id => groupById.value.get(id))
    .filter(Boolean),
)
const attachedSnippets = computed(() =>
  props.snippetIds
    .filter(id => !inheritedSnippetIds.value.includes(id))
    .map(id => snippetById.value.get(id))
    .filter(Boolean),
)
const anyAttached = computed(
  () =>
    defaultGroups.value.length ||
    defaultSnippets.value.length ||
    attachedGroups.value.length ||
    attachedSnippets.value.length,
)
const matches = item => item.name.toLowerCase().includes(query.value.trim().toLowerCase())
const unattachedGroups = computed(() =>
  props.groups.filter(g => !props.groupIds.includes(g.id) && !inheritedGroupIds.value.includes(g.id)),
)
const unattachedSnippets = computed(() =>
  props.instructions.filter(s => !props.snippetIds.includes(s.id) && !inheritedSnippetIds.value.includes(s.id)),
)
const searchable = computed(() => unattachedGroups.value.length + unattachedSnippets.value.length >= SEARCH_FROM)
const availableGroups = computed(() => unattachedGroups.value.filter(matches))
const availableSnippets = computed(() => unattachedSnippets.value.filter(matches))
const nothingToAdd = computed(
  () =>
    !availableGroups.value.length &&
    !availableSnippets.value.length &&
    !hiddenGroupItems.value.length &&
    !hiddenSnippetItems.value.length,
)

function unhide(kind, item) {
  emit('unhide', { kind, id: item.id })
  close()
}

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

function manage() {
  close()
  emit('manage')
}
</script>

<template>
  <div ref="root" class="ins-picker">
    <div class="chips">
      <span
        v-for="g in defaultGroups"
        :key="`dg${g.id}`"
        class="chip group inherited"
        :title="`${g.name} · ${fromTitle(g.from)}`"
      >
        <button class="chip-main" @click="emit('edit', { kind: 'group', id: g.id })">
          <span class="chip-name">📦 {{ g.name }}</span>
        </button>
        <span class="chip-src">{{ fromIcon(g.from) }}</span>
        <button
          class="chip-x"
          :title="`Hide ${g.name} in this chat`"
          @click="emit('hide', { kind: 'group', id: g.id })"
        >
          ✕
        </button>
      </span>
      <span
        v-for="s in defaultSnippets"
        :key="`ds${s.id}`"
        class="chip inherited"
        :title="`${s.name} · ${fromTitle(s.from)}`"
      >
        <button class="chip-main" @click="emit('edit', { kind: 'snippet', id: s.id })">
          <span class="dot" :style="{ background: instructionColor(s.name) }"></span>
          <span class="chip-name">{{ s.name }}</span>
        </button>
        <span class="chip-src">{{ fromIcon(s.from) }}</span>
        <button
          class="chip-x"
          :title="`Hide ${s.name} in this chat`"
          @click="emit('hide', { kind: 'snippet', id: s.id })"
        >
          ✕
        </button>
      </span>
      <span v-for="g in attachedGroups" :key="`g${g.id}`" class="chip group" :title="`${g.name} · ${groupTitle(g)}`">
        <button class="chip-main" @click="emit('edit', { kind: 'group', id: g.id })">
          <span class="chip-name">📦 {{ g.name }}</span>
        </button>
        <button class="chip-x" :title="`Detach ${g.name}`" @click="detachGroup(g)">✕</button>
      </span>
      <span v-for="s in attachedSnippets" :key="`s${s.id}`" class="chip" :title="s.name">
        <button class="chip-main" @click="emit('edit', { kind: 'snippet', id: s.id })">
          <span class="dot" :style="{ background: instructionColor(s.name) }"></span>
          <span class="chip-name">{{ s.name }}</span>
        </button>
        <button class="chip-x" :title="`Detach ${s.name}`" @click="detachSnippet(s)">✕</button>
      </span>
      <button class="add" @click="toggle">
        {{ anyAttached ? '＋' : '＋ Add instructions' }}
      </button>
    </div>

    <div v-if="open" class="menu">
      <input
        v-if="searchable"
        ref="searchInput"
        v-model="query"
        type="search"
        class="menu-search"
        placeholder="Search"
        aria-label="Search instructions"
        @keydown.esc="close"
      />
      <p v-if="availableGroups.length" class="menu-head">Groups</p>
      <button v-for="g in availableGroups" :key="`g${g.id}`" class="item" @click="attachGroup(g)">
        <span class="item-name">📦 {{ g.name }}</span>
        <span class="tag">{{ g.snippet_ids?.length || 0 }}</span>
      </button>
      <p v-if="availableSnippets.length" class="menu-head">Snippets</p>
      <button v-for="s in availableSnippets" :key="`s${s.id}`" class="item" :title="s.name" @click="attachSnippet(s)">
        <span class="dot" :style="{ background: instructionColor(s.name) }"></span>
        <span class="item-name">{{ s.name }}</span>
      </button>
      <template v-if="hiddenGroupItems.length || hiddenSnippetItems.length">
        <p class="menu-head">Hidden in this chat</p>
        <button
          v-for="g in hiddenGroupItems"
          :key="`hg${g.id}`"
          class="item hidden-default"
          :title="`Use ${g.name} here again (${fromTitle(g.from).toLowerCase()})`"
          @click="unhide('group', g)"
        >
          <span class="item-name">📦 {{ g.name }}</span>
          <span class="tag">{{ fromIcon(g.from) }}</span>
        </button>
        <button
          v-for="s in hiddenSnippetItems"
          :key="`hs${s.id}`"
          class="item hidden-default"
          :title="`Use ${s.name} here again (${fromTitle(s.from).toLowerCase()})`"
          @click="unhide('snippet', s)"
        >
          <span class="dot" :style="{ background: instructionColor(s.name) }"></span>
          <span class="item-name">{{ s.name }}</span>
          <span class="tag">{{ fromIcon(s.from) }}</span>
        </button>
      </template>
      <p v-if="nothingToAdd" class="empty">
        {{
          query.trim() ? 'Nothing matches' : instructions.length || groups.length ? 'All attached' : 'None saved yet'
        }}
      </p>
      <button v-if="manageable" class="item create" @click="manage">⚙ All instructions…</button>
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
  max-width: 170px; /* long names are cut short; the full name is in the tooltip */
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface2);
  font-size: 0.8rem;
  overflow: hidden;
}

.chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Attached by the chat's defaults: no ✕ — the icon says where from */
.chip.inherited {
  background: transparent;
}

.chip-src {
  flex-shrink: 0;
  padding: 0 0 0 2px;
  font-size: 0.7rem;
  opacity: 0.75;
}

.item.hidden-default .item-name {
  opacity: 0.6;
  text-decoration: line-through;
}

.dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.chip.group {
  border-color: var(--accent2);
}

.chip-main {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
  padding: 3px 4px 3px 10px;
  color: var(--text);
  background: none;
  border: none;
  font: inherit;
  cursor: pointer;
}

.chip-main:hover {
  text-decoration: underline;
}

.menu-search {
  width: 100%;
  margin-bottom: 4px;
  padding: 6px 9px;
  border-radius: 7px;
  font-size: 0.82rem;
}

.chip-x {
  flex-shrink: 0;
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
