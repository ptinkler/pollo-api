<script setup>
import { computed, ref } from 'vue'
import { getVideoThumbUrl } from '../composables/useApi'

const props = defineProps({
  video: { type: Object, required: true },
  project: { type: String, required: true },
  showArchive: { type: Boolean, default: true },
  showUnarchive: { type: Boolean, default: false }
})

defineEmits(['click', 'regenerate', 'use-as-ref', 'archive', 'unarchive', 'delete'])

const job = computed(() => props.video.job || {})
const model = computed(() => job.value.model || 'Unknown')
const prompt = computed(() => (job.value.prompt || '').substring(0, 100))
const date = computed(() => job.value.created_at ? new Date(job.value.created_at).toLocaleDateString() : '')
const thumbUrl = computed(() => getVideoThumbUrl(props.project, props.video.filename))

const thumbError = ref(false)

function handleThumbError() {
  thumbError.value = true
}
</script>

<template>
  <div class="gallery-card">
    <div class="card-clickable" @click="$emit('click', video)">
      <img
        v-if="!thumbError"
        class="gallery-thumb"
        :src="thumbUrl"
        alt=""
        loading="lazy"
        @error="handleThumbError"
      />
      <div v-else class="gallery-thumb-placeholder">🎬</div>
      <div class="gallery-card-body">
        <div class="video-model">{{ model }}</div>
        <div class="video-prompt">{{ prompt }}</div>
        <div class="video-meta">
          <span v-if="job.aspect_ratio">{{ job.aspect_ratio }}</span>
          <span v-if="job.length">{{ job.length }}s</span>
          <span v-if="date">{{ date }}</span>
        </div>
      </div>
    </div>

    <div class="card-actions">
      <button
        class="action-btn"
        title="Regenerate"
        @click.stop="$emit('regenerate', video)"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 4v6h-6M1 20v-6h6"/>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
        </svg>
      </button>
      <button
        class="action-btn"
        title="Use as Ref"
        @click.stop="$emit('use-as-ref', video)"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M15 3h6v6"/>
          <path d="M10 14L21 3"/>
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
        </svg>
      </button>
      <button
        v-if="showArchive"
        class="action-btn"
        title="Archive"
        @click.stop="$emit('archive', video)"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 8v13H3V8"/>
          <path d="M1 3h22v5H1z"/>
          <path d="M10 12h4"/>
        </svg>
      </button>
      <button
        v-if="showUnarchive"
        class="action-btn"
        title="Unarchive"
        @click.stop="$emit('unarchive', video)"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 8v13H3V8"/>
          <path d="M1 3h22v5H1z"/>
          <path d="M12 12v6"/>
          <path d="M9 15l3-3 3 3"/>
        </svg>
      </button>
      <button
        class="action-btn action-btn-danger"
        title="Delete"
        @click.stop="$emit('delete', video)"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 6h18"/>
          <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
          <line x1="10" y1="11" x2="10" y2="17"/>
          <line x1="14" y1="11" x2="14" y2="17"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.gallery-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.2s, transform 0.15s;
  position: relative;
}

.gallery-card:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
}

.card-clickable {
  cursor: pointer;
}

.gallery-thumb {
  width: 100%;
  aspect-ratio: 16/9;
  object-fit: cover;
  display: block;
  background: var(--surface2);
}

.gallery-thumb-placeholder {
  width: 100%;
  aspect-ratio: 16/9;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1e1e2e 0%, #2a2a3a 100%);
  color: var(--text2);
  font-size: 2rem;
}

.gallery-card-body {
  padding: 12px 14px;
  padding-bottom: 8px;
}

.video-model {
  font-weight: 600;
  font-size: 0.9rem;
  margin-bottom: 4px;
}

.video-prompt {
  font-size: 0.8rem;
  color: var(--text2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.video-meta {
  font-size: 0.75rem;
  color: var(--text2);
  margin-top: 6px;
  display: flex;
  gap: 8px;
}

.card-actions {
  display: flex;
  gap: 4px;
  padding: 8px 14px 12px;
  justify-content: flex-end;
  border-top: 1px solid var(--border);
  background: var(--bg);
}

.action-btn {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  cursor: pointer;
  color: var(--text2);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.action-btn:hover {
  background: var(--surface2);
  color: var(--text);
  border-color: var(--accent);
}

.action-btn-danger:hover {
  color: var(--red);
  border-color: var(--red);
}
</style>
