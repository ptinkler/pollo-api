<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { mediaOrigin } from '../../composables/useMedia'

// A grid of media-library items, lazy all the way down: tiles are added a
// page at a time as the end of the grid scrolls near, and each tile's
// small server-made thumbnail loads only when the tile is near the screen.
// With `selectable`, clicking toggles an item's selection ('toggle');
// otherwise it opens it ('open').
const props = defineProps({
  items: { type: Array, default: () => [] },
  selected: { type: Set, default: () => new Set() },
  selectable: { type: Boolean, default: false },
  pageSize: { type: Number, default: 60 },
})
const emit = defineEmits(['toggle', 'open'])

const shown = ref(props.pageSize)
const visible = computed(() => props.items.slice(0, shown.value))
// New filters or search: start from the top again
watch(() => props.items, () => { shown.value = props.pageSize })

// Add the next page when the sentinel after the last tile comes within
// ~2 screens. Without IntersectionObserver (old browsers, tests) show all.
const sentinel = ref(null)
let observer = null
watch(sentinel, (el) => {
  observer?.disconnect()
  if (!el) return
  if (typeof IntersectionObserver === 'undefined') {
    shown.value = Infinity
    return
  }
  observer = new IntersectionObserver((entries) => {
    if (!entries.some(e => e.isIntersecting)) return
    shown.value += props.pageSize
    // Still in range after the new page (a tall screen)? Observing afresh
    // reports the current state again, so it keeps filling.
    nextTick(() => {
      if (!sentinel.value) return
      observer.unobserve(sentinel.value)
      observer.observe(sentinel.value)
    })
  }, { rootMargin: '200% 0px' })
  observer.observe(el)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="media-grid">
    <button
      v-for="item in visible"
      :key="item.id"
      type="button"
      class="tile"
      :class="{ selected: selected.has(item.id) }"
      :title="item.prompt || item.name"
      @click="selectable ? emit('toggle', item) : emit('open', item)"
    >
      <img :src="item.thumb_url" alt="" loading="lazy" decoding="async" />
      <span v-if="item.kind === 'video'" class="badge video">▶</span>
      <span class="badge source">{{ item.source === 'upload' ? '⬆' : '✨' }}</span>
      <span class="caption">{{ mediaOrigin(item) }}</span>
      <span v-if="selectable" class="check">{{ selected.has(item.id) ? '✓' : '' }}</span>
    </button>
    <div v-if="visible.length < items.length" ref="sentinel" class="sentinel" aria-hidden="true"></div>
  </div>
</template>

<style scoped>
.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 8px;
}

.tile {
  position: relative;
  aspect-ratio: 1;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 10px;
  overflow: hidden;
  background: var(--surface2);
  cursor: pointer;
}

.tile:hover {
  border-color: var(--border);
}

.tile.selected {
  border-color: var(--accent);
}

.tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  pointer-events: none;
}

.sentinel {
  grid-column: 1 / -1;
  height: 1px;
}

.badge {
  position: absolute;
  top: 5px;
  font-size: 0.65rem;
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
}

.badge.video {
  left: 5px;
}

.badge.source {
  right: 5px;
}

.caption {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 10px 6px 4px;
  font-size: 0.68rem;
  color: #fff;
  text-align: left;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.75));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.check {
  position: absolute;
  top: 5px;
  left: 50%;
  transform: translateX(-50%);
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid #fff;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  font-size: 0.75rem;
  line-height: 18px;
}

.tile.selected .check {
  background: var(--accent);
  border-color: var(--accent);
}
</style>
