<script setup>
// Filter bar for the media library: v-model:filters is useMediaFilters' state
const filters = defineModel('filters', { type: Object, required: true })
defineProps({
  showKind: { type: Boolean, default: true },
})

const KINDS = [
  ['all', 'All'],
  ['image', 'Images'],
  ['video', 'Videos'],
]
const SOURCES = [
  ['all', 'Any source'],
  ['upload', 'Uploads'],
  ['generated', 'Creations'],
]
const ORIGINS = [
  ['all', 'Everywhere'],
  ['library', 'Library'],
  ['project', 'Projects'],
  ['chat', 'Chats'],
]
</script>

<template>
  <div class="media-filters">
    <div v-if="showKind" class="seg">
      <button
        v-for="[v, l] in KINDS"
        :key="v"
        type="button"
        :class="{ on: filters.kind === v }"
        @click="filters.kind = v"
      >
        {{ l }}
      </button>
    </div>
    <select v-model="filters.source" aria-label="Source">
      <option v-for="[v, l] in SOURCES" :key="v" :value="v">{{ l }}</option>
    </select>
    <select v-model="filters.origin" aria-label="Where from">
      <option v-for="[v, l] in ORIGINS" :key="v" :value="v">{{ l }}</option>
    </select>
    <input v-model="filters.q" type="search" placeholder="Search prompts, projects, chats…" aria-label="Search" />
  </div>
</template>

<style scoped>
.media-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.seg {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.seg button {
  padding: 6px 12px;
  border: none;
  background: none;
  color: var(--text2);
  cursor: pointer;
  font-size: 0.82rem;
}

.seg button.on {
  background: var(--surface2);
  color: var(--text);
}

select,
input {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  font: inherit;
  font-size: 0.82rem;
}

input {
  flex: 1;
  min-width: 160px;
}
</style>
