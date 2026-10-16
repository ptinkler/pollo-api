<script setup>
import { computed, ref } from 'vue'
import ConversationRow from './ConversationRow.vue'
import FoldHeading from './FoldHeading.vue'
import MoveChatDialog from './MoveChatDialog.vue'
import { useFolded } from '../../composables/useFolded'
import { dateGroups } from '../../composables/useChatList'

// The sidebar's chats: a Spaces section of collapsible space folders on top
// (like ChatGPT's Projects), then a Chats section of the loose/unfiled chats
// grouped by date (like Recents). Search replaces both with flat results.
// Chats move by dragging them onto a space or onto Chats, or with "Move to…".
// The sections grow with their chats; the sidebar around them scrolls.
const props = defineProps({
  list: { type: Object, required: true },
  spaces: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
})
const emit = defineEmits([
  'open',
  'rename',
  'remove',
  'new-in-space',
  'move',
  'space-settings', // a space, 'new' or 'global'
  'spaces-changed',
  'import',
])

const { isFolded, toggleFold } = useFolded()
const moving = ref(null) // the chat whose "Move to…" dialog is open
const dragged = ref(null) // the chat being dragged
const dropOver = ref(undefined) // the drop target under it: a space id, null (Chats) or undefined

const searching = computed(() => !!props.list.searchResults)

// Chats in each space (space list order), and the loose ones grouped by date
const spaceFolders = computed(() =>
  props.spaces.map(s => ({ space: s, items: props.list.conversations.filter(c => c.space_id === s.id) })),
)
const unfiledGroups = computed(() => dateGroups(props.list.conversations.filter(c => c.space_id == null)))

function moveTo(conv, spaceId) {
  if ((conv.space_id ?? null) !== spaceId) emit('move', { conv, spaceId })
}

// ── Dragging chats between spaces ──
function onDragStart(conv, e) {
  dragged.value = conv
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', conv.title) // Firefox won't drag without data
}

function onDragEnd() {
  dragged.value = null
  dropOver.value = undefined
}

function onDragOver(e, spaceId) {
  if (!dragged.value) return
  e.preventDefault()
  e.dataTransfer.dropEffect = (dragged.value.space_id ?? null) === spaceId ? 'none' : 'move'
  dropOver.value = spaceId
}

function onDragLeave(e, spaceId) {
  if (dropOver.value === spaceId && !e.currentTarget.contains(e.relatedTarget)) dropOver.value = undefined
}

function onDrop(spaceId) {
  const conv = dragged.value
  onDragEnd()
  if (conv) moveTo(conv, spaceId)
}

// What every chat row does (the same in search results, spaces and Chats)
const rowHandlers = {
  open: id => emit('open', id),
  pin: c => props.list.togglePin(c),
  'move-to': c => (moving.value = c),
  rename: c => emit('rename', c),
  remove: c => emit('remove', c),
  dragstart: onDragStart,
  dragend: onDragEnd,
}

const dropHandlers = spaceId => ({
  dragover: e => onDragOver(e, spaceId),
  dragleave: e => onDragLeave(e, spaceId),
  drop: e => {
    e.preventDefault()
    onDrop(spaceId)
  },
})
</script>

