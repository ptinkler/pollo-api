<!-- Studio left pane: thread navigator (search, favourites, pinned, spaces as
     folders, recents) with per-thread hover actions. Presentational — all
     state/actions come from props/emits. -->
<script setup>
import SidebarThreadRow from './SidebarThreadRow.vue'
import { ref, computed } from 'vue'

const props = defineProps({
  threads: { type: Array, default: () => [] },
  spaces: { type: Array, default: () => [] },
  active: { type: String, default: null },
  collapsed: { type: Boolean, default: false },
  search: { type: String, default: '' },
  filter: { type: String, default: 'all' }, // 'all' | 'chat' | 'gallery' | 'favourites'
})
const emit = defineEmits([
  'update:collapsed',
  'update:search',
  'update:filter',
  'open',
  'new',
  'pin',
  'rename',
  'delete',
  'settings',
  'open-space',
  'add-space',
  'rename-space',
  'delete-space',
  'space-settings',
  'move',
  'media',
  'tools',
])

const openSpaces = ref(new Set())
const pinnedSectionOpen = ref(true)
const spacesSectionOpen = ref(true)
const recentSectionOpen = ref(true)
function toggleSpace(id) {
  const s = openSpaces.value
  s.has(id) ? s.delete(id) : s.add(id)
  openSpaces.value = new Set(s)
}

// Inline rename (no modal / prompt)
const renamingId = ref(null)
const renameText = ref('')
const vFocusSelect = { mounted: el => (el.focus(), el.select()) }
function startRename(t) {
  renamingId.value = t.id
  renameText.value = t.title || ''
}
function commitRename(t) {
  if (renamingId.value !== t.id) return // already committed (e.g. Enter then blur)
  const name = renameText.value.trim()
  renamingId.value = null
  if (name && name !== (t.title || '')) emit('rename', t, name)
}
function cancelRename() {
  renamingId.value = null
}
const spaceKey = s => `space:${s.id}`
function startRenameSpace(s) {
  renamingId.value = spaceKey(s)
  renameText.value = s.name || ''
}
function commitRenameSpace(s) {
  if (renamingId.value !== spaceKey(s)) return
  const name = renameText.value.trim()
  renamingId.value = null
  if (name && name !== (s.name || '')) emit('rename-space', s, name)
}

// Drag a thread onto a space folder (or Recent) to move it
const dragId = ref(null)
const dropOn = ref(null)
function onDrop(spaceId) {
  const t = props.threads.find(x => x.id === dragId.value)
  if (t && t.space_id !== spaceId) emit('move', t, spaceId)
  dragId.value = null
  dropOn.value = null
}

// Chat/Gallery filter the list by a thread's kind; All and Favourites show
// every thread (Favourites swaps the centre pane for the gallery, not the nav).
function matchesKind(t) {
  const k = t.kind || 'chat'
  if (props.filter === 'chat') return k !== 'gallery'
  if (props.filter === 'gallery') return k === 'gallery'
  return true
}
const filtered = computed(() => {
  const q = props.search.trim().toLowerCase()
  return props.threads.filter(t => matchesKind(t) && (!q || (t.title || '').toLowerCase().includes(q)))
})
const pinned = computed(() => filtered.value.filter(t => t.pinned))
const bySpace = computed(() => {
  const map = {}
  for (const s of props.spaces) map[s.id] = { space: s, items: [] }
  const unfiled = []
  for (const t of filtered.value) {
    if (t.pinned) continue
    if (t.space_id != null && map[t.space_id]) map[t.space_id].items.push(t)
    else unfiled.push(t)
  }
  return { groups: Object.values(map), unfiled }
})
</script>

