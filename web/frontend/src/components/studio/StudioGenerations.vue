<!-- The thread's Generations gallery: every image/video it produced, newest
     first, as a simple thumbnail grid. Clicking one opens the lightbox. -->
<script setup>
import { computed } from 'vue'
import { chatMediaUrl, chatMediaPreviewUrl } from '../../composables/useChat'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  convId: { type: [String, Number], default: '' },
})

const emit = defineEmits(['open-media'])

// Flatten all finished media across the thread's messages, newest first.
const items = computed(() => {
  const out = []
  for (const m of props.messages) {
    for (const item of m.media || []) {
      if (item.file && (item.kind === 'image' || item.kind === 'video')) out.push(item)
    }
  }
  return out.reverse()
})

const src = item => chatMediaUrl(props.convId, item.file)
const preview = item => chatMediaPreviewUrl(props.convId, item.file)

function open(item) {
  emit('open-media', { url: src(item), kind: item.kind, prompt: item.prompt, file: item.file })
}
</script>

<template>
  <div class="gens">
    <div v-if="!items.length" class="empty">No generations in this thread yet.</div>
    <div v-else class="grid">
      <button
        v-for="(item, i) in items"
        :key="item.file + i"
        type="button"
        class="cell"
        :title="item.prompt || item.file"
        @click="open(item)"
      >
        <img v-if="item.kind === 'image'" :src="preview(item)" loading="lazy" alt="" />
        <video v-else :src="src(item)" preload="metadata" muted playsinline></video>
        <span v-if="item.kind === 'video'" class="vtag">▶</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.gens {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.empty {
  color: var(--smuted);
  text-align: center;
  padding: 40px 0;
  font-size: 0.9rem;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 10px;
}
.cell {
  position: relative;
  aspect-ratio: 1;
  border: 1px solid var(--sborder);
  border-radius: 10px;
  overflow: hidden;
  background: var(--sbg2);
  cursor: pointer;
  padding: 0;
}
.cell:hover {
  border-color: var(--saccent);
}
.cell img,
.cell video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.vtag {
  position: absolute;
  bottom: 6px;
  right: 6px;
  font-size: 0.7rem;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  border-radius: 4px;
  padding: 1px 6px;
}
</style>
