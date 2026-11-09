<script setup>
import { onBeforeUnmount, onMounted } from 'vue'

// A chat image full size, with what can be made from it. `item`: { url, prompt?, file? }
const props = defineProps({
  item: { type: Object, default: null },
})
const emit = defineEmits(['close', 'use-image', 'make-character'])

function onKey(e) {
  if (e.key === 'Escape' && props.item) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div v-if="item" class="lightbox" @click="emit('close')">
      <img :src="item.url" alt="" @click.stop />
      <p v-if="item.prompt" class="lightbox-caption" @click.stop>{{ item.prompt }}</p>
      <div v-if="item.file" class="lightbox-actions" @click.stop>
        <button class="btn lightbox-btn" @click="emit('use-image', { file: item.file, mode: 'image' })">
          🖼 Make a picture from this
        </button>
        <button class="btn lightbox-btn" @click="emit('use-image', { file: item.file, mode: 'video' })">
          🎬 Make a video from this
        </button>
        <button class="btn lightbox-btn" @click="emit('make-character', item.file)">
          👤 Make a character from this
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  cursor: zoom-out;
}

.lightbox img {
  /* Shrinks to whatever the caption and actions leave, so nothing is pushed off-screen. */
  flex: 0 1 auto;
  min-height: 0;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 8px;
  cursor: default;
}

.lightbox-actions {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.lightbox-btn {
  background: rgba(20, 23, 29, 0.85);
  border-color: rgba(255, 255, 255, 0.18);
  color: #fff;
}
.lightbox-btn:hover:not(:disabled) {
  background: rgba(40, 45, 56, 0.95);
  border-color: rgba(255, 255, 255, 0.35);
}

.lightbox-caption {
  flex-shrink: 0;
  max-width: 720px;
  max-height: 25vh;
  overflow-y: auto;
  margin: 0;
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  text-align: center;
  cursor: text;
}
</style>
