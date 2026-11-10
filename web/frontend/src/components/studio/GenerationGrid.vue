<!-- Presentational card grid shared by the thread Generations gallery and the
     cross-thread Favourites gallery. Items are pre-built (each: id, kind, url,
     preview, file, favourite, status, prompt…). Renders in-progress (pending)
     and failed tiles too, so the thread gallery doubles as a live queue. Card
     size S/M/L is remembered; kind + favourites filters are applied locally. -->
<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  empty: { type: String, default: 'Nothing here yet.' },
  // The Favourites page is already favourites-only, so it hides the ★ filter.
  favFilter: { type: Boolean, default: true },
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

const kind = ref('all') // all | image | video
const favOnly = ref(false)
const shown = computed(() =>
  props.items.filter(it => {
    if (kind.value !== 'all' && it.kind !== kind.value) return false
    if (favOnly.value && !it.favourite) return false
    return true
  }),
)
// A preview that fails once falls back to the full file, then retries once
// (a half-written file or a dropped connection), instead of staying blank
function onImgError(e, item) {
  const img = e.target
  if (!img.dataset.fb && item.url && img.src !== new URL(item.url, location.href).href) {
    img.dataset.fb = '1'
    img.src = item.url
  } else if (!img.dataset.retry) {
    img.dataset.retry = '1'
    setTimeout(() => (img.src = `${item.url}${item.url.includes('?') ? '&' : '?'}r=1`), 1500)
  }
}
const inProgress = computed(() => props.items.filter(it => it.status === 'pending').length)
</script>

<template>
  <div class="gens">
    <div class="gbar">
      <div class="gleft">
        <span class="gcount">{{ shown.length }} item{{ shown.length === 1 ? '' : 's' }}</span>
        <span v-if="inProgress" class="ginprog"><span class="dot"></span>{{ inProgress }} generating</span>
        <div class="seg" role="group" aria-label="Kind">
          <button v-for="k in ['all', 'image', 'video']" :key="k" :class="{ on: kind === k }" @click="kind = k">
            {{ k === 'all' ? 'All' : k === 'image' ? 'Images' : 'Videos' }}
          </button>
        </div>
        <button
          v-if="favFilter"
          class="gfav"
          :class="{ on: favOnly }"
          title="Favourites only"
          @click="favOnly = !favOnly"
        >
          <svg class="ic"><use href="#s-star" /></svg>
        </button>
        <!-- Extra filters from the page using the grid, in the same toolbar -->
        <slot name="filters"></slot>
      </div>
      <div class="seg" role="group" aria-label="Card size">
        <button v-for="s in ['s', 'm', 'l']" :key="s" :class="{ on: size === s }" @click="setSize(s)">
          {{ s.toUpperCase() }}
        </button>
      </div>
    </div>
    <div v-if="!items.length" class="empty">{{ empty }}</div>
    <div v-else-if="!shown.length" class="empty">Nothing matches these filters.</div>
    <div v-else class="grid" :style="{ '--min': minCol }">
      <div
        v-for="(item, i) in shown"
        :key="item.id + '-' + i"
        class="cell"
        :class="item.status"
        :title="item.prompt || item.file"
      >
        <div v-if="item.status === 'pending'" class="thumb state pending">
          <div class="spinner"></div>
          <div class="slabel">{{ item.kind === 'image' ? 'Creating image…' : 'Rendering video…' }}</div>
          <div v-if="item.prompt" class="sprompt">{{ item.prompt }}</div>
        </div>
        <button
          v-else-if="item.status === 'error'"
          type="button"
          class="thumb state errored"
          title="Open to see why it failed, retry or reuse its settings"
          @click="emit('open', item)"
        >
          <div class="slabel">{{ item.moderated ? 'Blocked' : 'Failed' }}</div>
          <div v-if="item.prompt" class="sprompt">{{ item.prompt }}</div>
          <div class="shint">Click for details</div>
        </button>
        <template v-else>
          <a class="thumb" :href="item.url" @click.prevent="emit('open', item)">
            <img
              v-if="item.kind === 'image'"
              :src="item.preview || item.url"
              loading="lazy"
              alt=""
              @error="onImgError($event, item)"
            />
            <video v-else :src="item.url" preload="metadata" muted playsinline></video>
            <span v-if="item.kind === 'video'" class="vtag">▶</span>
          </a>
          <button
            class="fav"
            :class="{ on: item.favourite }"
            :title="item.favourite ? 'Unfavourite' : 'Favourite'"
            @click.stop="emit('favourite', item)"
          >
            <svg class="ic"><use href="#s-star" /></svg>
          </button>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gens {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px 16px;
}
.gbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
}
.gleft {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.gcount {
  font-size: 12px;
  color: var(--smuted);
}
.ginprog {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--saccent);
}
.ginprog .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--saccent);
  animation: pulse 1.1s ease-in-out infinite;
}
.gfav {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--sborder);
  border-radius: var(--r);
  background: transparent;
  color: var(--smuted);
  cursor: pointer;
}
.gfav:hover {
  color: var(--sfg);
  border-color: var(--sfaint);
}
.gfav.on {
  color: var(--sstar);
  border-color: var(--sstar);
}
.gfav .ic {
  width: 15px;
  height: 15px;
}
.empty {
  color: var(--smuted);
  text-align: center;
  padding: 40px 0;
  font-size: 13px;
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
  border-radius: var(--r);
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
.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: default;
  padding: 10px;
  text-align: center;
}
.state.errored {
  border-color: var(--sdanger, #e5484d);
  color: var(--sdanger, #e5484d);
  cursor: pointer;
}
.state.errored:hover {
  background: color-mix(in srgb, var(--sdanger, #e5484d) 8%, var(--sbg2));
}
.shint {
  font-size: 10px;
  color: var(--sfaint);
  margin-top: 2px;
}
.slabel {
  font-size: 12px;
  font-weight: 600;
  color: var(--smuted);
}
.state.errored .slabel {
  color: var(--sdanger, #e5484d);
}
.sprompt {
  font-size: 11px;
  line-height: 1.35;
  color: var(--sfaint);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.spinner {
  width: 24px;
  height: 24px;
  border: 2.5px solid var(--sborder);
  border-top-color: var(--saccent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
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
  color: var(--sstar);
}
.fav .ic {
  width: 15px;
  height: 15px;
}
</style>
