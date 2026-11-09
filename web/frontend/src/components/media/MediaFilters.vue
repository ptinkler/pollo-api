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
  ['chat', 'Chats'],
  ['orphan', 'Orphaned'],
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

select,
input {
  padding: 5px 9px;
  font-size: 12.5px;
}

input {
  flex: 1;
  min-width: 160px;
}
</style>
