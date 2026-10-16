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

// Edit one instruction snippet or group (a group bundles snippets), or make a
// new one — the instruction counterpart of CharacterEditor. The full list
// lives on the Instructions page. Saving or deleting closes it.
const props = defineProps({
  // { kind: 'snippet' | 'group', id } — id null for a new one; null = closed
  target: { type: Object, default: null },
  instructions: { type: Array, default: () => [] }, // every snippet (a group's are picked from them)
  groups: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'changed'])
const showToast = inject('showToast', () => {})

const name = ref('')
const content = ref('') // snippet
const memberIds = ref([]) // group
const memberQuery = ref('')
const saving = ref(false)
const nameInput = ref(null)
const toggles = ref(null) // the "Default for" pills, saved along with the rest
const defaultsDirty = ref(false)

const isGroup = computed(() => props.target?.kind === 'group')
const editingId = computed(() => props.target?.id ?? null)
const current = computed(() =>
  editingId.value == null
    ? null
    : (isGroup.value ? props.groups : props.instructions).find(x => x.id === editingId.value),
)
const title = computed(() =>
  editingId.value == null ? `New ${isGroup.value ? 'group' : 'snippet'}` : isGroup.value ? 'Group' : 'Snippet',
)

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
const fieldsDirty = computed(() => {
  const cur = current.value
  if (!cur) return !!(name.value.trim() || content.value.trim() || memberIds.value.length)
  if (cur.name !== name.value) return true
  return isGroup.value ? !sameIds(memberIds.value, cur.snippet_ids || []) : cur.content !== content.value
})
const dirty = computed(() => fieldsDirty.value || defaultsDirty.value)

watch(
  () => props.target,
  async t => {
    if (!t) return
    const item = current.value
    name.value = item?.name ?? ''
    content.value = item?.content ?? ''
    memberIds.value = [...(item?.snippet_ids || [])]
    memberQuery.value = ''
    if (!item) {
      await nextTick()
      nameInput.value?.focus()
    }
  },
)

async function save() {
  if (!name.value.trim() || saving.value) return
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
    emit('changed', { kind: props.target.kind, item: saved })
    emit('close')
  } catch (e) {
    showToast(`Save failed: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function remove() {
  const what = isGroup.value
    ? `the group “${current.value.name}”? Its snippets are kept.`
    : `“${current.value.name}”? It's also taken out of chats, groups and defaults.`
  if (!confirm(`Delete ${what}`)) return
  try {
    await (isGroup.value ? deleteInstructionGroup : deleteInstruction)(editingId.value)
    emit('changed', { kind: props.target.kind, item: null })
    emit('close')
  } catch (e) {
    showToast(`Delete failed: ${e.message}`, 'error')
  }
}

function close() {
  if (!dirty.value || confirm('Discard unsaved changes?')) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="target" class="backdrop" @click.self="close" @keydown.esc="close">
      <form class="dialog" role="dialog" :aria-label="title" @submit.prevent="save">
        <div class="head">
          <h3>{{ title }}</h3>
          <button type="button" class="x" title="Close" @click="close">✕</button>
        </div>

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
            <span v-if="!members.length" class="empty">No snippets in it yet</span>
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
                <span class="dot" :style="{ background: instructionColor(s.name) }"></span>
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
          <button v-if="current" type="button" class="btn btn-danger" @click="remove">Delete</button>
          <span class="spacer"></span>
          <button type="button" class="btn btn-secondary" @click="close">Cancel</button>
          <button class="btn btn-primary" :disabled="saving || !dirty || !name.trim()">
            {{ current ? 'Save' : 'Create' }}
          </button>
        </div>
      </form>
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
  width: min(540px, 100%);
  max-height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 20px 18px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.head h3 {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text2);
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

.name {
  padding: 9px 11px;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
}

textarea {
  min-height: 220px;
  resize: vertical;
  padding: 10px 11px;
  border-radius: 8px;
  line-height: 1.5;
}

.members {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 200px;
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

.chip-name,
.item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-name {
  flex: 1;
}

.dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
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

.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: none;
  color: var(--text);
  text-align: left;
  font-size: 0.85rem;
  cursor: pointer;
}

.item:hover {
  background: var(--surface2);
}

.empty {
  font-size: 0.8rem;
  color: var(--text2);
  padding: 4px 2px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 4px;
}

.actions .btn {
  padding: 8px 16px;
}

.spacer {
  flex: 1;
}
</style>
