<!-- Studio left pane: thread navigator (search, favourites, pinned, spaces as
     folders, recents) with per-thread hover actions. Presentational — all
     state/actions come from props/emits. -->
<script setup>
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
function toggleSpace(id) {
  const s = openSpaces.value
  s.has(id) ? s.delete(id) : s.add(id)
  openSpaces.value = new Set(s)
}

// ── Inline rename (no modal / prompt) ──────────────────────────────────
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
    <div class="rail">
      <button class="rail-btn" title="Expand" @click="emit('update:collapsed', false)">
        <svg class="ic lg"><use href="#s-chev" /></svg>
      </button>
      <button class="rail-btn" title="New chat" @click="emit('new', 'chat')">
        <svg class="ic lg"><use href="#s-plus" /></svg>
      </button>
      <button class="rail-btn" title="Threads" @click="emit('update:collapsed', false)">
        <svg class="ic lg"><use href="#s-chat" /></svg>
      </button>
    </div>
    <div class="panel">
      <div class="phead">
        <span class="brand"
          ><span class="mk"
            ><svg class="ic"><use href="#s-spark" /></svg
          ></span>
          Studio</span
        >
        <button class="iconbtn" title="Collapse" @click="emit('update:collapsed', true)">
          <svg class="ic"><use href="#s-chevL" /></svg>
        </button>
      </div>
      <div class="pbody">
        <div class="newrow">
          <button class="newbtn" @click="emit('new', 'chat')">
            <svg class="ic"><use href="#s-plus" /></svg> New chat
          </button>
          <button class="newbtn" @click="emit('new', 'gallery')">
            <svg class="ic"><use href="#s-image" /></svg> New gallery
          </button>
        </div>
        <div class="nsearch">
          <svg class="ic"><use href="#s-search" /></svg>
          <input :value="search" placeholder="Search threads…" @input="emit('update:search', $event.target.value)" />
        </div>
        <div class="nfilter">
          <button :class="{ on: filter === 'all' }" @click="emit('update:filter', 'all')">All</button>
          <button :class="{ on: filter === 'chat' }" @click="emit('update:filter', 'chat')">Chat</button>
          <button :class="{ on: filter === 'gallery' }" @click="emit('update:filter', 'gallery')">Gallery</button>
          <button :class="{ on: filter === 'favourites' }" @click="emit('update:filter', 'favourites')">
            <svg class="ic"><use href="#s-star" /></svg> Favourites
          </button>
        </div>

        <template v-if="pinned.length">
          <div class="nlabel">Pinned</div>
          <div v-for="t in pinned" :key="t.id" class="nrow" :class="{ active: t.id === active }">
            <input
              v-if="renamingId === t.id"
              v-focus-select
              class="nrename"
              :value="renameText"
              @input="renameText = $event.target.value"
              @keydown.enter.prevent="commitRename(t)"
              @keydown.esc="cancelRename"
              @blur="commitRename(t)"
            />
            <button v-else class="nitem" @click="emit('open', t.id)">
              <svg class="ic"><use href="#s-chat" /></svg><span class="lbl">{{ t.title || 'Untitled' }}</span>
            </button>
            <div class="nactions">
              <button class="nact on" title="Unpin" @click.stop="emit('pin', t)">
                <svg class="ic sm"><use href="#s-pin" /></svg>
              </button>
              <button class="nact" title="Rename" @click.stop="startRename(t)">
                <svg class="ic sm"><use href="#s-pencil" /></svg>
              </button>
              <button class="nact" title="Delete" @click.stop="emit('delete', t)">
                <svg class="ic sm"><use href="#s-trash" /></svg>
              </button>
            </div>
          </div>
        </template>

        <div class="nlabel row">
          <span>Spaces</span>
          <button class="addspace" title="New space" @click="emit('add-space')">
            <svg class="ic sm"><use href="#s-plus" /></svg>
          </button>
        </div>
        <template v-for="g in bySpace.groups" :key="g.space.id">
          <div
            class="folder"
            :class="{ open: openSpaces.has(g.space.id), drop: dropOn === g.space.id }"
            @dragover.prevent="dropOn = g.space.id"
            @dragleave="dropOn = null"
            @drop.prevent="onDrop(g.space.id)"
          >
            <button class="fchev" @click="toggleSpace(g.space.id)">
              <svg class="ic sm"><use href="#s-chev" /></svg>
            </button>
            <button class="fmain" @click="emit('open-space', g.space)">
              <svg class="ic"><use href="#s-folder" /></svg><span class="lbl">{{ g.space.name }}</span
              ><span class="count">{{ g.items.length }}</span>
            </button>
            <div class="nactions">
              <button class="nact" title="Space defaults" @click.stop="emit('space-settings', g.space)">
                <svg class="ic sm"><use href="#s-cog" /></svg>
              </button>
              <button class="nact" title="Rename" @click.stop="emit('rename-space', g.space)">
                <svg class="ic sm"><use href="#s-pencil" /></svg>
              </button>
              <button class="nact" title="Delete" @click.stop="emit('delete-space', g.space)">
                <svg class="ic sm"><use href="#s-trash" /></svg>
              </button>
            </div>
          </div>
          <div v-show="openSpaces.has(g.space.id)" class="fkids">
            <div
              v-for="t in g.items"
              :key="t.id"
              class="nrow sm"
              :class="{ active: t.id === active }"
              draggable="true"
              @dragstart="dragId = t.id"
            >
              <input
                v-if="renamingId === t.id"
                v-focus-select
                class="nrename"
                :value="renameText"
                @input="renameText = $event.target.value"
                @keydown.enter.prevent="commitRename(t)"
                @keydown.esc="cancelRename"
                @blur="commitRename(t)"
              />
              <button v-else class="nitem" @click="emit('open', t.id)">
                <svg class="ic"><use href="#s-chat" /></svg><span class="lbl">{{ t.title || 'Untitled' }}</span>
              </button>
              <div class="nactions">
                <button class="nact" :class="{ on: t.pinned }" title="Pin" @click.stop="emit('pin', t)">
                  <svg class="ic sm"><use href="#s-pin" /></svg>
                </button>
                <button class="nact" title="Rename" @click.stop="startRename(t)">
                  <svg class="ic sm"><use href="#s-pencil" /></svg>
                </button>
                <button class="nact" title="Delete" @click.stop="emit('delete', t)">
                  <svg class="ic sm"><use href="#s-trash" /></svg>
                </button>
              </div>
            </div>
            <div v-if="!g.items.length" class="fempty">Empty — drag threads here</div>
          </div>
        </template>

        <div
          class="nlabel drop-target"
          :class="{ drop: dropOn === 'unfiled' }"
          @dragover.prevent="dropOn = 'unfiled'"
          @dragleave="dropOn = null"
          @drop.prevent="onDrop(null)"
        >
          Recent
        </div>
        <div
          v-for="t in bySpace.unfiled"
          :key="t.id"
          class="nrow sm"
          :class="{ active: t.id === active }"
          draggable="true"
          @dragstart="dragId = t.id"
        >
          <input
            v-if="renamingId === t.id"
            v-focus-select
            class="nrename"
            :value="renameText"
            @input="renameText = $event.target.value"
            @keydown.enter.prevent="commitRename(t)"
            @keydown.esc="cancelRename"
            @blur="commitRename(t)"
          />
          <button v-else class="nitem" @click="emit('open', t.id)">
            <svg class="ic"><use href="#s-chat" /></svg><span class="lbl">{{ t.title || 'Untitled' }}</span>
          </button>
          <div class="nactions">
            <button class="nact" :class="{ on: t.pinned }" title="Pin" @click.stop="emit('pin', t)">
              <svg class="ic sm"><use href="#s-pin" /></svg>
            </button>
            <button class="nact" title="Rename" @click.stop="startRename(t)">
              <svg class="ic sm"><use href="#s-pencil" /></svg>
            </button>
            <button class="nact" title="Delete" @click.stop="emit('delete', t)">
              <svg class="ic sm"><use href="#s-trash" /></svg>
            </button>
          </div>
        </div>
      </div>
      <div class="pfoot">
        <button class="footbtn" @click="emit('media')">
          <svg class="ic"><use href="#s-image" /></svg> Media
        </button>
        <button class="footbtn" @click="emit('tools')">
          <svg class="ic"><use href="#s-spark" /></svg> Tools &amp; library
        </button>
        <button class="footbtn" @click="emit('settings')">
          <svg class="ic"><use href="#s-cog" /></svg> Settings
        </button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.side {
  position: relative;
  flex: 0 0 auto;
  width: 268px;
  background: var(--sbg);
  border-right: 1px solid var(--sborder);
  transition: width 0.2s;
}
.side.collapsed {
  width: 54px;
}
.rail {
  display: none;
}
.side.collapsed > .rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  height: 100%;
  padding: 12px 0;
  background: var(--srail);
}
.rail-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
}
.rail-btn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.side.collapsed > .panel {
  display: none;
}
.panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.phead {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px;
  border-bottom: 1px solid var(--sborder2);
}
.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  font-weight: 650;
  letter-spacing: -0.02em;
  flex: 1;
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
.iconbtn {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
}
.iconbtn:hover {
  background: var(--shover);
  color: var(--sfg);
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
  padding: 9px 8px;
  border: 1px solid var(--sborder);
  color: var(--sfg);
  border-radius: 10px;
  background: none;
  cursor: pointer;
  font-size: 12.5px;
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
  position: relative;
  padding-bottom: 8px;
}
.nsearch .ic {
  position: absolute;
  left: 11px;
  top: 9px;
  color: var(--sfaint);
  width: 15px;
  height: 15px;
}
.nsearch input {
  width: 100%;
  padding: 8px 11px 8px 33px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  background: var(--spanel2);
  color: var(--sfg);
  outline: none;
}
.nfilter {
  display: flex;
  gap: 6px;
  padding-bottom: 6px;
}
.nfilter button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 11px;
  border: 1px solid var(--sborder);
  border-radius: 8px;
  color: var(--smuted);
  background: none;
  cursor: pointer;
  font-size: 12px;
}
.nfilter button.on {
  background: var(--saccent-soft);
  color: var(--saccent);
  border-color: transparent;
}
.nfilter .ic {
  width: 13px;
  height: 13px;
}
.nlabel {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: var(--sfaint);
  padding: 13px 10px 5px;
  font-weight: 650;
}
.nrow {
  position: relative;
  display: flex;
  align-items: center;
  border-radius: 9px;
}
.nrow:hover {
  background: var(--shover);
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
.nitem {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  padding: 8px 10px;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
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
  font-size: 13px;
}
.nrow.sm .nitem {
  padding: 7px 10px;
  font-size: 13px;
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
.nactions {
  display: none;
  align-items: center;
  gap: 1px;
  padding-right: 5px;
}
.nrow:hover .nactions {
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
.folder:hover .nactions {
  display: flex;
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
  padding: 8px 10px;
  border-radius: 9px;
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
