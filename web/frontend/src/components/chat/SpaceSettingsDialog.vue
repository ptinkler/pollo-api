<script setup>
import { computed, inject, nextTick, ref, watch } from 'vue'
import BaseDialog from '../BaseDialog.vue'
import CharacterPicker from '../characters/CharacterPicker.vue'
import InstructionPicker from './InstructionPicker.vue'
import { createSpace, deleteSpace, updateSettings, updateSpace } from '../../composables/useChat'
import { sameIds } from '../../utils/defaults'

// Settings for one bucket of new-chat defaults: a space (its name, and the
// characters and instructions chats made in it start with), a new space, or
// the global defaults every new chat starts with. Saving closes it; emits
// `changed` with what was saved so the list can reload.
const props = defineProps({
  target: { type: [Object, String], default: null }, // a space | 'new' | 'global' | null (closed)
  globalSettings: { type: Object, default: () => ({}) },
  characters: { type: Array, default: () => [] },
  instructions: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'changed'])
const showToast = inject('showToast', () => {})

const name = ref('')
const charIds = ref([])
const snippetIds = ref([])
const groupIds = ref([])
const saving = ref(false)
const nameInput = ref(null)

const isGlobal = computed(() => props.target === 'global')
const isNew = computed(() => props.target === 'new')
const title = computed(() =>
  isGlobal.value ? 'Defaults for every chat' : isNew.value ? 'New space' : `“${props.target?.name}” settings`,
)

const bucket = computed(() => (isGlobal.value ? props.globalSettings : isNew.value ? null : props.target))
const bucketLists = b => ({
  chars: b?.default_character_ids || [],
  snippets: b?.default_instruction_ids || [],
  groups: b?.default_instruction_group_ids || [],
})
const listsChanged = computed(() => {
  const was = bucketLists(bucket.value)
  return (
    !sameIds(charIds.value, was.chars) ||
    !sameIds(snippetIds.value, was.snippets) ||
    !sameIds(groupIds.value, was.groups)
  )
})
const nameChanged = computed(() => !isGlobal.value && name.value.trim() !== (bucket.value?.name || ''))
const dirty = computed(() => nameChanged.value || listsChanged.value)

watch(
  () => props.target,
  async t => {
    if (!t) return
    const lists = bucketLists(bucket.value)
    name.value = bucket.value?.name || ''
    charIds.value = [...lists.chars]
    snippetIds.value = [...lists.snippets]
    groupIds.value = [...lists.groups]
    if (!isGlobal.value) {
      await nextTick()
      nameInput.value?.focus()
    }
  },
)

function close() {
  if (!dirty.value || confirm('Discard unsaved changes?')) emit('close')
}

async function save() {
  const lists = {
    default_character_ids: charIds.value,
    default_instruction_ids: snippetIds.value,
    default_instruction_group_ids: groupIds.value,
  }
  if (!isGlobal.value && !name.value.trim()) return showToast('Give the space a name', 'error')
  saving.value = true
  try {
    const data = { name: name.value.trim(), ...lists }
    const saved = isGlobal.value
      ? await updateSettings(lists)
      : isNew.value
        ? await createSpace(data)
        : await updateSpace(props.target.id, data)
    emit('changed', saved)
    emit('close')
  } catch (e) {
    showToast(`Save failed: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!confirm(`Delete the space “${props.target.name}”? Its chats are kept and move to Chats.`)) return
  try {
    await deleteSpace(props.target.id)
    emit('changed', null)
    emit('close')
  } catch (e) {
    showToast(`Delete failed: ${e.message}`, 'error')
  }
}
</script>

<template>
  <BaseDialog :open="!!target" :title="title" form @close="close" @submit="save">
    <p class="sub">
      <template v-if="isGlobal">Every chat uses these characters and instructions.</template>
      <template v-else>Every chat in this space uses these, on top of the ones for all chats.</template>
    </p>

    <template v-if="!isGlobal">
      <label for="space-name">Name</label>
      <input id="space-name" ref="nameInput" v-model="name" maxlength="255" placeholder="e.g. Fantasy novel" />
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

    <template #actions>
      <button v-if="!isGlobal && !isNew" type="button" class="btn btn-danger" @click="remove">Delete space</button>
      <span class="spacer"></span>
      <button type="button" class="btn btn-secondary" @click="close">Cancel</button>
      <button class="btn btn-primary" :disabled="saving || (!isNew && !dirty) || (!isGlobal && !name.trim())">
        {{ isNew ? 'Create space' : 'Save' }}
      </button>
    </template>
  </BaseDialog>
</template>

<style scoped>
.sub {
  font-size: 0.8rem;
  color: var(--text2);
  line-height: 1.45;
}

label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text2);
  margin-top: 6px;
}

input {
  padding: 8px 10px;
  border-radius: 8px;
}
</style>
