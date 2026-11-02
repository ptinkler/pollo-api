<!-- Always-visible generation queue: a collapsible dock (bottom-right) that shows
     what's rendering across every thread, even after you navigate away. Finished
     and failed items stay until cleared. Clicking a row opens that thread's
     gallery. Fed by useGenQueue (polls /api/chat/generations/active). -->
<script setup>
import { ref } from 'vue'
import { chatMediaUrl, chatMediaPreviewUrl } from '../../composables/useChat'

defineProps({
  entries: { type: Array, default: () => [] },
  pending: { type: Number, default: 0 },
  done: { type: Number, default: 0 },
})
const emit = defineEmits(['open', 'clear', 'clear-one'])

const CKEY = 'studio.genQueue.collapsed'
const readCollapsed = () => {
  try {
    return localStorage.getItem(CKEY) === '1'
  } catch {
    return false
  }
}
const collapsed = ref(readCollapsed())
function toggle() {
  collapsed.value = !collapsed.value
  try {
    localStorage.setItem(CKEY, collapsed.value ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
}

const thumb = e =>
  e.kind === 'image' ? chatMediaPreviewUrl(e.conversation_id, e.file) : chatMediaUrl(e.conversation_id, e.file)
function label(e) {
  if (e.status === 'pending') return e.kind === 'video' ? 'Rendering video…' : 'Creating image…'
  if (e.status === 'error') return e.moderated ? 'Blocked' : 'Failed'
  return e.kind === 'video' ? 'Video ready' : 'Image ready'
}
</script>

<template>
  <div v-if="entries.length" class="qdock" :class="{ collapsed }">
    <div class="qhead" @click="toggle">
      <span class="qtitle">
        <span v-if="pending" class="qspin"></span>
        {{ pending ? `${pending} generating` : 'Generations' }}
      </span>
      <span class="qcount">{{ entries.length }}</span>
      <button class="qbtn" :title="collapsed ? 'Expand' : 'Collapse'" @click.stop="toggle">
        {{ collapsed ? '▴' : '▾' }}
      </button>
    </div>

    <div v-show="!collapsed" class="qbody">
      <button
        v-for="e in entries"
        :key="e.media_id"
        type="button"
        class="qrow"
        :class="e.status"
        @click="emit('open', e)"
      >
        <span class="qthumb" :class="e.kind">
          <img v-if="e.status === 'done' && e.file && e.kind === 'image'" :src="thumb(e)" loading="lazy" alt="" />
          <video v-else-if="e.status === 'done' && e.file" :src="thumb(e)" muted preload="metadata"></video>
          <span v-else-if="e.status === 'pending'" class="qspin sm"></span>
          <span v-else class="qfail">✕</span>
        </span>
        <span class="qinfo">
          <span class="qlabel">{{ label(e) }}</span>
          <span class="qsub">{{ e.conversation_title || 'Untitled thread' }}</span>
        </span>
        <span class="qx" title="Remove from queue" @click.stop="emit('clear-one', e.media_id)">×</span>
      </button>
    </div>

    <div v-show="!collapsed && done" class="qfoot">
      <button class="qclear" @click="emit('clear')">Clear {{ done }} finished</button>
    </div>
  </div>
</template>

<style scoped>
.qdock {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 900;
  width: 300px;
  max-width: calc(100vw - 32px);
  background: var(--spanel2, var(--sbg2));
  border: 1px solid var(--sborder);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-height: min(60vh, 460px);
}
.qhead {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 10px 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--sborder);
  background: var(--sbg);
}
.collapsed .qhead {
  border-bottom: none;
}
.qtitle {
  flex: 1;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--sfg);
}
.qcount {
  font-size: 11px;
  color: var(--smuted);
  background: var(--shover);
  border-radius: 10px;
  padding: 1px 8px;
}
.qbtn {
  border: none;
  background: transparent;
  color: var(--smuted);
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  padding: 2px 4px;
}
.qbody {
  overflow-y: auto;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.qrow {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--sfg);
  cursor: pointer;
  text-align: left;
  font: inherit;
}
.qrow:hover {
  background: var(--shover);
}
.qthumb {
  position: relative;
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  border-radius: 7px;
  overflow: hidden;
  background: var(--sbg2);
  display: grid;
  place-items: center;
}
.qthumb img,
.qthumb video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.qrow.error .qthumb {
  background: color-mix(in srgb, var(--sdanger, #e5484d) 14%, var(--sbg2));
}
.qfail {
  color: var(--sdanger, #e5484d);
  font-size: 13px;
  font-weight: 700;
}
.qinfo {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.qlabel {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.qrow.error .qlabel {
  color: var(--sdanger, #e5484d);
}
.qrow.pending .qlabel {
  color: var(--saccent);
}
.qsub {
  font-size: 11px;
  color: var(--smuted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.qx {
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 5px;
  color: var(--sfaint);
  font-size: 16px;
  line-height: 1;
}
.qx:hover {
  background: var(--sborder);
  color: var(--sfg);
}
.qfoot {
  padding: 6px;
  border-top: 1px solid var(--sborder);
}
.qclear {
  width: 100%;
  padding: 6px;
  border: 1px solid var(--sborder);
  border-radius: 7px;
  background: transparent;
  color: var(--smuted);
  cursor: pointer;
  font-size: 12px;
}
.qclear:hover {
  background: var(--shover);
  color: var(--sfg);
}
.qspin {
  width: 13px;
  height: 13px;
  border: 2px solid var(--sborder);
  border-top-color: var(--saccent);
  border-radius: 50%;
  animation: qspin 0.8s linear infinite;
}
.qspin.sm {
  width: 18px;
  height: 18px;
}
@keyframes qspin {
  to {
    transform: rotate(360deg);
  }
}
</style>
