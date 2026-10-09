import { ref, watch, inject } from 'vue'
import {
  fetchProject,
  deleteVideo,
  deleteJob,
  archiveJob,
  unarchiveJob,
  bulkMoveJobs,
  addFavourite,
  removeFavourite,
} from './useApi'

/**
 * Shared composable for video list panels (Gallery, Archive): loading,
 * delete, favourites, (un)archive, and select mode with bulk move/delete.
 *
 * @param {Object} props - Component props (must include `project` and `active`)
 * @param {Object} options
 * @param {boolean} options.archived - Whether to fetch archived or non-archived videos
 * @param {Function} options.emit - Component emit function
 */
export function useVideoList(props, { archived, emit }) {
  const showToast = inject('showToast')
  const videos = ref([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const data = await fetchProject(props.project, { archived })
      videos.value = data.videos || []
    } catch (err) {
      const label = archived ? 'archived videos' : 'videos'
      showToast(`Failed to load ${label}`, 'error')
      videos.value = []
    } finally {
      loading.value = false
    }
  }

  async function handleDelete(video) {
    if (!confirm('Delete this video permanently?')) return
    try {
      await deleteVideo(props.project, video.filename)
      videos.value = videos.value.filter(v => v.filename !== video.filename)
      emit('video-deleted', video.filename)
      showToast('Video deleted', 'success')
    } catch (err) {
      showToast('Failed to delete video', 'error')
    }
  }

  function openVideo(video) {
    emit('open-video', video)
  }

  function handleRegenerate(video) {
    emit('regenerate', video)
  }

  async function handleToggleFavourite(video) {
    await toggleFavourite(video, showToast)
  }

  function getVideoByFilename(filename) {
    return videos.value.find(v => v.filename === filename)
  }

  function removeVideo(filename) {
    videos.value = videos.value.filter(v => v.filename !== filename)
  }

  const plural = n => `${n} video${n !== 1 ? 's' : ''}`

  // Archive / unarchive one card — either way it leaves this list
  async function setArchived(video, archive) {
    const verb = archive ? 'archive' : 'unarchive'
    if (!video.job?.job_id) return showToast(`Cannot ${verb}: no job ID`, 'error')
    try {
      await (archive ? archiveJob : unarchiveJob)(video.job.job_id)
      removeVideo(video.filename)
      showToast(`Video ${verb}d`, 'success')
    } catch (err) {
      showToast(`Failed to ${verb}`, 'error')
    }
  }

  // ── Select mode ──
  const selectMode = ref(false)
  const selectedFilenames = ref(new Set())
  const selectedVideos = () => videos.value.filter(v => selectedFilenames.value.has(v.filename))

  function toggleSelectMode() {
    selectMode.value = !selectMode.value
    if (!selectMode.value) selectedFilenames.value = new Set()
  }

  function toggleSelect(video) {
    const next = new Set(selectedFilenames.value)
    next.has(video.filename) ? next.delete(video.filename) : next.add(video.filename)
    selectedFilenames.value = next
  }

  // Move modal — holds the job IDs to move (single card or bulk selection)
  const showMoveModal = ref(false)
  const pendingMoveJobIds = ref([])

  function openMoveModal(jobIds) {
    pendingMoveJobIds.value = jobIds
    showMoveModal.value = true
  }

  function handleCardMove(video) {
    if (!video.job?.job_id) return showToast('Cannot move: no job ID', 'error')
    openMoveModal([video.job.job_id])
  }

  function handleBulkMove() {
    openMoveModal(
      selectedVideos()
        .map(v => v.job?.job_id)
        .filter(Boolean),
    )
  }

  async function handleMove(targetProject) {
    showMoveModal.value = false
    const jobIds = pendingMoveJobIds.value
    if (!jobIds.length) return
    const movedFilenames = new Set(videos.value.filter(v => jobIds.includes(v.job?.job_id)).map(v => v.filename))
    try {
      await bulkMoveJobs(jobIds, targetProject)
      videos.value = videos.value.filter(v => !movedFilenames.has(v.filename))
      selectedFilenames.value = new Set([...selectedFilenames.value].filter(f => !movedFilenames.has(f)))
      if (selectedFilenames.value.size === 0) selectMode.value = false
      showToast(`Moved ${plural(jobIds.length)}`, 'success')
    } catch (err) {
      showToast('Failed to move videos', 'error')
    }
  }

  async function handleBulkDelete() {
    const toDelete = selectedVideos()
    if (!toDelete.length) return
    if (!confirm(`Delete ${plural(toDelete.length)} permanently?`)) return
    const results = await Promise.allSettled(
      toDelete.map(v => (v.job?.job_id ? deleteJob(v.job.job_id) : Promise.reject())),
    )
    const deletedFilenames = new Set(toDelete.filter((_, i) => results[i].status === 'fulfilled').map(v => v.filename))
    videos.value = videos.value.filter(v => !deletedFilenames.has(v.filename))
    selectedFilenames.value = new Set()
    selectMode.value = false
    showToast(`Deleted ${plural(deletedFilenames.size)}`, 'success')
  }

  // Load when active or when project changes
  watch(
    [() => props.active, () => props.project],
    ([active]) => {
      if (active) load()
    },
    { immediate: true },
  )

  return {
    videos,
    loading,
    load,
    handleDelete,
    openVideo,
    handleRegenerate,
    handleToggleFavourite,
    getVideoByFilename,
    removeVideo,
    showToast,
    handleArchive: video => setArchived(video, true),
    handleUnarchive: video => setArchived(video, false),
    selectMode,
    selectedFilenames,
    toggleSelectMode,
    toggleSelect,
    showMoveModal,
    pendingMoveJobIds,
    handleCardMove,
    handleBulkMove,
    handleMove,
    handleBulkDelete,
  }
}

/** Star / unstar one generated file (updates `video.favourite` in place). */
export async function toggleFavourite(video, showToast) {
  const starring = !video.favourite
  if (starring && !video.job?.job_id) return showToast('Cannot favourite: no job record', 'error')
  video.favourite = starring // optimistic
  try {
    if (starring) await addFavourite(video.job.job_id, video.filename)
    else await removeFavourite(video.filename)
  } catch {
    video.favourite = !starring
    showToast(`Failed to ${starring ? 'add to' : 'remove from'} favourites`, 'error')
  }
}
