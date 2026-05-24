<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, required: true },
  options: { type: Array, required: true },
  hint: { type: String, default: '' }
})

const emit = defineEmits(['update:modelValue'])

const focused = ref(false)
const hasValue = computed(() => props.modelValue !== '' && props.modelValue !== null)

function getOptionValue(opt) {
  return typeof opt === 'object' ? opt.value : opt
}

function getOptionLabel(opt) {
  return typeof opt === 'object' ? opt.label : opt
}
</script>

<template>
  <div :class="['sleek-select', { focused, 'has-value': hasValue }]">
    <div class="field-header">
      <span class="field-label">{{ label }}</span>
      <span v-if="hint" class="field-hint">{{ hint }}</span>
    </div>
    <div class="select-wrapper">
      <select
        :value="modelValue"
        @change="emit('update:modelValue', $event.target.value)"
        @focus="focused = true"
        @blur="focused = false"
      >
        <option v-for="opt in options" :key="getOptionValue(opt)" :value="getOptionValue(opt)">
          {{ getOptionLabel(opt) }}
        </option>
      </select>
      <div class="select-arrow">
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
          <path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="focus-ring"></div>
    </div>
  </div>
</template>

<style scoped>
.sleek-select {
  margin-bottom: 8px;
}

.field-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.field-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  transition: color 0.2s;
}

.sleek-select.focused .field-label {
  color: var(--accent2);
}

.field-hint {
  font-size: 0.68rem;
  color: var(--text2);
  opacity: 0.5;
  font-weight: 400;
}

.select-wrapper {
  position: relative;
}

select {
  width: 100%;
  appearance: none;
  background: linear-gradient(145deg, rgba(30, 30, 35, 0.9), rgba(25, 25, 30, 0.95));
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  padding: 11px 38px 11px 14px;
  font-size: 0.9rem;
  color: var(--text);
  outline: none;
  cursor: pointer;
  transition: all 0.25s ease;
  box-shadow:
    inset 0 1px 2px rgba(0, 0, 0, 0.2),
    0 1px 0 rgba(255, 255, 255, 0.03);
}

select option {
  background: #1e1e23;
  color: var(--text);
  padding: 8px 14px;
}

select:hover {
  border-color: rgba(255, 255, 255, 0.1);
}

.select-arrow {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text2);
  pointer-events: none;
  transition: color 0.2s, transform 0.25s ease;
  opacity: 0.6;
}

.sleek-select.focused .select-arrow {
  color: var(--accent2);
  opacity: 1;
  transform: translateY(-50%) rotate(180deg);
}

.sleek-select.focused select {
  border-color: rgba(108, 92, 231, 0.5);
  background: linear-gradient(145deg, rgba(35, 32, 45, 0.95), rgba(28, 26, 38, 0.98));
  box-shadow:
    inset 0 1px 2px rgba(0, 0, 0, 0.15),
    0 0 0 3px rgba(108, 92, 231, 0.12),
    0 4px 16px rgba(108, 92, 231, 0.06);
}

.focus-ring {
  position: absolute;
  inset: -1px;
  border-radius: 11px;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s;
  background: linear-gradient(135deg, rgba(108, 92, 231, 0.12), transparent 50%);
}

.sleek-select.focused .focus-ring {
  opacity: 1;
}
</style>
