<script setup>
import { useFolded } from '../../composables/useFolded'
import FoldHeading from './FoldHeading.vue'

// A foldable sidebar section: a FoldHeading over the default slot
defineProps({
  id: { type: String, required: true },
  title: { type: String, required: true },
  summary: { type: [String, Number], default: null },
  summaryAlways: { type: Boolean, default: false },
})

const { isFolded } = useFolded()
</script>

<template>
  <div class="side-section">
    <FoldHeading :id="id" :title="title" :summary="summary" :summary-always="summaryAlways">
      <template #actions><slot name="actions" /></template>
    </FoldHeading>
    <div v-show="!isFolded(id)" class="side-body"><slot /></div>
  </div>
</template>

<style scoped>
.side-section,
.side-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
