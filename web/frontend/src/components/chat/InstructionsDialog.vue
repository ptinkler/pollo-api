<script setup>
import { ref, computed, watch, nextTick, inject } from 'vue'
import { createInstruction, updateInstruction, deleteInstruction } from '../../composables/useChat'

const props = defineProps({
  open: { type: Boolean, default: false },
  instructions: { type: Array, default: () => [] },
  selectId: { type: Number, default: null },   // open on this one
})
const emit = defineEmits(['close', 'changed'])
const showToast = inject('showToast', () => {})

const editingId = ref(null)   // null = new
const name = ref('')
const content = ref('')
const isDefault = ref(false)
const saving = ref(false)
const nameInput = ref(null)

const dirty = computed(() => {
  const cur = props.instructions.find(i => i.id === editingId.value)
  if (!cur) return !!(name.value.trim() || content.value.trim())
  return cur.name !== name.value || cur.content !== content.value || cur.is_default !== isDefault.value
})

function load(item) {
  editingId.value = item?.id ?? null
  name.value = item?.name ?? ''
  content.value = item?.content ?? ''
  isDefault.value = item?.is_default ?? false
}

function confirmDiscard() {
  return !dirty.value || confirm('Discard unsaved changes?')
}

function pick(item) {
  if (item?.id === editingId.value || !confirmDiscard()) return
  load(item)
}

function startNew() {
  if (!confirmDiscard()) return
  load(null)
  nextTick(() => nameInput.value?.focus())
}

watch(() => props.open, (open) => {
  if (!open) return
  load(props.instructions.find(i => i.id === props.selectId) || props.instructions[0] || null)
  if (!props.instructions.length) nextTick(() => nameInput.value?.focus())
})

async function save() {
  if (!name.value.trim()) return showToast('Give the instructions a name', 'error')
  saving.value = true
  try {
    const data = { name: name.value.trim(), content: content.value, is_default: isDefault.value }
    const saved = editingId.value == null
      ? await createInstruction(data)
      : await updateInstruction(editingId.value, data)
    emit('changed', { saved })
    load(saved)
  } catch (e) {
    showToast(`Save failed: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (editingId.value == null) return load(null)
  if (!confirm(`Delete “${name.value}”? Chats using it will no longer get these instructions.`)) return
  try {
    await deleteInstruction(editingId.value)
    emit('changed', { deleted: editingId.value })
    load(null)
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
      <div class="dialog" role="dialog" aria-label="Custom instructions">
        <div class="head">
          <h3>Custom instructions</h3>
          <button class="x" title="Close" @click="close">✕</button>
        </div>
        <p class="sub">
          Saved here and attached per chat. Sent word for word to the chat model, and to image models
          with the <em>context</em> badge. Prompt-only image models and video models don't receive them.
        </p>

        <div class="body">
          <aside class="list">
            <button class="new" @click="startNew">＋ New</button>
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
          </aside>

          <section class="editor">
            <label for="ins-name">Name</label>
            <input id="ins-name" ref="nameInput" v-model="name" maxlength="255" placeholder="e.g. Picture-book storyteller" />
            <label for="ins-content">Instructions</label>
            <textarea
              id="ins-content"
              v-model="content"
              maxlength="20000"
              placeholder="How should the model behave in chats that use this? Tone, format, things to always or never do…"
            ></textarea>
            <label class="check">
              <input v-model="isDefault" type="checkbox" /> Attach to new chats by default
            </label>
            <div class="actions">
              <button v-if="editingId != null" class="btn btn-danger" @click="remove">Delete</button>
              <span class="spacer"></span>
              <button class="btn btn-secondary" @click="close">Close</button>
              <button class="btn btn-primary" :disabled="saving || !dirty || !name.trim()" @click="save">
                {{ editingId == null ? 'Save' : 'Save changes' }}
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
  min-height: 260px;
  flex: 1;
  resize: vertical;
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
