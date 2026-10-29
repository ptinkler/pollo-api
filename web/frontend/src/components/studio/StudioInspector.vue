<!-- Studio right pane: composes the inspector section components (models,
     media options, instructions, characters) for the active thread. -->
<script setup>
import StudioModelSection from './StudioModelSection.vue'
import StudioMediaOptions from './StudioMediaOptions.vue'
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
    <div class="rail">
      <button class="rail-btn" title="Expand" @click="$emit('update:collapsed', false)">
        <svg class="ic lg"><use href="#s-chevL" /></svg>
      </button>
      <button class="rail-btn" title="Inspector" @click="$emit('update:collapsed', false)">
        <svg class="ic lg"><use href="#s-spark" /></svg>
      </button>
    </div>
    <div class="panel">
      <div class="phead">
        <button class="iconbtn" title="Collapse" @click="$emit('update:collapsed', true)">
          <svg class="ic"><use href="#s-chev" /></svg>
        </button>
        <span class="brand">Inspector</span>
      </div>
      <div class="pbody">
        <StudioModelSection :models="models" :loading="modelsLoading" />
        <StudioMediaOptions />
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
  position: relative;
  flex: 0 0 auto;
  width: 288px;
  background: var(--sbg);
  border-left: 1px solid var(--sborder);
  transition: width 0.2s;
}
.side.collapsed {
  width: 54px;
}
.rail {
  display: none;
}
.side.collapsed > .rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  height: 100%;
  padding: 12px 0;
  background: var(--srail);
}
.rail-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
}
.rail-btn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.side.collapsed > .panel {
  display: none;
}
.panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.phead {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px;
  border-bottom: 1px solid var(--sborder2);
}
.brand {
  font-weight: 600;
}
.iconbtn {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
}
.iconbtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.pbody {
  flex: 1;
  overflow-y: auto;
  padding: 10px 14px;
}
</style>
