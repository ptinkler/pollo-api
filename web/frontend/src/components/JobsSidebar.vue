<script setup>
import { onUnmounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { useJobsQueue, TERMINAL_STATUSES } from '../composables/useJobsQueue'
import { getVideoThumbUrl, getFilenameFromPath } from '../composables/useApi'

const showToast = inject('showToast')
const router = useRouter()

const {
  activeJobs,
  runningJobs,
  hasRunningJobs,
  dismissJob,
  dismissAllCompleted,
  cleanup,
  setNotifyCallback
} = useJobsQueue()

// Set up toast notifications for job events
setNotifyCallback((message, type, duration) => {
  showToast(message, type, duration)
})

function getStatusIcon(status) {
  switch (status) {
    case 'done': return '✓'
    case 'error': return '✗'
    default: return ''
  }
}

function videoFilename(job) {
  return getFilenameFromPath(job.videoPath)
}

function thumbUrl(job) {
  const fname = videoFilename(job)
  if (!fname || !job.project) return null
  return getVideoThumbUrl(job.project, fname)
}

function openVideo(job) {
  const fname = videoFilename(job)
  if (fname && job.project) {
    router.push({
      name: 'project-video',
      params: { project: job.project, videoFilename: fname }
    })
  }
}

function openHistory(job) {
  if (job.project) {
    router.push({
      name: 'project-history',
      params: { project: job.project }
    })
  }
}

onUnmounted(() => {
  cleanup()
})
</script>

<template>
  <aside class="jobs-sidebar">
    <div class="sidebar-header">
      <span class="header-title">
        <span class="header-icon">⚡</span>
        <span>Generations</span>
      </span>
      <span v-if="hasRunningJobs" class="running-badge">{{ runningJobs.length }}</span>
    </div>

    <div class="sidebar-content">
      <div class="jobs-list">
        <div
          v-for="job in activeJobs"
          :key="job.jobId"
          :class="['job-item', job.status]"
        >
          <div class="job-left">
            <div v-if="!TERMINAL_STATUSES.includes(job.status)" class="job-spinner"></div>
            <div v-else class="job-icon">{{ getStatusIcon(job.status) }}</div>
          </div>

          <div class="job-info" @click="job.status === 'done' ? openVideo(job) : job.status === 'error' ? openHistory(job) : null">
            <div class="job-header">
              <span class="job-model">{{ job.model }}</span>
            </div>
            <div class="job-prompt">{{ job.prompt }}</div>
            <div class="job-status">{{ job.message }}</div>
            <img
              v-if="job.status === 'done' && thumbUrl(job)"
              :src="thumbUrl(job)"
              alt="Video thumbnail"
              class="job-thumb"
              @click.stop="openVideo(job)"
            />
          </div>

          <button
            v-if="TERMINAL_STATUSES.includes(job.status)"
            class="job-dismiss"
            @click.stop="dismissJob(job.jobId)"
            title="Dismiss"
          >×</button>
        </div>
      </div>

      <div v-if="activeJobs.some(j => TERMINAL_STATUSES.includes(j.status))" class="sidebar-footer">
        <button class="clear-btn" @click="dismissAllCompleted">
          Clear completed
        </button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.jobs-sidebar {
  width: 280px;
  flex-shrink: 0;
  background: var(--surface);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: sticky;
  top: 0;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  border-bottom: 1px solid var(--border);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text);
}

.header-icon {
  font-size: 1rem;
}

.running-badge {
  background: var(--accent);
  color: white;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  min-width: 20px;
  text-align: center;
}

.sidebar-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.jobs-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.job-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  background: var(--bg);
  border-radius: 10px;
  margin-bottom: 8px;
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.job-item.done .job-info,
.job-item.error .job-info {
  cursor: pointer;
}

.job-item.done .job-info:hover,
.job-item.error .job-info:hover {
  opacity: 0.8;
}

.job-item.error {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.2);
}

.job-left {
  flex-shrink: 0;
  width: 18px;
  display: flex;
  justify-content: center;
  padding-top: 2px;
}

.job-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.job-icon {
  font-size: 0.9rem;
  font-weight: bold;
}

.job-item.done .job-icon {
  color: var(--green);
}

.job-item.error .job-icon {
  color: var(--red);
}

.job-info {
  flex: 1;
  min-width: 0;
}

.job-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.job-model {
  font-size: 0.68rem;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.job-prompt {
  font-size: 0.82rem;
  color: var(--text);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.job-status {
  font-size: 0.72rem;
  color: var(--text2);
  margin-top: 4px;
}

.job-thumb {
  width: 100%;
  margin-top: 8px;
  border-radius: 6px;
  cursor: pointer;
  object-fit: cover;
  aspect-ratio: 16 / 9;
  background: var(--surface2);
  transition: opacity 0.15s;
}

.job-thumb:hover {
  opacity: 0.85;
}

.job-dismiss {
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  font-size: 1.1rem;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1;
  flex-shrink: 0;
  opacity: 0.5;
  transition: opacity 0.2s;
}

.job-dismiss:hover {
  opacity: 1;
  color: var(--text);
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--border);
}

.clear-btn {
  width: 100%;
  padding: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text2);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}

.clear-btn:hover {
  background: var(--surface2);
  color: var(--text);
  border-color: rgba(255, 255, 255, 0.1);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>

