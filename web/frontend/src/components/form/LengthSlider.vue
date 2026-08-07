<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Number, default: 10 },
  lengths: { type: Array, required: true }
})

const emit = defineEmits(['update:modelValue'])

// Long contiguous ranges (e.g. 4-30s) render as a slider instead of a button per value.
const isRange = computed(() => props.lengths.length > 15)
const min = computed(() => props.lengths[0])
const max = computed(() => props.lengths[props.lengths.length - 1])

function selectLength(len) {
  emit('update:modelValue', len)
}

function onSlide(event) {
  emit('update:modelValue', Number(event.target.value))
}
</script>

<template>
  <div class="length-picker-group">
    <label class="field-label">
      Length
      <span v-if="isRange" class="length-value">{{ modelValue }}s</span>
    </label>

    <input
      v-if="isRange"
      type="range"
      class="length-range"
      :min="min"
      :max="max"
      step="1"
      :value="modelValue"
      @input="onSlide"
    />
    <div v-else class="length-picker">
      <button
        v-for="len in lengths"
        :key="len"
        type="button"
        :class="['length-btn', { active: modelValue === len }]"
        @click="selectLength(len)"
      >
        {{ len }}s
      </button>
    </div>
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

.length-picker {
  display: flex;
  background: linear-gradient(145deg, rgba(25, 25, 30, 0.95), rgba(20, 20, 25, 0.98));
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-radius: 10px;
  padding: 4px;
  gap: 2px;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
}

.length-btn {
  padding: 7px 12px;
  background: transparent;
  border: none;
  border-radius: 7px;
  color: var(--text2);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.length-btn:hover {
  color: var(--text);
  background: rgba(255, 255, 255, 0.05);
}

.length-btn.active {
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  color: white;
  box-shadow:
    0 2px 8px rgba(108, 92, 231, 0.3),
    inset 0 1px 1px rgba(255, 255, 255, 0.1);
}
</style>
