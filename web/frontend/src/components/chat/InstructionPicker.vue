<script setup>
import { ref, computed } from 'vue'
import { instructionColor } from '../../utils/format'
import { defaultIcon as fromIcon, defaultTitle as fromTitle } from '../../utils/defaults'
import PickDialog from '../PickDialog.vue'

// Attached instruction groups and snippets as chips, plus a dialog to pick
// more (names aren't unique, so each card shows a preview of its text). Editing and creating happen in InstructionEditor (and the Instructions page); this
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
  // Attached but paused in this chat (own or inherited): shown dimmed, not sent
  pausedSnippets: { type: Array, default: () => [] },
  pausedGroups: { type: Array, default: () => [] },
})
// 'hide' / 'unhide': { kind, id } — a default switched off / on in this chat only
// 'pause' / 'resume': { kind, id } — an attachment paused / resumed in this chat
const emit = defineEmits([
  'update:snippetIds',
  'update:groupIds',
  'manage',
  'edit',
  'hide',
  'unhide',
  'pause',
  'resume',
])

const open = ref(false)
const close = () => (open.value = false)
const toggle = () => (open.value = !open.value)

const snippetById = computed(() => new Map(props.instructions.map(s => [s.id, s])))
const groupById = computed(() => new Map(props.groups.map(g => [g.id, g])))
const inheritedGroupIds = computed(() => [...props.inheritedGroups, ...props.hiddenGroups].map(x => x.id))
const inheritedSnippetIds = computed(() => [...props.inheritedSnippets, ...props.hiddenSnippets].map(x => x.id))
const fromDefaults = (list, byId) =>
  list.map(x => byId.get(x.id) && { ...byId.get(x.id), from: x.from }).filter(Boolean)
const defaultGroups = computed(() => fromDefaults(props.inheritedGroups, groupById.value))
const defaultSnippets = computed(() => fromDefaults(props.inheritedSnippets, snippetById.value))
const hiddenGroupItems = computed(() => fromDefaults(props.hiddenGroups, groupById.value))
const hiddenSnippetItems = computed(() => fromDefaults(props.hiddenSnippets, snippetById.value))
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
const unattachedGroups = computed(() =>
  props.groups.filter(g => !props.groupIds.includes(g.id) && !inheritedGroupIds.value.includes(g.id)),
)
const unattachedSnippets = computed(() =>
  props.instructions.filter(s => !props.snippetIds.includes(s.id) && !inheritedSnippetIds.value.includes(s.id)),
)
function unhide(kind, item) {
  emit('unhide', { kind, id: item.id })
}

function groupTitle(g) {
  const n = g.snippet_ids?.length || 0
  return `Group — ${n} snippet${n === 1 ? '' : 's'}`
}

function attachGroup(g) {
  emit('update:groupIds', [...props.groupIds, g.id])
}

function detachGroup(g) {
  emit(
    'update:groupIds',
    props.groupIds.filter(id => id !== g.id),
  )
}

function attachSnippet(s) {
  emit('update:snippetIds', [...props.snippetIds, s.id])
}

function detachSnippet(s) {
  emit(
    'update:snippetIds',
    props.snippetIds.filter(id => id !== s.id),
  )
}

const isPaused = (kind, id) => (kind === 'group' ? props.pausedGroups : props.pausedSnippets).includes(id)
function togglePause(kind, item) {
  emit(isPaused(kind, item.id) ? 'resume' : 'pause', { kind, id: item.id })
}

// Open the editor for a new snippet / group (same modal as editing one)
function create(kind) {
  close()
  emit('edit', { kind, id: null })
}

function manage() {
  close()
  emit('manage')
}

