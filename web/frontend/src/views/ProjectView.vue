<script setup>
import { ref, computed, watch, onMounted, onUnmounted, inject } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'
import GeneratePanel from './panels/GeneratePanel.vue'
import GalleryPanel from './panels/GalleryPanel.vue'
import HistoryPanel from './panels/HistoryPanel.vue'
import ArchivePanel from './panels/ArchivePanel.vue'
import VideoModal from '../components/VideoModal.vue'
import { fetchProject, fetchModels, archiveJob, unarchiveJob, archiveProject, unarchiveProject, deleteProject } from '../composables/useApi'
import { useJobsQueue } from '../composables/useJobsQueue'

const props = defineProps({
  project: { type: String, required: true }
})

const router = useRouter()
const route = useRoute()
const showToast = inject('showToast')

const { onJobComplete } = useJobsQueue()

const projectData = ref(null)
const models = ref({})

// Modal state
const selectedVideo = ref(null)
const modalVisible = ref(false)

// Regenerate state - holds job data to apply to generate panel
const regenerateJob = ref(null)

// Use-as-ref state - holds ref data to prefill in generate panel
const useAsRefData = ref(null)

// Gallery ref for video lookup
const galleryRef = ref(null)
const archiveRef = ref(null)

// Current tab from route - check matched routes for nested route meta
const activeTab = computed(() => {
  // Find the deepest matched route with a tab meta
  const matched = route.matched
  for (let i = matched.length - 1; i >= 0; i--) {
    if (matched[i].meta?.tab) {
      return matched[i].meta.tab
    }
  }
  return 'gallery'
})

// Video filename from route (for direct linking)
const videoFilename = computed(() => route.params.videoFilename)

const tabs = [
  { id: 'gallery', label: 'Gallery', route: 'project-gallery' },
  { id: 'generate', label: 'Generate', route: 'project-generate' },
  { id: 'history', label: 'History', route: 'project-history' },
  { id: 'archive', label: 'Archive', route: 'project-archive' }
]

async function loadProject() {
  try {
    projectData.value = await fetchProject(props.project)
    // Update page title with display name
    if (projectData.value?.name) {
      document.title = `${projectData.value.name} — Pollo`
    }
  } catch {
    projectData.value = { prompt: '', image_url: '', video_url: '', subject_url: '', audio_url: '' }
  }
}

async function loadModels() {
  try {
    models.value = await fetchModels()
  } catch (err) {
    showToast('Failed to load models', 'error')
  }
}


function openVideoModal(video) {
  selectedVideo.value = video
  modalVisible.value = true
  // Update URL to include video filename
  router.push({
    name: 'project-video',
    params: { project: props.project, videoFilename: video.filename }
  })
}

function closeVideoModal() {
  modalVisible.value = false
  selectedVideo.value = null
  // Go back to gallery without video in URL
  router.push({ name: 'project-gallery', params: { project: props.project } })
}

function handleRegenerate(video) {
  // Store the job settings for the generate panel to use
  if (video?.job) {
    regenerateJob.value = video.job
  }
  // Close modal if open
  if (modalVisible.value) {
    modalVisible.value = false
    selectedVideo.value = null
  }
  // Navigate to generate tab
  router.push({ name: 'project-generate', params: { project: props.project } })
}

function handleUseAsRef(video) {
  const job = video?.job || {}
  const refs = []
  let order = 1

  const isImage = job.media_type === 'image' || job.job_type === 'image'
  if (job.video_url) {
    refs.push({ type: isImage ? 'image' : 'video', name: isImage ? 'imgref1' : 'vidref1', url: job.video_url, order: order++ })
  }

  useAsRefData.value = {
    refs,
    prompt: job.prompt || '',
  }

  // Close modal if open
  if (modalVisible.value) {
    modalVisible.value = false
    selectedVideo.value = null
  }
  // Navigate to generate tab
  router.push({ name: 'project-generate', params: { project: props.project } })
}

function handleVideoDeleted(filename) {
  closeVideoModal()
  removeVideoFromPanels(filename)
}

const isProjectArchived = computed(() => !!projectData.value?.archived)

