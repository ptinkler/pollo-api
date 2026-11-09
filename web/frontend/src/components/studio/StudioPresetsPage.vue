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
          <button class="primary" @click="edit(null)">＋ New preset</button>
          <button class="closebtn" @click="$emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

      <div v-if="!presets.length" class="empty">No presets yet. Create one here, or save the current setup with +.</div>
      <div v-else class="grid">
        <button v-for="p in presets" :key="p.id" class="card" @click="edit(p)">
          <h3>{{ p.name }}</h3>
          <p class="desc">{{ presetSummary(p) }}</p>
        </button>
      </div>
    </div>

    <PresetEditor :open="editorOpen" :preset="editing" @close="editorOpen = false" />
  </div>
</template>

<style scoped>
.page {
  flex: 1;
  overflow-y: auto;
  padding: 32px 22px;
}
.pwrap {
  max-width: 820px;
  margin: 0 auto;
}
.phead {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}
h1 {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.02em;
}
.sub {
  font-size: 13px;
  color: var(--smuted);
  margin-top: 6px;
  line-height: 1.5;
  max-width: 560px;
}
.hactions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.primary {
  padding: 8px 14px;
  border: none;
  border-radius: 9px;
  background: var(--saccent);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}
.closebtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  color: var(--smuted);
  background: none;
  cursor: pointer;
}
.closebtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.empty {
  color: var(--smuted);
  font-size: 13px;
  padding: 20px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 14px;
}
.card {
  text-align: left;
  padding: 12px 14px;
  background: var(--sbg);
  border: 1px solid var(--sborder);
  border-radius: 12px;
  cursor: pointer;
}
.card:hover {
  border-color: var(--saccent);
}
.card h3 {
  font-size: 14px;
  font-weight: 600;
}
.desc {
  font-size: 12px;
  color: var(--smuted);
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
