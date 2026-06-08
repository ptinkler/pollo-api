<script setup>
import { ref, watch } from 'vue'
import { fetchProjects } from '../composables/useApi'

const props = defineProps({
  visible: { type: Boolean, default: false },
  currentProject: { type: String, required: true },
  count: { type: Number, default: 0 },
})

const emit = defineEmits(['move', 'close'])

const projects = ref([])
const selected = ref(null)
const loading = ref(false)

watch(() => props.visible, async (v) => {
  if (!v) { selected.value = null; return }
  loading.value = true
  try {
    const data = await fetchProjects({ archived: false })
    projects.value = (Array.isArray(data) ? data : []).filter(p => p.slug !== props.currentProject)
  } finally {
    loading.value = false
  }
})

function confirm() {
  if (selected.value) emit('move', selected.value)
}
</script>

<template>
  <div v-if="visible" class="modal-overlay" @click.self="emit('close')">
    <div class="move-modal">
      <button class="modal-close" @click="emit('close')">&times;</button>
      <h3>Move {{ count }} video{{ count !== 1 ? 's' : '' }} to project</h3>

      <div v-if="loading" class="move-loading">Loading projects...</div>

      <div v-else-if="!projects.length" class="move-empty">
        No other projects available.
      </div>

      <ul v-else class="project-list">
        <li
          v-for="p in projects"
          :key="p.slug"
          :class="['project-item', { active: selected === p.slug }]"
          @click="selected = p.slug"
        >
          {{ p.name }}
        </li>
      </ul>

      <div class="move-actions">
        <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
        <button class="btn btn-primary" :disabled="!selected" @click="confirm">Move</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.move-modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  width: 340px;
  max-width: 90vw;
  position: relative;
}

.move-modal h3 {
  margin: 0 0 16px;
  font-size: 1rem;
  font-weight: 600;
}

.modal-close {
  position: absolute;
  top: 12px;
  right: 14px;
  background: none;
  border: none;
  font-size: 1.4rem;
  color: var(--text2);
  cursor: pointer;
  line-height: 1;
  padding: 2px 6px;
}

.modal-close:hover { color: var(--text); }

.move-loading,
.move-empty {
  color: var(--text2);
  font-size: 0.9rem;
  padding: 12px 0;
}

.project-list {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.project-item {
  padding: 10px 14px;
  cursor: pointer;
  font-size: 0.9rem;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
}

.project-item:last-child { border-bottom: none; }
.project-item:hover { background: var(--surface2); }
.project-item.active {
  background: rgba(108, 92, 231, 0.2);
  color: var(--text);
}

.move-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