async function handleModalToggleArchive(video, archive) {
  if (!video?.job?.job_id) {
    showToast(`Cannot ${archive ? 'archive' : 'unarchive'}: no job ID`, 'error')
    return
  }
  try {
    if (archive) {
      await archiveJob(video.job.job_id)
    } else {
      await unarchiveJob(video.job.job_id)
    }
    closeVideoModal()
    removeVideoFromPanels(video.filename)
    showToast(`Video ${archive ? 'archived' : 'unarchived'}`, 'success')
  } catch (err) {
    showToast(`Failed to ${archive ? 'archive' : 'unarchive'} video`, 'error')
  }
}

function handleModalArchive(video) {
  handleModalToggleArchive(video, true)
}

function handleModalUnarchive(video) {
  handleModalToggleArchive(video, false)
}

async function handleArchiveProject() {
  const action = isProjectArchived.value ? 'Unarchive' : 'Archive'
  try {
    if (isProjectArchived.value) {
      await unarchiveProject(props.project)
    } else {
      await archiveProject(props.project)
    }
    showToast(`Project ${action.toLowerCase()}d`, 'success')
    router.push('/')
  } catch (err) {
    showToast(`Failed to ${action.toLowerCase()} project`, 'error')
  }
}

async function handleDeleteProject() {
  if (!confirm('Delete this project? This cannot be undone.')) return
  try {
    await deleteProject(props.project)
    showToast('Project deleted', 'success')
    router.push('/')
  } catch (err) {
    showToast('Failed to delete project', 'error')
  }
}

function removeVideoFromPanels(filename) {
  // Remove from gallery or archive without full refresh
  if (galleryRef.value?.removeVideo) {
    galleryRef.value.removeVideo(filename)
  }
  if (archiveRef.value?.removeVideo) {
    archiveRef.value.removeVideo(filename)
  }
}

// Track filenames we've already added via completion events (sync guard against race conditions)
const recentlyAddedFilenames = new Set()

function handleJobComplete(job) {
  // Add new video to gallery if it has a filename and isn't already there
  if (job.filename && galleryRef.value?.addVideo) {
    // Synchronous guard: prevent duplicate adds from concurrent event sources
    if (recentlyAddedFilenames.has(job.filename)) return
    // Also check the gallery's reactive list
    if (galleryRef.value.getVideoByFilename(job.filename)) return

    recentlyAddedFilenames.add(job.filename)
    // Clean up after a delay to avoid unbounded growth
    setTimeout(() => recentlyAddedFilenames.delete(job.filename), 30000)

    // Build video object matching gallery format
    const video = {
      filename: job.filename,
      job: job
    }
    galleryRef.value.addVideo(video)
  }
}

function viewVideoFromHistory(filename) {
  // Navigate to gallery with specific video
  router.push({
    name: 'project-video',
    params: { project: props.project, videoFilename: filename }
  })
}

// Watch for video filename in route to open modal
watch(videoFilename, async (filename) => {
  if (filename && activeTab.value === 'gallery') {
    // Wait for gallery to load, then find and open video
    await new Promise(resolve => setTimeout(resolve, 100))
    if (galleryRef.value?.getVideoByFilename) {
      const video = galleryRef.value.getVideoByFilename(filename)
      if (video) {
        selectedVideo.value = video
        modalVisible.value = true
      }
    }
  }
}, { immediate: true })

// Load project when it changes
watch(() => props.project, () => {
  loadProject()
}, { immediate: true })

// Subscribe to global job completions so gallery updates regardless of active tab
let unsubJobComplete = null
onMounted(() => {
  loadModels()
  unsubJobComplete = onJobComplete((job) => {
    // Only add videos for the current project
    if (job.project === props.project && job.filename && job.video_exists) {
      handleJobComplete(job)
    }
  })
})

onUnmounted(() => {
  if (unsubJobComplete) unsubJobComplete()
})
</script>

