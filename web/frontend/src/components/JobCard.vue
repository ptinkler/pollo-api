<script setup>
import { ref, computed, watch } from 'vue'
import { getVideoThumbUrl, getFilenameFromPath } from '../composables/useApi'
import { PROCESSING_STATUSES } from '../composables/useJobsQueue'

const props = defineProps({
  job: { type: Object, required: true },
  project: { type: String, default: '' }
})

defineEmits(['download', 'view-video', 'delete', 'check'])

const isProcessing = (status) => PROCESSING_STATUSES.includes(status)

const thumbError = ref(false)

const thumbUrl = computed(() => {
  if (!props.job.video_path || !props.job.video_exists || !props.project) return null
  const filename = getFilenameFromPath(props.job.video_path)
  return getVideoThumbUrl(props.project, filename)
})

// Reset thumb error when video becomes available (e.g., after download)
watch(() => [props.job.video_exists, props.job.video_path], () => {
  if (props.job.video_exists && props.job.video_path) {
    thumbError.value = false
  }
})


function handleThumbError() {
  thumbError.value = true
}
</script>

<template>
  <div :class="['job-card', job.status]" :data-job-id="job.job_id">
    <!-- Thumbnail -->
    <div v-if="thumbUrl && !thumbError" class="job-thumb" @click.stop="$emit('view-video', getFilenameFromPath(job.video_path))">
      <img :src="thumbUrl" alt="" @error="handleThumbError" />
    </div>
    <div v-else class="dot"></div>

    <div class="job-info">
      <div class="job-model">{{ job.model }}</div>
      <div class="job-message">{{ job.message }}</div>
      <div class="job-links">
        <a
          href="https://pollo.ai/api-platform/logs"
          target="_blank"
          class="job-link"
          @click.stop
        >
          {{ job.job_id }}
        </a>
        <a
          v-if="job.video_path && job.video_exists"
          href="#"
          class="job-link filename-link"
          @click.prevent.stop="$emit('view-video', getFilenameFromPath(job.video_path))"
        >
          📁 {{ getFilenameFromPath(job.video_path) }}
        </a>
      </div>
    </div>
    <div class="job-date">
      {{ job.created_at ? new Date(job.created_at).toLocaleString() : '' }}
    </div>

    <!-- Credits used -->
    <div class="job-credits" :title="job.status === 'error' ? 'Failed - no credits charged' : 'Credits used'">
      <span class="credits-value">{{ job.status === 'error' ? '0' : (job.credits_used ?? '—') }}</span>
      <span class="credits-label">cr</span>
    </div>

    <!-- Action buttons -->
    <button
      v-if="job.status === 'done' && job.video_url && !job.video_exists"
      class="btn btn-secondary btn-small"
      @click.stop="$emit('download', job.job_id)"
    >
      📥 Download
    </button>

    <!-- Spinner for processing jobs -->
    <div v-else-if="isProcessing(job.status)" class="processing-spinner" title="Polling..."></div>

    <!-- Retry/check button for transient errors (when there's a remote task to check) -->
    <button
      v-else-if="job.status === 'error' && job.task_id"
      class="btn btn-secondary btn-small"
      title="Check remote task status / retry download"
      @click.stop="$emit('check', job.job_id)"
    >
      🔁 Retry
    </button>

    <span class="badge">{{ job.status }}</span>

    <button
      class="btn-delete"
      title="Delete job and video"
      @click.stop="$emit('delete', job.job_id)"
    >
      🗑️
    </button>
  </div>
</template>

<style scoped>
.job-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.job-thumb {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.2s, transform 0.15s;
}

.job-thumb:hover {
  border-color: var(--accent);
  transform: scale(1.05);
}

.job-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--yellow);
  animation: pulse 1.5s ease-in-out infinite;
  flex-shrink: 0;
}

.job-card.done .dot {
  background: var(--green);
  animation: none;
}

.job-card.error .dot {
  background: var(--red);
  animation: none;
}

.job-card.downloading .dot {
  background: var(--accent);
}

.job-info {
  flex: 1;
  min-width: 0;
}

.job-model {
  font-weight: 600;
}

.job-message {
  font-size: 0.85rem;
  color: var(--text2);
}

.job-links {
  font-size: 0.75rem;
  margin-top: 4px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.job-link {
  color: var(--accent2);
  text-decoration: none;
  font-family: monospace;
}

.job-link:hover {
  text-decoration: underline;
  color: var(--accent);
}

.job-date {
  font-size: 0.78rem;
  color: var(--text2);
  white-space: nowrap;
}

.job-credits {
  display: flex;
  align-items: baseline;
  gap: 2px;
  flex-shrink: 0;
}

.credits-value {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent, #6366f1);
}

.credits-label {
  font-size: 0.7rem;
  color: var(--text2);
}

.job-card.error .credits-value {
  color: var(--text2);
}

.btn-small {
  padding: 5px 10px;
  font-size: 0.75rem;
  flex-shrink: 0;
}

.processing-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.btn-delete {
  background: none;
  border: none;
  cursor: pointer;
  opacity: 0.4;
  font-size: 0.9rem;
  padding: 4px;
  transition: opacity 0.2s;
  flex-shrink: 0;
}

.btn-delete:hover {
  opacity: 1;
}
</style>
