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

const props = defineProps({
  open: { type: Boolean, default: false },
  instructions: { type: Array, default: () => [] }, // snippets
  groups: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'changed'])
const showToast = inject('showToast', () => {})

const tab = ref('snippets') // 'snippets' | 'groups'
const saving = ref(false)
const nameInput = ref(null)

// ── Snippet editor ───────────────────────────────────────────────────
const editingId = ref(null) // null = new
const name = ref('')
const content = ref('')
const isDefault = ref(false)

const snippetDirty = computed(() => {
  const cur = props.instructions.find(i => i.id === editingId.value)
  if (!cur) return !!(name.value.trim() || content.value.trim())
  return cur.name !== name.value || cur.content !== content.value || cur.is_default !== isDefault.value
})

function loadSnippet(item) {
  editingId.value = item?.id ?? null
  name.value = item?.name ?? ''
  content.value = item?.content ?? ''
  isDefault.value = item?.is_default ?? false
}

// ── Group editor ─────────────────────────────────────────────────────
const groupEditingId = ref(null)
const groupName = ref('')
const groupSnippetIds = ref([])
const groupIsDefault = ref(false)

const groupDirty = computed(() => {
  const cur = props.groups.find(g => g.id === groupEditingId.value)
  const ids = [...groupSnippetIds.value].sort()
  if (!cur) return !!(groupName.value.trim() || ids.length)
  const was = [...(cur.snippet_ids || [])].sort()
  return (
    cur.name !== groupName.value ||
    cur.is_default !== groupIsDefault.value ||
    ids.length !== was.length ||
    ids.some((x, i) => x !== was[i])
  )
})

function loadGroup(item) {
  groupEditingId.value = item?.id ?? null
  groupName.value = item?.name ?? ''
  groupSnippetIds.value = [...(item?.snippet_ids || [])]
  groupIsDefault.value = item?.is_default ?? false
}

function toggleMember(id) {
  groupSnippetIds.value = groupSnippetIds.value.includes(id)
    ? groupSnippetIds.value.filter(x => x !== id)
    : [...groupSnippetIds.value, id]
}

const snippetName = id => props.instructions.find(s => s.id === id)?.name ?? '(deleted)'

// ── Shared ───────────────────────────────────────────────────────────
const dirty = computed(() => (tab.value === 'snippets' ? snippetDirty.value : groupDirty.value))

function confirmDiscard() {
  return !dirty.value || confirm('Discard unsaved changes?')
}

function resetTab(which) {
  if (which === 'snippets') loadSnippet(props.instructions[0] || null)
  else loadGroup(props.groups[0] || null)
}

function switchTab(which) {
  if (which === tab.value || !confirmDiscard()) return
  tab.value = which
  resetTab(which)
}

function pick(item) {
  if (tab.value === 'snippets') {
    if (item?.id === editingId.value || !confirmDiscard()) return
    loadSnippet(item)
  } else {
    if (item?.id === groupEditingId.value || !confirmDiscard()) return
    loadGroup(item)
  }
}

function startNew() {
  if (!confirmDiscard()) return
  if (tab.value === 'snippets') loadSnippet(null)
  else loadGroup(null)
  nextTick(() => nameInput.value?.focus())
}

watch(
  () => props.open,
  open => {
    if (!open) return
    tab.value = 'snippets'
    resetTab('snippets')
    if (!props.instructions.length) nextTick(() => nameInput.value?.focus())
  },
)

