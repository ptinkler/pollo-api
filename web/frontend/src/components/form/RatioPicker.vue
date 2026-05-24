<script setup>
const props = defineProps({
  modelValue: { type: String, default: '' },
  ratios: { type: Array, required: true }
})

const emit = defineEmits(['update:modelValue'])

const RATIO_ICONS = {
  '1:1': [18, 18],
  '4:3': [20, 15],
  '3:4': [15, 20],
  '16:9': [22, 12],
  '9:16': [12, 22],
  '21:9': [26, 11],
}

function selectRatio(ratio) {
  emit('update:modelValue', ratio)
}

function getIconSize(ratio) {
  const [w, h] = RATIO_ICONS[ratio] || [16, 16]
  return { width: `${w}px`, height: `${h}px` }
}
</script>

<template>
  <div class="ratio-picker">
    <button
      v-for="ratio in ratios"
      :key="ratio"
      type="button"
      :class="['ratio-btn', { active: modelValue === ratio }]"
      :title="ratio"
      @click="selectRatio(ratio)"
    >
      <div class="ratio-icon" :style="getIconSize(ratio)"></div>
      <span class="ratio-label">{{ ratio }}</span>
    </button>
  </div>
</template>

<style scoped>
.ratio-picker {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.ratio-btn {
  width: 44px;
  height: 44px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  background: linear-gradient(145deg, rgba(30, 30, 35, 0.9), rgba(25, 25, 30, 0.95));
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.25s ease;
  position: relative;
  box-shadow:
    inset 0 1px 2px rgba(0, 0, 0, 0.2),
    0 1px 0 rgba(255, 255, 255, 0.03);
}

.ratio-btn:hover {
  border-color: rgba(255, 255, 255, 0.12);
  background: linear-gradient(145deg, rgba(40, 38, 50, 0.9), rgba(32, 30, 40, 0.95));
}

.ratio-btn.active {
  border-color: rgba(108, 92, 231, 0.5);
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  box-shadow:
    0 0 0 2px rgba(108, 92, 231, 0.2),
    0 4px 12px rgba(108, 92, 231, 0.25),
    inset 0 1px 1px rgba(255, 255, 255, 0.1);
}

.ratio-icon {
  background: rgba(255, 255, 255, 0.25);
  border-radius: 2px;
  transition: all 0.2s;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.ratio-btn:hover .ratio-icon {
  background: rgba(255, 255, 255, 0.35);
}

.ratio-btn.active .ratio-icon {
  background: rgba(255, 255, 255, 0.9);
  border-color: transparent;
  box-shadow: 0 0 8px rgba(255, 255, 255, 0.3);
}

.ratio-label {
  position: absolute;
  bottom: -18px;
  font-size: 0.62rem;
  font-weight: 500;
  color: var(--text2);
  white-space: nowrap;
  opacity: 0.6;
  transition: all 0.2s;
}

.ratio-btn.active .ratio-label {
  color: var(--accent2);
  opacity: 1;
}
</style>
