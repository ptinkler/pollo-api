<!-- Inspector section: how much history + how many recent images each turn
     sends (the composer's memory/image sliders). -->
<script setup>
import { inject, computed } from 'vue'
import { MEMORY_STEPS, IMAGE_STEPS } from '../../composables/useComposerSettings'

const { mode, memoryIndex, imageIndex, historyLimit, imageLimit } = inject('composerSettings')

const label = v => (v == null ? 'All' : v)
// The filled part of the track, so these read like the video Length slider
const pct = (i, steps) => `${steps.length > 1 ? (i / (steps.length - 1)) * 100 : 0}%`
const memoryFill = computed(() => pct(memoryIndex.value, MEMORY_STEPS))
const imageFill = computed(() => pct(imageIndex.value, IMAGE_STEPS))
</script>

<template>
  <div v-if="mode !== 'video'" class="isection">
    <div class="ilabel">Context</div>

    <div v-if="mode === 'auto' || mode === 'text'" class="slider">
      <div class="srow">
        <span>Memory</span>
        <span class="sval">{{ label(historyLimit) }} {{ historyLimit === 1 ? 'message' : 'messages' }}</span>
      </div>
      <input
        v-model.number="memoryIndex"
        class="srange"
        type="range"
        min="0"
        :max="MEMORY_STEPS.length - 1"
        :style="{ '--fill': memoryFill }"
      />
    </div>

    <div class="slider">
      <div class="srow">
        <span>Images sent</span>
        <span class="sval">{{ imageLimit === 0 ? 'None' : label(imageLimit) }}</span>
      </div>
      <input
        v-model.number="imageIndex"
        class="srange"
        type="range"
        min="0"
        :max="IMAGE_STEPS.length - 1"
        :style="{ '--fill': imageFill }"
      />
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
  margin-bottom: 4px;
  color: var(--smuted);
  font-size: 12.5px;
}
.sval {
  color: var(--saccent);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
