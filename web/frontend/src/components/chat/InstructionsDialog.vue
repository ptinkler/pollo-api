<script setup>
import { ref, computed, watch, nextTick, inject } from 'vue'
import {
  createInstruction,
  updateInstruction,
  deleteInstruction,
  createInstructionGroup,
  updateInstructionGroup,
  deleteInstructionGroup,
} from '../../composables/useChat'
import DefaultToggles from './DefaultToggles.vue'
import { instructionColor } from '../../utils/format'

// Create and edit instruction snippets and groups (a group bundles snippets).
// One searchable list of both; `focus` opens on a given one.
const props = defineProps({
  open: { type: Boolean, default: false },
  instructions: { type: Array, default: () => [] }, // snippets
  groups: { type: Array, default: () => [] },
  focus: { type: Object, default: null }, // { kind: 'snippet' | 'group', id } to open on
})
const emit = defineEmits(['close', 'changed'])
const showToast = inject('showToast', () => {})

const query = ref('')
const kind = ref('snippet') // what's being edited: 'snippet' | 'group'
const editingId = ref(null) // null = new
const name = ref('')
const content = ref('') // snippet
const memberIds = ref([]) // group
const memberQuery = ref('')
const saving = ref(false)
const nameInput = ref(null)
const toggles = ref(null) // the "Default for" pills, saved along with the rest
const defaultsDirty = ref(false)

const isGroup = computed(() => kind.value === 'group')
const current = computed(() => (isGroup.value ? props.groups : props.instructions).find(x => x.id === editingId.value))

// ── The list ─────────────────────────────────────────────────────────
const matches = item => item.name.toLowerCase().includes(query.value.trim().toLowerCase())
const shownGroups = computed(() => props.groups.filter(matches))
const shownSnippets = computed(() => props.instructions.filter(matches))
const isActive = (k, item) => kind.value === k && editingId.value === item.id

// ── Group members ────────────────────────────────────────────────────
const snippetById = computed(() => new Map(props.instructions.map(s => [s.id, s])))
const members = computed(() => memberIds.value.map(id => snippetById.value.get(id)).filter(Boolean))
const addable = computed(() => {
  const q = memberQuery.value.trim().toLowerCase()
  return props.instructions.filter(s => !memberIds.value.includes(s.id) && s.name.toLowerCase().includes(q))
})

function addMember(s) {
  memberIds.value = [...memberIds.value, s.id]
  memberQuery.value = ''
}

function removeMember(s) {
  memberIds.value = memberIds.value.filter(id => id !== s.id)
}

// ── Editing ──────────────────────────────────────────────────────────
const sameIds = (a, b) => a.length === b.length && a.every(x => b.includes(x))
const dirty = computed(() => {
  const cur = current.value
  if (!cur) return !!(name.value.trim() || content.value.trim() || memberIds.value.length)
  if (cur.name !== name.value) return true
  return isGroup.value ? !sameIds(memberIds.value, cur.snippet_ids || []) : cur.content !== content.value
})

function load(k, item) {
  kind.value = k
  editingId.value = item?.id ?? null
  name.value = item?.name ?? ''
  content.value = item?.content ?? ''
  memberIds.value = [...(item?.snippet_ids || [])]
  memberQuery.value = ''
}

function confirmDiscard() {
  return !(dirty.value || defaultsDirty.value) || confirm('Discard unsaved changes?')
}

function pick(k, item) {
  if (isActive(k, item) || !confirmDiscard()) return
  load(k, item)
}

function startNew(k) {
  if (!confirmDiscard()) return
  load(k, null)
  nextTick(() => nameInput.value?.focus())
}

watch(
  () => props.open,
  open => {
    if (!open) return
    query.value = ''
    const f = props.focus
    const item = f && (f.kind === 'group' ? props.groups : props.instructions).find(x => x.id === f.id)
    if (item) load(f.kind, item)
    else if (props.instructions.length) load('snippet', props.instructions[0])
    else startNew('snippet')
  },
)

