<script setup>
import { ref, computed, watch, nextTick, inject } from 'vue'
import CharacterPicker from '../characters/CharacterPicker.vue'
import InstructionPicker from './InstructionPicker.vue'
import { createSpace, updateSpace, deleteSpace, updateSettings } from '../../composables/useChat'

// Manage the default buckets: the Global defaults (every chat) and each space's
// own defaults (chats in that space). Each is a set of default characters and
// instruction snippets/groups.
const GLOBAL = 'global'
const props = defineProps({
  open: { type: Boolean, default: false },
  spaces: { type: Array, default: () => [] },
  globalSettings: { type: Object, default: () => ({}) },
  characters: { type: Array, default: () => [] },
  instructions: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'changed'])
const showToast = inject('showToast', () => {})

const editingId = ref(GLOBAL) // GLOBAL | space id | null (new space)
const name = ref('')
const charIds = ref([])
const snippetIds = ref([])
const groupIds = ref([])
const saving = ref(false)
const nameInput = ref(null)

const isGlobal = computed(() => editingId.value === GLOBAL)
const isNew = computed(() => editingId.value == null)
const sameIds = (a, b) => a.length === b.length && [...a].sort().every((x, i) => x === [...b].sort()[i])

// The three id-lists of a bucket (empty bucket when null)
const bucketLists = b => ({
  default_character_ids: b?.default_character_ids || [],
  default_instruction_ids: b?.default_instruction_ids || [],
  default_instruction_group_ids: b?.default_instruction_group_ids || [],
})

// The bucket currently being edited, from the props (null while creating)
const source = computed(() => {
  if (isGlobal.value) return props.globalSettings
  if (isNew.value) return null
  return props.spaces.find(s => s.id === editingId.value) || null
})

const listsDirty = computed(() => {
  const cur = bucketLists(source.value)
  return (
    !sameIds(cur.default_character_ids, charIds.value) ||
    !sameIds(cur.default_instruction_ids, snippetIds.value) ||
    !sameIds(cur.default_instruction_group_ids, groupIds.value)
  )
})

const dirty = computed(() => {
  if (isNew.value) return !!(name.value.trim() || listsDirty.value)
  const nameChanged = !isGlobal.value && source.value?.name !== name.value
  return nameChanged || listsDirty.value
})

function load(target) {
  // target: GLOBAL, a space object, or null (new space)
  const bucket = target === GLOBAL ? props.globalSettings : target
  const lists = bucketLists(bucket)
  editingId.value = target === GLOBAL ? GLOBAL : (target?.id ?? null)
  name.value = bucket && target !== GLOBAL ? bucket.name : ''
  charIds.value = [...lists.default_character_ids]
  snippetIds.value = [...lists.default_instruction_ids]
  groupIds.value = [...lists.default_instruction_group_ids]
}

function confirmDiscard() {
  return !dirty.value || confirm('Discard unsaved changes?')
}

function pickGlobal() {
  if (isGlobal.value || !confirmDiscard()) return
  load(GLOBAL)
}

function pick(space) {
  if (space.id === editingId.value || !confirmDiscard()) return
  load(space)
}

function startNew() {
  if (!confirmDiscard()) return
  load(null)
  nextTick(() => nameInput.value?.focus())
}

watch(
  () => props.open,
  open => {
    if (open) load(GLOBAL)
  },
)

async function save() {
  const lists = {
    default_character_ids: charIds.value,
    default_instruction_ids: snippetIds.value,
    default_instruction_group_ids: groupIds.value,
  }
  if (!isGlobal.value && !name.value.trim()) return showToast('Give the space a name', 'error')
  saving.value = true
  try {
    if (isGlobal.value) {
      await updateSettings(lists)
      emit('changed')
    } else {
      const data = { name: name.value.trim(), ...lists }
      const saved = isNew.value ? await createSpace(data) : await updateSpace(editingId.value, data)
      emit('changed')
      load(saved)
    }
  } catch (e) {
    showToast(`Save failed: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (isGlobal.value) return
  if (isNew.value) return load(GLOBAL)
  if (!confirm(`Delete space “${name.value}”? Its chats are kept but become unfiled.`)) return
  try {
    await deleteSpace(editingId.value)
    emit('changed')
    load(GLOBAL)
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
      <div class="dialog" role="dialog" aria-label="Spaces and defaults">
        <div class="head">
          <h3>Spaces &amp; defaults</h3>
          <button class="x" title="Close" @click="close">✕</button>
        </div>
        <p class="sub">
          Global defaults are added to every new chat. A space groups chats and adds its own defaults on top for chats
          created in it. Set the characters and instructions each should start with.
        </p>

        <div class="body">
          <aside class="list">
            <button class="item global" :class="{ active: isGlobal }" @click="pickGlobal">
              <span class="item-name">🌐 Global</span>
              <span class="tag">all chats</span>
            </button>
            <div class="list-head">Spaces</div>
            <button
              v-for="s in spaces"
              :key="s.id"
              class="item"
              :class="{ active: s.id === editingId }"
              @click="pick(s)"
            >
              <span class="item-name">{{ s.name }}</span>
            </button>
            <p v-if="!spaces.length" class="empty">No spaces yet</p>
            <button class="new" @click="startNew">＋ New space</button>
          </aside>

          <section class="editor">
            <template v-if="!isGlobal">
              <label for="sp-name">Name</label>
              <input id="sp-name" ref="nameInput" v-model="name" maxlength="255" placeholder="e.g. Fantasy novel" />
            </template>

            <label>Default characters</label>
            <CharacterPicker
              :model-value="charIds"
              :characters="characters"
              :allow-create="false"
              @update:model-value="charIds = $event"
            />

            <label>Default instructions</label>
            <InstructionPicker
              :instructions="instructions"
              :groups="groups"
              :snippet-ids="snippetIds"
              :group-ids="groupIds"
              :manageable="false"
              @update:snippet-ids="snippetIds = $event"
              @update:group-ids="groupIds = $event"
            />

            <div class="actions">
              <button v-if="!isGlobal && !isNew" class="btn btn-danger" @click="remove">Delete</button>
              <span class="spacer"></span>
              <button class="btn btn-secondary" @click="close">Close</button>
              <button class="btn btn-primary" :disabled="saving || !dirty || (!isGlobal && !name.trim())" @click="save">
                {{ isNew ? 'Create' : 'Save changes' }}
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
  width: min(760px, 100%);
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
  margin: 6px 0 14px;
  line-height: 1.45;
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

.empty {
  font-size: 0.8rem;
  color: var(--text2);
  padding: 8px 4px;
}

.list-head {
  font-size: 0.62rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text2);
  padding: 10px 4px 2px;
}

.item.global {
  font-weight: 600;
}

.tag {
  font-size: 0.6rem;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--surface2);
  color: var(--accent2);
}

.editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.editor label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text2);
  margin-top: 6px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
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
