<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import BaseDialog from './BaseDialog.vue'

// Pick what a chat (or a space's defaults) uses: a searchable grid of cards,
// each switched on or off with a tap. Shared by the character and the
// instruction pickers. Names needn't be unique, so a card also shows its
// picture or a preview of its text and where it lives (`badge`).
//
// items: [{ key, name, sub?, img?, dot?, icon?, badge?, section?, on, from? }]
//   on    — currently in use here
//   from  — set for defaults (the icon/title of where they come from): turning
//           one off hides it in this chat rather than detaching it
// Emits `toggle` with the item; the parent decides what that means.
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  items: { type: Array, default: () => [] },
  empty: { type: String, default: 'Nothing saved yet' },
  searchPlaceholder: { type: String, default: 'Search' },
})
const emit = defineEmits(['close', 'toggle'])

const query = ref('')
const search = ref(null)
watch(
  () => props.open,
  async open => {
    if (!open) return
    query.value = ''
    await nextTick()
    search.value?.focus()
  },
)

const matches = item => {
  const q = query.value.trim().toLowerCase()
  return !q || `${item.name} ${item.sub || ''} ${item.badge || ''}`.toLowerCase().includes(q)
}
// In use first, then the rest; each in its section (Groups / Snippets…)
const sections = computed(() => {
  const out = new Map()
  for (const item of props.items.filter(matches)) {
    const name = item.section || ''
    if (!out.has(name)) out.set(name, [])
    out.get(name).push(item)
  }
  for (const list of out.values()) list.sort((a, b) => Number(b.on) - Number(a.on))
  return [...out.entries()]
})
const onCount = computed(() => props.items.filter(i => i.on).length)
</script>

<template>
  <BaseDialog :open="open" :title="title" width="720px" @close="emit('close')">
    <template #head>
      <span class="count">{{ onCount }} on</span>
    </template>
    <input
      ref="search"
      v-model="query"
      type="search"
      class="search"
      :placeholder="searchPlaceholder"
      :aria-label="searchPlaceholder"
    />
    <p v-if="!items.length" class="note">{{ empty }}</p>
    <p v-else-if="!sections.length" class="note">Nothing matches</p>
    <template v-for="[section, list] in sections" :key="section">
      <p v-if="section" class="section">{{ section }}</p>
      <div class="grid">
        <button
          v-for="item in list"
          :key="item.key"
          type="button"
          class="card"
          :class="{ on: item.on, default: !!item.from }"
          :aria-pressed="item.on"
          :title="
            item.from
              ? `${item.name} — ${item.from}. ${item.on ? 'Click to hide it in this chat' : 'Click to use it here again'}`
              : `${item.name}${item.sub ? `\n${item.sub}` : ''}`
          "
          @click="emit('toggle', item)"
        >
          <span v-if="'img' in item" class="thumb">
            <img v-if="item.img" :src="item.img" alt="" loading="lazy" />
            <span v-else class="blank">{{ item.icon || '👤' }}</span>
            <span class="tick" aria-hidden="true">{{ item.on ? '✓' : '' }}</span>
          </span>
          <span class="name">
            <span v-if="!('img' in item)" class="tick inline" aria-hidden="true">{{ item.on ? '✓' : '' }}</span>
            <span v-if="item.dot" class="dot" :style="{ background: item.dot }"></span>
            <span v-else-if="item.icon && !('img' in item)">{{ item.icon }}</span>
            <span class="name-text">{{ item.name }}</span>
          </span>
          <span v-if="item.sub" class="sub">{{ item.sub }}</span>
          <span v-if="item.badge || item.from" class="badge">{{ item.from || item.badge }}</span>
        </button>
      </div>
    </template>
    <template #actions>
      <slot name="actions" />
      <span class="spacer"></span>
      <button type="button" class="btn btn-primary" @click="emit('close')">Done</button>
    </template>
  </BaseDialog>
</template>

<style scoped>
.count {
  font-size: 12px;
  color: var(--text2);
}

.search {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: inherit;
  font: inherit;
}

.note {
  color: var(--text2);
  font-size: 13px;
}

.section {
  margin-top: 4px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text2);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(124px, 1fr));
  gap: 8px;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface2);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.card:hover {
  border-color: var(--text2);
}

.card.on {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent) inset;
}

.card.default:not(.on) {
  opacity: 0.6;
}

.thumb {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 1;
  border-radius: 7px;
  background: var(--surface);
  overflow: hidden;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb .blank {
  font-size: 28px;
  opacity: 0.6;
}

.dot {
  flex-shrink: 0;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.tick {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  font-size: 12px;
  color: #fff;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.5);
}

.tick.inline {
  position: static;
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  font-size: 10px;
  border-color: var(--border);
  background: transparent;
}

.card.on .tick {
  background: var(--accent);
  border-color: var(--accent);
}

.name {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
}

.name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sub {
  font-size: 11.5px;
  color: var(--text2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.35;
}

.badge {
  align-self: flex-start;
  max-width: 100%;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10.5px;
  color: var(--text2);
  border: 1px solid var(--border);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spacer {
  flex: 1;
}
</style>