async function save() {
  if (!name.value.trim()) return
  saving.value = true
  try {
    const id = editingId.value
    let saved
    if (isGroup.value) {
      const data = { name: name.value.trim(), snippet_ids: memberIds.value }
      saved = id == null ? await createInstructionGroup(data) : await updateInstructionGroup(id, data)
    } else {
      const data = { name: name.value.trim(), content: content.value }
      saved = id == null ? await createInstruction(data) : await updateInstruction(id, data)
    }
    await toggles.value?.commit(saved.id)
    emit('changed')
    load(kind.value, saved)
  } catch (e) {
    showToast(`Save failed: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function remove() {
  const what = isGroup.value
    ? `the group “${name.value}”? Its snippets are kept.`
    : `“${name.value}”? It's also taken out of chats and groups.`
  if (!confirm(`Delete ${what}`)) return
  try {
    await (isGroup.value ? deleteInstructionGroup : deleteInstruction)(editingId.value)
    emit('changed')
    load(kind.value, null)
  } catch (e) {
    showToast(`Delete failed: ${e.message}`, 'error')
  }
}

function close() {
  if (confirmDiscard()) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="backdrop" @click.self="close" @keydown.esc="close">
      <div class="dialog" role="dialog" aria-label="Instructions">
        <div class="head">
          <h3>Instructions</h3>
          <button class="x" title="Close" @click="close">✕</button>
        </div>

        <div class="body">
          <aside class="list">
            <input v-model="query" type="search" class="search" placeholder="Search" aria-label="Search instructions" />
            <div class="new-row">
              <button class="new" @click="startNew('snippet')">＋ Snippet</button>
              <button class="new" @click="startNew('group')">＋ Group</button>
            </div>
            <div class="items">
              <template v-if="shownGroups.length">
                <p class="list-head">Groups</p>
                <button
                  v-for="g in shownGroups"
                  :key="`g${g.id}`"
                  class="item"
                  :class="{ active: isActive('group', g) }"
                  @click="pick('group', g)"
                >
                  <span class="item-name">📦 {{ g.name }}</span>
                  <span class="count">{{ g.snippet_ids?.length || 0 }}</span>
                </button>
              </template>
              <template v-if="shownSnippets.length">
                <p class="list-head">Snippets</p>
                <button
                  v-for="s in shownSnippets"
                  :key="`s${s.id}`"
                  class="item"
                  :class="{ active: isActive('snippet', s) }"
                  :title="s.content"
                  @click="pick('snippet', s)"
                >
                  <span class="dot" :style="{ background: instructionColor(s.name) }"></span>
                  <span class="item-name">{{ s.name }}</span>
                </button>
              </template>
              <p v-if="!shownGroups.length && !shownSnippets.length" class="empty">
                {{ query ? 'Nothing matches' : 'None yet' }}
              </p>
            </div>
          </aside>

          <form class="editor" @submit.prevent="save">
            <p class="editing">
              {{ editingId == null ? `New ${isGroup ? 'group' : 'snippet'}` : isGroup ? 'Group' : 'Snippet' }}
            </p>
            <input
              ref="nameInput"
              v-model="name"
              class="name"
              maxlength="255"
              :placeholder="isGroup ? 'Group name' : 'Name, e.g. Terse tone'"
              aria-label="Name"
            />

            <textarea
              v-if="!isGroup"
              v-model="content"
              maxlength="20000"
              placeholder="What the chat model should do — a tone, a format, a rule."
              aria-label="Instructions"
            ></textarea>

            <template v-else>
              <div class="members">
                <span v-for="s in members" :key="s.id" class="chip" :title="s.name">
                  <span class="dot" :style="{ background: instructionColor(s.name) }"></span>
                  <span class="chip-name">{{ s.name }}</span>
                  <button type="button" class="chip-x" :title="`Remove ${s.name}`" @click="removeMember(s)">✕</button>
                </span>
                <span v-if="!members.length" class="empty">No snippets yet</span>
              </div>
              <div class="adder">
                <input
                  v-model="memberQuery"
                  type="search"
                  placeholder="Add a snippet…"
                  aria-label="Add a snippet"
                  @keydown.enter.prevent="addable[0] && addMember(addable[0])"
                />
                <div v-if="memberQuery.trim()" class="adder-menu">
                  <button v-for="s in addable" :key="s.id" type="button" class="item" @click="addMember(s)">
                    <span class="item-name">{{ s.name }}</span>
                  </button>
                  <p v-if="!addable.length" class="empty">No other snippets match</p>
                </div>
              </div>
            </template>

            <DefaultToggles
              ref="toggles"
              v-model:dirty="defaultsDirty"
              :kind="isGroup ? 'instruction_group' : 'instruction'"
              :item-id="editingId"
            />

            <div class="actions">
              <button v-if="editingId != null" type="button" class="btn btn-danger" @click="remove">Delete</button>
              <span class="spacer"></span>
              <button type="button" class="btn btn-secondary" @click="close">Close</button>
              <button class="btn btn-primary" :disabled="saving || !(dirty || defaultsDirty) || !name.trim()">
                {{ editingId == null ? 'Create' : 'Save' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.7);
  display: grid;
  place-items: center;
  padding: 16px;
}

.dialog {
  width: min(820px, 100%);
  height: min(620px, calc(100vh - 32px));
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 20px 18px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.head h3 {
  font-size: 1.05rem;
  font-weight: 600;
}

.x {
  background: none;
  border: none;
  color: var(--text2);
  font-size: 1rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}

.x:hover {
  background: var(--surface2);
  color: var(--text);
}

.body {
  display: grid;
  grid-template-columns: 230px 1fr;
  gap: 18px;
  min-height: 0;
  flex: 1;
}

/* ── List ── */
.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  border-right: 1px solid var(--border);
  padding-right: 14px;
}

.search {
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 0.85rem;
}

.new-row {
  display: flex;
  gap: 6px;
}

.new {
  flex: 1;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  cursor: pointer;
  font-weight: 600;
  font-size: 0.8rem;
}

.new:hover {
  border-color: var(--text2);
}

.items {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-height: 0;
  overflow-y: auto;
}

.list-head {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text2);
  padding: 8px 8px 3px;
}

.item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 8px;
  border: none;
  background: none;
  color: var(--text2);
  text-align: left;
  cursor: pointer;
  font-size: 0.85rem;
}

.item:hover {
  background: var(--surface2);
  color: var(--text);
}

.item.active {
  background: rgba(108, 92, 231, 0.18);
  color: var(--text);
}

.item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.count {
  font-size: 0.72rem;
  color: var(--text2);
}

.empty {
  font-size: 0.8rem;
  color: var(--text2);
  padding: 6px 8px;
}

/* ── Editor ── */
.editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
}

