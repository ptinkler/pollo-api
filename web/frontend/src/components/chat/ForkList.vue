<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

// The chats branched off at a message: "⑂ 2 branches", opening a list of them
defineProps({
  forks: { type: Array, required: true }, // [{ id, title }]
  align: { type: String, default: 'left' }, // which edge the list lines up with
})
const emit = defineEmits(['open'])

const open = ref(false)
const root = ref(null)

function onDocClick(e) {
  if (open.value && !root.value?.contains(e.target)) open.value = false
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

function pick(id) {
  open.value = false
  emit('open', id)
}
</script>

<template>
  <span ref="root" class="fork-list">
    <button class="fork-toggle" title="Chats branched off here" @click="open = !open">
      ⑂ {{ forks.length }} branch{{ forks.length === 1 ? '' : 'es' }}
    </button>
    <span v-if="open" class="fork-menu" :class="align">
      <button v-for="f in forks" :key="f.id" class="fork-item" :title="f.title" @click="pick(f.id)">
        {{ f.title }}
      </button>
    </span>
  </span>
</template>

<style scoped>
.fork-list {
  position: relative;
  display: inline-flex;
}

.fork-toggle {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 0.75rem;
  padding: 3px 7px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
}

.fork-toggle:hover {
  background: var(--surface2);
}

.fork-menu {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  min-width: 180px;
  max-width: 280px;
  padding: 4px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
}

.fork-menu.right {
  left: auto;
  right: 0;
}

.fork-item {
  background: none;
  border: none;
  color: var(--text);
  text-align: left;
  font-size: 0.8rem;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fork-item:hover {
  background: rgba(108, 92, 231, 0.2);
}
</style>
