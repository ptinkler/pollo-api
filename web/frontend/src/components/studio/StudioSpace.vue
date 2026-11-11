<!-- Studio center pane when a space is opened: its threads as a gallery. -->
<script setup>
import { ref, watch } from 'vue'
import { fetchConversationThumbs, chatMediaPreviewUrl } from '../../composables/useChat'

const props = defineProps({
  space: { type: Object, required: true },
  threads: { type: Array, default: () => [] },
})
defineEmits(['open', 'close', 'new'])

// Cover thumbnail per thread (newest image), loaded lazily; threads without a
// generated image fall back to the placeholder icon.
const thumbs = ref({})
watch(
  () => props.threads.map(t => t.id).join(','),
  async ids => {
    if (!ids) return
    try {
      const { thumbs: t } = await fetchConversationThumbs(props.threads.map(x => x.id))
      thumbs.value = Object.fromEntries(Object.entries(t).map(([id, file]) => [id, chatMediaPreviewUrl(id, file)]))
    } catch {
      /* placeholders shown */
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="page">
    <div class="pwrap full">
      <div class="phead">
        <h1>
          <svg class="ic lg"><use href="#s-folder" /></svg> {{ space.name }}
        </h1>
        <div class="hactions">
          <button class="btn btn-primary" @click="$emit('new')">
            <svg class="ic"><use href="#s-plus" /></svg> New thread
          </button>
          <button class="btn" @click="$emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>
      <div v-if="!threads.length" class="empty">No threads in this space yet.</div>
      <div v-else class="grid">
        <button v-for="t in threads" :key="t.id" class="gcard card" @click="$emit('open', t.id)">
          <div class="cthumb">
            <img v-if="thumbs[t.id]" :src="thumbs[t.id]" alt="" loading="lazy" />
            <div v-else class="cph">
              <svg class="ic lg"><use :href="t.kind === 'gallery' ? '#s-image' : '#s-chat'" /></svg>
            </div>
          </div>
          <span class="ct">{{ t.title || 'Untitled' }}</span>
          <span v-if="t.pinned" class="cfav"
            ><svg class="ic sm"><use href="#s-star" /></svg
          ></span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: stretch;
  padding: 8px;
}
.cthumb {
  aspect-ratio: 4 / 3;
  border-radius: var(--r);
  overflow: hidden;
  background: var(--sbg2);
}
.cthumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.cph {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--sfaint);
  background: var(--saccent-soft);
}
.cph .ic {
  width: 26px;
  height: 26px;
  color: var(--saccent);
}
.ct {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  padding: 0 4px 2px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.cfav {
  position: absolute;
  top: 12px;
  right: 12px;
  color: var(--sstar);
  background: rgba(0, 0, 0, 0.45);
  border-radius: var(--r-sm);
  padding: 3px;
  display: grid;
}
</style>
