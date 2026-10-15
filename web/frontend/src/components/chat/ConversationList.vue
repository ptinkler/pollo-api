<script setup>
import { computed, ref } from 'vue'
import FoldHeading from './FoldHeading.vue'
import { useFolded } from '../../composables/useFolded'
import { dateGroups } from '../../composables/useChatList'

// The sidebar's chats: a Spaces section of collapsible space folders on top
// (like ChatGPT's Projects), then a Chats section of the loose/unfiled chats
// grouped by date (like Recents). Search replaces both with flat results.
// `import` opens the ChatGPT importer (its chats land in a "ChatGPT" space).
const props = defineProps({
  list: { type: Object, required: true },
  spaces: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
})
const emit = defineEmits(['open', 'rename', 'remove', 'new-in-space', 'move', 'manage-spaces', 'import'])

const { isFolded, toggleFold } = useFolded()
const moveMenuFor = ref(null) // conversation id whose "move" menu is open

const searching = computed(() => !!props.list.searchResults)

// Chats in each space (space list order), and the loose ones grouped by date
const spaceFolders = computed(() =>
  props.spaces.map(s => ({ space: s, items: props.list.conversations.filter(c => c.space_id === s.id) })),
)
const unfiledGroups = computed(() => dateGroups(props.list.conversations.filter(c => c.space_id == null)))

function toggleMove(id) {
  moveMenuFor.value = moveMenuFor.value === id ? null : id
}

function move(conv, spaceId) {
  moveMenuFor.value = null
  if ((conv.space_id ?? null) !== spaceId) emit('move', { conv, spaceId })
}
</script>

<template>
  <div class="conv-root">
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
      <div
        v-for="c in list.searchResults"
        :key="c.id"
        class="conv-item"
        :class="{ active: c.id === activeId }"
        @click="emit('open', c.id)"
      >
        <span class="conv-text">
          <span class="conv-title">{{ c.title }}</span>
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
      <p v-if="!list.searchResults.length" class="conv-empty">No chats match</p>
    </div>

    <template v-else>
      <!-- Spaces (collapsible folders) -->
      <FoldHeading id="spaces" class="section-heading" title="Spaces" :summary="spaces.length">
        <template #actions>
          <span class="heading-btns">
            <button class="mini-btn" title="Import chats from a ChatGPT export" @click="emit('import')">Import</button>
            <button class="mini-btn" title="Create and edit spaces" @click="emit('manage-spaces')">Manage</button>
          </span>
        </template>
      </FoldHeading>
      <div v-show="!isFolded('spaces')" class="conv-list spaces-list">
        <template v-for="f in spaceFolders" :key="f.space.id">
          <div class="space-head">
            <button class="space-toggle" @click="toggleFold(`space:${f.space.id}`)">
              <span class="caret" :class="{ folded: isFolded(`space:${f.space.id}`) }">▾</span>
              <span class="folder">🗂</span>
              <span class="space-name">{{ f.space.name }}</span>
              <span class="space-count">{{ f.items.length }}</span>
            </button>
            <button class="space-add" title="New chat here" @click="emit('new-in-space', f.space.id)">＋</button>
          </div>
          <template v-if="!isFolded(`space:${f.space.id}`)">
            <div
              v-for="c in f.items"
              :key="c.id"
              class="conv-item nested"
              :class="{ active: c.id === activeId }"
              @click="emit('open', c.id)"
            >
              <span class="conv-text">
                <span class="conv-title"
                  ><span v-if="c.forked_from_id" class="conv-fork" title="Branched off another chat">⑂ </span
                  >{{ c.title }}</span
                >
              </span>
              <span class="conv-actions" @click.stop>
                <button :class="{ on: c.pinned }" :title="c.pinned ? 'Unpin' : 'Pin'" @click="list.togglePin(c)">
                  📌
                </button>
                <span class="move-wrap">
                  <button title="Move to space" @click="toggleMove(c.id)">🗂</button>
                  <div v-if="moveMenuFor === c.id" class="move-menu">
                    <button v-for="sp in spaces" :key="sp.id" :disabled="sp.id === c.space_id" @click="move(c, sp.id)">
                      {{ sp.name }}
                    </button>
                    <button :disabled="c.space_id == null" @click="move(c, null)">Chats (no space)</button>
                  </div>
                </span>
                <button title="Rename" @click="emit('rename', c)">✎</button>
                <button title="Delete" @click="emit('remove', c)">🗑</button>
              </span>
            </div>
            <p v-if="!f.items.length" class="space-empty">No chats yet</p>
          </template>
        </template>
        <p v-if="!spaces.length" class="space-empty">No spaces yet — use Manage to add one.</p>
      </div>

      <!-- Chats (loose / unfiled, by date) -->
      <FoldHeading
        id="chats"
        class="section-heading"
        title="Chats"
        :summary="unfiledGroups.reduce((n, g) => n + g.items.length, 0)"
      />
      <div v-show="!isFolded('chats')" class="conv-list chats-list">
        <template v-for="g in unfiledGroups" :key="g.label">
          <div class="conv-group">{{ g.label }}</div>
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
            </span>
            <span class="conv-actions" @click.stop>
              <button
                :class="{ on: c.pinned }"
                :title="c.pinned ? 'Unpin' : 'Pin to the top'"
                @click="list.togglePin(c)"
              >
                📌
              </button>
              <span v-if="spaces.length" class="move-wrap">
                <button title="Move to space" @click="toggleMove(c.id)">🗂</button>
                <div v-if="moveMenuFor === c.id" class="move-menu">
                  <button v-for="sp in spaces" :key="sp.id" @click="move(c, sp.id)">{{ sp.name }}</button>
                </div>
              </span>
              <button title="Rename" @click="emit('rename', c)">✎</button>
              <button title="Delete" @click="emit('remove', c)">🗑</button>
            </span>
          </div>
        </template>
        <p v-if="!unfiledGroups.length" class="conv-empty">No chats yet</p>
        <p v-if="list.more" class="conv-empty">Older chats aren't listed. Search to find them.</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.conv-root {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.section-heading {
  padding: 14px 14px 2px;
  flex: 0 0 auto;
}

.conv-list {
  overflow-y: auto;
  padding: 0 8px 4px;
  flex: 0 0 auto;
}

.spaces-list {
  max-height: 40vh;
}

.chats-list {
  flex: 1 1 auto;
  min-height: 80px;
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