// Every group and snippet as a card: in use (own, or from the defaults) or not
const preview = text => (text || '').replace(/\s+/g, ' ').trim().slice(0, 140)
const groupCard = (g, on, from) => ({
  key: `g${from ? 'd' : ''}${g.id}`,
  id: g.id,
  type: 'group',
  section: 'Groups',
  icon: '📦',
  name: g.name,
  sub: groupTitle(g),
  from: from ? `${fromIcon(from)} ${fromTitle(from)}` : undefined,
  on,
  kind: from ? 'default' : 'own',
})
const snippetCard = (sn, on, from) => ({
  key: `s${from ? 'd' : ''}${sn.id}`,
  id: sn.id,
  type: 'snippet',
  section: 'Snippets',
  dot: instructionColor(sn.name),
  name: sn.name,
  sub: preview(sn.content),
  from: from ? `${fromIcon(from)} ${fromTitle(from)}` : undefined,
  on,
  kind: from ? 'default' : 'own',
})
const cards = computed(() => [
  ...attachedGroups.value.map(g => groupCard(g, true)),
  ...defaultGroups.value.map(g => groupCard(g, true, g.from)),
  ...hiddenGroupItems.value.map(g => groupCard(g, false, g.from)),
  ...unattachedGroups.value.map(g => groupCard(g, false)),
  ...attachedSnippets.value.map(sn => snippetCard(sn, true)),
  ...defaultSnippets.value.map(sn => snippetCard(sn, true, sn.from)),
  ...hiddenSnippetItems.value.map(sn => snippetCard(sn, false, sn.from)),
  ...unattachedSnippets.value.map(sn => snippetCard(sn, false)),
])
function onToggle(item) {
  const byId = item.type === 'group' ? groupById.value : snippetById.value
  const it = byId.get(item.id)
  if (!it) return
  if (item.kind === 'default') {
    return item.on ? emit('hide', { kind: item.type, id: it.id }) : unhide(item.type, it)
  }
  if (item.type === 'group') return item.on ? detachGroup(it) : attachGroup(it)
  return item.on ? detachSnippet(it) : attachSnippet(it)
}
</script>

<template>
  <div class="ins-picker">
    <div class="chips">
      <span
        v-for="g in defaultGroups"
        :key="`dg${g.id}`"
        class="chip group inherited"
        :class="{ paused: isPaused('group', g.id) }"
        :title="`${g.name} · ${fromTitle(g.from)}`"
      >
        <button
          class="chip-pause"
          :title="isPaused('group', g.id) ? `Resume ${g.name}` : `Pause ${g.name} for now`"
          @click="togglePause('group', g)"
        >
          {{ isPaused('group', g.id) ? '▶' : '⏸' }}
        </button>
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
        :class="{ paused: isPaused('snippet', s.id) }"
        :title="`${s.name} · ${fromTitle(s.from)}`"
      >
        <button
          class="chip-pause"
          :title="isPaused('snippet', s.id) ? `Resume ${s.name}` : `Pause ${s.name} for now`"
          @click="togglePause('snippet', s)"
        >
          {{ isPaused('snippet', s.id) ? '▶' : '⏸' }}
        </button>
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
      <span
        v-for="g in attachedGroups"
        :key="`g${g.id}`"
        class="chip group"
        :class="{ paused: isPaused('group', g.id) }"
        :title="`${g.name} · ${groupTitle(g)}`"
      >
        <button
          class="chip-pause"
          :title="isPaused('group', g.id) ? `Resume ${g.name}` : `Pause ${g.name} for now`"
          @click="togglePause('group', g)"
        >
          {{ isPaused('group', g.id) ? '▶' : '⏸' }}
        </button>
        <button class="chip-main" @click="emit('edit', { kind: 'group', id: g.id })">
          <span class="chip-name">📦 {{ g.name }}</span>
        </button>
        <button class="chip-x" :title="`Detach ${g.name}`" @click="detachGroup(g)">✕</button>
      </span>
      <span
        v-for="s in attachedSnippets"
        :key="`s${s.id}`"
        class="chip"
        :class="{ paused: isPaused('snippet', s.id) }"
        :title="s.name"
      >
        <button
          class="chip-pause"
          :title="isPaused('snippet', s.id) ? `Resume ${s.name}` : `Pause ${s.name} for now`"
          @click="togglePause('snippet', s)"
        >
          {{ isPaused('snippet', s.id) ? '▶' : '⏸' }}
        </button>
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

    <PickDialog
      :open="open"
      title="Instructions"
      :items="cards"
      empty="No instructions saved yet"
      search-placeholder="Search instructions"
      @toggle="onToggle"
      @close="close"
    >
      <template v-if="manageable" #actions>
        <button type="button" class="btn btn-secondary" @click="create('snippet')">+ New snippet</button>
        <button type="button" class="btn btn-secondary" @click="create('group')">+ New group</button>
        <button type="button" class="btn btn-secondary" @click="manage">All instructions</button>
      </template>
    </PickDialog>
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

/* Paused: still attached, but dimmed and struck through — not sent for now */
.chip.paused .chip-main {
  opacity: 0.5;
}

.chip.paused .chip-name {
  text-decoration: line-through;
}

.chip-pause {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  padding: 0 2px 0 7px;
  font-size: 0.7rem;
  line-height: 1;
}

.chip-pause:hover {
  color: var(--text);
}

/* The icon already carries the left padding of the chip */
.chip-pause + .chip-main {
  padding-left: 4px;
}

.chip-src {
  flex-shrink: 0;
  padding: 0 0 0 2px;
  font-size: 0.7rem;
  opacity: 0.75;
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

/* Actions at the foot of the menu: quiet rows under a divider */
.menu-foot {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px solid var(--border);
}
</style>
