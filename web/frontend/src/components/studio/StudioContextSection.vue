<!-- Inspector section: how much history + how many recent images each turn
     sends (the composer's memory/image sliders). -->
<script setup>
import { inject } from 'vue'
import { MEMORY_STEPS, IMAGE_STEPS } from '../../composables/useComposerSettings'

const { mode, memoryIndex, imageIndex, historyLimit, imageLimit } = inject('composerSettings')

const label = v => (v == null ? 'All' : v)
</script>

<template>
  <div class="isection">
    <div class="ilabel">Context</div>

    <div v-if="mode === 'auto' || mode === 'text'" class="slider">
      <div class="srow">
        <span>Memory</span>
        <span class="sval">{{ label(historyLimit) }} {{ historyLimit === 1 ? 'message' : 'messages' }}</span>
      </div>
      <input v-model.number="memoryIndex" type="range" min="0" :max="MEMORY_STEPS.length - 1" />
    </div>

    <div class="slider">
      <div class="srow">
        <span>Images sent</span>
        <span class="sval">{{ imageLimit === 0 ? 'None' : label(imageLimit) }}</span>
      </div>
      <input v-model.number="imageIndex" type="range" min="0" :max="IMAGE_STEPS.length - 1" />
    </div>
  </div>
</template>

<style scoped>
.slider + .slider {
  margin-top: 14px;
}
.srow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 7px;
  color: var(--smuted);
  font-size: 12.5px;
}
.sval {
  color: var(--sfg);
}
input[type='range'] {
  width: 100%;
  accent-color: var(--saccent);
}
</style>
