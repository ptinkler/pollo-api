<!-- Tools → Presets: saved model + option sets, opened in the same kind of
     modal as characters. -->
<script setup>
import { inject, ref } from 'vue'
import PresetEditor from './PresetEditor.vue'
import { presetSummary } from '../../utils/presets'

defineEmits(['close'])
const { presets } = inject('composerSettings')

const editorOpen = ref(false)
const editing = ref(null)
function edit(p) {
  editing.value = p
  editorOpen.value = true
}
</script>

<template>
  <div class="page">
    <div class="pwrap">
      <div class="phead">
        <div>
          <h1>Presets</h1>
          <p class="sub">
            Saved sets of models and media options. Load one from the Presets box above the models in the inspector.
          </p>
        </div>
        <div class="hactions">
          <button class="btn btn-primary" @click="edit(null)">
            <svg class="ic"><use href="#s-plus" /></svg> New preset
          </button>
          <button class="btn" @click="$emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

      <div v-if="!presets.length" class="empty">No presets yet. Create one here, or save the current setup with +.</div>
      <div v-else class="grid">
        <button v-for="p in presets" :key="p.id" class="gcard card" @click="edit(p)">
          <h3>{{ p.name }}</h3>
          <p class="desc">{{ presetSummary(p) }}</p>
        </button>
      </div>
    </div>

    <PresetEditor :open="editorOpen" :preset="editing" @close="editorOpen = false" />
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 10px;
}
.card {
  padding: 10px 12px;
}
.card h3 {
  font-size: 13.5px;
  font-weight: 600;
}
.desc {
  font-size: 12px;
  color: var(--smuted);
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
