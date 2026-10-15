<script setup>
import { computed, ref } from 'vue'
import FoldHeading from './FoldHeading.vue'
import { useFolded } from '../../composables/useFolded'

// The sidebar's chat list (state and actions from useChatList): search, then
// chats grouped by space (collapsible) when spaces exist, else by date.
const props = defineProps({
  list: { type: Object, required: true },
  spaces: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
})
const emit = defineEmits(['open', 'rename', 'remove', 'new-in-space', 'move', 'manage-spaces'])

const { isFolded, toggleFold } = useFolded()
const moveMenuFor = ref(null) // conversation id whose "move" menu is open

// Chats grouped by space (space first in list order, then Unfiled), or null to
// fall back to the date groups when there are no spaces / while searching.
const spaceSections = computed(() => {
  if (props.list.searchResults || !props.spaces.length) return null
  const byId = new Map(props.spaces.map(s => [s.id, { key: `space:${s.id}`, space: s, items: [] }]))
  const unfiled = { key: 'space:unfiled', space: null, items: [] }
  for (const c of props.list.conversations) {
    const bucket = (c.space_id != null && byId.get(c.space_id)) || unfiled
    bucket.items.push(c)
  }
  const sections = props.spaces.map(s => byId.get(s.id))
  if (unfiled.items.length) sections.push(unfiled)
  return sections
})

function toggleMove(id) {
  moveMenuFor.value = moveMenuFor.value === id ? null : id
}

function move(conv, spaceId) {
  moveMenuFor.value = null
  if ((conv.space_id ?? null) !== spaceId) emit('move', { conv, spaceId })
}
</script>

<template>
  <FoldHeading id="chats" class="chats-heading" title="Chats" :summary="list.conversations.length">
    <template #actions>
      <button class="mini-btn" title="Create and edit spaces" @click="emit('manage-spaces')">Spaces</button>
    </template>
  </FoldHeading>
  <div v-show="!isFolded('chats')" class="conv-search">
    <input
      :value="list.search"
      type="search"
      placeholder="Search chats"
      aria-label="Search chats"
      @input="list.setSearch($event.target.value)"
    />
  </div>
  <div v-show="!isFolded('chats')" class="conv-list">
    <!-- Grouped by space -->
    <template v-if="spaceSections">
      <template v-for="s in spaceSections" :key="s.key">
        <div class="space-head">
          <button class="space-toggle" @click="toggleFold(s.key)">
            <span class="caret" :class="{ folded: isFolded(s.key) }">▾</span>
            <span class="space-name">{{ s.space ? s.space.name : 'Unfiled' }}</span>
            <span class="space-count">{{ s.items.length }}</span>
          </button>
          <button class="space-add" title="New chat here" @click="emit('new-in-space', s.space?.id ?? null)">＋</button>
        </div>
        <template v-if="!isFolded(s.key)">
          <div
            v-for="c in s.items"
            :key="c.id"
            class="conv-item"
            :class="{ active: c.id === activeId }"
            @click="emit('open', c.id)"
          >
            <span class="conv-text">
              <span class="conv-title"
                ><span v-if="c.forked_from_id" class="conv-fork" title="Branched off another chat">⑂ </span
                >{{ c.title }}</span
              >
              <span v-if="c.snippet" class="conv-snippet">{{ c.snippet }}</span>
            </span>
            <span class="conv-actions" @click.stop>
              <button
                :class="{ on: c.pinned }"
                :title="c.pinned ? 'Unpin' : 'Pin to the top'"
                @click="list.togglePin(c)"
              >
                📌
              </button>
              <span class="move-wrap">
                <button title="Move to space" @click="toggleMove(c.id)">📁</button>
                <div v-if="moveMenuFor === c.id" class="move-menu">
                  <button v-for="sp in spaces" :key="sp.id" :disabled="sp.id === c.space_id" @click="move(c, sp.id)">
                    {{ sp.name }}
                  </button>
                  <button :disabled="c.space_id == null" @click="move(c, null)">Unfiled</button>
                </div>
              </span>
              <button title="Rename" @click="emit('rename', c)">✎</button>
              <button title="Delete" @click="emit('remove', c)">🗑</button>
            </span>
          </div>
          <p v-if="!s.items.length" class="space-empty">No chats yet</p>
        </template>
      </template>
    </template>

    <!-- No spaces (or searching): the original date groups / flat results -->
    <template v-else>
      <template v-for="g in list.groups" :key="g.label || 'results'">
        <div v-if="g.label" class="conv-group">{{ g.label }}</div>
        <div
          v-for="c in g.items"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === activeId }"
          @click="emit('open', c.id)"
        >
          <span class="conv-text">
            <span class="conv-title"
              ><span v-if="c.forked_from_id" class="conv-fork" title="Branched off another chat">⑂ </span
              >{{ c.title }}</span
            >
            <span v-if="c.snippet" class="conv-snippet">{{ c.snippet }}</span>
          </span>
          <span class="conv-actions" @click.stop>
            <button :class="{ on: c.pinned }" :title="c.pinned ? 'Unpin' : 'Pin to the top'" @click="list.togglePin(c)">
              📌
            </button>
            <span v-if="spaces.length" class="move-wrap">
              <button title="Move to space" @click="toggleMove(c.id)">📁</button>
              <div v-if="moveMenuFor === c.id" class="move-menu">
                <button v-for="sp in spaces" :key="sp.id" @click="move(c, sp.id)">{{ sp.name }}</button>
              </div>
            </span>
            <button title="Rename" @click="emit('rename', c)">✎</button>
            <button title="Delete" @click="emit('remove', c)">🗑</button>
          </span>
        </div>
      </template>
    </template>

    <p v-if="list.searchResults && !list.searchResults.length" class="conv-empty">No chats match</p>
    <p v-else-if="!list.searchResults && !list.conversations.length" class="conv-empty">No chats yet</p>
    <p v-if="!list.searchResults && list.more" class="conv-empty">Older chats aren't listed. Search to find them.</p>
  </div>
