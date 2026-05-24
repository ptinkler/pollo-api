<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, required: true },
  type: { type: String, default: 'text' },
  placeholder: { type: String, default: '' },
  hint: { type: String, default: '' }
})

const emit = defineEmits(['update:modelValue'])

const focused = ref(false)
const hasValue = computed(() => !!props.modelValue)
</script>

<template>
  <div :class="['sleek-input', { focused, 'has-value': hasValue }]">
    <div class="field-header">
      <span class="field-label">{{ label }}</span>
      <span v-if="hint" class="field-hint">{{ hint }}</span>
    </div>
    <div class="input-wrapper">
      <input
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        @input="emit('update:modelValue', $event.target.value)"
        @focus="focused = true"
        @blur="focused = false"
      />
      <div class="focus-ring"></div>
    </div>
  </div>
</template>

<style scoped>
.sleek-input {
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

.sleek-input.focused .field-label {
  color: var(--accent2);
}

.field-hint {
  font-size: 0.68rem;
  color: var(--text2);
  opacity: 0.5;
  font-weight: 400;
}

.input-wrapper {
  position: relative;
}

input {
  width: 100%;
  background: linear-gradient(145deg, rgba(30, 30, 35, 0.9), rgba(25, 25, 30, 0.95));
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  padding: 11px 14px;
  font-size: 0.9rem;
  color: var(--text);
  outline: none;
  transition: all 0.25s ease;
  box-shadow:
    inset 0 1px 2px rgba(0, 0, 0, 0.2),
    0 1px 0 rgba(255, 255, 255, 0.03);
}

input::placeholder {
  color: var(--text2);
  opacity: 0.35;
}

input:hover {
  border-color: rgba(255, 255, 255, 0.1);
}

.sleek-input.focused input {
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

.sleek-input.focused .focus-ring {
  opacity: 1;
}
</style>
