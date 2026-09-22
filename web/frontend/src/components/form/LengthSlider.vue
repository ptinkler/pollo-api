<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Number, default: 10 },
  lengths: { type: Array, required: true }
})

const emit = defineEmits(['update:modelValue'])

// Unique id so multiple sliders on one page don't share tick marks.
const ticksId = `length-ticks-${Math.random().toString(36).slice(2)}`

// The slider steps through indices into `lengths`, not raw seconds — this
// keeps every stop a valid value even when lengths has gaps (e.g. pollo25's
// [4,5,...,12,15] skips 13 and 14) or as few as two entries (e.g. [5, 10]).
const maxIndex = computed(() => props.lengths.length - 1)

const currentIndex = computed(() => {
  const i = props.lengths.indexOf(props.modelValue)
  return i === -1 ? 0 : i
})

function onSlide(event) {
  emit('update:modelValue', props.lengths[Number(event.target.value)])
}
</script>

<template>
  <div class="length-picker-group">
    <label class="field-label">
      Length
      <span class="length-value">{{ modelValue }}s</span>
    </label>

    <input
      type="range"
      class="length-range"
      min="0"
      :max="maxIndex"
      step="1"
      :list="ticksId"
      :value="currentIndex"
      @input="onSlide"
    />
    <datalist :id="ticksId">
      <option v-for="(len, i) in lengths" :key="len" :value="i" :label="`${len}s`" />
    </datalist>
  </div>
</template>

<style scoped>
.length-picker-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.length-value {
  color: var(--text);
  font-weight: 700;
  letter-spacing: normal;
}

.length-range {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 34px;
  margin: 0;
  background: transparent;
  cursor: pointer;
}

.length-range::-webkit-slider-runnable-track {
  height: 6px;
  border-radius: 3px;
  background: linear-gradient(145deg, rgba(25, 25, 30, 0.95), rgba(20, 20, 25, 0.98));
  border: 1px solid rgba(255, 255, 255, 0.04);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
}

.length-range::-moz-range-track {
  height: 6px;
  border-radius: 3px;
  background: linear-gradient(145deg, rgba(25, 25, 30, 0.95), rgba(20, 20, 25, 0.98));
  border: 1px solid rgba(255, 255, 255, 0.04);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
}

.length-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  margin-top: -6px;
  border-radius: 50%;
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  box-shadow:
    0 2px 8px rgba(108, 92, 231, 0.4),
    inset 0 1px 1px rgba(255, 255, 255, 0.15);
  border: none;
}

.length-range::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  box-shadow:
    0 2px 8px rgba(108, 92, 231, 0.4),
    inset 0 1px 1px rgba(255, 255, 255, 0.15);
  border: none;
}
</style>
