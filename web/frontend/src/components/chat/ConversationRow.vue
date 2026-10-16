<script setup>
// One chat in the sidebar: its title (⑂ when branched off another chat, and
// the matching text in search results), and its actions on hover. Draggable
// onto a space or Chats when `draggable`.
defineProps({
  conv: { type: Object, required: true },
  active: { type: Boolean, default: false },
  nested: { type: Boolean, default: false }, // inside a space folder
  draggable: { type: Boolean, default: false },
  dragging: { type: Boolean, default: false },
})
// open: the chat's id; dragstart: (chat, event); the rest: the chat
const emit = defineEmits(['open', 'pin', 'move-to', 'rename', 'remove', 'dragstart', 'dragend'])
</script>

<template>
  <div
    class="conv-item"
    :class="{ active, nested, dragging }"
    :draggable="draggable ? 'true' : undefined"
    @dragstart="draggable && emit('dragstart', conv, $event)"
    @dragend="emit('dragend')"
    @click="emit('open', conv.id)"
  >
    <span class="conv-text">
      <span class="conv-title"
        ><span v-if="conv.forked_from_id" class="conv-fork" title="Branched off another chat">⑂ </span
        >{{ conv.title }}</span
      >
      <span v-if="conv.snippet" class="conv-snippet">{{ conv.snippet }}</span>
    </span>
    <span class="conv-actions" @click.stop>
      <button :class="{ on: conv.pinned }" :title="conv.pinned ? 'Unpin' : 'Pin to the top'" @click="emit('pin', conv)">
        📌
      </button>
      <button title="Move to…" @click="emit('move-to', conv)">↪</button>
      <button title="Rename" @click="emit('rename', conv)">✎</button>
      <button title="Delete" @click="emit('remove', conv)">🗑</button>
    </span>
  </div>
</template>

<style scoped>
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

.conv-item.dragging {
  opacity: 0.45;
}

.conv-item.nested {
  margin-left: 16px;
  padding-left: 10px;
  border-left: 1px solid var(--border);
  border-top-left-radius: 0;
  border-bottom-left-radius: 0;
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
</style>
