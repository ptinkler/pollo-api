<script setup>
const props = defineProps({
  modelValue: { type: Number, default: 10 },
  lengths: { type: Array, required: true }
})

const emit = defineEmits(['update:modelValue'])

function selectLength(len) {
  emit('update:modelValue', len)
}
</script>

<template>
  <div class="length-picker-group">
    <label class="field-label">Length</label>
    <div class="length-picker">
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
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
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
