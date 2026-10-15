<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useChatDefaults } from '../../composables/useChatDefaults'

// "Default for" pills on the item being edited: all new chats, and — when a
// chat in a space is in context — new chats in that space. Part of the
// editor's form: picks are kept here (`dirty` reports them) until the editor
// saves and calls `commit(id)` with the saved item's id, so they work for new
// items too.
const props = defineProps({
  kind: { type: String, required: true }, // 'character' | 'instruction' | 'instruction_group'
  itemId: { type: Number, default: null }, // null = not saved yet
})
const emit = defineEmits(['update:dirty'])

const { currentSpace, inGlobal, inSpace, toggleGlobal, toggleSpace, ensureLoaded } = useChatDefaults()
const saved = computed(() => ({
  global: props.itemId != null && inGlobal(props.kind, props.itemId),
  space: props.itemId != null && inSpace(props.kind, props.itemId),
}))
const global = ref(false)
const space = ref(false)
const dirty = computed(
  () => global.value !== saved.value.global || (!!currentSpace.value && space.value !== saved.value.space),
)

function reset() {
  global.value = saved.value.global
  space.value = saved.value.space
}

onMounted(async () => {
  await ensureLoaded()
  reset()
})
watch(() => [props.kind, props.itemId, currentSpace.value?.id], reset)
watch(dirty, d => emit('update:dirty', d), { immediate: true })

// Write the picks for the saved item (the id it was saved under)
async function commit(id) {
  if (global.value !== inGlobal(props.kind, id)) await toggleGlobal(props.kind, id)
  if (currentSpace.value && space.value !== inSpace(props.kind, id)) await toggleSpace(props.kind, id)
}

defineExpose({ commit, dirty })
</script>

<template>
  <div class="def-toggles">
    <span class="label">Default for</span>
    <button
      type="button"
      class="pill"
      :class="{ on: global }"
      :aria-pressed="global"
      title="Add to every new chat"
      @click="global = !global"
    >
      🌐 All chats
    </button>
    <button
      v-if="currentSpace"
      type="button"
      class="pill"
      :class="{ on: space }"
      :aria-pressed="space"
      :title="`Add to new chats in ${currentSpace.name}`"
      @click="space = !space"
    >
      🗂 {{ currentSpace.name }}
    </button>
  </div>
</template>

<style scoped>
.def-toggles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text2);
  margin-right: 2px;
}

.pill {
  max-width: 220px;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: none;
  color: var(--text2);
  font-size: 0.78rem;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pill:hover {
  color: var(--text);
  border-color: var(--text2);
}

.pill.on {
  background: rgba(108, 92, 231, 0.22);
  border-color: var(--accent);
  color: var(--text);
}
</style>
