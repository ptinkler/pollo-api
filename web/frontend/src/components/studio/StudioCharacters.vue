<!-- Inspector section: characters attached to the thread (own + inherited). -->
<script setup>
import CharacterPicker from '../characters/CharacterPicker.vue'

defineProps({
  characters: { type: Array, default: () => [] },
  characterIds: { type: Array, default: () => [] },
  names: { type: String, default: '' },
  support: { type: Object, default: () => ({ ok: true }) },
  inherited: { type: Array, default: () => [] },
  hidden: { type: Array, default: () => [] },
})
defineEmits(['update:characterIds', 'edit', 'create', 'hide', 'unhide'])
</script>

<template>
  <div class="isection">
    <div class="ilabel">Characters</div>
    <p v-if="!support.ok" class="warn">{{ support.reason }}</p>
    <CharacterPicker
      v-else
      :model-value="characterIds"
      :characters="characters"
      :inherited="inherited"
      :hidden="hidden"
      create-label="＋ New character (this thread)"
      @update:model-value="$emit('update:characterIds', $event)"
      @edit="$emit('edit', $event)"
      @create="$emit('create')"
      @hide="$emit('hide', $event)"
      @unhide="$emit('unhide', $event)"
    />
    <div v-if="names" class="attached">{{ names }}</div>
  </div>
</template>

<style scoped>
.warn {
  font-size: 12px;
  color: var(--smuted);
  line-height: 1.5;
}
.attached {
  margin-top: 8px;
  font-size: 12px;
  color: var(--smuted);
  line-height: 1.5;
}
</style>