<template>
  <aside class="side" :class="{ collapsed }">
    <button
      class="rail"
      type="button"
      title="Expand sidebar"
      aria-label="Expand sidebar"
      @click="emit('update:collapsed', false)"
    >
      <svg class="ic lg chev"><use href="#s-chev" /></svg>
      <span class="rail-label">Studio</span>
      <svg class="ic lg"><use href="#s-plus" /></svg>
      <svg class="ic lg"><use href="#s-chat" /></svg>
    </button>
    <div class="panel">
      <button class="panelhead" type="button" title="Collapse sidebar" @click="emit('update:collapsed', true)">
        <span class="brand"
          ><span class="mk"
            ><svg class="ic"><use href="#s-spark" /></svg
          ></span>
          Studio</span
        >
        <svg class="ic"><use href="#s-chevL" /></svg>
      </button>
      <div class="pbody">
        <div class="newrow">
          <a class="newbtn" href="/" @click.prevent="emit('new', 'chat')">
            <svg class="ic"><use href="#s-plus" /></svg> New chat
          </a>
          <a class="newbtn" href="/?new=gallery" @click.prevent="emit('new', 'gallery')">
            <svg class="ic"><use href="#s-image" /></svg> New gallery
          </a>
        </div>
        <div class="sbox nsearch">
          <svg class="ic"><use href="#s-search" /></svg>
          <input
            :value="search"
            type="search"
            placeholder="Search threads…"
            @input="emit('update:search', $event.target.value)"
          />
        </div>
        <div class="nfilter">
          <button class="pillbtn" :class="{ on: filter === 'all' }" @click="emit('update:filter', 'all')">All</button>
          <button class="pillbtn" :class="{ on: filter === 'chat' }" @click="emit('update:filter', 'chat')">
            Chat
          </button>
          <button class="pillbtn" :class="{ on: filter === 'gallery' }" @click="emit('update:filter', 'gallery')">
            Gallery
          </button>
          <a
            class="pillbtn ficon"
            :class="{ on: filter === 'favourites' }"
            title="Favourites"
            href="/favourites"
            @click.prevent="emit('update:filter', 'favourites')"
          >
            <svg class="ic"><use href="#s-star" /></svg>
          </a>
          <button class="pillbtn ficon" title="More filters — coming soon" disabled>
            <svg class="ic"><use href="#s-filter" /></svg>
          </button>
        </div>

        <template v-if="pinned.length">
          <button
            class="nlabel section-toggle"
            :aria-expanded="pinnedSectionOpen"
            @click="pinnedSectionOpen = !pinnedSectionOpen"
          >
            <svg class="ic sm"><use href="#s-chev" /></svg>
            <span>Pinned</span>
          </button>
          <div
            v-for="t in pinned"
            v-show="pinnedSectionOpen"
            :key="t.id"
            class="nrow"
            :class="{ active: t.id === active }"
          >
            <SidebarThreadRow
              v-model:rename-text="renameText"
              :thread="t"
              :renaming="renamingId === t.id"
              always-pinned
              @open="emit('open', t.id)"
              @pin="emit('pin', t)"
              @start-rename="startRename(t)"
              @commit-rename="commitRename(t)"
              @cancel-rename="cancelRename"
              @delete="emit('delete', t)"
            />
          </div>
        </template>

        <div class="nlabel row">
          <button
            class="section-toggle"
            :aria-expanded="spacesSectionOpen"
            @click="spacesSectionOpen = !spacesSectionOpen"
          >
            <svg class="ic sm"><use href="#s-chev" /></svg>
            <span>Spaces</span>
          </button>
          <button class="addspace" title="New space" @click="emit('add-space')">
            <svg class="ic sm"><use href="#s-plus" /></svg>
          </button>
        </div>
        <template v-for="g in bySpace.groups" :key="g.space.id">
          <div
            v-show="spacesSectionOpen"
            class="folder"
            :class="{ open: openSpaces.has(g.space.id), drop: dropOn === g.space.id }"
            @dragover.prevent="dropOn = g.space.id"
            @dragleave="dropOn = null"
            @drop.prevent="onDrop(g.space.id)"
          >
            <button class="fchev" @click="toggleSpace(g.space.id)">
              <svg class="ic sm"><use href="#s-chev" /></svg>
            </button>
            <input
              v-if="renamingId === spaceKey(g.space)"
              v-focus-select
              class="nrename"
              :value="renameText"
              @input="renameText = $event.target.value"
              @keydown.enter.prevent="commitRenameSpace(g.space)"
              @keydown.esc="cancelRename"
              @blur="cancelRename"
            />
            <a v-else class="fmain" :href="`/space/${g.space.id}`" @click.prevent="emit('open-space', g.space)">
              <svg class="ic"><use href="#s-folder" /></svg><span class="lbl">{{ g.space.name }}</span
              ><span class="count">{{ g.items.length }}</span>
            </a>
            <div class="nactions">
              <template v-if="renamingId === spaceKey(g.space)">
                <button
                  class="nact"
                  title="Confirm rename"
                  aria-label="Confirm rename"
                  @mousedown.prevent
                  @click="commitRenameSpace(g.space)"
                >
                  <svg class="ic sm"><use href="#s-check" /></svg>
                </button>
                <button
                  class="nact"
                  title="Cancel rename"
                  aria-label="Cancel rename"
                  @mousedown.prevent
                  @click="cancelRename"
                >
                  <svg class="ic sm"><use href="#s-close" /></svg>
                </button>
              </template>
              <template v-else>
                <button class="nact" title="Rename" @click.stop="startRenameSpace(g.space)">
                  <svg class="ic sm"><use href="#s-pencil" /></svg>
                </button>
                <button class="nact" title="Space defaults" @click.stop="emit('space-settings', g.space)">
                  <svg class="ic sm"><use href="#s-cog" /></svg>
                </button>
                <button class="nact danger" title="Delete" @click.stop="emit('delete-space', g.space)">
                  <svg class="ic sm"><use href="#s-trash" /></svg>
                </button>
              </template>
            </div>
          </div>
          <div v-show="spacesSectionOpen && openSpaces.has(g.space.id)" class="fkids">
            <div
              v-for="t in g.items"
              :key="t.id"
              class="nrow sm"
              :class="{ active: t.id === active }"
              draggable="true"
              @dragstart="dragId = t.id"
            >
              <SidebarThreadRow
                v-model:rename-text="renameText"
                :thread="t"
                :renaming="renamingId === t.id"
                :pinned="t.pinned"
                @open="emit('open', t.id)"
                @pin="emit('pin', t)"
                @start-rename="startRename(t)"
                @commit-rename="commitRename(t)"
                @cancel-rename="cancelRename"
                @delete="emit('delete', t)"
              />
            </div>
            <div v-if="!g.items.length" class="fempty">Empty — drag threads here</div>
          </div>
        </template>

        <button
          class="nlabel section-toggle drop-target"
          :class="{ drop: dropOn === 'unfiled' }"
          :aria-expanded="recentSectionOpen"
          @click="recentSectionOpen = !recentSectionOpen"
          @dragover.prevent="dropOn = 'unfiled'"
          @dragleave="dropOn = null"
          @drop.prevent="onDrop(null)"
        >
          <svg class="ic sm"><use href="#s-chev" /></svg>
          <span>Recent</span>
        </button>
        <div
          v-for="t in bySpace.unfiled"
          v-show="recentSectionOpen"
          :key="t.id"
          class="nrow sm"
          :class="{ active: t.id === active }"
          draggable="true"
          @dragstart="dragId = t.id"
        >
          <SidebarThreadRow
            v-model:rename-text="renameText"
            :thread="t"
            :renaming="renamingId === t.id"
            :pinned="t.pinned"
            @open="emit('open', t.id)"
            @pin="emit('pin', t)"
            @start-rename="startRename(t)"
            @commit-rename="commitRename(t)"
            @cancel-rename="cancelRename"
            @delete="emit('delete', t)"
          />
        </div>
      </div>
      <div class="pfoot">
        <a class="footbtn" href="/media" @click.prevent="emit('media')">
          <svg class="ic"><use href="#s-image" /></svg> Media
        </a>
        <a class="footbtn" href="/tools" @click.prevent="emit('tools')">
          <svg class="ic"><use href="#s-spark" /></svg> Tools &amp; library
        </a>
        <a class="footbtn" href="/settings" @click.prevent="emit('settings')">
          <svg class="ic"><use href="#s-cog" /></svg> Settings
        </a>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.side {
  width: 268px;
  background: var(--sbg);
  border-right: 1px solid var(--sborder);
}
/* These are <a> so they can be opened in a new tab; they must still look and
   sit exactly like the buttons they replaced. */
