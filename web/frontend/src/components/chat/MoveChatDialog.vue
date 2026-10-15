<script setup>
import { inject, nextTick, ref, watch } from 'vue'
import { createSpace } from '../../composables/useChat'

// "Move to…": pick where a chat goes — Chats (no space) or a space — or make
// a new space and move it there. Emits `move` with the space id (null =
// Chats), and `space-created` so the list can reload its spaces.
const props = defineProps({
  conv: { type: Object, default: null }, // null = closed
  spaces: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'move', 'space-created'])
const showToast = inject('showToast', () => {})

const newName = ref('')
const creating = ref(false)
const naming = ref(false)
const nameInput = ref(null)

watch(
  () => props.conv,
  c => {
    if (c) {
      newName.value = ''
      naming.value = false
    }
  },
)

function pick(spaceId) {
  if ((props.conv.space_id ?? null) !== spaceId) emit('move', spaceId)
  emit('close')
}

async function startNaming() {
  naming.value = true
  await nextTick()
  nameInput.value?.focus()
}

async function createAndMove() {
  const name = newName.value.trim()
  if (!name || creating.value) return
  creating.value = true
  try {
    const space = await createSpace({
      name,
      default_character_ids: [],
      default_instruction_ids: [],
      default_instruction_group_ids: [],
    })
    emit('space-created', space)
    pick(space.id)
  } catch (e) {
    showToast(`Couldn't create the space: ${e.message}`, 'error')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="conv" class="backdrop" @click.self="emit('close')" @keydown.esc="emit('close')">
      <div class="dialog" role="dialog" aria-label="Move chat">
        <div class="head">
          <h3>Move “{{ conv.title }}”</h3>
          <button class="x" title="Close" @click="emit('close')">✕</button>
        </div>
        <div class="targets">
          <button class="target" :class="{ current: conv.space_id == null }" @click="pick(null)">
            <span class="icon">💬</span><span class="name">Chats</span>
            <span v-if="conv.space_id == null" class="here">here now</span>
          </button>
          <button
            v-for="s in spaces"
            :key="s.id"
            class="target"
            :class="{ current: conv.space_id === s.id }"
            @click="pick(s.id)"
          >
            <span class="icon">🗂</span><span class="name">{{ s.name }}</span>
            <span v-if="conv.space_id === s.id" class="here">here now</span>
          </button>
          <form v-if="naming" class="new-space" @submit.prevent="createAndMove">
            <input ref="nameInput" v-model="newName" maxlength="255" placeholder="New space name" />
            <button class="btn btn-primary" :disabled="!newName.trim() || creating">Create &amp; move</button>
          </form>
          <button v-else class="target add" @click="startNaming">
            <span class="icon">＋</span><span class="name">New space…</span>
          </button>
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
  width: min(380px, 100%);
  max-height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 16px 12px;
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.head h3 {
  flex: 1;
  min-width: 0;
  font-size: 1rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.targets {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.target {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: none;
  border-radius: 8px;
  background: none;
  color: var(--text);
  font-size: 0.88rem;
  text-align: left;
  cursor: pointer;
}

.target:hover {
  background: var(--surface2);
}

.target.current {
  color: var(--text2);
}

.target.add {
  color: var(--text2);
}

.target.add:hover {
  color: var(--text);
}

.icon {
  width: 18px;
  text-align: center;
}

.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.here {
  font-size: 0.7rem;
  color: var(--text2);
}

.new-space {
  display: flex;
  gap: 6px;
  padding: 6px 4px 2px;
}

.new-space input {
  flex: 1;
  min-width: 0;
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 0.85rem;
}

.new-space .btn {
  padding: 7px 12px;
  font-size: 0.82rem;
  white-space: nowrap;
}
</style>