<template>
  <div class="conv-search">
    <input
      :value="list.search"
      type="search"
      placeholder="Search chats"
      aria-label="Search chats"
      @input="list.setSearch($event.target.value)"
    />
  </div>

  <!-- Search: flat results across every chat -->
  <div v-if="searching" class="conv-list">
    <ConversationRow
      v-for="c in list.searchResults"
      :key="c.id"
      :conv="c"
      :active="c.id === activeId"
      v-on="rowHandlers"
    />
    <p v-if="!list.searchResults.length" class="conv-empty">No chats match</p>
  </div>

  <template v-else>
    <!-- Spaces (collapsible folders) -->
    <FoldHeading id="spaces" class="section-heading" title="Spaces" :summary="spaces.length">
      <template #actions>
        <span class="heading-btns">
          <button class="mini-btn" title="Import chats from a ChatGPT export" @click="emit('import')">Import</button>
          <button class="mini-btn" title="New space" @click="emit('space-settings', 'new')">＋ New</button>
        </span>
      </template>
    </FoldHeading>
    <div v-show="!isFolded('spaces')" class="conv-list">
      <div
        v-for="f in spaceFolders"
        :key="f.space.id"
        class="drop-zone"
        :class="{ 'drop-over': dropOver === f.space.id && dragged?.space_id !== f.space.id }"
        v-on="dropHandlers(f.space.id)"
      >
        <div class="space-head">
          <button class="space-toggle" @click="toggleFold(`space:${f.space.id}`)">
            <span class="caret" :class="{ folded: isFolded(`space:${f.space.id}`) }">▾</span>
            <span class="folder">🗂</span>
            <span class="space-name">{{ f.space.name }}</span>
            <span class="space-count">{{ f.items.length }}</span>
          </button>
          <button class="space-btn" title="Space settings" @click="emit('space-settings', f.space)">⚙</button>
          <button class="space-add" title="New chat here" @click="emit('new-in-space', f.space.id)">＋</button>
        </div>
        <template v-if="!isFolded(`space:${f.space.id}`)">
          <ConversationRow
            v-for="c in f.items"
            :key="c.id"
            :conv="c"
            :active="c.id === activeId"
            :dragging="dragged?.id === c.id"
            nested
            draggable
            v-on="rowHandlers"
          />
          <p v-if="!f.items.length" class="space-empty">No chats yet. Drag one here.</p>
        </template>
      </div>
      <p v-if="!spaces.length" class="space-empty">No spaces yet. Use ＋ New to add one.</p>
    </div>

    <!-- Chats (loose / unfiled, by date) -->
    <div
      class="drop-zone"
      :class="{ 'drop-over': dropOver === null && dragged?.space_id != null }"
      v-on="dropHandlers(null)"
    >
      <FoldHeading
        id="chats"
        class="section-heading"
        title="Chats"
        :summary="unfiledGroups.reduce((n, g) => n + g.items.length, 0)"
      >
        <template #actions>
          <button class="mini-btn" title="Defaults for every new chat" @click="emit('space-settings', 'global')">
            ⚙
          </button>
        </template>
      </FoldHeading>
      <div v-show="!isFolded('chats')" class="conv-list">
        <template v-for="g in unfiledGroups" :key="g.label">
          <div class="conv-group">{{ g.label }}</div>
          <ConversationRow
            v-for="c in g.items"
            :key="c.id"
            :conv="c"
            :active="c.id === activeId"
            :dragging="dragged?.id === c.id"
            draggable
            v-on="rowHandlers"
          />
        </template>
        <p v-if="!unfiledGroups.length" class="conv-empty">No chats yet</p>
        <p v-if="list.more" class="conv-empty">Older chats aren't listed. Search to find them.</p>
      </div>
    </div>
  </template>

  <MoveChatDialog
    :conv="moving"
    :spaces="spaces"
    @close="moving = null"
    @move="moveTo(moving, $event)"
    @space-created="emit('spaces-changed')"
  />
</template>

<style scoped>
.section-heading {
  padding: 14px 14px 2px;
}

.conv-list {
  padding: 0 8px 4px;
}

/* A drop target while a chat is dragged over it */
.drop-zone {
  border-radius: 8px;
  transition:
    background 0.1s,
    box-shadow 0.1s;
}

.drop-zone.drop-over {
  background: rgba(108, 92, 231, 0.12);
  box-shadow: inset 0 0 0 1px rgba(108, 92, 231, 0.55);
}

.space-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text2);
  font-size: 0.85rem;
  padding: 2px 5px;
  border-radius: 4px;
  opacity: 0;
}

.space-head:hover .space-btn,
.space-btn:focus-visible {
  opacity: 1;
}

.space-btn:hover {
  background: var(--surface2);
  color: var(--text);
}

.space-head {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px 4px 1px;
}

.space-toggle {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text);
  font-size: 0.85rem;
  padding: 4px 4px;
  min-width: 0;
  text-align: left;
}

.space-toggle:hover {
  color: var(--text);
}

.caret {
  transition: transform 0.15s;
  font-size: 0.7rem;
  color: var(--text2);
}

.caret.folded {
  transform: rotate(-90deg);
}

.folder {
  font-size: 0.85rem;
}

.space-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.space-count {
  color: var(--text2);
  font-size: 0.78rem;
}

.space-add {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text2);
  font-size: 0.9rem;
  padding: 2px 6px;
  border-radius: 4px;
}

.space-add:hover {
  background: var(--surface2);
  color: var(--text);
}

.space-empty {
  font-size: 0.75rem;
  color: var(--text2);
  padding: 2px 10px 6px 26px;
  opacity: 0.7;
}

.heading-btns {
  display: flex;
  gap: 4px;
}

.mini-btn {
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 0.75rem;
}

.mini-btn:hover {
  background: var(--surface2);
  color: var(--text);
}

.conv-group {
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text2);
  opacity: 0.7;
  padding: 8px 10px 3px;
}

.conv-search {
  padding: 8px 12px 6px;
}

.conv-search input {
  width: 100%;
  padding: 6px 10px;
  font-size: 0.82rem;
  border-radius: 8px;
}

.conv-empty {
  padding: 12px;
  font-size: 0.8rem;
  color: var(--text2);
  text-align: center;
}
</style>
