<script setup>
import FoldHeading from './FoldHeading.vue'
import { useFolded } from '../../composables/useFolded'

// The sidebar's chat list (state and actions from useChatList): search,
// pinned chats, then the rest grouped by date
defineProps({
  list: { type: Object, required: true },
  activeId: { type: String, default: null },
})
const emit = defineEmits(['open', 'rename', 'remove'])

const { isFolded } = useFolded()
</script>

<template>
  <FoldHeading id="chats" class="chats-heading" title="Chats" :summary="list.conversations.length" />
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
          <button title="Rename" @click="emit('rename', c)">✎</button>
          <button title="Delete" @click="emit('remove', c)">🗑</button>
        </span>
      </div>
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

.conv-list {
  flex: 1 0 140px;
  min-height: 140px;
  overflow-y: auto;
  padding: 0 8px 8px;
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

.conv-empty {
  padding: 12px;
  font-size: 0.8rem;
  color: var(--text2);
  text-align: center;
}
</style>
