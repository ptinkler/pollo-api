<script setup>
import { computed, ref, watch, onMounted, onUnmounted, inject } from 'vue'
import { getVideoUrl, deleteVideo } from '../composables/useApi'

const props = defineProps({
  video: { type: Object, default: null },
  project: { type: String, required: true },
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'regenerate', 'use-as-ref', 'archive', 'unarchive', 'deleted'])
const showToast = inject('showToast')

const isArchived = computed(() => !!props.video?.job?.archived)

const videoEl = ref(null)

const job = computed(() => props.video?.job || {})
const videoUrl = computed(() =>
  props.video ? getVideoUrl(props.project, props.video.filename) : ''
)

const metaItems = computed(() => {
  const items = []
  if (job.value.aspect_ratio) items.push({ label: 'Ratio', value: job.value.aspect_ratio })
  if (job.value.resolution) items.push({ label: 'Resolution', value: job.value.resolution })
  if (job.value.length) items.push({ label: 'Length', value: `${job.value.length}s` })
  if (job.value.generate_audio) items.push({ label: 'Audio', value: 'Yes' })
  if (job.value.created_at) items.push({ label: 'Created', value: new Date(job.value.created_at).toLocaleString() })
  return items
})

function close() {
  if (videoEl.value) {
    videoEl.value.pause()
  }
  emit('close')
}

function handleKeydown(e) {
  if (e.key === 'Escape' && props.visible) {
    close()
  }
}

async function handleDelete() {
  if (!props.video || !confirm('Delete this video? This cannot be undone.')) return

  try {
    await deleteVideo(props.project, props.video.filename)
    close()
    emit('deleted', props.video.filename)
  } catch (err) {
    showToast('Delete failed: ' + err, 'error')
  }
}

// Stop video when modal closes
watch(() => props.visible, (visible) => {
  if (!visible && videoEl.value) {
    videoEl.value.pause()
    videoEl.value.src = ''
  }
})

// Global keyboard listener for Escape key
onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible && video" class="modal-overlay">
      <div class="modal-content">
        <button class="modal-close" @click="close">&times;</button>
        <video
          ref="videoEl"
          class="modal-video"
          :src="videoUrl"
          controls
        />
        <div class="modal-body">
          <h3>{{ job.model || 'Unknown Model' }}</h3>
          <div class="prompt-text">{{ job.prompt || 'No prompt recorded' }}</div>
          <div class="modal-meta">
            <div v-for="item in metaItems" :key="item.label" class="meta-item">
              {{ item.label }}: <span>{{ item.value }}</span>
            </div>
          </div>
          <div class="modal-actions">
            <button class="btn btn-primary" @click="$emit('regenerate', video)">🔄 Regenerate</button>
            <button class="btn btn-primary" @click="$emit('use-as-ref', video)">🎯 Use as Ref</button>
            <button class="btn btn-secondary" @click="$emit(isArchived ? 'unarchive' : 'archive', video)">
              📦 {{ isArchived ? 'Unarchive' : 'Archive' }}
            </button>
            <button class="btn btn-danger" @click="handleDelete">🗑️ Delete</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-content {
  background: var(--surface);
  border-radius: 12px;
  max-width: 800px;
  width: 95%;
  max-height: 90vh;
  overflow-y: auto;
  position: relative;
}

.modal-close {
  position: absolute;
  top: 12px;
  right: 12px;
  background: var(--surface2);
  border: none;
  color: var(--text);
  width: 32px;
  height: 32px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 1.2rem;
  z-index: 10;
}

.modal-close:hover {
  background: var(--border);
}

.modal-video {
  width: 100%;
  max-height: 50vh;
  object-fit: contain;
  display: block;
  background: #000;
}

.modal-body {
  padding: 20px;
}

.modal-body h3 {
  font-size: 1rem;
  margin-bottom: 12px;
  color: var(--accent2);
}

.prompt-text {
  font-size: 0.9rem;
  color: var(--text);
  margin-bottom: 16px;
  line-height: 1.5;
}

.modal-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
}

.meta-item {
  font-size: 0.8rem;
  color: var(--text2);
}

.meta-item span {
  color: var(--text);
  font-weight: 500;
}

.modal-actions {
  display: flex;
  gap: 12px;
}
</style>

