<script setup>
import { computed } from 'vue'
import { getImageUrl } from '../composables/useApi'

const props = defineProps({
  project: { type: Object, required: true },
  showArchive: { type: Boolean, default: true },
  showUnarchive: { type: Boolean, default: false }
})

defineEmits(['click', 'archive', 'unarchive', 'delete'])
</script>

<template>
  <div class="project-card">
    <div class="card-clickable" @click="$emit('click', project)">
      <div v-if="project.has_image" class="project-thumb">
        <img
          :src="getImageUrl(project.slug, project.thumb_ts)"
          :alt="project.name"
          @error="$event.target.style.display = 'none'"
        />
      </div>
      <div v-else-if="project.image_url" class="project-thumb">
        <img :src="project.image_url" :alt="project.name" />
      </div>
      <div v-else class="project-thumb-placeholder">
        <div class="prompt-preview">{{ project.prompt || 'No prompt' }}</div>
      </div>

      <div class="project-card-body">
        <div class="project-name">{{ project.name }}</div>
        <div class="project-meta">
          <span class="badge">{{ project.video_count }} video{{ project.video_count !== 1 ? 's' : '' }}</span>
        </div>
      </div>
    </div>

    <div class="card-actions">
      <button
        v-if="showArchive"
        class="action-btn"
        title="Archive"
        @click.stop="$emit('archive', project)"
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
        @click.stop="$emit('unarchive', project)"
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
        @click.stop="$emit('delete', project)"
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
.project-card {
  display: block;
  text-decoration: none;
  color: inherit;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.2s, transform 0.15s;
}

.project-card:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
}

.card-clickable {
  cursor: pointer;
}

.project-thumb {
  width: 100%;
  aspect-ratio: 4/3;
  background: var(--surface2);
  overflow: hidden;
}

.project-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.project-thumb-placeholder {
  width: 100%;
  aspect-ratio: 4/3;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: linear-gradient(135deg, #1e1e2e 0%, #2a2a3a 100%);
  overflow: hidden;
}

.prompt-preview {
  font-size: 0.9rem;
  line-height: 1.5;
  color: var(--text2);
  text-align: center;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-style: italic;
}

.project-card-body {
  padding: 12px 14px;
  padding-bottom: 8px;
}

.project-name {
  font-weight: 600;
  font-size: 0.95rem;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-meta {
  font-size: 0.78rem;
  color: var(--text2);
  display: flex;
  gap: 10px;
  align-items: center;
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
