import { ref, computed } from 'vue'
import { fetchJob, fetchJobs, downloadJobVideo } from './useApi'

// Global state - shared across all components
const activeJobs = ref([])
const pollIntervals = {}
const isMinimized = ref(false)
const isInitialized = ref(false)

const TERMINAL_STATUSES = ['done', 'error']
const PROCESSING_STATUSES = ['queued', 'creating', 'sending', 'processing', 'downloading']

function truncatePrompt(text, maxLen = 60) {
  if (!text) return ''
  return text.substring(0, maxLen) + (text.length > maxLen ? '...' : '')
}

// Callback for notifications
let notifyCallback = null
// Callbacks for job completion/error (with full job data)
const completionCallbacks = new Set()
const errorCallbacks = new Set()

function setNotifyCallback(callback) {
  notifyCallback = callback
}

function onJobComplete(callback) {
  completionCallbacks.add(callback)
  return () => completionCallbacks.delete(callback)
}

function onJobError(callback) {
  errorCallbacks.add(callback)
  return () => errorCallbacks.delete(callback)
}

// Computed
const runningJobs = computed(() =>
  activeJobs.value.filter(j => !TERMINAL_STATUSES.includes(j.status))
)

const hasRunningJobs = computed(() => runningJobs.value.length > 0)

// Functions
function addJob(jobId, model, prompt, project) {
  const newJob = {
    jobId,
    model,
    prompt: truncatePrompt(prompt),
    project,
    status: 'sending',
    message: 'Starting...',
    videoPath: null,
    errorShown: false,
    addedAt: Date.now()
  }
  activeJobs.value.unshift(newJob)
  startPolling(jobId)
  return newJob
}

function startPolling(jobId) {
  if (pollIntervals[jobId]) return

  // Poll immediately, then every 10 seconds
  pollJob(jobId)
  pollIntervals[jobId] = setInterval(() => pollJob(jobId), 10000)
}

function stopPolling(jobId) {
  if (pollIntervals[jobId]) {
    clearInterval(pollIntervals[jobId])
    delete pollIntervals[jobId]
  }
}

async function pollJob(jobId) {
  const jobIndex = activeJobs.value.findIndex(j => j.jobId === jobId)
  if (jobIndex === -1) {
    stopPolling(jobId)
    return
  }

  try {
    const job = await fetchJob(jobId)
    // Re-find index in case array was modified during async call
    const currentIndex = activeJobs.value.findIndex(j => j.jobId === jobId)
    if (currentIndex === -1) {
      stopPolling(jobId)
      return
    }
    const activeJob = activeJobs.value[currentIndex]

    activeJob.status = job.status
    activeJob.message = job.message

    if (job.status === 'done') {
      if (job.video_path) {
        activeJob.videoPath = job.video_path
      }

      // If done but no video file yet, trigger download and keep polling
      if (!job.video_exists && !job.video_path && job.video_url && !activeJob._downloadTriggered) {
        activeJob._downloadTriggered = true
        activeJob.message = 'Downloading video...'
        try {
          await downloadJobVideo(job.job_id)
        } catch {
          // Backend will handle it, keep polling
        }
        return  // Keep polling until video is available
      }

      stopPolling(jobId)
      // Notify
      if (notifyCallback) {
        notifyCallback('Video ready! 🎉', 'success')
      }
      // Notify completion listeners with full job data
      for (const cb of completionCallbacks) {
        cb(job)
      }
      return
    }

    if (job.status === 'error') {
      stopPolling(jobId)
      // Notify only once
      if (!activeJob.errorShown && notifyCallback) {
        notifyCallback('Generation failed: ' + job.message, 'error', 5000)
        activeJob.errorShown = true
      }
      // Notify error listeners
      for (const cb of errorCallbacks) {
        cb(job)
      }
      return
    }
  } catch (err) {
    // If job was deleted/not found (404), remove it from the sidebar
    if (err?.message?.includes('404')) {
      stopPolling(jobId)
      activeJobs.value = activeJobs.value.filter(j => j.jobId !== jobId)
    }
    // Other network errors - keep polling
  }
}

function dismissJob(jobId) {
  stopPolling(jobId)
  activeJobs.value = activeJobs.value.filter(j => j.jobId !== jobId)
}

function dismissAllCompleted() {
  const completed = activeJobs.value.filter(j => TERMINAL_STATUSES.includes(j.status))
  completed.forEach(j => stopPolling(j.jobId))
  activeJobs.value = activeJobs.value.filter(j => !TERMINAL_STATUSES.includes(j.status))
}

function toggleMinimized() {
  isMinimized.value = !isMinimized.value
}

// Initialize - fetch active jobs from server
async function initialize() {
  if (isInitialized.value) return
  isInitialized.value = true

  try {
    // Fetch jobs that are still running
    const jobs = await fetchJobs({ active: true })

    for (const job of jobs) {
      // Only add if not already in queue
      if (!activeJobs.value.find(j => j.jobId === job.job_id)) {
        const existingJob = {
          jobId: job.job_id,
          model: job.model,
          prompt: truncatePrompt(job.prompt),
          project: job.project,
          status: job.status,
          message: job.message,
          videoPath: job.video_path,
          errorShown: false,
          addedAt: new Date(job.created_at).getTime()
        }
        activeJobs.value.push(existingJob)

        // Resume polling for non-terminal jobs
        if (!TERMINAL_STATUSES.includes(job.status)) {
          startPolling(job.job_id)
        }
      }
    }

    // Sort by addedAt descending
    activeJobs.value.sort((a, b) => b.addedAt - a.addedAt)
  } catch (err) {
    console.error('Failed to fetch active jobs:', err)
  }
}

// Cleanup all polling
function cleanup() {
  Object.keys(pollIntervals).forEach(stopPolling)
}

export { TERMINAL_STATUSES, PROCESSING_STATUSES }

export function useJobsQueue() {
  return {
    // State
    activeJobs,
    isMinimized,

    // Computed
    runningJobs,
    hasRunningJobs,

    // Methods
    addJob,
    dismissJob,
    dismissAllCompleted,
    toggleMinimized,
    initialize,
    cleanup,
    setNotifyCallback,
    onJobComplete,
    onJobError
  }
}

