<script setup>
import { ref, computed, watch, inject, onUnmounted } from 'vue'
import JobCard from '../../components/JobCard.vue'
import { fetchJobs, fetchJob, downloadJobVideo as downloadVideo, deleteJob, checkJob } from '../../composables/useApi'
import { PROCESSING_STATUSES } from '../../composables/useJobsQueue'

const props = defineProps({
  project: { type: String, required: true },
  active: { type: Boolean, default: false }
})

const emit = defineEmits(['view-video', 'job-complete', 'video-deleted'])
const showToast = inject('showToast')

const jobs = ref([])
const loading = ref(false)
const pollingJobs = ref(new Set()) // Track which jobs are being polled
const pollTimers = ref({}) // Store timer IDs for cleanup

const jobStats = computed(() => {
  const total = jobs.value.length
  const done = jobs.value.filter(j => j.status === 'done').length
  const error = jobs.value.filter(j => j.status === 'error').length
  const active = total - done - error
  return { total, done, error, active }
})


async function loadHistory() {
  loading.value = true
  try {
    jobs.value = await fetchJobs({ project: props.project })

    // Auto-poll any processing jobs
    jobs.value
      .filter(j => PROCESSING_STATUSES.includes(j.status))
      .forEach(j => startPolling(j.job_id))
  } catch (err) {
    showToast('Failed to load history', 'error')
    jobs.value = []
  } finally {
    loading.value = false
  }
}

function startPolling(jobId) {
  if (pollingJobs.value.has(jobId)) return // Already polling
  pollingJobs.value.add(jobId)
  pollJob(jobId)
}

function stopPolling(jobId) {
  pollingJobs.value.delete(jobId)
  if (pollTimers.value[jobId]) {
    clearTimeout(pollTimers.value[jobId])
    delete pollTimers.value[jobId]
  }
}

function stopAllPolling() {
  pollingJobs.value.forEach(jobId => stopPolling(jobId))
}

async function pollJob(jobId) {
  if (!pollingJobs.value.has(jobId)) return // Polling was stopped

  try {
    const result = await fetchJob(jobId)
    updateJobInList(jobId, result)

    if (result.status === 'done') {
      stopPolling(jobId)
      if (result.video_url && !result.video_exists) {
        showToast('Job complete! Click to download video.', 'success')
      } else if (result.video_exists && result.filename) {
        showToast('Job complete!', 'success')
        // Notify parent that a new video is ready
        emit('job-complete', result)
      } else {
        showToast('Job complete!', 'success')
      }
    } else if (result.status === 'error') {
      stopPolling(jobId)
      showToast('Job failed: ' + result.message, 'error')
    } else {
      // Still processing, poll again in 10 seconds
      pollTimers.value[jobId] = setTimeout(() => pollJob(jobId), 10000)
    }
  } catch (err) {
    // Network error, retry in 10 seconds
    pollTimers.value[jobId] = setTimeout(() => pollJob(jobId), 10000)
  }
}

async function handleDownload(jobId) {
  try {
    await downloadVideo(jobId)
    showToast('Video downloaded!', 'success')
    // Fetch fresh job data to ensure we have all updated fields
    const freshJob = await fetchJob(jobId)
    updateJobInList(jobId, freshJob)
    // Notify parent that a new video is ready
    if (freshJob.video_exists && freshJob.filename) {
      emit('job-complete', freshJob)
    }
  } catch (err) {
    showToast('Download failed: ' + err, 'error')
  }
}

async function handleCheck(jobId) {
  // Manually trigger the server-side check/recovery endpoint for a failed job.
  try {
    showToast('Checking job status...', 'info')
    const updated = await checkJob(jobId)
    updateJobInList(jobId, updated)

    if (updated.status && PROCESSING_STATUSES.includes(updated.status)) {
      // If the check moved the job back into processing, start polling it
      startPolling(jobId)
      showToast('Job resumed: now processing', 'success')
    } else if (updated.status === 'downloading' || updated.status === 'done') {
      // If download started or completed, refresh and notify
      if (updated.status === 'downloading') {
        showToast('Download started (recovered job)', 'success')
      } else {
        showToast('Job completed after recovery', 'success')
        emit('job-complete', updated)
      }
    } else if (updated.status === 'error') {
      showToast('Job still failed: ' + (updated.message || ''), 'error')
    } else {
      showToast('Job status updated', 'info')
    }
  } catch (err) {
    showToast('Check failed: ' + err, 'error')
  }
}

function updateJobInList(jobId, updates) {
  const index = jobs.value.findIndex(j => j.job_id === jobId)
  if (index > -1) {
    // Create a new array to ensure Vue reactivity
    jobs.value = [
      ...jobs.value.slice(0, index),
      { ...jobs.value[index], ...updates },
      ...jobs.value.slice(index + 1)
    ]
  }
}

function handleViewVideo(filename) {
  emit('view-video', filename)
}

async function handleDelete(jobId) {
  if (!confirm('Delete this job and its video?')) return

  // Find the job to get its filename before deleting
  const job = jobs.value.find(j => j.job_id === jobId)
  const filename = job?.filename

  stopPolling(jobId)
  try {
    await deleteJob(jobId)
    jobs.value = jobs.value.filter(j => j.job_id !== jobId)
    showToast('Job deleted', 'success')
    // Notify parent to remove video from gallery/archive
    if (filename) {
      emit('video-deleted', filename)
    }
  } catch (err) {
    showToast('Failed to delete job', 'error')
  }
}

// Load when active or when project changes, stop polling when inactive
watch([() => props.active, () => props.project], ([active]) => {
  // Always stop old polling when anything changes
  stopAllPolling()
  if (active) {
    loadHistory()
  }
}, { immediate: true })

// Cleanup on unmount
onUnmounted(() => {
  stopAllPolling()
})
</script>

<template>
  <div class="history-panel">
    <div v-if="loading" class="loading">
      <p>Loading...</p>
    </div>

    <div v-else-if="!jobs.length" class="empty-state">
      <h3>No generations yet</h3>
      <p>Run a generation to see history</p>
    </div>

    <div v-else class="history-list">
      <div class="history-summary">
        <span class="summary-total">{{ jobStats.total }} generation{{ jobStats.total !== 1 ? 's' : '' }}</span>
        <span class="summary-done">{{ jobStats.done }} ✓</span>
        <span v-if="jobStats.error" class="summary-error">{{ jobStats.error }} ✗</span>
        <span v-if="jobStats.active" class="summary-active">{{ jobStats.active }} running</span>
      </div>
      <JobCard
        v-for="job in jobs"
        :key="job.job_id"
        :job="job"
        :project="project"
        @download="handleDownload"
        @view-video="handleViewVideo"
        @delete="handleDelete"
        @check="handleCheck"
      />
    </div>
  </div>
</template>

<style scoped>
.history-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 0.82rem;
}

.summary-total {
  color: var(--text2);
  font-weight: 500;
  margin-right: auto;
}

.summary-done {
  color: var(--green, #22c55e);
  font-weight: 600;
}

.summary-error {
  color: var(--red, #ef4444);
  font-weight: 600;
}

.summary-active {
  color: var(--accent, #6366f1);
  font-weight: 500;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>

