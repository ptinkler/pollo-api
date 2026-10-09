<script setup>
import { computed } from 'vue'
import { useFolded } from '../../composables/useFolded'

// A sidebar section's heading: its title folds the section away. Folded, it
// shows `summary` instead of the section (`summaryAlways`: shown either way);
// unfolded, the `actions` slot.
const props = defineProps({
  id: { type: String, required: true },
  title: { type: String, required: true },
  summary: { type: [String, Number], default: null },
  summaryAlways: { type: Boolean, default: false },
})

const { isFolded, toggleFold } = useFolded()
const folded = computed(() => isFolded(props.id))
</script>

<template>
  <div class="side-heading">
    <button class="fold" :class="{ folded }" @click="toggleFold(id)">{{ title }}</button>
    <span v-if="summary != null && (folded || summaryAlways)" class="heading-value">{{ summary }}</span>
    <slot v-else-if="!folded" name="actions" />
  </div>
</template>

<style scoped>
.side-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text2);
  padding: 8px 2px 0;
}

.fold {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: none;
  border: none;
  padding: 2px 0;
  color: inherit;
  font: inherit;
  text-transform: inherit;
  letter-spacing: inherit;
  cursor: pointer;
  white-space: nowrap;
}

.fold::before {
  content: '▾';
  font-size: 0.8rem;
  transition: transform 0.15s;
}

.fold.folded::before {
  transform: rotate(-90deg);
}

.fold:hover {
  color: var(--text);
}

.heading-value {
  text-transform: none;
  letter-spacing: 0;
  color: var(--text);
  font-size: 0.75rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  margin-left: 8px;
}
</style>
