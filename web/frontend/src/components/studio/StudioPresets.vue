<!-- Models header: pick a saved preset to load it, or save the current setup. -->
<script setup>
import { inject, ref } from 'vue'
import { useRouter } from 'vue-router'
import PresetEditor from './PresetEditor.vue'

const { presets, loadPreset, activePresetId } = inject('composerSettings')
const router = useRouter()
const creating = ref(false)

// The box shows the preset the setup matches; change anything and it goes back
// to "Presets". Choosing one loads it.
async function onPick(e) {
  const select = e.target
  const value = select.value
  if (value === '__manage') {
    select.value = activePresetId.value
    return router.push('/presets')
  }
  const preset = presets.value.find(p => p.id === value)
  if (preset) await loadPreset(preset)
  select.value = activePresetId.value // not matching after all (an option got adjusted): back to the prompt
}
</script>

<template>
  <div class="presets">
    <label class="ifield">
      <span class="fcap">Preset</span>
      <select :value="activePresetId" aria-label="Presets" @change="onPick">
        <option value="">{{ presets.length ? 'None' : 'None saved yet' }}</option>
        <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
        <option value="__manage">Manage presets…</option>
      </select>
    </label>
    <button class="add" title="Save the current models and options as a preset" @click="creating = true">+</button>
    <PresetEditor :open="creating" @close="creating = false" />
  </div>
</template>

<style scoped>
.presets {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}
.presets .ifield {
  flex: 1;
  min-width: 0;
}
.add {
  width: 30px;
  flex: 0 0 auto;
  border: 1px solid var(--sborder);
  border-radius: var(--r);
  background: var(--spanel2);
  color: var(--smuted);
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
}
.add:hover {
  border-color: var(--saccent);
  color: var(--saccent);
}
</style>
