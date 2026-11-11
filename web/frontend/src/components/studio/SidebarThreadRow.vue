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
    @blur="emit('commit-rename')"
  />
  <a v-else class="nitem" :href="`/${thread.id}`" @click.prevent="emit('open')">
    <svg class="ic"><use :href="threadIcon(thread)" /></svg><span class="lbl">{{ thread.title || 'Untitled' }}</span>
  </a>
  <div class="nactions">
    <button
      class="nact"
      :class="{ on: alwaysPinned || pinned }"
      :title="alwaysPinned ? 'Unpin' : 'Pin'"
      @click.stop="emit('pin')"
    >
      <svg class="ic sm"><use href="#s-pin" /></svg>
    </button>
    <button class="nact" title="Rename" @click.stop="emit('start-rename')">
      <svg class="ic sm"><use href="#s-pencil" /></svg>
    </button>
    <button class="nact" title="Delete" @click.stop="emit('delete')">
      <svg class="ic sm"><use href="#s-trash" /></svg>
    </button>
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
.nactions {
  display: none;
  align-items: center;
  gap: 1px;
  padding-right: 5px;
}
/* .nrow lives in StudioSidebar (it owns the row wrapper and its hover) */
:global(.nrow:hover) .nactions {
  display: flex;
}
.nact {
  width: 25px;
  height: 25px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: var(--sfaint);
  background: none;
  border: none;
  cursor: pointer;
}
.nact:hover {
  background: var(--sborder);
  color: var(--sfg);
}
.nact.on {
  color: var(--saccent);
}
</style>
