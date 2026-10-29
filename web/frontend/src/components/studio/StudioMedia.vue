<!-- Studio center pane: the media library (all generated images/videos),
     reusing MediaGrid + useMedia with server-side paging. -->
<script setup>
import { ref, onMounted } from 'vue'
import MediaGrid from '../media/MediaGrid.vue'
import { fetchMediaPage } from '../../composables/useMedia'

defineEmits(['close'])

const PAGE = 30
const KINDS = [
  { id: 'all', label: 'All' },
  { id: 'image', label: 'Images' },
  { id: 'video', label: 'Videos' },
]

const items = ref([])
const total = ref(0)
const kind = ref('all')
const q = ref('')
const loading = ref(false)
const preview = ref(null)

function params(offset) {
  return { offset, limit: PAGE, q: q.value || undefined, kind: kind.value === 'all' ? undefined : kind.value }
}
async function load() {
  loading.value = true
  try {
    const { items: page, total: t } = await fetchMediaPage(params(0))
    items.value = page
    total.value = t
  } finally {
    loading.value = false
  }
}
async function loadMore() {
  if (items.value.length >= total.value) return
  const { items: page } = await fetchMediaPage(params(items.value.length))
  items.value = [...items.value, ...page]
}
function setKind(k) {
  kind.value = k
  load()
}

onMounted(load)
</script>

<template>
  <div class="media">
    <div class="mhead">
      <h1>Media library</h1>
      <button class="closebtn" @click="$emit('close')">
        <svg class="ic"><use href="#s-chevL" /></svg> Back
      </button>
    </div>
    <div class="mbar">
      <div class="kinds">
        <button v-for="k in KINDS" :key="k.id" :class="{ on: kind === k.id }" @click="setKind(k.id)">
          {{ k.label }}
        </button>
      </div>
      <div class="msearch">
        <svg class="ic"><use href="#s-search" /></svg>
        <input v-model="q" placeholder="Search prompts…" @keyup.enter="load" />
      </div>
    </div>

    <div class="mbody">
      <div v-if="loading && !items.length" class="empty">Loading…</div>
      <div v-else-if="!items.length" class="empty">No media yet.</div>
      <MediaGrid v-else :items="items" :has-more="items.length < total" @open="preview = $event" @more="loadMore" />
    </div>

    <div v-if="preview" class="ovl" @click="preview = null">
      <video v-if="preview.kind === 'video'" :src="preview.url" class="pv" controls autoplay @click.stop />
      <img v-else :src="preview.url" class="pv" alt="" @click.stop />
    </div>
  </div>
</template>

<style scoped>
.media {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.mhead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 22px;
  border-bottom: 1px solid var(--sborder2);
}
h1 {
  font-size: 20px;
  font-weight: 650;
  letter-spacing: -0.02em;
}
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
.closebtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.mbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 22px;
}
.kinds {
  display: flex;
  gap: 6px;
}
.kinds button {
  padding: 6px 13px;
  border: 1px solid var(--sborder);
  border-radius: 8px;
  color: var(--smuted);
  background: none;
  cursor: pointer;
  font-size: 12.5px;
}
.kinds button.on {
  background: var(--saccent-soft);
  color: var(--saccent);
  border-color: transparent;
}
.msearch {
  position: relative;
  flex: 1;
  max-width: 320px;
}
.msearch .ic {
  position: absolute;
  left: 11px;
  top: 9px;
  width: 15px;
  height: 15px;
  color: var(--sfaint);
}
.msearch input {
  width: 100%;
  padding: 8px 11px 8px 33px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  background: var(--spanel2);
  color: var(--sfg);
  outline: none;
}
.mbody {
  flex: 1;
  overflow-y: auto;
  padding: 8px 22px 24px;
}
.empty {
  color: var(--sfaint);
  text-align: center;
  margin-top: 60px;
}
.ovl {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.82);
  padding: 32px;
}
.pv {
  max-width: 92vw;
  max-height: 92vh;
  border-radius: 10px;
}
</style>