.newbtn,
.footbtn,
.fmain,
.pillbtn.ficon {
  text-decoration: none;
  box-sizing: border-box;
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  font-weight: 650;
  letter-spacing: -0.02em;
}
.brand .mk {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: var(--saccent-soft);
  color: var(--saccent);
  display: grid;
  place-items: center;
}
.pbody {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}
.newrow {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}
.newbtn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid var(--sborder);
  color: var(--sfg);
  border-radius: var(--r);
  background: none;
  cursor: pointer;
  font-size: 12.5px;
  font-weight: 500;
  white-space: nowrap;
}
.newbtn:hover {
  border-color: var(--sfaint);
  background: var(--spanel2);
}
.newbtn .ic {
  color: var(--saccent);
}
.nsearch {
  margin-bottom: 8px;
}
.nfilter {
  display: flex;
  gap: 4px;
  padding-bottom: 6px;
}
/* Favourites + the filter placeholder are icon-only (text overflowed the rail) */
.nfilter .ficon {
  padding: 4px 7px;
  margin-left: auto;
}
.nfilter .ficon + .ficon {
  margin-left: 0;
}
.nlabel {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: var(--sfaint);
  padding: 13px 10px 5px 0;
  font-weight: 650;
}
.section-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  border: 0;
  background: none;
  text-align: left;
  cursor: pointer;
}
.section-toggle[aria-expanded='true'] .ic {
  transform: rotate(90deg);
}
.section-toggle .ic {
  transition: transform 0.15s;
}
.nlabel.section-toggle {
  color: var(--sfaint);
}
.nlabel.row .section-toggle {
  flex: 1;
  width: auto;
  padding: 0;
  color: var(--sfaint);
  font: inherit;
  text-transform: inherit;
}
.nrow {
  position: relative;
  display: flex;
  align-items: center;
  border-radius: var(--r);
}
.nrow:hover {
  background: var(--shover);
}
.nrow:hover :deep(.nactions),
.nrow:focus-within :deep(.nactions) {
  visibility: visible;
}
.nrow.active {
  background: var(--saccent-soft);
}
.nrow.active .nitem,
.nrow:hover .nitem {
  color: var(--sfg);
}
.nrow.active .ic {
  color: var(--saccent);
}
.nrow.sm .nitem {
  padding: 6px 10px;
  font-size: 13px;
}
.folder {
  display: flex;
  align-items: center;
  border-radius: 9px;
}
.folder:hover {
  background: var(--shover);
}
.fchev {
  width: 26px;
  height: 32px;
  display: grid;
  place-items: center;
  color: var(--sfaint);
  background: none;
  border: none;
  cursor: pointer;
}
.fchev .ic {
  transition: transform 0.15s;
}
.folder.open .fchev .ic {
  transform: rotate(90deg);
}
.fmain {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: 1;
  min-width: 0;
  padding: 7px 10px 7px 0;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
}
.fmain .ic {
  color: var(--sfaint);
}
.fmain .lbl {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fmain .count {
  font-size: 11px;
  color: var(--sfaint);
}
.side :deep(.nactions) {
  display: flex;
  align-items: center;
  gap: 1px;
  flex: 0 0 82px;
  justify-content: flex-end;
  padding-right: 5px;
  visibility: hidden;
}
.side :deep(.nact) {
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
.side :deep(.nact:hover) {
  background: var(--sborder);
  color: var(--sfg);
}
.side :deep(.nact.on) {
  color: var(--saccent);
}
.side :deep(.nact.danger),
.side :deep(.nact.danger:hover) {
  color: var(--sdanger);
}
.side :deep(.nact.danger:hover) {
  background: color-mix(in srgb, var(--sdanger) 12%, var(--sbg2));
}
.folder:hover :deep(.nactions),
.folder:focus-within :deep(.nactions) {
  visibility: visible;
}
.nrow:hover :deep(.nactions),
.nrow:focus-within :deep(.nactions) {
  visibility: visible;
}
.folder.drop {
  background: var(--saccent-soft);
  box-shadow: inset 0 0 0 1px var(--saccent);
}
.fkids {
  padding-left: 8px;
  margin-left: 20px;
  border-left: 1px solid var(--sborder2);
}
.fempty {
  padding: 7px 10px;
  color: var(--sfaint);
  font-size: 12px;
  font-style: italic;
}
.nlabel.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.addspace {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: var(--sfaint);
  background: none;
  border: none;
  cursor: pointer;
}
.addspace:hover {
  background: var(--shover);
  color: var(--sfg);
}
.drop-target.drop {
  color: var(--saccent);
  box-shadow: inset 0 0 0 1px var(--saccent);
  border-radius: 7px;
}
.pfoot {
  padding: 8px 10px;
  border-top: 1px solid var(--sborder2);
}
.footbtn {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 7px 10px;
  border-radius: var(--r);
  font-size: 13.5px;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
}
.footbtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.footbtn .ic {
  color: var(--sfaint);
}
</style>
