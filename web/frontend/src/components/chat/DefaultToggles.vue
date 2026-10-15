<script setup>
import { computed, onMounted } from 'vue'
import { useChatDefaults } from '../../composables/useChatDefaults'

// "Add to defaults" toggles for the item being managed: always a global one,
// plus a space one when a chat in a space is currently in context. Reads and
// writes the shared settings buckets directly.
const props = defineProps({
  kind: { type: String, required: true }, // 'character' | 'instruction' | 'instruction_group'
  itemId: { type: Number, default: null }, // null = unsaved (toggles disabled)
})

const { currentSpace, inGlobal, inSpace, toggleGlobal, toggleSpace, ensureLoaded } = useChatDefaults()
onMounted(ensureLoaded)
const onGlobal = computed(() => props.itemId != null && inGlobal(props.kind, props.itemId))
const onSpace = computed(() => props.itemId != null && inSpace(props.kind, props.itemId))
</script>

<template>
  <div class="def-toggles">
    <label class="check" :class="{ disabled: itemId == null }">
      <input type="checkbox" :checked="onGlobal" :disabled="itemId == null" @change="toggleGlobal(kind, itemId)" />
      Add to global defaults <span class="hint">· all new chats</span>
    </label>
    <label v-if="currentSpace" class="check" :class="{ disabled: itemId == null }">
      <input type="checkbox" :checked="onSpace" :disabled="itemId == null" @change="toggleSpace(kind, itemId)" />
      Add to “{{ currentSpace.name }}” defaults <span class="hint">· new chats in this space</span>
    </label>
    <p v-if="itemId == null" class="save-first">Save it first to add it to defaults.</p>
  </div>
</template>

<style scoped>
.def-toggles {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.check {
  display: flex;
  align-items: center;
  gap: 6px;
  text-transform: none;
  letter-spacing: 0;
  font-size: 0.82rem;
  color: var(--text);
  cursor: pointer;
}

.check.disabled {
  color: var(--text2);
  cursor: default;
}

.hint {
  color: var(--text2);
  font-size: 0.75rem;
}

.save-first {
  font-size: 0.75rem;
  color: var(--text2);
}
</style>