async function save() {
  const isSnippet = tab.value === 'snippets'
  const label = isSnippet ? name.value : groupName.value
  if (!label.trim()) return showToast(`Give the ${isSnippet ? 'snippet' : 'group'} a name`, 'error')
  saving.value = true
  try {
    if (isSnippet) {
      const data = { name: name.value.trim(), content: content.value, is_default: isDefault.value }
      const saved =
        editingId.value == null ? await createInstruction(data) : await updateInstruction(editingId.value, data)
      emit('changed')
      loadSnippet(saved)
    } else {
      const data = {
        name: groupName.value.trim(),
        snippet_ids: groupSnippetIds.value,
        is_default: groupIsDefault.value,
      }
      const saved =
        groupEditingId.value == null
          ? await createInstructionGroup(data)
          : await updateInstructionGroup(groupEditingId.value, data)
      emit('changed')
      loadGroup(saved)
    }
  } catch (e) {
    showToast(`Save failed: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (tab.value === 'snippets') {
    if (editingId.value == null) return loadSnippet(null)
    if (!confirm(`Delete “${name.value}”? It's removed from any chats and groups using it.`)) return
    try {
      await deleteInstruction(editingId.value)
      emit('changed')
      loadSnippet(null)
    } catch (e) {
      showToast(`Delete failed: ${e.message}`, 'error')
    }
  } else {
    if (groupEditingId.value == null) return loadGroup(null)
    if (!confirm(`Delete group “${groupName.value}”? Its snippets are kept; chats using it are detached.`)) return
    try {
      await deleteInstructionGroup(groupEditingId.value)
      emit('changed')
      loadGroup(null)
    } catch (e) {
      showToast(`Delete failed: ${e.message}`, 'error')
    }
  }
}

function close() {
  if (confirmDiscard()) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="backdrop" @click.self="close" @keydown.esc="close">
      <div class="dialog" role="dialog" aria-label="Custom instructions">
        <div class="head">
          <h3>Custom instructions</h3>
          <button class="x" title="Close" @click="close">✕</button>
        </div>
        <p class="sub">
          Snippets are small reusable instructions; a group bundles complementary snippets. Attach any number of
          snippets and groups to a chat — all of them are sent to the chat model word for word. Flag any of them "add to
          new chats by default".
        </p>

        <div class="tabs">
          <button :class="{ on: tab === 'snippets' }" @click="switchTab('snippets')">Snippets</button>
          <button :class="{ on: tab === 'groups' }" @click="switchTab('groups')">Groups</button>
        </div>

        <div class="body">
          <aside class="list">
            <button class="new" @click="startNew">＋ New {{ tab === 'snippets' ? 'snippet' : 'group' }}</button>
            <template v-if="tab === 'snippets'">
              <button
                v-for="i in instructions"
                :key="i.id"
                class="item"
                :class="{ active: i.id === editingId }"
                @click="pick(i)"
              >
                <span class="item-name">{{ i.name }}</span>
                <span v-if="i.is_default" class="tag" title="Attached to new chats">default</span>
              </button>
              <p v-if="!instructions.length" class="empty">None saved yet</p>
            </template>
            <template v-else>
              <button
                v-for="g in groups"
                :key="g.id"
                class="item"
                :class="{ active: g.id === groupEditingId }"
                @click="pick(g)"
              >
                <span class="item-name">📦 {{ g.name }}</span>
                <span v-if="g.is_default" class="tag" title="Attached to new chats">default</span>
              </button>
              <p v-if="!groups.length" class="empty">No groups yet</p>
            </template>
          </aside>

          <section v-if="tab === 'snippets'" class="editor">
            <label for="ins-name">Name</label>
            <input id="ins-name" ref="nameInput" v-model="name" maxlength="255" placeholder="e.g. Terse tone" />
            <label for="ins-content">Instructions</label>
            <textarea
              id="ins-content"
              v-model="content"
              maxlength="20000"
              placeholder="A single idea — a tone, a format, a rule. Keep snippets small so they combine cleanly."
            ></textarea>
            <label class="check"> <input v-model="isDefault" type="checkbox" /> Add to new chats by default </label>
            <div class="actions">
              <button v-if="editingId != null" class="btn btn-danger" @click="remove">Delete</button>
              <span class="spacer"></span>
              <button class="btn btn-secondary" @click="close">Close</button>
              <button class="btn btn-primary" :disabled="saving || !snippetDirty || !name.trim()" @click="save">
                {{ editingId == null ? 'Save' : 'Save changes' }}
              </button>
            </div>
          </section>

          <section v-else class="editor">
            <label for="grp-name">Name</label>
            <input
              id="grp-name"
              ref="nameInput"
              v-model="groupName"
              maxlength="255"
              placeholder="e.g. Support replies"
            />
            <label>Snippets in this group</label>
            <div class="members">
              <label v-for="s in instructions" :key="s.id" class="member">
                <input type="checkbox" :checked="groupSnippetIds.includes(s.id)" @change="toggleMember(s.id)" />
                {{ s.name }}
              </label>
              <p v-if="!instructions.length" class="empty">Create snippets first, then group them here.</p>
            </div>
            <p v-if="groupSnippetIds.length" class="members-summary">
              Sends: {{ groupSnippetIds.map(snippetName).join(', ') }}
            </p>
            <label class="check">
              <input v-model="groupIsDefault" type="checkbox" /> Add to new chats by default
            </label>
            <div class="actions">
              <button v-if="groupEditingId != null" class="btn btn-danger" @click="remove">Delete</button>
              <span class="spacer"></span>
              <button class="btn btn-secondary" @click="close">Close</button>
              <button class="btn btn-primary" :disabled="saving || !groupDirty || !groupName.trim()" @click="save">
                {{ groupEditingId == null ? 'Save' : 'Save changes' }}
              </button>
            </div>
          </section>
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
  max-height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 20px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.head h3 {
  font-size: 1.1rem;
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

.sub {
  font-size: 0.8rem;
  color: var(--text2);
  margin: 6px 0 12px;
  line-height: 1.45;
}

.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
}

.tabs button {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: none;
  color: var(--text2);
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
}

.tabs button.on {
  background: rgba(108, 92, 231, 0.18);
  color: var(--text);
  border-color: var(--accent);
}

.body {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 16px;
  min-height: 0;
  flex: 1;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
  border-right: 1px solid var(--border);
  padding-right: 12px;
}

.new {
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  cursor: pointer;
  font-weight: 600;
  font-size: 0.82rem;
  margin-bottom: 4px;
}

.item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
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

.tag {
  font-size: 0.65rem;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--surface2);
  color: var(--accent2);
}

.empty {
  font-size: 0.8rem;
  color: var(--text2);
  padding: 8px 4px;
}

.editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.editor textarea {
  min-height: 220px;
  flex: 1;
  resize: vertical;
}

.members {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
}

.member {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 2px;
  font-size: 0.85rem;
  color: var(--text);
  cursor: pointer;
  text-transform: none;
  letter-spacing: 0;
}

.members-summary {
  font-size: 0.75rem;
  color: var(--text2);
  line-height: 1.4;
}

.check {
  display: flex;
  align-items: center;
  gap: 6px;
  text-transform: none;
  letter-spacing: 0;
  font-size: 0.82rem;
  color: var(--text);
  margin-top: 4px;
  cursor: pointer;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.actions .btn {
  padding: 8px 16px;
}

.spacer {
  flex: 1;
}

@media (max-width: 640px) {
  .body {
    grid-template-columns: 1fr;
  }

  .list {
    border-right: none;
    border-bottom: 1px solid var(--border);
    padding: 0 0 10px;
    max-height: 140px;
  }
}
</style>
