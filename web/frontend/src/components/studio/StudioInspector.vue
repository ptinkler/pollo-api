<!-- Studio right pane: composes the inspector section components (models,
     media options, instructions, characters) for the active thread. -->
<script setup>
import StudioModelSection from './StudioModelSection.vue'
import StudioMediaOptions from './StudioMediaOptions.vue'
import StudioAudioOptions from './StudioAudioOptions.vue'
import StudioContextSection from './StudioContextSection.vue'
import StudioInstructions from './StudioInstructions.vue'
import StudioCharacters from './StudioCharacters.vue'

defineProps({
  models: { type: Object, required: true },
  modelsLoading: { type: Boolean, default: false },
  collapsed: { type: Boolean, default: false },
  instructions: { type: Object, required: true }, // { list, groups, snippetIds, groupIds, summary }
  characters: { type: Object, required: true }, // { list, ids, names, support }
})
// StudioModelSection / StudioMediaOptions read composer settings via inject
defineEmits([
  'update:collapsed',
  'update:snippetIds',
  'update:groupIds',
  'manage',
  'edit-instruction',
  'instr-hide',
  'instr-unhide',
  'instr-pause',
  'instr-resume',
  'update:characterIds',
  'edit-character',
  'create-character',
  'char-hide',
  'char-unhide',
])
</script>

<template>
  <aside class="side" :class="{ collapsed }">
    <!-- The collapsed rail expands on click. -->
    <button
      class="rail"
      type="button"
      title="Expand inspector"
      aria-label="Expand inspector"
      @click="$emit('update:collapsed', false)"
    >
      <svg class="ic lg chev"><use href="#s-chevL" /></svg>
      <span class="rail-label">Inspector</span>
    </button>
    <div class="panel">
      <button class="panelhead" type="button" title="Collapse inspector" @click="$emit('update:collapsed', true)">
        <span class="brand">Inspector</span>
        <svg class="ic"><use href="#s-chev" /></svg>
      </button>
      <div class="pbody">
        <StudioModelSection :models="models" :loading="modelsLoading" />
        <StudioMediaOptions />
        <StudioAudioOptions />
        <StudioContextSection />
        <StudioInstructions
          :instructions="instructions.list"
          :groups="instructions.groups"
          :snippet-ids="instructions.snippetIds"
          :group-ids="instructions.groupIds"
          :summary="instructions.summary"
          :inherited-snippets="instructions.inheritedSnippets"
          :inherited-groups="instructions.inheritedGroups"
          :hidden-snippets="instructions.hiddenSnippets"
          :hidden-groups="instructions.hiddenGroups"
          :paused-snippets="instructions.pausedSnippets"
          :paused-groups="instructions.pausedGroups"
          @update:snippet-ids="$emit('update:snippetIds', $event)"
          @update:group-ids="$emit('update:groupIds', $event)"
          @manage="$emit('manage')"
          @edit="$emit('edit-instruction', $event)"
          @hide="$emit('instr-hide', $event)"
          @unhide="$emit('instr-unhide', $event)"
          @pause="$emit('instr-pause', $event)"
          @resume="$emit('instr-resume', $event)"
        />
        <StudioCharacters
          :characters="characters.list"
          :character-ids="characters.ids"
          :names="characters.names"
          :support="characters.support"
          :inherited="characters.inherited"
          :hidden="characters.hidden"
          @update:character-ids="$emit('update:characterIds', $event)"
          @edit="$emit('edit-character', $event)"
          @create="$emit('create-character')"
          @hide="$emit('char-hide', $event)"
          @unhide="$emit('char-unhide', $event)"
        />
      </div>
    </div>
  </aside>
</template>

<style scoped>
.side {
  width: 288px;
  background: var(--sbg);
  border-left: 1px solid var(--sborder);
}
.brand {
  font-weight: 600;
}
.pbody {
  flex: 1;
  overflow-y: auto;
  padding: 4px 14px 10px;
}
</style>