<template>
  <div class="project-view">
    <div class="project-header">
      <RouterLink to="/" class="back-btn">
        <span class="back-arrow">←</span>
        <span class="back-text">Projects</span>
      </RouterLink>
      <div class="header-divider"></div>
      <h2>{{ projectData?.name || 'Loading...' }}</h2>
      <div class="header-actions">
        <button class="header-action-btn" :title="isProjectArchived ? 'Unarchive project' : 'Archive project'" @click="handleArchiveProject">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 8v13H3V8"/>
            <path d="M1 3h22v5H1z"/>
            <path d="M10 12h4"/>
          </svg>
          {{ isProjectArchived ? 'Unarchive' : 'Archive' }}
        </button>
        <button class="header-action-btn header-action-btn-danger" title="Delete project" @click="handleDeleteProject">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18"/>
            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
            <line x1="10" y1="11" x2="10" y2="17"/>
            <line x1="14" y1="11" x2="14" y2="17"/>
          </svg>
          Delete
        </button>
      </div>
    </div>

    <div class="tabs">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.id"
        :to="{ name: tab.route, params: { project: project } }"
        :class="['tab', { active: activeTab === tab.id }]"
      >
        {{ tab.label }}
      </RouterLink>
    </div>

    <GeneratePanel
      v-show="activeTab === 'generate'"
      :project="project"
      :project-data="projectData"
      :models="models"
      :regenerate-job="regenerateJob"
      :use-as-ref="useAsRefData"
      @regenerate-applied="regenerateJob = null"
      @use-as-ref-applied="useAsRefData = null"
    />

    <GalleryPanel
      v-show="activeTab === 'gallery'"
      ref="galleryRef"
      :project="project"
      :active="activeTab === 'gallery'"
      @open-video="openVideoModal"
      @regenerate="handleRegenerate"
      @use-as-ref="handleUseAsRef"
    />

    <HistoryPanel
      v-show="activeTab === 'history'"
      :project="project"
      :active="activeTab === 'history'"
      @view-video="viewVideoFromHistory"
      @job-complete="handleJobComplete"
      @video-deleted="removeVideoFromPanels"
    />

    <ArchivePanel
      v-show="activeTab === 'archive'"
      ref="archiveRef"
      :project="project"
      :active="activeTab === 'archive'"
      @open-video="openVideoModal"
      @regenerate="handleRegenerate"
      @use-as-ref="handleUseAsRef"
    />

    <VideoModal
      :video="selectedVideo"
      :project="project"
      :visible="modalVisible"
      @close="closeVideoModal"
      @regenerate="handleRegenerate"
      @use-as-ref="handleUseAsRef"
      @archive="handleModalArchive"
      @unarchive="handleModalUnarchive"
      @deleted="handleVideoDeleted"
    />
  </div>
</template>

<style scoped>
.project-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: linear-gradient(145deg, rgba(30, 30, 35, 0.9), rgba(25, 25, 30, 0.95));
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--text2);
  cursor: pointer;
  font-size: 0.85rem;
  padding: 8px 14px;
  border-radius: 8px;
  text-decoration: none;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.back-btn:hover {
  color: var(--text);
  border-color: rgba(108, 92, 231, 0.4);
  background: linear-gradient(145deg, rgba(40, 38, 50, 0.9), rgba(32, 30, 40, 0.95));
}

.back-arrow {
  font-size: 1rem;
  line-height: 1;
}

.back-text {
  font-weight: 500;
}

.header-divider {
  width: 1px;
  height: 24px;
  background: rgba(255, 255, 255, 0.1);
}

.project-header h2 {
  font-size: 1.3rem;
  font-weight: 600;
  color: var(--text);
}

.header-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.header-action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text2);
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 500;
  padding: 6px 12px;
  border-radius: 7px;
  transition: all 0.2s;
}

.header-action-btn:hover {
  background: var(--surface2);
  color: var(--text);
  border-color: var(--accent);
}

.header-action-btn-danger:hover {
  color: var(--red);
  border-color: var(--red);
}

.tabs {
  display: flex;
  gap: 4px;
  background: linear-gradient(145deg, rgba(22, 22, 28, 0.95), rgba(18, 18, 22, 0.98));
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-radius: 10px;
  padding: 4px;
  margin-bottom: 24px;
}

.tab {
  padding: 10px 20px;
  border-radius: 7px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text2);
  transition: all 0.2s;
  border: none;
  background: none;
  text-decoration: none;
}

.tab:hover {
  color: var(--text);
  background: rgba(255, 255, 255, 0.04);
}

.tab.active {
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  color: white;
  box-shadow: 0 2px 8px rgba(108, 92, 231, 0.3);
}
</style>
