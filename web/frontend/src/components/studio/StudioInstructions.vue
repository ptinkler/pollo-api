<!-- Inspector section: instructions attached to the thread (own + inherited). -->
<script setup>
import InstructionPicker from '../chat/InstructionPicker.vue'

defineProps({
  instructions: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
  snippetIds: { type: Array, default: () => [] },
  groupIds: { type: Array, default: () => [] },
  summary: { type: String, default: '' },
  inheritedSnippets: { type: Array, default: () => [] },
  inheritedGroups: { type: Array, default: () => [] },
  hiddenSnippets: { type: Array, default: () => [] },
  hiddenGroups: { type: Array, default: () => [] },
  pausedSnippets: { type: Array, default: () => [] },
  pausedGroups: { type: Array, default: () => [] },
})
defineEmits(['update:snippetIds', 'update:groupIds', 'manage', 'edit', 'hide', 'unhide', 'pause', 'resume'])
</script>

<template>
  <div class="isection">
    <div class="ilabel">Instructions</div>
    <InstructionPicker
      :instructions="instructions"
      :groups="groups"
      :snippet-ids="snippetIds"
      :group-ids="groupIds"
      :inherited-snippets="inheritedSnippets"
      :inherited-groups="inheritedGroups"
      :hidden-snippets="hiddenSnippets"
      :hidden-groups="hiddenGroups"
      :paused-snippets="pausedSnippets"
      :paused-groups="pausedGroups"
      @update:snippet-ids="$emit('update:snippetIds', $event)"
      @update:group-ids="$emit('update:groupIds', $event)"
      @manage="$emit('manage')"
      @edit="$emit('edit', $event)"
      @hide="$emit('hide', $event)"
      @unhide="$emit('unhide', $event)"
      @pause="$emit('pause', $event)"
      @resume="$emit('resume', $event)"
    />
    <div v-if="summary" class="attached">{{ summary }}</div>
  </div>
</template>

<style scoped>
.attached {
  margin-top: 8px;
  font-size: 12px;
  color: var(--smuted);
  line-height: 1.5;
}
</style>
