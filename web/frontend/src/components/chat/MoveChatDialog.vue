<script setup>
import { inject, nextTick, ref, watch } from 'vue'
import BaseDialog from '../BaseDialog.vue'
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
  <BaseDialog
    :open="!!conv"
    :title="conv ? `Move “${conv.title}”` : ''"
    label="Move chat"
    width="380px"
    @close="emit('close')"
  >
    <div v-if="conv" class="targets">
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
  </BaseDialog>
</template>

<style scoped>
.targets {
  display: flex;
  flex-direction: column;
  gap: 2px;
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