.editing {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text2);
}

.name {
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 600;
}

.editor textarea {
  flex: 1;
  min-height: 160px;
  resize: none;
  padding: 10px;
  border-radius: 8px;
  line-height: 1.5;
}

.members {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-content: flex-start;
  max-height: 40%;
  overflow-y: auto;
}

.chip {
  display: inline-flex;
  align-items: center;
  max-width: 240px;
  gap: 6px;
  padding: 3px 4px 3px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface2);
  font-size: 0.8rem;
}

.chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-x {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  font-size: 0.7rem;
  padding: 2px 5px;
  border-radius: 999px;
}

.chip-x:hover {
  background: var(--border);
  color: var(--text);
}

.adder {
  position: relative;
}

.adder input {
  width: 100%;
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 0.85rem;
}

.adder-menu {
  position: absolute;
  z-index: 5;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  max-height: 220px;
  overflow-y: auto;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  padding-top: 6px;
}

.actions .btn {
  padding: 8px 16px;
}

.spacer {
  flex: 1;
}

@media (max-width: 640px) {
  .dialog {
    height: calc(100vh - 32px);
  }

  .body {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }

  .list {
    border-right: none;
    border-bottom: 1px solid var(--border);
    padding: 0 0 10px;
    max-height: 200px;
  }
}
</style>
