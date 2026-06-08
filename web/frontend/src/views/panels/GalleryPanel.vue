<script setup>
import { ref } from 'vue'
import VideoCard from '../../components/VideoCard.vue'
import MoveToProjectModal from '../../components/MoveToProjectModal.vue'
import { archiveJob, bulkMoveJobs, deleteJob } from '../../composables/useApi'
import { useVideoList } from '../../composables/useVideoList'

const props = defineProps({
  project: { type: String, required: true },
  active: { type: Boolean, default: false }
})

const emit = defineEmits(['open-video', 'regenerate', 'use-as-ref', 'video-deleted'])

const {
  videos, loading, load,
  handleDelete, openVideo, handleRegenerate,
  getVideoByFilename, removeVideo, showToast,
} = useVideoList(props, { archived: false, emit })

// Selection state
const selectMode = ref(false)
const selectedFilenames = ref(new Set())

// Move modal — holds the job IDs to move (single card or bulk selection)
const showMoveModal = ref(false)
const pendingMoveJobIds = ref([])

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) selectedFilenames.value = new Set()
}

function toggleSelect(video) {
  const next = new Set(selectedFilenames.value)
  next.has(video.filename) ? next.delete(video.filename) : next.add(video.filename)
  selectedFilenames.value = next
}

function openMoveModal(jobIds) {
  pendingMoveJobIds.value = jobIds
  showMoveModal.value = true
}

function handleCardMove(video) {
  if (!video.job?.job_id) { showToast('Cannot move: no job ID', 'error'); return }
  openMoveModal([video.job.job_id])
}

function handleBulkMove() {
  const jobIds = videos.value
    .filter(v => selectedFilenames.value.has(v.filename))
    .map(v => v.job?.job_id)
    .filter(Boolean)
  openMoveModal(jobIds)
}

async function handleMove(targetProject) {
  showMoveModal.value = false
  const jobIds = pendingMoveJobIds.value
  if (!jobIds.length) return
  // Filenames to remove from the list
  const movedFilenames = new Set(
    videos.value.filter(v => jobIds.includes(v.job?.job_id)).map(v => v.filename)
  )
  try {
    await bulkMoveJobs(jobIds, targetProject)
    videos.value = videos.value.filter(v => !movedFilenames.has(v.filename))
    selectedFilenames.value = new Set([...selectedFilenames.value].filter(f => !movedFilenames.has(f)))
    if (selectedFilenames.value.size === 0) selectMode.value = false
    showToast(`Moved ${jobIds.length} video${jobIds.length !== 1 ? 's' : ''}`, 'success')
  } catch (err) {
    showToast('Failed to move videos', 'error')
  }
}

async function handleBulkDelete() {
  const toDelete = videos.value.filter(v => selectedFilenames.value.has(v.filename))
  if (!toDelete.length) return
  if (!confirm(`Delete ${toDelete.length} video${toDelete.length !== 1 ? 's' : ''} permanently?`)) return
  const results = await Promise.allSettled(
    toDelete.map(v => v.job?.job_id ? deleteJob(v.job.job_id) : Promise.reject())
  )
  const deleted = toDelete.filter((_, i) => results[i].status === 'fulfilled')
  const deletedFilenames = new Set(deleted.map(v => v.filename))
  videos.value = videos.value.filter(v => !deletedFilenames.has(v.filename))
  selectedFilenames.value = new Set()
  selectMode.value = false
  showToast(`Deleted ${deleted.length} video${deleted.length !== 1 ? 's' : ''}`, 'success')
}

async function handleArchive(video) {
  if (!video.job?.job_id) { showToast('Cannot archive: no job ID', 'error'); return }
  try {
    await archiveJob(video.job.job_id)
    videos.value = videos.value.filter(v => v.filename !== video.filename)
    showToast('Video archived', 'success')
  } catch (err) {
    showToast('Failed to archive', 'error')
  }
}

function addVideo(video) {
  if (videos.value.some(v => v.filename === video.filename)) return
  videos.value = [video, ...videos.value]
}

function refresh() { load() }

defineExpose({ refresh, getVideoByFilename, removeVideo, addVideo })
</script>

<template>
  <div class="gallery-panel">
    <div v-if="loading" class="loading">
      <p>Loading...</p>
    </div>

    <template v-else-if="videos.length">
      <div class="panel-toolbar">
        <button class="btn btn-secondary toolbar-btn" @click="toggleSelectMode">
          {{ selectMode ? 'Cancel' : 'Select' }}
        </button>
      </div>

      <div v-if="selectMode && selectedFilenames.size > 0" class="selection-bar">
        <span>{{ selectedFilenames.size }} selected</span>
        <div class="selection-actions">
          <button class="btn btn-primary" @click="handleBulkMove">Move to project</button>
          <button class="btn btn-danger" @click="handleBulkDelete">Delete</button>
        </div>
      </div>

      <div class="gallery-grid">
        <VideoCard
          v-for="video in videos"
          :key="video.filename"
          :video="video"
          :project="project"
          :show-archive="!selectMode"
          :show-unarchive="false"
          :show-move="!selectMode"
          :selectable="selectMode"
          :selected="selectedFilenames.has(video.filename)"
          @click="openVideo"
          @regenerate="handleRegenerate"
          @use-as-ref="(v) => emit('use-as-ref', v)"
          @archive="handleArchive"
          @move="handleCardMove"
          @delete="handleDelete"
          @toggle-select="toggleSelect"
        />
      </div>
    </template>

    <div v-else class="empty-state">
      <h3>No videos yet</h3>
      <p>Generate one first</p>
    </div>

    <MoveToProjectModal
      :visible="showMoveModal"
      :current-project="project"
      :count="pendingMoveJobIds.length"
      @move="handleMove"
      @close="showMoveModal = false"
    />
  </div>
</template>

<style scoped>
.panel-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.toolbar-btn {
  font-size: 0.8rem;
  padding: 5px 12px;
}

.selection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--surface);
  border: 1px solid var(--accent);
  border-radius: 8px;
  padding: 8px 14px;
  margin-bottom: 12px;
  font-size: 0.9rem;
  color: var(--text2);
}

.selection-actions {
  display: flex;
  gap: 8px;
}
</style>
