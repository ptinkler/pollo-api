<!-- Presentational card grid shared by the thread Generations gallery and the
     cross-thread Favourites gallery. Items are pre-built (each: id, kind, url,
     preview, file, favourite, prompt…). Card size S/M/L is remembered. -->
<script setup>
import { computed, ref } from 'vue'

defineProps({
  items: { type: Array, default: () => [] },
  empty: { type: String, default: 'Nothing here yet.' },
})
const emit = defineEmits(['open', 'favourite'])

const SIZE_KEY = 'studio.gallerySize'
const MIN = { s: 100, m: 150, l: 230 }
const readSize = () => {
  try {
    return localStorage.getItem(SIZE_KEY) || 'm'
  } catch {
    return 'm'
  }
}
const size = ref(readSize())
function setSize(s) {
  size.value = s
  try {
    localStorage.setItem(SIZE_KEY, s)
  } catch {
    /* storage unavailable */
  }
}
const minCol = computed(() => `${MIN[size.value] || MIN.m}px`)
</script>

<template>
  <div class="gens">
    <div class="gbar">
      <span class="gcount">{{ items.length }} item{{ items.length === 1 ? '' : 's' }}</span>
      <div class="gsize">
        <button v-for="s in ['s', 'm', 'l']" :key="s" :class="{ on: size === s }" @click="setSize(s)">
          {{ s.toUpperCase() }}
        </button>
      </div>
    </div>
    <div v-if="!items.length" class="empty">{{ empty }}</div>
    <div v-else class="grid" :style="{ '--min': minCol }">
      <div v-for="(item, i) in items" :key="item.id + '-' + i" class="cell" :title="item.prompt || item.file">
        <button type="button" class="thumb" @click="emit('open', item)">
          <img v-if="item.kind === 'image'" :src="item.preview || item.url" loading="lazy" alt="" />
          <video v-else :src="item.url" preload="metadata" muted playsinline></video>
          <span v-if="item.kind === 'video'" class="vtag">▶</span>
        </button>
        <button
          class="fav"
          :class="{ on: item.favourite }"
          :title="item.favourite ? 'Unfavourite' : 'Favourite'"
          @click.stop="emit('favourite', item)"
        >
          <svg class="ic"><use href="#s-star" /></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gens {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px 16px;
}
.gbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
}
.gcount {
  font-size: 12px;
  color: var(--smuted);
}
.gsize {
  display: inline-flex;
  gap: 2px;
  border: 1px solid var(--sborder);
  border-radius: 7px;
  padding: 2px;
}
.gsize button {
  min-width: 26px;
  padding: 3px 7px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--smuted);
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
}
.gsize button.on {
  background: var(--shover);
  color: var(--sfg);
}
.empty {
  color: var(--smuted);
  text-align: center;
  padding: 40px 0;
  font-size: 0.9rem;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--min, 150px), 1fr));
  gap: 10px;
}
.cell {
  position: relative;
  aspect-ratio: 1;
}
.thumb {
  width: 100%;
  height: 100%;
  border: 1px solid var(--sborder);
  border-radius: 10px;
  overflow: hidden;
  background: var(--sbg2);
  cursor: pointer;
  padding: 0;
  display: block;
}
.thumb:hover {
  border-color: var(--saccent);
}
.thumb img,
.thumb video {
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
.fav {
  position: absolute;
  top: 6px;
  left: 6px;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.5);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s;
}
.cell:hover .fav,
.fav.on {
  opacity: 1;
}
.fav.on {
  color: #ffd25a;
}
.fav .ic {
  width: 15px;
  height: 15px;
}
</style>