</template>

<style scoped>
.chats-heading {
  padding: 16px 14px 4px;
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

.conv-list {
  flex: 1 0 140px;
  min-height: 140px;
  overflow-y: auto;
  padding: 0 8px 8px;
}

.space-head {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 8px 6px 2px;
}

.space-toggle {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text2);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 4px;
  min-width: 0;
}

.space-toggle:hover {
  color: var(--text);
}

.caret {
  transition: transform 0.15s;
  font-size: 0.7rem;
}

.caret.folded {
  transform: rotate(-90deg);
}

.space-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.space-count {
  opacity: 0.6;
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
  padding: 2px 16px 6px;
  opacity: 0.7;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text2);
}

.conv-item:hover {
  background: var(--surface2);
  color: var(--text);
}

.conv-item.active {
  background: rgba(108, 92, 231, 0.18);
  color: var(--text);
}

.conv-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.conv-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-fork {
  color: var(--accent);
}

.conv-snippet {
  font-size: 0.72rem;
  color: var(--text2);
  opacity: 0.8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-group {
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text2);
  opacity: 0.7;
  padding: 10px 10px 3px;
}

.conv-search {
  padding: 2px 12px 6px;
}

.conv-search input {
  width: 100%;
  padding: 6px 10px;
  font-size: 0.82rem;
  border-radius: 8px;
}

.conv-actions {
  display: none;
  gap: 2px;
}

.conv-item:hover .conv-actions {
  display: flex;
}

.conv-actions button {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.8rem;
  padding: 2px 4px;
  border-radius: 4px;
  color: var(--text2);
}

.conv-actions button:hover {
  background: var(--border);
}

.conv-actions button:not(.on):first-child {
  opacity: 0.5;
}

.conv-item:has(.conv-actions .on) .conv-actions {
  display: flex;
}

.conv-item:has(.conv-actions .on) .conv-actions button:not(.on) {
  display: none;
}

.conv-item:hover:has(.conv-actions .on) .conv-actions button:not(.on) {
  display: inline-block;
}

.move-wrap {
  position: relative;
  display: inline-flex;
}

.move-menu {
  position: absolute;
  z-index: 60;
  top: calc(100% + 2px);
  right: 0;
  min-width: 140px;
  max-height: 220px;
  overflow-y: auto;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.move-menu button {
  text-align: left;
  padding: 5px 8px;
  font-size: 0.8rem;
  border-radius: 6px;
  color: var(--text);
}

.move-menu button:disabled {
  opacity: 0.4;
  cursor: default;
}

.conv-empty {
  padding: 12px;
  font-size: 0.8rem;
  color: var(--text2);
  text-align: center;
}
</style>
