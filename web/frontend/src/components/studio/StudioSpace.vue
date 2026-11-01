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
  <div class="space">
    <div class="swrap">
      <div class="shead">
        <h1>
          <svg class="ic lg"><use href="#s-folder" /></svg> {{ space.name }}
        </h1>
        <div class="sactions">
          <button class="btn" @click="$emit('new')">
            <svg class="ic"><use href="#s-plus" /></svg> New thread
          </button>
          <button class="closebtn" @click="$emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>
      <div v-if="!threads.length" class="empty">No threads in this space yet.</div>
      <div v-else class="grid">
        <button v-for="t in threads" :key="t.id" class="card" @click="$emit('open', t.id)">
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
.space {
  flex: 1;
  overflow-y: auto;
  padding: 32px 22px;
}
.swrap {
  max-width: 900px;
  margin: 0 auto;
}
.shead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}
h1 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.02em;
  min-width: 0;
}
h1 .ic {
  color: var(--saccent);
}
.sactions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}
.btn,
.closebtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  color: var(--smuted);
  background: none;
  cursor: pointer;
}
.btn:hover,
.closebtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.btn .ic {
  color: var(--saccent);
}
.empty {
  color: var(--sfaint);
  text-align: center;
  margin-top: 60px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: stretch;
  padding: 10px;
  border: 1px solid var(--sborder);
  border-radius: 12px;
  background: var(--sbg);
  color: var(--sfg);
  cursor: pointer;
  text-align: left;
}
.card:hover {
  border-color: var(--sfaint);
  background: var(--spanel2);
}
.cthumb {
  aspect-ratio: 4 / 3;
  border-radius: 8px;
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
  width: 28px;
  height: 28px;
  color: var(--saccent);
}
.ct {
  font-weight: 550;
  line-height: 1.4;
  padding: 0 6px 4px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.cfav {
  position: absolute;
  top: 14px;
  right: 14px;
  color: var(--saccent);
  background: rgba(0, 0, 0, 0.4);
  border-radius: 6px;
  padding: 2px;
}
</style>
