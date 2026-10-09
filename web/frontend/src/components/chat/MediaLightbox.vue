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
        <button class="lightbox-animate" @click="emit('use-image', { file: item.file, mode: 'image' })">
          🖼 Make a picture from this
        </button>
        <button class="lightbox-animate" @click="emit('use-image', { file: item.file, mode: 'video' })">
          🎬 Make a video from this
        </button>
        <button class="lightbox-animate" @click="emit('make-character', item.file)">
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
  max-width: 100%;
  max-height: calc(100vh - 120px);
  object-fit: contain;
  border-radius: 8px;
  cursor: default;
}

.lightbox-actions {
  display: flex;
  gap: 8px;
}

.lightbox-animate {
  padding: 8px 16px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  color: white;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
}

.lightbox-caption {
  max-width: 720px;
  color: var(--text2);
  font-size: 0.85rem;
  text-align: center;
  cursor: text;
}
</style>
