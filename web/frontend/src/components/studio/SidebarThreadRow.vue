<!-- One thread in the sidebar list: its name (or the rename box), and the
     pin / rename / delete actions that appear on hover. The three places
     that list threads — pinned, inside a space, and unfiled — differ only in
     the row wrapper (drag handlers, pinned state), which stays with them. -->
<script setup>
defineProps({
  thread: { type: Object, required: true },
  renaming: { type: Boolean, default: false },
  renameText: { type: String, default: '' },
  // The pinned list shows "Unpin" and is always lit; elsewhere it toggles
  pinned: { type: Boolean, default: false },
  alwaysPinned: { type: Boolean, default: false },
})
const emit = defineEmits([
  'open',
  'pin',
  'start-rename',
  'commit-rename',
  'cancel-rename',
  'delete',
  'update:renameText',
])

const vFocusSelect = { mounted: el => (el.focus(), el.select()) }
// Icon per thread kind: the gallery icon (same as "New gallery") vs the chat icon.
const threadIcon = t => (t.kind === 'gallery' ? '#s-image' : '#s-chat')
</script>

<template>
  <input
    v-if="renaming"
    v-focus-select
    class="nrename"
    :value="renameText"
    @input="emit('update:renameText', $event.target.value)"
    @keydown.enter.prevent="emit('commit-rename')"
    @keydown.esc="emit('cancel-rename')"
    @blur="emit('cancel-rename')"
  />
  <a v-else class="nitem" :href="`/${thread.id}`" @click.prevent="emit('open')">
    <svg class="ic"><use :href="threadIcon(thread)" /></svg><span class="lbl">{{ thread.title || 'Untitled' }}</span>
  </a>
  <div class="nactions">
    <template v-if="renaming">
      <button
        class="nact"
        title="Confirm rename"
        aria-label="Confirm rename"
        @mousedown.prevent
        @click="emit('commit-rename')"
      >
        <svg class="ic sm"><use href="#s-check" /></svg>
      </button>
      <button
        class="nact"
        title="Cancel rename"
        aria-label="Cancel rename"
        @mousedown.prevent
        @click="emit('cancel-rename')"
      >
        <svg class="ic sm"><use href="#s-close" /></svg>
      </button>
    </template>
    <template v-else>
      <button class="nact" title="Rename" @click.stop="emit('start-rename')">
        <svg class="ic sm"><use href="#s-pencil" /></svg>
      </button>
      <button
        class="nact"
        :class="{ on: alwaysPinned || pinned }"
        :title="alwaysPinned || pinned ? 'Unpin' : 'Pin'"
        :aria-label="alwaysPinned || pinned ? 'Unpin chat' : 'Pin chat'"
        :aria-pressed="alwaysPinned || pinned"
        @click.stop="emit('pin')"
      >
        <svg class="ic sm"><use href="#s-pin" /></svg>
      </button>
      <button class="nact danger" title="Delete" aria-label="Delete chat" @click.stop="emit('delete')">
        <svg class="ic sm"><use href="#s-trash" /></svg>
      </button>
    </template>
  </div>
</template>

<style scoped>
.nitem {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  padding: 7px 10px;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: none;
}
.nitem .ic {
  color: var(--sfaint);
}
.nitem .lbl {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nrename {
  flex: 1;
  min-width: 0;
  margin: 3px 6px;
  padding: 6px 8px;
  border: 1px solid var(--saccent);
  border-radius: 7px;
  background: var(--spanel2, var(--sbg2));
  color: var(--sfg);
  outline: none;
  font: inherit;
}
</style>
